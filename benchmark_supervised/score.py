"""Score the supervised runs beside every Experiment A system -> SUPERVISED_SCORES.md.

    python -m benchmark_supervised.score

Runs `eval/score_event_level.py` unchanged — same gold, matcher, field rules
and bootstrap — over its default roster (prompt 5, the NER baseline, every
OpenRouter run) plus each run in `benchmark_supervised/runs/`. Experiment A's
own outputs are not touched: the report, pairs and JSON are written here.

Two sections are appended, both computed with the scorer's own functions:

  12. the paired difference against the NER baseline — the comparison this
      system exists for — with `score_event_level.paired_difference`;
  13. where each run loses recall: gold events with a lexicon trigger, with a
      trigger the classifier kept, and inside an emitted record.

The Experiment A link audit judged links made between the original systems
and the gold, so it is left out of this report rather than shown beside a
system it never looked at.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import numpy as np  # noqa: E402

from benchmark_supervised import parse  # noqa: E402
from benchmark_supervised.features import Doc, gold_assignment  # noqa: E402
from benchmark_supervised.model import THRESHOLD  # noqa: E402
from eval import score_event_level as sel  # noqa: E402

HERE = REPO_ROOT / "benchmark_supervised"
RUNS = HERE / "runs"
OUT = HERE / "SUPERVISED_SCORES.md"
JSON_OUT = HERE / "supervised_scores.json"
#: LOWO first: it is the primary run.
ORDER = ("lowo", "kfold5_seed48", "kfold5_seed49", "kfold5_seed50")
NER_LABEL = "NER baseline"
GROUPS = ("all", "single", "multi")
_AUDIT_STUB = "_Not yet drawn. `make event-audit-sample` writes it._"
_AUDIT_NOTE = ("_Not applicable. Experiment A's link audit judged links to the original "
               "systems only (`eval/EVENT_LEVEL_SCORES.md` §11); none of its decisions involve "
               "the supervised runs._")


def supervised_runs() -> list[tuple[str, Path]]:
    found = []
    for sub in sorted(RUNS.iterdir() if RUNS.exists() else [],
                      key=lambda p: (ORDER.index(p.name) if p.name in ORDER else len(ORDER), p.name)):
        jsonl, stats = sub / "event_extractions.jsonl", sub / "run_stats.json"
        if jsonl.exists() and stats.exists():
            found.append((json.loads(stats.read_text())["label"], jsonl))
    return found


def paired_vs_ner(gold: sel.GoldSet, runs: list[tuple[str, Path]]) -> dict[str, dict]:
    ner_path = dict(sel.REFERENCE_RUNS)[NER_LABEL]
    ner = sel.score_system(NER_LABEL, ner_path, gold)
    groups = sel.groups_for(gold)
    out: dict[str, dict] = {}
    for label, path in runs:
        s = sel.score_system(label, path, gold)
        out[label] = {}
        for group in GROUPS:
            keys = [k for k in groups.get(group, []) if k in s.per_window and k in ner.per_window]
            if keys:
                out[label][group] = sel.paired_difference(
                    np.vstack([s.per_window[k] for k in keys]),
                    np.vstack([ner.per_window[k] for k in keys]), label, group)
    return out


def recall_funnel(gold: sel.GoldSet, runs: list[tuple[str, Path]]) -> dict[str, dict]:
    """Verifiable gold events reachable by a trigger, kept by the trigger
    classifier, and inside a cluster that became a record."""
    docs = {k: Doc(p) for k, p in parse.load_all(gold.keys).items()}
    owners = {}
    for key, doc in docs.items():
        assign = gold_assignment(doc, gold.events.get(key, []))
        owners[key] = {t.start: assign[t.idx] for t in doc.triggers if t.idx in assign}
    out: dict[str, dict] = {}
    for label, path in runs:
        detail = {d["asset_key"]: d for d in map(json.loads, path.with_name(
            "predictions_detail.jsonl").read_text(encoding="utf-8").splitlines())}
        c = dict.fromkeys(("verifiable", "with_trigger", "trigger_kept", "in_record"), 0)
        for key in gold.keys:
            kept, recorded = set(), set()
            for ev in detail[key]["events"]:
                ids = {owners[key][m["start"]] for m in ev["mentions"] if m["start"] in owners[key]}
                kept |= ids
                if (any(p > THRESHOLD for p in ev["years"].values())
                        and any(p > THRESHOLD for p in ev["places"].values())):
                    recorded |= ids
            reachable = set(owners[key].values())
            for g in gold.events.get(key, []):
                if g.verifiable:
                    c["verifiable"] += 1
                    c["with_trigger"] += g.gold_event_id in reachable
                    c["trigger_kept"] += g.gold_event_id in kept
                    c["in_record"] += g.gold_event_id in recorded
        out[label] = c
    return out


def render_extra(paired: dict[str, dict], funnel: dict[str, dict]) -> str:
    L = ["## 12. Paired difference against the NER baseline", "",
         "Complete-record correctness, supervised run minus the NER baseline, on the windows "
         "both returned; 95% paired cluster bootstrap (`score_event_level.paired_difference`).",
         "", "| System | Windows | All windows | Single-event | Multi-event |",
         "|---|---:|---|---|---|"]
    for label, by_group in paired.items():
        cells = []
        for group in GROUPS:
            d = by_group.get(group)
            cells.append("–" if not d else sel._pp(d["point"]) + (
                "" if np.isnan(d["lo"]) else f" ({d['lo'] * 100:+.1f} to {d['hi'] * 100:+.1f})"))
        L.append(f"| {label} | {by_group.get('all', {}).get('windows', '–')} | "
                 + " | ".join(cells) + " |")
    L += ["", "## 13. Where recall is lost", "",
          "Verifiable gold events, counted down the pipeline. `With a trigger`: a hazard-lexicon "
          "match reports it (the candidate ceiling; the same for every run). `Trigger kept`: the "
          f"trigger classifier scored one of those mentions above {THRESHOLD}. `In a record`: that "
          f"mention's event got a year and a place above {THRESHOLD}, so it was emitted. Matching "
          "to the gold (§2, detection R) can still fail after that.", "",
          "| System | Verifiable gold events | With a trigger | Trigger kept | In a record |",
          "|---|---:|---:|---:|---:|"]
    for label, c in funnel.items():
        n = c["verifiable"]
        L.append(f"| {label} | {n} | " + " | ".join(
            f"{c[k]} ({c[k] / n:.1%})" for k in ("with_trigger", "trigger_kept", "in_record")) + " |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    runs = sel.load_runs([], sel.DEFAULT_OR_DIR) + supervised_runs()
    status = sel.main([
        *[f"--run={label}={path}" for label, path in runs],
        "--out", str(OUT),
        "--pairs-out", str(HERE / "supervised_pairs.csv"),
        "--json-out", str(JSON_OUT),
        "--audit", str(HERE / "no_link_audit.csv"),
        *(argv or []),
    ])
    if status:
        return status
    gold = sel.load_gold(sel.DEFAULT_GOLD, sel.DEFAULT_WINDOWS, sel.DEFAULT_QUEUE,
                         list(sel.DEFAULT_STORES))
    paired = paired_vs_ner(gold, supervised_runs())
    funnel = recall_funnel(gold, supervised_runs())
    report = OUT.read_text(encoding="utf-8").replace(_AUDIT_STUB, _AUDIT_NOTE)
    OUT.write_text(report.rstrip("\n") + "\n\n" + render_extra(paired, funnel), encoding="utf-8")
    payload = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    payload["paired_vs_ner_baseline"] = paired
    payload["recall_funnel"] = funnel
    JSON_OUT.write_text(json.dumps(sel._jsonable(payload), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
