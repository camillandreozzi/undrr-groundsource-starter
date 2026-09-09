"""Unit tests for the NER benchmark's own logic.

Covers the parts that decide what the baseline emits — date normalisation,
location cleaning, the hazard lexicon and event assembly — plus the statistics
the comparison rests on. These are the pieces where a silent bug would show up
as a quality difference between the two pipelines rather than as a crash.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmark_ner.compare import cohen_kappa, jaccard, prf  # noqa: E402
from benchmark_ner.hazard_lexicon import find_hazards, join_labels  # noqa: E402
from benchmark_ner.ner_extract import (  # noqa: E402
    admin_level_for,
    clean_location,
    date_precision,
    impact_sentences,
    normalise_date,
    to_output_rows,
)
from benchmark_ner.score_paired import mcnemar_exact  # noqa: E402


class TestDateNormalisation(unittest.TestCase):
    def test_precise_forms(self):
        for text, expected in [
            ("12 January 2010", "2010-01-12"),
            ("January 12, 2010", "2010-01-12"),
            ("Dec. 26, 2004", "2004-12-26"),
            ("2010-01-12", "2010-01-12"),
            ("March 2010", "2010-03"),
            ("in 1998", "1998"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(normalise_date(text), expected)

    def test_year_survives_a_seasonal_phrase(self):
        # The point of not blocklisting relative words: this is a real event date.
        self.assertEqual(normalise_date("the summer of 2019"), "2019")

    def test_rejects_unusable(self):
        for text in ["the 1990s", "last year", "recent years", "three days",
                     "annually", "the past decade", "page 12", ""]:
            with self.subTest(text=text):
                self.assertIsNone(normalise_date(text))

    def test_duration_number_is_not_a_year(self):
        self.assertIsNone(normalise_date("over 2000 years"))
        # ...but a year alongside a duration still counts.
        self.assertEqual(normalise_date("3 days in 2019"), "2019")

    def test_year_range_is_bounded(self):
        self.assertIsNone(normalise_date("2099"))
        self.assertIsNone(normalise_date("1850"))

    def test_precision(self):
        self.assertEqual(date_precision("2010-01-12"), 3)
        self.assertEqual(date_precision("2010-01"), 2)
        self.assertEqual(date_precision("2010"), 1)
        self.assertEqual(date_precision(""), 0)


class TestLocationCleaning(unittest.TestCase):
    def test_strips_articles_and_punctuation(self):
        self.assertEqual(clean_location("  the Philippines,  "), "Philippines")
        self.assertEqual(clean_location("Port-au-Prince"), "Port-au-Prince")

    def test_rejects_non_places(self):
        for text in ["United Nations", "the region", "2015", "%", "a", None, ""]:
            with self.subTest(text=text):
                self.assertIsNone(clean_location(text))

    def test_admin_levels(self):
        self.assertEqual(admin_level_for("Haiti", "GPE"), "country")
        self.assertEqual(admin_level_for("Port of Beirut", "FAC"), "point")
        self.assertEqual(admin_level_for("Andaman coast", "LOC"), "feature")
        self.assertEqual(admin_level_for("Gonaives", "GPE"), "unknown")


class TestHazardLexicon(unittest.TestCase):
    def test_finds_prevention_web_labels(self):
        labels = {h.label for h in find_hazards(
            "A tsunami followed the earthquake; flooding and landslides came later."
        )}
        self.assertEqual(labels, {"Tsunami", "Earthquake", "Flood", "Landslide"})

    def test_normalises_source_terms(self):
        self.assertEqual(
            {h.label for h in find_hazards("Typhoon Haiyan made landfall")},
            {"Cyclone, Hurricane and Typhoon"},
        )

    def test_ignores_metaphors(self):
        self.assertEqual(find_hazards("The population explosion of the 1990s"), [])

    def test_compound_label_format_matches_the_llm(self):
        # The LLM emits "Earthquake | Tsunami"; order must be stable so the two
        # runs' hazard strings are comparable.
        self.assertEqual(join_labels(["Tsunami", "Earthquake"]), "Earthquake | Tsunami")
        self.assertEqual(join_labels(["Earthquake", "Tsunami"]), "Earthquake | Tsunami")

    def test_generic_risk_language_is_not_a_hazard(self):
        self.assertEqual(find_hazards("disaster risk reduction and emergency planning"), [])


class TestImpacts(unittest.TestCase):
    def test_numeric_impacts_rank_first(self):
        out = impact_sentences([
            "Homes were damaged across the district.",
            "At least 40 people were killed.",
        ])
        self.assertEqual(out[0], "At least 40 people were killed.")
        self.assertEqual(len(out), 2)

    def test_ignores_sentences_without_impact_language(self):
        self.assertEqual(impact_sentences(["The workshop was held in Geneva."]), [])


class TestOutputSchema(unittest.TestCase):
    """The whole design rests on being byte-compatible with the LLM's schema."""

    META = {"asset_key": "k", "title": "t", "publication_year": "2020",
            "language": "English", "countries": "Haiti", "themes": None,
            "hazards": None, "organizations": None, "content_url": "u"}

    def test_empty_document_row(self):
        from fonte.app_event_focus import OUTPUT_HEADERS

        rows = to_output_rows(self.META, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), set(OUTPUT_HEADERS))
        self.assertFalse(rows[0]["is_verifiable_event"])
        self.assertEqual(rows[0]["missing_information"],
                         "no verified reliable event extracted")

    def test_event_row_matches_headers_and_joins_with_pipes(self):
        from fonte.app_event_focus import OUTPUT_HEADERS

        rows = to_output_rows(self.META, [{
            "event_hazard": "Flood",
            "event_dates": ["2010-01-12", "2010-02"],
            "affected_locations": ["Gonaives", "Haiti"],
            "location_admin_levels": ["unknown", "country"],
            "key_impacts": ["500 homes destroyed"],
            "event_confidence": "high",
            "evidence_snippets": ["Flooding affected Gonaives."],
            "missing_information": [],
        }])
        self.assertEqual(set(rows[0]), set(OUTPUT_HEADERS))
        self.assertEqual(rows[0]["event_dates"], "2010-01-12 | 2010-02")
        self.assertEqual(rows[0]["affected_locations"], "Gonaives | Haiti")
        self.assertTrue(rows[0]["is_verifiable_event"])

    def test_literal_pipe_in_a_value_cannot_corrupt_a_list_field(self):
        rows = to_output_rows(self.META, [{
            "event_hazard": "Flood",
            "event_dates": ["2010"],
            "affected_locations": ["Foo | Bar"],
            "location_admin_levels": ["unknown"],
            "key_impacts": [],
            "event_confidence": "medium",
            "evidence_snippets": [],
            "missing_information": [],
        }])
        self.assertEqual(rows[0]["affected_locations"], "Foo / Bar")


