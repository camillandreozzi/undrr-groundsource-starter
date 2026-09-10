"""
Human annotation over the review-queue documents — model-independent ground truth.

Run from the repository root:

    make annotate
    # or: python3 -m streamlit run eval/human_annotation_app.py

WHY THIS IS NOT `gold_validation_app.py`
----------------------------------------
That app records a *verdict about one run* ("prompt 5 got this event right"). A
verdict cannot be reused: judging a second model means judging 175 events again,
and the two passes are not on the same scale because they were made on different
days against different screens.

This app records what the *document* says — hazards, dates, locations, impacts —
with no reference to which pipeline produced it. Annotate once, then score any
number of runs against it with `eval/score_against_human.py`. That turns "how
does model X compare" into a five-second question instead of a day of review.

THE UNIT IS THE DOCUMENT, NOT THE QUEUE EVENT
---------------------------------------------
The 175-row queue is 167 distinct documents, and it samples *events*: prompt 5
emits 572 verifiable events across those same 167 documents, so a queue row
covers on average under a third of its document. Annotating per queue row would
make gold a partial list, and every unannotated event a run found would score as
a false positive — precision would measure the sampling, not the model.

So each item here is one document and the annotation is everything that document
reports. Gold is then complete, and precision, recall and F1 all mean what they
say for any run, whatever way it splits a document into events.

Annotate ALL the events in the document, not just the one the queue sampled.

THE SEED
--------
The extraction shown on the right is a reading aid, labelled the *seed*: the
union of every verifiable event a reference run found in this document (prompt 5
by default). "Accept seed as gold" is one click for the common case where it is
already right, but the fields start blank, so the default costs a decision
rather than a nod.

DOCUMENTS ARE PREFETCHED, NOT READ LIVE
---------------------------------------
The document text comes from `eval/annotation_documents.json`, a store holding
only the queue's 167 documents (~2 MB), built once by
`eval/prefetch_annotation_documents.py`. It loads in ~14 ms.

The alternative — reading `benchmark_ner/outputs/documents.parquet` on start —
scanned 57 MB to keep 1.8 MB, cost ~1.9 s, and tied the reviewer to a gitignored
bulk artefact a fresh checkout does not have. The store is built automatically on
first run if it is absent, so this costs no setup; after that the parquet is
never touched, and nothing is read on a rerun.

Storage: `eval/human_annotations.csv`, built on first run from the queue and the
document store. Written atomically, with one timestamped backup per session
before the first write.

Overrides:
    HUMAN_ANNOTATIONS_CSV   where annotations live      (default eval/human_annotations.csv)
    ANNOTATION_QUEUE_CSV    which documents to annotate (default eval/production_validation.csv)
    ANNOTATION_DOCUMENTS    prefetched document store   (default eval/annotation_documents.json)
    ANNOTATION_DOCUMENTS_PARQUET
                            bulk source for that store  (default benchmark_ner/outputs/documents.parquet)
    ANNOTATION_SEED_RUN     reference run for the seed  (default outputs/event_extractions/event_extractions.jsonl)
    ANNOTATOR               name stamped on each row
"""
from __future__ import annotations

import csv
import html
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

DEFAULT_ANNOTATIONS = REPO_ROOT / "eval" / "human_annotations.csv"
DEFAULT_QUEUE = REPO_ROOT / "eval" / "production_validation.csv"
# What the app reads: only the queue's documents, ~2 MB, no pyarrow needed.
DEFAULT_DOCUMENT_STORE = REPO_ROOT / "eval" / "annotation_documents.json"
# What the store is built from, once: 10,000 documents, 57 MB, gitignored.
DEFAULT_DOCUMENTS_PARQUET = REPO_ROOT / "benchmark_ner" / "outputs" / "documents.parquet"
DEFAULT_SEED_RUN = REPO_ROOT / "outputs" / "event_extractions" / "event_extractions.jsonl"

