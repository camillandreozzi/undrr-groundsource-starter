"""
Blind event-level annotation — one record per occurrence, not one per document.

Run from the repository root:

    make event-annotate
    # or: python3 -m streamlit run eval/event_annotation_app.py

WHY A NEW APP
-------------
`human_annotation_app.py` records a document's hazards, dates and places as
three unlinked lists, which is exactly what cannot answer "did the system keep
hazard, year and place together?". And it shows the production run's output as
a seed with an "Accept seed as gold" button; the resulting gold is
byte-identical to the seed on 76–91% of fields (docs/VALIDATION_METHODS.md).

This app shows the window and nothing else: no seed, no model output, no
earlier annotation, and not the sampling stratum. Each event is entered as its
own record — hazard, year span, the places it affected, and verbatim quotes
from the window that establish it. Those quotes are what the matcher anchors
on (`eval/event_matching.py`), so a quote that cannot be found in the window is
refused at save time.

The guideline is `eval/EVENT_LEVEL_PROTOCOL.md` §1; a summary is in the sidebar.

Storage, both written atomically with a timestamped backup per session:
    eval/event_level_windows.csv   one row per window: status, event count, time
    eval/event_level_gold.csv      one row per gold event

Overrides:
    EVENT_QUEUE_CSV       the drawn sample   (default eval/event_level_queue.csv)
    EVENT_WINDOWS_CSV     window status      (default eval/event_level_windows.csv)
    EVENT_GOLD_CSV        gold events        (default eval/event_level_gold.csv)
    ANNOTATOR             name stamped on each window
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from eval.human_annotation_app import (  # noqa: E402
    _env_path, _hazard_vocabulary, create_backup, load_document_store,
    locate_snippet, read_csv, render_document, write_csv_atomic,
)

EVAL = REPO_ROOT / "eval"
DEFAULT_QUEUE = EVAL / "event_level_queue.csv"
DEFAULT_WINDOWS = EVAL / "event_level_windows.csv"
DEFAULT_GOLD = EVAL / "event_level_gold.csv"
DOCUMENT_STORES = (EVAL / "annotation_documents.json",
                   EVAL / "annotation_documents_document_sample.json")

# No stratum, no prior gold, no seed: the queue's other columns stay in the queue.
WINDOW_COLUMNS = (
    "asset_key", "review_rank", "title", "content_url",
    "window_status", "has_events", "n_events", "all_listed", "notes",
    "annotator", "annotated_at", "seconds_spent",
)
GOLD_COLUMNS = (
    "asset_key", "gold_event_id", "hazard_primary", "hazard_secondary",
    "year_start", "year_end", "date_text", "locations",
    "support_quotes", "support_spans", "verifiable", "notes",
)
EVENT_FIELDS = ("hazard_primary", "hazard_secondary", "year_start", "year_end",
                "date_text", "locations", "support_quotes", "verifiable", "notes")
STATUS_DONE = "done"
MAX_QUOTES = 5
_YEAR = re.compile(r"^(1[0-9]\d\d|20\d\d)$")

GUIDELINE = """
**One event = one concrete past or current occurrence of a hazard.**

- A cascade from one trigger told as one occurrence (earthquake → tsunami,
  cyclone → flood) is **one** event: primary = the trigger, secondary = the rest.
