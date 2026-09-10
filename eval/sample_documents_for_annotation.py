"""
Draw a *document* sample for human annotation — the negative-control queue.

    python3 eval/sample_documents_for_annotation.py

WHY THIS EXISTS
---------------
`eval/production_validation.csv` samples **events**, so the 167 documents behind
it are the document footprint of an event sample. Every one of them contains an
event the production run found, by construction: a document the run declined
could not enter the queue at any step. That set has no true negatives, so
`docs/VALIDATION_METHODS.md` §1 has to concede that **recall is estimable on it
and precision is not**, and §5 lists that as an open limitation.

This script fixes exactly that. It samples uniformly at random from the **full
10,000-document corpus**, including the 8,087 documents the production run found
nothing in. Roughly four in five draws will be documents the run declined, and
those are the true negatives the earlier queue could not contain.

What the new sample buys, and what it does not
----------------------------------------------
* **Specificity and precision become estimable.** A document the run declined and
  the annotator confirms as event-free is a true negative; one the annotator says
  does report an event is a false negative the old queue could never surface.
* **Recall does not.** At the corpus base rate of 19.1%, 50 documents yields
  about 10 event-bearing ones — enough to sanity-check, far too few to move the
  94.9-98.1% recall figures. Quote recall from the 167, specificity from here.
* **The two sets are disjoint.** Documents already in `human_annotations.csv` are
  excluded, so the samples can be pooled or reported separately without
  double-counting any document.

Output: a queue CSV in the shape `human_annotation_app.py` expects, so the same
annotation app reads it with no changes:

    ANNOTATION_QUEUE_CSV=eval/document_sample_queue.csv \\
    HUMAN_ANNOTATIONS_CSV=eval/human_annotations_document_sample.csv \\
    ANNOTATION_DOCUMENTS=eval/annotation_documents_document_sample.json \\
        python3 -m streamlit run eval/human_annotation_app.py

    # or simply: make annotate-docsample
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DOCUMENTS = REPO_ROOT / "benchmark_ner" / "outputs" / "documents.parquet"
DEFAULT_RUN = REPO_ROOT / "outputs" / "event_extractions" / "event_extractions.jsonl"
DEFAULT_EXCLUDE = REPO_ROOT / "eval" / "human_annotations.csv"
DEFAULT_OUT = REPO_ROOT / "eval" / "document_sample_queue.csv"

# `human_annotation_app.build_annotations` reads asset_key, review_rank, stratum,
# title, content_url, language, and filters on in_queue == Y. The rest is
# provenance: what the run did on this document, so the sample can be described
# without re-reading the JSONL.
QUEUE_COLUMNS = [
    "asset_key",
    "review_rank",
    "stratum",
    "title",
    "content_url",
    "language",
    "publication_year",
    "char_count",
    "corpus_hazards",
    "run_found_events",
    "run_event_records",
    "in_queue",
]

LOG = logging.getLogger("eval.sample_documents_for_annotation")


class SamplingError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def load_corpus(path: Path) -> list[dict]:
    """The full fetched corpus — one record per document, no text."""
    if not path.exists():
        raise SamplingError(
            f"Document corpus not found: {path}\n"
            "Fetch it first:  make ner-fetch"
        )
    import pyarrow.parquet as pq

    columns = ["asset_key", "title", "content_url", "language",
               "publication_year", "hazards", "char_count"]
    table = pq.read_table(path, columns=columns)
    return table.to_pylist()


def load_run_counts(path: Path) -> tuple[Counter, Counter]:
    """Per document: how many verifiable events the run emitted, and how many
    records it wrote at all (a declined document still gets a record)."""
    verifiable: Counter = Counter()
    records: Counter = Counter()
    if not path.exists():
        LOG.warning("Reference run not found: %s — run columns will read 0", path)
        return verifiable, records

    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            key = obj.get("asset_key")
            if not key:
                continue
            records[key] += 1
            flag = obj.get("is_verifiable_event")
            if flag is True or str(flag).strip().lower() == "true":
                verifiable[key] += 1
    return verifiable, records


def load_excluded_keys(paths: list[Path]) -> set[str]:
    """Documents already annotated, which must not be drawn again."""
    excluded: set[str] = set()
    for path in paths:
        if not path.exists():
            LOG.warning("Exclusion file not found, ignoring: %s", path)
            continue
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row.get("asset_key") or "").strip()
                if key:
                    excluded.add(key)
        LOG.info("Excluding %d documents from %s", len(excluded), path.name)
    return excluded


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def draw(corpus: list[dict], excluded: set[str], n: int, seed: int) -> list[dict]:
    """Uniform random draw over the eligible documents.

    Sorted before sampling so the draw depends on the seed alone and not on the
    parquet's row order.
    """
    eligible = [d for d in corpus if d.get("asset_key") not in excluded]
    LOG.info("Corpus %d documents, %d excluded, %d eligible",
             len(corpus), len(corpus) - len(eligible), len(eligible))
    if len(eligible) < n:
        raise SamplingError(f"Only {len(eligible)} eligible documents for n={n}")
    eligible.sort(key=lambda d: d.get("asset_key") or "")
    return random.Random(seed).sample(eligible, n)


def build_queue_rows(sample: list[dict], verifiable: Counter,
                     records: Counter, stratum: str) -> list[dict]:
    rows = []
    for rank, doc in enumerate(sample, start=1):
        key = doc.get("asset_key") or ""
        rows.append({
            "asset_key": key,
            "review_rank": str(rank),
            "stratum": stratum,
            "title": (doc.get("title") or "").strip(),
            "content_url": (doc.get("content_url") or "").strip(),
            "language": (doc.get("language") or "").strip(),
            "publication_year": (doc.get("publication_year") or "").strip(),
            "char_count": str(doc.get("char_count") or 0),
            "corpus_hazards": (doc.get("hazards") or "").strip(),
            # 0 here means the production run declined this document. The app
            # reads it to show an empty seed instead of a phantom one-event seed.
            "run_found_events": str(verifiable.get(key, 0)),
            "run_event_records": str(records.get(key, 0)),
            "in_queue": "Y",
        })
    return rows


def write_queue(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=QUEUE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarise(rows: list[dict], corpus_size: int, eligible: int,
              n: int, seed: int) -> dict:
    positives = sum(1 for r in rows if int(r["run_found_events"]) > 0)
    return {
        "sampling": "uniform_random_over_documents",
        "population": {
            "corpus_documents": corpus_size,
            "eligible_after_exclusions": eligible,
        },
        "params": {"n": n, "seed": seed},
        "composition": {
            "run_found_events": positives,
            "run_declined": len(rows) - positives,
            "language": dict(Counter(r["language"] for r in rows).most_common()),
            "publication_year": dict(
                sorted(Counter(r["publication_year"] for r in rows).items())),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS)
    p.add_argument("--run", type=Path, default=DEFAULT_RUN,
                   help="reference run, used only to record what it found")
    p.add_argument("--exclude", type=Path, nargs="*", default=[DEFAULT_EXCLUDE],
                   help="CSVs whose asset_keys must not be drawn again")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--n", type=int, default=50)
    # Deliberately not 42: that seed drew the event sample, and a distinct seed
    # keeps the two draws visibly independent in the write-up.
    p.add_argument("--seed", type=int, default=43)
    p.add_argument("--stratum", default="random_document",
                   help="label carried into the annotation file for segmentation")
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing queue")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    if args.out.exists() and not args.force:
        LOG.error("%s already exists. Re-run with --force to redraw "
                  "(annotations keyed to the old draw would be orphaned).", args.out)
        return 1

    try:
        corpus = load_corpus(args.documents)
        verifiable, records = load_run_counts(args.run)
        excluded = load_excluded_keys(list(args.exclude))
        sample = draw(corpus, excluded, args.n, args.seed)
    except SamplingError as exc:
        LOG.error("%s", exc)
        return 2

    rows = build_queue_rows(sample, verifiable, records, args.stratum)
    write_queue(args.out, rows)

    eligible = len([d for d in corpus if d.get("asset_key") not in excluded])
    summary = summarise(rows, len(corpus), eligible, args.n, args.seed)
    summary_path = args.out.with_name(args.out.stem + "_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2))

    positives = summary["composition"]["run_found_events"]
    base_rate = sum(1 for c in verifiable.values() if c > 0) / max(1, len(corpus))
    LOG.info("")
    LOG.info("Wrote %s — %d documents (seed=%d).", args.out, len(rows), args.seed)
    LOG.info("  the run found events in %d of them, declined %d.",
             positives, len(rows) - positives)
    LOG.info("  corpus base rate is %.1f%%, so ~%.0f positives were expected.",
             base_rate * 100, base_rate * args.n)
    LOG.info("Wrote %s", summary_path)
    LOG.info("")
    LOG.info("Annotate it with:  make annotate-docsample")
    return 0


if __name__ == "__main__":
    sys.exit(main())
