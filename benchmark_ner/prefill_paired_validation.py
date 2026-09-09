"""benchmark_ner/prefill_paired_validation.py — the NER queue, paired to the LLM's.

Not a fresh random sample. For each of the 175 events already queued in
`eval/production_validation.csv`, this emits the NER baseline's extraction for
the **same document**, so both runs are judged on the same evidence by the same
rubric. Pairing is what makes the difference testable (McNemar) rather than two
independent estimates with overlapping intervals.

A document the baseline missed entirely still gets a row, with the extraction
fields blank. That is a real outcome — a miss — and dropping it would silently
inflate NER's score.

The output carries exactly the columns `eval/gold_validation_app.py` requires,
so judging needs no changes to the app:

    GOLD_VALIDATION_CSV=benchmark_ner/ner_paired_validation.csv \\
        .venv/bin/python -m streamlit run eval/gold_validation_app.py

`--ner-only-n` additionally writes a second queue of events the baseline found
in documents where the LLM found nothing. Without it the comparison can only
ever show NER losing: every metric would be defined on the LLM's own positives.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import shutil
import sys
from datetime import datetime
from pathlib import Path

from fonte.hazard_families import hazard_family

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "benchmark_ner" / "outputs"
DEFAULT_LLM_QUEUE = REPO_ROOT / "eval" / "production_validation.csv"
DEFAULT_NER = OUT_DIR / "ner_extractions.jsonl"
BENCH_DIR = REPO_ROOT / "benchmark_ner"
# The judged queues live beside the code, not under the gitignored outputs/ —
# they are human labour and belong in version control.
DEFAULT_OUT = BENCH_DIR / "ner_paired_validation.csv"
DEFAULT_ONLY_OUT = BENCH_DIR / "ner_only_validation.csv"

LOG = logging.getLogger("benchmark_ner.prefill")

# Same column contract as eval/prefill_gold_validation.py, plus the pairing key.
REFERENCE_FIELDS = (
    "asset_key",
    "event_index",
    "event_count",
    "title",
    "content_url",
    "language",
    "event_hazard",
    "event_dates",
    "affected_locations",
    "location_admin_levels",
    "key_impacts",
    "event_confidence",
    "evidence_snippets",
    "missing_information",
)
COMPUTED_FIELDS = ("stratum", "auto_risk", "review_rank", "in_queue", "paired_with_llm_event")
JUDGMENT_FIELDS = ("verdict", "notes")
OUTPUT_FIELDS = (*REFERENCE_FIELDS, *COMPUTED_FIELDS, *JUDGMENT_FIELDS)

CONF_ORDER = {"high": 2, "medium": 1, "low": 0}


def load_ner_events(path: Path) -> dict[str, list[dict]]:
    by_asset: dict[str, list[dict]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            v = obj.get("is_verifiable_event")
            if not (v is True or str(v).strip().lower() == "true"):
                continue
            by_asset.setdefault(obj["asset_key"], []).append(obj)
    return by_asset


def pick_counterpart(llm_row: dict, candidates: list[dict]) -> dict | None:
    """The NER event to judge against this LLM event.

    Prefer a hazard-family match — judging an LLM flood row against an NER
    earthquake row from the same document would measure nothing. Fall back to
    the highest-confidence event so a document that produced *something*
    is still judged rather than counted as a miss.
    """
    if not candidates:
        return None
    want = hazard_family(llm_row.get("event_hazard") or "")
    same = [c for c in candidates if hazard_family(c.get("event_hazard") or "") == want]
    pool = same or candidates
    return max(
        pool,
        key=lambda c: (
            CONF_ORDER.get(str(c.get("event_confidence") or "").lower(), -1),
            len(str(c.get("affected_locations") or "")),
        ),
    )


def blank_row(llm_row: dict) -> dict:
    """A document the baseline found no event in."""
    return {
        "asset_key": llm_row.get("asset_key", ""),
        "event_index": llm_row.get("event_index", ""),
        "event_count": 0,
        "title": llm_row.get("title", ""),
        "content_url": llm_row.get("content_url", ""),
        "language": llm_row.get("language", ""),
        "event_hazard": "",
        "event_dates": "",
        "affected_locations": "",
        "location_admin_levels": "",
        "key_impacts": "",
        "event_confidence": "",
        "evidence_snippets": "",
        "missing_information": "NER BASELINE FOUND NO EVENT IN THIS DOCUMENT",
    }


def row_from_event(event: dict, llm_row: dict) -> dict:
    out = {f: event.get(f, "") for f in REFERENCE_FIELDS}
    # Keep the pairing key stable: the join with the LLM queue is on
    # (asset_key, event_index), so the NER row must carry the LLM's index.
    out["asset_key"] = llm_row.get("asset_key", "")
    out["event_index"] = llm_row.get("event_index", "")
    out["event_count"] = event.get("event_count", "")
    return out


def backup(path: Path) -> None:
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = path.with_name(f"{path.name}.bak.{stamp}")
        shutil.copy2(path, dest)
        LOG.info("Backed up existing queue -> %s", dest)


def write_queue(path: Path, rows: list[dict]) -> None:
    backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(OUTPUT_FIELDS), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in OUTPUT_FIELDS})
    LOG.info("Wrote %d rows -> %s", len(rows), path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--llm-queue", type=Path, default=DEFAULT_LLM_QUEUE,
                   help="The judged/judging LLM queue to pair against.")
    p.add_argument("--ner", type=Path, default=DEFAULT_NER)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--ner-only-n", type=int, default=50,
                   help="Also queue N events NER found where the LLM found none. 0 to skip.")
    p.add_argument("--ner-only-out", type=Path, default=DEFAULT_ONLY_OUT)
    p.add_argument("--llm-extractions", type=Path,
                   default=REPO_ROOT / "outputs" / "event_extractions" / "event_extractions.jsonl",
                   help="Used to identify documents where the LLM found nothing.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    for path in (args.llm_queue, args.ner):
        if not path.exists():
            LOG.error("Missing input: %s", path)
            return 1

    llm_rows = [r for r in csv.DictReader(args.llm_queue.open(encoding="utf-8"))
                if (r.get("in_queue") or "").strip().upper() == "Y"]
    if not llm_rows:
        LOG.error("No in_queue=Y rows in %s", args.llm_queue)
        return 1
    LOG.info("Pairing against %d queued LLM events", len(llm_rows))

    ner_by_asset = load_ner_events(args.ner)

    rows: list[dict] = []
    misses = 0
    family_matches = 0
    for llm_row in llm_rows:
        candidates = ner_by_asset.get(llm_row.get("asset_key", ""), [])
        pick = pick_counterpart(llm_row, candidates)
        if pick is None:
            row = blank_row(llm_row)
            misses += 1
        else:
            row = row_from_event(pick, llm_row)
            if hazard_family(pick.get("event_hazard") or "") == hazard_family(
                llm_row.get("event_hazard") or ""
            ):
                family_matches += 1
        # Same stratum and review order as the LLM queue, so the two are judged
        # in lockstep and segment identically at scoring time.
        row["stratum"] = llm_row.get("stratum", "")
        row["auto_risk"] = llm_row.get("auto_risk", "")
        row["review_rank"] = llm_row.get("review_rank", "")
        row["in_queue"] = "Y"
        row["paired_with_llm_event"] = llm_row.get("event_hazard", "")
        row["verdict"] = ""
        row["notes"] = ""
        rows.append(row)

    rows.sort(key=lambda r: int(r["review_rank"]) if str(r["review_rank"]).isdigit() else 10**9)
    write_queue(args.out, rows)
    LOG.info("  NER found no event in %d / %d paired documents (%.1f%%)",
             misses, len(rows), 100 * misses / len(rows))
    LOG.info("  hazard family matched the LLM event in %d / %d",
             family_matches, len(rows) - misses)

    # ---- NER-only arm -----------------------------------------------------
    if args.ner_only_n > 0:
        if not args.llm_extractions.exists():
            LOG.warning("No %s — skipping the NER-only arm.", args.llm_extractions)
            return 0
        llm_positive: set[str] = set()
        with args.llm_extractions.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                v = obj.get("is_verifiable_event")
                if v is True or str(v).strip().lower() == "true":
                    llm_positive.add(obj["asset_key"])

        pool = [e for key, events in ner_by_asset.items() if key not in llm_positive
                for e in events]
        if not pool:
            LOG.info("No NER-only events — nothing for the extra-recall arm.")
            return 0
        rng = random.Random(args.seed)
        picked = rng.sample(pool, min(args.ner_only_n, len(pool)))
        only_rows = []
        for rank, e in enumerate(picked, start=1):
            row = {f: e.get(f, "") for f in REFERENCE_FIELDS}
            row["stratum"] = e.get("event_hazard", "")
            row["auto_risk"] = ""
            row["review_rank"] = rank
            row["in_queue"] = "Y"
            row["paired_with_llm_event"] = ""
            row["verdict"] = ""
            row["notes"] = ""
            only_rows.append(row)
        write_queue(args.ner_only_out, only_rows)
        LOG.info("  NER-only pool: %d events across %d documents the LLM left empty",
                 len(pool), len({e["asset_key"] for e in pool}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
