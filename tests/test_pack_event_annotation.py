from __future__ import annotations

import csv
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_PATH = REPO_ROOT / "eval" / "pack_event_annotation.py"


def load_pack_module():
    spec = importlib.util.spec_from_file_location("pack_event_annotation", PACK_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pack = load_pack_module()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.zip_path = Path(cls.tmp.name) / "bundle.zip"
        cls.pack.build_bundle(cls.zip_path, annotator="Second Annotator")
        with zipfile.ZipFile(cls.zip_path) as zf:
            cls.names = set(zf.namelist())
            cls.zf_read = {n: zf.read(n) for n in cls.names}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def _read(self, path: str) -> str:
        return self.zf_read[f"{self.pack.TOP}/{path}"].decode("utf-8")

    def test_no_gold_and_no_model_output(self) -> None:
        for name in self.names:
            self.assertNotIn("event_level_gold", name)
            self.assertNotIn("event_level_windows", name)
            self.assertNotIn("score", name)
            self.assertNotIn("extractions", name)

    def test_queue_keeps_only_blind_columns(self) -> None:
        rows = list(csv.DictReader(io.StringIO(self._read("eval/event_level_queue.csv"))))
        self.assertEqual(tuple(rows[0].keys()), self.pack.QUEUE_COLUMNS)
        self.assertTrue(all(r["in_queue"] == "Y" for r in rows))

    def test_documents_are_the_queued_windows_only(self) -> None:
        rows = list(csv.DictReader(io.StringIO(self._read("eval/event_level_queue.csv"))))
        docs = json.loads(self._read("eval/annotation_documents.json"))["documents"]
        self.assertEqual(set(docs), {r["asset_key"] for r in rows})
        self.assertTrue(all(set(d) == {"text", "char_count"} for d in docs.values()))

    def test_guideline_is_protocol_section_1(self) -> None:
        guideline = self._read("GUIDELINE.md")
        self.assertIn("What counts as an event", guideline)
        self.assertNotIn("## 2.", guideline)
        self.assertNotIn("Deviations", guideline)

    def test_start_script_is_executable_and_named(self) -> None:
        with zipfile.ZipFile(self.zip_path) as zf:
            info = zf.getinfo(f"{self.pack.TOP}/start.command")
        self.assertTrue((info.external_attr >> 16) & 0o111)
        self.assertIn('${ANNOTATOR:-Second Annotator}', self._read("start.command"))

    def test_app_imports_from_the_bundle_alone(self) -> None:
        with tempfile.TemporaryDirectory() as out:
            with zipfile.ZipFile(self.zip_path) as zf:
                zf.extractall(out)
            root = Path(out) / self.pack.TOP
            probe = ("import importlib.util, sys; "
                     "spec = importlib.util.spec_from_file_location('app', 'eval/event_annotation_app.py'); "
                     "app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app); "
                     "import benchmark_ner.hazard_lexicon as h; "
                     "print(len(app._hazard_vocabulary()), h.__file__)")
            result = subprocess.run([sys.executable, "-I", "-c", probe], cwd=root,
                                    capture_output=True, text=True, check=True)
        count, lexicon = result.stdout.split()
        self.assertGreater(int(count), 0)
        self.assertTrue(lexicon.startswith(str(root.resolve())) or lexicon.startswith(str(root)))


if __name__ == "__main__":
    unittest.main()
