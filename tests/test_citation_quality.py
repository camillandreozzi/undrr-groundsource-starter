"""Unit tests for the evidence-snippet audit.

This metric is easy to make look good by accident. Every test here pins one of
the ways it could quietly inflate: matching through PDF line noise is the
feature, matching through *anything* is the bug; a translated snippet must be
held out rather than posted as a fabrication; and a snippet that belongs to a
different document must not be found in this one.

Nothing here makes a network call or reads the corpus.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_openrouter.citation_quality import (  # noqa: E402
    Document,
    GROUNDED,
    QUOTABLE,
    RunReport,
    char_stream,
    classify,
    guess_language,
    numbers,
    snippet_language,
)

ENGLISH = (
    "The flood of 12 October 2018 struck the district of Kilima, where more "
    "than 3,400 homes were damaged and about 12,000 people were displaced. "
    "The report says that the water retreated before the waves arrived, and "
    "that the harbour was closed for a week after the storm surge. Relief "
    "agencies have been working in the area since then, and the government "
    "has said it will rebuild the schools that were destroyed by the event."
)

SPANISH = (
    "La inundacion del 12 de octubre de 2018 afecto al distrito de Kilima, "
    "donde mas de 3.400 viviendas resultaron danadas y cerca de 12.000 "
    "personas fueron desplazadas. El informe senala que el agua se retiro "
    "antes de que llegaran las olas, y que el puerto estuvo cerrado durante "
    "una semana despues de la marejada. Las agencias de ayuda han trabajado "
    "en la zona desde entonces, y el gobierno ha dicho que reconstruira las "
    "escuelas que fueron destruidas por el evento."
)


def doc(text: str = ENGLISH, key: str = "a" * 64) -> Document:
    return Document.build(key, text)


class TestNormalisation(unittest.TestCase):
    def test_pdf_line_damage_is_invisible(self):
        """`retrac-\\nted` and `E\\nnc\\no` are how this corpus arrives."""
        self.assertEqual(char_stream("retrac-\nted"), char_stream("retracted"))
        self.assertEqual(char_stream("E\nnc\no\nu\nnter"), "encounter")

    def test_case_punctuation_and_diacritics_fold(self):
        self.assertEqual(char_stream("Malé, “2018”!"), char_stream("male 2018"))

    def test_numbers_fold_their_separators(self):
        self.assertEqual(numbers("12,000 and 12 000 and 12000"), {"12000"})
        self.assertIn("3400", numbers("3,400 homes"))

    def test_a_decimal_does_not_become_a_year(self):
        """`magnitude 7.2` folded to `72` would match any year ending in 72."""
        self.assertEqual(numbers("magnitude 7.2"), {"7.2"})
        self.assertEqual(numbers("in 2018, 3,400 homes"), {"2018", "3400"})


class TestGrades(unittest.TestCase):
    def test_exact_quote_is_verbatim(self):
        v = classify("the harbour was closed for a week", doc())
        self.assertEqual(v.grade, "verbatim")

    def test_quote_survives_line_breaks_and_curly_quotes(self):
        v = classify("“the water re-\ntreated before the waves arrived”", doc())
        self.assertEqual(v.grade, "verbatim")

    def test_ellipsis_is_matched_fragment_by_fragment(self):
        v = classify("more than 3,400 homes were damaged … "
                     "the harbour was closed for a week", doc())
        self.assertEqual(v.grade, "verbatim_elided")

    def test_out_of_order_fragments_are_not_elided_quotes(self):
        """An ellipsis joins text in document order. Reversed is not a quote."""
        v = classify("the harbour was closed for a week … "
                     "more than 3,400 homes were damaged", doc())
        self.assertNotIn(v.grade, ("verbatim", "verbatim_elided"))

    def test_light_edits_are_near_verbatim(self):
        """Two typos in a quote. A quote with typos is still a quote."""
        v = classify("more than 3,400 homez were damagd", doc())
        self.assertEqual(v.grade, "near_verbatim")

    def test_reworded_but_same_words_is_paraphrase(self):
        v = classify("about 12,000 people displaced and 3,400 homes damaged",
                     doc())
        self.assertEqual(v.grade, "paraphrase")
        self.assertNotIn(v.grade, QUOTABLE)
        self.assertIn(v.grade, GROUNDED)

    def test_content_from_elsewhere_is_unsupported(self):
        v = classify("A magnitude 7.2 earthquake levelled the cathedral in "
                     "Christchurch, killing nobody at all.", doc())
        self.assertEqual(v.grade, "unsupported")

    def test_snippet_with_no_content_is_not_a_fabrication(self):
        self.assertEqual(classify("©", doc()).grade, "no_content")

    def test_figures_are_checked_against_the_document(self):
        v = classify("about 12,000 people were displaced and 40,000 died", doc())
        self.assertEqual(v.figures, 2)
        self.assertEqual(v.figures_found, 1)


class TestLanguageHoldOut(unittest.TestCase):
    def test_document_language_is_placed(self):
        self.assertEqual(guess_language(ENGLISH * 3), "en")
        self.assertEqual(guess_language(SPANISH * 3), "es")

    def test_non_latin_majority_beats_the_word_profile(self):
        """Romaji and English boilerplate must not carry a Japanese report."""
        self.assertEqual(guess_language("平成二十五年版 防災白書 " * 40 + "Tokyo"),
                         "CJK")

    def test_english_snippet_from_a_spanish_source_is_held_out(self):
        v = classify("About 12,000 people were displaced from the district "
                     "and the harbour was closed.", doc(SPANISH))
        self.assertEqual(v.grade, "cross_language")

    def test_a_quote_from_a_spanish_source_is_still_found(self):
        """Holding out translations must not hold out real quotes."""
        v = classify("el puerto estuvo cerrado durante una semana", doc(SPANISH))
        self.assertEqual(v.grade, "verbatim")

    def test_english_source_still_takes_the_accusation(self):
        """The hold-out must not swallow the finding on an English source."""
        v = classify("A volcano buried the capital and 40,000 people died "
                     "in the eruption of that year.", doc(ENGLISH))
        self.assertIn(v.grade, ("weak", "unsupported"))

    def test_short_snippets_carry_no_language_claim(self):
        self.assertEqual(snippet_language("600 houses"), "")


class TestRunReport(unittest.TestCase):
    def test_held_out_grades_leave_the_denominator(self):
        report = RunReport("r")
        report.snippets = 10
        report.grades.update({"verbatim": 5, "unsupported": 2,
                              "cross_script": 1, "cross_language": 1,
                              "no_content": 1})
        self.assertEqual(report.judged, 7)
        self.assertEqual(report.rate(QUOTABLE), (5, 7))


if __name__ == "__main__":
    unittest.main()
