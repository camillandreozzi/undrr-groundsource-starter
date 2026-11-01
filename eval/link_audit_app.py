"""
Link audit — judge the matcher's decisions one at a time, with the window in view.

Run from the repository root:

    make event-audit
    # or: python3 -m streamlit run eval/link_audit_app.py

WHAT IT DOES
------------
`make event-audit-sample` drew 117 of the matcher's decisions into
`eval/event_link_audit.csv` (protocol §6): every tier-C link, 25 tier-A/B links
and 15 false positives. Each asks one question — is this record the same
occurrence as this gold event, or, for a false positive, is it really none of
them? Answering from the CSV means reading quotes out of context, so this app
shows the window with the passages that matter marked:

    shaded yellow      the record's own evidence quotes
    green underline    the support quotes of the gold event it was linked to
    blue dashed        the support quotes of the window's other gold events

The model that produced the record is not shown, nor the link's tier: neither
should move a judgement of identity. Verdicts are written back into the same
CSV (`verdict`, `correct_gold_event_id`, `notes`, plus `audited_at` and
`seconds_spent`), atomically, with a timestamped backup per session.
`make event-score` then reports agreement by decision type (§11).

Overrides:
    EVENT_AUDIT_CSV       the audit sample   (default eval/event_link_audit.csv)
    EVENT_GOLD_CSV        gold events        (default eval/event_level_gold.csv)
    EVENT_WINDOWS_CSV     window titles/URLs (default eval/event_level_windows.csv)
"""
from __future__ import annotations

import html
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from eval.event_matching import _merge, locate_evidence, window_hay  # noqa: E402
from eval.human_annotation_app import (  # noqa: E402
    _env_path, _normalise_ws, create_backup, load_document_store, locate_snippet,
    read_csv, write_csv_atomic,
)

EVAL = REPO_ROOT / "eval"
DEFAULT_AUDIT = EVAL / "event_link_audit.csv"
DEFAULT_GOLD = EVAL / "event_level_gold.csv"
DEFAULT_WINDOWS = EVAL / "event_level_windows.csv"
DOCUMENT_STORES = (EVAL / "annotation_documents.json",
                   EVAL / "annotation_documents_document_sample.json")

#: Written by this app; appended to the audit file's columns if missing.
EXTRA_COLUMNS = ("audited_at", "seconds_spent")
VERDICTS = ("agree", "disagree")
TAGS = {
    "merged": "the record blends several occurrences",
    "cascade": "same occurrence under a cascade hazard's label",
    "unclear": "a hard call — worth a second look",
}
LINK_KINDS = ("link_AB", "link_C")
KIND_NAMES = {"link_AB": "Paired by quoted evidence", "link_C": "Paired by year and place only",
              "fp": "Left unpaired"}

RULES = """
**You are judging identity, not field accuracy.** Is the record about the same
real-world occurrence as the gold event?

- Ignore whether its hazard, year or places are *right* — those are scored
  separately. The right occurrence with a wrong year or an extra place →
  **agree**.
- A cascade under its secondary hazard's label (a flood record for the
  cyclone) is the same occurrence → **agree**, tag *cascade*.
- Read the record's evidence first (shaded yellow), then its dates and places.
- **Merged records.** If the record blends several occurrences and you cannot
  say which one it is mainly about → **disagree**, tag *merged*. Mainly one
  occurrence with a stray value → **agree**.
- Gold events marked *not verifiable* are occurrences too.
- When you disagree, name the right gold event if one fits. For an unpaired
  record that is one of the gold events, naming it is required.
""".strip()

# Bit flags for what covers a character of the window.
REC, LINKED, OTHER = 1, 2, 4


class AuditError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def load_audit(path: Path) -> tuple[list[str], list[dict]]:
    """The audit rows in `audit_id` order, and the columns to write them back with."""
    if not path.exists():
        raise AuditError(f"Audit sample not found: {path}\nDraw it first:  make event-audit-sample")
    fieldnames, rows = read_csv(path)
    missing = [c for c in ("audit_id", "kind", "asset_key", "verdict") if c not in fieldnames]
    if missing:
        raise AuditError(f"{path.name} lacks columns: {', '.join(missing)}")
    fieldnames += [c for c in EXTRA_COLUMNS if c not in fieldnames]
    rows.sort(key=lambda r: int(r.get("audit_id") or 0))
    return fieldnames, rows


