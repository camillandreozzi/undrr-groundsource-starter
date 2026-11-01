"""Unit tests for Experiment B: configurations, schemas, normaliser, windows, runner, scorer.

An ablation is only interpretable if each configuration differs from `full` by
exactly the text it claims to remove, and if `full` is production. So the first
tests pin `full` to prompt 5 byte for byte and check every transform against
the sections it leaves alone. The scorer tests then check the two readings and
the paired bootstrap on windows built from text, as Experiment A's tests do.
"""
from __future__ import annotations

import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT, REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from ablation.configs import (  # noqa: E402
    CONFIGS, RECIPES, AblationError, _replace_once, build_config, check_prompts, parse_sections,
)
from ablation.normalise_hazards import VOCABULARY, normalise_hazard  # noqa: E402
from ablation.runner import SPEC, extract_one, load_progress, plan_jobs, run, run_dir  # noqa: E402
from ablation.schemas import build_schema  # noqa: E402
from ablation.score_ablation import (  # noqa: E402
    ALL_COUNTERS, ALL_METRICS, WindowCache, _named, delta, drop_reason, extra_counts,
    location_traceable, shared_weights,
)
from benchmark_openrouter.run_openrouter import extract_document  # noqa: E402
from eval.event_matching import GoldEvent, PredEvent  # noqa: E402
from eval.score_event_level import COUNTERS, score_window  # noqa: E402
from fonte.app_event_focus import (  # noqa: E402
    OUTPUT_HEADERS, DocumentEventExtractions, DocumentRow, extraction_to_output_rows,
)
from fonte.prompts import (  # noqa: E402
    PREVENTIONWEB_HAZARD_INSTRUCTION, UNIFIED_VERIFICATION_RECALL_SYSTEM_PROMPT,
    UNIFIED_VERIFICATION_RECALL_USER_INSTRUCTION, get_prompt,
)
from openai.lib._parsing._completions import type_to_response_format_param  # noqa: E402

TWO_EVENTS = (
    "Annual report. In 2020, severe floods inundated large parts of Thailand, displacing "
    "thousands of families. Separately, a prolonged drought struck India in 2022, causing "
    "crop losses across several states. The agency coordinated relief in both cases.")


def gold(i, hazard, year, locations, quotes):
    return GoldEvent.from_row({
        "asset_key": "k", "gold_event_id": str(i), "hazard_primary": hazard,
        "hazard_secondary": "", "year_start": str(year), "year_end": "",
        "locations": locations, "support_quotes": quotes, "verifiable": "yes"})


def pred(i, hazard, dates, locations, evidence=""):
    return PredEvent.from_row({
        "asset_key": "k", "event_index": str(i), "event_hazard": hazard,
        "event_dates": dates, "affected_locations": locations,
        "evidence_snippets": evidence}, i)


def event(**kw):
    base = {"is_single_actual_event": False, "is_verifiable_event": True,
            "event_hazard": "Flood", "event_dates": ["2020"], "affected_locations": ["Bangkok"],
            "location_admin_levels": ["city"], "key_impacts": ["homes damaged"],
            "event_confidence": "high", "evidence_snippets": ["severe floods inundated"],
            "missing_information": []}
    return {**base, **kw}


# Every branch of the post-filter: kept, unverifiable, low, capitalised, missing
# hazard, a duplicate of the first, and a second distinct event.
RAW_EVENTS = [
    event(),
    event(is_verifiable_event=False),
    event(event_confidence="low"),
    event(event_confidence="High"),
    event(event_hazard=None),
    event(event_dates=[" 2020 "], affected_locations=["bangkok"]),
    event(event_hazard="Drought and Desertification", event_dates=["2022"],
          affected_locations=["India"], location_admin_levels=[]),
]


def doc(key="k", text=TWO_EVENTS):
    return DocumentRow(asset_key=key, source_id=1, attachment_id=None, asset_url=None,
                       asset_type=None, status=None, extraction_method=None,
                       char_count=len(text), text=text, last_processed_at=None, title="t",
                       publication_year="2023", language="English", countries=None,
                       themes=None, hazards="Flood", organizations=None, content_url=None)


