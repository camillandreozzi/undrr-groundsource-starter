"""
Draw the windows for the event-level stress test (Experiment A).

    python3 eval/sample_event_level_windows.py          # or: make event-sample

WHAT IS DRAWN, AND FROM WHERE
-----------------------------
The frame is the 217 documents already annotated at document level
(`eval/human_annotations_pooled.csv`), kept where the annotator said the window
reports an event, the window reads as English, and the pooled annotation names
at most `MAX_YEARS` distinct years (a workload cap; how many it removes is
written to the summary).

The goal is to test whether a system keeps hazard, year and place together when
a window holds several occurrences, so multi-event windows are over-sampled.
Strata come from the **earlier human annotation only** — the pooled hazards and
years the annotator listed — never from what any model extracted:

  single                   ≤1 hazard, ≤1 year      the control
  same_hazard_multi_year   1 hazard, ≥2 years      where matching on hazard fails
  multi_hazard_same_year   ≥2 hazards, ≤1 year     where hazard/place can swap
  multi_hazard_multi_year  ≥2 hazards, ≥2 years    the reviewers' example

These are proxies: the pooled annotation does not say which year goes with
which hazard, which is the reason for the new annotation. Results are reported
by the new gold's own event count as well as by stratum.

Hazards are compared with `event_matching.hazard_key`, years with
`score_against_human._years`, so the proxy uses the scorer's own rules.

Within a stratum the draw is uniform over the eligible windows sorted by
asset_key, seeded, so it depends on the seed alone. The combined queue is then
shuffled, so the annotator meets the strata interleaved and the queue order
gives no hint of which stratum a window came from.

If a stratum has fewer eligible windows than its allocation, all of them are
taken and the shortfall moves to `SHORTFALL_TO` (protocol §2). The summary
records it.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_openrouter.citation_quality import guess_language  # noqa: E402
from eval.event_matching import hazard_key  # noqa: E402
from eval.human_annotation_app import load_document_store, read_csv, write_csv_atomic  # noqa: E402
from eval.score_against_human import _split, _years  # noqa: E402

LOG = logging.getLogger("eval.sample_event_level_windows")

EVAL = REPO_ROOT / "eval"
DEFAULT_FRAME = EVAL / "human_annotations_pooled.csv"
DEFAULT_STORES = (EVAL / "annotation_documents.json",
                  EVAL / "annotation_documents_document_sample.json")
DEFAULT_OUT = EVAL / "event_level_queue.csv"

#: Neither 42 (event sample) nor 43 (document sample): a third, visibly
#: independent draw.
DEFAULT_SEED = 44
MAX_YEARS = 8
ALLOCATION: tuple[tuple[str, int], ...] = (
    ("single", 15),
    ("same_hazard_multi_year", 10),
    ("multi_hazard_same_year", 10),
    ("multi_hazard_multi_year", 10),
)
SHORTFALL_TO = "multi_hazard_multi_year"

QUEUE_COLUMNS = (
    "asset_key", "review_rank", "stratum", "sample_arm", "title", "content_url",
    "window_chars", "prior_hazard_keys", "prior_years", "seed_event_count", "in_queue",
)


class SamplingError(RuntimeError):
    pass


def proxy_stratum(row: dict) -> str:
    keys = {hazard_key(h) for h in _split(row.get("gold_hazards"))}
    years = _years(_split(row.get("gold_dates")))
    if len(keys) <= 1:
        return "single" if len(years) <= 1 else "same_hazard_multi_year"
    return "multi_hazard_same_year" if len(years) <= 1 else "multi_hazard_multi_year"


def build_frame(rows: list[dict], texts: dict[str, str],
                max_years: int = MAX_YEARS) -> tuple[list[dict], Counter]:
    """Eligible rows, each tagged with its stratum, and why the others were dropped."""
    eligible: list[dict] = []
    dropped: Counter = Counter()
    for r in rows:
        key = r.get("asset_key", "")
        if (str(r.get("annotation_status", "")).strip().lower() != "done"
                or r.get("gold_is_event") != "yes"):
            dropped["no_event_in_prior_annotation"] += 1
            continue
        text = texts.get(key, "")
        if not text.strip():
            dropped["no_window_text"] += 1
            continue
        if guess_language(text) != "en":
            dropped["not_english"] += 1
            continue
        if len(_years(_split(r.get("gold_dates")))) > max_years:
            dropped["over_year_cap"] += 1
            continue
        eligible.append({**r, "stratum": proxy_stratum(r), "window_chars": str(len(text))})
    return eligible, dropped


def allocate(pools: dict[str, int], allocation=ALLOCATION,
             shortfall_to: str = SHORTFALL_TO) -> tuple[dict[str, int], list[str]]:
    """The pre-registered allocation, with any shortfall moved to `shortfall_to`."""
    planned = dict(allocation)
    actual = dict(planned)
    notes: list[str] = []
    short = 0
    for stratum, n in planned.items():
        have = pools.get(stratum, 0)
        if have < n:
            actual[stratum] = have
            short += n - have
            notes.append(f"{stratum}: {have} eligible for {n} planned; "
                         f"{n - have} moved to {shortfall_to}")
    actual[shortfall_to] += short
    if actual[shortfall_to] > pools.get(shortfall_to, 0):
        raise SamplingError(
            f"Not enough eligible windows: {shortfall_to} needs {actual[shortfall_to]}, "
            f"has {pools.get(shortfall_to, 0)}")
    return actual, notes


def draw(eligible: list[dict], allocation: dict[str, int], seed: int) -> list[dict]:
    rng = random.Random(seed)
    picked: list[dict] = []
    for stratum, n in allocation.items():
        pool = sorted((r for r in eligible if r["stratum"] == stratum),
                      key=lambda r: r["asset_key"])
        picked.extend(rng.sample(pool, n))
    rng.shuffle(picked)
    out = []
    for rank, r in enumerate(picked, start=1):
        out.append({
            "asset_key": r["asset_key"],
            "review_rank": str(rank),
            "stratum": r["stratum"],
            "sample_arm": r.get("sample_arm", ""),
            "title": r.get("title", ""),
            "content_url": r.get("content_url", ""),
            "window_chars": r["window_chars"],
            # Counts only, not values: the queue must not leak the earlier
            # annotation's content into the blind pass.
            "prior_hazard_keys": str(len({hazard_key(h) for h in _split(r.get("gold_hazards"))})),
            "prior_years": str(len(_years(_split(r.get("gold_dates"))))),
            "seed_event_count": r.get("seed_event_count", ""),
            "in_queue": "Y",
        })
    return out


def summarise(frame_rows: int, dropped: Counter, eligible: list[dict], queue: list[dict],
              allocation: dict[str, int], notes: list[str], seed: int, max_years: int) -> dict:
    pools = Counter(r["stratum"] for r in eligible)
    by_stratum: dict[str, dict] = {}
    for stratum, n in allocation.items():
        rows = [r for r in queue if r["stratum"] == stratum]
        seeds = [int(r["seed_event_count"] or 0) for r in rows]
        by_stratum[stratum] = {
            "eligible": pools.get(stratum, 0),
            "drawn": len(rows),
            "sampling_fraction": round(len(rows) / pools[stratum], 4) if pools.get(stratum) else None,
            "arms": dict(Counter(r["sample_arm"] for r in rows)),
            # Reported to describe the draw; never used to make it.
            "seed_event_count_mean": round(sum(seeds) / len(seeds), 2) if seeds else None,
            "seed_event_count_ge2": sum(1 for s in seeds if s >= 2),
        }
    return {
        "sampling": "stratified_by_prior_human_annotation",
        "framing": "targeted stress test; not weighted to the corpus",
        "params": {"seed": seed, "max_years": max_years,
                   "allocation_planned": dict(ALLOCATION), "allocation_actual": allocation,
                   "shortfall_to": SHORTFALL_TO},
        "frame": {"rows": frame_rows, "dropped": dict(dropped), "eligible": len(eligible)},
        "shortfall_notes": notes,
        "strata": by_stratum,
    }


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frame", type=Path, default=DEFAULT_FRAME)
    p.add_argument("--documents", type=Path, nargs="+", default=list(DEFAULT_STORES))
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--max-years", type=int, default=MAX_YEARS)
    p.add_argument("--force", action="store_true", help="overwrite an existing queue")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    if args.out.exists() and not args.force:
        LOG.error("%s already exists. Re-run with --force to redraw "
                  "(annotations keyed to the old draw would be orphaned).", args.out)
        return 1
    if not args.frame.exists():
        LOG.error("Frame not found: %s", args.frame)
        return 2

    _, rows = read_csv(args.frame)
    texts: dict[str, str] = {}
    for path in args.documents:
        documents, _ = load_document_store(path)
        texts.update({k: v.get("text", "") for k, v in documents.items()})

    eligible, dropped = build_frame(rows, texts, args.max_years)
    try:
        allocation, notes = allocate(Counter(r["stratum"] for r in eligible))
    except SamplingError as exc:
        LOG.error("%s", exc)
        return 2
    queue = draw(eligible, allocation, args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(args.out, QUEUE_COLUMNS, queue)
    summary = summarise(len(rows), dropped, eligible, queue, allocation, notes,
                        args.seed, args.max_years)
    summary_path = args.out.with_name(args.out.stem + "_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    LOG.info("Frame %d rows, %d eligible; dropped %s", len(rows), len(eligible), dict(dropped))
    for stratum, info in summary["strata"].items():
        LOG.info("  %-24s %2d drawn of %3d eligible", stratum, info["drawn"], info["eligible"])
    for note in notes:
        LOG.warning("  shortfall: %s", note)
    LOG.info("Wrote %s (seed=%d) and %s", args.out, args.seed, summary_path)
    LOG.info("Annotate it with:  make event-annotate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
