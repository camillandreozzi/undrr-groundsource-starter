"""Score the ablation runs -> ablation/ABLATION_SCORES.md, ablation_scores.json, ablation_pairs.csv.

    python -m ablation.score_ablation                     # refuses unless all 10 runs exist
    python -m ablation.score_ablation --allow-partial     # preview on what has run
    python -m ablation.score_ablation --references-only   # September + Azure rows, no ablation runs

Experiment A's scorer, unchanged, does the work on each window: `score_window`
pairs records with gold events (`eval/event_matching.py`) and counts. What this
module adds is the ablation's own reading of those counts:

  hazards       every run's `event_hazard` goes through `normalise_hazard`
                first (identity on exact PreventionWeb labels), so `no_vocab`
                and `bare` are scored on the same label space as the gold.
  readings      R2, evidence-blind (primary): snippets are stripped before
                matching, so every configuration is linked by years and places
                alone (tier C). R1, anchored: Experiment A's rules as they are.
                `no_evidence` and `bare` emit no snippets, so for them R1 is R2;
                only R2 compares all five on one rule. Pooled document F1 does
                not use the matching at all and is the same under both.
  extra counts  false alarms on event-absent windows; literal traceability of
                each record's places and years; snippet grades from
                `citation_quality.classify`; hazard normalisation; and schema
                compliance from the raw pre-filter JSON.
  uncertainty   one bootstrap weight matrix per group (2,000 resamples, seed 42
                with the group's name; the overall group resampled within
                event-present and event-absent windows) shared by every
                configuration, reading and contrast, so differences are paired.
                A configuration's estimate pools its two replicates' counts;
                replicate 2 minus replicate 1 is the noise floor.

On every run it first re-scores the September OpenRouter and Azure runs on
Experiment A's own 45 windows and requires every counter to equal
`eval/event_level_scores.json` — the loop below is a re-implementation of
`score_system`, and this proves it. The rules are frozen in
`ablation/ABLATION_PROTOCOL.md`.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import logging
import re
import subprocess
import sys
import zlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import numpy as np  # noqa: E402

from ablation.configs import CONFIGS  # noqa: E402
from ablation.normalise_hazards import LEXICON_SHA256, VOCABULARY, normalise_hazard  # noqa: E402
from ablation.runner import REPLICATES, RUNS, SPEC, WINDOWS, read_windows, run_dir  # noqa: E402
from benchmark_openrouter.agreement import REFERENCE_RUNS  # noqa: E402
from benchmark_openrouter.citation_quality import GROUNDED, HELD_OUT, QUOTABLE, Document, classify  # noqa: E402
from eval.event_matching import FIELDS, PredEvent  # noqa: E402
from eval.human_annotation_app import load_document_store  # noqa: E402
from eval.score_against_human import Run, _fold, _split  # noqa: E402
from eval.score_event_level import (  # noqa: E402
    BOOTSTRAP_N, BOOTSTRAP_SEED, COUNTERS, DEFAULT_GOLD, DEFAULT_QUEUE, DEFAULT_STORES,
    DEFAULT_WINDOWS, METRICS, GoldSet, _div, _hmean, load_gold, score_window,
)
from fonte.app_event_focus import LOCATION_ADMIN_LEVELS  # noqa: E402

LOG = logging.getLogger("ablation.score")

ABLATION = REPO_ROOT / "ablation"
DEFAULT_OUT = ABLATION / "ABLATION_SCORES.md"
DEFAULT_JSON = ABLATION / "ablation_scores.json"
DEFAULT_PAIRS = ABLATION / "ablation_pairs.csv"
WINDOWS_SUMMARY = ABLATION / "windows_summary.json"
PROTOCOL = ABLATION / "ABLATION_PROTOCOL.md"
EXPA_SCORES = REPO_ROOT / "eval" / "event_level_scores.json"

BASELINE = "full"
READINGS = ("R2", "R1")
EVIDENCE_FREE = ("no_evidence", "bare")         # R1 is R2 for these
SEPTEMBER = ("GPT-5 Sept (OpenRouter)",
             REPO_ROOT / "benchmark_openrouter" / "outputs_pooled" / "openai-gpt-5"
             / "event_extractions.jsonl", "GPT-5 (OpenRouter)")
AZURE = (REFERENCE_RUNS[0][0] + " — production", REFERENCE_RUNS[0][1], REFERENCE_RUNS[0][0])
REFERENCES = (SEPTEMBER, AZURE)                 # (label, path, Experiment A label)
HARD = ("hard_negative", "expA_none")

EXTRA = (
    "win", "win_absent", "win_fa", "win_fa_strict", "rec_absent", "fp_absent_literal",
    "rec_trace_loc", "rec_trace_year", "rec_trace_both",
    "snip_n", "snip_judged", "snip_quotable", "snip_grounded", "snip_unsupported",
    "rec_with_snip", "rec_quotable",
    "rec_hz_changed", "rec_hz_unmapped", "rec_hz_exact_raw",
    "date_entries", "date_iso",
    "raw_win", "raw_events", "drop_unverifiable", "drop_confidence", "drop_missing",
    "drop_duplicate", "admin_mismatch", "admin_invalid",
)
ALL_COUNTERS = COUNTERS + EXTRA
_IDX = {name: i for i, name in enumerate(ALL_COUNTERS)}

_ISO = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")
_YEAR = re.compile(r"(?<!\d)(1[0-9]\d\d|20[0-9]\d)(?!\d)")
_VOCAB = {_fold(v) for v in VOCABULARY}
_ADMIN = set(LOCATION_ADMIN_LEVELS)
_DROPS = ("drop_unverifiable", "drop_confidence", "drop_missing", "drop_duplicate")


class ScoringError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Metrics on top of Experiment A's (scalars and bootstrap arrays alike)
# ---------------------------------------------------------------------------

def _named(vec) -> dict:
    return {name: vec[..., i] for name, i in _IDX.items()}


ABL_METRICS = {
    "records_per_window": lambda s: _div(s["records"], s["win"]),
    "fa_rate": lambda s: _div(s["win_fa"], s["win_absent"]),
    "rec_per_absent": lambda s: _div(s["rec_absent"], s["win_absent"]),
    # S3: records on event-absent windows whose places and year are literally in
    # the window are set aside as "unknown" rather than counted as false.
    "fa_rate_s3": lambda s: _div(s["win_fa_strict"], s["win_absent"]),
    "det_p_s3": lambda s: _div(s["records_matched"], s["records"] - s["fp_absent_literal"]),
    "det_f1_s3": lambda s: _hmean(_div(s["records_matched"], s["records"] - s["fp_absent_literal"]),
                                  _div(s["gold_req_matched"], s["gold_req"])),
    "trace_loc": lambda s: _div(s["rec_trace_loc"], s["records"]),
    "trace_year": lambda s: _div(s["rec_trace_year"], s["records"]),
    "trace_both": lambda s: _div(s["rec_trace_both"], s["records"]),
    "snip_per_record": lambda s: _div(s["snip_n"], s["records"]),
    "snip_quotable": lambda s: _div(s["snip_quotable"], s["snip_judged"]),
    "snip_grounded": lambda s: _div(s["snip_grounded"], s["snip_judged"]),
    "snip_unsupported": lambda s: _div(s["snip_unsupported"], s["snip_judged"]),
    "rec_quotable": lambda s: _div(s["rec_quotable"], s["records"]),
    "hz_changed": lambda s: _div(s["rec_hz_changed"], s["records"]),
    "hz_unmapped": lambda s: _div(s["rec_hz_unmapped"], s["records"]),
    "hz_exact_raw": lambda s: _div(s["rec_hz_exact_raw"], s["records"]),
    "date_iso": lambda s: _div(s["date_iso"], s["date_entries"]),
    "raw_events_per_window": lambda s: _div(s["raw_events"], s["raw_win"]),
    "drop_any": lambda s: _div(sum(s[d] for d in _DROPS), s["raw_events"]),
    **{d: (lambda d: lambda s: _div(s[d], s["raw_events"]))(d) for d in _DROPS},
    "admin_mismatch": lambda s: _div(s["admin_mismatch"], s["raw_events"]),
    "admin_invalid": lambda s: _div(s["admin_invalid"], s["raw_events"]),
}
ALL_METRICS = {**METRICS, **ABL_METRICS}


# ---------------------------------------------------------------------------
# Gold: Experiment A's, read in place, plus the empty-gold windows
# ---------------------------------------------------------------------------

def _texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    for path in DEFAULT_STORES:
        documents, _ = load_document_store(path)
        texts.update({k: v.get("text", "") for k, v in documents.items()})
    return texts


def load_ablation_gold(windows_path: Path = WINDOWS) -> tuple[GoldSet, GoldSet]:
    """(ablation gold over the frozen windows, Experiment A's own gold)."""
    expa = load_gold(DEFAULT_GOLD, DEFAULT_WINDOWS, DEFAULT_QUEUE, list(DEFAULT_STORES))
    frozen_sha = json.loads(WINDOWS_SUMMARY.read_text(encoding="utf-8"))["sources"][DEFAULT_GOLD.name]
    if expa.sha256 != frozen_sha:
        raise ScoringError("eval/event_level_gold.csv changed since the windows were frozen")
    texts = _texts()
    windows: dict[str, dict] = {}
    for w in read_windows(windows_path):
        key = w["asset_key"]
        if hashlib.sha256(texts.get(key, "").encode("utf-8")).hexdigest() != w["text_sha256"]:
            raise ScoringError(f"{key[:12]}: window text changed since freezing")
        windows[key] = {**expa.windows.get(key, {}), **w, "asset_key": key,
                        "review_rank": w["ablation_rank"], "stratum": w["subgroup"]}
    missing = sorted(set(expa.windows) - set(windows))
    if missing:
        raise ScoringError(f"Experiment A windows missing from the ablation set: {missing}")
    events = {k: v for k, v in expa.events.items() if k in windows}
    gold = GoldSet(windows, events, {k: texts[k] for k in windows}, len(windows), expa.sha256)
    return gold, expa


def groups_for(gold: GoldSet) -> dict[str, tuple[list[str], bool]]:
    """name -> (window keys, stratify the bootstrap by event presence)."""
    keys = gold.keys
    meta = gold.windows

    def pick(pred) -> list[str]:
        return [k for k in keys if pred(meta[k])]

    return {
        "all": (keys, True),
        "event_present": (pick(lambda m: m["group"] == "event_present"), False),
        "single": (pick(lambda m: m["subgroup"] == "single"), False),
        "multi": (pick(lambda m: m["subgroup"] == "multi"), False),
        "event_absent": (pick(lambda m: m["group"] == "event_absent"), False),
        "random_negative": (pick(lambda m: m["subgroup"] == "random_negative"), False),
        "hard_negative": (pick(lambda m: m["subgroup"] in HARD), False),
        "S1_no_dev_pool": (pick(lambda m: not m.get("dev_pool_400")), True),
        "S2_no_gold_validation": (pick(lambda m: not m.get("gold_validation")), True),
    }


# ---------------------------------------------------------------------------
# Per-window counts beyond Experiment A's
# ---------------------------------------------------------------------------

def _hay(text: str) -> str:
    """Folded, punctuation as spaces, padded: a word-bounded `in` test."""
    return " " + " ".join(re.sub(r"[^\w]+", " ", _fold(text)).split()) + " "


def location_traceable(location: str, hay: str) -> bool:
    """The place, word-bounded, or else every comma-separated part of it."""
    whole = _hay(location)
    if whole.strip() and whole in hay:
        return True
    parts = [_hay(p) for p in location.split(",") if _hay(p).strip()]
    return len(parts) > 1 and all(p in hay for p in parts)


def drop_reason(event: dict, seen: set) -> str | None:
    """Mirror of `DocumentEventExtractions._keep_verified_unique_events` on raw JSON."""
    if not event.get("is_verifiable_event"):
        return "drop_unverifiable"
    if event.get("event_confidence") not in {"high", "medium"}:
        return "drop_confidence"
    hazard = event.get("event_hazard")
    dates = event.get("event_dates") or []
    locations = event.get("affected_locations") or []
    if not hazard or not dates or not locations:
        return "drop_missing"
    key = (hazard.strip().lower(),
           tuple(s.strip().lower() for s in dates if s.strip()),
           tuple(s.strip().lower() for s in locations if s.strip()))
    if key in seen:
        return "drop_duplicate"
    seen.add(key)
    return None


@dataclass
class WindowCache:
    texts: dict[str, str]
    _hay: dict[str, str] = field(default_factory=dict)
    _doc: dict[str, Document] = field(default_factory=dict)

    def hay(self, key: str) -> str:
        if key not in self._hay:
            self._hay[key] = _hay(self.texts[key])
        return self._hay[key]

    def doc(self, key: str) -> Document:
        if key not in self._doc:
            self._doc[key] = Document.build(key, self.texts[key])
        return self._doc[key]


def extra_counts(key: str, raw_rows: list[dict], preds: list[PredEvent], absent: bool,
                 cache: WindowCache, raw_path: Path | None) -> tuple[dict, Counter]:
    c = dict.fromkeys(EXTRA, 0)
    unmapped: Counter = Counter()
    c["win"] = 1
    hay = cache.hay(key)
    window_years = set(_YEAR.findall(cache.texts[key]))
    strict_fp = False
    for row, p in zip(raw_rows, preds):
        norm = normalise_hazard(row.get("event_hazard"))
        c["rec_hz_changed"] += norm.changed
        c["rec_hz_unmapped"] += bool(norm.unmapped)
        unmapped.update(norm.unmapped)
        c["rec_hz_exact_raw"] += bool(norm.components) and all(
            _fold(h) in _VOCAB for h in _split(row.get("event_hazard")))
        for d in _split(row.get("event_dates")):
            c["date_entries"] += 1
            c["date_iso"] += bool(_ISO.match(d))

        loc_ok = bool(p.locations) and all(location_traceable(loc, hay) for loc in p.locations)
        year_ok = any(str(y) in window_years for y in p.years)
        c["rec_trace_loc"] += loc_ok
        c["rec_trace_year"] += year_ok
        c["rec_trace_both"] += loc_ok and year_ok

        grades = [classify(s, cache.doc(key)).grade for s in p.snippets]
        judged = [g for g in grades if g not in HELD_OUT]
        c["snip_n"] += len(grades)
        c["snip_judged"] += len(judged)
        c["snip_quotable"] += sum(g in QUOTABLE for g in judged)
        c["snip_grounded"] += sum(g in GROUNDED for g in judged)
        c["snip_unsupported"] += sum(g == "unsupported" for g in judged)
        c["rec_with_snip"] += bool(grades)
        quotable = any(g in QUOTABLE for g in judged)
        c["rec_quotable"] += quotable

        if absent:
            literal = loc_ok and year_ok and (not grades or quotable)
            c["fp_absent_literal"] += literal
            strict_fp |= not literal
    if absent:
        c["win_absent"] = 1
        c["rec_absent"] = len(preds)
        c["win_fa"] = int(bool(preds))
        c["win_fa_strict"] = int(strict_fp)

    if raw_path is not None and raw_path.exists():
        events = json.loads(raw_path.read_text(encoding="utf-8")).get("events") or []
        c["raw_win"] = 1
        c["raw_events"] = len(events)
        seen: set = set()
        kept = 0
        for e in events:
            reason = drop_reason(e, seen)
            if reason:
                c[reason] += 1
            else:
                kept += 1
            locs, levels = e.get("affected_locations") or [], e.get("location_admin_levels") or []
            c["admin_mismatch"] += len(locs) != len(levels)
            c["admin_invalid"] += any(lvl not in _ADMIN for lvl in levels)
        if kept != len(preds):
            raise ScoringError(f"{raw_path}: post-filter keeps {kept} events, "
                               f"the output has {len(preds)}")
    return c, unmapped


# ---------------------------------------------------------------------------
# Scoring one run
# ---------------------------------------------------------------------------

@dataclass
class Scored:
    label: str
    returned: list[str]
    errored: list[str]
    absent: list[str]
    per_window: dict[str, dict[str, np.ndarray]]   # reading -> key -> counts
    rows: list[dict]
    unmapped: Counter


def score_run(label: str, path: Path, gold: GoldSet, cache: WindowCache, *,
              raw_dir: Path | None = None, readings=READINGS) -> Scored:
    run = Run(label, path)
    returned, errored, absent = [], [], []
    for key in gold.keys:
        (absent if key not in run.docs else errored if key in run.errored else returned).append(key)
    per_window: dict[str, dict[str, np.ndarray]] = {r: {} for r in readings}
    rows: list[dict] = []
    unmapped: Counter = Counter()
    for key in returned:
        raw_rows = run.events.get(key, [])
        normalised = [{**r, "event_hazard": normalise_hazard(r.get("event_hazard")).value}
                      for r in raw_rows]
        preds = [PredEvent.from_row(r, i + 1) for i, r in enumerate(normalised)]
        is_absent = gold.windows[key].get("group") == "event_absent"
        extra, missed = extra_counts(key, raw_rows, preds, is_absent, cache,
                                     raw_dir / f"{key}.json" if raw_dir else None)
        unmapped.update(missed)
        meta = {"asset_key": key, **gold.windows[key]}
        for reading in readings:
            p = preds if reading == "R1" else [dataclasses.replace(x, snippets=()) for x in preds]
            counts, window_rows = score_window(p, gold.events.get(key, []), gold.texts[key],
                                               label, meta, gold.window_class(key))
            per_window[reading][key] = np.array(
                [counts.get(c, extra.get(c, 0)) for c in ALL_COUNTERS], dtype=float)
            rows.extend({**r, "reading": reading} for r in window_rows)
    return Scored(label, returned, errored, absent, per_window, rows, unmapped)


def check_expA_reproduction(expa: GoldSet, cache: WindowCache) -> list[str]:
    """Every counter of the reference runs on Experiment A's windows, R1, vs its scores file."""
    published = json.loads(EXPA_SCORES.read_text(encoding="utf-8"))["results"]
    problems = []
    for label, path, expa_label in REFERENCES:
        scored = score_run(label, path, expa, cache, readings=("R1",))
        totals = sum(scored.per_window["R1"].values())
        want = published[expa_label]["all"]["counts"]
        diff = {c: (int(totals[_IDX[c]]), want[c]) for c in COUNTERS
                if int(totals[_IDX[c]]) != want[c]}
        if diff:
            problems.append(f"{expa_label}: {diff}")
    return problems


# ---------------------------------------------------------------------------
# Paired bootstrap
# ---------------------------------------------------------------------------

def shared_weights(keys: list[str], strata: list[str] | None, group: str,
                   n_boot: int = BOOTSTRAP_N) -> np.ndarray:
    """(n_boot, n) resampling counts, the same for every system scored on `group`."""
    n = len(keys)
    rng = np.random.default_rng([BOOTSTRAP_SEED, zlib.crc32(group.encode())])
    if strata is None:
        idx = rng.integers(0, n, size=(n_boot, n))
    else:
        cols = []
        for s in sorted(set(strata)):
            pos = np.array([i for i, v in enumerate(strata) if v == s])
            cols.append(pos[rng.integers(0, len(pos), size=(n_boot, len(pos)))])
        idx = np.concatenate(cols, axis=1)
    weights = np.zeros((n_boot, n))
    np.add.at(weights, (np.arange(n_boot)[:, None], idx), 1)
    return weights


def _ci(values: np.ndarray) -> tuple[float, float]:
    values = values[~np.isnan(values)]
    if not values.size:
        return float("nan"), float("nan")
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def estimate(m: np.ndarray, w: np.ndarray) -> dict:
    totals, boot = _named(m.sum(axis=0)), _named(w @ m)
    out = {}
    for name, fn in ALL_METRICS.items():
        lo, hi = _ci(np.asarray(fn(boot), dtype=float))
        out[name] = {"point": float(fn(totals)), "lo": lo, "hi": hi}
    out["counts"] = {c: int(totals[c]) for c in ALL_COUNTERS}
    return out


def delta(a: np.ndarray, b: np.ndarray, w: np.ndarray) -> dict:
    ta, tb = _named(a.sum(axis=0)), _named(b.sum(axis=0))
    ba, bb = _named(w @ a), _named(w @ b)
    out = {}
    for name, fn in ALL_METRICS.items():
        lo, hi = _ci(np.asarray(fn(ba), dtype=float) - np.asarray(fn(bb), dtype=float))
        out[name] = {"point": float(fn(ta) - fn(tb)), "lo": lo, "hi": hi}
    return out


def _matrix(per_window: dict[str, np.ndarray], keys: list[str]) -> np.ndarray:
    return np.stack([per_window[k] for k in keys])


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def run_path(config: str, rep: int, root: Path = RUNS) -> Path:
    return run_dir(root, config, rep) / "event_extractions.jsonl"


def evaluate(gold: GoldSet, cache: WindowCache, *, root: Path = RUNS,
             allow_partial: bool = False, references_only: bool = False) -> dict:
    ablation: dict[tuple[str, int], Scored] = {}
    if not references_only:
        for config in CONFIGS:
            for rep in range(1, REPLICATES + 1):
                path = run_path(config, rep, root)
                if not path.exists():
                    if not allow_partial:
                        raise ScoringError(f"Missing run: {path.relative_to(REPO_ROOT)} "
                                           "(pass --allow-partial to preview)")
                    continue
                ablation[(config, rep)] = score_run(f"{config} r{rep}", path, gold, cache,
                                                    raw_dir=path.parent / "raw")
    references = {label: score_run(label, path, gold, cache)
                  for label, path, _ in REFERENCES if path.exists()}

    # Contrasts use only windows every ablation run returned.
    common = [k for k in gold.keys if all(k in s.returned for s in ablation.values())]
    dropped = [k for k in gold.keys if k not in common]
    groups = groups_for(gold)
    weights: dict[str, tuple[list[str], np.ndarray]] = {}
    for name, (keys, stratify) in groups.items():
        keys = [k for k in keys if k in common] if ablation else keys
        if len(keys) >= 2:
            strata = [gold.windows[k]["group"] for k in keys] if stratify else None
            weights[name] = (keys, shared_weights(keys, strata, name))

    def config_matrix(config: str, reading: str, keys: list[str], reps=None) -> np.ndarray | None:
        mats = [_matrix(ablation[(config, r)].per_window[reading], keys)
                for r in (reps or range(1, REPLICATES + 1)) if (config, r) in ablation]
        return sum(mats) if mats else None

    results: dict = {}
    contrasts: dict = {}
    noise: dict = {}
    for config in CONFIGS:
        for reading in READINGS:
            for g, (keys, w) in weights.items():
                m = config_matrix(config, reading, keys)
                if m is None:
                    continue
                results.setdefault(config, {}).setdefault(reading, {})[g] = estimate(m, w)
                base = config_matrix(BASELINE, reading, keys)
                if config != BASELINE and base is not None:
                    contrasts.setdefault(config, {}).setdefault(reading, {})[g] = delta(m, base, w)
                r1 = config_matrix(config, reading, keys, reps=(1,))
                r2 = config_matrix(config, reading, keys, reps=(2,))
                if r1 is not None and r2 is not None:
                    noise.setdefault(config, {}).setdefault(reading, {})[g] = delta(r2, r1, w)

    reference_results: dict = {}
    for label, s in references.items():
        for reading in READINGS:
            for g, (keys, _w) in weights.items():
                keys = [k for k in groups[g][0] if k in s.returned]
                if len(keys) < 2:
                    continue
                strata = [gold.windows[k]["group"] for k in keys] if groups[g][1] else None
                reference_results.setdefault(label, {}).setdefault(reading, {})[g] = estimate(
                    _matrix(s.per_window[reading], keys), shared_weights(keys, strata, g))

    coverage = {s.label: {"returned": len(s.returned), "errored": len(s.errored),
                          "absent": len(s.absent)}
                for s in [*ablation.values(), *references.values()]}
    unmapped = {config: sum((ablation[(config, r)].unmapped for r in range(1, REPLICATES + 1)
                             if (config, r) in ablation), Counter())
                for config in CONFIGS}
    run_stats = {}
    for (config, rep) in ablation:
        stats_path = run_dir(root, config, rep) / "run_stats.json"
        if stats_path.exists():
            run_stats[f"{config} r{rep}"] = json.loads(stats_path.read_text(encoding="utf-8"))
    return {
        "results": results, "contrasts": contrasts, "noise": noise,
        "references": reference_results, "coverage": coverage,
        "groups": {g: len(k) for g, (k, _w) in weights.items()},
        "common_windows": len(common), "dropped_windows": dropped,
        "unmapped_hazards": {c: dict(u.most_common()) for c, u in unmapped.items()},
        "run_stats": run_stats,
        "rows": [r for s in [*ablation.values(), *references.values()] for r in s.rows],
        "runs_scored": [f"{c} r{r}" for c, r in ablation],
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _pct(x: float) -> str:
    return "–" if x != x else f"{100 * x:.1f}%"


def _ci_pct(e: dict) -> str:
    return "–" if e["point"] != e["point"] else (
        f"{_pct(e['point'])} ({_pct(e['lo'])}–{_pct(e['hi'])})")


def _pp(e: dict) -> str:
    if e["point"] != e["point"]:
        return "–"
    mark = " ◆" if (e["lo"] > 0 or e["hi"] < 0) else ""
    return (f"{100 * e['point']:+.1f} pp ({100 * e['lo']:+.1f} to {100 * e['hi']:+.1f}){mark}")


def _num(e: dict, digits: int = 2) -> str:
    return "–" if e["point"] != e["point"] else (
        f"{e['point']:.{digits}f} ({e['lo']:.{digits}f}–{e['hi']:.{digits}f})")


def _git_state() -> str:
    try:
        commit = subprocess.run(["git", "log", "-1", "--format=%h", "--", str(PROTOCOL)],
                                cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", str(PROTOCOL)],
                               cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"
    if not commit:
        return "**not committed**"
    return f"commit `{commit}`" + (" **with uncommitted edits**" if dirty else "")


def render(ev: dict, gold: GoldSet, repro: list[str]) -> str:
    R, C, N = ev["results"], ev["contrasts"], ev["noise"]
    configs = [c for c in CONFIGS if c in R]
    L: list[str] = []
    add = L.append

    add("# Experiment B — controlled ablation of prompt 5\n")
    add("> **Retrospective diagnostic ablation.** The windows were selected on production "
        "output (every Experiment A window because prompt 5 found an event in it) and the "
        "event-absent gold was annotated with production output visible. Differences below "
        "say which constraints matter on these windows; none is an estimate of "
        "generalisation performance.\n")
    add(f"- Protocol: `ablation/ABLATION_PROTOCOL.md` at {_git_state()}.")
    add(f"- Windows: `ablation/windows.csv` sha256 "
        f"`{hashlib.sha256(WINDOWS.read_bytes()).hexdigest()[:16]}…` — "
        + ", ".join(f"{g} {n}" for g, n in ev["groups"].items()) + ".")
    add(f"- Gold: Experiment A `event_level_gold.csv` sha256 `{gold.sha256[:16]}…`, read in "
        "place; event-absent windows carry no gold events.")
    add(f"- Hazard normaliser `LEXICON_SHA256` `{LEXICON_SHA256[:16]}…`, applied to every run.")
    add(f"- Model `{SPEC.id}`, reasoning effort {SPEC.reasoning_effort}, structured output "
        f"{SPEC.structured_output}; {REPLICATES} replicates per configuration, pooled.")
    add("- Experiment A reproduction (September and Azure runs on its 45 windows, R1, every "
        "counter): " + ("**ok**." if not repro else "**FAILED** — " + "; ".join(repro)))
    add(f"- Runs scored: {', '.join(ev['runs_scored']) or 'none'}. Windows in every "
        f"contrast: {ev['common_windows']}"
        + (f"; dropped (an ablation run errored): {', '.join(k[:12] for k in ev['dropped_windows'])}"
           if ev["dropped_windows"] else "") + ".")
    add("\n_Intervals: 95% percentile window-cluster bootstrap, 2,000 resamples, one weight "
        "matrix per group shared by every configuration (paired). Δ = configuration − `full`. "
        "◆ = interval excludes 0. Uncorrected for multiple comparisons. Judge every Δ against "
        "the replicate noise in §8._\n")

    add("## 1. Coverage and cost\n")
    add("| Run | Returned | Errored | Absent | Events | Failed calls | Cost | Providers |")
    add("|---|---:|---:|---:|---:|---:|---:|---|")
    for label, cov in ev["coverage"].items():
        st = ev["run_stats"].get(label, {})
        add(f"| {label} | {cov['returned']} | {cov['errored']} | {cov['absent']} | "
            f"{st.get('events', '–')} | {st.get('failed_attempts', '–')} | "
            f"{('$%.2f' % st['cost_usd']) if 'cost_usd' in st else '–'} | "
            f"{', '.join(f'{k} {v}' for k, v in (st.get('providers') or {}).items()) or '–'} |")

    def table(title: str, metrics: list[tuple[str, str]], reading: str, group: str = "all",
              rows_for=None) -> None:
        add(title)
        add("| Config | " + " | ".join(f"{h} | Δ {h}" for _m, h in metrics) + " |")
        add("|---|" + "---|---|" * len(metrics))
        for c in rows_for or configs:
            res = R.get(c, {}).get(reading, {}).get(group)
            if res is None:
                continue
            cells = []
            for m, _h in metrics:
                d = C.get(c, {}).get(reading, {}).get(group, {}).get(m)
                cells += [_ci_pct(res[m]), _pp(d) if d else "—"]
            add(f"| `{c}` | " + " | ".join(cells) + " |")
        add("")

    add("\n## 2. Primary outcomes (R2, all windows)\n")
    table("", [("det_f1", "Detection F1"), ("pooled_f1", "Pooled attribute F1")], "R2")

    add("## 3. Event-level detail (R2, all windows)\n")
    table("", [("det_p", "Detection P"), ("det_r", "Detection R"), ("crc", "CRC"),
               ("crr", "CRR")], "R2")
    table("", [("attr_f1", "Attribute F1"), ("attr_f1_hazard", "hazard"),
               ("attr_f1_year", "year"), ("attr_f1_location", "location")], "R2")
    table("", [("pooled_f1_hazard", "Pooled hazard"), ("pooled_f1_year", "Pooled year"),
               ("pooled_f1_location", "Pooled location")], "R2")

    add("## 4. By window group (R2)\n")
    for g in ("event_present", "single", "multi"):
        table(f"**{g}**\n", [("det_f1", "Detection F1"), ("crc", "CRC"),
                             ("pooled_f1", "Pooled F1")], "R2", g)

    add("## 5. Event-absent windows\n")
    add("A record on an event-absent window has no gold event, so every one is a false "
        "positive. `S3` sets aside records whose places and year (and any evidence) are "
        "literally in the window — the Validation 2 \"no\" had no written guideline — as a "
        "bound on how much of the false-alarm rate could be gold error.\n")
    for g in ("event_absent", "random_negative", "hard_negative"):
        add(f"**{g}**\n")
        add("| Config | False-alarm windows | Δ | Records / window | Δ | False-alarm S3 | Δ |")
        add("|---|---|---|---|---|---|---|")
        for c in configs:
            res = R.get(c, {}).get("R2", {}).get(g)
            if res is None:
                continue
            d = C.get(c, {}).get("R2", {}).get(g, {})
            add(f"| `{c}` | {_ci_pct(res['fa_rate'])} | {_pp(d['fa_rate']) if d else '—'} | "
                f"{_num(res['rec_per_absent'])} | "
                f"{('%+.2f' % d['rec_per_absent']['point']) if d else '—'} | "
                f"{_ci_pct(res['fa_rate_s3'])} | {_pp(d['fa_rate_s3']) if d else '—'} |")
        add("")
    table("Detection with the S3 bound, all windows:\n",
          [("det_p_s3", "Detection P (S3)"), ("det_f1_s3", "Detection F1 (S3)")], "R2")

    add("## 6. Traceability\n")
    add("Snippet grades are `citation_quality.classify` against the window; held-out grades "
        "are out of the denominator. `no_evidence` and `bare` emit no evidence by design: "
        "snippet traceability is **unavailable** for them, not zero. Attribute traceability — "
        "every place word-bounded in the window, and a year that appears in it — applies to "
        "all five.\n")
    add("| Config | Snippets / record | Quotable | Grounded | Unsupported | Records with a "
        "quotable snippet | Places literal | Year literal | Both |")
    add("|---|---:|---|---|---|---|---|---|---|")
    for c in configs:
        res = R[c]["R2"]["all"]
        snip = c not in EVIDENCE_FREE
        cell = (lambda m: _ci_pct(res[m]) if snip else "unavailable")
        add(f"| `{c}` | {('%.2f' % res['snip_per_record']['point']) if snip else '—'} | "
            f"{cell('snip_quotable')} | {cell('snip_grounded')} | {cell('snip_unsupported')} | "
            f"{cell('rec_quotable')} | {_ci_pct(res['trace_loc'])} | "
            f"{_ci_pct(res['trace_year'])} | {_ci_pct(res['trace_both'])} |")
    add("")
    table("Δ attribute traceability:\n", [("trace_both", "Places and year literal")], "R2")

    add("## 7. Schema compliance (raw JSON before the post-filter)\n")
    add("| Config | Raw events / window | Dropped | not verifiable | low confidence | missing "
        "field | duplicate | Admin-level mismatch | Invalid admin tag | Exact-vocabulary "
        "hazard | ISO date |")
    add("|---|---:|---|---|---|---|---|---|---|---|---|")
    for c in configs:
        res = R[c]["R2"]["all"]
        per_window = res["raw_events_per_window"]["point"]
        add(f"| `{c}` | {'–' if per_window != per_window else f'{per_window:.2f}'} | "
            f"{_pct(res['drop_any']['point'])} | "
            + " | ".join(_pct(res[d]["point"]) for d in _DROPS)
            + f" | {_pct(res['admin_mismatch']['point'])} | {_pct(res['admin_invalid']['point'])}"
            f" | {_pct(res['hz_exact_raw']['point'])} | {_pct(res['date_iso']['point'])} |")
    add("\nError rows and failed calls are in §1. `no_vocab` and `bare` are not asked for exact "
        "labels; their exact-vocabulary rate is descriptive.\n")

    add("## 8. Replicate noise (replicate 2 − replicate 1, R2, all windows)\n")
    add("| Config | Detection F1 | Pooled F1 | CRC | False-alarm windows |")
    add("|---|---|---|---|---|")
    for c in configs:
        n = N.get(c, {}).get("R2", {}).get("all")
        if n:
            add(f"| `{c}` | {_pp(n['det_f1'])} | {_pp(n['pooled_f1'])} | {_pp(n['crc'])} | "
                f"{_pp(n['fa_rate'])} |")
    add("")

    add("## 9. Sensitivity\n")
    for g, title in (("S1_no_dev_pool", "S1 — without the 2 dev-pool windows"),
                     ("S2_no_gold_validation", "S2 — without the 5 `gold_validation` windows")):
        table(f"**{title}** (R2)\n", [("det_f1", "Detection F1"), ("pooled_f1", "Pooled F1")],
              "R2", g)
    table("**S4 — R1, Experiment A's anchored matching** (configurations that emit evidence)\n",
          [("det_f1", "Detection F1"), ("crc", "CRC"), ("attr_f1", "Attribute F1")], "R1",
          rows_for=[c for c in configs if c not in EVIDENCE_FREE])

    add("## 10. Hazard normalisation\n")
    add("| Config | Records relabelled | Records with an unmapped component | Top unmapped |")
    add("|---|---|---|---|")
    for c in configs:
        res = R[c]["R2"]["all"]
        top = ", ".join(f"{k} ({v})" for k, v in list(ev["unmapped_hazards"].get(c, {}).items())[:6])
        add(f"| `{c}` | {_pct(res['hz_changed']['point'])} | {_pct(res['hz_unmapped']['point'])} "
            f"| {top or '–'} |")
    add("\nUnmapped components pass through to `hazard_key`, whose family regex still rolls "
        "some up (a bare \"storm\" lands in the cyclone family).\n")

    add("## 11. Reference rows (not contrasted)\n")
    add("The September OpenRouter GPT-5 prompt-5 run and the Azure production run on the same "
        "windows. The Azure run is the one the windows were selected on.\n")
    add("| Run | Reading | Detection F1 | Pooled F1 | CRC | False-alarm windows |")
    add("|---|---|---|---|---|---|")
    for label, by_reading in ev["references"].items():
        for reading in READINGS:
            res = by_reading.get(reading, {}).get("all")
            if res:
                add(f"| {label} | {reading} | {_ci_pct(res['det_f1'])} | {_ci_pct(res['pooled_f1'])} "
                    f"| {_ci_pct(res['crc'])} | {_ci_pct(res['fa_rate'])} |")
    add("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_pairs(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for r in rows:
        fields.extend(k for k in r if k not in fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, float) and obj != obj:
        return None
    return obj


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--allow-partial", action="store_true", help="score whatever runs exist")
    p.add_argument("--references-only", action="store_true",
                   help="only the September and Azure rows (before the ablation runs)")
    p.add_argument("--runs-root", type=Path, default=RUNS)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    p.add_argument("--pairs-out", type=Path, default=DEFAULT_PAIRS)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("eval.score_event_level").setLevel(logging.ERROR)   # quote warnings: Exp A's

    gold, expa = load_ablation_gold()
    cache = WindowCache(gold.texts)
    repro = check_expA_reproduction(expa, cache)
    if repro:
        raise ScoringError("The re-implemented loop does not reproduce Experiment A:\n  "
                           + "\n  ".join(repro))
    ev = evaluate(gold, cache, root=args.runs_root, allow_partial=args.allow_partial,
                  references_only=args.references_only)
    args.out.write_text(render(ev, gold, repro), encoding="utf-8")
    write_pairs(args.pairs_out, ev.pop("rows"))
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "gold_sha256": gold.sha256, "lexicon_sha256": LEXICON_SHA256,
               "windows_sha256": hashlib.sha256(WINDOWS.read_bytes()).hexdigest(),
               "fields": list(FIELDS), **ev}
    args.json_out.write_text(json.dumps(_jsonable(payload), indent=1) + "\n", encoding="utf-8")
    for path in (args.out, args.json_out, args.pairs_out):
        print(f"-> {path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
