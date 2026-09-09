"""benchmark_ner/score_paired.py — the accuracy half of the benchmark.

Two arms, and they become available at different times.

**Arm 1 — runs today, needs no new judging.** For the LLM events a human has
already judged, report how often the NER baseline agreed with the LLM, split by
that verdict. If the baseline tracks the LLM more closely on events humans
confirmed than on ones they rejected, agreement is carrying signal; if it is
flat across verdicts, the automatic agreement numbers in `compare.py` say
nothing about quality.

**Arm 2 — needs both queues judged.** Joins `eval/production_validation.csv`
and `benchmark_ner/outputs/ner_paired_validation.csv` on
`(asset_key, event_index)`, counts only events judged on *both* sides, and
reports accuracy and useful-rate for each run with Wilson intervals, the paired
difference with an exact McNemar test, and a per-hazard-family breakdown.

McNemar rather than two independent proportion tests: the same events are
judged twice, so the informative quantity is the discordant pairs — events one
run got right and the other did not.

    python benchmark_ner/score_paired.py
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime
from math import comb
from pathlib import Path
from typing import Optional

from fonte.hazard_families import hazard_family
from fonte.stats import format_rate

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "benchmark_ner" / "outputs"
DEFAULT_LLM_QUEUE = REPO_ROOT / "eval" / "production_validation.csv"
BENCH_DIR = REPO_ROOT / "benchmark_ner"
DEFAULT_NER_QUEUE = BENCH_DIR / "ner_paired_validation.csv"
DEFAULT_NER_ONLY = BENCH_DIR / "ner_only_validation.csv"
DEFAULT_NER_JSONL = OUT_DIR / "ner_extractions.jsonl"
DEFAULT_OUT = REPO_ROOT / "benchmark_ner" / "PAIRED_VALIDATION.md"

LOG = logging.getLogger("benchmark_ner.score")

VERDICTS = ("correct", "partial", "wrong")


def _display_path(path: Path) -> str:
    """Repo-relative when it can be, absolute otherwise — the report is meant
    to be copy-pasteable, and a queue kept outside the repo still has to work."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def verdict_of(row: dict) -> Optional[str]:
    v = (row.get("verdict") or "").strip().lower()
    return v if v in VERDICTS else None


def key_of(row: dict) -> tuple[str, str]:
    return (row.get("asset_key", ""), str(row.get("event_index", "")).strip())


def read_queue(path: Path) -> dict[tuple[str, str], dict]:
    with path.open(encoding="utf-8") as fh:
        return {key_of(r): r for r in csv.DictReader(fh)
                if (r.get("in_queue") or "").strip().upper() == "Y"}


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts.

    b = LLM right / NER wrong, c = NER right / LLM wrong. Exact rather than
    chi-square because at n=175 the discordant cells are small, which is
    precisely where the chi-square approximation misbehaves.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def summarise(rows: list[dict]) -> dict:
    c = Counter(verdict_of(r) for r in rows)
    judged = sum(c[v] for v in VERDICTS)
    useful = c["correct"] + c["partial"]
    return {
        "judged": judged,
        "correct": c["correct"],
        "partial": c["partial"],
        "wrong": c["wrong"],
        "unjudged": c[None],
        "accuracy": c["correct"] / judged if judged else None,
        "useful_rate": useful / judged if judged else None,
        "_correct": c["correct"],
        "_useful": useful,
    }


# --------------------------------------------------------------------------
# Arm 1 — agreement split by the verdicts that already exist
# --------------------------------------------------------------------------

