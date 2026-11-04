"""Unit tests for the supervised extractor (benchmark_supervised/).

The parts where a silent bug would read as a quality difference rather than a
crash: candidate extraction, the parse-to-hay offset map, gold labelling, the
fold split (a window must never train the model that predicts it), clustering
and decoding. Parses are synthetic, so no spaCy model is loaded.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_supervised.features import (  # noqa: E402
    SNIPPET_MAX, Doc, gold_assignment, place_label, year_label,
)
from benchmark_supervised.model import Extractor, MaxEnt, TrainingWindow, cluster_mentions  # noqa: E402
from benchmark_supervised.parse import PRIMARY_MODEL, Parsed  # noqa: E402
from benchmark_supervised.run import folds  # noqa: E402
from eval.event_matching import GoldEvent  # noqa: E402


def make_parsed(text: str, places: tuple[str, ...] = (), key: str = "k" * 64) -> Parsed:
    """A minimal parse: word tokens, sentences split at full stops, every
    occurrence of each name in `places` tagged GPE by the primary model."""
    tokens = [[m.start(), m.end(), m.group(0).lower(), "NN", "NOUN", i, False]
              for i, m in enumerate(re.finditer(r"\w+|[^\w\s]", text))]
    sents, start = [], 0
    for m in re.finditer(r"\.(?:\s|$)", text):
        sents.append((start, m.end()))
        start = m.end()
    if start < len(text):
        sents.append((start, len(text)))
    ents = sorted([m.start(), m.end(), "GPE", PRIMARY_MODEL]
                  for name in places for m in re.finditer(re.escape(name), text))
    return Parsed(key=key, text=text, sents=sents, tokens=tokens, ents=ents, models={})


def gold(key: str, gid: int, hazard: str, year: int, locations: tuple[str, ...],
         quote: str) -> GoldEvent:
    return GoldEvent(asset_key=key, gold_event_id=gid, hazard_primary=hazard,
                     hazard_secondary=(), year_start=year, year_end=year,
                     locations=locations, support_quotes=(quote,), verifiable=True)


class TestCandidates(unittest.TestCase):
    def test_years(self):
        doc = Doc(make_parsed("Floods in 1999-2001, the 1990s, 12000 people, and plans for 2030."))
        values = {c.value: c for c in doc.years}
        self.assertEqual(set(values), {"1999", "2001", "2030"})
        self.assertTrue(values["1999"].mentions[0].in_range)
        self.assertTrue(values["2001"].mentions[0].in_range)
        self.assertFalse(values["2030"].mentions[0].in_range)

    def test_places_group_by_casefolded_value(self):
        doc = Doc(make_parsed("Floods hit Kenya. Later Kenya recovered.", places=("Kenya",)))
        self.assertEqual([c.value for c in doc.places], ["Kenya"])
        self.assertEqual(len(doc.places[0].mentions), 2)

    def test_triggers_come_from_the_lexicon(self):
        doc = Doc(make_parsed("An earthquake and a tsunami struck."))
        self.assertEqual([t.label for t in doc.triggers], ["Earthquake", "Tsunami"])


class TestOffsets(unittest.TestCase):
    def test_ligature_shifts_hay_offsets(self):
        text = "The ﬁre service responded to the flood in 2010."
        doc = Doc(make_parsed(text))
        self.assertEqual(doc.to_hay(len(text)), len(text.casefold()))
        flood = next(t for t in doc.triggers if t.label == "Flood")
        self.assertEqual(text.casefold()[doc.to_hay(flood.start):].split()[0], "flood")

    def test_gold_assignment_survives_a_ligature(self):
        text = "A ﬁeld report. The flood of 2010 hit Kenya. Droughts are common."
        doc = Doc(make_parsed(text, places=("Kenya",)))
        g = gold(doc.key, 1, "Flood", 2010, ("Kenya",), "The flood of 2010 hit Kenya.")
        assignment = gold_assignment(doc, [g])
        flood = next(t for t in doc.triggers if t.label == "Flood")
        drought = next(t for t in doc.triggers if t.label.startswith("Drought"))
        self.assertEqual(assignment, {flood.idx: 1})
        self.assertNotIn(drought.idx, assignment)


class TestLabels(unittest.TestCase):
    def test_year_and_place_labels(self):
        doc = Doc(make_parsed("Floods in 2010 and 2012 hit Kenya and Peru.", places=("Kenya", "Peru")))
        g = gold(doc.key, 1, "Flood", 2010, ("Kenya",), "Floods in 2010")
        years = {c.value: year_label(c, g) for c in doc.years}
        places = {c.value: place_label(c, g) for c in doc.places}
        self.assertEqual(years, {"2010": 1, "2012": 0})
        self.assertEqual(places, {"Kenya": 1, "Peru": 0})


class TestFolds(unittest.TestCase):
    def test_lowo_and_kfold_partition_the_windows(self):
        keys = [f"w{i:02d}" for i in range(23)]
        for split in (folds(keys, None, None), folds(keys, 5, 48)):
            flat = [k for fold in split for k in fold]
            self.assertEqual(sorted(flat), keys)
            self.assertEqual(len(flat), len(set(flat)))
        self.assertTrue(all(len(f) == 1 for f in folds(keys, None, None)))

    def test_kfold_is_seeded(self):
        keys = [f"w{i:02d}" for i in range(23)]
        self.assertEqual(folds(keys, 5, 48), folds(keys, 5, 48))
        self.assertNotEqual(folds(keys, 5, 48), folds(keys, 5, 49))


class _Stub:
    """A coref model: same hazard label -> same event."""

    def __init__(self, doc):
        self.doc = doc

    def proba(self, X):
        import numpy as np
        return np.array([1.0 if x["same_label"] else 0.0 for x in X])


class TestDecoding(unittest.TestCase):
    def test_constant_classifier_on_one_class(self):
        clf = MaxEnt().fit([{"a": 1.0}, {"a": 2.0}], [0, 0])
        self.assertEqual(list(clf.proba([{"a": 3.0}])), [0.0])

    def test_clustering_follows_coref(self):
        doc = Doc(make_parsed("The flood. The earthquake. More flooding. The quake."))
        groups = cluster_mentions(doc, doc.triggers, _Stub(doc))
        self.assertEqual([[t.label for t in g] for g in groups],
                         [["Flood", "Flood"], ["Earthquake", "Earthquake"]])

    def test_snippet_is_verbatim_and_bounded(self):
        text = ("word " * 200) + "the flood of 2010 " + ("word " * 200)
        doc = Doc(make_parsed(text))
        snip = doc.snippet(doc.triggers[0])
        self.assertIn("flood", snip)
        self.assertIn(snip, text)
        self.assertLessEqual(len(snip), SNIPPET_MAX + 40)

    def test_fit_and_predict_end_to_end(self):
        texts = [
            ("a" * 64, "Report. The flood of 2010 hit Kenya, killing 30. Flood risk will grow by 2030."),
            ("b" * 64, "Report. The earthquake of 2015 hit Nepal, killing 900. Earthquake drills are planned."),
            ("c" * 64, "Report. The flood of 2012 hit Peru, killing 12. Flood plans will follow in 2031."),
        ]
        places = ("Kenya", "Nepal", "Peru")
        windows = []
        for key, text in texts:
            doc = Doc(make_parsed(text, places, key))
            hazard, year, place = {"a": ("Flood", 2010, "Kenya"), "b": ("Earthquake", 2015, "Nepal"),
                                   "c": ("Flood", 2012, "Peru")}[key[0]]
            quote = next(s for s in text.split(". ") if str(year) in s)
            windows.append(TrainingWindow(doc, [gold(key, 1, hazard, year, (place,), quote)]))
        extractor = Extractor.fit(windows[:2])
        events, detail = extractor.predict(windows[2].doc)
        self.assertEqual(len(events), len(detail))
        for e in events:
            self.assertEqual(set(e), {"event_hazard", "event_dates", "affected_locations",
                                      "location_admin_levels", "key_impacts", "event_confidence",
                                      "evidence_snippets", "missing_information"})
            for s in e["evidence_snippets"]:
                self.assertIn(s, windows[2].doc.text)


if __name__ == "__main__":
    unittest.main()
