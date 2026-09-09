"""Unit tests for the multi-model benchmark's own logic.

The parts worth testing here are the ones where a silent bug looks like a model
quality difference rather than a crash: the JSON recovery on the fallback path
(a model wrongly scored as failing), the output schema contract (a run the
existing scorers would reject), the resume rule (silently skipping documents
that errored), and the agreement arithmetic the report rests on.

Nothing here makes a network call.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_openrouter.agreement import pairwise  # noqa: E402
from benchmark_openrouter.models import ROSTER, select, slugify  # noqa: E402
from benchmark_openrouter.run_openrouter import (  # noqa: E402
    fallback_schema_text,
    strip_to_json,
)
from eval.score_against_human import Run  # noqa: E402
from fonte.app_event_focus import (  # noqa: E402
    DocumentEventExtractions,
    DocumentRow,
    OUTPUT_HEADERS,
    extraction_to_output_rows,
    is_error_row,
)


def _doc(key: str = "a" * 64) -> DocumentRow:
    return DocumentRow(
        asset_key=key, source_id=1, attachment_id=2, asset_url="u", asset_type="pdf",
        status="ok", extraction_method="m", char_count=10, text="t",
        last_processed_at="2026-01-01", title="T", publication_year="2020",
        language="English", countries="Chile", themes=None, hazards=None,
        organizations=None, content_url="c",
    )


class TestJsonRecovery(unittest.TestCase):
    """The fallback path sees whatever the model felt like emitting."""

    def test_plain_object(self):
        self.assertEqual(strip_to_json('{"events": []}'), '{"events": []}')

    def test_markdown_fence(self):
        for raw in ['```json\n{"events": []}\n```', '```\n{"events": []}\n```']:
            with self.subTest(raw=raw):
                self.assertEqual(json.loads(strip_to_json(raw)), {"events": []})

    def test_surrounding_prose(self):
        raw = 'Sure! Here is the extraction:\n{"events": []}\nLet me know if that helps.'
        self.assertEqual(json.loads(strip_to_json(raw)), {"events": []})

    def test_brace_inside_a_string_does_not_end_the_object(self):
        raw = '{"events": [{"event_hazard": "Flood }"}]}'
        self.assertEqual(json.loads(strip_to_json(raw))["events"][0]["event_hazard"],
                         "Flood }")

    def test_escaped_quote_inside_a_string(self):
        raw = r'{"events": [{"event_hazard": "a \" }"}]}'
        self.assertEqual(json.loads(strip_to_json(raw))["events"][0]["event_hazard"],
                         'a " }')

    def test_nested_objects(self):
        raw = 'text {"a": {"b": {"c": 1}}} trailing'
        self.assertEqual(json.loads(strip_to_json(raw)), {"a": {"b": {"c": 1}}})

    def test_non_object_is_left_for_the_caller_to_reject(self):
        # A bare string is valid JSON; the runner must catch it, not Pydantic.
        self.assertEqual(json.loads(strip_to_json('"just a string"')), "just a string")


class TestFallbackSchema(unittest.TestCase):
    def test_is_valid_json_and_describes_events(self):
        schema = json.loads(fallback_schema_text())
        self.assertEqual(schema["type"], "object")
        self.assertIn("events", schema["properties"])

    def test_descriptions_are_stripped(self):
        # The full descriptions triple the size and derailed a reasoning model.
        self.assertNotIn("description", fallback_schema_text())

    def test_every_extraction_field_survives(self):
        props = json.loads(fallback_schema_text())["$defs"]["EventExtraction"]["properties"]
        self.assertEqual(set(props), set(DocumentEventExtractions
                                         .model_fields["events"]
                                         .annotation.__args__[0].model_fields))


class TestOutputContract(unittest.TestCase):
    """Everything downstream depends on this schema being byte-identical."""

    def test_rows_match_output_headers_exactly(self):
        extraction = DocumentEventExtractions.model_validate({"events": [{
            "is_single_actual_event": True, "is_verifiable_event": True,
            "event_hazard": "Flood", "event_dates": ["2019"],
            "affected_locations": ["Beira"], "location_admin_levels": ["city"],
            "key_impacts": ["homes damaged"], "event_confidence": "high",
            "evidence_snippets": ["Beira was flooded"], "missing_information": [],
        }]})
        rows = extraction_to_output_rows(_doc(), extraction)
        self.assertEqual(list(rows[0]), OUTPUT_HEADERS)

    def test_empty_extraction_still_emits_one_row(self):
        rows = extraction_to_output_rows(_doc(), DocumentEventExtractions(events=[]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_count"], 0)
        self.assertEqual(list(rows[0]), OUTPUT_HEADERS)

    def test_post_filter_drops_unverifiable_events(self):
        # A model that ignores prompt 5's bar must not gain event count by it.
        extraction = DocumentEventExtractions.model_validate({"events": [
            {"is_single_actual_event": True, "is_verifiable_event": False,
             "event_hazard": "Flood", "event_dates": ["2019"],
             "affected_locations": ["Beira"], "location_admin_levels": ["city"],
             "key_impacts": [], "event_confidence": "high",
             "evidence_snippets": [], "missing_information": []},
            {"is_single_actual_event": True, "is_verifiable_event": True,
             "event_hazard": "Flood", "event_dates": ["2019"],
             "affected_locations": ["Beira"], "location_admin_levels": ["city"],
             "key_impacts": [], "event_confidence": "low",
             "evidence_snippets": [], "missing_information": []},
        ]})
        self.assertEqual(extraction.events, [])


class TestResumeRule(unittest.TestCase):
    """A document whose last attempt errored must be retried, not skipped."""

    @staticmethod
    def _succeeded(rows: list[dict]) -> bool:
        return bool(rows) and not any(is_error_row(r) for r in rows)

    def test_error_row_is_not_success(self):
        self.assertFalse(self._succeeded([{"key_impacts": "ERROR: 429 rate limit"}]))

    def test_good_row_is_success(self):
        self.assertTrue(self._succeeded([{"key_impacts": "homes damaged"}]))

    def test_no_rows_is_not_success(self):
        self.assertFalse(self._succeeded([]))

    def test_one_error_among_good_rows_requeues_the_document(self):
        self.assertFalse(self._succeeded([{"key_impacts": "ok"},
                                          {"key_impacts": "ERROR: timeout"}]))


class TestRoster(unittest.TestCase):
    def test_slugs_are_unique_and_filesystem_safe(self):
        slugs = [m.slug for m in ROSTER]
        self.assertEqual(len(slugs), len(set(slugs)))
        for s in slugs:
            self.assertRegex(s, r"^[a-z0-9-]+$")

    def test_slugify(self):
        self.assertEqual(slugify("anthropic/claude-opus-5"), "anthropic-claude-opus-5")
        self.assertEqual(slugify("openai/gpt-5.4"), "openai-gpt-5-4")

    def test_tiers_are_all_populated(self):
        for tier in ("frontier", "open", "small"):
            self.assertTrue(select(tier=tier), f"{tier} tier is empty")

    def test_off_roster_model_is_accepted(self):
        spec = select(models=["some/new-model"])[0]
        self.assertEqual(spec.id, "some/new-model")


class TestPairwiseAgreement(unittest.TestCase):
    """The agreement arithmetic the report rests on."""

    @staticmethod
    def _run(label: str, rows: list[dict]) -> Run:
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                         encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
            path = Path(f.name)
        return Run(label, path)

    @staticmethod
    def _row(key: str, hazard="Flood", locs="Beira", dates="2019", verifiable=True):
        return {"asset_key": key, "is_verifiable_event": verifiable,
                "event_hazard": hazard, "affected_locations": locs,
                "event_dates": dates, "location_admin_levels": "city"}

    def test_identical_runs_agree_perfectly(self):
        rows = [self._row("d1"), self._row("d2", hazard="Earthquake")]
        a, b = self._run("A", rows), self._run("B", rows)
        result = pairwise(a, b, ["d1", "d2"])
        self.assertEqual(result["detection_agreement"], 1.0)
        self.assertEqual(result["both"], 2)
        for f1 in result["sets"].values():
            self.assertEqual(f1, 1.0)

    def test_detection_disagreement_is_counted_directionally(self):
        # B attempted d2 and found nothing. In this schema that is still a row,
        # with is_verifiable_event false — which is what distinguishes it from
        # a document B never ran.
        a = self._run("A", [self._row("d1"), self._row("d2")])
        b = self._run("B", [self._row("d1"), self._row("d2", verifiable=False)])
        result = pairwise(a, b, ["d1", "d2"])
        self.assertEqual(result["n"], 2)
        self.assertEqual(result["both"], 1)
        self.assertEqual(result["a_only"], 1)
        self.assertEqual(result["b_only"], 0)
        self.assertEqual(result["detection_agreement"], 0.5)

    def test_a_document_one_run_never_attempted_is_excluded(self):
        # Otherwise an unfinished run reads as one that found nothing.
        a = self._run("A", [self._row("d1"), self._row("d2")])
        b = self._run("B", [self._row("d1")])
        result = pairwise(a, b, ["d1", "d2"])
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["detection_agreement"], 1.0)

    def test_a_document_neither_run_flags_counts_as_agreement(self):
        a = self._run("A", [self._row("d1", verifiable=False)])
        b = self._run("B", [self._row("d1", verifiable=False)])
        result = pairwise(a, b, ["d1"])
        self.assertEqual(result["neither"], 1)
        self.assertEqual(result["detection_agreement"], 1.0)

    def test_compound_hazards_are_split_before_folding(self):
        # "Earthquake | Tsunami" must cover both families, matching the scorer.
        a = self._run("A", [self._row("d1", hazard="Earthquake | Tsunami")])
        b = self._run("B", [self._row("d1", hazard="Earthquake")])
        # Both fold to the `earthquake` family, so this is full agreement.
        self.assertEqual(pairwise(a, b, ["d1"])["sets"]["hazard"], 1.0)

    def test_fuzzy_locations_beat_exact_on_qualifier_differences(self):
        # The common real disagreement: one model names the district, the other
        # the same place with a qualifier. token_set_ratio scores that 100.
        a = self._run("A", [self._row("d1", locs="Sindhupalchok District")])
        b = self._run("B", [self._row("d1", locs="Sindhupalchok")])
        result = pairwise(a, b, ["d1"])
        self.assertEqual(result["sets"]["location"], 0.0)
        self.assertEqual(result["sets"]["location_fuzzy"], 1.0)

    def test_fuzzy_matching_is_whitespace_tokenised_so_hyphens_still_miss(self):
        # Documents the limit of the shared `fuzzy_matched` helper rather than
        # working around it: "Port-au-Prince" is one token, so it scores 71
        # against "Port au Prince" and stays below the 90 threshold. Changing
        # this would silently move every number in eval/score_against_human.py.
        a = self._run("A", [self._row("d1", locs="Port-au-Prince")])
        b = self._run("B", [self._row("d1", locs="Port au Prince")])
        self.assertEqual(pairwise(a, b, ["d1"])["sets"]["location_fuzzy"], 0.0)

    def test_set_metrics_skip_documents_only_one_run_flagged(self):
        # Otherwise a run that finds nothing scores a free perfect hazard F1.
        a = self._run("A", [self._row("d1"), self._row("d2", hazard="Drought")])
        b = self._run("B", [self._row("d1")])
        self.assertEqual(pairwise(a, b, ["d1", "d2"])["sets"]["hazard"], 1.0)


if __name__ == "__main__":
    unittest.main()
