"""
Pack the blind event-level annotation (Experiment A) for a second annotator.

    python3 eval/pack_event_annotation.py --annotator "Name"    # or: make event-pack ANNOTATOR="Name"

WHAT GOES IN, AND WHAT STAYS OUT
--------------------------------
The annotator gets a zip they can run without the repository: the annotation
app and the two modules it imports, the 45 queued windows, and protocol §1 as
the guideline, verbatim, so both annotators work from the same text.

The repository is not sent, because it holds everything the annotation must be
blind to: the first annotator's gold, every model's output, the scores and the
paper. Inside the zip:

- the queue keeps `asset_key`, `review_rank`, `title`, `content_url` and
  `in_queue`; the stratum, the earlier annotation's hazard and year counts and
  the seed count are dropped, since the CSV can be opened outside the app;
- the document store holds the queued windows' text and nothing else;
- there is no window-status or gold file. The app creates both, empty, on
  first run.

The annotator sends back `eval/event_level_windows.csv` and
`eval/event_level_gold.csv` from their copy. Keep them under new names, e.g.
`eval/event_level_gold_<name>.csv`, so they never overwrite the first
annotator's files.

Output: `outputs/event_annotation_<name>.zip` (gitignored). Refuses to
overwrite it without --force.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL = REPO_ROOT / "eval"
QUEUE = EVAL / "event_level_queue.csv"
PROTOCOL = EVAL / "EVENT_LEVEL_PROTOCOL.md"
DOCUMENT_STORES = (EVAL / "annotation_documents.json",
                   EVAL / "annotation_documents_document_sample.json")
# The app and what it imports, copied unchanged.
CODE = ("eval/event_annotation_app.py", "eval/human_annotation_app.py",
        "benchmark_ner/__init__.py", "benchmark_ner/hazard_lexicon.py")
QUEUE_COLUMNS = ("asset_key", "review_rank", "title", "content_url", "in_queue")
# The version annotator 1 ran.
STREAMLIT = "streamlit==1.57.0"
TOP = "event_annotation"

STREAMLIT_CONFIG = """\
[server]
showEmailPrompt = false
address = "localhost"

[browser]
gatherUsageStats = false
"""

START_COMMAND = """\
#!/bin/sh
# macOS / Linux. Double-click on a Mac, or run ./start.command in a terminal.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "First run: installing Streamlit into .venv (one minute)..."
  python3 -m venv .venv && .venv/bin/python -m pip install -q -r requirements.txt || exit 1
fi
ANNOTATOR="${{ANNOTATOR:-{annotator}}}" exec .venv/bin/python -m streamlit run eval/event_annotation_app.py
"""

START_BAT = """\
@echo off
rem Windows. Double-click, or run start.bat in a terminal.
cd /d "%~dp0"
if not exist .venv\\Scripts\\python.exe (
  echo First run: installing Streamlit into .venv ^(one minute^)...
  python -m venv .venv || exit /b 1
  .venv\\Scripts\\python -m pip install -q -r requirements.txt || exit /b 1
)
if "%ANNOTATOR%"=="" set ANNOTATOR={annotator}
.venv\\Scripts\\python -m streamlit run eval\\event_annotation_app.py
"""

README = """\
# Event-level annotation: {n} windows

Thank you for annotating. Each window is the first 12,000 characters of a
disaster-risk document. For each one, record every concrete hazard event it
reports: hazard, year(s), affected places, and verbatim quotes that show it.
The rules are in `GUIDELINE.md`. Read it once before you start, and open it
again whenever you are unsure. The app's sidebar has a short version.

## Running it