- Same hazard, different years → **separate** events.
- Same hazard and year, unconnected places told as separate occurrences →
  **separate** events. One named event over many places ("2010 Pakistan
  floods") → **one** event.
- Multi-year drought or epidemic → one event with a year span.
- **Not events:** forecasts, scenarios, exercises, projects, generic
  recurrence ("floods hit X every year").

**Verifiable** = the window states the hazard, a time (at least a year) and at
least one directly affected place. Record concrete events that miss one of
these too, marked *not verifiable*. Coarser than a year (a decade,
"recently") → leave the years blank.

**Years** from the text only — never the publication year.

**Locations:** every place the window names as directly affected by *this*
event, at every level it names (country and sub-national), one per line, as
written.

**Support quotes:** copy from the document, one per line. Quote every passage
that reports this occurrence (up to 5); at least the one that names it.
""".strip()


class EventAnnotationError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def build_windows(queue_path: Path, windows_path: Path, gold_path: Path) -> list[dict]:
    """The window-status file from the queue, and an empty gold file beside it."""
    if not queue_path.exists():
        raise EventAnnotationError(
            f"Sample not found: {queue_path}\nDraw it first:  make event-sample")
    _, queue = read_csv(queue_path)
    queue = [r for r in queue if str(r.get("in_queue", "")).strip().upper() == "Y"]
    if not queue:
        raise EventAnnotationError(f"No rows with in_queue == Y in {queue_path}")
    queue.sort(key=lambda r: int(r.get("review_rank") or 10 ** 9))
    rows = [{**{c: "" for c in WINDOW_COLUMNS},
             **{c: r.get(c, "") for c in ("asset_key", "review_rank", "title", "content_url")}}
            for r in queue]
    write_csv_atomic(windows_path, WINDOW_COLUMNS, rows)
    if not gold_path.exists():
        write_csv_atomic(gold_path, GOLD_COLUMNS, [])
    return rows


def replace_window_events(gold_rows: list[dict], asset_key: str,
                          new_rows: list[dict]) -> list[dict]:
    """Every gold row, with this window's replaced, in review order of saving."""
    return [r for r in gold_rows if r.get("asset_key") != asset_key] + new_rows


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def split_lines(value: str, also_pipes: bool = False) -> list[str]:
    parts = re.split(r"[\n|]" if also_pipes else r"\n", str(value or ""))
    seen: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.append(p)
    return seen


def support_spans(doc_text: str, quotes: list[str]) -> str:
    spans = []
    for quote in quotes:
        found, _kind = locate_snippet(doc_text, quote)
        spans.extend([list(s) for s in found])
    return json.dumps(spans)


def validate_event(event: dict, doc_text: str, n: int) -> tuple[dict, list[str]]:
    """One event from the form, as a gold row, and what is wrong with it.

    `event` holds the raw widget values for EVENT_FIELDS; `n` is its 1-based
    position, used in messages.
    """
    errors: list[str] = []
    label = f"Event {n}"

    primary = str(event.get("hazard_primary") or "").strip()
    secondary = [h for h in (event.get("hazard_secondary") or []) if h and h != primary]
    if not primary:
        errors.append(f"{label}: choose a primary hazard.")

    start = str(event.get("year_start") or "").strip()
    end = str(event.get("year_end") or "").strip()
    for name, value in (("start year", start), ("end year", end)):
        if value and not _YEAR.match(value):
            errors.append(f"{label}: {name} '{value}' is not a four-digit year.")
    if end and not start:
        errors.append(f"{label}: an end year needs a start year.")
    if start and not end:
        end = start
    if _YEAR.match(start) and _YEAR.match(end) and int(end) < int(start):
        errors.append(f"{label}: end year is before start year.")

    locations = split_lines(event.get("locations"), also_pipes=True)
    quotes = split_lines(event.get("support_quotes"))
    verifiable = event.get("verifiable")
    if verifiable not in ("yes", "no"):
        errors.append(f"{label}: say whether it is verifiable.")
    if verifiable == "yes" and not (primary and start and locations):
        errors.append(f"{label}: verifiable needs a hazard, a year and at least one location "
                      "— otherwise mark it not verifiable.")
    if not quotes:
        errors.append(f"{label}: add at least one support quote.")
    if len(quotes) > MAX_QUOTES:
        errors.append(f"{label}: at most {MAX_QUOTES} support quotes.")
    for quote in quotes:
        _spans, kind = locate_snippet(doc_text, quote)
        if kind != "exact":
            errors.append(f"{label}: quote not found verbatim in the window — "
                          f"copy it from the document: “{quote[:70]}”")

    row = {
        "hazard_primary": primary,
        "hazard_secondary": " | ".join(secondary),
        "year_start": start,
        "year_end": end,
        "date_text": str(event.get("date_text") or "").strip(),
        "locations": " | ".join(locations),
        "support_quotes": "\n".join(quotes),
        "support_spans": support_spans(doc_text, quotes),
        "verifiable": verifiable or "",
        "notes": str(event.get("notes") or "").strip(),
    }
    return row, errors


def validate_window(has_events: Optional[str], events: list[dict], all_listed: bool,
                    doc_text: str, asset_key: str) -> tuple[list[dict], list[str]]:
    """The window's gold rows, numbered, and every error across them."""
    if has_events not in ("yes", "no"):
        return [], ["Say whether this window reports any concrete event."]
    if has_events == "no":
        return [], [] if not events else [
            "You marked the window as having no event but listed events — remove them first."]
    if not events:
        return [], ["Add at least one event, or mark the window as having none."]
    rows: list[dict] = []
    errors = [] if all_listed else ["Confirm that every event in the window is listed."]
    for i, event in enumerate(events, start=1):
        row, errs = validate_event(event, doc_text, i)
        rows.append({"asset_key": asset_key, "gold_event_id": str(i), **row})
        errors.extend(errs)
    return rows, errors


# ---------------------------------------------------------------------------
# Form state
# ---------------------------------------------------------------------------

def _key(i: int, name: str) -> str:
    return f"ev{i}_{name}"


def _blank_event() -> dict:
    return {"hazard_primary": "", "hazard_secondary": [], "year_start": "", "year_end": "",
            "date_text": "", "locations": "", "support_quotes": "", "verifiable": None,
            "notes": ""}


def _event_from_row(row: dict) -> dict:
    return {
        "hazard_primary": row.get("hazard_primary", ""),
        "hazard_secondary": [h.strip() for h in str(row.get("hazard_secondary") or "").split("|")
                             if h.strip()],
        "year_start": row.get("year_start", ""),
        "year_end": row.get("year_end", "") if row.get("year_end") != row.get("year_start") else "",
        "date_text": row.get("date_text", ""),
        "locations": "\n".join(split_lines(row.get("locations"), also_pipes=True)),
        "support_quotes": row.get("support_quotes", ""),
        "verifiable": row.get("verifiable") or None,
        "notes": row.get("notes", ""),
    }


def _read_event(state, i: int) -> dict:
    return {f: state.get(_key(i, f)) for f in EVENT_FIELDS}


def _write_event(state, i: int, event: dict) -> None:
    for f in EVENT_FIELDS:
        state[_key(i, f)] = event.get(f, _blank_event()[f])


def _load_window(state, window: dict, events: list[dict]) -> None:
    for k in [k for k in state.keys() if str(k).startswith("ev")]:
        del state[k]
    state["n_events"] = len(events)
    for i, row in enumerate(events):
        _write_event(state, i, _event_from_row(row))
    state["has_events"] = window.get("has_events") or None
    state["all_listed"] = str(window.get("all_listed", "")).strip().upper() == "Y"
    state["window_notes"] = window.get("notes", "")
    state["loaded_for"] = window["asset_key"]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

def _is_done(row: dict) -> bool:
    return str(row.get("window_status", "")).strip().lower() == STATUS_DONE


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Event-level annotation", layout="wide")
    queue_path = _env_path("EVENT_QUEUE_CSV", DEFAULT_QUEUE)
    windows_path = _env_path("EVENT_WINDOWS_CSV", DEFAULT_WINDOWS)
    gold_path = _env_path("EVENT_GOLD_CSV", DEFAULT_GOLD)

    try:
        if not windows_path.exists():
            built = build_windows(queue_path, windows_path, gold_path)
            st.toast(f"Created {windows_path.name} — {len(built)} windows")
        _, windows = read_csv(windows_path)
        if not gold_path.exists():
            write_csv_atomic(gold_path, GOLD_COLUMNS, [])
        _, gold_rows = read_csv(gold_path)
    except EventAnnotationError as exc:
        st.error(str(exc))
        st.stop()

    for path in (windows_path, gold_path):
        flag = f"backup::{path}"
        if flag not in st.session_state:
            st.session_state[flag] = str(create_backup(path))

    @st.cache_resource(show_spinner="Loading windows…")
    def _texts() -> dict[str, str]:
        out: dict[str, str] = {}
        for store in DOCUMENT_STORES:
            documents, _ = load_document_store(store)
            out.update({k: v.get("text", "") for k, v in documents.items()})
        return out

    @st.cache_data(show_spinner=False)
    def _rendered(doc_text: str, quotes: tuple[str, ...]) -> str:
        return render_document(doc_text, list(quotes))

    texts = _texts()
    vocab = _hazard_vocabulary()
    state = st.session_state
    if "pos" not in state:
        state.pos = next((i for i, r in enumerate(windows) if not _is_done(r)), 0)
    if "item_started" not in state:
        state.item_started = time.monotonic()

    def go(pos: int) -> None:
        state.pos = max(0, min(pos, len(windows) - 1))
        state.item_started = time.monotonic()
        st.rerun()

    # -- sidebar -----------------------------------------------------------
    done = sum(1 for r in windows if _is_done(r))
    st.sidebar.header("Progress")
    st.sidebar.progress(done / len(windows) if windows else 0.0)
    st.sidebar.write(f"**{done} / {len(windows)}** windows annotated · "
                     f"{len(gold_rows)} events recorded")
    annotator = st.sidebar.text_input(
        "Annotator", value=os.environ.get("ANNOTATOR", "")
        or next((r["annotator"] for r in reversed(windows) if r.get("annotator")), ""))
    if st.sidebar.button("Jump to next unannotated", use_container_width=True):
        go(next((i for i, r in enumerate(windows) if not _is_done(r)), state.pos))
    nav = st.sidebar.columns(2)
    if nav[0].button("← Prev", use_container_width=True, disabled=state.pos <= 0):
        go(state.pos - 1)
    if nav[1].button("Next →", use_container_width=True, disabled=state.pos >= len(windows) - 1):
        go(state.pos + 1)
    with st.sidebar.expander("Guideline", expanded=False):
        st.markdown(GUIDELINE)
    st.sidebar.caption(f"Windows: `{windows_path.name}` · gold: `{gold_path.name}`")

    # -- current window ----------------------------------------------------
    pos = state.pos
    window = windows[pos]
    key = window["asset_key"]
    doc_text = texts.get(key, "")
    saved = sorted((r for r in gold_rows if r.get("asset_key") == key),
                   key=lambda r: int(r.get("gold_event_id") or 0))
    if state.get("loaded_for") != key:
        _load_window(state, window, saved)

    st.title(window.get("title") or "(untitled)")
    head = st.columns([3, 1])
    head[0].caption(f"Window **{pos + 1} of {len(windows)}** · {len(doc_text):,} characters "
                    f"— exactly what the models were given · `{key}`")
    if window.get("content_url"):
        head[1].link_button("Open source ↗", window["content_url"], use_container_width=True)
    if _is_done(window):
        st.success(f"Annotated by {window.get('annotator') or 'unknown'} on "
                   f"{window.get('annotated_at', '?')} — saving again overwrites it.")

    events = [_read_event(state, i) for i in range(state.n_events)]
    quotes = tuple(q for e in events for q in split_lines(e.get("support_quotes")))

    left, right = st.columns([1.1, 0.9], gap="large")
    with left:
        if not doc_text:
            st.error("No window text for this asset_key. Run `make annotate-prefetch`.")
        else:
            st.markdown(
                f'<div style="height:760px;overflow-y:auto;padding:14px;border:1px solid '
                f'rgba(128,128,128,.35);border-radius:6px;line-height:1.6;font-size:0.92rem;'
                f'white-space:pre-wrap">{_rendered(doc_text, quotes)}</div>',
                unsafe_allow_html=True)
            st.caption("Highlighted: your support quotes as found in the window.")

    with right:
        st.radio("Does this window report any concrete past or current event?",
                 ("yes", "no"), horizontal=True, key="has_events")

        for i in range(state.n_events):
            with st.container(border=True):
                top = st.columns([4, 1])
                top[0].markdown(f"**Event {i + 1}**")
                if top[1].button("Remove", key=f"rm_{i}", use_container_width=True):
                    for j in range(i, state.n_events - 1):
                        _write_event(state, j, _read_event(state, j + 1))
                    for f in EVENT_FIELDS:
                        state.pop(_key(state.n_events - 1, f), None)
                    state.n_events -= 1
                    st.rerun()
                st.selectbox("Primary hazard", ["", *vocab], key=_key(i, "hazard_primary"))
                st.multiselect("Secondary (cascading) hazards", vocab,
                               key=_key(i, "hazard_secondary"))
                years = st.columns(3)
                years[0].text_input("Start year", key=_key(i, "year_start"))
                years[1].text_input("End year (if a span)", key=_key(i, "year_end"))
                years[2].text_input("Date as written (optional)", key=_key(i, "date_text"))
                st.text_area("Affected locations — one per line", height=90,
                             key=_key(i, "locations"))
                st.text_area("Support quotes — one per line, copied from the window",
                             height=110, key=_key(i, "support_quotes"))
                for quote in split_lines(state.get(_key(i, "support_quotes"))):
                    _spans, kind = locate_snippet(doc_text, quote)
                    mark = "✓ found" if kind == "exact" else "✗ not found verbatim"
                    st.caption(f"{mark}: “{quote[:80]}”")
                st.radio("Verifiable (hazard, year and place all stated)?", ("yes", "no"),
                         horizontal=True, key=_key(i, "verifiable"))
                st.text_input("Notes", key=_key(i, "notes"))

        if st.button("➕ Add event", use_container_width=True):
            _write_event(state, state.n_events, _blank_event())
            state.n_events += 1
            st.rerun()

        st.checkbox("Every concrete event in this window is listed above", key="all_listed")
        st.text_input("Window notes", key="window_notes")

        if st.button("💾 Save & next", type="primary", use_container_width=True):
            events = [_read_event(state, i) for i in range(state.n_events)]
            rows, errors = validate_window(state.get("has_events"), events,
                                           bool(state.get("all_listed")), doc_text, key)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                elapsed = max(0, int(time.monotonic() - state.item_started))
                windows[pos].update({
                    "window_status": STATUS_DONE,
                    "has_events": state.get("has_events"),
                    "n_events": str(len(rows)),
                    "all_listed": "Y" if state.get("has_events") == "yes" else "",
                    "notes": str(state.get("window_notes") or "").strip(),
                    "annotator": annotator.strip(),
                    "annotated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "seconds_spent": str(int(window.get("seconds_spent") or 0) + elapsed),
                })
                write_csv_atomic(gold_path, GOLD_COLUMNS,
                                 replace_window_events(gold_rows, key, rows))
                write_csv_atomic(windows_path, WINDOW_COLUMNS, windows)
                state.pop("loaded_for", None)
                go(next((i for i in range(pos + 1, len(windows)) if not _is_done(windows[i])),
                        next((i for i, r in enumerate(windows) if not _is_done(r)), pos)))

        if done == len(windows):
            st.success("All windows annotated. Score every run:  `make event-score`")


if __name__ == "__main__":
    main()
