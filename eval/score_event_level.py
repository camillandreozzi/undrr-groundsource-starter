"""
Score extraction runs against the event-level gold — complete records, not pooled attributes.

    python3 eval/score_event_level.py                    # every run; refuses until all windows are done
    python3 eval/score_event_level.py --allow-partial    # preview on what is annotated so far
    python3 eval/score_event_level.py --audit-sample eval/event_link_audit.csv

`eval/score_against_human.py` unions a document's gold hazards, dates and
locations and compares them with the union of a run's events. Two events with
their years and places swapped score 100% there. This scorer pairs each
predicted record with at most one gold event (`eval/event_matching.py`), scores
the fields only within that pair, and reports:

  detection            records matched to a gold event / records; verifiable
                       gold events matched / verifiable gold events.
  complete-record      records that are matched AND carry that event's hazard,
  correctness          year and locations / ALL records. A record with no gold
                       event stays in the denominator.
  attribute F1         per-field TP/FP/FN inside matched pairs; an unmatched
                       record's values are all FP, a missed event's all FN.
  pooled F1            the document-level reading on the same windows with the
                       same value rules, so the gap is association alone.
  misassociation       wrong values in matched pairs that belong to another
                       gold event of the same window — the swap itself.

Everything is reported overall, for single- and multi-event windows separately
(by the gold's own event count, not the sampling stratum), and per sampling
stratum. The sample over-represents multi-event windows by design: it is a
stress test, and nothing here is weighted back to the corpus.

Intervals are 95% percentile cluster bootstraps over windows (events in one
window are not independent draws). The full rules, frozen before scoring, are
in `eval/EVENT_LEVEL_PROTOCOL.md`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import subprocess
import sys
import zlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import numpy as np  # noqa: E402

from benchmark_openrouter.agreement import REFERENCE_RUNS, discover_runs  # noqa: E402
from eval.event_matching import (  # noqa: E402
    FIELDS, GoldEvent, PredEvent, Window, gold_value_counts, match_window,
    optimistic_alignment, pooled_counts, pred_value_counts,
)
from eval.human_annotation_app import load_document_store, read_csv, write_csv_atomic  # noqa: E402
from eval.score_against_human import Run  # noqa: E402
from fonte.stats import wilson_interval  # noqa: E402

LOG = logging.getLogger("eval.score_event_level")

EVAL = REPO_ROOT / "eval"
DEFAULT_GOLD = EVAL / "event_level_gold.csv"
DEFAULT_WINDOWS = EVAL / "event_level_windows.csv"
DEFAULT_QUEUE = EVAL / "event_level_queue.csv"
DEFAULT_STORES = (EVAL / "annotation_documents.json",
                  EVAL / "annotation_documents_document_sample.json")
DEFAULT_OR_DIR = REPO_ROOT / "benchmark_openrouter" / "outputs_pooled"
DEFAULT_OUT = EVAL / "EVENT_LEVEL_SCORES.md"
DEFAULT_PAIRS = EVAL / "event_level_pairs.csv"
DEFAULT_JSON = EVAL / "event_level_scores.json"
DEFAULT_AUDIT = EVAL / "event_link_audit.csv"
PROTOCOL = EVAL / "EVENT_LEVEL_PROTOCOL.md"

#: The system every other one is compared against in the paired table.
BASELINE = REFERENCE_RUNS[0][0]

BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 42
AUDIT_SEED = 45
AUDIT_LINKS_AB = 25
AUDIT_FPS = 15

CLASSES = ("single", "multi", "none")
CLASS_LABEL = {"single": "single-event", "multi": "multi-event",
               "none": "no verifiable event"}


class ScoringError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Gold
# ---------------------------------------------------------------------------

@dataclass
class GoldSet:
    windows: dict[str, dict]          # asset_key -> queue row merged with window row
    events: dict[str, list[GoldEvent]]
    texts: dict[str, str]
    queued: int
    sha256: str

    @property
    def keys(self) -> list[str]:
        return sorted(self.windows, key=lambda k: int(self.windows[k].get("review_rank") or 0))

    def window_class(self, key: str) -> str:
        n = sum(1 for g in self.events.get(key, []) if g.verifiable)
        return "none" if n == 0 else "single" if n == 1 else "multi"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def load_gold(gold_path: Path, windows_path: Path, queue_path: Path,
              store_paths: list[Path], allow_partial: bool = False) -> GoldSet:
    for path in (gold_path, windows_path, queue_path):
        if not path.exists():
            raise ScoringError(f"Not found: {path}\n"
                               "Draw the sample (make event-sample) and annotate it "
                               "(make event-annotate) first.")
    _, queue = read_csv(queue_path)
    queue_by_key = {r["asset_key"]: r for r in queue}
    _, window_rows = read_csv(windows_path)
    done = {r["asset_key"]: r for r in window_rows
            if str(r.get("window_status", "")).strip().lower() == "done"}
    if not done:
        raise ScoringError(f"No window in {windows_path} is annotated yet.")
    if len(done) < len(queue) and not allow_partial:
        raise ScoringError(
            f"{len(done)} of {len(queue)} windows annotated. The pre-registered "
            "result needs all of them; pass --allow-partial to preview.")

    _, gold_rows = read_csv(gold_path)
    events: dict[str, list[GoldEvent]] = defaultdict(list)
    for row in gold_rows:
        if row.get("asset_key") in done:
            events[row["asset_key"]].append(GoldEvent.from_row(row))

    texts: dict[str, str] = {}
    for path in store_paths:
        documents, _ = load_document_store(path)
        texts.update({k: v.get("text", "") for k, v in documents.items()})
    missing = sorted(k for k in done if not texts.get(k))
    if missing:
        raise ScoringError(f"No window text for {len(missing)} annotated windows: "
                           + ", ".join(k[:12] for k in missing))

    windows = {k: {**queue_by_key.get(k, {}), **row} for k, row in done.items()}
    return GoldSet(windows, dict(events), texts, len(queue), _sha256(gold_path))


# ---------------------------------------------------------------------------
# Per-window counts
# ---------------------------------------------------------------------------

COUNTERS = (
    "records", "records_matched", "gold_req", "gold_req_matched",
    "complete", "gold_complete", "matched_pairs", "exact_all",
    *[f"{k}_{f}" for k in ("ok", "exact", "tp", "fp", "fn", "ptp", "pfp", "pfn", "mis", "uns")
      for f in FIELDS],
    "tier_A", "tier_B", "tier_C", "split", "no_event", "merge", "missed",
    "opt_complete",
)
_IDX = {name: i for i, name in enumerate(COUNTERS)}


def _fmt_years(g: GoldEvent) -> str:
    if g.year_start is None:
        return ""
    return str(g.year_start) if g.year_end in (None, g.year_start) else f"{g.year_start}-{g.year_end}"


def score_window(preds: list[PredEvent], golds: list[GoldEvent], text: str,
                 system: str, meta: dict, window_class: str) -> tuple[dict[str, int], list[dict]]:
    """Counts for one system on one window, and the audit-trail rows."""
    c = dict.fromkeys(COUNTERS, 0)
    window = Window(text, golds)
    match = match_window(preds, window)

    c["records"] = len(preds)
    c["gold_req"] = sum(1 for g in golds if g.verifiable)
    rows: list[dict] = []
    base = {"system": system, "asset_key": meta["asset_key"],
            "review_rank": meta.get("review_rank", ""), "stratum": meta.get("stratum", ""),
            "window_class": window_class}

    def pred_cols(p: PredEvent) -> dict:
        return {"event_index": p.event_index, "pred_hazard": " | ".join(p.hazards),
                "pred_dates": p.dates, "pred_locations": " | ".join(p.locations),
                "pred_evidence": " | ".join(p.snippets)}

    def gold_cols(g: GoldEvent) -> dict:
        return {"gold_event_id": g.gold_event_id, "gold_verifiable": "yes" if g.verifiable else "no",
                "gold_hazard": " | ".join([g.hazard_primary, *g.hazard_secondary]),
                "gold_years": _fmt_years(g), "gold_locations": " | ".join(g.locations),
                "gold_support": " || ".join(g.support_quotes)}

    for link in match.links:
        v = link.verdict
        c["records_matched"] += 1
        c["matched_pairs"] += 1
        c[f"tier_{link.tier}"] += 1
        if link.gold.verifiable:
            c["gold_req_matched"] += 1
        if v.complete:
            c["complete"] += 1
            if link.gold.verifiable:
                c["gold_complete"] += 1
        if all(v.exact[f] for f in FIELDS):
            c["exact_all"] += 1
        for f in FIELDS:
            c[f"ok_{f}"] += v.ok[f]
            c[f"exact_{f}"] += v.exact[f]
            c[f"tp_{f}"] += v.tp[f]
            c[f"fp_{f}"] += v.fp[f]
            c[f"fn_{f}"] += v.fn[f]
            c[f"mis_{f}"] += v.misassociated[f]
            c[f"uns_{f}"] += v.unsupported[f]
        rows.append({**base, "status": "matched", "tier": link.tier,
                     "identity_score": f"{link.score:.3f}", "complete": int(v.complete),
                     **{f"ok_{f}": int(v.ok[f]) for f in FIELDS},
                     **{f"exact_{f}": int(v.exact[f]) for f in FIELDS},
                     **{f"mis_{f}": v.misassociated[f] for f in FIELDS},
                     **{f"uns_{f}": v.unsupported[f] for f in FIELDS},
                     **pred_cols(link.pred), **gold_cols(link.gold)})

    for p, reason in match.unmatched_pred:
        c[reason] += 1
        for f, n in pred_value_counts(p).items():
            c[f"fp_{f}"] += n
        rows.append({**base, "status": "false_positive", "unmatched_reason": reason,
                     "complete": 0, **pred_cols(p)})

    for g, reason in match.unmatched_gold:
        if g.verifiable:
            c[reason] += 1
            for f, n in gold_value_counts(g).items():
                c[f"fn_{f}"] += n
        rows.append({**base, "status": "false_negative" if g.verifiable else "unmatched_not_required",
                     "unmatched_reason": reason, **gold_cols(g)})

    for f, (tp, fp, fn) in pooled_counts(preds, golds).items():
        c[f"ptp_{f}"], c[f"pfp_{f}"], c[f"pfn_{f}"] = tp, fp, fn

    c["opt_complete"] = sum(1 for _p, _g, v in optimistic_alignment(preds, golds) if v.complete)
    for g_id, quote in window.unlocated_quotes:
        LOG.warning("%s gold event %d: support quote not found in the window: %.60s",
                    meta["asset_key"][:12], g_id, quote)
    return c, rows


# ---------------------------------------------------------------------------
# Metrics (work on scalars and on bootstrap arrays alike)
# ---------------------------------------------------------------------------

def _div(n, d):
    n, d = np.asarray(n, dtype=float), np.asarray(d, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(d > 0, n / np.where(d > 0, d, 1), np.nan)


def _f1(tp, fp, fn):
    return _div(2 * np.asarray(tp, dtype=float), 2 * np.asarray(tp, dtype=float) + fp + fn)


def _sum(s, prefix):
    return sum(s[f"{prefix}_{f}"] for f in FIELDS)


def _hmean(p, r):
    p, r = np.asarray(p, dtype=float), np.asarray(r, dtype=float)
    return _div(2 * p * r, p + r)


# A record matched to a `verifiable=no` gold event counts as detected (it is a
# real occurrence) but such events are never required, so P and R have
# different numerators; F1 is their harmonic mean rather than a TP/FP/FN count.
METRICS = {
    "det_p": lambda s: _div(s["records_matched"], s["records"]),
    "det_r": lambda s: _div(s["gold_req_matched"], s["gold_req"]),
    "det_f1": lambda s: _hmean(_div(s["records_matched"], s["records"]),
                               _div(s["gold_req_matched"], s["gold_req"])),
    "crc": lambda s: _div(s["complete"], s["records"]),
    "crr": lambda s: _div(s["gold_complete"], s["gold_req"]),
    "attr_f1": lambda s: _f1(_sum(s, "tp"), _sum(s, "fp"), _sum(s, "fn")),
    "pooled_f1": lambda s: _f1(_sum(s, "ptp"), _sum(s, "pfp"), _sum(s, "pfn")),
    "gap": lambda s: (_f1(_sum(s, "ptp"), _sum(s, "pfp"), _sum(s, "pfn"))
                      - _f1(_sum(s, "tp"), _sum(s, "fp"), _sum(s, "fn"))),
    "opt_crc": lambda s: _div(s["opt_complete"], s["records"]),
    **{f"attr_p_{f}": (lambda f: lambda s: _div(s[f"tp_{f}"], s[f"tp_{f}"] + s[f"fp_{f}"]))(f)
       for f in FIELDS},
    **{f"attr_r_{f}": (lambda f: lambda s: _div(s[f"tp_{f}"], s[f"tp_{f}"] + s[f"fn_{f}"]))(f)
       for f in FIELDS},
    **{f"attr_f1_{f}": (lambda f: lambda s: _f1(s[f"tp_{f}"], s[f"fp_{f}"], s[f"fn_{f}"]))(f)
       for f in FIELDS},
    **{f"pooled_f1_{f}": (lambda f: lambda s: _f1(s[f"ptp_{f}"], s[f"pfp_{f}"], s[f"pfn_{f}"]))(f)
       for f in FIELDS},
    **{f"agree_{f}": (lambda f: lambda s: _div(s[f"ok_{f}"], s["matched_pairs"]))(f)
       for f in FIELDS},
    **{f"exact_{f}": (lambda f: lambda s: _div(s[f"exact_{f}"], s["matched_pairs"]))(f)
       for f in FIELDS},
    "agree_all": lambda s: _div(s["complete"], s["matched_pairs"]),
    "exact_all": lambda s: _div(s["exact_all"], s["matched_pairs"]),
    **{f"mis_share_{f}": (lambda f: lambda s: _div(s[f"mis_{f}"], s[f"mis_{f}"] + s[f"uns_{f}"]))(f)
       for f in FIELDS},
}

#: Rates whose denominator is a count of records or events, where a Wilson
#: interval (records treated as independent) is shown beside the bootstrap.
WILSON = {"det_p": ("records_matched", "records"), "det_r": ("gold_req_matched", "gold_req"),
          "crc": ("complete", "records"), "crr": ("gold_complete", "gold_req")}


def _named(vec) -> dict:
    return {name: vec[..., i] for name, i in _IDX.items()}


def _seed(*parts: str) -> list[int]:
    return [BOOTSTRAP_SEED, zlib.crc32("|".join(parts).encode())]


def summarise(matrix: np.ndarray, label: str, group: str) -> dict:
    """Point estimates and 95% cluster-bootstrap intervals for one group."""
    n = matrix.shape[0]
    totals = _named(matrix.sum(axis=0))
    out = {"windows": n, **{k: int(totals[k]) for k in
                             ("records", "gold_req", "matched_pairs", "complete")}}
    boot = None
    if n >= 2:
        rng = np.random.default_rng(_seed(label, group))
        idx = rng.integers(0, n, size=(BOOTSTRAP_N, n))
        boot = _named(matrix[idx].sum(axis=1))
    for name, fn in METRICS.items():
        point = float(fn(totals))
        lo = hi = float("nan")
        if boot is not None:
            values = fn(boot)
            values = values[~np.isnan(values)]
            if values.size:
                lo, hi = (float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5)))
        out[name] = {"point": point, "lo": lo, "hi": hi}
    for name, (num, den) in WILSON.items():
        if totals[den]:
            out[name]["wilson"] = list(wilson_interval(int(totals[num]), int(totals[den])))
    for name in COUNTERS:
        out.setdefault("counts", {})[name] = int(totals[name])
    return out


def paired_difference(a: np.ndarray, b: np.ndarray, label: str, group: str) -> dict:
    """Complete-record correctness, system minus baseline, on shared windows."""
    n = a.shape[0]
    point = float(METRICS["crc"](_named(a.sum(axis=0))) - METRICS["crc"](_named(b.sum(axis=0))))
    lo = hi = float("nan")
    if n >= 2:
        rng = np.random.default_rng(_seed("paired", label, group))
        idx = rng.integers(0, n, size=(BOOTSTRAP_N, n))
        diff = (METRICS["crc"](_named(a[idx].sum(axis=1)))
                - METRICS["crc"](_named(b[idx].sum(axis=1))))
        diff = diff[~np.isnan(diff)]
        if diff.size:
            lo, hi = float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))
    return {"windows": n, "point": point, "lo": lo, "hi": hi}


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def load_runs(specs: list[str], or_dir: Path) -> list[tuple[str, Path]]:
    if specs:
        out = []
        for spec in specs:
            label, _, path = spec.partition("=")
            out.append((label, Path(path)) if path else (Path(label).stem, Path(label)))
        return out
    runs = [(label, path) for label, path in REFERENCE_RUNS if path.exists()]
    runs += [(label, path) for label, path, _stats in discover_runs(or_dir)]
    return runs


@dataclass
class SystemResult:
    label: str
    returned: list[str]
    errored: list[str]
    absent: list[str]
    per_window: dict[str, np.ndarray]
    rows: list[dict]


def score_system(label: str, path: Path, gold: GoldSet) -> SystemResult:
    run = Run(label, path)
    errored, absent, returned = [], [], []
    for key in gold.keys:
        if key not in run.docs:
            absent.append(key)
        elif key in run.errored:
            errored.append(key)
        else:
            returned.append(key)
    per_window: dict[str, np.ndarray] = {}
    rows: list[dict] = []
    for key in returned:
        preds = [PredEvent.from_row(r, i + 1) for i, r in enumerate(run.events.get(key, []))]
        meta = {"asset_key": key, **gold.windows[key]}
        counts, window_rows = score_window(preds, gold.events.get(key, []), gold.texts[key],
                                           label, meta, gold.window_class(key))
        per_window[key] = np.array([counts[c] for c in COUNTERS], dtype=float)
        rows.extend(window_rows)
    return SystemResult(label, returned, errored, absent, per_window, rows)


def groups_for(gold: GoldSet) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {"all": gold.keys}
    for cls in CLASSES:
        keys = [k for k in gold.keys if gold.window_class(k) == cls]
        if keys:
            groups[cls] = keys
    for stratum in sorted({gold.windows[k].get("stratum", "") for k in gold.keys} - {""}):
        groups[f"stratum:{stratum}"] = [k for k in gold.keys
                                        if gold.windows[k].get("stratum") == stratum]
    return groups


def evaluate(gold: GoldSet, systems: list[SystemResult]) -> dict:
    groups = groups_for(gold)
    results: dict[str, dict] = {}
    for s in systems:
        if not s.per_window:
            continue
        results[s.label] = {}
        for group, keys in groups.items():
            keys = [k for k in keys if k in s.per_window]
            if keys:
                matrix = np.vstack([s.per_window[k] for k in keys])
                results[s.label][group] = summarise(matrix, s.label, group)

    paired: dict[str, dict] = {}
    base = next((s for s in systems if s.label == BASELINE and s.per_window), None)
    if base is not None:
        for s in systems:
            if s is base or not s.per_window:
                continue
            paired[s.label] = {}
            for group in ("all", "single", "multi"):
                keys = [k for k in groups.get(group, [])
                        if k in s.per_window and k in base.per_window]
                if keys:
                    paired[s.label][group] = paired_difference(
                        np.vstack([s.per_window[k] for k in keys]),
                        np.vstack([base.per_window[k] for k in keys]), s.label, group)
    return {"groups": {g: len(k) for g, k in groups.items()}, "results": results, "paired": paired}


# ---------------------------------------------------------------------------
# Link audit
# ---------------------------------------------------------------------------

AUDIT_COLUMNS = (
    "audit_id", "kind", "system", "asset_key", "event_index", "gold_event_id", "tier",
    "pred_hazard", "pred_dates", "pred_locations", "pred_evidence",
    "gold_hazard", "gold_years", "gold_locations", "gold_support", "window_gold_events",
    "question", "verdict", "correct_gold_event_id", "notes",
)
QUESTIONS = {
    "link_AB": "Do this record and this gold event describe the same occurrence? (agree/disagree)",
    "link_C": "Do this record and this gold event describe the same occurrence? (agree/disagree)",
    "fp": "The matcher found no gold event for this record. Agree that none of the window's "
          "gold events is the occurrence it describes? If not, give correct_gold_event_id.",
}


def audit_sample(rows: list[dict], gold: GoldSet) -> list[dict]:
    """All tier-C links, then a seeded draw of tier-A/B links and of false positives."""
    def window_gold(key: str) -> str:
        return " ;; ".join(f"{g.gold_event_id}: {g.hazard_primary} {_fmt_years(g)} — "
                           f"{' | '.join(g.locations)}" for g in gold.events.get(key, []))

    links_c = [r for r in rows if r.get("status") == "matched" and r.get("tier") == "C"]
    links_ab = [r for r in rows if r.get("status") == "matched" and r.get("tier") in ("A", "B")]
    fps = [r for r in rows if r.get("status") == "false_positive"]
    rng = random.Random(AUDIT_SEED)
    picked = ([("link_C", r) for r in links_c]
              + [("link_AB", r) for r in rng.sample(links_ab, min(AUDIT_LINKS_AB, len(links_ab)))]
              + [("fp", r) for r in rng.sample(fps, min(AUDIT_FPS, len(fps)))])
    rng.shuffle(picked)
    out = []
    for i, (kind, r) in enumerate(picked, start=1):
        out.append({**{c: r.get(c, "") for c in AUDIT_COLUMNS}, "audit_id": str(i), "kind": kind,
                    "window_gold_events": window_gold(r["asset_key"]),
                    "question": QUESTIONS[kind], "verdict": "",
                    "correct_gold_event_id": "", "notes": ""})
    return out


def read_audit(path: Path) -> dict[str, dict[str, int]]:
    if not path.exists():
        return {}
    _, rows = read_csv(path)
    out: dict[str, dict[str, int]] = defaultdict(lambda: {"agree": 0, "disagree": 0, "pending": 0})
    for r in rows:
        verdict = str(r.get("verdict", "")).strip().lower()
        out[r.get("kind", "?")][verdict if verdict in ("agree", "disagree") else "pending"] += 1
    return dict(out)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _pct(x: float) -> str:
    return "–" if x is None or np.isnan(x) else f"{x:.1%}"


def _pp(x: float) -> str:
    return "–" if x is None or np.isnan(x) else f"{x * 100:+.1f} pp"


def _ci(m: dict) -> str:
    if np.isnan(m["point"]):
        return "–"
    if np.isnan(m["lo"]):
        return _pct(m["point"])
    return f"{_pct(m['point'])} ({m['lo']:.1%}–{m['hi']:.1%})"


def _wilson(m: dict) -> str:
    if "wilson" not in m:
        return "–"
    lo, hi = m["wilson"]
    return f"{lo:.1%}–{hi:.1%}"


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def protocol_state() -> str:
    rel = str(PROTOCOL.relative_to(REPO_ROOT))
    commit = _git("log", "-1", "--format=%h", "--", rel)
    dirty = bool(_git("status", "--porcelain", "--", rel))
    if not commit:
        return "**not committed — this run is not pre-registered**"
    return f"commit `{commit}`" + (" **with uncommitted edits since**" if dirty else "")


def render(gold: GoldSet, systems: list[SystemResult], ev: dict,
           audit: dict[str, dict[str, int]], gold_path: Path) -> str:
    res, paired = ev["results"], ev["paired"]
    scored = [s for s in systems if s.label in res]
    n_events = sum(len(v) for v in gold.events.values())
    n_ver = sum(1 for v in gold.events.values() for g in v if g.verifiable)
    classes = {c: sum(1 for k in gold.keys if gold.window_class(k) == c) for c in CLASSES}
    partial = len(gold.keys) < gold.queued
    unlocated = sum(len(Window(gold.texts[k], gold.events.get(k, [])).unlocated_quotes)
                    for k in gold.keys)

    L: list[str] = []
    L.append("# Event-level scores — complete records, not pooled attributes")
    L.append("")
    L.append("> **Targeted stress test.** The windows were drawn to over-represent "
             "multi-event documents (protocol §2). Nothing here is weighted back to the "
             "corpus, and no figure in this file estimates archive-wide accuracy.")
    L.append("")
    if partial:
        L.append(f"> ⚠️ **PARTIAL** — {len(gold.keys)} of {gold.queued} queued windows "
                 "annotated. Preview only; not the pre-registered result.")
        L.append("")
    L.append(f"- Gold: `{gold_path.name}` sha256 `{gold.sha256[:16]}…` — {n_events} gold events "
             f"({n_ver} verifiable) over {len(gold.keys)} windows: {classes['single']} single-event, "
             f"{classes['multi']} multi-event, {classes['none']} with no verifiable event.")
    L.append(f"- Protocol: `{PROTOCOL.name}` at {protocol_state()}.")
    L.append("- Matching: evidence-anchored one-to-one (protocol §4); field rules protocol §5. "
             f"Intervals: 95% cluster bootstrap over windows ({BOOTSTRAP_N:,} resamples, "
             f"seed {BOOTSTRAP_SEED}).")
    if unlocated:
        L.append(f"- ⚠️ {unlocated} gold support quote(s) could not be located in their window "
                 "— those events can only be matched through tier B or C.")
    L.append("")

    L.append("## 1. Coverage")
    L.append("")
    L.append("| System | Windows returned | Errored | Absent | Records on the sample |")
    L.append("|---|---:|---:|---:|---:|")
    for s in systems:
        records = sum(int(v[_IDX["records"]]) for v in s.per_window.values())
        L.append(f"| {s.label} | {len(s.returned)}/{len(gold.keys)} | {len(s.errored)} | "
                 f"{len(s.absent)} | {records if s.per_window else '–'} |")
    L.append("")
    L.append("_A system is scored only on the windows it returned (error policy `exclude`, "
             "as in `score_against_human.py`). Systems with none returned are not scored._")
    L.append("")

    L.append("## 2. Headline")
    L.append("")
    L.append("`Complete-record correctness` = records matched to a gold event **and** carrying "
             "its hazard, year and locations, over **all** records — a record with no gold event "
             "stays in the denominator. `Complete-record recall` = verifiable gold events "
             "recovered by such a record. `Pooling gap` = document-level pooled F1 minus "
             "event-level attribute F1 on the same windows and value rules: what pooling hid.")
    L.append("")
    L.append("| System | Records | Gold events | Detection P | Detection R | "
             "Complete-record correctness (95% CI) | Wilson | Complete-record recall | "
             "Event-level attribute F1 | Pooled document F1 | Pooling gap |")
    L.append("|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|")
    for s in scored:
        a = res[s.label]["all"]
        L.append(f"| {s.label} | {a['records']} | {a['gold_req']} | {_pct(a['det_p']['point'])} | "
                 f"{_pct(a['det_r']['point'])} | {_ci(a['crc'])} | {_wilson(a['crc'])} | "
                 f"{_pct(a['crr']['point'])} | {_pct(a['attr_f1']['point'])} | "
                 f"{_pct(a['pooled_f1']['point'])} | {_pp(a['gap']['point'])} |")
    L.append("")

    L.append("## 3. Single-event vs multi-event windows")
    L.append("")
    L.append("Windows are classed by the gold's own count of verifiable events, not by the "
             "sampling stratum.")
    L.append("")
    L.append("| System | Class | Windows | Records | Gold events | Detection P | Detection R | "
             "Complete-record correctness (95% CI) | Event-level attribute F1 | Pooled F1 | Gap |")
    L.append("|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|")
    for s in scored:
        for cls in ("single", "multi"):
            a = res[s.label].get(cls)
            if not a:
                continue
            L.append(f"| {s.label} | {CLASS_LABEL[cls]} | {a['windows']} | {a['records']} | "
                     f"{a['gold_req']} | {_pct(a['det_p']['point'])} | {_pct(a['det_r']['point'])} | "
                     f"{_ci(a['crc'])} | {_pct(a['attr_f1']['point'])} | "
                     f"{_pct(a['pooled_f1']['point'])} | {_pp(a['gap']['point'])} |")
    L.append("")

    L.append("## 4. Field agreement on matched events")
    L.append("")
    L.append("Of the records matched to a gold event, how many carry that event's value. "
             "`Association` is the primary rule (protocol §5); `exact` additionally requires "
             "every gold location, the full year span and the exact hazard labels.")
    L.append("")
    L.append("| System | Matched | Hazard | Year | Location | All three | "
             "Exact hazard | Exact year | Exact location | Exact all |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in scored:
        a = res[s.label]["all"]
        L.append(f"| {s.label} | {a['matched_pairs']} | "
                 + " | ".join(_pct(a[f"agree_{f}"]["point"]) for f in FIELDS)
                 + f" | {_pct(a['agree_all']['point'])} | "
                 + " | ".join(_pct(a[f"exact_{f}"]["point"]) for f in FIELDS)
                 + f" | {_pct(a['exact_all']['point'])} |")
    L.append("")

    L.append("## 5. Event-level attribute P / R / F1, per field")
    L.append("")
    L.append("| System | Field | Precision | Recall | F1 (95% CI) | Pooled F1 | Gap |")
    L.append("|---|---|---:|---:|---|---:|---:|")
    for s in scored:
        a = res[s.label]["all"]
        for f in FIELDS:
            gap = a[f"pooled_f1_{f}"]["point"] - a[f"attr_f1_{f}"]["point"]
            L.append(f"| {s.label} | {f} | {_pct(a[f'attr_p_{f}']['point'])} | "
                     f"{_pct(a[f'attr_r_{f}']['point'])} | {_ci(a[f'attr_f1_{f}'])} | "
                     f"{_pct(a[f'pooled_f1_{f}']['point'])} | {_pp(gap)} |")
    L.append("")

    L.append("## 6. Misassociation — wrong values that belong to another event")
    L.append("")
    L.append("Wrong values in matched records, split into those that are correct for a "
             "*different* gold event in the same window (the attribute swap a pooled metric "
             "credits) and those that belong to no event in the window.")
    L.append("")
    L.append("| System | Field | Wrong values | Another event's | Unsupported | Share misassociated | "
             "Multi-event windows: wrong | another event's |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for s in scored:
        a = res[s.label]["all"]["counts"]
        m = res[s.label].get("multi", {}).get("counts", {})
        for f in FIELDS:
            wrong = a[f"mis_{f}"] + a[f"uns_{f}"]
            share = a[f"mis_{f}"] / wrong if wrong else float("nan")
            mw = m.get(f"mis_{f}", 0) + m.get(f"uns_{f}", 0)
            L.append(f"| {s.label} | {f} | {wrong} | {a[f'mis_{f}']} | {a[f'uns_{f}']} | "
                     f"{_pct(share)} | {mw if m else '–'} | {m.get(f'mis_{f}', '–')} |")
    L.append("")

    L.append("## 7. Matcher diagnostics")
    L.append("")
    L.append("Links by tier (A anchored on located evidence, B paraphrase, C year + location "
             "fallback). False positives: `split` — the record's identity points at a gold event "
             "another record took; `no event` — nothing in the gold it could be. False "
             "negatives: `merged` — a record matched elsewhere also carries this event's "
             "evidence; `missed` — no record does.")
    L.append("")
    L.append("| System | Tier A | Tier B | Tier C | FP: split | FP: no event | FN: merged | FN: missed |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for s in scored:
        a = res[s.label]["all"]["counts"]
        L.append(f"| {s.label} | {a['tier_A']} | {a['tier_B']} | {a['tier_C']} | {a['split']} | "
                 f"{a['no_event']} | {a['merge']} | {a['missed']} |")
    L.append("")

    L.append("## 8. What the matching rule costs")
    L.append("")
    L.append("The same records under a field-maximising alignment that ignores evidence and "
             "pairs records with gold events to maximise complete records. It is the most "
             "generous one-to-one reading possible — an upper bound, never the result.")
    L.append("")
    L.append("| System | Complete-record correctness, evidence-anchored | Field-maximising bound | Δ |")
    L.append("|---|---:|---:|---:|")
    for s in scored:
        a = res[s.label]["all"]
        L.append(f"| {s.label} | {_pct(a['crc']['point'])} | {_pct(a['opt_crc']['point'])} | "
                 f"{_pp(a['opt_crc']['point'] - a['crc']['point'])} |")
    L.append("")

    if paired:
        L.append(f"## 9. Paired difference against {BASELINE}")
        L.append("")
        L.append("Complete-record correctness, system minus baseline, on the windows both "
                 "returned; 95% paired cluster bootstrap.")
        L.append("")
        L.append("| System | Windows | All windows | Single-event | Multi-event |")
        L.append("|---|---:|---|---|---|")
        for label, by_group in paired.items():
            cells = []
            for group in ("all", "single", "multi"):
                d = by_group.get(group)
                cells.append("–" if not d else
                             _pp(d["point"]) + ("" if np.isnan(d["lo"]) else
                                                f" ({d['lo'] * 100:+.1f} to {d['hi'] * 100:+.1f})"))
            L.append(f"| {label} | {by_group.get('all', {}).get('windows', '–')} | "
                     + " | ".join(cells) + " |")
        L.append("")

    strata = [g for g in ev["groups"] if g.startswith("stratum:")]
    if strata:
        L.append("## 10. By sampling stratum")
        L.append("")
        L.append("Strata are the pre-annotation proxies the sample was drawn on (protocol §2).")
        L.append("")
        L.append("| System | Stratum | Windows | Records | Detection P | Detection R | "
                 "Complete-record correctness |")
        L.append("|---|---|---:|---:|---:|---:|---|")
        for s in scored:
            for g in strata:
                a = res[s.label].get(g)
                if a:
                    L.append(f"| {s.label} | {g.split(':', 1)[1]} | {a['windows']} | "
                             f"{a['records']} | {_pct(a['det_p']['point'])} | "
                             f"{_pct(a['det_r']['point'])} | {_ci(a['crc'])} |")
        L.append("")

    L.append("## 11. Link audit")
    L.append("")
    if audit:
        L.append("A seeded sample of the matcher's decisions, judged by the annotator after "
                 "scoring. It checks the matcher; it does not change any figure above.")
        L.append("")
        L.append("| Decision | Judged | Annotator agrees | Pending |")
        L.append("|---|---:|---|---:|")
        for kind in ("link_AB", "link_C", "fp"):
            v = audit.get(kind)
            if not v:
                continue
            judged = v["agree"] + v["disagree"]
            rate = (f"{v['agree'] / judged:.1%} ({v['agree']}/{judged})" if judged else "–")
            L.append(f"| {kind} | {judged} | {rate} | {v['pending']} |")
    else:
        L.append("_Not yet drawn. `make event-audit-sample` writes it._")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

PAIR_COLUMNS = (
    "system", "asset_key", "review_rank", "stratum", "window_class", "status",
    "unmatched_reason", "tier", "identity_score", "event_index", "gold_event_id",
    "gold_verifiable", "complete",
    *[f"ok_{f}" for f in FIELDS], *[f"exact_{f}" for f in FIELDS],
    *[f"mis_{f}" for f in FIELDS], *[f"uns_{f}" for f in FIELDS],
    "pred_hazard", "pred_dates", "pred_locations", "pred_evidence",
    "gold_hazard", "gold_years", "gold_locations", "gold_support",
)


def _jsonable(obj):
    if isinstance(obj, float) and np.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    p.add_argument("--windows", type=Path, default=DEFAULT_WINDOWS)
    p.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    p.add_argument("--documents", type=Path, nargs="+", default=list(DEFAULT_STORES))
    p.add_argument("--run", action="append", default=[],
                   help="label=path; repeatable. Default: prompt 5, NER baseline and "
                        "every OpenRouter run in --or-dir")
    p.add_argument("--or-dir", type=Path, default=DEFAULT_OR_DIR)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--pairs-out", type=Path, default=DEFAULT_PAIRS)
    p.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    p.add_argument("--audit", type=Path, default=DEFAULT_AUDIT,
                   help="link-audit file to report on, if it exists")
    p.add_argument("--audit-sample", type=Path, default=None,
                   help="write a link-audit sample here (refuses to clobber without --force)")
    p.add_argument("--force", action="store_true")
    p.add_argument("--allow-partial", action="store_true",
                   help="score before every queued window is annotated")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    try:
        gold = load_gold(args.gold, args.windows, args.queue, list(args.documents),
                         args.allow_partial)
    except ScoringError as exc:
        LOG.error("%s", exc)
        return 1

    systems = []
    for label, path in load_runs(args.run, args.or_dir):
        LOG.info("Scoring %s", label)
        systems.append(score_system(label, path, gold))

    ev = evaluate(gold, systems)
    rows = [r for s in systems for r in s.rows]

    if args.audit_sample:
        if args.audit_sample.exists() and not args.force:
            LOG.error("%s exists; pass --force to redraw (verdicts in it would be lost).",
                      args.audit_sample)
            return 1
        sample = audit_sample(rows, gold)
        write_csv_atomic(args.audit_sample, AUDIT_COLUMNS, sample)
        LOG.info("Wrote %s — %d decisions to judge", args.audit_sample, len(sample))

    audit = read_audit(args.audit_sample or args.audit)
    args.out.write_text(render(gold, systems, ev, audit, args.gold) + "\n", encoding="utf-8")
    write_csv_atomic(args.pairs_out, PAIR_COLUMNS, rows)
    payload = {
        "gold_sha256": gold.sha256,
        "protocol": protocol_state(),
        "windows_annotated": len(gold.keys),
        "windows_queued": gold.queued,
        "window_classes": {c: sum(1 for k in gold.keys if gold.window_class(k) == c)
                           for c in CLASSES},
        "coverage": {s.label: {"returned": len(s.returned), "errored": len(s.errored),
                               "absent": len(s.absent)} for s in systems},
        **ev,
        "audit": audit,
    }
    args.json_out.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    LOG.info("Wrote %s, %s, %s", args.out, args.pairs_out, args.json_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
