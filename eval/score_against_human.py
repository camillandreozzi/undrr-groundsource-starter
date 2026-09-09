"""
Score any extraction run against the human annotations. No re-judging.

    python3 eval/score_against_human.py --run outputs/event_extractions/event_extractions.jsonl
    python3 eval/score_against_human.py \
        --run "prompt 5=outputs/event_extractions/event_extractions.jsonl" \
        --run "NER baseline=benchmark_ner/outputs/ner_extractions.jsonl"

A run is a JSONL or CSV file in the `event_extractions` schema
(`fonte.app_event_focus.OUTPUT_HEADERS`). Name it with `label=path` to
control how it appears in the table; otherwise the filename is used.

WHY DOCUMENT LEVEL
------------------
Two pipelines split the same document into events differently — the LLM's
"Earthquake | Tsunami" is the baseline's two candidates — so `event_index` is
not a shared key and joining on it would score segmentation, not extraction.
Everything here is therefore aggregated per `asset_key`: gold hazards, dates and
locations are the union over that document's annotated rows, and a run's are the
union over its verifiable events for the same document. A model is not penalised
for grouping differently, only for what it did and did not find.

FAILED CALLS ARE NOT FINDINGS
-----------------------------
A document whose only rows are error rows (`fonte.app_event_focus.
is_error_row` — `key_impacts` starts with "ERROR:") was never extracted: the
provider returned 403, or the model emitted something that would not parse. The
run made no claim about that document, and scoring the absence of a claim as
"found no event" measures the transport, not the model. Three OpenRouter runs
failed on 167/167 documents and scored 0.0% accuracy for it; DeepSeek scored
65.6% recall where its recall on documents it actually returned is 97.2%.

So errored documents are excluded from that run's denominator by default and
reported as coverage (`--error-policy exclude`). `--error-policy count-as-miss`
restores the older behaviour, which is the right choice only when you are
grading a pipeline end-to-end rather than comparing models.

Coverage is not free: a run scored on fewer documents is scored on an easier or
harder subset by luck, and its intervals are wider. Both are reported, and the
paired tests use only documents both runs actually returned.

WHAT IS REPORTED, AND WHY EACH
------------------------------
Detection, per document, on the documents a run returned:

  accuracy      hits / n. Dominated by prevalence here (157 of 167 documents
                carry an event), so it is reported but should not be ranked on.
  recall        of the gold-positive documents, how many the run found.
  specificity   of the gold-negative documents, how many it correctly declined.
                This is the discriminating number on this set and the one every
                run does badly on.
  precision     reported for continuity; with 10 negatives it is pinned near
                the prevalence and carries almost no information.
  balanced acc. (recall + specificity) / 2 — accuracy with the prevalence taken
                out, which is what "accuracy" is usually meant to convey.
  MCC           correlation over the full confusion matrix; the single number
                least fooled by an unbalanced set.

Every rate carries a 95% Wilson interval on its own denominator.

Fields, on documents gold says carry an event:

  micro P/R/F1  pooled TP/FP/FN over documents — a document counts in
                proportion to how much it contains. The headline.
  macro F1      mean of per-document F1 — every document counts once. Reported
                beside micro because they answer different questions and this
                set has documents carrying 1 location and documents carrying 30.
  bootstrap CI  95% percentile interval on micro F1 from 2,000 document-level
                resamples (seeded), so two runs' field scores can be compared
                without pretending a point estimate is exact.

Matching rules are reported side by side rather than chosen for you, because
the choice moves the numbers more than the model choice does:

  Hazard        family-level (`fonte.hazard_families`), compounds split
                on `|` first so label order cannot matter.
  Locations     exact (casefold); fuzzy raw (rapidfuzz token_set_ratio >= 90,
                no preprocessing — the rule as published); fuzzy normalised
                (NFKD, marks stripped, rapidfuzz's default_process, >= 90),
                which is the same rule with punctuation folded so that
                "Louisville" matches "Louisville, Kentucky".
  Dates         exact string; and year-set, comparing the 4-digit years each
                side mentions, which is the granularity gold actually carries
                (253 of 493 gold dates are a bare year).

With two or more runs, an exact McNemar test on event detection over the
documents both runs returned: the same documents are judged once, so the
informative quantity is the discordant pairs, not two independent proportions.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import re
import sys
import unicodedata
from collections import defaultdict
from math import comb, sqrt
from pathlib import Path
from typing import Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from fonte.app_event_focus import is_error_row  # noqa: E402
from fonte.hazard_families import hazard_family  # noqa: E402
from fonte.stats import format_rate, wilson_interval  # noqa: E402

DEFAULT_ANNOTATIONS = REPO_ROOT / "eval" / "human_annotations.csv"
DEFAULT_OUT = REPO_ROOT / "eval" / "HUMAN_ANNOTATION_SCORES.md"
FUZZY_THRESHOLD = 90
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 42

LOG = logging.getLogger("eval.score_against_human")

_YEAR = re.compile(r"(?<!\d)(1[0-9]\d\d|20[0-9]\d)(?!\d)")


def _split(value) -> list[str]:
    return [p.strip() for p in str(value or "").split("|") if p.strip()]


def _is_verifiable(obj: dict) -> bool:
    v = obj.get("is_verifiable_event")
    return v is True or str(v).strip().lower() == "true"


def _fold(s: str) -> str:
    """NFKD, combining marks dropped, casefolded — `Malé` and `Male` converge."""
    decomposed = unicodedata.normalize("NFKD", str(s or ""))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return unicodedata.normalize("NFKC", stripped).casefold()


def _years(values: Iterable[str]) -> set[str]:
    return {m for v in values for m in _YEAR.findall(str(v))}


# ---------------------------------------------------------------------------
# Gold
# ---------------------------------------------------------------------------

class Gold:
    """Human annotations, aggregated to one record per document."""

    def __init__(self, path: Path, include_uncertain: bool = True):
        csv.field_size_limit(10 ** 9)
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.rows = [r for r in rows
                     if str(r.get("annotation_status", "")).strip().lower() == "done"]
        self.skipped_uncertain = 0
        if not include_uncertain:
            keep = [r for r in self.rows
                    if str(r.get("gold_uncertain", "")).strip().upper() != "Y"]
            self.skipped_uncertain = len(self.rows) - len(keep)
            self.rows = keep

        self.has_event: dict[str, bool] = {}
        self.families: dict[str, set[str]] = defaultdict(set)
        self.locations: dict[str, set[str]] = defaultdict(set)
        self.dates: dict[str, set[str]] = defaultdict(set)
        self.strata: dict[str, str] = {}
        for r in self.rows:
            key = r["asset_key"]
            self.strata.setdefault(key, r.get("stratum", ""))
            # A document counts as bearing an event if any annotated row says so.
            self.has_event[key] = self.has_event.get(key, False) or r.get("gold_is_event") == "yes"
            if r.get("gold_is_event") != "yes":
                continue
            self.families[key].update(hazard_family(h) for h in _split(r.get("gold_hazards")))
            self.locations[key].update(l.casefold() for l in _split(r.get("gold_locations")))
            self.dates[key].update(_split(r.get("gold_dates")))

    def totals(self) -> dict[str, int]:
        """Gold items per field over every gold-positive document.

        The denominator for "recall over the whole set": a run that returned
        two thirds of the documents is missing the other third's locations too,
        and dividing only by what it saw hides that.
        """
        keys = [k for k, v in self.has_event.items() if v]
        loc = sum(len(self.locations[k]) for k in keys)
        return {
            "hazard": sum(len(self.families[k]) for k in keys),
            "location": loc,
            "location_fuzzy": loc,
            "location_fuzzy_norm": loc,
            "date": sum(len(self.dates[k]) for k in keys),
            "date_year": sum(len(_years(self.dates[k])) for k in keys),
        }

    @property
    def documents(self) -> list[str]:
        return sorted(self.has_event)

    @property
    def positives(self) -> int:
        return sum(self.has_event.values())

    @property
    def annotated_rows(self) -> int:
        return len(self.rows)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

class Run:
    """One extraction run, indexed by asset_key. JSONL or CSV.

    `errored` holds documents whose every row is an error row — the run
    returned nothing about them, which is not the same as returning "no event".
    """

    def __init__(self, label: str, path: Path):
        self.label = label
        self.path = path
        self.events: dict[str, list[dict]] = defaultdict(list)
        self.docs: set[str] = set()
        self.errors: dict[str, int] = defaultdict(int)
        self.ok_rows: dict[str, int] = defaultdict(int)
        for obj in self._records(path):
            key = obj.get("asset_key")
            if not key:
                continue
            self.docs.add(key)
            if is_error_row(obj):
                self.errors[key] += 1
                continue
            self.ok_rows[key] += 1
            if _is_verifiable(obj):
                self.events[key].append(obj)

    @staticmethod
    def _records(path: Path) -> Iterable[dict]:
        if not path.exists():
            raise FileNotFoundError(f"Run file not found: {path}")
        if path.suffix.lower() == ".csv":
            csv.field_size_limit(10 ** 9)
            with path.open(newline="", encoding="utf-8") as f:
                yield from csv.DictReader(f)
            return
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    @property
    def errored(self) -> set[str]:
        """Documents the run never returned: error rows and no successful row."""
        return {k for k, n in self.errors.items() if n and not self.ok_rows.get(k)}

    def has_event(self, key: str) -> bool:
        return bool(self.events.get(key))

    def families(self, key: str) -> set[str]:
        # Split the compound before folding: an event labelled
        # "Earthquake | Tsunami" covers both families, and `hazard_family` on
        # the whole string would keep only the first. Gold is split the same
        # way, so the two sides are on one scale.
        return {hazard_family(label)
                for e in self.events.get(key, [])
                for label in _split(e.get("event_hazard"))}

    def locations(self, key: str) -> set[str]:
        out: set[str] = set()
        for e in self.events.get(key, []):
            out.update(l.casefold() for l in _split(e.get("affected_locations")))
        return out

    def dates(self, key: str) -> set[str]:
        out: set[str] = set()
        for e in self.events.get(key, []):
            out.update(_split(e.get("event_dates")))
        return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def mcc(tp: int, fp: int, fn: int, tn: int) -> Optional[float]:
    """Matthews correlation over the confusion matrix; None when undefined.

    Undefined — a zero row or column — is the honest answer for a run that
    flagged every document it returned, and reporting 0.0 there would read as
    "no better than chance" rather than "not measurable".
    """
    denom = sqrt(float(tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if denom == 0:
        return None
    return (tp * tn - fp * fn) / denom


def _greedy_pairs(a: set[str], b: set[str], score) -> int:
    """Greedy 1-to-1 matches, best pair first, each string usable once."""
    pairs = []
    for x in a:
        for y in b:
            s = score(x, y)
            if s is not None:
                pairs.append((s, x, y))
    pairs.sort(reverse=True)
    used_a: set[str] = set()
    used_b: set[str] = set()
    matched = 0
    for _s, x, y in pairs:
        if x in used_a or y in used_b:
            continue
        used_a.add(x)
        used_b.add(y)
        matched += 1
    return matched


_RAPIDFUZZ_WARNED = False


def _rapidfuzz():
    global _RAPIDFUZZ_WARNED
    try:
        from rapidfuzz import fuzz, utils
        return fuzz, utils
    except ImportError:
        if not _RAPIDFUZZ_WARNED:
            LOG.warning("rapidfuzz is not installed — fuzzy location columns fall "
                        "back to exact matching and are not meaningful.")
            _RAPIDFUZZ_WARNED = True
        return None, None


def fuzzy_matched(a: set[str], b: set[str], threshold: int = FUZZY_THRESHOLD,
                  normalise: bool = False) -> int:
    """Greedy 1-to-1 matches above `threshold`.

    `normalise=False` is the rule as published: `token_set_ratio` with no
    processor, which tokenises on whitespace without stripping punctuation, so
    "louisville," and "louisville" are different tokens and the pair scores
    66.7. `normalise=True` folds diacritics and hands rapidfuzz its
    `default_process` (lowercase, non-alphanumerics to spaces), which is what
    makes an appended parent qualifier match.
    """
    if not a or not b:
        return 0
    fuzz, utils = _rapidfuzz()
    if fuzz is None:
        return len(a & b)
    if normalise:
        def score(x, y):
            s = fuzz.token_set_ratio(_fold(x), _fold(y), processor=utils.default_process)
            return s if s >= threshold else None
    else:
        def score(x, y):
            s = fuzz.token_set_ratio(x, y)
            return s if s >= threshold else None
    return _greedy_pairs(a, b, score)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value on the discordant pairs (b, c)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def bootstrap_f1(per_doc: dict[str, tuple[int, int, int]],
                 n_boot: int = BOOTSTRAP_N,
                 seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    """95% percentile interval on micro F1, resampling documents.

    The document is the independent unit here — locations within one document
    are not independent draws — so the resample is over documents, carrying
    each one's whole (tp, fp, fn) triple.
    """
    keys = list(per_doc)
    if len(keys) < 2:
        return (0.0, 1.0)
    rng = random.Random(seed)
    triples = [per_doc[k] for k in keys]
    n = len(triples)
    scores = []
    for _ in range(n_boot):
        tp = fp = fn = 0
        for _i in range(n):
            t = triples[rng.randrange(n)]
            tp += t[0]
            fp += t[1]
            fn += t[2]
        scores.append(prf(tp, fp, fn)[2])
    scores.sort()
    lo = scores[int(0.025 * n_boot)]
    hi = scores[min(n_boot - 1, int(0.975 * n_boot))]
    return lo, hi


# Weights for the composite, carried over from `eval/score_against_gold.py`
# (FIELD_WEIGHTS) so the two scorers rank on the same priorities rather than on
# two different opinions. The composite uses the corrected matching rules —
# normalised locations, year-set dates — because a composite built on a metric
# that ranks surface conventions would inherit that.
COMPOSITE_WEIGHTS = (
    ("detection", 1.0),
    ("hazard", 1.5),
    ("location_fuzzy_norm", 1.5),
    ("date_year", 0.5),
)

FIELD_RULES = (
    ("hazard", "Hazard family"),
    ("location", "Locations (exact)"),
    ("location_fuzzy", f"Locations (fuzzy ≥{FUZZY_THRESHOLD}, raw)"),
    ("location_fuzzy_norm", f"Locations (fuzzy ≥{FUZZY_THRESHOLD}, normalised)"),
    ("date", "Dates (exact)"),
    ("date_year", "Dates (year-set)"),
)


def score_run(gold: Gold, run: Run, error_policy: str = "exclude") -> dict:
    errored = run.errored if error_policy == "exclude" else set()
    present = [k for k in gold.documents if k in run.docs]
    docs = [k for k in present if k not in errored]

    det_tp = det_fp = det_fn = det_tn = 0
    correct_flags: dict[str, bool] = {}
    per_doc: dict[str, dict[str, tuple[int, int, int]]] = {
        name: {} for name, _ in FIELD_RULES}

    for key in docs:
        g, r = gold.has_event[key], run.has_event(key)
        correct_flags[key] = (g == r)
        if g and r:
            det_tp += 1
        elif r and not g:
            det_fp += 1
        elif g and not r:
            det_fn += 1
        else:
            det_tn += 1
        if not g:
            continue  # set metrics are defined on documents that carry an event

        gl, rl = gold.locations[key], run.locations(key)
        gd, rd = gold.dates[key], run.dates(key)
        gy, ry = _years(gd), _years(rd)
        exact_sets = {
            "hazard": (gold.families[key], run.families(key)),
            "location": (gl, rl),
            "date": (gd, rd),
            "date_year": (gy, ry),
        }
        for name, (gs, rs) in exact_sets.items():
            tp = len(gs & rs)
            per_doc[name][key] = (tp, len(rs) - tp, len(gs) - tp)
        for name, norm in (("location_fuzzy", False), ("location_fuzzy_norm", True)):
            tp = fuzzy_matched(gl, rl, normalise=norm)
            per_doc[name][key] = (tp, len(rl) - tp, len(gl) - tp)

    n = len(docs)
    n_pos = det_tp + det_fn
    n_neg = det_fp + det_tn
    hits = det_tp + det_tn
    recall = det_tp / n_pos if n_pos else 0.0
    spec = det_tn / n_neg if n_neg else 0.0

    # One combined record per document: hazard, location and date treated as a
    # single content set, each under its own matching rule. This is the joint
    # question — "did the run get this document right?" — which no per-field
    # number answers, because a run can be strong on hazards and weak on dates
    # and each field's F1 hides the other.
    per_doc["combined"] = {
        k: tuple(sum(x) for x in zip(per_doc["hazard"][k],
                                     per_doc["location_fuzzy_norm"][k],
                                     per_doc["date_year"][k]))
        for k in per_doc["hazard"]
    }

    totals = gold.totals()
    totals["combined"] = (totals["hazard"] + totals["location_fuzzy_norm"]
                          + totals["date_year"])
    sets = {}
    for name, _label in FIELD_RULES + (("combined", "All fields"),):
        tp = sum(v[0] for v in per_doc[name].values())
        fp = sum(v[1] for v in per_doc[name].values())
        fn = sum(v[2] for v in per_doc[name].values())
        f1s = [prf(*v)[2] for v in per_doc[name].values() if v[0] + v[2] > 0]
        sets[name] = {
            "tp": tp, "fp": fp, "fn": fn,
            "prf": prf(tp, fp, fn),
            # Recall against every gold item in the set, not only those on
            # documents this run returned.
            "recall_all": tp / totals[name] if totals[name] else 0.0,
            "gold_all": totals[name],
            "macro_f1": sum(f1s) / len(f1s) if f1s else 0.0,
            "macro_n": len(f1s),
            "ci": bootstrap_f1(per_doc[name]),
        }

    combined = per_doc["combined"]
    exact_docs = sum(1 for v in combined.values() if v[1] == 0 and v[2] == 0)
    n_gold_docs = len(combined)

    # Composite over the corrected rules, and the same thing discounted by how
    # much of the set the run actually processed.
    det_f1 = prf(det_tp, det_fp, det_fn)[2]
    parts = {"detection": det_f1, **{k: sets[k]["prf"][2] for k, _w in COMPOSITE_WEIGHTS
                                     if k != "detection"}}
    total_w = sum(w for _k, w in COMPOSITE_WEIGHTS)
    composite = sum(w * parts[k] for k, w in COMPOSITE_WEIGHTS) / total_w if n else 0.0
    coverage = n / len(gold.documents) if gold.documents else 0.0

    return {
        "label": run.label,
        "documents": n,
        "annotated": len(gold.documents),
        "errored": len(run.errored),
        "absent": len(gold.documents) - len(present),
        "coverage": coverage,
        "composite": composite,
        "composite_effective": composite * coverage,
        # Recall over every gold-positive document in the set, not just the ones
        # this run returned: the end-to-end yield.
        "recall_overall": det_tp / gold.positives if gold.positives else 0.0,
        "recall_overall_ci": wilson_interval(det_tp, gold.positives),
        "detection": {
            "tp": det_tp, "fp": det_fp, "fn": det_fn, "tn": det_tn,
            "n_pos": n_pos, "n_neg": n_neg,
            "accuracy": hits / n if n else 0.0,
            "acc_ci": wilson_interval(hits, n),
            "rate": format_rate(hits, n),
            "recall": recall, "recall_ci": wilson_interval(det_tp, n_pos),
            "specificity": spec, "spec_ci": wilson_interval(det_tn, n_neg),
            "balanced": (recall + spec) / 2 if n_pos and n_neg else None,
            "mcc": mcc(det_tp, det_fp, det_fn, det_tn),
            "prf": prf(det_tp, det_fp, det_fn),
        },
        "sets": sets,
        "exact_docs": exact_docs,
        "n_gold_docs": n_gold_docs,
        "exact_rate": exact_docs / n_gold_docs if n_gold_docs else 0.0,
        "exact_ci": wilson_interval(exact_docs, n_gold_docs),
        "exact_rate_all": exact_docs / gold.positives if gold.positives else 0.0,
        "correct_flags": correct_flags,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x:.1%}"


def _ci(bounds: tuple[float, float]) -> str:
    return f"{bounds[0]:.1%}–{bounds[1]:.1%}"


def _opt(x: Optional[float]) -> str:
    return "–" if x is None else f"{x:.3f}"


def _display(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def render(gold: Gold, results: list[dict], ann_path: Path, error_policy: str) -> str:
    n_docs = len(gold.documents)
    out: list[str] = ["# Extraction runs scored against human annotations", ""]
    out.append(f"Annotations: `{_display(ann_path)}` — "
               f"{gold.annotated_rows} annotated rows over {n_docs} documents, "
               f"{gold.positives} of which carry a verifiable event "
               f"({gold.positives / n_docs:.1%} prevalence).")
    if gold.skipped_uncertain:
        out.append(f"\n{gold.skipped_uncertain} rows flagged uncertain were excluded "
                   "(`--exclude-uncertain`).")
    out += ["",
            "All metrics are per document; see the module docstring for why. "
            f"Error policy: **{error_policy}** — documents a run returned only "
            "error rows for are "
            + ("excluded from its denominator and reported as coverage below."
               if error_policy == "exclude"
               else "scored as 'found no event'."),
            ""]

    out += ["## 1. Documents processed, and the score relative to them", "",
            "A run cannot be credited or blamed for a document it never got "
            "back, so every score in this report is computed over the documents "
            "that run actually returned. This table says how many that was, and "
            "then gives the two readings of its score side by side.", "",
            "**On what it processed** is the model comparison: quality per "
            "document returned, which is the only basis on which runs with "
            "different failure rates can be ranked against each other. "
            "**Over the whole set** is the pipeline reading: the same quality "
            "discounted by coverage, which is what you would actually get from "
            "this run over all "
            f"{n_docs} documents. They differ only where a run failed calls.", "",
            "The composite is a weighted mean of detection F1, hazard F1, "
            "location F1 and date F1 (weights 1.0 / 1.5 / 1.5 / 0.5, carried "
            "over from `eval/score_against_gold.py` so the two scorers rank on "
            "the same priorities), computed on the corrected matching rules.", "",
            "| Run | Processed | Coverage | Recall (all docs) | Composite × coverage | Recall (processed) | Composite (processed) | Errored | Absent |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        if not r["documents"]:
            out.append(f"| {r['label']} | 0/{r['annotated']} | 0.0% | "
                       f"0.0% | 0.0% | – | – | {r['errored']} | {r['absent']} |")
            continue
        d = r["detection"]
        out.append(f"| {r['label']} | {r['documents']}/{r['annotated']} | "
                   f"{_pct(r['coverage'])} | "
                   f"{_pct(r['recall_overall'])} | "
                   f"{_pct(r['composite_effective'])} | "
                   f"{_pct(d['recall'])} | {_pct(r['composite'])} | "
                   f"{r['errored']} | {r['absent']} |")
    out += ["",
            "_`Recall (processed)` is over the gold-positive documents the run "
            "returned; `Recall (all docs)` is over all "
            f"{gold.positives} gold-positive documents in the set, so the gap "
            "between the two columns is exactly what the run's failed calls "
            "cost. A run at 100% coverage has identical pairs._"]
    dead = [r for r in results if r["documents"] == 0]
    if dead:
        out += ["", "> **" + ", ".join(r["label"] for r in dead) + "** returned "
                "nothing on every annotated document. No score in this report is "
                "a statement about these models — the zeroes in the right-hand "
                "columns are the pipeline's, not the model's."]

    out += ["", "## 2. Event detection", "",
            "`Recall, all docs` divides by every gold-positive document in the "
            "set; `Recall, processed` divides by the ones this run returned. "
            "They are equal at full coverage and differ by exactly the run's "
            "failure rate otherwise. `Specificity` is over the gold-negative "
            "documents returned. Accuracy is shown for "
            "continuity but is dominated by the "
            f"{gold.positives / n_docs:.0%} prevalence of this set — "
            "balanced accuracy and MCC are the ones to rank on.", "",
            "| Run | n | Recall, all docs (95% CI) | Recall, processed (95% CI) | Specificity (95% CI) | Balanced acc. | MCC | Accuracy (95% CI) |",
            "|---|---:|---|---|---|---:|---:|---|"]
    for r in results:
        d = r["detection"]
        if not r["documents"]:
            out.append(f"| {r['label']} | 0 | 0.0% (n={gold.positives}) | – | – | – | – | – |")
            continue
        bal = "–" if d["balanced"] is None else _pct(d["balanced"])
        out.append(
            f"| {r['label']} | {r['documents']} | "
            f"{_pct(r['recall_overall'])} ({_ci(r['recall_overall_ci'])}, "
            f"n={gold.positives}) | "
            f"{_pct(d['recall'])} ({_ci(d['recall_ci'])}, n={d['n_pos']}) | "
            f"{_pct(d['specificity'])} ({_ci(d['spec_ci'])}, n={d['n_neg']}) | "
            f"{bal} | {_opt(d['mcc'])} | "
            f"{_pct(d['accuracy'])} ({_ci(d['acc_ci'])}) |")

    out += ["", "### Confusion matrices", "",
            "| Run | TP | FP | FN | TN | Precision | F1 |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        if not r["documents"]:
            out.append(f"| {r['label']} | – | – | – | – | – | – |")
            continue
        d = r["detection"]
        p, _rc, f1 = d["prf"]
        out.append(f"| {r['label']} | {d['tp']} | {d['fp']} | {d['fn']} | {d['tn']} | "
                   f"{_pct(p)} | {_pct(f1)} |")
    out += ["",
            "_Precision is reported for continuity only. With "
            f"{n_docs - gold.positives} gold-negative documents in the set it is "
            "pinned near the prevalence for any run that flags most documents, "
            "and it separates nothing._"]

    out += ["", "## 3. Field extraction, on documents gold says carry an event", "",
            "`Recall (all)` divides by every gold item in the set — including "
            "those on documents the run never returned — so it is comparable "
            "across runs with different coverage. `Recall (processed)` divides "
            "only by the documents the run returned, and is the recall the "
            "F1 column uses. "
            "Micro F1 pools TP/FP/FN over documents; macro F1 averages "
            "per-document F1 so a one-location document counts as much as a "
            "thirty-location one. The interval is a 95% percentile bootstrap "
            f"over {BOOTSTRAP_N:,} document-level resamples (seed {BOOTSTRAP_SEED}); "
            "overlapping intervals mean the difference is not resolvable at this "
            "sample size.", "",
            "| Run | Field | Precision | Recall (all) | Recall (processed) | Micro F1 (95% CI) | Macro F1 | TP | FP | FN |",
            "|---|---|---:|---:|---:|---|---:|---:|---:|---:|"]
    for r in results:
        if not r["documents"]:
            continue
        for name, label in FIELD_RULES:
            s = r["sets"][name]
            p, rc, f1 = s["prf"]
            out.append(f"| {r['label']} | {label} | {_pct(p)} | "
                       f"{_pct(s['recall_all'])} | {_pct(rc)} | "
                       f"{_pct(f1)} ({_ci(s['ci'])}) | {_pct(s['macro_f1'])} | "
                       f"{s['tp']} | {s['fp']} | {s['fn']} |")

    out += ["", "## 4. All fields together, per document", "",
            "Hazard, location and date treated as one content set per document, "
            "each field under its own corrected rule (hazard family; locations "
            f"fuzzy ≥{FUZZY_THRESHOLD} normalised; dates year-set). This is the "
            "joint question — did the run get this document right? — which no "
            "single-field row answers, because a run can be strong on hazards "
            "and weak on dates and each field's F1 hides the other.", "",
            "`Exact match` is the share of gold-positive documents where the run "
            "produced every gold item and nothing else: no false positive and no "
            "false negative across all three fields. It is the strictest reading "
            "here and the one closest to \"a reviewer would have accepted this "
            "row unedited\".", "",
            "| Run | Docs | Exact match (95% CI) | Precision | Recall | F1 (95% CI) | Macro F1 | Recall (all docs) | Exact match (all docs) |",
            "|---|---:|---|---:|---:|---|---:|---:|---:|"]
    ranked = sorted((r for r in results if r["documents"]),
                    key=lambda r: -r["sets"]["combined"]["prf"][2])
    for r in ranked:
        c = r["sets"]["combined"]
        p, rc, f1 = c["prf"]
        out.append(f"| {r['label']} | {r['n_gold_docs']} | "
                   f"{_pct(r['exact_rate'])} ({_ci(r['exact_ci'])}) | "
                   f"{_pct(p)} | {_pct(rc)} | {_pct(f1)} ({_ci(c['ci'])}) | "
                   f"{_pct(c['macro_f1'])} | {_pct(c['recall_all'])} | "
                   f"{_pct(r['exact_rate_all'])} |")
    for r in results:
        if not r["documents"]:
            out.append(f"| {r['label']} | 0 | – | – | – | – | – | 0.0% | 0.0% |")
    out += ["",
            "_Sorted by F1. `Docs` is the gold-positive documents the run "
            "returned; the two right-hand columns divide by all "
            f"{gold.positives} instead, so they read as pipeline yield. "
            "Precision, macro F1 and the intervals have no all-documents form — "
            "a document the run never returned supplies neither a numerator nor "
            "a denominator._"]

    out += ["", "## 5. What the matching rule costs", "",
            "The same run under different matching rules. A gap here is a "
            "property of the metric, not of the model — and where it is larger "
            "than the gap between two models, the metric is what is being "
            "ranked.", "",
            "| Run | Loc exact | Loc fuzzy raw | Loc fuzzy normalised | Δ norm−exact | Date exact | Date year-set | Δ year−exact |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        if not r["documents"]:
            continue
        le = r["sets"]["location"]["prf"][2]
        lf = r["sets"]["location_fuzzy"]["prf"][2]
        ln = r["sets"]["location_fuzzy_norm"]["prf"][2]
        de = r["sets"]["date"]["prf"][2]
        dy = r["sets"]["date_year"]["prf"][2]
        out.append(f"| {r['label']} | {_pct(le)} | {_pct(lf)} | {_pct(ln)} | "
                   f"+{(ln - le) * 100:.1f} pp | {_pct(de)} | {_pct(dy)} | "
                   f"+{(dy - de) * 100:.1f} pp |")

    scored = [r for r in results if r["documents"]]
    if len(scored) >= 2:
        out += ["", "## 6. Paired comparison — exact McNemar on event detection", "",
                "Paired over the documents **both** runs returned, so a run is "
                "never charged for the other's failed calls. `n` is that "
                "intersection.", "",
                "| A | B | n | A only | B only | p |", "|---|---|---:|---:|---:|---:|"]
        for i in range(len(scored)):
            for j in range(i + 1, len(scored)):
                a, b = scored[i], scored[j]
                shared = set(a["correct_flags"]) & set(b["correct_flags"])
                only_a = sum(1 for k in shared
                             if a["correct_flags"][k] and not b["correct_flags"][k])
                only_b = sum(1 for k in shared
                             if b["correct_flags"][k] and not a["correct_flags"][k])
                p = mcnemar_exact(only_a, only_b)
                shown = f"**{p:.4f}**" if p < 0.05 else f"{p:.4f}"
                out.append(f"| {a['label']} | {b['label']} | {len(shared)} | "
                           f"{only_a} | {only_b} | {shown} |")
        out += ["",
                "_'A only' counts documents A got right and B got wrong. p is "
                "two-sided; the concordant pairs carry no information. Bold "
                "marks p < 0.05, uncorrected for multiple comparisons — with "
                f"{len(scored) * (len(scored) - 1) // 2} pairs, expect some by chance._"]

    absent = [r for r in results if r["absent"] or r["errored"]]
    if absent:
        out += ["", "## 7. Coverage gaps in detail", ""]
        for r in absent:
            bits = []
            if r["errored"]:
                bits.append(f"{r['errored']} returned only error rows")
            if r["absent"]:
                bits.append(f"{r['absent']} absent from the output")
            out.append(f"- **{r['label']}**: " + "; ".join(bits) +
                       (" — excluded from its denominator."
                        if error_policy == "exclude" and r["errored"]
                        else "."))
    out.append("")
    return "\n".join(out)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", action="append", default=[], metavar="[LABEL=]PATH",
                   help="an extraction run to score; repeatable")
    p.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--exclude-uncertain", action="store_true",
                   help="drop rows the annotator flagged with 🚩")
    p.add_argument("--error-policy", choices=("exclude", "count-as-miss"),
                   default="exclude",
                   help="what to do with documents a run returned only error "
                        "rows for (default: exclude from its denominator)")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()
    if not args.run:
        LOG.error("Nothing to score. Pass at least one --run [LABEL=]PATH.")
        return 2
    if not args.annotations.exists():
        LOG.error("No annotations at %s. Run `make annotate` first.", args.annotations)
        return 2

    gold = Gold(args.annotations, include_uncertain=not args.exclude_uncertain)
    if not gold.rows:
        LOG.error("No rows in %s have annotation_status == done.", args.annotations)
        return 2

    results = []
    for spec in args.run:
        label, sep, raw = spec.partition("=")
        path = Path(raw if sep else spec).expanduser()
        run = Run(label.strip() if sep else path.stem, path)
        if run.errored:
            LOG.info("%s: %d/%d documents returned only error rows.",
                     run.label, len(run.errored), len(run.docs))
        results.append(score_run(gold, run, error_policy=args.error_policy))

    report = render(gold, results, args.annotations.resolve(), args.error_policy)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    LOG.info("Wrote %s", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