def load_ner_by_asset(path: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            v = obj.get("is_verifiable_event")
            if v is True or str(v).strip().lower() == "true":
                out[obj["asset_key"]].append(obj)
    return out


def agreement_by_verdict(llm_queue: dict, ner_by_asset: dict) -> list[dict]:
    """For each existing human verdict, did the baseline agree with the LLM?

    Two levels of agreement: the document produced any event at all, and the
    hazard family matched.
    """
    buckets: dict[str, dict[str, int]] = {
        v: {"n": 0, "found": 0, "family": 0} for v in VERDICTS
    }
    for row in llm_queue.values():
        v = verdict_of(row)
        if v is None:
            continue
        b = buckets[v]
        b["n"] += 1
        cands = ner_by_asset.get(row.get("asset_key", ""), [])
        if cands:
            b["found"] += 1
            want = hazard_family(row.get("event_hazard") or "")
            if any(hazard_family(c.get("event_hazard") or "") == want for c in cands):
                b["family"] += 1
    return [{"verdict": v, **buckets[v]} for v in VERDICTS]


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--llm-queue", type=Path, default=DEFAULT_LLM_QUEUE)
    p.add_argument("--ner-queue", type=Path, default=DEFAULT_NER_QUEUE)
    p.add_argument("--ner-only-queue", type=Path, default=DEFAULT_NER_ONLY)
    p.add_argument("--ner-extractions", type=Path, default=DEFAULT_NER_JSONL)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    if not args.llm_queue.exists():
        LOG.error("Missing LLM queue: %s", args.llm_queue)
        return 1

    llm_queue = read_queue(args.llm_queue)
    llm_summary = summarise(list(llm_queue.values()))

    L: list[str] = []
    A = L.append
    A("# NER baseline vs LLM — paired human validation")
    A("")
    A(f"**LLM queue:** `{args.llm_queue}`  ")
    A(f"**NER queue:** `{args.ner_queue}`  ")
    A(f"**Generated:** {datetime.now():%Y-%m-%d %H:%M}")
    A("")
    A(f"LLM queue: {llm_summary['judged']} of {len(llm_queue)} judged "
      f"({llm_summary['correct']} correct / {llm_summary['partial']} partial / "
      f"{llm_summary['wrong']} wrong).")
    A("")

    # ---- Arm 1 ------------------------------------------------------------
    A("## Arm 1 — does agreement track the human verdict?")
    A("")
    ner_by_asset = load_ner_by_asset(args.ner_extractions)
    if not ner_by_asset:
        A(f"No NER extractions at `{args.ner_extractions}` — run `ner_extract.py` first.")
        A("")
    else:
        arm1 = agreement_by_verdict(llm_queue, ner_by_asset)
        total_judged = sum(b["n"] for b in arm1)
        A(f"For the {total_judged} LLM events already judged, how often did the")
        A("baseline find *something* in the same document, and how often did its")
        A("hazard family match?")
        A("")
        A("| Human verdict on the LLM event | n | NER found an event | NER hazard family matched |")
        A("|---|---:|---:|---:|")
        for b in arm1:
            if b["n"] == 0:
                continue
            A(f"| {b['verdict']} | {b['n']} | {format_rate(b['found'], b['n'])} "
              f"| {format_rate(b['family'], b['n'])} |")
        A("")
        A("Read this as a validity check on `compare.py`: if the baseline agrees")
        A("with the LLM about as often on rejected events as on confirmed ones,")
        A("then agreement is not a proxy for quality and only Arm 2 can rank the")
        A("two pipelines.")
        A("")

    # ---- Arm 2 ------------------------------------------------------------
    A("## Arm 2 — accuracy on the same events")
    A("")
    if not args.ner_queue.exists():
        A(f"No NER queue at `{args.ner_queue}`. Build it with:")
        A("")
        A("```")
        A("python benchmark_ner/prefill_paired_validation.py")
        A("```")
        A("")
    else:
        ner_queue = read_queue(args.ner_queue)
        shared = sorted(set(llm_queue) & set(ner_queue))
        pairs = [(llm_queue[k], ner_queue[k]) for k in shared]
        both = [(l, n) for l, n in pairs if verdict_of(l) and verdict_of(n)]

        A(f"- Paired events: {len(shared)}")
        A(f"- Judged on the LLM side: {sum(1 for l, _ in pairs if verdict_of(l))}")
        A(f"- Judged on the NER side: {sum(1 for _, n in pairs if verdict_of(n))}")
        A(f"- **Judged on both (the comparable set): {len(both)}**")
        A("")

        if not both:
            A("Nothing judged on both sides yet. Judge the NER queue with:")
            A("")
            A("```")
            A(f"GOLD_VALIDATION_CSV={_display_path(args.ner_queue)} \\")
            A("    .venv/bin/python -m streamlit run eval/gold_validation_app.py")
            A("```")
            A("")
        else:
            ls = summarise([l for l, _ in both])
            ns = summarise([n for _, n in both])
            A("| | LLM | NER baseline |")
            A("|---|---|---|")
            A(f"| Accuracy (correct) | {format_rate(ls['_correct'], ls['judged'])} "
              f"| {format_rate(ns['_correct'], ns['judged'])} |")
            A(f"| Useful (correct + partial) | {format_rate(ls['_useful'], ls['judged'])} "
              f"| {format_rate(ns['_useful'], ns['judged'])} |")
            A(f"| correct / partial / wrong | {ls['correct']} / {ls['partial']} / {ls['wrong']} "
              f"| {ns['correct']} / {ns['partial']} / {ns['wrong']} |")
            A("")

            for label, is_hit in (
                ("correct", lambda r: verdict_of(r) == "correct"),
                ("correct or partial", lambda r: verdict_of(r) in ("correct", "partial")),
            ):
                b = sum(1 for l, n in both if is_hit(l) and not is_hit(n))
                c = sum(1 for l, n in both if is_hit(n) and not is_hit(l))
                agree = len(both) - b - c
                p = mcnemar_exact(b, c)
                A(f"**Paired difference on \"{label}\"** — {agree} events both runs")
                A(f"scored the same way; {b} where only the LLM did, {c} where only")
                A(f"the baseline did. Exact McNemar p = {p:.4f}"
                  f"{' (significant at 0.05)' if p < 0.05 else ' (not significant at 0.05)'}.")
                A("")

            # Per hazard family.
            fams: dict[str, list] = defaultdict(list)
            for l, n in both:
                fams[hazard_family(l.get("event_hazard") or l.get("stratum") or "")].append((l, n))
            A("### By hazard family")
            A("")
            A("Cells are small; read them as indicative.")
            A("")
            A("| Family | n | LLM accuracy | NER accuracy |")
            A("|---|---:|---|---|")
            for fam, items in sorted(fams.items(), key=lambda x: -len(x[1])):
                lc = sum(1 for l, _ in items if verdict_of(l) == "correct")
                nc = sum(1 for _, n in items if verdict_of(n) == "correct")
                A(f"| {fam} | {len(items)} | {format_rate(lc, len(items))} "
                  f"| {format_rate(nc, len(items))} |")
            A("")

    # ---- NER-only arm -----------------------------------------------------
    A("## Arm 3 — events only the baseline found")
    A("")
    if not args.ner_only_queue.exists():
        A(f"No NER-only queue at `{args.ner_only_queue}`.")
    else:
        only = read_queue(args.ner_only_queue)
        s = summarise(list(only.values()))
        if s["judged"] == 0:
            A(f"{len(only)} events queued, none judged yet. These are events the")
            A("baseline found in documents the LLM left empty — the only place a")
            A("recall advantage for NER could show up.")
        else:
            A(f"Of {s['judged']} judged events the LLM missed entirely:")
            A("")
            A(f"- Correct: {format_rate(s['_correct'], s['judged'])}")
            A(f"- Useful (correct + partial): {format_rate(s['_useful'], s['judged'])}")
            A("")
            A("A high rate here is a recall gap in the LLM run; a low rate means")
            A("the baseline's extra events are noise.")
    A("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(L))
    LOG.info("Wrote %s", args.out)
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
