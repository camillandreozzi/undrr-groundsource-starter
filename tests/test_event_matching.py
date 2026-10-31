"""Unit tests for the event-level experiment: matcher, scorer, sampler, app helpers.

The matcher is the place where a silent bug would not crash but would decide
the result: pair records with gold events on the fields, and the attribute swap
the experiment exists to detect scores as correct. So the reviewers' own example
is the first test, and every test here builds its window from text, the way the
real gold is built.
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT, REPO_ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from eval.event_annotation_app import (  # noqa: E402
    build_windows, replace_window_events, split_lines, validate_event, validate_window,
)
from eval.event_matching import (  # noqa: E402
    GoldEvent, PredEvent, Window, hazard_key, judge, locate_evidence, match_window,
    optimistic_alignment, pooled_counts,
)
from eval.sample_event_level_windows import (  # noqa: E402
    SamplingError, allocate, draw, proxy_stratum,
)
from eval.score_event_level import (  # noqa: E402
    COUNTERS, METRICS, _jsonable, _named, paired_difference, score_window, summarise,
)

TWO_EVENTS = (
    "Annual report. In 2020, severe floods inundated large parts of Thailand, displacing "
    "thousands of families. Separately, a prolonged drought struck India in 2022, causing "
    "crop losses across several states. The agency coordinated relief in both cases.")


def gold(i, hazard, years, locations, quotes, verifiable="yes", secondary=""):
    start, _, end = str(years).partition("-")
    return GoldEvent.from_row({
        "asset_key": "k", "gold_event_id": str(i), "hazard_primary": hazard,
        "hazard_secondary": secondary, "year_start": start, "year_end": end,
        "locations": locations, "support_quotes": quotes, "verifiable": verifiable})


def pred(i, hazard, dates, locations, evidence=""):
    return PredEvent.from_row({
        "asset_key": "k", "event_index": str(i), "event_hazard": hazard,
        "event_dates": dates, "affected_locations": locations,
        "evidence_snippets": evidence}, i)


FLOOD_TH = gold(1, "Flood", 2020, "Thailand",
                "In 2020, severe floods inundated large parts of Thailand")
DROUGHT_IN = gold(2, "Drought and Desertification", 2022, "India",
                  "a prolonged drought struck India in 2022")


class SwapExampleTests(unittest.TestCase):
    """Gold: Flood/2020/Thailand + Drought/2022/India. Predicted: the years and
    places swapped. Pooled scoring calls it perfect; it must not be."""

    def setUp(self):
        self.preds = [
            pred(1, "Flood", "2022", "India", '"severe floods inundated large parts of Thailand"'),
            pred(2, "Drought and Desertification", "2020", "Thailand",
                 "a prolonged drought struck India"),
        ]
        self.window = Window(TWO_EVENTS, [FLOOD_TH, DROUGHT_IN])

    def test_pooled_reading_is_perfect(self):
        for field, (tp, fp, fn) in pooled_counts(self.preds, [FLOOD_TH, DROUGHT_IN]).items():
            self.assertEqual((fp, fn), (0, 0), field)
            self.assertEqual(tp, 2, field)

    def test_records_match_by_evidence_and_neither_is_complete(self):
        m = match_window(self.preds, self.window)
        pairs = {(l.pred.event_index, l.gold.gold_event_id, l.tier) for l in m.links}
        self.assertEqual(pairs, {(1, 1, "A"), (2, 2, "A")})
        self.assertFalse(any(l.verdict.complete for l in m.links))
        self.assertTrue(all(l.verdict.ok["hazard"] for l in m.links))

    def test_every_wrong_value_is_misassociated(self):
        m = match_window(self.preds, self.window)
        for link in m.links:
            self.assertEqual(link.verdict.misassociated, {"hazard": 0, "year": 1, "location": 1})
            self.assertEqual(link.verdict.unsupported, {"hazard": 0, "year": 0, "location": 0})

    def test_scorer_reports_zero_complete_and_full_pooled(self):
        counts, _rows = score_window(self.preds, [FLOOD_TH, DROUGHT_IN], TWO_EVENTS,
                                     "sys", {"asset_key": "k"}, "multi")
        s = _named(np.array([counts[c] for c in COUNTERS], dtype=float))
        self.assertEqual(float(METRICS["crc"](s)), 0.0)
        self.assertEqual(float(METRICS["pooled_f1"](s)), 1.0)
        self.assertEqual(float(METRICS["det_p"](s)), 1.0)
        self.assertLess(float(METRICS["attr_f1"](s)), 1.0)

    def test_field_maximising_bound_cannot_rescue_it(self):
        self.assertFalse(any(v.complete for _p, _g, v in
                             optimistic_alignment(self.preds, [FLOOD_TH, DROUGHT_IN])))


class SameHazardTests(unittest.TestCase):
    TEXT = ("Floods struck Sindh province in 2010, destroying crops. Four years later, "
            "in 2014, floods hit Punjab province and displaced villagers.")
    G1 = gold(1, "Flood", 2010, "Sindh province", "Floods struck Sindh province in 2010")
    G2 = gold(2, "Flood", 2014, "Punjab province", "in 2014, floods hit Punjab province")

    def test_identity_comes_from_evidence_not_hazard_or_fields(self):
        # Quotes the 2010 event but carries the 2014 event's year and place.
        p = pred(1, "Flood", "2014", "Punjab province", "Floods struck Sindh province in 2010")
        m = match_window([p], Window(self.TEXT, [self.G1, self.G2]))
        self.assertEqual(m.links[0].gold.gold_event_id, 1)
        self.assertFalse(m.links[0].verdict.complete)
        self.assertEqual(m.unmatched_gold[0][0].gold_event_id, 2)

    def test_two_correct_records_both_complete(self):
        ps = [pred(1, "Flood", "2010", "Sindh province", "Floods struck Sindh province in 2010"),
              pred(2, "Flood", "2014-07", "Punjab", "floods hit Punjab province")]
        m = match_window(ps, Window(self.TEXT, [self.G1, self.G2]))
        self.assertEqual([l.verdict.complete for l in m.links], [True, True])


class TierTests(unittest.TestCase):
    def test_quote_marks_do_not_stop_a_verbatim_snippet_locating(self):
        spans, kind = locate_evidence(TWO_EVENTS, TWO_EVENTS.casefold(),
                                      "“a prolonged drought struck India”")
        self.assertTrue(spans)
        self.assertEqual(kind, "exact")

    def test_paraphrase_links_through_tier_b(self):
        p = pred(1, "Flood", "2020", "Thailand",
                 "Thailand inundated by severe floods displacing families")
        m = match_window([p], Window(TWO_EVENTS, [FLOOD_TH, DROUGHT_IN]))
        self.assertEqual([(l.gold.gold_event_id, l.tier) for l in m.links], [(1, "B")])

    def test_no_evidence_needs_year_and_location(self):
        window = Window(TWO_EVENTS, [FLOOD_TH, DROUGHT_IN])
        both = pred(1, "Flood", "2020", "Thailand")
        self.assertEqual([(l.gold.gold_event_id, l.tier)
                          for l in match_window([both], window).links], [(1, "C")])

    def test_hazard_alone_never_links(self):
        window = Window(TWO_EVENTS, [FLOOD_TH, DROUGHT_IN])
        only_hazard = pred(1, "Flood", "1999", "Peru")
        m = match_window([only_hazard], window)
        self.assertEqual(m.links, [])
        self.assertEqual(m.unmatched_pred[0][1], "no_event")

    def test_year_without_location_does_not_link(self):
        m = match_window([pred(1, "Flood", "2020", "Peru")], Window(TWO_EVENTS, [FLOOD_TH]))
        self.assertEqual(m.links, [])


class SegmentationTests(unittest.TestCase):
    TEXT = ("On 26 December 2004 a magnitude 9.1 earthquake off Sumatra triggered a tsunami "
            "that devastated Aceh province.")
    G = gold(1, "Earthquake", 2004, "Aceh province | Sumatra",
             "a magnitude 9.1 earthquake off Sumatra triggered a tsunami", secondary="Tsunami")

    def test_split_cascade_is_one_match_and_one_false_positive(self):
        ps = [pred(1, "Earthquake", "2004-12-26", "Sumatra", "magnitude 9.1 earthquake off Sumatra"),
              pred(2, "Tsunami", "2004-12-26", "Aceh province", "triggered a tsunami that devastated")]
        m = match_window(ps, Window(self.TEXT, [self.G]))
        self.assertEqual(len(m.links), 1)
        self.assertEqual([reason for _p, reason in m.unmatched_pred], ["split"])

    def test_compound_record_is_complete(self):
        p = pred(1, "Earthquake | Tsunami", "2004-12-26", "Aceh province", "earthquake off Sumatra")
        link = match_window([p], Window(self.TEXT, [self.G])).links[0]
        self.assertTrue(link.verdict.complete)
        self.assertTrue(link.verdict.exact["hazard"])
        self.assertFalse(link.verdict.exact["location"])  # Sumatra not recovered

    def test_secondary_hazard_alone_is_not_the_event(self):
        p = pred(1, "Tsunami", "2004", "Aceh province", "earthquake off Sumatra")
        # Tsunami folds into the earthquake family, so this one passes at family
        # level; a hazard outside the event's families must not.
        self.assertTrue(match_window([p], Window(self.TEXT, [self.G])).links[0].verdict.ok["hazard"])
        q = pred(1, "Flood", "2004", "Aceh province", "earthquake off Sumatra")
        self.assertFalse(match_window([q], Window(self.TEXT, [self.G])).links[0].verdict.ok["hazard"])


class FieldRuleTests(unittest.TestCase):
    G = gold(1, "Drought and Desertification", "2009-2011", "Kenya | Turkana County", "x" * 20)

    def test_year_inside_span_is_correct_but_not_exact(self):
        v = judge(pred(1, "Drought and Desertification", "2010", "Turkana County"), self.G, [])
        self.assertTrue(v.ok["year"])
        self.assertFalse(v.exact["year"])

    def test_year_outside_span_is_wrong(self):
        v = judge(pred(1, "Drought and Desertification", "2008-2011", "Kenya"), self.G, [])
        self.assertFalse(v.ok["year"])

    def test_one_stray_location_breaks_association(self):
        v = judge(pred(1, "Drought", "2010", "Turkana County | Somalia"), self.G, [])
        self.assertFalse(v.ok["location"])
        self.assertEqual(v.unsupported["location"], 1)

    def test_appended_parent_still_matches(self):
        v = judge(pred(1, "Drought", "2010", "Turkana County, Kenya"), self.G, [])
        self.assertTrue(v.ok["location"])

    def test_other_family_keeps_labels_apart(self):
        self.assertNotEqual(hazard_key("Epidemic and pandemic"), hazard_key("Cold Wave"))
        self.assertEqual(hazard_key("Tsunami"), hazard_key("Earthquake"))


class VerifiabilityTests(unittest.TestCase):
    def test_unverifiable_gold_is_matchable_but_never_a_miss(self):
        g = gold(1, "Flood", "", "Thailand", "In 2020, severe floods inundated large parts",
                 verifiable="no")
        counts, rows = score_window([], [g], TWO_EVENTS, "sys", {"asset_key": "k"}, "none")
        self.assertEqual((counts["gold_req"], counts["missed"]), (0, 0))
        self.assertEqual(rows[0]["status"], "unmatched_not_required")

        p = pred(1, "Flood", "2020", "Thailand", "severe floods inundated large parts of Thailand")
        counts, _ = score_window([p], [g], TWO_EVENTS, "sys", {"asset_key": "k"}, "none")
        self.assertEqual((counts["records_matched"], counts["complete"]), (1, 0))

    def test_unmatched_record_stays_in_the_denominator(self):
        ps = [pred(1, "Flood", "2020", "Thailand", "severe floods inundated large parts of Thailand"),
              pred(2, "Earthquake", "1999", "Chile", "a great earthquake shook Valparaiso")]
        counts, _ = score_window(ps, [FLOOD_TH], TWO_EVENTS, "sys", {"asset_key": "k"}, "single")
        s = _named(np.array([counts[c] for c in COUNTERS], dtype=float))
        self.assertEqual(float(METRICS["crc"](s)), 0.5)
        self.assertEqual(counts["no_event"], 1)


class DeterminismTests(unittest.TestCase):
    TEXT = "Floods and landslides hit Nepal and India in 2017 during the monsoon."
    QUOTE = "Floods and landslides hit Nepal and India in 2017"

    def _links(self, ps, gs):
        return [(l.pred.event_index, l.gold.gold_event_id)
                for l in match_window(ps, Window(self.TEXT, gs)).links]

    def test_tied_evidence_breaks_on_time_and_place_not_hazard(self):
        g1 = gold(1, "Flood", 2017, "Nepal", self.QUOTE)
        g2 = gold(2, "Landslide", 2017, "India", self.QUOTE)
        # Hazards deliberately crossed: context must decide on year + place only.
        ps = [pred(1, "Flood", "2017", "India", "Floods and landslides hit Nepal and India"),
              pred(2, "Landslide", "2017", "Nepal", "Floods and landslides hit Nepal and India")]
        runs = [self._links(ps, [g1, g2]) for _ in range(3)]
        self.assertEqual(runs[0], [(1, 2), (2, 1)])
        self.assertTrue(all(r == runs[0] for r in runs))

    def test_fully_tied_pairs_by_rank_order(self):
        g1 = gold(1, "Flood", 2017, "Nepal | India", self.QUOTE)
        g2 = gold(2, "Landslide", 2017, "Nepal | India", self.QUOTE)
        ps = [pred(1, "Landslide", "2017", "Nepal", "Floods and landslides hit Nepal and India"),
              pred(2, "Flood", "2017", "India", "Floods and landslides hit Nepal and India")]
        self.assertEqual(self._links(ps, [g1, g2]), [(1, 1), (2, 2)])

    def test_bootstrap_is_seeded(self):
        windows = [
            score_window([pred(1, "Flood", "2022", "India", "severe floods inundated large parts"),
                          pred(2, "Drought", "2022", "India", "a prolonged drought struck India")][:n],
                         [FLOOD_TH, DROUGHT_IN], TWO_EVENTS, "s", {"asset_key": "k"}, "multi")[0]
            for n in (0, 1, 2, 1, 2, 2)]
        matrix = np.array([[c[k] for k in COUNTERS] for c in windows], dtype=float)
        # Through the JSON form, where NaN (an undefined rate) compares equal.
        same = lambda f: json.dumps(_jsonable(f()), sort_keys=True)
        self.assertEqual(same(lambda: summarise(matrix, "a", "all")),
                         same(lambda: summarise(matrix, "a", "all")))
        self.assertEqual(same(lambda: paired_difference(matrix, matrix[::-1], "a", "all")),
                         same(lambda: paired_difference(matrix, matrix[::-1], "a", "all")))
        # Only the drought record is complete (the flood one carries 2022/India).
        self.assertAlmostEqual(summarise(matrix, "a", "all")["crc"]["point"], 3 / 8)


class SamplerTests(unittest.TestCase):
    def test_strata_from_prior_annotation(self):
        row = lambda h, d: {"gold_hazards": h, "gold_dates": d}
        self.assertEqual(proxy_stratum(row("Flood", "2010")), "single")
        self.assertEqual(proxy_stratum(row("Flood", "2010 | 2012-05")), "same_hazard_multi_year")
        self.assertEqual(proxy_stratum(row("Flood | Drought", "2010")), "multi_hazard_same_year")
        self.assertEqual(proxy_stratum(row("Flood | Drought", "2010 | 2012")),
                         "multi_hazard_multi_year")
        # Same family counts as one hazard.
        self.assertEqual(proxy_stratum(row("Earthquake | Tsunami", "2011")), "single")

    def test_shortfall_moves_to_the_largest_multi_stratum(self):
        pools = {"single": 30, "same_hazard_multi_year": 20,
                 "multi_hazard_same_year": 7, "multi_hazard_multi_year": 40}
        actual, notes = allocate(pools)
        self.assertEqual(actual["multi_hazard_same_year"], 7)
        self.assertEqual(actual["multi_hazard_multi_year"], 13)
        self.assertEqual(sum(actual.values()), 45)
        self.assertEqual(len(notes), 1)
        with self.assertRaises(SamplingError):
            allocate({**pools, "multi_hazard_multi_year": 12})

    def test_draw_is_seeded_and_interleaved(self):
        eligible = [{"asset_key": f"{s}{i:03d}", "stratum": s, "window_chars": "1"}
                    for s in ("single", "same_hazard_multi_year", "multi_hazard_same_year",
                              "multi_hazard_multi_year") for i in range(20)]
        alloc = {"single": 15, "same_hazard_multi_year": 10,
                 "multi_hazard_same_year": 10, "multi_hazard_multi_year": 10}
        a, b = draw(eligible, alloc, 44), draw(eligible, alloc, 44)
        self.assertEqual(a, b)
        self.assertEqual(Counter(r["stratum"] for r in a), Counter(alloc))
        self.assertNotEqual([r["stratum"] for r in a[:15]], ["single"] * 15)


class AppHelperTests(unittest.TestCase):
    EVENT = {"hazard_primary": "Flood", "hazard_secondary": [], "year_start": "2020",
             "year_end": "", "date_text": "", "locations": "Thailand\nBangkok | Ayutthaya",
             "support_quotes": "In 2020, severe floods inundated large parts of Thailand",
             "verifiable": "yes", "notes": ""}

    def test_valid_event_becomes_a_row(self):
        row, errors = validate_event(self.EVENT, TWO_EVENTS, 1)
        self.assertEqual(errors, [])
        self.assertEqual(row["year_end"], "2020")
        self.assertEqual(row["locations"], "Thailand | Bangkok | Ayutthaya")
        self.assertNotEqual(row["support_spans"], "[]")

    def test_unlocatable_quote_is_refused(self):
        _row, errors = validate_event({**self.EVENT, "support_quotes": "floods everywhere in 2020"},
                                      TWO_EVENTS, 1)
        self.assertTrue(any("not found verbatim" in e for e in errors))

    def test_verifiable_needs_year_and_place(self):
        _row, errors = validate_event({**self.EVENT, "year_start": ""}, TWO_EVENTS, 1)
        self.assertTrue(any("verifiable needs" in e for e in errors))
        _row, errors = validate_event({**self.EVENT, "year_start": "", "verifiable": "no"},
                                      TWO_EVENTS, 1)
        self.assertEqual(errors, [])

    def test_bad_years_are_refused(self):
        for start, end in (("20", ""), ("2020", "2019"), ("", "2020")):
            _row, errors = validate_event({**self.EVENT, "year_start": start, "year_end": end},
                                          TWO_EVENTS, 1)
            self.assertTrue(errors, (start, end))

    def test_window_rules(self):
        self.assertTrue(validate_window(None, [], False, TWO_EVENTS, "k")[1])
        self.assertEqual(validate_window("no", [], False, TWO_EVENTS, "k"), ([], []))
        rows, errors = validate_window("yes", [self.EVENT], False, TWO_EVENTS, "k")
        self.assertTrue(any("every event" in e for e in errors))
        rows, errors = validate_window("yes", [self.EVENT, self.EVENT], True, TWO_EVENTS, "k")
        self.assertEqual(errors, [])
        self.assertEqual([r["gold_event_id"] for r in rows], ["1", "2"])

    def test_replace_and_split(self):
        rows = [{"asset_key": "a", "gold_event_id": "1"}, {"asset_key": "b", "gold_event_id": "1"}]
        out = replace_window_events(rows, "a", [{"asset_key": "a", "gold_event_id": "9"}])
        self.assertEqual([(r["asset_key"], r["gold_event_id"]) for r in out], [("b", "1"), ("a", "9")])
        self.assertEqual(split_lines("x | y\nx", also_pipes=True), ["x", "y"])
        self.assertEqual(split_lines("a quote | with a pipe"), ["a quote | with a pipe"])

    def test_windows_file_hides_the_stratum(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            queue = tmp / "queue.csv"
            with queue.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["asset_key", "review_rank", "stratum",
                                                  "title", "content_url", "in_queue"])
                w.writeheader()
                w.writerow({"asset_key": "b", "review_rank": "2", "stratum": "single",
                            "title": "B", "content_url": "", "in_queue": "Y"})
                w.writerow({"asset_key": "a", "review_rank": "1", "stratum": "multi",
                            "title": "A", "content_url": "", "in_queue": "Y"})
            rows = build_windows(queue, tmp / "windows.csv", tmp / "gold.csv")
            self.assertEqual([r["asset_key"] for r in rows], ["a", "b"])
            self.assertNotIn("stratum", (tmp / "windows.csv").read_text().splitlines()[0])
            self.assertTrue((tmp / "gold.csv").exists())


if __name__ == "__main__":
    unittest.main()