class TestStatistics(unittest.TestCase):
    def test_prf(self):
        p, r, f = prf(tp=8, fp=2, fn=4)
        self.assertAlmostEqual(p, 0.8)
        self.assertAlmostEqual(r, 8 / 12)
        self.assertAlmostEqual(f, 2 * 0.8 * (8 / 12) / (0.8 + 8 / 12))

    def test_kappa_is_zero_at_chance(self):
        # Perfectly independent 50/50 raters: observed agreement equals expected.
        self.assertAlmostEqual(cohen_kappa(tp=25, fp=25, fn=25, tn=25), 0.0)

    def test_kappa_is_one_on_perfect_agreement(self):
        self.assertAlmostEqual(cohen_kappa(tp=50, fp=0, fn=0, tn=50), 1.0)

    def test_kappa_punishes_a_lopsided_corpus(self):
        # 90% agreement, but almost all of it on the majority class.
        self.assertLess(cohen_kappa(tp=2, fp=5, fn=5, tn=88), 0.4)

    def test_jaccard(self):
        self.assertEqual(jaccard(set(), set()), 1.0)
        self.assertEqual(jaccard({"a"}, {"a", "b"}), 0.5)

    def test_mcnemar_exact(self):
        # No discordant pairs -> nothing to distinguish the two runs.
        self.assertEqual(mcnemar_exact(0, 0), 1.0)
        # Symmetric discordance -> p = 1.
        self.assertAlmostEqual(mcnemar_exact(5, 5), 1.0)
        # 10 vs 0 is a two-sided binomial tail of 2 * 0.5**10.
        self.assertAlmostEqual(mcnemar_exact(10, 0), 2 * 0.5 ** 10)
        self.assertAlmostEqual(mcnemar_exact(0, 10), 2 * 0.5 ** 10)
        # Direction must not change the p-value.
        self.assertAlmostEqual(mcnemar_exact(12, 4), mcnemar_exact(4, 12))
        self.assertLess(mcnemar_exact(15, 3), 0.05)
        self.assertGreater(mcnemar_exact(9, 6), 0.05)


if __name__ == "__main__":
    unittest.main()