# Carried over from the queue so the annotation file stands alone, and so
# results can still be segmented by the strata the queue was sampled on.
SEED_COLUMNS = (
    "asset_key", "review_rank", "stratum", "title", "content_url", "language",
    "queued_events", "seed_event_count",
    "seed_hazard", "seed_dates", "seed_locations", "seed_impacts", "seed_evidence",
)
# Everything a human writes. `gold_*` is the annotation proper; the rest is
# provenance, and is what lets a second annotator's pass be compared to a first.
ANNOTATION_COLUMNS = (
    "gold_is_event", "gold_hazards", "gold_dates", "gold_locations", "gold_impacts",
    "gold_uncertain", "notes",
    "annotation_status", "annotator", "annotated_at", "seconds_spent",
)
COLUMNS = SEED_COLUMNS + ANNOTATION_COLUMNS

IS_EVENT_CHOICES = ("yes", "no", "unclear")
STATUS_DONE = "done"

# How much of a fragment must be found before we call it located. Evidence is
# often a faithful quote with the whitespace changed, which a strict equality
# test would report as a fabrication.
_FRAGMENT_PREFIX_WORDS = 8
# Shorter than this and a fragment matches too much of any document to mean
# anything ("the flood", "in 2010").
_MIN_FRAGMENT_CHARS = 12
# Extractors stitch a quote out of separated pieces: "Federal Office...
# triggered the system in the context of floods on the Oder river in 2010."
# Each piece is verbatim; the whole string is not, so locate the pieces.
_ELLIPSIS = re.compile(r"\s*(?:\.{3,}|\u2026)\s*")


class AnnotationError(ValueError):
    """Raised when the queue or document source is missing or malformed."""


# ---------------------------------------------------------------------------
# CSV plumbing (same contract as gold_validation_app: atomic write + backup)
# ---------------------------------------------------------------------------

def _split(value: str) -> list[str]:
    return [p.strip() for p in str(value or "").split("|") if p.strip()]


def _join(parts: Iterable[str]) -> str:
    seen: list[str] = []
    for p in parts:
        p = str(p).strip()
        if p and p not in seen:
            seen.append(p)
    return " | ".join(seen)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    csv.field_size_limit(10 ** 9)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [{k: (v if v is not None else "") for k, v in r.items()} for r in reader]
    return fieldnames, rows


def write_csv_atomic(path: Path, fieldnames: Iterable[str], rows: Iterable[dict[str, str]]) -> None:
    path = path.resolve()
    fieldnames = list(fieldnames)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({c: row.get(c, "") for c in fieldnames})
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        finally:
            raise


def create_backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak.{stamp}")
    counter = 2
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak.{stamp}.{counter}")
        counter += 1
    shutil.copy2(path, backup)
    return backup


# ---------------------------------------------------------------------------
# Bootstrap: queue -> annotation skeleton
# ---------------------------------------------------------------------------

def load_seed_run(path: Path, asset_keys: set[str]) -> dict[str, list[dict]]:
    """Every verifiable event the reference run found, per document."""
    events: dict[str, list[dict]] = {}
    if not path.exists():
        return events
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            key = obj.get("asset_key")
            if key not in asset_keys:
                continue
            verifiable = obj.get("is_verifiable_event")
            if verifiable is True or str(verifiable).strip().lower() == "true":
                events.setdefault(key, []).append(obj)
    return events


