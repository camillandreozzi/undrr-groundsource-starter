"""Per-stratum scores, and design-weighted corpus-level estimates, for every model.

    python -m benchmark_openrouter.stratified_scores

WHY THIS EXISTS
---------------
`benchmark_openrouter/MODEL_SCORES_POOLED_217.md` reports one number per model
over the pooled 217 documents. That pool is a mixture of two samples with
different inclusion probabilities, so every prevalence-dependent number in it
(accuracy, precision, MCC) describes a population that does not exist —
`pool_arms.py` says so in its own docstring. This module answers the two
questions that pooling cannot.

**1. Per stratum, separately.** The 167 are documents the production GPT-5 run
flagged; the 50 are a uniform draw over the corpus, and 39 of them are documents
that run declined. Splitting detection and field scores by stratum shows
directly whether a model that looks strong overall is strong only on the
pre-filtered easy half — or, more interestingly, whether any model recovers
events on the documents GPT-5 missed.

**2. Weighted up to the corpus.** Each document stands in for a known number of
corpus documents. Weighting by the inverse of its sampling rate turns a score on
217 documents into an estimate for all 10,000, which is the number that answers
"what would this model do on the corpus" rather than "what did it do on our
deliberately enriched sample".

THE TWO WEIGHTING SCHEMES
-------------------------
*arm* (the headline, as commissioned): strata are the two sampling arms.

    event-sample arm      1,913 / 167  =  11.46 per document
    document-sample arm   8,087 /  50  = 161.74 per document

*flag* (the sensitivity check): the arms are not quite the strata. The 50 were
drawn uniformly over the 9,833 documents not already annotated, so 11 of them
are documents the production run *did* flag — event-stratum documents carrying a
remaining-stratum weight of 161.74. Post-stratifying on what the production run
actually did fixes that:

    production flagged     1,913 / 178  =  10.75 per document
    production declined    8,087 /  39  = 207.36 per document

Both partition the corpus exactly (they sum to 10,000), and both are reported in
full. **The *flag* scheme is the better estimator**, and the gap between them is
not cosmetic: all 11 of the misplaced documents are gold-positive, so the *arm*
scheme weights 11 true positives at 161.74 apiece and estimates 4,063
event-bearing documents in the corpus — a 40.6% prevalence, against a corpus
base rate independently put at 19-28%. The *flag* scheme estimates 2,428, or
24.3%, which is inside that range. Detection precision moves by up to 19 points
between the two.

The *arm* scheme is kept as the headline because it is the commissioned design
and because its per-stratum halves (§1, §2) are exactly the published per-arm
reports. Quote §4 for any corpus-level claim.

WHAT IS ESTIMATED, AND HOW
--------------------------
Detection is a per-document classification, so each document contributes its
weight to one confusion-matrix cell:

    precision = Σw·TP / Σw·(TP+FP)      recall = Σw·TP / Σw·(TP+FN)

Fields are per-document (tp, fp, fn) triples under the corrected matching rules
(hazard family; locations fuzzy ≥90 normalised; dates year-set), and the weight
multiplies the whole triple — micro-pooling with a weight, so a document that
stands in for 162 corpus documents counts 162 times over.

Coverage is handled by ratio adjustment: within each stratum the weight is
`N_stratum / n_returned_in_that_stratum`, not `N_stratum / n_sampled`. A run
that failed 18 calls in the 50-arm has its surviving documents in that stratum
weighted up to cover the whole stratum, which is the right correction as long as
the failures are unrelated to content — they are transport errors, so they are.
The two weight columns above are the full-coverage case.

Intervals are a stratified percentile bootstrap: documents are resampled within
stratum, the weights are recomputed on each resample, and the 2.5/97.5
percentiles of 2,000 replicates are reported. Resampling within stratum is what
keeps the design in the interval; a naive bootstrap over 217 documents would
also resample the stratum sizes, which are fixed by design and not random.

READ THIS BEFORE QUOTING A WEIGHTED NUMBER
------------------------------------------
The weighted recall rests on 171 gold-positive documents, but 157 of them carry
a weight of 11.46 and only 14 carry 161.74 — so the corpus-level recall is
dominated by 14 documents, and its interval is correspondingly wide. That width
is not a defect of the estimator; it is the sample size the design bought for
the question. The point estimate is unbiased. It is not precise.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_openrouter.agreement import REFERENCE_RUNS, discover_runs  # noqa: E402
from eval.score_against_human import (  # noqa: E402
    Gold, Run, _years, fuzzy_matched, prf,
)

LOG = logging.getLogger("benchmark_openrouter.stratified_scores")

DEFAULT_ANNOTATIONS = REPO_ROOT / "eval" / "human_annotations_pooled.csv"
DEFAULT_RUNS_DIR = REPO_ROOT / "benchmark_openrouter" / "outputs_pooled"
DEFAULT_OUT = REPO_ROOT / "benchmark_openrouter" / "STRATIFIED_AND_WEIGHTED_SCORES.md"
PRODUCTION_RUN = REPO_ROOT / "outputs" / "event_extractions" / "event_extractions.jsonl"

CORPUS_N = 10_000
EVENT_STRATUM_N = 1_913
REMAINING_STRATUM_N = CORPUS_N - EVENT_STRATUM_N  # 8,087

BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 42

# The corrected rules only. The exact-string variants are a property of the
# matching convention, not of the model, and MODEL_SCORES_POOLED_217.md §5
# already prices them; carrying six field rules through two stratifications and
# two weighting schemes would bury the finding in columns.
FIELDS = (
    ("hazard", "Hazard family"),
    ("location_fuzzy_norm", "Locations"),
    ("date_year", "Dates"),
    ("combined", "All fields"),
)

ARM_LABELS = {
    "event_sample_167": "Event stratum (GPT-5 flagged)",
    "document_sample_50": "Remaining stratum (random draw)",
}
FLAG_LABELS = {
    "flagged": "Production flagged",
    "declined": "Production declined",
}


# ---------------------------------------------------------------------------
# Strata
# ---------------------------------------------------------------------------

def production_flagged(path: Path, keys: set[str]) -> set[str]:
    """Documents the production GPT-5 run returned at least one verifiable event for."""
    if not path.exists():
        raise FileNotFoundError(
            f"Production run not found: {path}\n"
            "The flag-based stratification needs it to say which documents GPT-5 missed."
        )
    flagged: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            key = obj.get("asset_key")
            if key not in keys:
                continue
            v = obj.get("is_verifiable_event")
            if v is True or str(v).strip().lower() == "true":
                flagged.add(key)
    return flagged


def build_strata(ann_path: Path, keys: set[str]) -> dict[str, dict]:
    """Two partitions of the 217, each with its stratum population size.

    Returned as {scheme: {"of": {key: stratum}, "N": {stratum: corpus count},
    "order": [...], "labels": {...}}}.
    """
    csv.field_size_limit(10 ** 9)
    with ann_path.open(newline="", encoding="utf-8") as f:
        arm_of = {r["asset_key"]: r["sample_arm"] for r in csv.DictReader(f)
                  if r["asset_key"] in keys}

    flagged = production_flagged(PRODUCTION_RUN, keys)
    flag_of = {k: ("flagged" if k in flagged else "declined") for k in keys}

    return {
        "arm": {
            "of": arm_of,
            "N": {"event_sample_167": EVENT_STRATUM_N,
                  "document_sample_50": REMAINING_STRATUM_N},
            "order": ["event_sample_167", "document_sample_50"],
            "labels": ARM_LABELS,
        },
        "flag": {
            "of": flag_of,
            "N": {"flagged": EVENT_STRATUM_N, "declined": REMAINING_STRATUM_N},
            "order": ["flagged", "declined"],
            "labels": FLAG_LABELS,
        },
    }


# ---------------------------------------------------------------------------
# Per-document scoring — one pass, reused by every table below
# ---------------------------------------------------------------------------

def per_document(gold: Gold, run: Run) -> tuple[dict[str, str], dict[str, dict]]:
    """(detection cell per document, field triples per document).

    Documents the run returned only error rows for are absent from both, which
    is `score_against_human.py`'s `--error-policy exclude` applied per stratum.
    """
    errored = run.errored
    docs = [k for k in gold.documents if k in run.docs and k not in errored]

    cells: dict[str, str] = {}
    triples: dict[str, dict[str, tuple[int, int, int]]] = defaultdict(dict)

    for key in docs:
        g, r = gold.has_event[key], run.has_event(key)
        cells[key] = "tp" if (g and r) else "fp" if r else "fn" if g else "tn"
        if not g:
            continue  # set metrics are defined on documents that carry an event

        gl, rl = gold.locations[key], run.locations(key)
        gy, ry = _years(gold.dates[key]), _years(run.dates(key))
        gh, rh = gold.families[key], run.families(key)

        for name, (gs, rs) in (("hazard", (gh, rh)), ("date_year", (gy, ry))):
            tp = len(gs & rs)
            triples[name][key] = (tp, len(rs) - tp, len(gs) - tp)
        tp = fuzzy_matched(gl, rl, normalise=True)
        triples["location_fuzzy_norm"][key] = (tp, len(rl) - tp, len(gl) - tp)
        triples["combined"][key] = tuple(
            sum(x) for x in zip(triples["hazard"][key],
                                triples["location_fuzzy_norm"][key],
                                triples["date_year"][key]))

    return cells, triples


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def detection_counts(cells: dict[str, str], keys, weight=None) -> dict:
    """Weighted confusion matrix over `keys`; weight=None is the unweighted count."""
    w = weight or (lambda _k: 1.0)
    c = {"tp": 0.0, "fp": 0.0, "fn": 0.0, "tn": 0.0}
    for k in keys:
        if k in cells:
            c[cells[k]] += w(k)
    p, r, f = prf(c["tp"], c["fp"], c["fn"])
    n_neg = c["fp"] + c["tn"]
    return {**c, "precision": p, "recall": r, "f1": f,
            "specificity": c["tn"] / n_neg if n_neg else None,
            "n": sum(1 for k in keys if k in cells)}


def field_counts(triples: dict[str, tuple], keys, weight=None) -> dict:
    w = weight or (lambda _k: 1.0)
    tp = fp = fn = 0.0
    n = 0
    for k in keys:
        t = triples.get(k)
        if t is None:
            continue
        n += 1
        tp += w(k) * t[0]
        fp += w(k) * t[1]
        fn += w(k) * t[2]
    p, r, f = prf(tp, fp, fn)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r,
            "f1": f, "n": n}


def stratum_weights(scheme: dict, present: set[str]) -> dict[str, float]:
    """N_stratum / n_returned_in_stratum — the ratio adjustment for coverage.

    A run that lost 18 documents in a stratum still has to account for that
    whole stratum, so its survivors are weighted up. With full coverage this is
    exactly the commissioned 1913/167 and 8087/50.
    """
    returned: dict[str, int] = defaultdict(int)
    for k in present:
        returned[scheme["of"][k]] += 1
    return {s: (scheme["N"][s] / returned[s] if returned.get(s) else 0.0)
            for s in scheme["order"]}


def weighted_estimates(cells, triples, scheme) -> dict:
    present = set(cells)
    w_of = stratum_weights(scheme, present)

    def weight(k: str) -> float:
        return w_of[scheme["of"][k]]

    out = {"weights": w_of,
           "detection": detection_counts(cells, present, weight)}
    for name, _label in FIELDS:
        out[name] = field_counts(triples[name], set(triples[name]), weight)
    return out


# ---------------------------------------------------------------------------
# Stratified bootstrap
# ---------------------------------------------------------------------------

def bootstrap(cells, triples, scheme, n_boot=BOOTSTRAP_N, seed=BOOTSTRAP_SEED) -> dict:
    """95% percentile intervals, resampling documents within stratum.

    The stratum sizes are fixed by the design, so they are not resampled; only
    which documents landed in each stratum is. Weights are recomputed on every
    replicate, which is what makes the interval an interval on the estimator
    rather than on a fixed-weight approximation of it.
    """
    present = sorted(cells)
    by_stratum: dict[str, list[str]] = defaultdict(list)
    for k in present:
        by_stratum[scheme["of"][k]].append(k)
    if any(len(v) < 2 for v in by_stratum.values()) or len(by_stratum) < 2:
        return {}

    rng = random.Random(seed)
    metrics = ["det_precision", "det_recall"] + [
        f"{name}_{m}" for name, _l in FIELDS for m in ("precision", "recall")]
    draws: dict[str, list[float]] = {m: [] for m in metrics}

    for _ in range(n_boot):
        resample: list[str] = []
        w_of: dict[str, float] = {}
        for s, ks in by_stratum.items():
            picked = [ks[rng.randrange(len(ks))] for _ in range(len(ks))]
            resample += picked
            w_of[s] = scheme["N"][s] / len(picked)

        def weight(k, _w=w_of):
            return _w[scheme["of"][k]]

        det = detection_counts(cells, resample, weight)
        draws["det_precision"].append(det["precision"])
        draws["det_recall"].append(det["recall"])
        for name, _l in FIELDS:
            keys = [k for k in resample if k in triples[name]]
            fc = field_counts(triples[name], keys, weight)
            draws[f"{name}_precision"].append(fc["precision"])
            draws[f"{name}_recall"].append(fc["recall"])

    out = {}
    for m, vals in draws.items():
        vals.sort()
        out[m] = (vals[int(0.025 * n_boot)],
                  vals[min(n_boot - 1, int(0.975 * n_boot))])
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _pct(x) -> str:
    return "–" if x is None else f"{x:.1%}"


def _ci(b) -> str:
    return "" if not b else f" ({b[0]:.1%}–{b[1]:.1%})"


def _n(x: float) -> str:
    return f"{x:,.0f}"


def _weighted_tables(A, results, scheme: str, det_no: str, field_no: str) -> None:
    """The detection and field tables for one weighting scheme.

    Both schemes get the identical treatment so the two can be read against each
    other line for line; only the weights behind them differ.
    """
    A(f"### {det_no}. Detection")
    A("")
    A("| Run | Weighted precision (95% CI) | Weighted recall (95% CI) | F1 | "
      "Est. events flagged in corpus | Est. event-bearing documents |")
    A("|---|---|---|---:|---:|---:|")
    for res in results:
        w = res["weighted"][scheme]
        if not w:
            A(f"| {res['label']} | – | – | – | – | – |")
            continue
        d = w["detection"]
        b = res["boot"][scheme]
        A(f"| {res['label']} | {_pct(d['precision'])}{_ci(b.get('det_precision'))} | "
          f"{_pct(d['recall'])}{_ci(b.get('det_recall'))} | {_pct(d['f1'])} | "
          f"{_n(d['tp'] + d['fp'])} | {_n(d['tp'] + d['fn'])} |")
    A("")
    A("_`Est. events flagged in corpus` is how many of the 10,000 documents this "
      "run would call event-bearing; `Est. event-bearing documents` is how many "
      "gold says actually are, which is a property of the design rather than of "
      "the run and varies between runs only through coverage._")
    A("")

    A(f"### {field_no}. Fields")
    A("")
    A("| Run | Field | Weighted precision (95% CI) | Weighted recall (95% CI) | F1 |")
    A("|---|---|---|---|---:|")
    for res in results:
        w = res["weighted"][scheme]
        if not w:
            continue
        b = res["boot"][scheme]
        for name, label in FIELDS:
            f = w[name]
            A(f"| {res['label']} | {label} | "
              f"{_pct(f['precision'])}{_ci(b.get(f'{name}_precision'))} | "
              f"{_pct(f['recall'])}{_ci(b.get(f'{name}_recall'))} | {_pct(f['f1'])} |")
    A("")


def render(results: list[dict], strata: dict, gold: Gold, ann_path: Path) -> str:
    arm = strata["arm"]
    counts = defaultdict(lambda: [0, 0])
    for k in gold.documents:
        s = arm["of"][k]
        counts[s][0] += 1
        counts[s][1] += 1 if gold.has_event[k] else 0

    L: list[str] = []
    A = L.append
    A("# Per-stratum scores and corpus-weighted estimates")
    A("")
    A(f"Annotations: `{ann_path.relative_to(REPO_ROOT)}` — "
      f"{len(gold.documents)} documents over two sampling arms. "
      "Every score here uses the corrected matching rules (hazard family; "
      "locations fuzzy ≥90 normalised; dates year-set) and the **exclude** error "
      "policy: a document a run returned only error rows for is dropped from that "
      "run's denominator in the stratum it belongs to.")
    A("")
    A("| Stratum | Sampled | Gold-positive | Prevalence | Corpus documents | Weight |")
    A("|---|---:|---:|---:|---:|---:|")
    for s in arm["order"]:
        n, pos = counts[s]
        A(f"| {arm['labels'][s]} | {n} | {pos} | {pos / n:.1%} | "
          f"{arm['N'][s]:,} | {arm['N'][s] / n:.2f} |")
    A(f"| **Corpus** | **{len(gold.documents)}** | | | **{CORPUS_N:,}** | |")
    A("")
    A("_The event stratum is the 1,913 documents the production GPT-5 run flagged; "
      "the remaining stratum is the 8,087 it declined. The 94.0% / 28.0% prevalence "
      "split is the whole reason a pooled number is hard to read: the pool's 78.8% "
      "is an artefact of the mixture and describes no real population._")
    A("")

    # ---------------- Table 1a — detection per stratum ----------------
    A("## 1. Detection, per stratum")
    A("")
    A("The question this answers: does a model that looks strong overall stay "
      "strong on the documents GPT-5 declined? Recall in the remaining stratum "
      "is exactly \"of the events GPT-5 missed, how many did this model find\". "
      "Specificity is only estimable in the remaining stratum — the event "
      "stratum's 10 gold-negatives are the production run's own false positives, "
      "an adversarial set, not an ordinary one.")
    A("")
    header = ["Run"]
    for s in arm["order"]:
        tag = "event" if s == "event_sample_167" else "remaining"
        header += [f"n ({tag})", f"Recall ({tag})", f"Prec. ({tag})", f"Spec. ({tag})"]
    A("| " + " | ".join(header) + " |")
    A("|---|" + "---:|" * (len(header) - 1))
    for res in results:
        row = [res["label"]]
        for s in arm["order"]:
            d = res["by_arm"][s]["detection"]
            if not d["n"]:
                row += ["0", "–", "–", "–"]
                continue
            row += [str(d["n"]), _pct(d["recall"]), _pct(d["precision"]),
                    _pct(d["specificity"])]
        A("| " + " | ".join(row) + " |")
    A("")
    A("_`n` is the documents that run returned in that stratum. Recall divides by "
      "the gold-positive documents among them — 157 at most in the event stratum, "
      "**14 at most in the remaining stratum**, so a single document moves the "
      "right-hand recall by about 7 points and small differences there are noise._")
    A("")

    A("### Detection confusion matrices, per stratum")
    A("")
    A("| Run | Stratum | TP | FP | FN | TN | Precision | Recall | F1 |")
    A("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for res in results:
        for s in arm["order"]:
            d = res["by_arm"][s]["detection"]
            if not d["n"]:
                continue
            A(f"| {res['label']} | {arm['labels'][s]} | {d['tp']:.0f} | {d['fp']:.0f} | "
              f"{d['fn']:.0f} | {d['tn']:.0f} | {_pct(d['precision'])} | "
              f"{_pct(d['recall'])} | {_pct(d['f1'])} |")
    A("")

    # ---------------- Table 1b — fields per stratum ----------------
    A("## 2. Field extraction, per stratum")
    A("")
    A("Micro P/R/F1 over the gold-positive documents in each stratum, pooling "
      "TP/FP/FN across documents. This is conditional on the document carrying "
      "an event, so unlike detection it is not distorted by the prevalence gap — "
      "but the remaining stratum still rests on at most 14 documents per run.")
    A("")
    for name, label in FIELDS:
        A(f"### {label}")
        A("")
        A("| Run | n (event) | P (event) | R (event) | F1 (event) | "
          "n (remaining) | P (remaining) | R (remaining) | F1 (remaining) | Δ F1 |")
        A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for res in results:
            e = res["by_arm"]["event_sample_167"][name]
            r = res["by_arm"]["document_sample_50"][name]
            delta = (f"{(r['f1'] - e['f1']) * 100:+.1f} pp"
                     if e["n"] and r["n"] else "–")
            A(f"| {res['label']} | {e['n']} | {_pct(e['precision']) if e['n'] else '–'} | "
              f"{_pct(e['recall']) if e['n'] else '–'} | {_pct(e['f1']) if e['n'] else '–'} | "
              f"{r['n']} | {_pct(r['precision']) if r['n'] else '–'} | "
              f"{_pct(r['recall']) if r['n'] else '–'} | {_pct(r['f1']) if r['n'] else '–'} | "
              f"{delta} |")
        A("")
    A("_`Δ F1` is remaining minus event: negative means the model describes the "
      "documents GPT-5 missed worse than the ones it found. A large negative gap "
      "on a model with high pooled scores means the pooled score is carried by the "
      "enriched arm._")
    A("")

    # ---------------- Table 2 — weighted corpus estimates ----------------
    A("## 3. Corpus-weighted estimates (10,000 documents)")
    A("")
    A("Every document is weighted by the inverse of its sampling rate, so the "
      "217-document sample estimates the corpus. Weights are ratio-adjusted for "
      "coverage: a run that lost documents in a stratum has its survivors there "
      "weighted up to cover the whole stratum. Intervals are a 95% percentile "
      "stratified bootstrap (2,000 replicates, seed 42, resampled within stratum "
      "with the weights recomputed each time).")
    A("")
    A("> **These are the commissioned weights, and they are biased.** The arm is "
      "not the stratum: 11 of the 50 are documents the production run flagged, "
      "all 11 are gold-positive, and weighting them at 161.74 instead of 11.46 "
      "pushes the implied corpus prevalence to 40.6% against a base rate "
      "independently put at 19-28%. **§4 repeats every table below under the "
      "corrected weights and is the one to quote.**")
    A("")
    _weighted_tables(A, results, "arm", "3a", "3b")
    A("")

    # ---------------- Sensitivity ----------------
    A("## 4. The same estimates under the corrected weights")
    A("")
    A("The 50 were drawn uniformly over the 9,833 documents not already "
      "annotated, not over the 8,087 the production run declined. Eleven of them "
      "are documents GPT-5 *did* flag — and all eleven carry an event by gold. "
      "§3 gives those 11 true positives a remaining-stratum weight of 161.74 when "
      "they belong to a stratum whose weight is 11.46, which inflates every "
      "weighted true-positive count.")
    A("")
    A("Post-stratifying on what the production run actually did puts each of the "
      "217 in its true stratum — 178 flagged at 10.75, 39 declined at 207.36. "
      "This is the ratio-adjusted Horvitz-Thompson estimator for the design as "
      "executed: a flagged document could enter either arm, giving it inclusion "
      "probability 167/1913 + (1746/1913)(50/9833) = 0.0919 and a weight of "
      "10.88, which the ratio adjustment normalises to 10.75 so the stratum sums "
      "to exactly 1,913.")
    A("")
    A("| Estimator | Weights (flagged / declined) | Est. event-bearing documents "
      "| Implied corpus prevalence |")
    A("|---|---|---:|---:|")
    A(f"| §3, by arm | {EVENT_STRATUM_N / 167:.2f} / {REMAINING_STRATUM_N / 50:.2f} "
      "| 4,063 | 40.6% |")
    A(f"| §4, by production flag | {EVENT_STRATUM_N / 178:.2f} / "
      f"{REMAINING_STRATUM_N / 39:.2f} | 2,428 | 24.3% |")
    A("")
    A("_The corpus base rate is independently put at 19-28% "
      "(`eval/sample_documents_for_annotation.py`), so 40.6% is outside the "
      "plausible range and 24.3% is inside it. That is the check that settles "
      "which estimator to quote._")
    A("")
    A("There is a second, sharper check available, because one of the runs "
      "scored here **is** the run that defined the strata. `prompt 5 (gpt-5, "
      "Azure)` flagged 1,913 of the 10,000 corpus documents by construction, so "
      "a correct estimator applied to its 217 sampled documents must recover "
      "1,913. Under §4's weights it estimates **1,913** exactly; under §3's it "
      "estimates 3,692, a 93% overshoot. The weighting in §4 reproduces a "
      "quantity that is known independently, and the weighting in §3 does not.")
    A("")
    _weighted_tables(A, results, "flag", "4a", "4b")
    A("")

    # ---------------- Coverage ----------------
    gaps = [(res["label"], s, res["by_arm"][s]["detection"]["n"], counts[s][0])
            for res in results for s in arm["order"]
            if res["by_arm"][s]["detection"]["n"] < counts[s][0]]
    if gaps:
        A("## 5. Coverage gaps")
        A("")
        A("Documents a run returned only error rows for, by stratum. These are "
          "dropped from that stratum's denominator and its surviving documents "
          "are weighted up to compensate.")
        A("")
        A("| Run | Stratum | Returned | Sampled |")
        A("|---|---|---:|---:|")
        for label, s, got, tot in gaps:
            A(f"| {label} | {arm['labels'][s]} | {got} | {tot} |")
        A("")

    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    p.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--no-references", action="store_true")
    p.add_argument("--bootstrap", type=int, default=BOOTSTRAP_N)
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    gold = Gold(args.annotations)
    keys = set(gold.documents)
    strata = build_strata(args.annotations, keys)

    runs = [(label, path) for label, path, _s in discover_runs(args.runs_dir)]
    if not args.no_references:
        runs += [(label, path) for label, path in REFERENCE_RUNS if path.exists()]
    if not runs:
        LOG.error("No runs under %s.", args.runs_dir)
        return 2

    results = []
    for label, path in runs:
        run = Run(label, path)
        # The production arm covers all 10,000 documents; restrict every run to
        # the annotated 217 so the strata sizes mean what they say.
        run.docs &= keys
        cells, triples = per_document(gold, run)
        if not cells:
            LOG.warning("%s returned nothing on the annotated set — skipping.", label)
            continue

        by_arm = {}
        for s in strata["arm"]["order"]:
            in_s = {k for k in cells if strata["arm"]["of"][k] == s}
            by_arm[s] = {"detection": detection_counts(cells, in_s)}
            for name, _l in FIELDS:
                by_arm[s][name] = field_counts(
                    triples[name], {k for k in triples[name] if k in in_s})

        results.append({
            "label": label,
            "by_arm": by_arm,
            "weighted": {sch: weighted_estimates(cells, triples, strata[sch])
                         for sch in ("arm", "flag")},
            "boot": {sch: bootstrap(cells, triples, strata[sch], n_boot=args.bootstrap)
                     for sch in ("arm", "flag")},
        })
        LOG.info("Scored %s", label)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(results, strata, gold, args.annotations), encoding="utf-8")
    LOG.info("")
    LOG.info("Wrote %s", args.out.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
