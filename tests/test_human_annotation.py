"""Unit tests for the human annotation queue and the scorer that reads it.

These cover the two places where a silent bug would not crash but would quietly
corrupt a comparison: the evidence locator (which decides whether a quote reads
as verbatim or as invented) and the document-level aggregation (which decides
whether precision measures the model or the sampling).
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT, REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from eval.human_annotation_app import (  # noqa: E402
    COLUMNS,
    AnnotationError,
    build_annotations,
    build_document_store,
    load_document_store,
    locate_snippet,
    render_document,
    write_csv_atomic,
)
from eval.prefetch_annotation_documents import queue_asset_keys  # noqa: E402
from eval.score_against_human import (  # noqa: E402
    Gold, Run, fuzzy_matched, mcc, mcnemar_exact, prf, score_run,
)
from fonte.hazard_families import hazard_family  # noqa: E402

DOC = ("The Federal Office activated the service. Rapid mapping and damage "
       "assessments after disaster events triggered the system in the context "
       "of floods on the Oder river in 2010. Recovery took two years.")


class LocateSnippetTests(unittest.TestCase):
    def test_verbatim_quote_is_exact(self):
        spans, kind = locate_snippet(DOC, "floods on the Oder river in 2010")
        self.assertEqual(kind, "exact")
        self.assertEqual(len(spans), 1)

    def test_line_breaks_do_not_break_a_quote(self):
        _, kind = locate_snippet("floods on the\n   Oder river", "floods on the Oder river")
        self.assertEqual(kind, "exact")

    def test_ellipsis_stitched_quote_locates_each_fragment(self):
        # Extractors join separated pieces with an ellipsis. Every piece is
        # verbatim; the string as a whole is not, and must not read as invented.
        spans, kind = locate_snippet(
            DOC, "The Federal Office activated... floods on the Oder river in 2010")
        self.assertEqual(kind, "exact")
        self.assertEqual(len(spans), 2)

    def test_partial_when_only_some_fragments_are_present(self):
        _, kind = locate_snippet(
            DOC, "The Federal Office activated... a tsunami warning was issued")
        self.assertEqual(kind, "partial")

    def test_absent_quote_is_none(self):
        _, kind = locate_snippet(DOC, "an earthquake struck the capital that night")
        self.assertEqual(kind, "none")

    def test_fragments_too_short_to_discriminate_are_ignored(self):
        _, kind = locate_snippet(DOC, "in 2010")
        self.assertEqual(kind, "none")

    def test_render_marks_and_escapes(self):
        html = render_document("Tom & Jerry saw floods on the Oder river",
                               ["floods on the Oder river"])
        self.assertIn("<mark", html)
        self.assertIn("Tom &amp; Jerry", html)


class BuildAnnotationsTests(unittest.TestCase):
    """The queue samples events; the annotation unit must be the document."""

    QUEUE_ROWS = [
        {"asset_key": "a", "event_index": "0", "event_count": "3", "in_queue": "Y",
         "review_rank": "2", "stratum": "high", "title": "A", "content_url": "u",
         "language": "English", "event_hazard": "Flood", "event_dates": "2019",
         "affected_locations": "Beira", "key_impacts": "", "evidence_snippets": ""},
        {"asset_key": "a", "event_index": "1", "event_count": "3", "in_queue": "Y",
         "review_rank": "5", "stratum": "high", "title": "A", "content_url": "u",
         "language": "English", "event_hazard": "Landslide", "event_dates": "2019",
         "affected_locations": "Sofala", "key_impacts": "", "evidence_snippets": ""},
        {"asset_key": "b", "event_index": "0", "event_count": "1", "in_queue": "N",
         "review_rank": "", "stratum": "low", "title": "B", "content_url": "",
         "language": "English", "event_hazard": "Drought and Desertification",
         "event_dates": "", "affected_locations": "", "key_impacts": "",
         "evidence_snippets": ""},
    ]

    def _queue(self, tmp: Path) -> Path:
        path = tmp / "queue.csv"
        write_csv_atomic(path, list(self.QUEUE_ROWS[0]), self.QUEUE_ROWS)
        return path

    def test_rows_are_collapsed_to_one_per_document(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            rows = build_annotations(self._queue(tmp), tmp / "ann.csv", tmp / "absent.jsonl")
        self.assertEqual([r["asset_key"] for r in rows], ["a"])
        self.assertEqual(rows[0]["queued_events"], "2")
        self.assertEqual(list(rows[0]), list(COLUMNS))

    def test_seed_merges_the_documents_events(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            rows = build_annotations(self._queue(tmp), tmp / "ann.csv", tmp / "absent.jsonl")
        self.assertEqual(rows[0]["seed_hazard"], "Flood | Landslide")
        self.assertEqual(rows[0]["seed_locations"], "Beira | Sofala")
        # A date shared by both events is listed once.
        self.assertEqual(rows[0]["seed_dates"], "2019")

    def test_seed_run_supplies_events_the_queue_did_not_sample(self):
        # The queue holds 2 of the document's 3 events; seeding from the queue
        # alone would bias an "accept seed as gold" click towards a short gold.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            run = tmp / "run.jsonl"
            run.write_text("\n".join(json.dumps(o) for o in [
                {"asset_key": "a", "is_verifiable_event": True, "event_hazard": "Flood",
                 "event_dates": "2019", "affected_locations": "Beira"},
                {"asset_key": "a", "is_verifiable_event": True, "event_hazard": "Landslide",
                 "event_dates": "2019", "affected_locations": "Sofala"},
                {"asset_key": "a", "is_verifiable_event": True, "event_hazard": "Cyclone",
                 "event_dates": "2019", "affected_locations": "Nampula"},
                {"asset_key": "a", "is_verifiable_event": False, "event_hazard": "Wildfire",
                 "event_dates": "", "affected_locations": "Nowhere"},
            ]), encoding="utf-8")
            rows = build_annotations(self._queue(tmp), tmp / "ann.csv", run)
        self.assertEqual(rows[0]["seed_event_count"], "3")
        self.assertIn("Nampula", rows[0]["seed_locations"])
        self.assertNotIn("Wildfire", rows[0]["seed_hazard"])


class DocumentStoreTests(unittest.TestCase):
    """The app reads a prefetched subset, never the 57 MB bulk parquet."""

    @staticmethod
    def _parquet(tmp: Path) -> Path:
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = tmp / "documents.parquet"
        pq.write_table(pa.table({
            "asset_key": ["a", "b", "c"],
            "text": ["alpha text", "beta text", "gamma text"],
            "char_count": [40000, 11, 12],
            "title": ["A", "B", "C"],
            "content_url": ["", "", ""],
        }), path)
        return path

    def test_store_holds_only_the_requested_documents(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            out = tmp / "store.json"
            documents = build_document_store(self._parquet(tmp), {"a", "c"}, out)
            reloaded, meta = load_document_store(out)
        self.assertEqual(set(documents), {"a", "c"})
        self.assertEqual(set(reloaded), {"a", "c"})
        self.assertEqual(reloaded["a"]["text"], "alpha text")
        # char_count is the untrimmed source length, which the app shows to say
        # how much of the document the models never saw.
        self.assertEqual(reloaded["a"]["char_count"], 40000)
        self.assertEqual(meta["document_count"], 2)
        self.assertEqual(meta["missing"], [])

    def test_documents_absent_from_the_parquet_are_recorded_not_raised(self):
        # The app still takes an annotation for these; it just cannot show text.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            out = tmp / "store.json"
            build_document_store(self._parquet(tmp), {"a", "zzz"}, out)
            _, meta = load_document_store(out)
        self.assertEqual(meta["missing"], ["zzz"])

    def test_missing_store_reads_as_empty_rather_than_raising(self):
        with tempfile.TemporaryDirectory() as d:
            documents, meta = load_document_store(Path(d) / "absent.json")
        self.assertEqual(documents, {})
        self.assertEqual(meta, {})

    def test_missing_parquet_is_an_actionable_error(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            with self.assertRaises(AnnotationError) as caught:
                build_document_store(tmp / "absent.parquet", {"a"}, tmp / "store.json")
        self.assertIn("make ner-fetch", str(caught.exception))

    def test_store_write_is_atomic(self):
        # A crash mid-write must not leave a truncated store behind.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            out = tmp / "store.json"
            build_document_store(self._parquet(tmp), {"a"}, out)
            self.assertEqual([p.name for p in tmp.iterdir() if p.suffix == ".tmp"], [])

    def test_prefetch_takes_the_documents_from_the_queue(self):
        rows = BuildAnnotationsTests.QUEUE_ROWS
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            queue = tmp / "queue.csv"
            write_csv_atomic(queue, list(rows[0]), rows)
            keys = queue_asset_keys(queue)
        # "b" is in the file but not in_queue, so it is not prefetched.
        self.assertEqual(keys, {"a"})


class ScoringTests(unittest.TestCase):
    GOLD = [
        {"asset_key": "a", "gold_is_event": "yes", "gold_hazards": "Earthquake | Flood",
         "gold_dates": "2019", "gold_locations": "Beira | Sofala",
         "gold_uncertain": "", "annotation_status": "done", "stratum": "high"},
        {"asset_key": "b", "gold_is_event": "no", "gold_hazards": "", "gold_dates": "",
         "gold_locations": "", "gold_uncertain": "Y", "annotation_status": "done",
         "stratum": "low"},
        {"asset_key": "c", "gold_is_event": "yes", "gold_hazards": "Flood",
         "gold_dates": "2020", "gold_locations": "Lagos", "gold_uncertain": "",
         "annotation_status": "", "stratum": "low"},
    ]

    def _gold(self, tmp: Path, **kwargs) -> Gold:
        path = tmp / "gold.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(self.GOLD[0]))
            w.writeheader()
            w.writerows(self.GOLD)
        return Gold(path, **kwargs)

    def _run(self, tmp: Path, records: list[dict]) -> Run:
        path = tmp / "run.jsonl"
        path.write_text("\n".join(json.dumps(o) for o in records), encoding="utf-8")
        return Run("run", path)

    def test_unannotated_rows_are_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            gold = self._gold(Path(d))
        self.assertEqual(gold.documents, ["a", "b"])

    def test_exclude_uncertain_drops_flagged_rows(self):
        with tempfile.TemporaryDirectory() as d:
            gold = self._gold(Path(d), include_uncertain=False)
        self.assertEqual(gold.documents, ["a"])
        self.assertEqual(gold.skipped_uncertain, 1)

    def test_compound_hazards_are_split_on_both_sides(self):
        # "Earthquake | Tsunami" covers two families. Folding the whole string
        # would keep only the first and score a correct run as a miss.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [
                {"asset_key": "a", "is_verifiable_event": True,
                 "event_hazard": "Earthquake | Flood", "event_dates": "2019",
                 "affected_locations": "Beira | Sofala"},
                {"asset_key": "b", "is_verifiable_event": False},
            ])
            result = score_run(gold, run)
        # `hazard_family` keeps only the first match, so folding the whole
        # compound would give {"flood"} and score this identical run at 50%
        # recall. Both sides split first, so both see both families.
        self.assertEqual(hazard_family("Earthquake | Flood"), "flood")
        self.assertEqual(gold.families["a"], {"earthquake", "flood"})
        self.assertEqual(run.families("a"), {"earthquake", "flood"})
        self.assertEqual(result["sets"]["hazard"]["prf"], (1.0, 1.0, 1.0))

    def test_perfect_run_scores_perfectly(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [
                {"asset_key": "a", "is_verifiable_event": True,
                 "event_hazard": "Earthquake | Flood", "event_dates": "2019",
                 "affected_locations": "Beira | Sofala"},
                {"asset_key": "b", "is_verifiable_event": False},
            ])
            result = score_run(gold, run)
        self.assertEqual(result["detection"]["accuracy"], 1.0)
        for field in ("hazard", "location", "date"):
            self.assertEqual(result["sets"][field]["prf"], (1.0, 1.0, 1.0), field)

    def test_documents_absent_from_a_run_are_reported_not_counted(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [{"asset_key": "a", "is_verifiable_event": True,
                                   "event_hazard": "Earthquake | Flood", "event_dates": "2019",
                                   "affected_locations": "Beira | Sofala"}])
            result = score_run(gold, run)
        self.assertEqual(result["documents"], 1)
        self.assertEqual(result["absent"], 1)

    # --- failed API calls -------------------------------------------------

    def test_errored_documents_are_excluded_not_scored_as_misses(self):
        # A 403 or an unparseable reply is not the model saying "no event".
        # Scoring it as one measured the transport and cost DeepSeek 32 points
        # of recall on the real benchmark.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [
                {"asset_key": "a", "is_verifiable_event": True,
                 "event_hazard": "Earthquake | Flood", "event_dates": "2019",
                 "affected_locations": "Beira | Sofala"},
                {"asset_key": "b", "is_verifiable_event": None,
                 "key_impacts": "ERROR: Error code: 403 - provider refused"},
            ])
            self.assertEqual(run.errored, {"b"})
            result = score_run(gold, run)
        # Document b drops out of the denominator entirely.
        self.assertEqual(result["documents"], 1)
        self.assertEqual(result["errored"], 1)
        self.assertEqual(result["detection"]["tn"], 0)
        self.assertEqual(result["detection"]["fp"], 0)
        self.assertEqual(result["detection"]["accuracy"], 1.0)

    def test_error_policy_count_as_miss_restores_the_old_behaviour(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [
                {"asset_key": "a", "is_verifiable_event": True,
                 "event_hazard": "Earthquake | Flood", "event_dates": "2019",
                 "affected_locations": "Beira | Sofala"},
                {"asset_key": "b", "is_verifiable_event": None,
                 "key_impacts": "ERROR: boom"},
            ])
            result = score_run(gold, run, error_policy="count-as-miss")
        # b is gold-negative, so counting the failure as "found no event"
        # accidentally credits a true negative — which is exactly the problem.
        self.assertEqual(result["documents"], 2)
        self.assertEqual(result["detection"]["tn"], 1)

    def test_a_document_with_one_good_row_is_still_scored(self):
        # Partial failure within a document is not total failure: a resumed run
        # can carry both, and the successful row is a real claim.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [
                {"asset_key": "a", "is_verifiable_event": None,
                 "key_impacts": "ERROR: transient"},
                {"asset_key": "a", "is_verifiable_event": True,
                 "event_hazard": "Earthquake | Flood", "event_dates": "2019",
                 "affected_locations": "Beira | Sofala"},
            ])
            self.assertEqual(run.errored, set())
            result = score_run(gold, run)
        self.assertEqual(result["documents"], 1)
        self.assertEqual(result["sets"]["hazard"]["prf"], (1.0, 1.0, 1.0))

    def test_a_run_that_errored_everywhere_is_scored_on_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [
                {"asset_key": "a", "is_verifiable_event": None, "key_impacts": "ERROR: 403"},
                {"asset_key": "b", "is_verifiable_event": None, "key_impacts": "ERROR: 403"},
            ])
            result = score_run(gold, run)
        self.assertEqual(result["documents"], 0)
        self.assertEqual(result["coverage"], 0.0)
        # Not 0% accuracy — no denominator at all.
        self.assertEqual(result["detection"]["mcc"], None)

    def test_recall_is_reported_against_both_denominators(self):
        # Document a is returned and extracted perfectly; document c is a gold
        # row the run never got to. Recall over what it processed is 1.0;
        # recall over the whole set is not, and both belong in the report.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [
                {"asset_key": "a", "is_verifiable_event": True,
                 "event_hazard": "Earthquake | Flood", "event_dates": "2019",
                 "affected_locations": "Beira | Sofala"},
                {"asset_key": "b", "is_verifiable_event": None,
                 "key_impacts": "ERROR: 403"},
            ])
            result = score_run(gold, run)
        # Only document a is gold-positive and annotated, so here the two agree.
        self.assertEqual(result["detection"]["recall"], 1.0)
        self.assertEqual(result["recall_overall"], 1.0)
        # Field recall likewise divides by every gold item in the set.
        haz = result["sets"]["hazard"]
        self.assertEqual(haz["gold_all"], 2)
        self.assertEqual(haz["recall_all"], 1.0)

    def test_field_recall_over_all_uses_the_full_gold_denominator(self):
        # A run that returns nothing at all still has a defined recall over the
        # whole set: zero. That is the pipeline reading.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [
                {"asset_key": "a", "is_verifiable_event": None, "key_impacts": "ERROR: 403"},
                {"asset_key": "b", "is_verifiable_event": None, "key_impacts": "ERROR: 403"},
            ])
            result = score_run(gold, run)
        self.assertEqual(result["recall_overall"], 0.0)
        self.assertEqual(result["sets"]["location"]["recall_all"], 0.0)
        # ...and the denominator is the set's, not the run's.
        self.assertEqual(result["sets"]["location"]["gold_all"], 2)

    # --- matching rules ---------------------------------------------------

    def test_normalised_fuzzy_absorbs_a_comma_qualifier_and_raw_does_not(self):
        # The published rule calls token_set_ratio with no processor, so the
        # comma welds to the matching token and the pair scores 66.7.
        gold = {"louisville"}
        run = {"louisville, kentucky"}
        self.assertEqual(fuzzy_matched(gold, run, normalise=False), 0)
        self.assertEqual(fuzzy_matched(gold, run, normalise=True), 1)

    def test_normalised_fuzzy_still_refuses_a_different_place(self):
        # Folding punctuation must not turn the rule into "anything matches".
        self.assertEqual(fuzzy_matched({"haiti"}, {"port-au-prince"}, normalise=True), 0)

    def test_normalised_fuzzy_folds_diacritics(self):
        self.assertEqual(fuzzy_matched({"male"}, {"mal\u00e9"}, normalise=True), 1)

    def test_year_set_dates_credit_a_coarser_gold(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [
                {"asset_key": "a", "is_verifiable_event": True,
                 "event_hazard": "Earthquake | Flood", "event_dates": "2019-03-14",
                 "affected_locations": "Beira | Sofala"},
                {"asset_key": "b", "is_verifiable_event": False},
            ])
            result = score_run(gold, run)
        # Gold says "2019"; the run says "2019-03-14". Exact scores it a miss
        # on both sides, year-set scores it a hit.
        self.assertEqual(result["sets"]["date"]["prf"], (0.0, 0.0, 0.0))
        self.assertEqual(result["sets"]["date_year"]["prf"], (1.0, 1.0, 1.0))

    # --- statistics -------------------------------------------------------

    def test_mcc_is_none_when_a_run_flags_everything(self):
        # A run with no predicted negatives has an undefined correlation.
        # Returning 0.0 would read as "chance"; None reads as "not measurable".
        self.assertIsNone(mcc(tp=10, fp=5, fn=0, tn=0))
        self.assertAlmostEqual(mcc(tp=5, fp=0, fn=0, tn=5), 1.0)

    def test_specificity_and_balanced_accuracy_see_the_negatives(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [
                {"asset_key": "a", "is_verifiable_event": True,
                 "event_hazard": "Earthquake | Flood", "event_dates": "2019",
                 "affected_locations": "Beira | Sofala"},
                # b carries no event, but the run flags one anyway.
                {"asset_key": "b", "is_verifiable_event": True,
                 "event_hazard": "Flood", "event_dates": "2001",
                 "affected_locations": "Nowhere"},
            ])
            result = score_run(gold, run)
        d_ = result["detection"]
        self.assertEqual(d_["recall"], 1.0)
        self.assertEqual(d_["specificity"], 0.0)
        self.assertEqual(d_["balanced"], 0.5)
        # Accuracy alone would say 50% and imply a coin flip; it is really a
        # run that never declines anything.
        self.assertIsNone(d_["mcc"])

    def test_set_metrics_ignore_documents_with_no_gold_event(self):
        # Document b carries no event; a run emitting nothing there must not be
        # charged a false negative on locations it was right not to produce.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            gold = self._gold(tmp)
            run = self._run(tmp, [
                {"asset_key": "a", "is_verifiable_event": True,
                 "event_hazard": "Earthquake | Flood",
                 "event_dates": "2019", "affected_locations": "Beira | Sofala"},
                {"asset_key": "b", "is_verifiable_event": False},
            ])
            result = score_run(gold, run)
        self.assertEqual(result["sets"]["location"]["fp"], 0)
        self.assertEqual(result["sets"]["location"]["fn"], 0)

    def test_prf_and_mcnemar_edges(self):
        self.assertEqual(prf(0, 0, 0), (0.0, 0.0, 0.0))
        self.assertEqual(mcnemar_exact(0, 0), 1.0)
        self.assertLess(mcnemar_exact(14, 2), 0.01)


if __name__ == "__main__":
    unittest.main()
