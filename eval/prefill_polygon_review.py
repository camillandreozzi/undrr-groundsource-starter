"""
eval/prefill_polygon_review.py — auto-prioritise the polygon validation pass.

The generated sample is too large to hand-judge. This caps it to a review queue
and scores a label-free risk heuristic on every row.

Two sampling modes, and the choice decides what the resulting accuracy means:

  --sampling random  (default)  Allocates the queue across strata in proportion
      to their POOL sizes (from polygon_validation_summary.json), drawing
      uniformly within each stratum. Because the sample itself was drawn
      randomly per stratum, the queue is then representative of all resolved +
      unresolved locations, so accuracy estimates population accuracy.
  --sampling risk               Highest auto_risk first, fixed rows per stratum.
      Surfaces failure modes, but over-weights hard cases and equal-weights
      strata of very different sizes, so accuracy is a lower bound.

Adds:
  auto_risk    0..1 heuristic risk that the resolution is wrong
  review_rank  order to work through
  in_queue     Y for the capped sample to actually judge, N otherwise

Heuristics (label-free, from resolver metadata):
  + used a country-level fallback        (coarse / overshoot risk)
  + admin_level == 'country' but the text names a sub-national place
  + low resolution_confidence
  + huge area_km2 for a place that reads specific
Does not fill location_correct/geometry_correct/date_correct — those stay blank
for the human. Backs up the file first.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
from datetime import datetime
from pathlib import Path

DEFAULT = (
    "outputs/test_2000_gpt5_medium_prompt05_polygon_validation/"
    "polygon_validation_sample.csv"
)


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def risk(row: dict) -> float:
    r = 0.0
    if str(row.get("resolution_used_fallback", "")).strip().lower() in {"true", "1", "yes"}:
        r += 0.4
    admin = str(row.get("resolution_admin_level", "")).strip().lower()
    text = str(row.get("location_text", "")).strip()
    if admin == "country" and len(text.split()) > 1:
        r += 0.25
    conf = _f(row.get("resolution_confidence"), 1.0)
    if conf < 0.4:
        r += 0.25
    elif conf < 0.7:
        r += 0.1
    if _f(row.get("area_km2")) > 500_000 and admin in {"", "region", "state"}:
        r += 0.1
    return min(r, 1.0)


def _pool_sizes(path: Path, strata: list[str]) -> dict[str, int]:
    """Population size per stratum, from the sample builder's summary."""
    summary = path.parent / "polygon_validation_summary.json"
    if summary.exists():
        pools = json.loads(summary.read_text()).get("pool_sizes", {})
        if all(s in pools for s in strata):
            return {s: int(pools[s]) for s in strata}
    raise SystemExit(
        f"Need pool sizes for proportional sampling but could not read them from {summary}.\n"
        "Re-run scripts/make_polygon_validation_sample.py, or pass --sampling risk."
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT)
    ap.add_argument("--per-stratum", type=int, default=20,
                    help="rows to queue per stratum, for --sampling risk")
    ap.add_argument("--total", type=int, default=60,
                    help="total rows to queue, for --sampling random")
    ap.add_argument("--sampling", choices=("random", "risk"), default="random",
                    help="random: pool-proportional, supports a population accuracy "
                         "estimate (default). risk: highest auto_risk first per stratum.")
    ap.add_argument("--seed", type=int, default=42, help="Seed for --sampling random.")
    args = ap.parse_args()

    path = Path(__file__).resolve().parent.parent / args.file
    rows = list(csv.DictReader(path.open()))
    shutil.copy(path, path.with_suffix(f".csv.bak.{datetime.now():%Y%m%d-%H%M%S}"))

    for r in rows:
        r["auto_risk"] = round(risk(r), 3)

    by_stratum: dict[str, list[dict]] = {}
    for r in rows:
        by_stratum.setdefault(r.get("stratum", "?"), []).append(r)

    if args.sampling == "risk":
        # Rank within stratum by risk desc; queue the top `per-stratum` of each.
        for group in by_stratum.values():
            group.sort(key=lambda x: x["auto_risk"], reverse=True)
            for i, r in enumerate(group, 1):
                r["review_rank"] = i
                r["in_queue"] = "Y" if i <= args.per_stratum else "N"
    else:
        # Allocate proportional to pool size, then draw uniformly within stratum.
        strata = sorted(by_stratum)
        pools = _pool_sizes(path, strata)
        total_pool = sum(pools.values())
        exact = {s: pools[s] * args.total / total_pool for s in strata}
        quota = {s: min(int(x), len(by_stratum[s])) for s, x in exact.items()}
        while sum(quota.values()) < min(args.total, len(rows)):
            candidates = [s for s in strata if quota[s] < len(by_stratum[s])]
            if not candidates:
                break
            s = max(candidates, key=lambda s: exact[s] - quota[s])
            quota[s] += 1

        rng = random.Random(args.seed)
        for r in rows:
            r["in_queue"] = "N"
            r["review_rank"] = ""
        picked: list[dict] = []
        for s in strata:
            picked.extend(rng.sample(by_stratum[s], quota[s]))
        rng.shuffle(picked)
        for i, r in enumerate(picked, 1):
            r["review_rank"] = i
            r["in_queue"] = "Y"

    fields = list(rows[0].keys())
    for c in ("auto_risk", "review_rank", "in_queue"):
        if c not in fields:
            fields.append(c)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    queued = sum(1 for r in rows if r.get("in_queue") == "Y")
    print(f"{len(rows)} rows scored; queued {queued} for human judgement "
          f"({args.sampling} sampling).")
    pools = _pool_sizes(path, sorted(by_stratum)) if args.sampling == "random" else None
    total_pool = sum(pools.values()) if pools else 0
    for s, g in sorted(by_stratum.items()):
        q = sum(1 for r in g if r["in_queue"] == "Y")
        line = f"  {s:<18}{q:>4} queued of {len(g):>4} sampled"
        if pools:
            line += (f"   queue share {q / queued:>6.1%}"
                     f"   population share {pools[s] / total_pool:>6.1%}")
        print(line)


if __name__ == "__main__":
    main()