def build_annotations(queue_path: Path, out_path: Path,
                      seed_run_path: Path = DEFAULT_SEED_RUN) -> list[dict[str, str]]:
    """One blank annotation row per queued *document*, seeded with a reference run.

    Rows are collapsed by asset_key: the queue samples events, and annotating the
    same document twice would produce two half-annotations that cannot be merged.
    """
    if not queue_path.exists():
        raise AnnotationError(
            f"Review queue not found: {queue_path}\n"
            "Build it first:  python3 eval/prefill_gold_validation.py"
        )
    _, rows = read_csv(queue_path)
    queued = [r for r in rows if str(r.get("in_queue", "")).strip().upper() == "Y"]
    if not queued:
        raise AnnotationError(f"No rows with in_queue == Y in {queue_path}")

    def rank(value) -> int:
        try:
            return int(value or 10 ** 9)
        except (TypeError, ValueError):
            return 10 ** 9

    by_doc: dict[str, list[dict]] = {}
    for r in queued:
        by_doc.setdefault(r.get("asset_key", ""), []).append(r)

    seed_events = load_seed_run(seed_run_path, set(by_doc))

    out: list[dict[str, str]] = []
    for key, queue_rows_for_doc in by_doc.items():
        first = queue_rows_for_doc[0]
        # Prefer the full run: the queue holds only the sampled events, and a
        # partial seed would quietly bias an "accept seed as gold" click.
        events = seed_events.get(key)
        if events is None:
            # A document-level queue (eval/sample_documents_for_annotation.py)
            # can legitimately contain documents the run declined — that is the
            # point of it. Those get a genuinely empty seed, so the screen reads
            # "0 events" instead of showing the queue row as a phantom one.
            declined = str(first.get("run_found_events", "")).strip() == "0"
            events = [] if declined else queue_rows_for_doc
        row = {c: "" for c in COLUMNS}
        row.update({
            "asset_key": key,
            "review_rank": str(min(rank(r.get("review_rank")) for r in queue_rows_for_doc)),
            "stratum": first.get("stratum", ""),
            "title": first.get("title", ""),
            "content_url": first.get("content_url", ""),
            "language": first.get("language", ""),
            "queued_events": str(len(queue_rows_for_doc)),
            "seed_event_count": str(len(events)),
            "seed_hazard": _join(h for e in events for h in _split(e.get("event_hazard"))),
            "seed_dates": _join(d for e in events for d in _split(e.get("event_dates"))),
            "seed_locations": _join(l for e in events for l in _split(e.get("affected_locations"))),
            "seed_impacts": _join(i for e in events for i in _split(e.get("key_impacts"))),
            "seed_evidence": _join(s for e in events for s in _split(e.get("evidence_snippets"))),
        })
        out.append(row)
    out.sort(key=lambda r: rank(r["review_rank"]))
    write_csv_atomic(out_path, COLUMNS, out)
    return out


def build_document_store(parquet_path: Path, asset_keys: set[str], out_path: Path) -> dict[str, dict]:
    """Extract just the queue's documents from the bulk parquet, once.

    The parquet is 10,000 documents and 57 MB; the annotation queue needs 167 of
    them and 1.8 MB of text. Reading the whole thing on every app start cost ~2 s
    and made the reviewer depend on a gitignored bulk artefact that a fresh
    checkout does not have. This writes the subset the app actually reads.
    """
    if not parquet_path.exists():
        raise AnnotationError(
            f"Cannot build the document store: {parquet_path} not found.\n"
            "Fetch the documents first:  make ner-fetch"
        )
    import pyarrow.parquet as pq

    table = pq.read_table(parquet_path, columns=["asset_key", "text", "char_count"])
    keys = table.column("asset_key").to_pylist()
    texts = table.column("text").to_pylist()
    counts = table.column("char_count").to_pylist()

    documents: dict[str, dict] = {}
    for key, text, count in zip(keys, texts, counts):
        if key in asset_keys and key not in documents:
            documents[key] = {"text": text or "", "char_count": int(count or 0)}

    payload = {
        "source": str(parquet_path),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "document_count": len(documents),
        "missing": sorted(asset_keys - set(documents)),
        "documents": documents,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{out_path.name}.", suffix=".tmp",
                                    dir=out_path.parent, text=True)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp_path, out_path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        finally:
            raise
    return documents


def load_document_store(path: Path) -> tuple[dict[str, dict], dict]:
    """The prefetched documents and the store's own metadata."""
    if not path.exists():
        return {}, {}
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("documents", {}), {
        k: v for k, v in payload.items() if k != "documents"}


# ---------------------------------------------------------------------------
# Evidence handling
# ---------------------------------------------------------------------------

def _normalise_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def locate_snippet(doc_text: str, snippet: str) -> tuple[list[tuple[int, int]], str]:
    """Where `snippet` sits in `doc_text`, and how completely.

    Returns (spans, kind) with kind one of exact / partial / none. Offsets index
    a whitespace-normalised copy of the document, which is what the viewer
    renders — quoting across a line break is normal and must not read as a
    fabricated quote. Ellipsis-separated fragments are located independently,
    for the same reason.
    """
    hay = _normalise_ws(doc_text).casefold()
    if not hay or not str(snippet or "").strip():
        return [], "none"

    fragments = [f for f in _ELLIPSIS.split(_normalise_ws(snippet))
                 if len(f.strip()) >= _MIN_FRAGMENT_CHARS]
    if not fragments:
        return [], "none"

    spans: list[tuple[int, int]] = []
    found = 0
    for fragment in fragments:
        needle = fragment.casefold()
        at = hay.find(needle)
        if at >= 0:
            spans.append((at, at + len(needle)))
            found += 1
            continue
        words = needle.split()
        if len(words) > _FRAGMENT_PREFIX_WORDS:
            prefix = " ".join(words[:_FRAGMENT_PREFIX_WORDS])
            at = hay.find(prefix)
            if at >= 0:
                spans.append((at, at + len(prefix)))
                found += 1
    if found == len(fragments):
        return spans, "exact"
    return spans, "partial" if found else "none"


