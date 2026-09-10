"""Freeze the 167 annotation-queue documents into a local snapshot.

    python -m benchmark_openrouter.build_documents            # from Databricks
    python -m benchmark_openrouter.build_documents --from-parquet

WHY NOT REUSE eval/annotation_documents.json
--------------------------------------------
That store holds `text` and `char_count` only — everything the annotation app
needs. Prompt 5 is given more than the text: `build_prompt_payload` wraps a
`document_metadata` block (title, countries, themes, hazards, organizations,
publication year, language, urls, ids, last_processed_at) around it, and the
prompt explicitly instructs the model to read it. Feeding a different metadata
block than the production gpt-5 run saw would confound a model comparison with
an input comparison.

So the snapshot carries the full `DocumentRow`. Databricks is the default source
because it is the only one that has all of it. `benchmark_ner/outputs/documents.parquet`
is a usable fallback for anyone without Databricks access, but it lacks five
fields (source_id, attachment_id, asset_url, asset_type, last_processed_at);
those become null and the snapshot records that it happened, so the caveat
travels with the data instead of living in someone's memory.

The result is tracked in git (~2 MB), which is what makes the benchmark
reproducible from a clean checkout.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from dotenv import load_dotenv  # noqa: E402

from eval.prefetch_annotation_documents import queue_asset_keys  # noqa: E402
from fonte.app_event_focus import (  # noqa: E402
    DocumentRow,
    connect_databricks,
    trim_text,
)

LOG = logging.getLogger("benchmark_openrouter.build_documents")

#: The prompt never sees more than this (`--max-chars` on the production run),
#: so storing the untrimmed text would put ~17 MB in git for no benefit. The
#: original length survives in `char_count`, which is what the metadata block
#: reports to the model anyway.
MAX_CHARS = 12_000

DEFAULT_QUEUE = REPO_ROOT / "eval" / "production_validation.csv"
DEFAULT_PARQUET = REPO_ROOT / "benchmark_ner" / "outputs" / "documents.parquet"
DEFAULT_OUT = REPO_ROOT / "benchmark_openrouter" / "documents.json"

#: DocumentRow fields the parquet fallback cannot supply.
PARQUET_MISSING_FIELDS = (
    "source_id", "attachment_id", "asset_url", "asset_type", "last_processed_at",
)
#: DocumentRow fields no source here supplies (unused by the prompt payload).
UNUSED_FIELDS = ("status", "extraction_method")


class BuildError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def fetch_from_databricks(keys: set[str]) -> dict[str, dict]:
    """The same asset-joined-to-chunk-metadata query `fetch_documents` runs,
    restricted to our asset_keys instead of ordered-and-limited."""
    asset_table = os.getenv(
        "DATABRICKS_SOURCE_ASSET_TABLE",
        "undrr_d_datahub_databricks_ws.gold.asset_texts",
    )
    chunk_table = os.getenv(
        "DATABRICKS_SOURCE_CHUNK_TABLE",
        "undrr_d_datahub_databricks_ws.gold.asset_text_chunks",
    )
    # asset_key is a 64-char hex digest; assert that before interpolating.
    bad = [k for k in keys if len(k) != 64 or not all(c in "0123456789abcdef" for c in k)]
    if bad:
        raise BuildError(f"Refusing to query: {len(bad)} asset_key(s) are not hex digests, e.g. {bad[0]!r}")
    key_list = ", ".join(f"'{k}'" for k in sorted(keys))

    query = f"""
    WITH chunk_meta AS (
        SELECT
            asset_key,
            MAX(title) AS title,
            MAX(publication_year) AS publication_year,
            MAX(language) AS language,
            MAX(countries) AS countries,
            MAX(themes) AS themes,
            MAX(hazards) AS hazards,
            MAX(organizations) AS organizations,
            MAX(content_url) AS content_url
        FROM {chunk_table}
        GROUP BY asset_key
    )
    SELECT
        a.asset_key,
        a.source_id,
        a.attachment_id,
        a.asset_url,
        a.asset_type,
        a.status,
        a.extraction_method,
        a.char_count,
        a.text,
        CAST(a.last_processed_at AS STRING) AS last_processed_at,
        m.title,
        m.publication_year,
        m.language,
        m.countries,
        m.themes,
        m.hazards,
        m.organizations,
        m.content_url
    FROM {asset_table} a
    LEFT JOIN chunk_meta m
        ON a.asset_key = m.asset_key
    WHERE a.asset_key IN ({key_list})
      AND a.text IS NOT NULL
      AND LENGTH(TRIM(a.text)) > 0
    """

    started = time.perf_counter()
    LOG.info("Querying Databricks for %d documents...", len(keys))
    with connect_databricks() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [d[0] for d in cursor.description]
    LOG.info("Fetched %d rows in %.1fs.", len(rows), time.perf_counter() - started)

    return {r["asset_key"]: r for r in (dict(zip(columns, row)) for row in rows)}


def fetch_from_parquet(keys: set[str], path: Path) -> dict[str, dict]:
    if not path.exists():
        raise BuildError(
            f"{path} not found. It is gitignored bulk output — run `make ner-fetch`, "
            "or drop --from-parquet to read from Databricks."
        )
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    available = set(table.column_names)
    out: dict[str, dict] = {}
    for record in table.to_pylist():
        key = record.get("asset_key")
        if key not in keys:
            continue
        out[key] = {
            **{f: None for f in PARQUET_MISSING_FIELDS + UNUSED_FIELDS},
            **{k: v for k, v in record.items() if k in available},
        }
    return out


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def to_document_row(record: dict) -> dict:
    """Project a source record onto exactly the DocumentRow fields, in order.

    `text` is trimmed to the window the prompt actually receives. `char_count`
    is left as the source reported it — untrimmed — because that is the value
    the production run put in the model's metadata block.
    """
    row = {f: record.get(f) for f in DocumentRow.__dataclass_fields__}
    row["text"] = trim_text(row.get("text") or "", max_chars=MAX_CHARS)
    return row


def write_snapshot(documents: dict[str, dict], out: Path, *, source: str,
                   metadata_source: str) -> None:
    payload = {
        "source": source,
        "metadata_source": metadata_source,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "document_count": len(documents),
        "text_trimmed_to": MAX_CHARS,
        "null_fields": (list(PARQUET_MISSING_FIELDS)
                        if metadata_source == "parquet" else []),
        # Sorted so the tracked file has a stable diff between rebuilds.
        "documents": {k: documents[k] for k in sorted(documents)},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, out)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--queue", type=Path, default=DEFAULT_QUEUE,
                   help="review queue whose in_queue==Y rows define the documents")
    p.add_argument("--from-parquet", action="store_true",
                   help="read from benchmark_ner/outputs/documents.parquet instead of "
                        "Databricks; five metadata fields will be null")
    p.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args()


def _display(path: Path) -> str:
    """Path relative to the repo when it is inside it, otherwise as given.

    `--queue eval/foo.csv` is resolved against the working directory, not
    REPO_ROOT, so a bare `.relative_to(REPO_ROOT)` raises on any relative
    argument even though the file is perfectly readable.
    """
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv(REPO_ROOT / ".env")
    args = parse_args()

    try:
        keys = queue_asset_keys(args.queue)
        LOG.info("Queue %s covers %d distinct documents.",
                 _display(args.queue), len(keys))

        if args.from_parquet:
            LOG.warning("Reading metadata from parquet — %s will be null.",
                        ", ".join(PARQUET_MISSING_FIELDS))
            raw = fetch_from_parquet(keys, args.parquet)
            source, metadata_source = _display(args.parquet), "parquet"
        else:
            raw = fetch_from_databricks(keys)
            source, metadata_source = "databricks", "databricks"
    except BuildError as exc:
        LOG.error("%s", exc)
        return 2
    except Exception as exc:  # noqa: BLE001 - surface connection errors plainly
        LOG.error("Fetch failed: %s", exc)
        if not args.from_parquet:
            LOG.error("If Databricks is unavailable, retry with --from-parquet.")
        return 2

    documents = {k: to_document_row(v) for k, v in raw.items()}
    missing = sorted(keys - set(documents))
    if missing:
        LOG.warning("%d queued documents had no text and were skipped: %s",
                    len(missing), ", ".join(m[:16] for m in missing[:5]))

    write_snapshot(documents, args.out, source=source, metadata_source=metadata_source)
    LOG.info("Wrote %s — %d documents, %.1f MB, metadata_source=%s.",
             _display(args.out), len(documents),
             args.out.stat().st_size / 1e6, metadata_source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
