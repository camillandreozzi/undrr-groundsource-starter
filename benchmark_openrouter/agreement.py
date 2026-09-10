"""Cross-model statistics that need no human annotation. Run this today.

    python -m benchmark_openrouter.agreement

EVERY NUMBER HERE IS AGREEMENT, NOT ACCURACY. There is no ground truth in this
file. Two models agreeing tells you they behave alike, not that either is right
— they can be wrong together, and on the location rules they probably are.
Accuracy lives in `score_all.py`, against `eval/human_annotations.csv`.

What it is good for:

  * a behavioural profile per model — how often it finds an event at all, how
    many it emits, which hazard families it reaches for, and what admin levels
    it tags. The admin-level mix is the most direct read available on whether
    prompt 5's sub-national location discipline actually landed, and it needs no
    gold at all.
  * cost and throughput, measured, per model.
  * a disagreement queue. Where the roster splits on "does this document carry a
    verifiable event?", human judgement is worth the most. That ranking is
    written to outputs/disagreement_queue.csv as a directed annotation order.

Everything is aggregated per `asset_key`, for the same reason
`eval/score_against_human.py` is: `event_index` is not a shared key across
models, so joining on it would compare segmentation rather than extraction.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_ner.compare import cohen_kappa, prf  # noqa: E402
from benchmark_openrouter.models import BY_SLUG  # noqa: E402
from eval.score_against_human import Run, _split, fuzzy_matched  # noqa: E402
from fonte.hazard_families import hazard_family  # noqa: E402
from fonte.stats import format_rate  # noqa: E402

LOG = logging.getLogger("benchmark_openrouter.agreement")

OUT_DIR = REPO_ROOT / "benchmark_openrouter" / "outputs"
DEFAULT_REPORT = REPO_ROOT / "benchmark_openrouter" / "MODEL_AGREEMENT.md"
DEFAULT_QUEUE_OUT = OUT_DIR / "disagreement_queue.csv"

#: Reference arms already on disk. Not OpenRouter runs, but the whole point of
#: comparison is having something to compare against.
REFERENCE_RUNS = (
    ("prompt 5 (gpt-5, Azure)",
     REPO_ROOT / "outputs" / "event_extractions" / "event_extractions.jsonl"),
    ("NER baseline",
     REPO_ROOT / "benchmark_ner" / "outputs" / "ner_extractions.jsonl"),
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def discover_runs(out_dir: Path) -> list[tuple[str, Path, dict]]:
    """Every completed OpenRouter run, in roster order, with its stats."""
    found = []
    for sub in sorted(out_dir.iterdir()) if out_dir.exists() else []:
        jsonl = sub / "event_extractions.jsonl"
        if not sub.is_dir() or not jsonl.exists():
            continue
        stats_path = sub / "run_stats.json"
        stats = json.loads(stats_path.read_text()) if stats_path.exists() else {}
        spec = BY_SLUG.get(sub.name)
        label = stats.get("label") or (spec.label if spec else sub.name)
        found.append((label, jsonl, stats))
    return found


def load_all(out_dir: Path, documents: set[str] | None) -> list[tuple[Run, dict]]:
    runs: list[tuple[Run, dict]] = []
    for label, path, stats in discover_runs(out_dir):
        runs.append((Run(label, path), stats))
    for label, path in REFERENCE_RUNS:
        if path.exists():
            runs.append((Run(label, path), {"reference": True}))
        else:
            LOG.warning("Reference run missing, skipping: %s", path)
    if documents:
        # The reference gpt-5 arm covers 10,000 documents; restrict every run to
        # the shared 167 so the comparison is on one population.
        for run, _ in runs:
            run.docs &= documents
            run.events = defaultdict(list, {k: v for k, v in run.events.items()
                                            if k in documents})
    return runs


def snapshot_documents(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).get("documents", {}))


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def profile(run: Run, stats: dict, documents: list[str]) -> dict:
    events = [e for k in documents for e in run.events.get(k, [])]
    # `Run` keeps only verifiable events, so error rows never reach it. The
    # runner already counted them, which is the more reliable source anyway.
    error_docs = stats.get("error_rows")
    with_event = sum(1 for k in documents if run.has_event(k))
    admin = Counter(lvl for e in events for lvl in _split(e.get("location_admin_levels")))
    families = Counter(f for k in documents for f in run.families(k))
    n_loc = sum(len(_split(e.get("affected_locations"))) for e in events)
    n_date = sum(len(_split(e.get("event_dates"))) for e in events)
    # A run that only covered part of the set must not be read as if the
    # documents it never attempted were documents it found nothing in.
    attempted = len(run.docs & set(documents))
    return {
        "label": run.label,
        "documents": len(documents),
        "attempted": attempted,
        "complete": attempted == len(documents),
        "with_event": with_event,
        "with_event_rate": format_rate(with_event, attempted) if attempted else "—",
        "events": len(events),
        "events_per_doc": len(events) / attempted if attempted else 0.0,
        "locations_per_event": n_loc / len(events) if events else 0.0,
        "dates_per_event": n_date / len(events) if events else 0.0,
        "sub_national_share": (
            sum(v for k, v in admin.items() if k not in ("country", "unknown"))
            / sum(admin.values()) if admin else 0.0),
        "country_share": admin.get("country", 0) / sum(admin.values()) if admin else 0.0,
        "unknown_share": admin.get("unknown", 0) / sum(admin.values()) if admin else 0.0,
        "admin": admin,
        "families": families,
        "errors": error_docs,
        "cost": stats.get("cost_usd"),
        "minutes": (stats.get("wall_seconds") or 0) / 60 or None,
        "mode": ", ".join(stats.get("structured_output_mode") or []) or "—",
    }


# ---------------------------------------------------------------------------
# Pairwise agreement
# ---------------------------------------------------------------------------

def pairwise(a: Run, b: Run, documents: list[str]) -> dict:
    # Only documents both runs actually attempted. Without this, an incomplete
    # run reads as one that found nothing on everything it never saw.
    documents = [k for k in documents if k in a.docs and k in b.docs]
    tp = fp = fn = tn = 0
    sets = {"hazard": [0, 0, 0], "location": [0, 0, 0],
            "location_fuzzy": [0, 0, 0], "date": [0, 0, 0]}
    for key in documents:
        ha, hb = a.has_event(key), b.has_event(key)
        if ha and hb:
            tp += 1
        elif hb and not ha:
            fp += 1
        elif ha and not hb:
            fn += 1
        else:
            tn += 1
        if not (ha and hb):
            continue  # set agreement is only defined where both found something
        for name, sa, sb in (("hazard", a.families(key), b.families(key)),
                             ("location", a.locations(key), b.locations(key)),
                             ("date", a.dates(key), b.dates(key))):
            shared = len(sa & sb)
            sets[name][0] += shared
            sets[name][1] += len(sb) - shared
            sets[name][2] += len(sa) - shared
        la, lb = a.locations(key), b.locations(key)
        ftp = fuzzy_matched(la, lb)
        sets["location_fuzzy"][0] += ftp
        sets["location_fuzzy"][1] += len(lb) - ftp
        sets["location_fuzzy"][2] += len(la) - ftp

    n = len(documents)
    return {
        "a": a.label, "b": b.label, "n": n,
        "detection_agreement": (tp + tn) / n if n else 0.0,
        "kappa": cohen_kappa(tp, fp, fn, tn),
        "both": tp, "a_only": fn, "b_only": fp, "neither": tn,
        "sets": {k: prf(*v)[2] for k, v in sets.items()},
    }


# ---------------------------------------------------------------------------
# Disagreement queue
# ---------------------------------------------------------------------------

def disagreement_queue(runs: list[Run], documents: list[str], out: Path) -> int:
    """Rank the documents by how evenly the roster splits on 'has an event'.

    A document every model agrees on teaches an annotator little. One that
    splits the roster 6-6 is where a human judgement moves the most.
    """
    rows = []
    for key in documents:
        votes = [r for r in runs if key in r.docs]
        yes = sum(1 for r in votes if r.has_event(key))
        n = len(votes)
        if not n:
            continue
        # 0 when unanimous, 1 at a perfect split.
        split = 1 - abs(yes - (n - yes)) / n
        rows.append({
            "asset_key": key,
            "runs_voting": n,
            "says_event": yes,
            "says_no_event": n - yes,
            "split_score": round(split, 3),
            "agreed_by": "; ".join(r.label for r in votes if r.has_event(key)),
        })
    rows.sort(key=lambda r: (-r["split_score"], r["asset_key"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["asset_key"])
        writer.writeheader()
        writer.writerows(rows)
    return sum(1 for r in rows if r["split_score"] > 0)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _display(path: Path) -> str:
    """Repo-relative when it can be, as given otherwise.

    A relative `--report`/`--queue-out` resolves against the working directory,
    not REPO_ROOT, so a bare `.relative_to(REPO_ROOT)` raises on one even though
    the file was written perfectly well.
    """
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _pct(x) -> str:
    return "—" if x is None else f"{x:.1%}"


def render(profiles: list[dict], pairs: list[dict], documents: list[str],
           contested: int, queue_path: Path) -> str:
    incomplete = [p for p in profiles if not p["complete"]]
    out = ["# Prompt 5 across models — agreement, not accuracy", "",
           f"{len(profiles)} runs over {len(documents)} shared documents "
           "(the human annotation queue's set).", "",
           "> Every figure on this page is **agreement between models**. None of it is "
           "accuracy — there is no ground truth here. Two models can be wrong in the "
           "same way, and on prompt 5's location rules that is the likely failure mode. "
           "For accuracy see `MODEL_SCORES.md`.", "",
           "> **The document set is not neutral.** These 167 documents are the ones "
           "behind the review queue, and that queue was built from events the "
           "prompt-5 / gpt-5 production run itself emitted. So that arm finds an event "
           "in 100% of them *by construction*, and every other model's detection rate "
           "is being measured against a set selected in gpt-5's favour. It says how "
           "well a model reproduces gpt-5's finds, not how well it does on the corpus. "
           "Only the human annotations settle which of them was right.", ""]
    if incomplete:
        out += ["> **Incomplete runs.** " + "; ".join(
            f"{p['label']} covered {p['attempted']}/{p['documents']}"
            for p in incomplete) + ". Their rates are over what they attempted, and "
            "pairwise rows use only documents both runs attempted — but small "
            "coverage means wide uncertainty. Finish them with `--resume`.", ""]

    out += ["## Behaviour per model", "",
            "| Model | Covered | Docs w/ event | Events | Ev/doc | Loc/ev | Errors | Mode | Cost $ | Min |",
            "|---|---:|---|---:|---:|---:|---:|---|---:|---:|"]
    for p in profiles:
        cost = "—" if p["cost"] is None else f"{p['cost']:.2f}"
        mins = "—" if p["minutes"] is None else f"{p['minutes']:.0f}"
        errors = "—" if p["errors"] is None else str(p["errors"])
        covered = (f"{p['attempted']}" if p["complete"]
                   else f"**{p['attempted']}**/{p['documents']}")
        out.append(f"| {p['label']} | {covered} | {p['with_event_rate']} | {p['events']} | "
                   f"{p['events_per_doc']:.2f} | {p['locations_per_event']:.2f} | "
                   f"{errors} | {p['mode']} | {cost} | {mins} |")

    out += ["", "## Location granularity — did the sub-national rule land?", "",
            "Prompt 5 forbids a bare country for sub-national hazards. A high "
            "`country` share is a model ignoring that rule; a high `unknown` share is a "
            "model unable to self-tag. Neither needs gold to read.", "",
            "| Model | Sub-national | country | unknown |", "|---|---:|---:|---:|"]
    for p in profiles:
        out.append(f"| {p['label']} | {_pct(p['sub_national_share'])} | "
                   f"{_pct(p['country_share'])} | {_pct(p['unknown_share'])} |")

    families = sorted({f for p in profiles for f in p["families"]})
    if families:
        out += ["", "## Hazard families found, per model", "",
                "| Model | " + " | ".join(families) + " |",
                "|---|" + "---:|" * len(families)]
        for p in profiles:
            cells = " | ".join(str(p["families"].get(f, 0)) for f in families)
            out.append(f"| {p['label']} | {cells} |")

    out += ["", "## Pairwise agreement on event detection", "",
            "κ corrects for chance: most documents yield no event, so raw agreement is "
            "high by default and only κ says whether two models agree for a reason. "
            "κ is 0 when one run flags everything — there are then no true negatives "
            "for chance agreement to be corrected against, which is exactly the case "
            "for the gpt-5 arm on this selected set.", "",
            "| A | B | n | Agreement | κ | Both | A only | B only |",
            "|---|---|---:|---:|---:|---:|---:|---:|"]
    for pr in sorted(pairs, key=lambda x: -x["kappa"]):
        out.append(f"| {pr['a']} | {pr['b']} | {pr['n']} | "
                   f"{_pct(pr['detection_agreement'])} | "
                   f"{pr['kappa']:.3f} | {pr['both']} | {pr['a_only']} | {pr['b_only']} |")

    out += ["", "## Pairwise field agreement (F1), on documents where both found an event",
            "", "| A | B | Hazard | Locations | Locations (fuzzy) | Dates |",
            "|---|---|---:|---:|---:|---:|"]
    for pr in sorted(pairs, key=lambda x: -x["sets"]["location_fuzzy"]):
        s = pr["sets"]
        out.append(f"| {pr['a']} | {pr['b']} | {_pct(s['hazard'])} | "
                   f"{_pct(s['location'])} | {_pct(s['location_fuzzy'])} | "
                   f"{_pct(s['date'])} |")

    rel = _display(queue_path)
    out += ["", "## Where to annotate next", "",
            f"{contested} of {len(documents)} documents split the roster on whether they "
            "carry a verifiable event. Those are where a human judgement is worth the "
            f"most, ranked in `{rel}`.", ""]
    return "\n".join(out)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--snapshot", type=Path,
                   default=REPO_ROOT / "benchmark_openrouter" / "documents.json")
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--queue-out", type=Path, default=DEFAULT_QUEUE_OUT)
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()

    shared = snapshot_documents(args.snapshot)
    if not shared:
        LOG.error("No document snapshot at %s — run "
                  "`python -m benchmark_openrouter.build_documents` first.", args.snapshot)
        return 2

    runs = load_all(args.out_dir, shared)
    if not runs:
        LOG.error("No runs found under %s. Run the benchmark first.", args.out_dir)
        return 2

    documents = sorted(shared)
    profiles = [profile(run, stats, documents) for run, stats in runs]
    run_objs = [r for r, _ in runs]
    pairs = [pairwise(run_objs[i], run_objs[j], documents)
             for i in range(len(run_objs)) for j in range(i + 1, len(run_objs))]

    contested = disagreement_queue(run_objs, documents, args.queue_out)
    report = render(profiles, pairs, documents, contested, args.queue_out)
    args.report.write_text(report, encoding="utf-8")
    print(report)
    LOG.info("Wrote %s and %s", _display(args.report),
             _display(args.queue_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