def render_document(doc_text: str, snippets: list[str]) -> str:
    """The document as HTML with every located evidence fragment marked."""
    text = _normalise_ws(doc_text)
    spans: list[tuple[int, int, str]] = []
    for snip in snippets:
        located, kind = locate_snippet(doc_text, snip)
        spans.extend((start, end, kind) for start, end in located)
    spans.sort()

    merged: list[list] = []
    for start, end, kind in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
            if merged[-1][2] == "partial":
                merged[-1][2] = kind
        else:
            merged.append([start, end, kind])

    out: list[str] = []
    cursor = 0
    for start, end, kind in merged:
        out.append(html.escape(text[cursor:start]))
        colour = "#ffe08a" if kind == "exact" else "#cfe8ff"
        out.append(
            f'<mark style="background:{colour};color:#111;padding:1px 2px;border-radius:2px">'
            f"{html.escape(text[start:end])}</mark>")
        cursor = end
    out.append(html.escape(text[cursor:]))
    return "".join(out)


# ---------------------------------------------------------------------------
# Queue navigation
# ---------------------------------------------------------------------------

def is_done(row: dict) -> bool:
    return str(row.get("annotation_status", "")).strip().lower() == STATUS_DONE


def first_unannotated(rows: list[dict]) -> int:
    for i, r in enumerate(rows):
        if not is_done(r):
            return i
    return 0


def next_unannotated_after(rows: list[dict], pos: int) -> int:
    for i in range(pos + 1, len(rows)):
        if not is_done(rows[i]):
            return i
    ahead = first_unannotated(rows)
    if not is_done(rows[ahead]) and ahead != pos:
        return ahead
    return min(pos + 1, len(rows) - 1)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser().resolve() if value else default


def _hazard_vocabulary() -> list[str]:
    """The PreventionWeb labels the models were told to emit."""
    try:
        from benchmark_ner.hazard_lexicon import ALL_LABELS
        return list(ALL_LABELS)
    except Exception:
        return []


def _form_values(source: dict, vocab: list[str], prefix: str) -> dict:
    """The widget state for one document, from `{prefix}is_event` etc. fields."""
    hazards = _split(source.get(f"{prefix}hazards") or source.get(f"{prefix}hazard"))
    return {
        "is_event": (source.get(f"{prefix}is_event") or "").strip() or IS_EVENT_CHOICES[0],
        "hazards": [h for h in hazards if h in vocab],
        "hazards_other": _join(h for h in hazards if h not in vocab),
        "dates": source.get(f"{prefix}dates", ""),
        "locations": source.get(f"{prefix}locations", ""),
        "impacts": source.get(f"{prefix}impacts", ""),
    }


def _seed_form_state(pos: int, row: dict, vocab: list[str]) -> None:
    """Load a document's saved annotation into the form when the document changes.

    The widgets own their state from then on, so passing `default=`/`value=` as
    well would make Streamlit ignore it and warn, and would silently undo an
    "Accept seed as gold" click on the next rerun.

    Reloading is triggered by the document changing rather than by the widget
    keys being absent: Streamlit drops the state of widgets a run did not
    render, so navigating away and back would otherwise show a blank form for a
    document already annotated.
    """
    import streamlit as st

    if st.session_state.get("form_loaded_for") == row["asset_key"]:
        return
    values = _form_values(row, vocab, "gold_")
    if not str(row.get("gold_is_event", "")).strip():
        values["is_event"] = IS_EVENT_CHOICES[0]
    for name, value in values.items():
        st.session_state[f"{name}_{pos}"] = value
    st.session_state[f"uncertain_{pos}"] = (
        str(row.get("gold_uncertain", "")).strip().upper() == "Y")
    st.session_state[f"notes_{pos}"] = row.get("notes", "")
    st.session_state["form_loaded_for"] = row["asset_key"]


