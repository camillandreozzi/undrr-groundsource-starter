"""Cross-validated runs over Experiment A's windows, in the shared output schema.

    python -m benchmark_supervised.run --freeze              # record code + config, once
    python -m benchmark_supervised.run                       # leave-one-window-out (primary)
    python -m benchmark_supervised.run --kfold 5 --seed 48   # sensitivity: less training data
    python -m benchmark_supervised.run --resubstitution      # wiring check -> runs_smoke/

The only event-level labels that exist are the 45 blind gold windows, which are
also the test set. So every window is predicted by a model that never saw it:

  lowo     45 folds; each window is predicted by a model trained on the other
           44. Deterministic — no seed anywhere in the pipeline.
  kfold    5 folds over windows (seeded shuffle); each model trains on ~36.
           Shows how much the result leans on training-set size.

`--resubstitution` trains and predicts on all 45. It checks the plumbing only,
is written to `runs_smoke/`, and is never a result.

Output is the `fonte.app_event_focus.OUTPUT_HEADERS` schema
(`benchmark_ner.ner_extract.to_output_rows`), so `eval/score_event_level.py`
scores it unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_ner.ner_extract import to_output_rows  # noqa: E402
from benchmark_supervised import features, model, parse  # noqa: E402
from benchmark_supervised.features import Doc, gold_assignment  # noqa: E402
from benchmark_supervised.model import (  # noqa: E402
    Extractor, TrainingWindow, pool_examples, window_examples,
)
from eval.event_matching import _loc_match  # noqa: E402
from eval.human_annotation_app import read_csv  # noqa: E402
from eval.score_event_level import (  # noqa: E402
    DEFAULT_GOLD, DEFAULT_QUEUE, DEFAULT_STORES, DEFAULT_WINDOWS, load_gold,
)
from fonte.app_event_focus import save_csv, save_jsonl  # noqa: E402

LOG = logging.getLogger("benchmark_supervised.run")

HERE = REPO_ROOT / "benchmark_supervised"
RUNS = HERE / "runs"
SMOKE = HERE / "runs_smoke"
FROZEN = HERE / "FROZEN.json"
FROZEN_CODE = (
    "benchmark_supervised/parse.py", "benchmark_supervised/features.py",
    "benchmark_supervised/model.py", "benchmark_supervised/run.py",
    "benchmark_ner/hazard_lexicon.py", "benchmark_ner/ner_extract.py",
    "eval/event_matching.py",
)
LABEL = "Supervised extractor"


def code_hashes() -> dict[str, str]:
    return {p: hashlib.sha256((REPO_ROOT / p).read_bytes()).hexdigest() for p in FROZEN_CODE}


def config() -> dict:
    return {
        "classifier": "L2 logistic regression (sklearn lbfgs), DictVectorizer + MaxAbsScaler",
        "C": model.C, "threshold": model.THRESHOLD, "clustering": "average linkage, cut at 1 - threshold",
        "max_locations": model.MAX_LOCATIONS, "max_snippets": model.MAX_SNIPPETS,
        "bow_reach": features.BOW_REACH, "sent_cap": features.SENT_CAP, "dep_cap": features.DEP_CAP,
        "year_range": [features.YEAR_MIN, features.YEAR_MAX],
        "last_event_year": features.LAST_EVENT_YEAR, "snippet_max": features.SNIPPET_MAX,
        "ner_models": [parse.PRIMARY_MODEL, parse.SECONDARY_MODEL],
        "place_labels": sorted(features.PLACE_LABELS),
    }


def folds(keys: list[str], kfold: int | None, seed: int | None) -> list[list[str]]:
    if not kfold:
        return [[k] for k in keys]
    from sklearn.model_selection import KFold
    splitter = KFold(n_splits=kfold, shuffle=True, random_state=seed)
    return [[keys[i] for i in test] for _, test in splitter.split(keys)]


def ceilings(docs: dict[str, Doc], gold: dict) -> dict:
    """What the fixed candidates allow at best, over all windows. Reads gold
    only to count; nothing here reaches a model."""
    events = reach_events = years = reach_years = places = reach_places = 0
    for key, doc in docs.items():
        golds = gold.get(key, [])
        assigned = set(gold_assignment(doc, golds).values())
        year_values = {int(c.value) for c in doc.years}
        for g in golds:
            if not g.verifiable:
                continue
            events += 1
            reach_events += g.gold_event_id in assigned
            for y in {g.year_start, g.year_end} - {None}:
                years += 1
                reach_years += y in year_values
            for loc in g.locations:
                places += 1
                reach_places += any(_loc_match(c.value, loc) for c in doc.places)
    return {
        "verifiable_events": events, "events_with_a_trigger": reach_events,
        "gold_year_endpoints": years, "year_endpoints_among_candidates": reach_years,
        "gold_locations": places, "locations_among_candidates": reach_places,
    }


def window_meta() -> dict[str, dict]:
    _, rows = read_csv(DEFAULT_WINDOWS)
    return {r["asset_key"]: {"asset_key": r["asset_key"], "title": r.get("title"),
                             "content_url": r.get("content_url")} for r in rows}


def frozen_state() -> dict:
    if not FROZEN.exists():
        return {"frozen": False}
    frozen = json.loads(FROZEN.read_text())
    return {"frozen": True, "frozen_at": frozen.get("frozen_at"),
            "code_matches": frozen.get("code") == code_hashes(),
            "config_matches": frozen.get("config") == config()}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--kfold", type=int, default=None, help="k-fold over windows instead of LOWO")
    p.add_argument("--seed", type=int, default=None, help="fold shuffle seed (with --kfold)")
    p.add_argument("--resubstitution", action="store_true",
                   help="train and predict on all windows: a wiring check, never a result")
    p.add_argument("--freeze", action="store_true", help="write FROZEN.json and stop")
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    warnings.filterwarnings("ignore", category=FutureWarning)

    keys = parse.window_keys()
    gs = load_gold(DEFAULT_GOLD, DEFAULT_WINDOWS, DEFAULT_QUEUE, list(DEFAULT_STORES))
    parsed = parse.load_all(keys)

    if args.freeze:
        if FROZEN.exists() and not args.force:
            LOG.error("%s exists; pass --force to re-freeze.", FROZEN)
            return 1
        FROZEN.write_text(json.dumps({
            "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "code": code_hashes(), "config": config(),
            "ner_models": next(iter(parsed.values())).models,
            "gold_sha256": gs.sha256, "windows": len(keys),
            "runs": ["lowo (primary)", "kfold 5, seeds 48 49 50 (sensitivity)"],
        }, indent=2) + "\n")
        LOG.info("Wrote %s", FROZEN)
        return 0

    if args.resubstitution:
        name, label, out_root, splits = "resubstitution", f"{LABEL} (resubstitution)", SMOKE, [keys]
    elif args.kfold:
        if args.seed is None:
            LOG.error("--kfold needs --seed")
            return 1
        name = f"kfold{args.kfold}_seed{args.seed}"
        label, out_root = f"{LABEL} ({args.kfold}-fold, seed {args.seed})", RUNS
        splits = folds(keys, args.kfold, args.seed)
    else:
        name, label, out_root, splits = "lowo", f"{LABEL} (LOWO)", RUNS, folds(keys, None, None)

    state = frozen_state()
    if out_root is RUNS and not (state.get("code_matches") and state.get("config_matches")):
        LOG.error("Code or config differs from %s (or it is missing). Scored runs must "
                  "match the freeze; run --freeze first, or log the change.", FROZEN)
        return 1
    out_dir = out_root / name
    if (out_dir / "event_extractions.jsonl").exists() and not args.force:
        LOG.error("%s already has a run; pass --force to overwrite.", out_dir)
        return 1

    docs = {k: Doc(parsed[k]) for k in keys}
    meta = window_meta()
    started = time.time()
    examples = {k: window_examples(TrainingWindow(docs[k], gs.events.get(k, []))) for k in keys}
    rows, detail, fold_counts = [], [], []
    for n, test in enumerate(splits, 1):
        train_keys = keys if args.resubstitution else [k for k in keys if k not in test]
        extractor = Extractor.from_examples(pool_examples([examples[k] for k in train_keys]))
        fold_counts.append({"test": [k[:12] for k in test], "train_windows": len(train_keys),
                            "examples": extractor.counts})
        for key in test:
            events, trail = extractor.predict(docs[key])
            rows.extend(to_output_rows(meta[key], events))
            detail.append({"asset_key": key, "fold": n, "events": trail})
        LOG.info("fold %d/%d: trained on %d windows, predicted %d", n, len(splits),
                 len(train_keys), len(test))

    order = {k: i for i, k in enumerate(keys)}
    rows.sort(key=lambda r: (order[r["asset_key"]], r.get("event_index") or 0))
    out_dir.mkdir(parents=True, exist_ok=True)
    save_jsonl(rows, out_dir / "event_extractions.jsonl")
    save_csv(rows, out_dir / "event_extractions.csv")
    save_jsonl(detail, out_dir / "predictions_detail.jsonl")
    records = sum(1 for r in rows if r.get("is_verifiable_event"))
    stats = {
        "label": label, "scheme": name, "windows": len(keys), "folds": len(splits),
        "records": records, "rows": len(rows), "seconds": round(time.time() - started, 1),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gold_sha256": gs.sha256, "ner_models": next(iter(parsed.values())).models,
        "config": config(), "freeze": state,
        "candidate_ceilings": ceilings(docs, gs.events),
        "fold_training": fold_counts,
    }
    (out_dir / "run_stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    LOG.info("Wrote %s: %d records over %d windows (%.0fs)", out_dir, records, len(keys),
             stats["seconds"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
