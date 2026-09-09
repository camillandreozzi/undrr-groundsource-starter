"""
eval/score_gold_validation.py — accuracy from the gold validation pass.

Reads eval/gold_validation.csv (verdicts filled in by gold_validation_app.py)
and reports, overall and per segment:

  accuracy     correct / judged
  useful_rate  (correct + partial) / judged   # mirrors Google Groundsource's "useful" split
  counts       correct / partial / wrong / unjudged

Segments come in two granularities, both in the output under `segment_kind`:

  ALL      the whole judged queue
  family   hazard family (flood, earthquake, cyclone, …) — the level to
           report at, since a few hundred judgements spread over the 50 raw
           hazard values leaves single digits per value
  hazard   the raw event_hazard stratum, kept for drill-down only

Only in_queue == Y rows count. Writes eval/gold_validation_scores.csv, or a
name derived from --in when a non-default queue is scored.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from fonte.hazard_families import hazard_family
from fonte.stats import margin_of_error, wilson_interval

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IN = REPO_ROOT / "eval" / "gold_validation.csv"
DEFAULT_OUT = REPO_ROOT / "eval" / "gold_validation_scores.csv"

VERDICTS = ("correct", "partial", "wrong")


def _summary(rows: list[dict]) -> dict:
    c = {v: 0 for v in VERDICTS}
    unjudged = 0
    for r in rows:
        v = (r.get("verdict") or "").strip().lower()
        if v in c:
            c[v] += 1
        else:
            unjudged += 1
    judged = sum(c.values())
    acc_lo, acc_hi = wilson_interval(c["correct"], judged)
    useful = c["correct"] + c["partial"]
    use_lo, use_hi = wilson_interval(useful, judged)
    return {
        "judged": judged,
        "correct": c["correct"],
        "partial": c["partial"],
        "wrong": c["wrong"],
        "unjudged": unjudged,
        "accuracy": round(c["correct"] / judged, 3) if judged else "",
        "accuracy_lo": round(acc_lo, 3) if judged else "",
        "accuracy_hi": round(acc_hi, 3) if judged else "",
        "accuracy_moe_pp": round(margin_of_error(c["correct"], judged), 1) if judged else "",
        "useful_rate": round(useful / judged, 3) if judged else "",
        "useful_rate_lo": round(use_lo, 3) if judged else "",
        "useful_rate_hi": round(use_hi, 3) if judged else "",
    }


def _grouped(rows: list[dict], kind: str, key) -> list[dict]:
    """Summarise `rows` grouped by `key`, heaviest group first."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    out = [{"segment_kind": kind, "segment": g, **_summary(rs)} for g, rs in groups.items()]
    out.sort(key=lambda x: x["judged"], reverse=True)
    return out


def _default_out(inp: Path) -> Path:
    """gold_validation.csv -> gold_validation_scores.csv, next to the input."""
    return inp.with_name(f"{inp.stem}_scores.csv")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    ap.add_argument("--out", type=Path, default=None,
                    help="Scores CSV to write (default: <input stem>_scores.csv beside the input).")
    args = ap.parse_args()

    if not args.inp.exists():
        ap.error(f"Validation CSV not found: {args.inp}")
    out = args.out or _default_out(args.inp)

    rows = [r for r in csv.DictReader(args.inp.open(encoding="utf-8"))
            if str(r.get("in_queue", "")).strip().upper() == "Y"]
    if not rows:
        ap.error("No in_queue == Y rows to score.")

    overall = {"segment_kind": "ALL", "segment": "ALL", **_summary(rows)}
    families = _grouped(rows, "family", lambda r: hazard_family(r.get("stratum", "")))
    strata = _grouped(rows, "hazard", lambda r: r.get("stratum", "(unknown)") or "(unknown)")
    all_rows = [overall, *families, *strata]

    fields = ["segment_kind", "segment", "judged", "correct", "partial", "wrong",
              "unjudged", "accuracy", "accuracy_lo", "accuracy_hi", "accuracy_moe_pp",
              "useful_rate", "useful_rate_lo", "useful_rate_hi"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_rows)

    print(f"Wrote {out}\n")

    def _pct(d, key):
        if d["judged"] == 0:
            return "–".rjust(7)
        return f"{d[key]:.1%}".rjust(7)

    def _ci(d):
        if d["judged"] == 0:
            return ""
        return f"[{d['accuracy_lo']:.0%}–{d['accuracy_hi']:.0%}]"

    def _line(d):
        return (f"{d['segment']:<28}{d['judged']:>7}{_pct(d, 'accuracy')}"
                f"{_ci(d):>12}{_pct(d, 'useful_rate')}"
                f"  {d['correct']}/{d['partial']}/{d['wrong']}/{d['unjudged']}")

    print(f"{'segment':<28}{'judged':>7}{'acc':>7}{'95% CI':>12}{'useful':>7}  (✓/~/✗/?)")
    print(_line(overall))
    for title, group in (("By hazard family", families), ("By raw hazard stratum", strata)):
        print(f"\n{title}")
        print("-" * 78)
        for d in group:
            print(_line(d))
    if overall["judged"]:
        print(f"\n95% CIs are Wilson intervals. Overall accuracy is "
              f"±{overall['accuracy_moe_pp']}pp at n={overall['judged']}.")
    if overall["unjudged"]:
        print(f"Note: {overall['unjudged']} of {len(rows)} queued events still unjudged.")


if __name__ == "__main__":
    main()
