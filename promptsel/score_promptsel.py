"""Score Experiment D -> promptsel/PROMPTSEL_SCORES.md, promptsel_scores.json, promptsel_pairs.csv,
promptsel_geocode_pairs.csv.

    python -m promptsel.score_promptsel                   # refuses unless all 10 runs exist
    python -m promptsel.score_promptsel --allow-partial   # preview on what has run

Experiment B's scorer does the extraction side unchanged: `score_run` gives
each window Experiment A's counts (`score_window`) plus Experiment B's extra
counts — false alarms, traceability, snippet grades, hazard normalisation,
schema compliance — under the readings R2 (evidence-blind, primary) and R1.
What this module adds:

  geocoding   every record's places, resolved once per distinct place by the
              production geocoder (`promptsel.geocode`, `resolutions.csv`),
              scored with production's confidence. A pair is "in band" when
              0.70 <= confidence <= 0.98, the June comparison's rule.
  bridge      the June yield statistic — in-band event-locations per window —
              split by whether the record they belong to links to a gold event
              under the reading: valid + invalid = in band, and yield
              precision = valid / in band.
  contrasts   Δ = pk − p5 for k = 1..4, each configuration's two replicates
              pooled, on Experiment B's paired bootstrap (`shared_weights`).
  verdicts    the pre-registered reading rules of PROMPTSEL_PROTOCOL.md §10,
              applied in code (`tradeoff_cell`, `selection_verdict`,
              `bridging_verdict`).
  June        the June criterion recomputed on these windows, descriptively.

Three self-checks run before anything is reported: Experiment A's published
counts are reproduced (as in Experiment B); `explode_rows` equals production's
explosion on every run; and the Azure production run's geocoding on these
windows is reproduced row for row from `resolutions.csv`.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import logging
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ablation.normalise_hazards import LEXICON_SHA256  # noqa: E402
from ablation.runner import REPLICATES, SPEC, WINDOWS, run_dir  # noqa: E402
from ablation.score_ablation import (  # noqa: E402
    _DROPS, ALL_COUNTERS, ALL_METRICS, AZURE, READINGS, SEPTEMBER, Scored, ScoringError,
    WindowCache, _ci, _ci_pct, _jsonable, _matrix, _num, _pct, _pp, check_expA_reproduction,
    groups_for, load_ablation_gold, score_run, shared_weights, write_pairs,
)
from eval.event_matching import FIELDS  # noqa: E402
from eval.score_event_level import GoldSet, _div  # noqa: E402
from fonte.run_polygon_resolution import event_uuid  # noqa: E402
from promptsel.configs import BASELINE, CONFIGS, JUNE_LABELS, build_config, manifest  # noqa: E402
from promptsel.geocode import (  # noqa: E402
    BAND, GEO_COUNTERS, RESOLUTIONS, check_explosion, explode_rows, geo_window_counts,
    load_resolutions, pair_confidence, pair_key, statuses_from_rows,
)
from promptsel.runner import PROTOCOL, RUNS  # noqa: E402

LOG = logging.getLogger("promptsel.score")

PROMPTSEL = REPO_ROOT / "promptsel"
DEFAULT_OUT = PROMPTSEL / "PROMPTSEL_SCORES.md"
DEFAULT_JSON = PROMPTSEL / "promptsel_scores.json"
DEFAULT_PAIRS = PROMPTSEL / "promptsel_pairs.csv"
DEFAULT_GEO_PAIRS = PROMPTSEL / "promptsel_geocode_pairs.csv"
ABLATION_RUNS = REPO_ROOT / "ablation" / "runs"
PRODUCTION_GEOMETRIES = REPO_ROOT / "outputs" / "event_extractions" / "event_geometries.parquet"
JUNE_SUMMARY = (REPO_ROOT / "outputs"
                / "test_400_gpt5_medium_prompt05_vs_prompt01_04_resolution_confidence_070_098")
EXP_B_FULL = "Exp B full"
PREDECESSORS = tuple(c for c in CONFIGS if c != BASELINE)
PRIMARY = ("det_f1", "pooled_f1")
EQUIVALENCE_MARGIN = 0.05

COUNTERS_D = ALL_COUNTERS + GEO_COUNTERS
IDX_D = {name: i for i, name in enumerate(COUNTERS_D)}

GEO_METRICS = {
    "geo_pairs_per_window": lambda s: _div(s["geo_pairs"], s["win"]),
    "geo_resolved_rate": lambda s: _div(s["geo_resolved"], s["geo_pairs"]),
    "geo_inband_rate": lambda s: _div(s["geo_inband"], s["geo_pairs"]),
    "geo_mean_conf": lambda s: _div(s["geo_conf_sum"], s["geo_resolved"]),
    "geo_inband_mean_conf": lambda s: _div(s["geo_inband_conf_sum"], s["geo_inband"]),
    "geo_records_geocoded": lambda s: _div(s["geo_rec"], s["records"]),
    # The bridge: the June yield statistic, and its valid and invalid parts.
    "geo_inband_per_window": lambda s: _div(s["geo_inband"], s["win"]),
    "geo_valid_inband_per_window": lambda s: _div(s["geo_inband_valid"], s["win"]),
    "geo_invalid_inband_per_window": lambda s: _div(s["geo_inband"] - s["geo_inband_valid"],
                                                    s["win"]),
    "geo_yield_precision": lambda s: _div(s["geo_inband_valid"], s["geo_inband"]),
    "geo_rec_yield_precision": lambda s: _div(s["geo_rec_inband_valid"], s["geo_rec_inband"]),
    "geo_win_inband_share": lambda s: _div(s["geo_win_inband"], s["win"]),
    # S5: band without its upper bound, and any resolved place.
    "geo_wide_per_window": lambda s: _div(s["geo_wide"], s["win"]),
    "geo_wide_yield_precision": lambda s: _div(s["geo_wide_valid"], s["geo_wide"]),
    "geo_resolved_per_window": lambda s: _div(s["geo_resolved"], s["win"]),
    "geo_resolved_yield_precision": lambda s: _div(s["geo_resolved_valid"], s["geo_resolved"]),
    # S6: "valid" as a complete record, or as correct places.
    "geo_complete_inband_per_window": lambda s: _div(s["geo_inband_complete"], s["win"]),
    "geo_locok_inband_per_window": lambda s: _div(s["geo_inband_locok"], s["win"]),
    "geo_yield_precision_complete": lambda s: _div(s["geo_inband_complete"], s["geo_inband"]),
    "geo_yield_precision_locok": lambda s: _div(s["geo_inband_locok"], s["geo_inband"]),
    "geo_overshoot_share": lambda s: _div(s["geo_overshoot"], s["geo_resolved"]),
    "geo_country_fallback_share": lambda s: _div(s["geo_country_fallback"], s["geo_resolved"]),
}
METRICS_D = {**ALL_METRICS, **GEO_METRICS}


# ---------------------------------------------------------------------------
# Paired bootstrap over the combined counter vector
# ---------------------------------------------------------------------------

def named_with(vec, idx: dict[str, int]) -> dict:
    return {name: vec[..., i] for name, i in idx.items()}


def estimate_with(m: np.ndarray, w: np.ndarray, idx: dict[str, int] = IDX_D,
                  metrics: dict = METRICS_D) -> dict:
    """`ablation.score_ablation.estimate` over any counter layout."""
    totals, boot = named_with(m.sum(axis=0), idx), named_with(w @ m, idx)
    out = {}
    for name, fn in metrics.items():
        lo, hi = _ci(np.asarray(fn(boot), dtype=float))
        out[name] = {"point": float(fn(totals)), "lo": lo, "hi": hi}
    out["counts"] = {c: int(totals[c]) if float(totals[c]).is_integer() else float(totals[c])
                     for c in idx}
    return out


def delta_with(a: np.ndarray, b: np.ndarray, w: np.ndarray, idx: dict[str, int] = IDX_D,
               metrics: dict = METRICS_D) -> dict:
    """`ablation.score_ablation.delta` over any counter layout."""
    ta, tb = named_with(a.sum(axis=0), idx), named_with(b.sum(axis=0), idx)
    ba, bb = named_with(w @ a, idx), named_with(w @ b, idx)
    out = {}
    for name, fn in metrics.items():
        lo, hi = _ci(np.asarray(fn(ba), dtype=float) - np.asarray(fn(bb), dtype=float))
        out[name] = {"point": float(fn(ta) - fn(tb)), "lo": lo, "hi": hi}
    return out


# ---------------------------------------------------------------------------
# Reading rules (protocol §10). Δ is always pk − p5.
# ---------------------------------------------------------------------------

def direction(d: dict | None) -> int:
    """+1 resolved in pk's favour, -1 resolved in p5's favour, 0 not resolved."""
    if not d or d["lo"] != d["lo"]:
        return 0
    return 1 if d["lo"] > 0 else -1 if d["hi"] < 0 else 0


# (precision, recall), each from p5's side: +1 p5 better, 0 not resolved, -1 pk better.
CELLS = {
    (1, 1): "p5 dominates",
    (1, 0): "p5 more precise, no detectable recall cost",
    (1, -1): "trade-off: p5 trades recall for precision",
    (0, 1): "p5 higher recall, no detectable precision cost",
    (0, 0): "not distinguishable",
    (0, -1): "pk higher recall, no detectable precision cost",
    (-1, 1): "trade-off: p5 trades precision for recall",
    (-1, 0): "pk more precise, no detectable recall cost",
    (-1, -1): "pk dominates p5",
}
CONTRADICTING_CELLS = {(0, -1), (-1, 0), (-1, -1)}


def tradeoff_cell(d_precision: dict | None, d_recall: dict | None) -> tuple[tuple[int, int], str]:
    key = (-direction(d_precision), -direction(d_recall))
    return key, CELLS[key]


def equivalent(d: dict | None, margin: float = EQUIVALENCE_MARGIN) -> bool:
    return bool(d) and d["lo"] == d["lo"] and -margin < d["lo"] and d["hi"] < margin


def selection_verdict(contrasts: dict[str, dict]) -> dict:
    """contrasts: pk -> metric -> Δ (R2, all windows). Returns the verdict and its reasons."""
    reasons, per = [], {}
    contradicted = False
    supported = True
    for pk, c in contrasts.items():
        key, cell = tradeoff_cell(c.get("det_p"), c.get("det_r"))
        better_p5 = [m for m in PRIMARY if direction(c.get(m)) == -1]
        better_pk = [m for m in PRIMARY if direction(c.get(m)) == 1]
        per[pk] = {"cell": cell, "p5_better_on": better_p5, "pk_better_on": better_pk,
                   "equivalent_on": [m for m in PRIMARY if equivalent(c.get(m))]}
        if better_pk:
            contradicted = True
            reasons.append(f"{pk} is resolved-better than p5 on {', '.join(better_pk)}")
        if key in CONTRADICTING_CELLS:
            contradicted = True
            reasons.append(f"{pk}: {cell}")
        if not better_p5:
            supported = False
    verdict = ("contradicted" if contradicted else "supported" if supported and contrasts
               else "not contradicted")
    return {"verdict": verdict, "reasons": reasons, "per_predecessor": per}


def bridging_verdict(c: dict) -> dict:
    """One predecessor against p5 on the yield bridge (R2, all windows)."""
    y = direction(c.get("geo_inband_per_window"))
    v = direction(c.get("geo_valid_inband_per_window"))
    p = direction(c.get("geo_yield_precision"))
    if y != 0:
        higher = "pk" if y > 0 else "p5"
        if v != y or p == -y:
            return {"verdict": "more extracted ≠ more valid", "higher_yield": higher,
                    "detail": f"{higher} has resolved-higher in-band yield, but "
                              + ("its valid in-band yield is not resolved-higher"
                                 if v != y else "its yield precision is resolved-lower")}
        if p == 0:
            return {"verdict": "yield tracked validity", "higher_yield": higher,
                    "detail": f"{higher} has resolved-higher in-band and valid in-band yield; "
                              "yield precision not resolved"}
        return {"verdict": "yield tracked validity, precision also higher", "higher_yield": higher,
                "detail": f"{higher} is resolved-higher on in-band yield, valid yield and "
                          "yield precision"}
    return {"verdict": "in-band yield not distinguishable", "higher_yield": None,
            "detail": "in-band yield difference not resolved"}


# ---------------------------------------------------------------------------
# Scoring runs, with geocoding
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class RunD:
    label: str
    path: Path
    scored: Scored
    pairs: dict[str, list[dict]]                     # asset_key -> exploded rows
    geo: dict[str, dict[str, np.ndarray]]            # reading -> key -> combined vector
    audit: list[dict]


def score_run_d(label: str, path: Path, gold: GoldSet, cache: WindowCache,
                resolutions: dict, *, raw_dir: Path | None = None) -> RunD:
    scored = score_run(label, path, gold, cache, raw_dir=raw_dir)
    exploded = explode_rows(path)
    check_explosion(path, exploded)
    pairs: dict[str, list[dict]] = defaultdict(list)
    for r in exploded:
        if r["asset_key"] in gold.windows:
            pairs[r["asset_key"]].append(r)
    rows_by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in scored.rows:
        rows_by[(r["reading"], r["asset_key"])].append(r)

    combined: dict[str, dict[str, np.ndarray]] = {}
    audit = []
    for reading, per_window in scored.per_window.items():
        combined[reading] = {}
        for key, vec in per_window.items():
            statuses = statuses_from_rows(rows_by[(reading, key)])
            counts, rows = geo_window_counts(pairs.get(key, []), statuses, resolutions)
            combined[reading][key] = np.concatenate(
                [vec, np.array([counts[c] for c in GEO_COUNTERS], dtype=float)])
            audit += [{"system": label, "reading": reading, **r} for r in rows]
    return RunD(label, path, scored, dict(pairs), combined, audit)


def check_geocoding_reproduction(azure: RunD, resolutions: dict,
                                 parquet: Path = PRODUCTION_GEOMETRIES) -> list[str]:
    """The Azure run's resolved (uuid, confidence) on these windows, against its parquet."""
    if not parquet.exists():
        return [f"{parquet.relative_to(REPO_ROOT)} is missing"]
    keys = sorted(azure.pairs)
    stored = pd.read_parquet(parquet, columns=["uuid", "asset_key", "resolution_confidence"],
                             filters=[("asset_key", "in", keys)])
    want = Counter((u, round(float(c), 9)) for u, c in
                   zip(stored["uuid"], stored["resolution_confidence"]))
    got: Counter = Counter()
    for rows in azure.pairs.values():
        for p in rows:
            res = resolutions[pair_key(p)]
            if res["resolved"] not in (1, "1"):
                continue
            conf, _ = pair_confidence(res, p["hazard"], p["extractor_admin_level"])
            got[(event_uuid(p["asset_key"], p["location_text"], p["start_date"], p["end_date"]),
                 round(conf, 9))] += 1
    if got == want:
        return []
    return [f"{sum((got - want).values())} recomputed row(s) not in production, "
            f"{sum((want - got).values())} production row(s) not recomputed"]


