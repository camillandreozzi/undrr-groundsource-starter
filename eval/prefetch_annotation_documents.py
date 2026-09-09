"""
Prefetch the annotation queue's documents into a small local store.

    python3 eval/prefetch_annotation_documents.py
    # or: make annotate-prefetch

`benchmark_ner/outputs/documents.parquet` holds all 10,000 fetched documents in
57 MB. The annotation queue needs 167 of them, 1.8 MB of text. Reading the bulk
file on every app start cost about two seconds and, worse, made the reviewer
depend on a gitignored artefact that a fresh checkout does not have.

This writes `eval/annotation_documents.json`: exactly the documents the queue
covers, as plain JSON the app loads in milliseconds with no pyarrow. Run it once
after `make ner-fetch`, or whenever the queue changes.

`human_annotation_app.py` builds the same store on first run if it is missing,
so this script is a convenience and a CI step, not a prerequisite.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.human_annotation_app import (  # noqa: E402
    DEFAULT_DOCUMENT_STORE,
    DEFAULT_DOCUMENTS_PARQUET,
    DEFAULT_QUEUE,
    AnnotationError,
    build_document_store,
    read_csv,
)

LOG = logging.getLogger("eval.prefetch_annotation_documents")


def queue_asset_keys(queue_path: Path) -> set[str]:
    """The distinct documents behind the queue's in_queue rows."""
    if not queue_path.exists():
        raise AnnotationError(f"Review queue not found: {queue_path}")
    _, rows = read_csv(queue_path)
    keys = {r.get("asset_key", "") for r in rows
            if str(r.get("in_queue", "")).strip().upper() == "Y"}
    keys.discard("")
    if not keys:
        raise AnnotationError(f"No rows with in_queue == Y in {queue_path}")
    return keys


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--queue", type=Path, default=DEFAULT_QUEUE,
                   help="review queue naming the documents to prefetch")
    p.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS_PARQUET,
                   help="bulk parquet of fetched documents")
    p.add_argument("--out", type=Path, default=DEFAULT_DOCUMENT_STORE,
                   help="where to write the store")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()
    try:
        keys = queue_asset_keys(args.queue)
        LOG.info("Queue %s covers %d distinct documents.", args.queue, len(keys))
        documents = build_document_store(args.documents, keys, args.out)
    except AnnotationError as exc:
        LOG.error("%s", exc)
        return 2

    missing = sorted(keys - set(documents))
    size_mb = args.out.stat().st_size / 1e6
    LOG.info("Wrote %s — %d documents, %.1f MB.", args.out, len(documents), size_mb)
    if missing:
        # Not fatal: the app shows the seed evidence and still takes an
        # annotation, it just cannot show the document text for these.
        LOG.warning("%d queued documents have no fetched text: %s",
                    len(missing), ", ".join(missing[:5]) + ("…" if len(missing) > 5 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
