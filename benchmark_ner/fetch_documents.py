"""benchmark_ner/fetch_documents.py — pull the benchmark corpus from Databricks.

Re-runs the *same* query the production extraction used
(`fonte.app_event_focus.fetch_documents`) so the NER baseline sees the
same 10,000 documents, and trims each text to the same 12,000-character window
the LLM was given. Anything else would compare two different corpora.

The query is `ORDER BY last_processed_at DESC ... LIMIT 10000`, not a pinned
list of asset_keys, so the table may have shifted since the production run on
2026-08-07. This script reports the asset_key overlap against that run and
refuses to continue below --min-overlap: the overlap is the denominator every
downstream comparison is restricted to.

    python benchmark_ner/fetch_documents.py
    python benchmark_ner/fetch_documents.py --limit 200 --out /tmp/docs.parquet
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from fonte.app_event_focus import fetch_documents, trim_text

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "benchmark_ner" / "outputs" / "documents.parquet"
DEFAULT_REFERENCE = (
    REPO_ROOT / "outputs" / "event_extractions" / "event_extractions.jsonl"
)

LOG = logging.getLogger("benchmark_ner.fetch")

# Columns kept for the benchmark. `text` is the trimmed window; the rest are the
# metadata fields the extractor's output rows carry, so ner_extract.py can fill
# the same schema without a second query.
COLUMNS = [
    "asset_key",
    "title",
    "publication_year",
    "language",
    "countries",
    "themes",
    "hazards",
    "organizations",
    "content_url",
    "char_count",
    "text",
]


def reference_asset_keys(path: Path) -> set[str]:
    """asset_keys of the run we are benchmarking against."""
    if not path.exists():
        return set()
    keys: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                keys.add(json.loads(line)["asset_key"])
            except (json.JSONDecodeError, KeyError):
                continue
    return keys


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--limit", type=int, default=10000,
                   help="Documents to fetch. Must match the run being compared (10000).")
    p.add_argument("--max-chars", type=int, default=12000,
                   help="Trim each text to this many characters — the window the LLM saw.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE,
                   help="event_extractions.jsonl of the run to compare against.")
    p.add_argument("--min-overlap", type=float, default=0.95,
                   help="Fail if fewer than this fraction of fetched docs are in the reference run.")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    # `fonte.app_event_focus` only loads .env inside its own main(), and
    # we call fetch_documents() directly — so the Databricks credentials have to
    # be loaded here or connect_databricks() sees an empty environment.
    load_dotenv()

    docs = fetch_documents(args.limit)
    if not docs:
        LOG.error("Databricks returned no documents.")
        return 1

    rows = []
    for d in docs:
        row = asdict(d)
        row["text"] = trim_text(row["text"] or "", max_chars=args.max_chars)
        rows.append({c: row.get(c) for c in COLUMNS})

    df = pd.DataFrame(rows, columns=COLUMNS)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    LOG.info("Wrote %d documents -> %s", len(df), args.out)
    LOG.info("  trimmed text: mean %.0f chars, max %d",
             df["text"].str.len().mean(), df["text"].str.len().max())

    ref = reference_asset_keys(args.reference)
    if not ref:
        LOG.warning("No reference run at %s — skipping the overlap check. "
                    "Comparisons will have no verified common corpus.", args.reference)
        return 0

    fetched = set(df["asset_key"])
    common = fetched & ref
    overlap = len(common) / len(fetched)
    LOG.info("Overlap with %s: %d / %d fetched (%.1f%%); reference run has %d docs",
             args.reference.name, len(common), len(fetched), 100 * overlap, len(ref))

    # Persist the intersection so every downstream step uses the same denominator
    # instead of recomputing it (and possibly disagreeing).
    common_path = args.out.with_name("common_asset_keys.json")
    common_path.write_text(json.dumps(sorted(common)))
    LOG.info("Wrote the %d-key intersection -> %s", len(common), common_path)

    if overlap < args.min_overlap:
        LOG.error(
            "Overlap %.1f%% is below --min-overlap %.1f%%. The source table has "
            "moved since the reference run; comparing these two corpora would "
            "confound corpus drift with model difference. Either accept a "
            "smaller intersection by lowering --min-overlap, or pin the "
            "reference run's asset_keys.",
            100 * overlap, 100 * args.min_overlap,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
