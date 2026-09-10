"""Recompute three scores the headline table does not carry, from the same runs.

    python3 eval/score_strict_rules.py              # pooled 217
    python3 eval/score_strict_rules.py --arm 167

Nothing is re-judged and no run is re-executed: this reads
`eval/human_annotations_pooled.csv` and `benchmark_openrouter/outputs_pooled/`
exactly as `paper/make_tab_validation_pooled.py` does, and re-pools the same
`Gold`/`Run` objects under three stricter rules. Each answers a question the
published rule is generous about.

1. HAZARD AT LABEL LEVEL
   The table's `Haz.` column folds both sides through
   `fonte.hazard_families.hazard_family` before comparing, so `Tsunami` and
   `Earthquake | Tsunami` match and everything in the residual `other` bucket
   matches everything else in it. Here the same sets are compared as written
   (split on `|`, NFKD-folded, casefolded) with no family collapse, which is
   the number `paper/par_hazard_matching.tex` states is measured nowhere.

2. LOCATIONS WITHOUT SUBSET CREDIT
   `Loc-fz` is rapidfuzz `token_set_ratio` >= 90 on normalised strings.
   That scorer returns 100 whenever one side's token set is contained in the
   other's, so `Louisville` scores a match against `Louisville, Kentucky` and
   `Sindh` against `Sindh, Pakistan` — which is deliberate (an appended parent
   qualifier is not an error) but also means a run is credited for naming a
   province when gold names a district inside it, and vice versa. The strict
   rule keeps the threshold and rejects exactly one thing: a pair whose token
   sets stand in a proper subset relation. Pairs are re-matched greedily under
   the strict rule rather than filtered out of the generous matching, so a
   string freed by a rejection can still match something else.

   The subset matches are also reported on their own, since which way to read
   them is a judgement call and the count is what makes it one. They are split
   by what the extra tokens are: a generic feature or administrative type word
   (`Unzen` against `Unzen volcano`, `Sindhuli` against `Sindhuli district`)
   or a place name, which is nearly always an appended parent
   (`Vesuvius` against `Vesuvius, Italy`). Neither names a different place, so
   the strict F1 is a floor on location agreement rather than a correction to
   it, and both numbers are needed to say so.

3. PRECISION INCLUDING THE NEGATIVE DOCUMENTS
   `score_run` computes every field metric on documents gold says carry an
   event (`if not g: continue`), so an item extracted from a document gold
   calls a non-event is invisible to the pooled P/R/F1. On the pooled 217 that
   silently discards 46 of 217 documents from the precision denominator, and
   they are the documents on which a run's spurious output is concentrated.
   Here a gold-negative document contributes an empty reference set, so every
   item a run reports on it is a false positive. Recall is unchanged by
   construction; only precision and F1 move.

Output is a Markdown table on stdout, or to --out.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT, REPO_ROOT / "paper"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from _validation_tables import ARMS, EXPECTED, NER_RUN, SHORT  # noqa: E402
from benchmark_openrouter.agreement import discover_runs  # noqa: E402
from eval.score_against_human import (  # noqa: E402
    FUZZY_THRESHOLD, Gold, Run, _fold, _split, _years, prf,
)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _greedy(a: set[str], b: set[str], score) -> list[tuple[str, str]]:
    """`score_against_human._greedy_pairs`, but returning the pairs it chose."""
    pairs = []
    for x in a:
        for y in b:
            s = score(x, y)
            if s is not None:
                pairs.append((s, x, y))
    pairs.sort(reverse=True)
    used_a: set[str] = set()
    used_b: set[str] = set()
    out = []
    for _s, x, y in pairs:
        if x in used_a or y in used_b:
            continue
        used_a.add(x)
        used_b.add(y)
        out.append((x, y))
    return out


def _rf():
    from rapidfuzz import fuzz, utils
    return fuzz, utils


def _tokens(s: str) -> frozenset[str]:
    """The token set `token_set_ratio` works on, after the same preprocessing."""
    _fuzz, utils = _rf()
    return frozenset(utils.default_process(_fold(s)).split())


def _is_subset_pair(x: str, y: str) -> bool:
    """True when one side's tokens are a proper subset of the other's."""
    tx, ty = _tokens(x), _tokens(y)
    return tx != ty and (tx <= ty or ty <= tx)


def _norm_score(x: str, y: str):
    fuzz, utils = _rf()
    s = fuzz.token_set_ratio(_fold(x), _fold(y), processor=utils.default_process)
    return s if s >= FUZZY_THRESHOLD else None


def _strict_score(x: str, y: str):
    """The published rule with subset pairs refused, everything else identical."""
    if _is_subset_pair(x, y):
        return None
    return _norm_score(x, y)


# Feature and administrative type words. A subset pair whose extra tokens are
# drawn only from these is the same place with its kind spelled out, which is
# a naming convention rather than a difference of granularity.
GENERIC = frozenset("""
volcano volcanic mount mt mountain lake river basin valley area region district
districts province provinces prefecture state county city town municipality
municipal island islands governorate department division subcounty metropolitan
greater upazila tehsil taluka zone territory territories commune canton parish
rural urban ward block sector reservoir dam bay gulf coast coastal delta strait
peninsula range national park sea
""".split())


def classify(pairs: list[tuple[str, str]]) -> dict[str, int]:
    """Split matched pairs into identical / subset / other surface variation.

    Subset pairs are further split by what the containing side adds: a type
    word from `GENERIC`, or a place name (in practice an appended parent).
    """
    out = {"identical": 0, "subset": 0, "variant": 0,
           "subset_typeword": 0, "subset_placename": 0}
    for x, y in pairs:
        tx, ty = _tokens(x), _tokens(y)
        if tx == ty:
            out["identical"] += 1
        elif tx <= ty or ty <= tx:
            out["subset"] += 1
            diff = (ty - tx) if tx < ty else (tx - ty)
            out["subset_typeword" if diff <= GENERIC else "subset_placename"] += 1
        else:
            out["variant"] += 1
    return out


# ---------------------------------------------------------------------------
# Gold, at label level
# ---------------------------------------------------------------------------

def gold_labels(path: Path) -> dict[str, set[str]]:
    """Raw hazard labels per document — `Gold` keeps only the folded families.

    Same row filter as `Gold`: annotation_status done, gold_is_event yes.
    """
    csv.field_size_limit(10 ** 9)
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if str(r.get("annotation_status", "")).strip().lower() != "done":
            continue
        if r.get("gold_is_event") != "yes":
            continue
        out[r["asset_key"]].update(_fold(h) for h in _split(r.get("gold_hazards")))
    return out


def run_labels(run: Run, key: str) -> set[str]:
    return {_fold(label)
            for e in run.events.get(key, [])
            for label in _split(e.get("event_hazard"))}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score(gold: Gold, glabels: dict[str, set[str]], run: Run) -> dict:
    """Every stricter variant for one run, on the documents it returned."""
    docs = [k for k in gold.documents if k in run.docs and k not in run.errored]
    pos = [k for k in docs if gold.has_event[k]]
    neg = [k for k in docs if not gold.has_event[k]]

    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])

    def add(name: str, gs: set[str], rs: set[str], tp: int) -> None:
        c = counts[name]
        c[0] += tp
        c[1] += len(rs) - tp
        c[2] += len(gs) - tp

    kinds = {"identical": 0, "subset": 0, "variant": 0,
             "subset_typeword": 0, "subset_placename": 0}
    subset_docs: set[str] = set()

    for key in pos:
        # 1. hazard: family (the published rule) against label as written
        gf, rf_ = gold.families[key], run.families(key)
        add("haz_family", gf, rf_, len(gf & rf_))
        gl_, rl_ = glabels.get(key, set()), run_labels(run, key)
        add("haz_label", gl_, rl_, len(gl_ & rl_))

        # 2. locations: published fuzzy rule, and the same rule refusing subsets
        gloc, rloc = gold.locations[key], run.locations(key)
        generous = _greedy(gloc, rloc, _norm_score)
        strict = _greedy(gloc, rloc, _strict_score)
        add("loc_fuzzy", gloc, rloc, len(generous))
        add("loc_strict", gloc, rloc, len(strict))
        k = classify(generous)
        for name, v in k.items():
            kinds[name] += v
        if k["subset"]:
            subset_docs.add(key)

        # 3. the pooled record, on gold-positive documents only (as published)
        gy, ry = _years(gold.dates[key]), _years(run.dates(key))
        add("date_year", gy, ry, len(gy & ry))

    pooled_pos = [sum(x) for x in zip(counts["haz_family"], counts["loc_fuzzy"],
                                      counts["date_year"])]

    # 3, continued: the same pooling with the gold-negative documents included.
    # Their reference set is empty, so every item reported on them is a false
    # positive and neither TP nor FN can change.
    spurious = 0
    fired = 0
    for key in neg:
        n = (len(run.families(key)) + len(run.locations(key))
             + len(_years(run.dates(key))))
        spurious += n
        if run.has_event(key):
            fired += 1
    pooled_all = [pooled_pos[0], pooled_pos[1] + spurious, pooled_pos[2]]

    return {
        "label": run.label,
        "n_pos": len(pos),
        "n_neg": len(neg),
        "fired_on_neg": fired,
        "spurious_items": spurious,
        "subset_matches": kinds["subset"],
        "matched_pairs": kinds["identical"] + kinds["subset"] + kinds["variant"],
        "subset_docs": len(subset_docs),
        "match_kinds": kinds,
        "haz_family": prf(*counts["haz_family"]),
        "haz_label": prf(*counts["haz_label"]),
        "loc_fuzzy": prf(*counts["loc_fuzzy"]),
        "loc_strict": prf(*counts["loc_strict"]),
        "pooled_pos": prf(*pooled_pos),
        "pooled_all": prf(*pooled_all),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=sorted(ARMS), default="217")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    arm = ARMS[args.arm]
    gold = Gold(arm["annotations"])
    glabels = gold_labels(arm["annotations"])

    available = {label: path for label, path, _ in discover_runs(arm["out_dir"])}
    if NER_RUN.exists():
        available["NER baseline"] = NER_RUN

    results = []
    for label in EXPECTED:
        path = available.get(label)
        if path is None or label not in SHORT:
            continue
        s = score(gold, glabels, Run(label, path))
        if s["n_pos"]:
            results.append(s)
    results.sort(key=lambda s: -s["pooled_pos"][2])

    def p(x: float) -> str:
        return f"{x * 100:.1f}"

    n_neg = results[0]["n_neg"] if results else 0
    lines = [
        f"# Stricter rules over the same runs (arm {args.arm})",
        "",
        f"Annotations: `{arm['annotations'].name}`; runs: `{arm['out_dir'].name}/`. "
        "No re-judging, no re-running — the published scorer's objects re-pooled.",
        "",
        "| Model | Haz-fam F1 | Haz-label F1 | Loc-fz F1 | Loc-strict F1 | "
        "Subset matches | Pooled P (pos only) | Pooled P (+neg) | Pooled F1 (+neg) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in results:
        lines.append(
            f"| {SHORT[s['label']]} | {p(s['haz_family'][2])} | {p(s['haz_label'][2])} "
            f"| {p(s['loc_fuzzy'][2])} | {p(s['loc_strict'][2])} "
            f"| {s['subset_matches']} | {p(s['pooled_pos'][0])} "
            f"| {p(s['pooled_all'][0])} | {p(s['pooled_all'][2])} |")

    lines += [
        "",
        f"Gold-negative documents in the denominator of the `+neg` columns: {n_neg}.",
        "",
        "| Model | Fired on neg docs | Spurious items | Matched pairs | Identical "
        "| Subset (type word) | Subset (place name) | Variant | Subset share |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in results:
        k = s["match_kinds"]
        share = s["subset_matches"] / s["matched_pairs"] if s["matched_pairs"] else 0.0
        lines.append(
            f"| {SHORT[s['label']]} | {s['fired_on_neg']}/{s['n_neg']} "
            f"| {s['spurious_items']} | {s['matched_pairs']} | {k['identical']} "
            f"| {k['subset_typeword']} | {k['subset_placename']} | {k['variant']} "
            f"| {p(share)} |")

    text = "\n".join(lines) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