# ---------------------------------------------------------------------------
# The June criterion, recomputed on these windows (descriptive)
# ---------------------------------------------------------------------------

def _june_keyer():
    path = REPO_ROOT / "scripts" / "compare_resolution_filtered_runs.py"
    spec = importlib.util.spec_from_file_location("compare_resolution_filtered_runs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.add_event_keys


def june_criterion(runs: dict[tuple[str, int], RunD]) -> dict:
    """Per replicate: in-band rows, windows, mean confidence; p1-p4 union vs p5; valid shares."""
    add_event_keys = _june_keyer()
    out = {}
    for rep in range(1, REPLICATES + 1):
        tables, rows_per = {}, {}
        for config in CONFIGS:
            run = runs.get((config, rep))
            if run is None:
                continue
            inband = [a for a in run.audit if a["reading"] == "R2" and a["in_band"]]
            df = pd.DataFrame(inband, columns=["asset_key", "hazard", "location_text",
                                               "start_date", "end_date", "confidence", "valid"])
            df = add_event_keys(df) if len(df) else df.assign(event_location_key=[])
            tables[config] = df
            rows_per[config] = {
                "inband_rows": len(df), "windows": int(df["asset_key"].nunique()) if len(df) else 0,
                "mean_confidence": float(df["confidence"].mean()) if len(df) else float("nan"),
                "valid_share": float(df["valid"].mean()) if len(df) else float("nan"),
            }
        if BASELINE not in tables or not all(c in tables for c in PREDECESSORS):
            continue
        union = pd.concat([tables[c] for c in PREDECESSORS], ignore_index=True)

        def valid_keys(df):
            return set(df.loc[df["valid"] == 1, "event_location_key"])

        u_keys, p_keys = set(union["event_location_key"]), set(tables[BASELINE]["event_location_key"])
        u_valid, p_valid = valid_keys(union), valid_keys(tables[BASELINE])
        both = u_keys & p_keys
        out[f"r{rep}"] = {
            "per_config": rows_per,
            "union": {"keys": len(u_keys), "windows": int(union["asset_key"].nunique()),
                      "valid_share": _share(u_valid, u_keys)},
            "p5": {"keys": len(p_keys), "valid_share": _share(p_valid, p_keys)},
            "both": len(both), "p5_only": len(p_keys - u_keys), "union_only": len(u_keys - p_keys),
            "jaccard": len(both) / len(u_keys | p_keys) if (u_keys | p_keys) else float("nan"),
            "p5_only_valid_share": _share(p_valid, p_keys - u_keys),
            "union_only_valid_share": _share(u_valid, u_keys - p_keys),
        }
    return out


def _share(valid: set, keys: set) -> float:
    return len(valid & keys) / len(keys) if keys else float("nan")


def june_reference() -> dict:
    """The June files, quoted as they are."""
    out = {}
    for name in ("selection_summary.csv", "retrieval_overlap_summary.csv"):
        path = JUNE_SUMMARY / name
        if path.exists():
            out[name] = pd.read_csv(path).to_dict(orient="records")
    return out


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def run_path(config: str, rep: int, root: Path = RUNS) -> Path:
    return run_dir(root, config, rep) / "event_extractions.jsonl"


def evaluate(gold: GoldSet, cache: WindowCache, resolutions: dict, *, root: Path = RUNS,
             allow_partial: bool = False, configs=CONFIGS, baseline: str = BASELINE,
             reps: int = REPLICATES) -> dict:
    runs: dict[tuple[str, int], RunD] = {}
    for config in configs:
        for rep in range(1, reps + 1):
            path = run_path(config, rep, root)
            if not path.exists():
                if not allow_partial:
                    raise ScoringError(f"Missing run: {path} (pass --allow-partial to preview)")
                continue
            runs[(config, rep)] = score_run_d(f"{config} r{rep}", path, gold, cache, resolutions,
                                              raw_dir=path.parent / "raw")
    full_b = {}
    for rep in range(1, reps + 1):
        path = run_path("full", rep, ABLATION_RUNS)
        if path.exists():
            full_b[rep] = score_run_d(f"{EXP_B_FULL} r{rep}", path, gold, cache, resolutions,
                                      raw_dir=path.parent / "raw")
    references = {label: score_run_d(label, path, gold, cache, resolutions)
                  for label, path, _ in (SEPTEMBER, AZURE) if path.exists()}

    common = [k for k in gold.keys if all(k in r.scored.returned for r in runs.values())]
    dropped = [k for k in gold.keys if k not in common]
    groups = groups_for(gold)
    weights: dict[str, tuple[list[str], np.ndarray]] = {}
    for name, (keys, stratify) in groups.items():
        keys = [k for k in keys if k in common]
        if len(keys) >= 2:
            strata = [gold.windows[k]["group"] for k in keys] if stratify else None
            weights[name] = (keys, shared_weights(keys, strata, name))

    def pooled(source: dict, reading: str, keys: list[str], which=None) -> np.ndarray | None:
        mats = [_matrix(r.geo[reading], keys) for k, r in source.items()
                if which is None or k in which]
        return sum(mats) if mats else None

    def config_runs(config: str) -> dict:
        return {rep: r for (c, rep), r in runs.items() if c == config}

    results: dict = {}
    contrasts: dict = {}
    noise: dict = {}
    drift: dict = {}
    for config in configs:
        mine = config_runs(config)
        for reading in READINGS:
            for g, (keys, w) in weights.items():
                m = pooled(mine, reading, keys)
                if m is None:
                    continue
                results.setdefault(config, {}).setdefault(reading, {})[g] = estimate_with(m, w)
                base = pooled(config_runs(baseline), reading, keys)
                if config != baseline and base is not None:
                    contrasts.setdefault(config, {}).setdefault(reading, {})[g] = delta_with(
                        m, base, w)
                r1, r2 = pooled(mine, reading, keys, (1,)), pooled(mine, reading, keys, (2,))
                if r1 is not None and r2 is not None:
                    noise.setdefault(config, {}).setdefault(reading, {})[g] = delta_with(r2, r1, w)
    if full_b:
        for reading in READINGS:
            for g, (keys, w) in weights.items():
                fb = pooled(full_b, reading, keys)
                results.setdefault(EXP_B_FULL, {}).setdefault(reading, {})[g] = estimate_with(fb, w)
                p5 = pooled(config_runs(baseline), reading, keys)
                if p5 is not None:
                    drift.setdefault(reading, {})[g] = delta_with(p5, fb, w)

    reference_results: dict = {}
    for label, r in references.items():
        for reading in READINGS:
            for g in weights:
                keys = [k for k in groups[g][0] if k in r.scored.returned]
                if len(keys) < 2:
                    continue
                strata = [gold.windows[k]["group"] for k in keys] if groups[g][1] else None
                reference_results.setdefault(label, {}).setdefault(reading, {})[g] = estimate_with(
                    _matrix(r.geo[reading], keys), shared_weights(keys, strata, g))

    primary = {pk: contrasts.get(pk, {}).get("R2", {}).get("all", {}) for pk in configs
               if pk != baseline and pk in contrasts}
    verdicts = {
        "selection": selection_verdict(primary) if primary else None,
        "bridging": {pk: bridging_verdict(c) for pk, c in primary.items()},
        "selection_S4_R1": selection_verdict(
            {pk: contrasts[pk].get("R1", {}).get("all", {}) for pk in primary}) if primary else None,
    }

    all_runs = [*runs.values(), *full_b.values(), *references.values()]
    coverage = {r.label: {"returned": len(r.scored.returned), "errored": len(r.scored.errored),
                          "absent": len(r.scored.absent)} for r in all_runs}
    unmapped = {config: sum((r.scored.unmapped for r in config_runs(config).values()), Counter())
                for config in configs}
    run_stats = {}
    for (config, rep) in runs:
        stats_path = run_dir(root, config, rep) / "run_stats.json"
        if stats_path.exists():
            run_stats[f"{config} r{rep}"] = json.loads(stats_path.read_text(encoding="utf-8"))
    return {
        "results": results, "contrasts": contrasts, "noise": noise, "drift": drift,
        "references": reference_results, "verdicts": verdicts,
        "june": june_criterion(runs), "june_reference": june_reference(),
        "coverage": coverage, "groups": {g: len(k) for g, (k, _w) in weights.items()},
        "common_windows": len(common), "dropped_windows": dropped,
        "unmapped_hazards": {c: dict(u.most_common()) for c, u in unmapped.items()},
        "run_stats": run_stats,
        "runs_scored": [f"{c} r{r}" for c, r in runs],
        "rows": [r for run in all_runs for r in run.scored.rows],
        "geo_rows": [a for run in all_runs for a in run.audit],
        "_azure": references.get(AZURE[0]),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _git_state(path: Path = PROTOCOL) -> str:
    try:
        commit = subprocess.run(["git", "log", "-1", "--format=%h", "--", str(path)],
                                cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", str(path)],
                               cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"
    if not commit:
        return "**not committed**"
    return f"commit `{commit}`" + (" **with uncommitted edits**" if dirty else "")


def _f(e: dict, digits: int = 2) -> str:
    return _num(e, digits)


def _dnum(e: dict | None, digits: int = 2) -> str:
    if not e or e["point"] != e["point"]:
        return "—"
    mark = " ◆" if (e["lo"] > 0 or e["hi"] < 0) else ""
    return f"{e['point']:+.{digits}f} ({e['lo']:+.{digits}f} to {e['hi']:+.{digits}f}){mark}"


def render(ev: dict, gold: GoldSet, checks: dict) -> str:
    R, C, N = ev["results"], ev["contrasts"], ev["noise"]
    configs = [c for c in CONFIGS if c in R]
    names = {c: build_config(c).prompt.name for c in CONFIGS}
    L: list[str] = []
    add = L.append

    add("# Experiment D — retrospective accuracy assessment of the prompt-5 selection\n")
    add("> **This is not how prompt 5 was chosen.** On 2026-06-01 prompt 5 was selected on "
        "resolver-filtered yield (resolved event-locations at confidence 0.70–0.98, their mean "
        "confidence, and overlap with the union of prompts 1–4); no human-reference accuracy "
        "figure for it existed then (`PROMPTSEL_PROTOCOL.md` §1). This report scores the five "
        "prompts after the fact against Experiment A's blind gold on Experiment B's 80 windows. "
        "The windows were selected on prompt 5's production output, which favours p5: a deficit "
        "for p5 here is robust, an advantage is only consistent with the selection.\n")
    add(f"- Protocol: `promptsel/PROMPTSEL_PROTOCOL.md` at {_git_state()}.")
    add(f"- Windows: `ablation/windows.csv` sha256 "
        f"`{hashlib.sha256(WINDOWS.read_bytes()).hexdigest()[:16]}…` — "
        + ", ".join(f"{g} {n}" for g, n in ev["groups"].items()) + ".")
    add(f"- Gold: Experiment A `event_level_gold.csv` sha256 `{gold.sha256[:16]}…`, read in "
        "place; event-absent windows carry no gold events.")
    add(f"- Hazard normaliser `LEXICON_SHA256` `{LEXICON_SHA256[:16]}…`, applied to every run.")
    add(f"- Model `{SPEC.id}`, reasoning effort {SPEC.reasoning_effort}, structured output "
        f"{SPEC.structured_output}; {REPLICATES} replicates per prompt, pooled.")
    add("- Prompts: " + "; ".join(
        f"`{c}` {names[c]} (`{manifest(build_config(c))['system_sha16']}`)" for c in CONFIGS)
        + ". p1–p4 are the current multi-event texts, not the single-event texts of June.")
    for label, problems in checks.items():
        add(f"- {label}: " + ("**ok**." if not problems else "**FAILED** — " + "; ".join(problems)))
    add(f"- Runs scored: {', '.join(ev['runs_scored']) or 'none'}. Windows in every "
        f"contrast: {ev['common_windows']}"
        + (f"; dropped (a run errored): {', '.join(k[:12] for k in ev['dropped_windows'])}"
           if ev["dropped_windows"] else "") + ".")
    add("\n_Intervals: 95% percentile window-cluster bootstrap, 2,000 resamples, one weight "
        "matrix per group shared by every prompt (paired). Δ = pk − p5. ◆ = interval excludes 0. "
        "Uncorrected for multiple comparisons. Judge every Δ against the replicate noise in "
        "§12._\n")

    def table(metrics: list[tuple[str, str]], reading: str = "R2", group: str = "all",
              fmt=_ci_pct, dfmt=_pp, rows_for=None, title: str = "") -> None:
        if title:
            add(title)
        add("| Prompt | " + " | ".join(f"{h} | Δ {h}" for _m, h in metrics) + " |")
        add("|---|" + "---|---|" * len(metrics))
        for c in rows_for or configs:
            res = R.get(c, {}).get(reading, {}).get(group)
            if res is None:
                continue
            cells = []
            for m, _h in metrics:
                d = C.get(c, {}).get(reading, {}).get(group, {}).get(m)
                cells += [fmt(res[m]), dfmt(d) if d else "—"]
            add(f"| `{c}` | " + " | ".join(cells) + " |")
        add("")

    add("## 1. Coverage and cost\n")
    add("| Run | Returned | Errored | Absent | Events | Failed calls | Cost | Providers |")
    add("|---|---:|---:|---:|---:|---:|---:|---|")
    for label, cov in ev["coverage"].items():
        st = ev["run_stats"].get(label, {})
        add(f"| {label} | {cov['returned']} | {cov['errored']} | {cov['absent']} | "
            f"{st.get('events', '–')} | {st.get('failed_attempts', '–')} | "
            f"{('$%.2f' % st['cost_usd']) if 'cost_usd' in st else '–'} | "
            f"{', '.join(f'{k} {v}' for k, v in (st.get('providers') or {}).items()) or '–'} |")

    add("\n## 2. Primary outcomes (R2, all windows)\n")
    table([("det_f1", "Detection F1"), ("pooled_f1", "Pooled attribute F1")])
    table([("det_p", "Detection P"), ("det_r", "Detection R")])

    add("## 3. Reading rules (protocol §10)\n")
    sel = ev["verdicts"]["selection"]
    if sel:
        add(f"**Selection verdict: {sel['verdict']}.**"
            + (" " + "; ".join(sel["reasons"]) + "." if sel["reasons"] else "") + "\n")
        add("| Predecessor | Precision/recall cell | p5 resolved-better on | pk resolved-better on "
            "| Equivalent (±5 pp) on | Bridge |")
        add("|---|---|---|---|---|---|")
        for pk, v in sel["per_predecessor"].items():
            b = ev["verdicts"]["bridging"][pk]
            add(f"| `{pk}` | {v['cell']} | {', '.join(v['p5_better_on']) or '–'} | "
                f"{', '.join(v['pk_better_on']) or '–'} | {', '.join(v['equivalent_on']) or '–'} "
                f"| {b['verdict']}: {b['detail']} |")
        s4 = ev["verdicts"]["selection_S4_R1"]
        add(f"\nUnder R1 (S4) the selection verdict is **{s4['verdict']}**.\n")
    else:
        add("_No contrasts yet._\n")

    add("## 4. Event-level detail (R2, all windows)\n")
    table([("crc", "CRC"), ("crr", "CRR"), ("attr_f1", "Attribute F1")])
    table([("pooled_f1_hazard", "Pooled hazard"), ("pooled_f1_year", "Pooled year"),
           ("pooled_f1_location", "Pooled location")])

    add("## 5. By window group (R2)\n")
    for g in ("event_present", "single", "multi"):
        table([("det_p", "Detection P"), ("det_r", "Detection R"), ("pooled_f1", "Pooled F1")],
              group=g, title=f"**{g}**\n")

    add("## 6. Event-absent windows\n")
    add("Every record on an event-absent window is a false positive. `S3` sets aside records "
        "whose places and year (and any evidence) are literally in the window, as a bound on "
        "how much of the false-alarm rate could be gold error. The 30 random negatives were "
        "judged with p5's empty production output visible (favours p5); the 6 hard negatives "
        "are windows where production p5 emitted an event that was rejected (counts against "
        "p5).\n")
    for g in ("event_absent", "random_negative", "hard_negative"):
        table([("fa_rate", "False-alarm windows"), ("fa_rate_s3", "False-alarm S3")], group=g,
              title=f"**{g}**\n")
    table([("det_p_s3", "Detection P (S3)"), ("det_f1_s3", "Detection F1 (S3)")],
          title="Detection with the S3 bound, all windows:\n")

    add("## 7. Candidate yield\n")
    table([("records_per_window", "Records / window"),
           ("raw_events_per_window", "Raw events / window")], fmt=_f, dfmt=_dnum)
    add("| Prompt | Dropped by the post-filter | not verifiable | low confidence | missing field "
        "| duplicate | Exact-vocabulary hazard | ISO date |")
    add("|---|---|---|---|---|---|---|---|")
    for c in configs:
        res = R[c]["R2"]["all"]
        add(f"| `{c}` | {_pct(res['drop_any']['point'])} | "
            + " | ".join(_pct(res[d]["point"]) for d in _DROPS)
            + f" | {_pct(res['hz_exact_raw']['point'])} | {_pct(res['date_iso']['point'])} |")
    add("")

    add("## 8. Evidence support\n")
    add("Snippet grades are `citation_quality.classify` against the window; held-out grades are "
        "out of the denominator. p1–p4 allow paraphrased snippets (\"no long quotes\"), so "
        "snippet grades partly measure style. Attribute traceability — every place "
        "word-bounded in the window, and a year that appears in it — does not depend on "
        "snippets.\n")
    table([("snip_quotable", "Quotable snippets"), ("rec_quotable", "Records with a quotable "
           "snippet"), ("snip_unsupported", "Unsupported snippets")])
    table([("trace_loc", "Places literal"), ("trace_year", "Year literal"),
           ("trace_both", "Both")])

    add("## 9. Geocoding success\n")
    add("Each record's places, exploded and hinted as `fonte-polygons` does, resolved once per "
        "distinct place by the production geocoder, scored with production's confidence. "
        "Success is the resolver's, not a judged geometry.\n")
    table([("geo_pairs_per_window", "Places / window"),
           ("geo_records_geocoded", "Records with ≥1 place")], fmt=_f, dfmt=_dnum)
    table([("geo_resolved_rate", "Resolved"), ("geo_inband_rate", "In band 0.70–0.98")])
    table([("geo_mean_conf", "Mean confidence (resolved)"),
           ("geo_inband_mean_conf", "Mean confidence (in band)")], fmt=lambda e: _f(e, 3),
          dfmt=lambda d: _dnum(d, 3))

    add("## 10. Yield and validity (R2)\n")
    add("In-band event-locations per window is the statistic prompt 5 was selected on in "
        "June. Here each one is labelled by its record: **valid** if the record links to a "
        "gold event, **invalid** otherwise (an unmatched record, or any record on an "
        "event-absent window). Yield precision = valid / in band.\n")
    table([("geo_inband_per_window", "In band / window"),
           ("geo_valid_inband_per_window", "Valid in band / window"),
           ("geo_invalid_inband_per_window", "Invalid in band / window")], fmt=_f, dfmt=_dnum)
    table([("geo_yield_precision", "Yield precision"),
           ("geo_rec_yield_precision", "Record yield precision"),
           ("geo_win_inband_share", "Windows with ≥1 in band")])

    add("## 11. The June criterion, recomputed on these windows (descriptive)\n")
    add("June's rule (`scripts/compare_resolution_filtered_runs.py`): in-band rows per prompt, "
        "the p1–p4 union deduplicated on asset‖hazard‖location‖start‖end, and its exact-key "
        "overlap with p5. A key is valid if any record behind it links to a gold event (R2). "
        "June ran on 400 documents, single-event p1–p4 and Azure; these are 80 windows, "
        "multi-event p1–p4 and OpenRouter, so the two are not comparable figure for figure.\n")
    for rep, j in ev["june"].items():
        add(f"**Replicate {rep}**\n")
        add("| Prompt | In-band rows | Windows | Mean confidence | Valid share |")
        add("|---|---:|---:|---:|---|")
        for c, v in j["per_config"].items():
            add(f"| `{c}` ({JUNE_LABELS[c]}) | {v['inband_rows']} | {v['windows']} | "
                f"{v['mean_confidence']:.3f} | {_pct(v['valid_share'])} |")
        add(f"\nUnion p1–p4: {j['union']['keys']} keys over {j['union']['windows']} windows, "
            f"{_pct(j['union']['valid_share'])} valid; p5: {j['p5']['keys']} keys, "
            f"{_pct(j['p5']['valid_share'])} valid. Both {j['both']}, p5 only {j['p5_only']} "
            f"({_pct(j['p5_only_valid_share'])} valid), union only {j['union_only']} "
            f"({_pct(j['union_only_valid_share'])} valid); Jaccard {j['jaccard']:.3f}.\n")
    ref = ev["june_reference"]
    if ref:
        add("June, as recorded (`selection_summary.csv`, `retrieval_overlap_summary.csv`):\n")
        add("| June label | In-band rows | Documents | Mean confidence |")
        add("|---|---:|---:|---:|")
        for r in ref.get("selection_summary.csv", []):
            add(f"| {r['prompt_label']} | {r['selected_geometry_rows']} | "
                f"{r['selected_unique_assets']} | {r['avg_resolution_confidence']:.3f} |")
        for r in ref.get("retrieval_overlap_summary.csv", []):
            add(f"\nUnion {r['four_prompt_union_count']}, p5 {r['unified_count']}, both "
                f"{r['both']}, p5 only {r['unified_only']}, union only "
                f"{r['four_prompt_union_only']}; Jaccard {r['jaccard_overlap']:.3f}.")
        add("")

    add("## 12. Rankings, replicate noise and cross-session drift\n")
    add("| Rank by | " + " | ".join(str(i) for i in range(1, len(configs) + 1)) + " |")
    add("|---|" + "---|" * len(configs))
    for m, h in (("geo_inband_per_window", "In band / window (June's yield)"),
                 ("records_per_window", "Records / window"), ("det_f1", "Detection F1"),
                 ("pooled_f1", "Pooled attribute F1"), ("geo_yield_precision", "Yield precision")):
        order = sorted(configs, key=lambda c: -R[c]["R2"]["all"][m]["point"])
        add(f"| {h} | " + " | ".join(f"`{c}`" for c in order) + " |")
    add("\nRanks are point estimates; whether two adjacent prompts differ is in §2–§10.\n")
    add("Replicate 2 − replicate 1 (R2, all windows):\n")
    add("| Prompt | Detection F1 | Pooled F1 | In band / window |")
    add("|---|---|---|---|")
    for c in configs:
        n = N.get(c, {}).get("R2", {}).get("all")
        if n:
            add(f"| `{c}` | {_pp(n['det_f1'])} | {_pp(n['pooled_f1'])} | "
                f"{_dnum(n['geo_inband_per_window'])} |")
    d = ev["drift"].get("R2", {}).get("all")
    if d:
        add(f"\nCross-session drift, p5 (this run) − Experiment B `full` (2026-11-01), both "
            f"pooled over two replicates: detection F1 {_pp(d['det_f1'])}, pooled F1 "
            f"{_pp(d['pooled_f1'])}, in band / window {_dnum(d['geo_inband_per_window'])}. "
            "Descriptive; `full` is never a contrast baseline.\n")

    add("## 13. Sensitivity\n")
    for g, title in (("S1_no_dev_pool", "S1 — without the 2 dev-pool windows"),
                     ("S2_no_gold_validation", "S2 — without the 5 `gold_validation` windows")):
        table([("det_p", "Detection P"), ("det_r", "Detection R"), ("det_f1", "Detection F1"),
               ("pooled_f1", "Pooled F1")], group=g, title=f"**{title}** (R2)\n")
    table([("det_p", "Detection P"), ("det_r", "Detection R"), ("det_f1", "Detection F1"),
           ("crc", "CRC")], reading="R1",
          title="**S4 — R1, Experiment A's anchored matching** (all five emit evidence)\n")
    table([("geo_wide_per_window", "In [0.70, 1.0] / window"),
           ("geo_resolved_per_window", "Resolved / window")], fmt=_f, dfmt=_dnum,
          title="**S5 — other bands**\n")
    table([("geo_wide_yield_precision", "Yield precision [0.70, 1.0]"),
           ("geo_resolved_yield_precision", "Yield precision, any resolved")])
    table([("geo_complete_inband_per_window", "Complete-record in band / window"),
           ("geo_locok_inband_per_window", "Correct-place in band / window")], fmt=_f,
          dfmt=_dnum, title="**S6 — stricter \"valid\"**\n")
    table([("geo_yield_precision_complete", "Yield precision, complete record"),
           ("geo_yield_precision_locok", "Yield precision, correct places")])

    add("## 14. Hazard normalisation\n")
    add("| Prompt | Records relabelled | Records with an unmapped component | Top unmapped |")
    add("|---|---|---|---|")
    for c in configs:
        res = R[c]["R2"]["all"]
        top = ", ".join(f"{k} ({v})" for k, v in list(ev["unmapped_hazards"].get(c, {}).items())[:6])
        add(f"| `{c}` | {_pct(res['hz_changed']['point'])} | {_pct(res['hz_unmapped']['point'])} "
            f"| {top or '–'} |")
    add("")

    add("## 15. Reference rows (not contrasted)\n")
    add("Experiment B's `full` replicates (prompt 5, same harness, 2026-11-01), the September "
        "OpenRouter GPT-5 prompt-5 run and the Azure production run, on the same windows. The "
        "Azure run is the one the windows were selected on.\n")
    add("| Run | Reading | Detection P | Detection R | Detection F1 | Pooled F1 | In band / window "
        "| Yield precision |")
    add("|---|---|---|---|---|---|---|---|")
    rows = {EXP_B_FULL: R.get(EXP_B_FULL, {}), **ev["references"]}
    for label, by_reading in rows.items():
        for reading in READINGS:
            res = by_reading.get(reading, {}).get("all")
            if res:
                add(f"| {label} | {reading} | {_ci_pct(res['det_p'])} | {_ci_pct(res['det_r'])} | "
                    f"{_ci_pct(res['det_f1'])} | {_ci_pct(res['pooled_f1'])} | "
                    f"{_f(res['geo_inband_per_window'])} | {_ci_pct(res['geo_yield_precision'])} |")
    add("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--allow-partial", action="store_true",
                   help="score whatever runs exist; accept uncached (rehearsal) resolutions")
    p.add_argument("--accept-geo-drift", action="store_true",
                   help="report, rather than refuse on, a failed production geocoding check "
                        "(log it as a deviation)")
    p.add_argument("--runs-root", type=Path, default=RUNS)
    p.add_argument("--resolutions", type=Path, default=RESOLUTIONS)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    p.add_argument("--pairs-out", type=Path, default=DEFAULT_PAIRS)
    p.add_argument("--geo-pairs-out", type=Path, default=DEFAULT_GEO_PAIRS)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("eval.score_event_level").setLevel(logging.ERROR)   # quote warnings: Exp A's

    if not args.resolutions.exists():
        raise ScoringError(f"{args.resolutions} is missing; run make promptsel-geocode")
    resolutions = load_resolutions(args.resolutions)
    uncached = sum(r["fetched_from"] == "uncached" for r in resolutions.values())
    if uncached and not args.allow_partial:
        raise ScoringError(f"{uncached} resolution(s) are offline placeholders; "
                           "run make promptsel-geocode")

    gold, expa = load_ablation_gold()
    cache = WindowCache(gold.texts)
    checks = {"Experiment A reproduction (September and Azure runs on its 45 windows, R1, "
              "every counter)": check_expA_reproduction(expa, cache)}
    if checks[next(iter(checks))]:
        raise ScoringError("The re-implemented loop does not reproduce Experiment A")
    ev = evaluate(gold, cache, resolutions, root=args.runs_root, allow_partial=args.allow_partial)
    checks["`explode_rows` equals production's `explode_extractions` on every run"] = []
    azure = ev.pop("_azure")
    geo_check = (check_geocoding_reproduction(azure, resolutions) if azure
                 else ["Azure run missing"])
    checks["Production geocoding reproduced on these windows (Azure run, every resolved "
           "uuid and confidence)"] = geo_check
    if geo_check and not args.accept_geo_drift:
        raise ScoringError("Production geocoding not reproduced: " + "; ".join(geo_check))
    if uncached:
        checks["Resolutions"] = [f"REHEARSAL — {uncached} uncached pair(s) recorded unresolved"]

    args.out.write_text(render(ev, gold, checks), encoding="utf-8")
    write_pairs(args.pairs_out, ev.pop("rows"))
    write_pairs(args.geo_pairs_out, ev.pop("geo_rows"))
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "gold_sha256": gold.sha256, "lexicon_sha256": LEXICON_SHA256,
               "windows_sha256": hashlib.sha256(WINDOWS.read_bytes()).hexdigest(),
               "resolutions_sha256": hashlib.sha256(args.resolutions.read_bytes()).hexdigest(),
               "band": list(BAND), "fields": list(FIELDS), "checks": checks, **ev}
    args.json_out.write_text(json.dumps(_jsonable(payload), indent=1) + "\n", encoding="utf-8")
    for path in (args.out, args.json_out, args.pairs_out, args.geo_pairs_out):
        print(f"-> {path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