You need Python 3.10 or newer (https://www.python.org/downloads/).

- **Mac / Linux:** double-click `start.command`, or run `./start.command`
  in a terminal from this folder. If macOS blocks it, right-click it and
  choose Open.
- **Windows:** double-click `start.bat`.

The first run installs Streamlit into a `.venv` folder here, which takes about
a minute. After that the app opens in your browser at http://localhost:8501.
Keep the terminal window open while you work.

Your work is saved each time you press **Save & next**. You can stop whenever
you like: close the browser tab and the terminal, run the start script again
later, and the app takes you to the next window you have not annotated.

## Please

- Work alone, from the window text and this guideline. Do not discuss
  particular documents with anyone until you have sent your files back.
- Quote from the window shown in the app. The source link is there for
  context only.
- Expect roughly 10 minutes per window. The timer pauses between sessions.

## When you are done

Email these two files back as attachments. They are in the `eval` folder
inside this folder:

- `eval/event_level_windows.csv`
- `eval/event_level_gold.csv`

Please don't open and save them in Excel or Numbers first: a spreadsheet can
change the text encoding and break the quotes. (Files ending in `.bak.<date>`
are automatic backups. You can ignore them.)
"""


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "annotator"


def guideline(protocol: str) -> str:
    """Protocol §1, verbatim: the same rules the first annotator worked from."""
    match = re.search(r"^## 1\..*?(?=^## 2\.)", protocol, flags=re.S | re.M)
    if not match:
        raise SystemExit(f"Could not find §1 in {PROTOCOL}")
    return "# Annotation guideline\n\n" + match.group(0).split("\n", 1)[1].strip() + "\n"


def blind_queue(path: Path) -> tuple[list[dict[str, str]], str]:
    """The queued rows, with every column outside QUEUE_COLUMNS dropped."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if str(r.get("in_queue", "")).strip().upper() == "Y"]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=QUEUE_COLUMNS, extrasaction="ignore",
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return rows, out.getvalue()


def blind_documents(asset_keys: list[str]) -> dict:
    """A document store holding only these windows' text."""
    documents: dict[str, dict] = {}
    for store in DOCUMENT_STORES:
        with store.open(encoding="utf-8") as f:
            documents.update(json.load(f).get("documents", {}))
    missing = [k for k in asset_keys if not documents.get(k, {}).get("text")]
    if missing:
        raise SystemExit(f"No window text for {len(missing)} queued windows, e.g. {missing[0]}")
    return {
        "source": "eval/pack_event_annotation.py",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "document_count": len(asset_keys),
        "missing": [],
        "documents": {k: {"text": documents[k]["text"], "char_count": len(documents[k]["text"])}
                      for k in asset_keys},
    }


def build_bundle(out_path: Path, annotator: str = "") -> list[str]:
    """Write the zip; return the paths inside it."""
    rows, queue_csv = blind_queue(QUEUE)
    keys = [r["asset_key"] for r in rows]
    files: dict[str, tuple[str | bytes, int]] = {
        path: ((REPO_ROOT / path).read_bytes(), 0o644) for path in CODE}
    files.update({
        "eval/event_level_queue.csv": (queue_csv, 0o644),
        "eval/annotation_documents.json":
            (json.dumps(blind_documents(keys), ensure_ascii=False), 0o644),
        "GUIDELINE.md": (guideline(PROTOCOL.read_text(encoding="utf-8")), 0o644),
        "README.md": (README.format(n=len(keys)), 0o644),
        "requirements.txt": (STREAMLIT + "\n", 0o644),
        ".streamlit/config.toml": (STREAMLIT_CONFIG, 0o644),
        "start.command": (START_COMMAND.format(annotator=annotator), 0o755),
        "start.bat": (START_BAT.format(annotator=annotator).replace("\n", "\r\n"), 0o644),
    })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, (content, mode) in sorted(files.items()):
            info = zipfile.ZipInfo(f"{TOP}/{name}", date_time=datetime.now().timetuple()[:6])
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, content)
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument("--annotator", default="",
                        help="name stamped on each window (they can change it in the app)")
    parser.add_argument("--out", type=Path,
                        help="zip path (default outputs/event_annotation_<name>.zip)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing zip")
    args = parser.parse_args(argv)

    out = args.out or REPO_ROOT / "outputs" / f"event_annotation_{_slug(args.annotator)}.zip"
    if out.exists() and not args.force:
        print(f"{out} exists; pass --force to rebuild it.", file=sys.stderr)
        return 1
    names = build_bundle(out, args.annotator.strip())
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {len(names)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