def load_gold_events(path: Path) -> dict[str, list[dict]]:
    """Every gold event, per window, in id order."""
    _, rows = read_csv(path)
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["asset_key"]].append(r)
    for events in out.values():
        events.sort(key=lambda r: int(r.get("gold_event_id") or 0))
    return dict(out)


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

def is_decided(row: dict) -> bool:
    return str(row.get("verdict", "")).strip().lower() in VERDICTS


def split_notes(notes: str) -> tuple[list[str], str]:
    """Tags and free text from a stored `notes` value ("merged; cascade; text")."""
    parts = [p.strip() for p in str(notes or "").split(";") if p.strip()]
    tags = [p for p in parts if p in TAGS]
    return tags, "; ".join(p for p in parts if p not in TAGS)


def join_notes(tags: list[str], text: str) -> str:
    return "; ".join([t for t in TAGS if t in tags] + ([text.strip()] if text.strip() else []))


def validate_decision(kind: str, verdict: str | None, correct_id: str, linked_id: str,
                      window_ids: list[str]) -> list[str]:
    errors: list[str] = []
    if verdict not in VERDICTS:
        return ["Choose an answer."]
    if verdict == "disagree" and kind == "fp" and not correct_id:
        errors.append("You said it is one of the gold events — choose which one.")
    if verdict == "disagree" and correct_id:
        if correct_id not in window_ids:
            errors.append(f"Gold event {correct_id} is not in this window.")
        elif correct_id == linked_id:
            errors.append("That is the event the matcher already linked — answer yes, "
                          "or choose a different event.")
    return errors


