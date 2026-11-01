from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = REPO_ROOT / "eval" / "link_audit_app.py"


def load_app_module():
    spec = importlib.util.spec_from_file_location("link_audit_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


WINDOW = ("In 2010 heavy floods hit Sindh province. Thousands were displaced. "
          "Separately, the 2005 earthquake struck Kashmir <and> Muzaffarabad.")


class ValidateDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = load_app_module()

    def test_needs_an_answer(self) -> None:
        self.assertEqual(self.app.validate_decision("link_C", None, "", "1", ["1", "2"]),
                         ["Choose an answer."])

    def test_unpaired_disagree_needs_an_event(self) -> None:
        self.assertTrue(self.app.validate_decision("fp", "disagree", "", "", ["1", "2"]))
        self.assertEqual(self.app.validate_decision("fp", "disagree", "2", "", ["1", "2"]), [])

    def test_link_disagree_may_name_none(self) -> None:
        self.assertEqual(self.app.validate_decision("link_AB", "disagree", "", "1", ["1", "2"]), [])

    def test_rejects_the_linked_event_and_foreign_ids(self) -> None:
        self.assertTrue(self.app.validate_decision("link_C", "disagree", "1", "1", ["1", "2"]))
        self.assertTrue(self.app.validate_decision("link_C", "disagree", "9", "1", ["1", "2"]))

    def test_agree_is_enough(self) -> None:
        self.assertEqual(self.app.validate_decision("fp", "agree", "", "", ["1"]), [])


class DecisionRowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = load_app_module()
        self.row = {"audit_id": "3", "kind": "link_C", "asset_key": "k", "gold_event_id": "1",
                    "pred_dates": "2016-02", "verdict": "", "correct_gold_event_id": "",
                    "notes": "", "seconds_spent": "10"}

    def test_notes_roundtrip(self) -> None:
        stored = self.app.join_notes(["unclear", "merged"], "  five cyclones ")
        self.assertEqual(stored, "merged; unclear; five cyclones")
        self.assertEqual(self.app.split_notes(stored), (["merged", "unclear"], "five cyclones"))

    def test_apply_keeps_other_columns_and_clears_id_on_agree(self) -> None:
        out = self.app.apply_decision({**self.row, "correct_gold_event_id": "2"}, "agree", "2",
                                      [], "", 5, "2026-11-01T00:00:00+00:00")
        self.assertEqual(out["verdict"], "agree")
        self.assertEqual(out["correct_gold_event_id"], "")
        self.assertEqual(out["pred_dates"], "2016-02")
        self.assertEqual(out["seconds_spent"], "15")

    def test_csv_roundtrip_through_the_audit_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.csv"
            fields = list(self.row)
            self.app.write_csv_atomic(path, fields, [self.row])
            fieldnames, rows = self.app.load_audit(path)
            self.assertEqual(fieldnames, fields + ["audited_at"])
            rows[0] = self.app.apply_decision(rows[0], "disagree", "2", ["merged"], "", 0, "t")
            self.app.write_csv_atomic(path, fieldnames, rows)
            _, again = self.app.load_audit(path)
            self.assertEqual((again[0]["verdict"], again[0]["correct_gold_event_id"],
                              again[0]["notes"], again[0]["pred_dates"]),
                             ("disagree", "2", "merged", "2016-02"))


class HighlightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = load_app_module()

    def test_marks_each_kind_and_escapes(self) -> None:
        body, kinds = self.app.highlight_window(
            WINDOW, ['"heavy floods hit Sindh province"', "not in this window at all, anywhere"],
            ["In 2010 heavy floods hit Sindh province."],
            ["the 2005 earthquake struck Kashmir <and> Muzaffarabad."])
        self.assertEqual(kinds, ["exact", "none"])
        self.assertIn("data-rec", body)
        self.assertIn("data-gold", body)
        self.assertIn("data-other", body)
        self.assertIn("&lt;and&gt;", body)
        self.assertNotIn("<and>", body)
        # The record's evidence sits inside the linked quote: shaded and underlined.
        self.assertIn("background:#ffe08a;border-bottom:3px solid #16a34a", body)

    def test_plain_text_when_nothing_is_located(self) -> None:
        body, kinds = self.app.highlight_window(WINDOW, [], [], [])
        self.assertEqual(kinds, [])
        self.assertNotIn("<span", body)

    def test_gold_label(self) -> None:
        label = self.app.gold_label({"gold_event_id": "2", "hazard_primary": "Earthquake",
                                     "hazard_secondary": "Tsunami", "year_start": "2004",
                                     "year_end": "2005", "locations": "Aceh | Sri Lanka",
                                     "verifiable": "no"})
        self.assertEqual(label, "2: Earthquake + Tsunami 2004–2005 — Aceh, Sri Lanka · "
                                "not verifiable")


if __name__ == "__main__":
    unittest.main()
