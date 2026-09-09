"""Score every model against the human annotations. Run when annotation is done.

    python -m benchmark_openrouter.score_all              # refuses below 167/167
    python -m benchmark_openrouter.score_all --allow-partial
    python -m benchmark_openrouter.score_all --only "Claude Opus 4.1" --only "GPT-5 (OpenRouter)"

This is a driver, not a scorer. All the statistics come from
`eval/score_against_human.py`, unchanged: per-document event detection with 95%
Wilson intervals, hazard-family / location / date set P/R/F1 on the documents
gold says carry an event, and an exact McNemar test on every pair of runs. The
only work done here is assembling the `--run "label=path"` arguments — every
OpenRouter run, plus the two arms already on disk (the gpt-5 Azure production
run and the NER baseline) so the comparison has references.

THE READINESS GUARD
-------------------
Scoring a partially annotated set is the easy way to publish a number that
quietly rests on a third of the sample, and the subset is not random — it is
whatever was annotated first. So this refuses to run until all 167 documents are
marked `done`, and prints how far along you are. `--allow-partial` overrides it
and stamps the shortfall into the report title, because a caveat that lives in
someone's memory is not a caveat.
"""
from __future__ import annotations

import argparse
import csv
import logging
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_openrouter.agreement import REFERENCE_RUNS, discover_runs  # noqa: E402
from eval.prefetch_annotation_documents import queue_asset_keys  # noqa: E402

LOG = logging.getLogger("benchmark_openrouter.score_all")

OUT_DIR = REPO_ROOT / "benchmark_openrouter" / "outputs"
ANNOTATIONS = REPO_ROOT / "eval" / "human_annotations.csv"
QUEUE = REPO_ROOT / "eval" / "production_validation.csv"
SCORER = REPO_ROOT / "eval" / "score_against_human.py"
DEFAULT_REPORT = REPO_ROOT / "benchmark_openrouter" / "MODEL_SCORES.md"


def annotation_progress(path: Path) -> tuple[int, int]:
    """(documents marked done, documents in the file)."""
    csv.field_size_limit(10 ** 9)
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    done = {r["asset_key"] for r in rows
            if str(r.get("annotation_status", "")).strip().lower() == "done"}
    return len(done), len({r["asset_key"] for r in rows})


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--annotations", type=Path, default=ANNOTATIONS)
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--only", action="append", default=[],
                   help="restrict to these run labels; repeatable. Useful because "
                        "N runs produce N*(N-1)/2 McNemar rows.")
    p.add_argument("--no-references", action="store_true",
                   help="omit the gpt-5 Azure and NER baseline arms")
    p.add_argument("--exclude-uncertain", action="store_true",
                   help="drop annotations the reviewer flagged uncertain")
    p.add_argument("--allow-partial", action="store_true",
                   help="score even though annotation is incomplete")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()

    if not args.annotations.exists():
        LOG.error("No annotations at %s. Run `make annotate` first.", args.annotations)
        return 2

    expected = len(queue_asset_keys(QUEUE))
    done, _total = annotation_progress(args.annotations)
    LOG.info("Annotation progress: %d/%d documents done.", done, expected)
    if done < expected and not args.allow_partial:
        LOG.error(
            "Not ready: %d of %d documents are annotated. Scoring now would report on "
            "whichever %d were annotated first, which is not a random subset.\n"
            "Finish with `make annotate`, or pass --allow-partial to score anyway.",
            done, expected, done)
        return 1

    runs: list[tuple[str, Path]] = [(label, path)
                                    for label, path, _stats in discover_runs(args.out_dir)]
    if not runs:
        LOG.error("No OpenRouter runs under %s. Run the benchmark first.", args.out_dir)
        return 2
    if not args.no_references:
        runs += [(label, path) for label, path in REFERENCE_RUNS if path.exists()]
    if args.only:
        wanted = set(args.only)
        runs = [r for r in runs if r[0] in wanted]
        if not runs:
            LOG.error("--only matched no runs. Available: %s",
                      ", ".join(l for l, _, _ in discover_runs(args.out_dir)))
            return 2

    n = len(runs)
    LOG.info("Scoring %d run(s) — %d McNemar pairs.", n, n * (n - 1) // 2)

    cmd = [sys.executable, str(SCORER),
           "--annotations", str(args.annotations),
           "--out", str(args.report)]
    for label, path in runs:
        cmd += ["--run", f"{label}={path}"]
    if args.exclude_uncertain:
        cmd.append("--exclude-uncertain")

    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        return result.returncode

    if done < expected:
        # Stamp the shortfall into the report so it cannot be read without it.
        text = args.report.read_text(encoding="utf-8")
        args.report.write_text(
            text.replace(
                "# Extraction runs scored against human annotations",
                "# Extraction runs scored against human annotations\n\n"
                f"> **PARTIAL — {done} of {expected} documents annotated.** The scored "
                "subset is whatever was annotated first, not a random sample, so these "
                "figures are provisional.",
                1),
            encoding="utf-8")
    LOG.info("Wrote %s", args.report.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
