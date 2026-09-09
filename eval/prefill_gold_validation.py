"""
eval/prefill_gold_validation.py — build the gold-run validation queue.

Flattens a prompt-5 extraction JSONL (default: the `gold` production run) to
one row per verifiable event, scores a label-free risk heuristic, and queues a
sample for a single correct/partial/wrong verdict per event. Everything is
automated except the verdict.

Two sampling modes, and the choice decides what the resulting accuracy means:

  --sampling random  (default)  Proportional to hazard-family share of the
      population, drawn uniformly within family. The judged set is
      representative, so accuracy estimates population accuracy.
  --sampling risk               Highest auto_risk first, round-robin across
      strata. Deliberately over-weights hard cases: good for surfacing failure
      modes, but the resulting accuracy is a lower bound, not an estimate.

Adds:
  stratum      hazard bucket used for coverage (the event_hazard)
  auto_risk    0..1 heuristic risk that the extraction is wrong (always scored,
               and useful as a covariate even when sampling randomly)
  review_rank  order to work through
  in_queue     Y for the capped sample to actually judge, N otherwise
  verdict      left blank for the human (correct | partial | wrong)
  notes        left blank for the human

Risk heuristics (no labels, from the extraction itself):
  + medium/low event_confidence            (model itself is less sure)
  + multi-event document                   (disaggregation is harder)
  + vague date (year-only, "since", range)  (temporal precision risk)
  + country/region admin level             (location specificity risk)
  + thin evidence / flagged missing_information

Writes eval/gold_validation.csv (backed up first if it already exists).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
from datetime import datetime
from pathlib import Path

from fonte.hazard_families import hazard_family

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "outputs" / "gold" / "event_extractions.jsonl"
DEFAULT_OUT = REPO_ROOT / "eval" / "gold_validation.csv"

REFERENCE_FIELDS = (
    "asset_key",
    "event_index",
    "event_count",
    "title",
    "content_url",
    "language",
    "event_hazard",
    "event_dates",
    "affected_locations",
    "location_admin_levels",
    "key_impacts",
    "event_confidence",
    "evidence_snippets",
    "missing_information",
)
COMPUTED_FIELDS = ("stratum", "auto_risk", "review_rank", "in_queue")
JUDGMENT_FIELDS = ("verdict", "notes")
OUTPUT_FIELDS = (*REFERENCE_FIELDS, *COMPUTED_FIELDS, *JUDGMENT_FIELDS)

_VAGUE_DATE_HINTS = ("since", "early", "late", "mid", "around", "before", "after", "?")


def _is_verifiable(obj: dict) -> bool:
    if not str(obj.get("event_index", "")).strip():
        return False
    v = obj.get("is_verifiable_event")
    return v is True or str(v).strip().lower() == "true"


def _count_parts(value: str) -> int:
    return len([p for p in str(value or "").split("|") if p.strip()])


def _date_is_vague(value: str) -> bool:
    v = str(value or "").strip().lower()
    if not v:
        return True
    if any(h in v for h in _VAGUE_DATE_HINTS):
        return True
    # A precise date is YYYY-MM-DD; anything shorter (year, year-month) is vague.
    first = v.split("|")[0].strip()
    return len(first) < 10


def risk(obj: dict) -> float:
    r = 0.0
    conf = str(obj.get("event_confidence", "")).strip().lower()
    if conf == "medium":
        r += 0.40
    elif conf == "low":
        r += 0.60
    elif conf == "high":
        r += 0.10
    else:
        r += 0.30  # missing/unknown confidence

    try:
        if int(obj.get("event_count", 1)) > 1:
            r += 0.15
    except (TypeError, ValueError):
        pass

    if _date_is_vague(obj.get("event_dates", "")):
        r += 0.20

    admin = str(obj.get("location_admin_levels", "")).strip().lower()
    if any(a in admin for a in ("country", "national", "region", "state")):
        r += 0.20

    if _count_parts(obj.get("evidence_snippets", "")) <= 1:
        r += 0.10
    if _count_parts(obj.get("missing_information", "")) >= 1:
        r += 0.10

    return round(min(r, 1.0), 3)


def load_events(path: Path) -> list[dict]:
    events: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _is_verifiable(obj):
                events.append(obj)
    return events


def queue_round_robin(events: list[dict], target: int) -> None:
    """Mark ~target events in_queue=Y, risk-first but balanced across strata.

    Picks the highest-risk remaining event from each stratum in turn until the
    target is reached, so no single hazard dominates the sample.
    """
    by_stratum: dict[str, list[dict]] = {}
    for e in events:
        by_stratum.setdefault(e["stratum"], []).append(e)
    for group in by_stratum.values():
        group.sort(key=lambda x: x["auto_risk"], reverse=True)

    order = sorted(by_stratum.keys())
    cursors = {s: 0 for s in order}
    picked: list[dict] = []
    target = min(target, len(events))
    while len(picked) < target:
        progressed = False
        for s in order:
            if len(picked) >= target:
                break
            grp = by_stratum[s]
            i = cursors[s]
            if i < len(grp):
                picked.append(grp[i])
                cursors[s] = i + 1
                progressed = True
        if not progressed:
            break

    for e in events:
        e["in_queue"] = "N"
        e["review_rank"] = ""
    for rank, e in enumerate(picked, start=1):
        e["in_queue"] = "Y"
        e["review_rank"] = rank


def queue_random(events: list[dict], target: int, seed: int) -> None:
    """Mark ~target events in_queue=Y as a representative random sample.

    Allocation is proportional to each hazard family's share of the population
    (largest-remainder), and the draw within a family is uniform. That makes the
    judged set an unbiased estimate of population accuracy — unlike the
    risk-first queue, which deliberately over-weights hard cases — while still
    guaranteeing the family cells the report breaks results down by.
    """
    rng = random.Random(seed)
    target = min(target, len(events))

    by_family: dict[str, list[dict]] = {}
    for e in events:
        by_family.setdefault(hazard_family(e["stratum"]), []).append(e)

    # Largest-remainder allocation so the quotas sum to exactly `target`.
    total = len(events)
    exact = {f: len(g) * target / total for f, g in by_family.items()}
    quota = {f: min(int(x), len(by_family[f])) for f, x in exact.items()}
    while sum(quota.values()) < target:
        candidates = [f for f in by_family if quota[f] < len(by_family[f])]
        if not candidates:
            break
        f = max(candidates, key=lambda f: (exact[f] - quota[f], len(by_family[f])))
        quota[f] += 1

    picked: list[dict] = []
    for family, group in by_family.items():
        picked.extend(rng.sample(group, quota[family]))
    rng.shuffle(picked)

    for e in events:
        e["in_queue"] = "N"
        e["review_rank"] = ""
    for rank, e in enumerate(picked, start=1):
        e["in_queue"] = "Y"
        e["review_rank"] = rank


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                    help="Prompt-5 extraction JSONL (default: the gold run).")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="Validation CSV to write.")
    ap.add_argument("--target", type=int, default=100,
                    help="Approximate number of events to queue for judging.")
    ap.add_argument("--sampling", choices=("random", "risk"), default="random",
                    help="random: representative sample, supports a population "
                         "accuracy estimate (default). risk: highest auto_risk "
                         "first, balanced across strata — finds failure modes but "
                         "over-weights hard cases, so it measures a lower bound.")
    ap.add_argument("--seed", type=int, default=42,
                    help="Seed for --sampling random.")
    args = ap.parse_args()

    if not args.source.exists():
        ap.error(
            f"Source extraction not found: {args.source}\n"
            "Run the gold extraction first, e.g.:\n"
            "  fonte-extract --prompt 5 --limit 2000 --workers 12 "
            "--reasoning-effort medium --output-dir outputs/gold --resume"
        )

    events = load_events(args.source)
    if not events:
        ap.error(f"No verifiable events found in {args.source}.")

    for e in events:
        e["stratum"] = (e.get("event_hazard") or "(unknown)").strip() or "(unknown)"
        e["auto_risk"] = risk(e)
        e["verdict"] = ""
        e["notes"] = ""

    if args.sampling == "random":
        queue_random(events, args.target, args.seed)
    else:
        queue_round_robin(events, args.target)

    # Output rows ordered: queued first by review_rank, then the rest by risk.
    queued = [e for e in events if e["in_queue"] == "Y"]
    rest = [e for e in events if e["in_queue"] != "Y"]
    queued.sort(key=lambda x: x["review_rank"])
    rest.sort(key=lambda x: x["auto_risk"], reverse=True)
    ordered = queued + rest

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        backup = args.out.with_suffix(f".csv.bak.{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(args.out, backup)

    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(OUTPUT_FIELDS), extrasaction="ignore")
        w.writeheader()
        for e in ordered:
            w.writerow({c: e.get(c, "") for c in OUTPUT_FIELDS})

    n_strata = len({e["stratum"] for e in queued})
    print(f"{len(events)} verifiable events; queued {len(queued)} ({args.sampling} sampling) "
          f"across {n_strata} hazard strata.")

    # Show the queue against the population, so any skew is visible up front.
    print(f"\n{'hazard family':<16}{'queued':>8}{'share':>8}{'population':>12}{'share':>8}")
    pop: dict[str, int] = {}
    for e in events:
        f = hazard_family(e["stratum"])
        pop[f] = pop.get(f, 0) + 1
    qc: dict[str, int] = {}
    for e in queued:
        f = hazard_family(e["stratum"])
        qc[f] = qc.get(f, 0) + 1
    for f in sorted(pop, key=lambda f: pop[f], reverse=True):
        n_q = qc.get(f, 0)
        print(f"  {f:<14}{n_q:>8}{n_q / len(queued):>7.1%}{pop[f]:>12}{pop[f] / len(events):>8.1%}")
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