def _fill_form_state(pos: int, source: dict, vocab: list[str]) -> None:
    """Overwrite the form with the seed extraction."""
    import streamlit as st

    for name, value in _form_values(source, vocab, "").items():
        st.session_state[f"{name}_{pos}"] = value


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Human annotation", layout="wide")

    ann_path = _env_path("HUMAN_ANNOTATIONS_CSV", DEFAULT_ANNOTATIONS)
    queue_path = _env_path("ANNOTATION_QUEUE_CSV", DEFAULT_QUEUE)
    store_path = _env_path("ANNOTATION_DOCUMENTS", DEFAULT_DOCUMENT_STORE)
    parquet_path = _env_path("ANNOTATION_DOCUMENTS_PARQUET", DEFAULT_DOCUMENTS_PARQUET)
    seed_path = _env_path("ANNOTATION_SEED_RUN", DEFAULT_SEED_RUN)

    try:
        if not ann_path.exists():
            built = build_annotations(queue_path, ann_path, seed_path)
            st.toast(f"Created {ann_path.name} — {len(built)} documents")
        fieldnames, rows = read_csv(ann_path)
    except AnnotationError as exc:
        st.error(str(exc))
        st.stop()

    missing = [c for c in COLUMNS if c not in fieldnames]
    if missing:
        st.error(f"{ann_path} is missing columns: {', '.join(missing)}. "
                 "Delete it to rebuild, or add them by hand.")
        st.stop()

    backup_key = f"backup::{ann_path}"
    if backup_key not in st.session_state:
        st.session_state[backup_key] = str(create_backup(ann_path))

    asset_keys = tuple(sorted({r["asset_key"] for r in rows}))

    # Read the prefetched store. Build it once if it is not there yet, so the
    # app still works with no setup — but never read the 57 MB parquet again
    # after that, and never on a rerun.
    @st.cache_resource(show_spinner="Loading prefetched documents…")
    def _document_store(store: str, parquet: str, keys: tuple[str, ...]) -> tuple[dict, dict]:
        documents, meta = load_document_store(Path(store))
        if documents:
            return documents, meta
        documents = build_document_store(Path(parquet), set(keys), Path(store))
        _, meta = load_document_store(Path(store))
        return documents, dict(meta, just_built=True)

    try:
        docs, store_meta = _document_store(str(store_path), str(parquet_path), asset_keys)
    except AnnotationError as exc:
        st.warning(str(exc))
        docs, store_meta = {}, {}

    # Highlighting is pure string work over ~12 KB, but it would otherwise run
    # again on every button click. Key it on the document and its snippets.
    @st.cache_data(show_spinner=False)
    def _rendered(doc_text: str, snippets: tuple[str, ...]) -> str:
        return render_document(doc_text, list(snippets))

    if "pos" not in st.session_state:
        st.session_state.pos = first_unannotated(rows)
    if "item_started" not in st.session_state:
        st.session_state.item_started = time.monotonic()

    # -- sidebar -----------------------------------------------------------
    done = sum(1 for r in rows if is_done(r))
    st.sidebar.header("Progress")
    st.sidebar.progress(done / len(rows) if rows else 0.0)
    st.sidebar.write(f"**{done} / {len(rows)}** documents annotated")
    yes = sum(1 for r in rows if is_done(r) and r.get("gold_is_event") == "yes")
    no = sum(1 for r in rows if is_done(r) and r.get("gold_is_event") == "no")
    unclear = sum(1 for r in rows if is_done(r) and r.get("gold_is_event") == "unclear")
    st.sidebar.write(f"reports an event: {yes}  ·  none: {no}  ·  unclear: {unclear}")
    flagged = sum(1 for r in rows if str(r.get("gold_uncertain", "")).strip().upper() == "Y")
    if flagged:
        st.sidebar.write(f"🚩 {flagged} flagged for a second look")

    annotator = st.sidebar.text_input(
        "Annotator", value=os.environ.get("ANNOTATOR", "") or _last_annotator(rows))

    if st.sidebar.button("Jump to next unannotated", use_container_width=True):
        st.session_state.pos = first_unannotated(rows)
        st.session_state.item_started = time.monotonic()
        st.rerun()
    nav = st.sidebar.columns(2)
    if nav[0].button("← Prev", use_container_width=True, disabled=st.session_state.pos <= 0):
        st.session_state.pos -= 1
        st.session_state.item_started = time.monotonic()
        st.rerun()
    if nav[1].button("Next →", use_container_width=True,
                     disabled=st.session_state.pos >= len(rows) - 1):
        st.session_state.pos += 1
        st.session_state.item_started = time.monotonic()
        st.rerun()

    jump = st.sidebar.number_input("Go to document", min_value=1, max_value=len(rows),
                                   value=st.session_state.pos + 1, step=1)
    if int(jump) - 1 != st.session_state.pos:
        st.session_state.pos = int(jump) - 1
        st.session_state.item_started = time.monotonic()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.caption(f"File: `{ann_path.name}`")
    st.sidebar.caption(f"Backup: `{Path(st.session_state[backup_key]).name}`")
    if docs:
        built = store_meta.get("built_at", "?")
        st.sidebar.caption(
            f"Documents: `{store_path.name}` — {len(docs)} prefetched, built {built}")
        if store_meta.get("just_built"):
            st.toast(f"Prefetched {len(docs)} documents into {store_path.name}")
        for key in store_meta.get("missing", []):
            st.sidebar.warning(f"No fetched text for {key}")
        if st.sidebar.button("Rebuild document store", use_container_width=True,
                             help="Re-extract the documents from the bulk parquet."):
            try:
                build_document_store(parquet_path, set(asset_keys), store_path)
                _document_store.clear()
                st.rerun()
            except AnnotationError as exc:
                st.sidebar.error(str(exc))
    else:
        st.sidebar.warning(
            f"No document text. Build the store with `make annotate-prefetch` "
            f"(it needs {parquet_path.name}, from `make ner-fetch`); until then "
            "only the seed evidence is shown.")

    # -- current item ------------------------------------------------------
    pos = max(0, min(int(st.session_state.pos), len(rows) - 1))
    st.session_state.pos = pos
    row = rows[pos]
    doc = docs.get(row["asset_key"], {})
    snippets = _split(row.get("seed_evidence"))

    st.title(row.get("title") or "(untitled)")
    head = st.columns([3, 1])
    head[0].caption(
        f"Document **{pos + 1} of {len(rows)}** · stratum `{row.get('stratum','-')}`"
        f" · language {row.get('language') or '?'} · `{row.get('asset_key','')}`")
    if row.get("content_url"):
        head[1].link_button("Open source ↗", row["content_url"], use_container_width=True)
    if is_done(row):
        st.success(
            f"Annotated as **{row.get('gold_is_event','?')}** by "
            f"{row.get('annotator') or 'unknown'} on {row.get('annotated_at','?')} — "
            "editing below overwrites it.")

    left, right = st.columns([1.15, 0.85], gap="large")

    with left:
        st.subheader("Fetched document")
        if doc:
            shown, total = len(doc["text"]), int(doc.get("char_count") or 0)
            note = f"{shown:,} characters — the window the models were given"
            if total > shown:
                note += f" (source document is {total:,})"
            st.caption(note)
            body = _rendered(doc["text"], tuple(snippets))
            st.markdown(
                f'<div style="height:620px;overflow-y:auto;padding:14px;border:1px solid '
                f'rgba(128,128,128,.35);border-radius:6px;line-height:1.6;font-size:0.92rem;'
                f'white-space:pre-wrap">{body}</div>',
                unsafe_allow_html=True)
            st.caption("Highlighted: 🟨 evidence found verbatim · "
                       "🟦 quote only partly found")
        else:
            st.info("No fetched text for this asset_key.")

        st.subheader("Seed evidence snippets")
        if not snippets:
            st.caption("_(the seed run cited none)_")
        for snip in snippets:
            _, kind = locate_snippet(doc.get("text", ""), snip)
            mark = {
                "exact": "✓ found in the document",
                "partial": "≈ only part of the quote found",
                "none": "✗ not found — check whether it is translated, "
                        "paraphrased, or invented",
            }[kind if doc else "none"]
            st.markdown(f"- {snip}  \n  <small><em>{mark}</em></small>",
                        unsafe_allow_html=True)

    with right:
        n_seed = row.get("seed_event_count") or "?"
        with st.expander(f"Seed extraction — {n_seed} event(s) merged "
                         "(reading aid, not ground truth)", expanded=True):
            st.markdown(f"**Hazards:** {row.get('seed_hazard') or '-'}")
            st.markdown(f"**Dates:** {row.get('seed_dates') or '-'}")
            st.markdown(f"**Locations:** {row.get('seed_locations') or '-'}")
            st.markdown(f"**Impacts:** {row.get('seed_impacts') or '-'}")

        try:
            if int(row.get("seed_event_count") or 0) > 5:
                st.caption("⚠️ Large seed — check it against the document before accepting.")
        except (TypeError, ValueError):
            pass

        seed_is_empty = str(row.get("seed_event_count") or "0").strip() in {"", "0"}
        if seed_is_empty:
            st.info("The reference run found **no event** in this document. "
                    "Read it and decide independently — if it really reports "
                    "none, *🚫 No event & next* records a true negative.")

        if st.button("⤵ Accept seed as gold", use_container_width=True,
                     disabled=seed_is_empty,
                     help="Copy the seed extraction into the form below. Review, then save."):
            _fill_form_state(pos, {
                "is_event": "yes",
                "hazards": row.get("seed_hazard", ""),
                "dates": row.get("seed_dates", ""),
                "locations": row.get("seed_locations", ""),
                "impacts": row.get("seed_impacts", ""),
            }, _hazard_vocabulary())
            st.rerun()

        st.subheader("Ground truth")
        st.caption("Everything **this document** reports, not just the event the "
                   "queue sampled — gold has to be complete or precision is "
                   "measuring the sampling.")

        vocab = _hazard_vocabulary()
        _seed_form_state(pos, row, vocab)

        is_event = st.radio(
            "Does this document report at least one specific, verifiable event?",
            IS_EVENT_CHOICES, horizontal=True, key=f"is_event_{pos}")
        hazards = st.multiselect(
            "Hazards (PreventionWeb labels)", vocab, key=f"hazards_{pos}")
        hazards_other = st.text_input(
            "Hazards not in the list (| separated)", key=f"hazards_other_{pos}")
        dates = st.text_input("Dates (| separated)", key=f"dates_{pos}")
        locations = st.text_area("Locations (| separated)", height=70,
                                 key=f"locations_{pos}")
        impacts = st.text_area("Impacts (| separated)", height=70, key=f"impacts_{pos}")
        uncertain = st.checkbox("🚩 Flag — I am not confident in this annotation",
                                key=f"uncertain_{pos}")
        notes = st.text_input("Notes", key=f"notes_{pos}")

        def _persist(values: dict) -> None:
            elapsed = max(0, int(time.monotonic() - st.session_state.item_started))
            prior = int(row.get("seconds_spent") or 0)
            rows[pos].update(values)
            rows[pos].update({
                "annotation_status": STATUS_DONE,
                "annotator": annotator.strip(),
                "annotated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "seconds_spent": str(prior + elapsed),
            })
            write_csv_atomic(ann_path, fieldnames, rows)

        actions = st.columns([1.3, 1])
        if actions[0].button("💾 Save & next", type="primary", use_container_width=True):
            _persist({
                "gold_is_event": is_event,
                "gold_hazards": _join(hazards + _split(hazards_other)),
                "gold_dates": _join(_split(dates)),
                "gold_locations": _join(_split(locations)),
                "gold_impacts": _join(_split(impacts)),
                "gold_uncertain": "Y" if uncertain else "",
                "notes": notes.strip(),
            })
            st.session_state.pos = next_unannotated_after(rows, pos)
            st.session_state.item_started = time.monotonic()
            st.rerun()

        if actions[1].button("🚫 No event & next", use_container_width=True,
                             help="This document reports no specific, verifiable event."):
            _persist({
                "gold_is_event": "no",
                "gold_hazards": "", "gold_dates": "", "gold_locations": "", "gold_impacts": "",
                "gold_uncertain": "Y" if uncertain else "",
                "notes": notes.strip(),
            })
            st.session_state.pos = next_unannotated_after(rows, pos)
            st.session_state.item_started = time.monotonic()
            st.rerun()

        if done == len(rows):
            st.success("All documents annotated. Score any run:\n\n"
                       "`make annotate-score`")


def _last_annotator(rows: list[dict]) -> str:
    for r in reversed(rows):
        name = str(r.get("annotator", "")).strip()
        if name:
            return name
    return ""


if __name__ == "__main__":
    main()