class FakeClient:
    """Records each `parse` call and answers with a fixed raw payload."""

    def __init__(self, raw=None, parsed_none=False):
        self.calls = []
        self.raw = raw if raw is not None else {"events": RAW_EVENTS}
        self.parsed_none = parsed_none
        self.chat = NS(completions=NS(parse=self.parse))

    def parse(self, **kw):
        self.calls.append(kw)
        text = json.dumps(self.raw)
        parsed = None if self.parsed_none else kw["response_format"].model_validate_json(text)
        return NS(choices=[NS(message=NS(parsed=parsed, content=text), finish_reason="stop")],
                  usage=None, model="openai/gpt-5", provider="OpenAI", id="gen-1")


# ---------------------------------------------------------------------------
# Configurations
# ---------------------------------------------------------------------------

class FullIsProductionTests(unittest.TestCase):
    def test_full_prompt_is_prompt_5(self):
        cfg = build_config("full")
        self.assertIs(cfg.prompt, get_prompt(5))
        self.assertEqual(cfg.prompt.system_prompt, UNIFIED_VERIFICATION_RECALL_SYSTEM_PROMPT)
        self.assertEqual(cfg.prompt.user_instruction, UNIFIED_VERIFICATION_RECALL_USER_INSTRUCTION)

    def test_full_hash_matches_the_september_run(self):
        from ablation.configs import manifest
        self.assertEqual(manifest(build_config("full"))["system_sha16"], "cfbf35634b527da4")

    def test_full_schema_is_the_production_class(self):
        self.assertIs(build_config("full").schema, DocumentEventExtractions)

    def test_sections_join_back(self):
        sections = parse_sections()
        self.assertEqual("".join(sections.values()), UNIFIED_VERIFICATION_RECALL_SYSTEM_PROMPT)
        self.assertEqual(sections["hazard"],
                         f"Hazard classification:\n{PREVENTIONWEB_HAZARD_INSTRUCTION}\n\n")

    def test_rendered_prompts_are_in_sync(self):
        self.assertEqual(check_prompts(), [])


class TransformTests(unittest.TestCase):
    def kept_equal(self, name, changed):
        """Every section outside `changed` is byte-equal to production's."""
        full = parse_sections()
        system = build_config(name).prompt.system_prompt
        for section, text in full.items():
            if section not in changed:
                self.assertIn(text, system, f"{name} altered {section}")

    def test_no_evidence(self):
        cfg = build_config("no_evidence")
        self.assertNotIn("evidence_snippets", cfg.prompt.system_prompt)
        self.assertNotIn("evidence item", cfg.prompt.system_prompt)
        self.assertIn("key_impacts must be grounded in the source", cfg.prompt.system_prompt)
        self.assertEqual(cfg.prompt.user_instruction, UNIFIED_VERIFICATION_RECALL_USER_INSTRUCTION)
        self.kept_equal("no_evidence", {"evidence", "confidence"})

    def test_no_vocab(self):
        system = build_config("no_vocab").prompt.system_prompt
        for gone in ("Main PreventionWeb hazard labels", "no exact PreventionWeb label fits",
                     "Normalize common source terms"):
            self.assertNotIn(gone, system)
        self.assertIn("short description of the hazard", system)
        self.kept_equal("no_vocab", {"hazard"})

    def test_reduced_rules(self):
        cfg = build_config("reduced_rules")
        system = cfg.prompt.system_prompt
        for gone in ("Use prompt 3 / prompt 4", "Reject forecasts", "Date rules:",
                     "Location rules:", "Confidence and verifiability:", "is_single_actual_event:",
                     "Omit passing mentions", "country-level rule above", "satisfies these rules"):
            self.assertNotIn(gone, system)
        self.assertIn(PREVENTIONWEB_HAZARD_INSTRUCTION, system)
        self.assertIn("key_impacts and evidence_snippets must be grounded", system)
        self.assertNotEqual(cfg.prompt.user_instruction, UNIFIED_VERIFICATION_RECALL_USER_INSTRUCTION)
        self.kept_equal("reduced_rules", {"preamble", "search_scope", "evidence", "date",
                                          "location", "admin", "confidence", "single_event",
                                          "return"})

    def test_bare_is_the_same_in_every_order(self):
        base = build_config("bare")
        for order in itertools.permutations(RECIPES["bare"]):
            cfg = build_config("bare", order=order)
            self.assertEqual(cfg.prompt.system_prompt, base.prompt.system_prompt, order)
            self.assertEqual(cfg.prompt.user_instruction, base.prompt.user_instruction)
            self.assertIs(cfg.schema, base.schema)

    def test_replace_once_refuses_a_missing_or_repeated_target(self):
        with self.assertRaises(AblationError):
            _replace_once("a b", "c", "d")
        with self.assertRaises(AblationError):
            _replace_once("a a", "a", "d")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def _event_schema(schema):
    fmt = type_to_response_format_param(schema)["json_schema"]
    return fmt, fmt["schema"]["$defs"]["EventExtraction"]