def apply_decision(row: dict, verdict: str, correct_id: str, tags: list[str], text: str,
                   elapsed: int, now: str) -> dict:
    """The row with this decision written into it; every other column untouched."""
    return {
        **row,
        "verdict": verdict,
        "correct_gold_event_id": correct_id if verdict == "disagree" else "",
        "notes": join_notes(tags, text),
        "audited_at": now,
        "seconds_spent": str(int(row.get("seconds_spent") or 0) + max(0, elapsed)),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def gold_label(g: dict) -> str:
    start, end = g.get("year_start", ""), g.get("year_end", "")
    years = start if end in ("", start) else f"{start}–{end}"
    hazards = " + ".join(h.strip() for h in [g.get("hazard_primary", ""),
                                             *str(g.get("hazard_secondary") or "").split("|")]
                         if h.strip())
    places = ", ".join(p.strip() for p in str(g.get("locations") or "").split("|") if p.strip())
    flag = "" if str(g.get("verifiable", "")).strip().lower() == "yes" else " · not verifiable"
    return (f"{g['gold_event_id']}: {hazards or '(no hazard)'} {years or '(no year)'} — "
            f"{places or '(no place)'}{flag}")


def quotes_of(g: dict) -> list[str]:
    return [q.strip() for q in str(g.get("support_quotes") or "").splitlines() if q.strip()]


def _style(mask: int) -> str:
    parts = []
    if mask & REC:
        parts.append("background:#ffe08a")
    elif mask & LINKED:
        parts.append("background:#dcfce7")
    if mask & LINKED:
        parts.append("border-bottom:3px solid #16a34a")
    elif mask & OTHER:
        parts.append("border-bottom:2px dashed #2563eb")
    return ";".join(parts)


def highlight_window(doc_text: str, record_snippets: list[str], linked_quotes: list[str],
                     other_quotes: list[str]) -> tuple[str, list[str]]:
    """The window as HTML with the three kinds of passage marked, and how each of
    the record's snippets was found: exact, partial, near or none.

    Offsets follow `locate_snippet`: they index the whitespace-normalised
    window, which is what is rendered.
    """
    text = _normalise_ws(doc_text)
    hay = window_hay(doc_text)
    mask = [0] * len(text)
    starts: dict[int, set[str]] = defaultdict(set)

    def mark(spans, bit: int, name: str) -> None:
        for s, e in _merge(spans):
            s, e = max(0, s), min(len(text), e)
            if s < e:
                starts[s].add(name)
                for i in range(s, e):
                    mask[i] |= bit

    kinds, rec_spans = [], []
    for snippet in record_snippets:
        spans, kind = locate_evidence(doc_text, hay, snippet)
        kinds.append(kind)
        rec_spans.extend(spans)
    mark(rec_spans, REC, "rec")
    mark([s for q in linked_quotes for s in locate_snippet(doc_text, q)[0]], LINKED, "gold")
    mark([s for q in other_quotes for s in locate_snippet(doc_text, q)[0]], OTHER, "other")

    cuts = sorted({0, len(text), *starts,
                   *(i for i in range(1, len(text)) if mask[i] != mask[i - 1])})
    out = []
    for a, b in zip(cuts, cuts[1:]):
        attrs = "".join(f' data-{n}="1"' for n in sorted(starts.get(a, ())))
        style = _style(mask[a])
        chunk = html.escape(text[a:b])
        out.append(f'<span style="{style}"{attrs}>{chunk}</span>' if style or attrs else chunk)
    return "".join(out), kinds


VIEW = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
     color:#1d1d1f;background:#fff}
.bar{position:sticky;top:0;z-index:1;background:#f4f4f5;border-bottom:1px solid #ddd;
     padding:7px 12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:12px}
.bar button{font:inherit;padding:3px 10px;border:1px solid #bbb;border-radius:5px;
     background:#fff;color:#1d1d1f;cursor:pointer}
.bar button:disabled{opacity:.4;cursor:default}
.key{margin-left:6px;white-space:nowrap}
.txt{padding:12px 16px;white-space:pre-wrap}
</style></head><body>
<div class="bar">
  <button id="b-rec" onclick="jump('rec')">Record evidence ↓ <span id="n-rec"></span></button>
  <button id="b-gold" onclick="jump('gold')">Linked gold quote ↓ <span id="n-gold"></span></button>
  <button id="b-other" onclick="jump('other')">Other gold quotes ↓ <span id="n-other"></span></button>
  <span class="key"><span style="background:#ffe08a">&nbsp;record&nbsp;</span></span>
  <span class="key"><span style="border-bottom:3px solid #16a34a">linked gold</span></span>
  <span class="key"><span style="border-bottom:2px dashed #2563eb">other gold</span></span>
</div>
<div class="txt">%%BODY%%</div>
<script>
const at = {rec: 0, gold: 0, other: 0};
function jump(k) {
  const els = document.querySelectorAll('[data-' + k + ']');
  if (!els.length) return;
  els[at[k] % els.length].scrollIntoView({block: 'center', behavior: 'smooth'});
  at[k]++;
}
for (const k of ['rec', 'gold', 'other']) {
  const n = document.querySelectorAll('[data-' + k + ']').length;
  document.getElementById('n-' + k).textContent = '(' + n + ')';
  if (!n) document.getElementById('b-' + k).disabled = true;
}
window.addEventListener('load', () => {
  if (document.querySelector('[data-rec]')) jump('rec'); else jump('gold');
});
</script></body></html>"""

FOUND = {"exact": "✓ found", "near": "≈ found, near-verbatim", "partial": "◐ partly found",
         "none": "✗ not found in the window"}


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Link audit", layout="wide")
    audit_path = _env_path("EVENT_AUDIT_CSV", DEFAULT_AUDIT)
    gold_path = _env_path("EVENT_GOLD_CSV", DEFAULT_GOLD)
    windows_path = _env_path("EVENT_WINDOWS_CSV", DEFAULT_WINDOWS)

    try:
        fieldnames, rows = load_audit(audit_path)
    except AuditError as exc:
        st.error(str(exc))
        st.stop()
    if not rows:
        st.error(f"{audit_path.name} has no rows.")
        st.stop()

    flag = f"backup::{audit_path}"
    if flag not in st.session_state:
        st.session_state[flag] = str(create_backup(audit_path))

    @st.cache_resource(show_spinner="Loading windows…")
    def _texts() -> dict[str, str]:
        out: dict[str, str] = {}
        for store in DOCUMENT_STORES:
            documents, _ = load_document_store(store)
            out.update({k: v.get("text", "") for k, v in documents.items()})
        return out

    @st.cache_data(show_spinner=False)
    def _gold(path: str) -> dict[str, list[dict]]:
        return load_gold_events(Path(path))

    @st.cache_data(show_spinner=False)
    def _windows(path: str) -> dict[str, dict]:
        return {r["asset_key"]: r for r in read_csv(Path(path))[1]} if Path(path).exists() else {}

    @st.cache_data(show_spinner=False)
    def _view(doc_text: str, rec: tuple[str, ...], linked: tuple[str, ...],
              other: tuple[str, ...]) -> tuple[str, list[str]]:
        body, kinds = highlight_window(doc_text, list(rec), list(linked), list(other))
        return VIEW.replace("%%BODY%%", body), kinds

    texts = _texts()
    gold = _gold(str(gold_path))
    meta = _windows(str(windows_path))
    state = st.session_state
    if "pos" not in state:
        state.pos = next((i for i, r in enumerate(rows) if not is_decided(r)), 0)
    if "item_started" not in state:
        state.item_started = time.monotonic()

    def go(pos: int) -> None:
        state.pos = max(0, min(pos, len(rows) - 1))
        state.item_started = time.monotonic()
        st.rerun()

    def next_undecided(after: int) -> int:
        order = list(range(after + 1, len(rows))) + list(range(0, after + 1))
        return next((i for i in order if not is_decided(rows[i])), after)

    # -- sidebar -----------------------------------------------------------
    done = sum(1 for r in rows if is_decided(r))
    st.sidebar.header("Progress")
    st.sidebar.progress(done / len(rows))
    st.sidebar.write(f"**{done} / {len(rows)}** decisions made")
    for kind, name in KIND_NAMES.items():
        of_kind = [r for r in rows if r.get("kind") == kind]
        if of_kind:
            st.sidebar.caption(f"{name}: {sum(map(is_decided, of_kind))} / {len(of_kind)}")
    if st.sidebar.button("Jump to next undecided", use_container_width=True):
        go(next_undecided(state.pos))
    nav = st.sidebar.columns(2)
    if nav[0].button("← Prev", use_container_width=True, disabled=state.pos <= 0):
        go(state.pos - 1)
    if nav[1].button("Next →", use_container_width=True, disabled=state.pos >= len(rows) - 1):
        go(state.pos + 1)
    target = st.sidebar.number_input("Go to decision #", 1, len(rows), state.pos + 1)
    if st.sidebar.button("Go", use_container_width=True):
        go(int(target) - 1)
    with st.sidebar.expander("How to judge", expanded=done == 0):
        st.markdown(RULES)
    st.sidebar.caption(f"Writing to `{audit_path.name}` · backup "
                       f"`{Path(state[flag]).name}`")

    # -- current decision --------------------------------------------------
    pos = state.pos
    row = rows[pos]
    aid, kind, key = row["audit_id"], row.get("kind", ""), row["asset_key"]
    events = gold.get(key, [])
    labels = {g["gold_event_id"]: gold_label(g) for g in events}
    linked_id = row.get("gold_event_id", "") if kind in LINK_KINDS else ""
    doc_text = texts.get(key, "")
    window = meta.get(key, {})

    st.title(window.get("title") or "(untitled)")
    head = st.columns([3, 1])
    head[0].caption(f"Decision **{pos + 1} of {len(rows)}** · audit id {aid} · "
                    f"{len(doc_text):,} characters — the window the models were given · `{key}`")
    if window.get("content_url"):
        head[1].link_button("Open source ↗", window["content_url"], use_container_width=True)
    if is_decided(row):
        corrected = row.get("correct_gold_event_id")
        st.success(f"Answered **{row['verdict']}**"
                   + (f" → gold event {corrected}" if corrected else "")
                   + f" on {row.get('audited_at') or '?'} — saving again overwrites it.")

    snippets = [s.strip() for s in str(row.get("pred_evidence") or "").split("|") if s.strip()]
    linked_quotes = [q for g in events if g["gold_event_id"] == linked_id for q in quotes_of(g)]
    other_quotes = [q for g in events if g["gold_event_id"] != linked_id for q in quotes_of(g)]

    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        if not doc_text:
            st.error("No window text for this asset_key. Run `make annotate-prefetch`.")
            kinds = ["none"] * len(snippets)
        else:
            page, kinds = _view(doc_text, tuple(snippets), tuple(linked_quotes),
                                tuple(other_quotes))
            st.iframe(page, height=780)

    with right:
        with st.container(border=True):
            st.markdown("**The record** (which model made it is hidden)")
            st.markdown(f"- **Hazard:** {row.get('pred_hazard') or '—'}\n"
                        f"- **Dates:** {row.get('pred_dates') or '—'}\n"
                        f"- **Places:** {row.get('pred_locations') or '—'}")
            st.markdown("**Its evidence** — shaded yellow in the window")
            for snippet, found in zip(snippets, kinds):
                st.caption(f"{FOUND.get(found, found)}: “{snippet[:220]}”")
            if not snippets:
                st.caption("The record quotes no evidence.")

        with st.container(border=True):
            if kind in LINK_KINDS:
                st.markdown(f"**The matcher paired it with gold event {linked_id}** — "
                            "green underline in the window")
                st.markdown(labels.get(linked_id, f"{linked_id}: (not in the gold file)"))
            else:
                st.markdown("**The matcher found no gold event for it.**")
            others = [labels[i] for i in labels if i != linked_id]
            if others:
                st.markdown("**Other gold events in this window** — blue dashes")
                st.markdown("\n".join(f"- {label}" for label in others))
            elif not events:
                st.caption("This window has no gold events.")

        if kind in LINK_KINDS:
            question = f"Is the record the same occurrence as gold event {linked_id}?"
            answers = {"agree": "Yes — same occurrence",
                       "disagree": "No — a different occurrence"}
            pick_label, none_label = "Which gold event is it, if any?", "— none of them —"
        else:
            question = "Is it right that none of the gold events is this occurrence?"
            answers = {"agree": "Yes — it is none of them",
                       "disagree": "No — it is one of the gold events"}
            pick_label, none_label = "Which gold event is it?", "— choose —"

        saved_verdict = str(row.get("verdict", "")).strip().lower()
        verdict = st.radio(f"**{question}**", VERDICTS, format_func=answers.get,
                           index=VERDICTS.index(saved_verdict) if saved_verdict in VERDICTS else None,
                           key=f"verdict_{aid}")
        options = [""] + [i for i in labels if i != linked_id]
        saved_id = row.get("correct_gold_event_id", "")
        correct_id = st.selectbox(pick_label, options,
                                  format_func=lambda i: labels.get(i, i) if i else none_label,
                                  index=options.index(saved_id) if saved_id in options else 0,
                                  disabled=verdict != "disagree", key=f"correct_{aid}")
        saved_tags, saved_text = split_notes(row.get("notes", ""))
        tags = st.multiselect("Tags", list(TAGS), default=saved_tags,
                              format_func=lambda t: f"{t} — {TAGS[t]}", key=f"tags_{aid}")
        note = st.text_input("Notes", value=saved_text, key=f"note_{aid}")

        if st.button("💾 Save & next", type="primary", use_container_width=True):
            errors = validate_decision(kind, verdict, correct_id, linked_id, list(labels))
            if errors:
                for e in errors:
                    st.error(e)
            else:
                elapsed = int(time.monotonic() - state.item_started)
                rows[pos] = apply_decision(row, verdict, correct_id, tags, note, elapsed,
                                           datetime.now(timezone.utc).isoformat(timespec="seconds"))
                write_csv_atomic(audit_path, fieldnames, rows)
                go(next_undecided(pos))

        if done == len(rows):
            st.success("Every decision is made. Report agreement:  `make event-score`")


if __name__ == "__main__":
    main()
