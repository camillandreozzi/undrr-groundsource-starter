"""
eval/score_polygon_validation.py — the END of the polygon-validation pass.

Reads the hand-judged polygon validation sample and reports accuracy for
location / geometry / date, overall and by confidence stratum. Only counts
rows the human actually judged (location_correct filled). Writes a one-page
eval/POLYGON_VALIDATION.md, or wherever --out points.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from fonte.stats import wilson_interval

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT = (
    "outputs/test_2000_gpt5_medium_prompt05_polygon_validation/"
    "polygon_validation_sample.csv"
)
DEFAULT_OUT = "eval/POLYGON_VALIDATION.md"
JUDGE = ["location_correct", "geometry_correct", "date_correct"]


def _yes(v) -> bool | None:
    s = str(v).strip().lower()
    if s in {"y", "yes", "true", "1"}:
        return True
    if s in {"n", "no", "false", "0"}:
        return False
    return None


def _rate(rows, col):
    vals = [_yes(r.get(col)) for r in rows]
    vals = [v for v in vals if v is not None]
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)


def _counts(rows, col) -> tuple[int, int]:
    vals = [v for v in (_yes(r.get(col)) for r in rows) if v is not None]
    return sum(vals), len(vals)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT,
                    help="Judged polygon_validation_sample.csv (repo-relative or absolute).")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="Markdown report to write (repo-relative or absolute).")
    args = ap.parse_args()
    path = REPO_ROOT / args.file
    rows = [r for r in csv.DictReader(path.open()) if _yes(r.get("location_correct")) is not None]
    if not rows:
        print("No judged rows yet (location_correct is blank everywhere).")
        return

    lines = [f"# Polygon validation — {path.parent.name}", "",
             f"Generated: {datetime.now():%Y-%m-%d %H:%M}",
             f"Source: `{args.file}`", "",
             f"Judged rows: **{len(rows)}**", "",
             "| Field | Accuracy | 95% CI | n |",
             "|---|---:|:---:|---:|"]
    for col in JUDGE:
        k, n = _counts(rows, col)
        if n:
            lo, hi = wilson_interval(k, n)
            lines.append(f"| {col} | {k / n:.1%} | {lo:.1%}–{hi:.1%} | {n} |")
        else:
            lines.append(f"| {col} | – | – | 0 |")

    lines += ["", "## By confidence stratum", "",
              "| Stratum | location | geometry | date | n |", "|---|---:|---:|---:|---:|"]
    strata: dict[str, list] = {}
    for r in rows:
        strata.setdefault(r.get("stratum", "?"), []).append(r)
    for s, g in sorted(strata.items()):
        cells = []
        for col in JUDGE:
            rate, _ = _rate(g, col)
            cells.append(f"{rate:.0%}" if rate is not None else "–")
        lines.append(f"| {s} | {cells[0]} | {cells[1]} | {cells[2]} | {len(g)} |")

    lines += [
        "",
        "Intervals are 95% Wilson score intervals. Per-stratum cells are small —",
        "read them as indicative and rely on the overall row for the headline.",
    ]

    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n-> wrote {out}")


if __name__ == "__main__":
    main()