class SchemaTests(unittest.TestCase):
    def test_every_schema_is_strict_and_named_as_production(self):
        _, prod = _event_schema(DocumentEventExtractions)
        for name in CONFIGS:
            fmt, ev = _event_schema(build_config(name).schema)
            self.assertEqual(fmt["name"], "DocumentEventExtractions")
            self.assertTrue(fmt["strict"])
            self.assertEqual(list(fmt["schema"]["$defs"]), ["EventExtraction"])
            self.assertEqual(ev["required"], list(ev["properties"]))
            self.assertFalse(ev["additionalProperties"])
            expected = [p for p in prod["properties"]
                        if not (p == "evidence_snippets" and name in ("no_evidence", "bare"))]
            self.assertEqual(list(ev["properties"]), expected, name)

    def test_no_evidence_differs_only_by_the_field(self):
        _, prod = _event_schema(DocumentEventExtractions)
        _, ev = _event_schema(build_config("no_evidence").schema)
        trimmed = {k: v for k, v in prod["properties"].items() if k != "evidence_snippets"}
        self.assertEqual(ev["properties"], trimmed)

    def test_neutral_descriptions_carry_no_rules(self):
        _, ev = _event_schema(build_config("reduced_rules").schema)
        text = json.dumps(ev)
        for rule in ("Phase 2", "publication", "Chernobyl", "downwind", "explicitly stated"):
            self.assertNotIn(rule, text)
        self.assertIn("high, medium, low", ev["properties"]["event_confidence"]["description"])

    def test_post_filter_is_identical_across_schemas(self):
        def kept(schema):
            out = schema.model_validate({"events": RAW_EVENTS})
            return [(e.event_hazard, e.event_dates, e.location_admin_levels) for e in out.events]
        want = kept(DocumentEventExtractions)
        self.assertEqual(len(want), 2)
        self.assertEqual(want[1][2], ["unknown"])        # admin levels padded
        for name in CONFIGS:
            self.assertEqual(kept(build_config(name).schema), want, name)

    def test_output_rows_keep_the_contract(self):
        for name in CONFIGS:
            extraction = build_config(name).schema.model_validate({"events": RAW_EVENTS})
            rows = extraction_to_output_rows(doc(), extraction)
            self.assertEqual(set(rows[0]), set(OUTPUT_HEADERS))
            if name in ("no_evidence", "bare"):
                self.assertTrue(all(r["evidence_snippets"] == "" for r in rows))

    def test_drop_reason_agrees_with_the_validator(self):
        seen: set = set()
        reasons = [drop_reason(e, seen) for e in RAW_EVENTS]
        self.assertEqual(reasons, [None, "drop_unverifiable", "drop_confidence", "drop_confidence",
                                   "drop_missing", "drop_duplicate", None])
        kept = DocumentEventExtractions.model_validate({"events": RAW_EVENTS}).events
        self.assertEqual(len(kept), reasons.count(None))


# ---------------------------------------------------------------------------
# Hazard normalisation
# ---------------------------------------------------------------------------

class NormaliserTests(unittest.TestCase):
    def test_identity_on_exact_labels_and_compounds(self):
        for label in VOCABULARY:
            n = normalise_hazard(label)
            self.assertEqual(n.value, label)
            self.assertFalse(n.changed)
        for compound in ("Earthquake | Tsunami", "Tsunami | Earthquake",
                         "Cyclone, Hurricane and Typhoon | Flood | Landslide"):
            self.assertEqual(normalise_hazard(compound).value, compound)

    def test_every_label_is_in_the_prompt(self):
        for label in VOCABULARY:
            self.assertIn(label, PREVENTIONWEB_HAZARD_INSTRUCTION)

    def test_prompt_table_examples(self):
        cases = {
            "typhoon": "Cyclone, Hurricane and Typhoon", "storm surge": "Cyclone, Hurricane and Typhoon",
            "volcanic eruption": "Volcano", "disease outbreak": "Epidemic and pandemic",
            "heat-wave": "Heatwave and Extreme Heat", "locust outbreak": "Insect infestation",
            "gas leak": "Nuclear, biological, chemical (NBC)", "dam failure": "Technological hazard",
            "debris flow": "Landslide", "flash flooding": "Flood",
            "fall armyworm infestation": "Fall armyworm", "earthquake and tsunami":
            "Earthquake | Tsunami", "flood": "Flood",
        }
        for raw, want in cases.items():
            self.assertEqual(normalise_hazard(raw).value, want, raw)

    def test_unmapped_passes_through(self):
        n = normalise_hazard("Severe storm")
        self.assertEqual(n.value, "Severe storm")
        self.assertEqual(n.unmapped, ("Severe storm",))
        self.assertEqual(normalise_hazard("Population explosion").unmapped, ("Population explosion",))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class RunnerTests(unittest.TestCase):
    def test_full_sends_the_production_request(self):
        a, b = FakeClient(), FakeClient()
        extract_document(a, doc(), SPEC, get_prompt(5), {})
        extract_one(b, doc(), SPEC, build_config("full"))
        self.assertEqual(a.calls, b.calls)

    def test_ablations_send_their_own_prompt_and_schema(self):
        client = FakeClient()
        cfg = build_config("bare")
        extract_one(client, doc(), SPEC, cfg)
        call = client.calls[0]
        self.assertEqual(call["messages"][0]["content"], cfg.prompt.system_prompt)
        self.assertTrue(call["messages"][1]["content"].startswith(cfg.prompt.user_instruction))
        self.assertIs(call["response_format"], cfg.schema)
        self.assertEqual(call["extra_body"]["reasoning"], {"effort": "medium"})

    def test_a_refusal_raises_instead_of_falling_back(self):
        client = FakeClient(parsed_none=True)
        with self.assertRaises(ValueError):
            extract_one(client, doc(), SPEC, build_config("full"))
        self.assertEqual(len(client.calls), 1)

    def test_run_writes_outputs_and_resumes(self):
        docs = [doc("a"), doc("b")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run(["full", "no_evidence"], 2, docs, out_root=root, workers=2,
                client_factory=FakeClient)
            d = run_dir(root, "no_evidence", 2)
            stats = json.loads((d / "run_stats.json").read_text())
            self.assertEqual((stats["documents_finished"], stats["events"]), (2, 4))
            self.assertEqual(stats["providers"], {"OpenAI": 2})
            self.assertTrue((d / "raw" / "a.json").exists())
            rows = [json.loads(l) for l in (d / "event_extractions.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 4)
            self.assertEqual(plan_jobs(["full", "no_evidence"], 2, docs, root), [])

            # An error record is re-queued; the retry supersedes it.
            with (d / "progress.jsonl").open("a") as f:
                f.write(json.dumps({"asset_key": "b", "error": True, "rows": []}) + "\n")
            pending = plan_jobs(["no_evidence"], 2, docs, root)
            self.assertEqual([(j.rep, j.doc.asset_key) for j in pending], [(2, "b")])
            run(["no_evidence"], 2, docs, out_root=root, workers=1, client_factory=FakeClient)
            self.assertFalse(load_progress(d)["b"]["error"])

    def test_job_order_is_seeded(self):
        docs = [doc(k) for k in "abcdef"]
        with tempfile.TemporaryDirectory() as tmp:
            a = plan_jobs(list(CONFIGS), 2, docs, Path(tmp))
            b = plan_jobs(list(CONFIGS), 2, docs, Path(tmp))
        self.assertEqual([(j.config, j.rep, j.doc.asset_key) for j in a],
                         [(j.config, j.rep, j.doc.asset_key) for j in b])
        self.assertEqual(len(a), len(CONFIGS) * 2 * 6)


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

class WindowTests(unittest.TestCase):
    def test_frozen_windows_match_a_rebuild(self):
        import csv
        from ablation.build_windows import OUT, build_windows
        rows, summary = build_windows()
        with OUT.open(newline="", encoding="utf-8") as f:
            frozen = list(csv.DictReader(f))
        self.assertEqual([{k: str(v) for k, v in r.items()} for r in rows], frozen)
        self.assertEqual(summary["groups"], {"event_present": 44, "event_absent": 36})
        self.assertEqual(summary["subgroups"], {"single": 10, "multi": 34, "expA_none": 1,
                                                "random_negative": 30, "hard_negative": 5})

    def test_negatives_have_no_gold_events(self):
        import csv
        from ablation.build_windows import EXPA_GOLD, OUT
        with OUT.open(newline="", encoding="utf-8") as f:
            negatives = {r["asset_key"] for r in csv.DictReader(f) if r["source"] == "v2_negative"}
        with EXPA_GOLD.open(newline="", encoding="utf-8") as f:
            self.assertFalse(negatives & {r["asset_key"] for r in csv.DictReader(f)})


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

FLOOD_TH = gold(1, "Flood", 2020, "Thailand", "severe floods inundated large parts of Thailand")
DROUGHT_IN = gold(2, "Drought and Desertification", 2022, "India",
                  "a prolonged drought struck India in 2022")


def _vector(counts, extra=None):
    extra = extra or {}
    return np.array([counts.get(c, extra.get(c, 0)) for c in ALL_COUNTERS], dtype=float)


class ReadingTests(unittest.TestCase):
    def preds(self):
        return [pred(1, "Flood", "2020", "Thailand", "severe floods inundated large parts"),
                pred(2, "Drought and Desertification", "2022", "India",
                     "a prolonged drought struck India")]

    def score(self, preds):
        return score_window(preds, [FLOOD_TH, DROUGHT_IN], TWO_EVENTS, "s",
                            {"asset_key": "k"}, "multi")[0]

    def test_r2_links_on_years_and_places_only(self):
        import dataclasses
        r1 = self.score(self.preds())
        r2 = self.score([dataclasses.replace(p, snippets=()) for p in self.preds()])
        self.assertEqual((r1["tier_A"], r1["tier_C"]), (2, 0))
        self.assertEqual((r2["tier_A"], r2["tier_B"], r2["tier_C"]), (0, 0, 2))

    def test_pooled_counts_do_not_depend_on_the_reading(self):
        import dataclasses
        r1 = self.score(self.preds())
        r2 = self.score([dataclasses.replace(p, snippets=()) for p in self.preds()])
        for c in COUNTERS:
            if c.startswith(("ptp_", "pfp_", "pfn_")):
                self.assertEqual(r1[c], r2[c], c)

    def test_false_alarms_on_an_event_absent_window(self):
        cache = WindowCache({"k": TWO_EVENTS})
        preds = self.preds()
        rows = [{"event_hazard": p.hazards[0], "event_dates": p.dates} for p in preds]
        c, _ = extra_counts("k", rows, preds, True, cache, None)
        self.assertEqual((c["win_absent"], c["win_fa"], c["rec_absent"]), (1, 1, 2))
        # Both records are literally in the window and quote it: S3 sets them aside.
        self.assertEqual((c["fp_absent_literal"], c["win_fa_strict"]), (2, 0))
        c, _ = extra_counts("k", [], [], True, cache, None)
        self.assertEqual((c["win_fa"], c["rec_absent"]), (0, 0))

    def test_location_traceability_is_word_bounded(self):
        hay = " flooding in nigeria hit kano and lagos nigeria "
        self.assertFalse(location_traceable("Niger", hay))
        self.assertTrue(location_traceable("Nigeria", hay))
        self.assertTrue(location_traceable("Kano, Nigeria", hay))
        self.assertFalse(location_traceable("Abuja, Nigeria", hay))


class BootstrapTests(unittest.TestCase):
    def matrix(self):
        rng = np.random.default_rng(0)
        return rng.integers(0, 5, size=(12, len(ALL_COUNTERS))).astype(float)

    def test_delta_of_a_system_with_itself_is_zero(self):
        m = self.matrix()
        w = shared_weights([str(i) for i in range(12)], None, "all")
        for name, d in delta(m, m, w).items():
            if d["point"] == d["point"]:
                self.assertEqual((d["point"], d["lo"], d["hi"]), (0.0, 0.0, 0.0), name)

    def test_weights_are_seeded_and_respect_strata(self):
        keys = [str(i) for i in range(10)]
        strata = ["a"] * 4 + ["b"] * 6
        w1 = shared_weights(keys, strata, "all")
        w2 = shared_weights(keys, strata, "all")
        np.testing.assert_array_equal(w1, w2)
        self.assertTrue((w1.sum(axis=1) == 10).all())
        self.assertTrue((w1[:, :4].sum(axis=1) == 4).all())

    def test_metrics_cover_every_counter_name_they_use(self):
        totals = _named(np.ones(len(ALL_COUNTERS)))
        for name, fn in ALL_METRICS.items():
            fn(totals)      # a KeyError here is a metric reading a counter that is not kept


if __name__ == "__main__":
    unittest.main()
