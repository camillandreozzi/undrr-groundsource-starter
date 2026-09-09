"""benchmark_ner/ner_extract.py — the NER baseline extractor.

spaCy `en_core_web_lg` + the PreventionWeb hazard lexicon, over the same
documents and the same 12,000-character window as the LLM run. No API calls.

The output is written in the **exact `event_extractions` schema**
(`fonte.app_event_focus.OUTPUT_HEADERS`), which is the point: every
downstream tool in this repo — `fonte-polygons`,
`eval/prefill_gold_validation.py`, `eval/gold_validation_app.py`,
`scripts/visualize_event_extractions.py` — then runs on the baseline unchanged,
so the two pipelines are geocoded and judged by identical machinery.

How an event is assembled
-------------------------
1. Hazard mentions are found by regex (`hazard_lexicon`).
2. A ±`--window` sentence window around each hazard mention is scanned for
   `GPE`/`LOC`/`FAC` entities (locations) and `DATE` entities (dates).
3. A window with at least one location and at least one normalisable date
   becomes a candidate event.
4. Candidates in a document are grouped by the set of hazard labels their
   window contains, one output row per group — so co-mentioned hazards yield a
   single "Earthquake | Tsunami" event, mirroring both the LLM's compound-label
   convention and its one-row-per-distinct-event contract.

Usage:
    python benchmark_ner/ner_extract.py
    python benchmark_ner/ner_extract.py --limit 200 --output-dir /tmp/ner_smoke
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from bisect import bisect_right
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from fonte.app_event_focus import save_csv, save_jsonl

REPO_ROOT = Path(__file__).resolve().parent.parent
# Importable both as `python -m benchmark_ner.ner_extract` and as a plain
# script path, which is how the docstring and the Makefile each invoke it.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmark_ner.hazard_lexicon import find_hazards, join_labels  # noqa: E402

DEFAULT_DOCS = REPO_ROOT / "benchmark_ner" / "outputs" / "documents.parquet"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "benchmark_ner" / "outputs"

LOG = logging.getLogger("benchmark_ner.extract")

LOCATION_LABELS = {"GPE", "LOC", "FAC"}
DATE_LABEL = "DATE"


# --------------------------------------------------------------------------
# Date normalisation
# --------------------------------------------------------------------------

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

# Plausible event years. Anything outside this is a page number, a quantity, or
# an OCR artefact that spaCy mislabelled as a DATE.
_YEAR_MIN, _YEAR_MAX = 1900, 2035

_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY_RE = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_ALT})\.?,?\s+(\d{{4}})\b", re.I)
_MDY_RE = re.compile(rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
_MY_RE = re.compile(rf"\b({_MONTH_ALT})\.?,?\s+(\d{{4}})\b", re.I)
_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")

# "three days", "over 20 years" — a span of time, not a date. The year regex
# would otherwise read "over 2000 years" as the year 2000, so this is checked
# against the *span* of the year match, not merely the presence of the phrase:
# "3 days in 2019" still yields 2019.
_DURATION = re.compile(
    r"(?:about|around|over|nearly|almost|some|more than|less than|up to)?\s*"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*"
    r"(?:-|\s)?(?:year|month|week|day|hour|minute|decade|centur)",
    re.I,
)
_DECADE = re.compile(r"\b(?:1[89]\d0|20\d0)s\b")


def normalise_date(text: str) -> Optional[str]:
    """A DATE entity as `YYYY-MM-DD` / `YYYY-MM` / `YYYY`, or None if unusable.

    Returns the most precise form the string supports, matching the convention
    the LLM was instructed to use.

    The test is simply whether the string contains an absolute anchor. Relative
    references ("last year", "recently") have no year to find and fall out on
    their own — an explicit blocklist of them would also have thrown away
    "the summer of 2019", which is a perfectly good year-precision event date.
    Decades ("the 1990s") and durations are rejected explicitly, since both do
    contain digits that would otherwise parse as a year.
    """
    if not text:
        return None
    t = " ".join(text.split())
    if _DECADE.search(t):
        return None

    m = _ISO_RE.search(t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _YEAR_MIN <= y <= _YEAR_MAX and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    for rx, order in ((_DMY_RE, "dmy"), (_MDY_RE, "mdy")):
        m = rx.search(t)
        if m:
            if order == "dmy":
                d, mon, y = int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3))
            else:
                mon, d, y = _MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
            if _YEAR_MIN <= y <= _YEAR_MAX and 1 <= d <= 31:
                return f"{y:04d}-{mon:02d}-{d:02d}"

    m = _MY_RE.search(t)
    if m:
        mon, y = _MONTHS[m.group(1).lower()], int(m.group(2))
        if _YEAR_MIN <= y <= _YEAR_MAX:
            return f"{y:04d}-{mon:02d}"

    for m in _YEAR_RE.finditer(t):
        y = int(m.group(1))
        if not (_YEAR_MIN <= y <= _YEAR_MAX):
            continue
        # Reject a year that is really the count in a duration ("over 2000
        # years"), but keep one that merely sits alongside a duration.
        if any(d.start() <= m.start() < d.end() for d in _DURATION.finditer(t)):
            continue
        return f"{y:04d}"
    return None


def date_precision(value: str) -> int:
    """3 = day, 2 = month, 1 = year, 0 = unusable."""
    n = len(value or "")
    return 3 if n == 10 else 2 if n == 7 else 1 if n == 4 else 0


# --------------------------------------------------------------------------
# Location cleaning
# --------------------------------------------------------------------------

_LEADING_ARTICLE = re.compile(r"^(?:the|a|an)\s+", re.I)
_TRAILING_JUNK = re.compile(r"[\s,;:.\-–—'’\"]+$")
_LEADING_JUNK = re.compile(r"^[\s,;:.\-–—'’\"]+")
# spaCy routinely tags these as GPE/LOC in policy prose. None of them is a place
# a geocoder can resolve to a footprint, and each one would otherwise dominate
# the location sets in a corpus of UN documents.
_NON_PLACES = {
    "un", "u.n.", "united nations", "undrr", "unisdr", "unesco", "unicef",
    "who", "world bank", "eu", "european union", "oecd", "asean", "african union",
    "state", "states", "country", "countries", "region", "regions", "nation",
    "nations", "city", "cities", "province", "district", "north", "south",
    "east", "west", "central", "global", "world", "earth", "international",
    "national", "local", "government", "sendai framework", "hyogo framework",
}


def clean_location(text: str) -> Optional[str]:
    """Normalise an entity string, or None when it is not a usable place name."""
    if not text:
        return None
    t = " ".join(text.split())
    t = _LEADING_JUNK.sub("", t)
    t = _TRAILING_JUNK.sub("", t)
    t = _LEADING_ARTICLE.sub("", t).strip()
    if len(t) < 2 or len(t) > 80:
        return None
    if t.lower() in _NON_PLACES:
        return None
    # Needs at least one letter; "2015" and "10 %" are not places.
    if not re.search(r"[^\W\d_]", t):
        return None
    return t


_COUNTRY_CACHE: dict[str, bool] = {}


def is_country(name: str) -> bool:
    """True when pycountry resolves the string to a country.

    Used for `location_admin_levels`, which the polygon resolver reads to decide
    whether a sub-national hazard was given a whole-country footprint
    (`geometry_overshoot`). Getting countries right is the only admin tag that
    changes downstream behaviour, so the other tags stay conservative.
    """
    key = name.lower()
    if key in _COUNTRY_CACHE:
        return _COUNTRY_CACHE[key]
    try:
        import pycountry
        pycountry.countries.lookup(name)
        hit = True
    except Exception:
        hit = False
    _COUNTRY_CACHE[key] = hit
    return hit


def admin_level_for(name: str, ent_label: str) -> str:
    """Self-tag in the same vocabulary as `LOCATION_ADMIN_LEVELS`."""
    if is_country(name):
        return "country"
    if ent_label == "FAC":
        return "point"
    if ent_label == "LOC":
        return "feature"
    return "unknown"


# --------------------------------------------------------------------------
# Impact detection
# --------------------------------------------------------------------------

# Stems take \w* so "damaged", "injuries" and "displacement" all match — a bare
# stem followed by \b silently matches nothing.
_IMPACT_TERMS = re.compile(
    r"\b(?:kill\w*|death\w*|died|fatalit\w*|casualt\w*|injur\w*|missing"
    r"|displac\w*|evacuat\w*|homeless|affected|destroy\w*|destruction|damag\w*"
    r"|collaps\w*|loss\w*|inundat\w*|submerged|washed away)\b",
    re.I,
)
_HAS_NUMBER = re.compile(r"\d|\b(?:hundreds?|thousands?|millions?|billions?|dozens?)\b", re.I)


def impact_sentences(sents: Iterable[str]) -> list[str]:
    """Window sentences that state an impact. Numbers preferred, not required.

    Mirrors the LLM's brief, which asks for qualitative impacts when numbers are
    absent — otherwise the baseline would look artificially impact-free on the
    many documents that describe damage without counting it.
    """
    numeric: list[str] = []
    qualitative: list[str] = []
    for s in sents:
        if not _IMPACT_TERMS.search(s):
            continue
        (numeric if _HAS_NUMBER.search(s) else qualitative).append(s)
    return numeric + qualitative


# --------------------------------------------------------------------------
# Event assembly
# --------------------------------------------------------------------------

def _truncate(s: str, n: int = 240) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _pipe_safe(s: str) -> str:
    """List fields are joined with ' | ', so a literal pipe would corrupt them."""
    return s.replace("|", "/")


def build_events(
    spacy_doc,
    *,
    window: int,
    max_locations: int,
    max_dates: int,
    max_impacts: int,
    max_snippets: int,
    publication_year: Optional[str],
) -> list[dict]:
    """Assemble candidate events from one parsed document."""
    text = spacy_doc.text
    hazards = find_hazards(text)
    if not hazards:
        return []

    sents = list(spacy_doc.sents)
    if not sents:
        return []
    starts = [s.start_char for s in sents]

    def sentence_index(char_pos: int) -> int:
        # Sentences are ordered and non-overlapping, so the last start at or
        # before the position is the containing sentence.
        return max(0, bisect_right(starts, char_pos) - 1)

    # Entities bucketed by sentence, once, so overlapping windows stay cheap.
    locs_by_sent: dict[int, list[tuple[str, str]]] = defaultdict(list)
    dates_by_sent: dict[int, list[tuple[str, str]]] = defaultdict(list)
    hazards_by_sent: dict[int, set[str]] = defaultdict(set)
    for ent in spacy_doc.ents:
        if ent.label_ in LOCATION_LABELS:
            name = clean_location(ent.text)
            if name:
                locs_by_sent[sentence_index(ent.start_char)].append((name, ent.label_))
        elif ent.label_ == DATE_LABEL:
            norm = normalise_date(ent.text)
            if norm:
                dates_by_sent[sentence_index(ent.start_char)].append((norm, ent.text))
    for hz in hazards:
        hazards_by_sent[sentence_index(hz.start)].add(hz.label)

    # One candidate per hazard mention, keyed by every hazard label its window
    # contains — so "the earthquake and the tsunami that followed" produces a
    # single "Earthquake | Tsunami" event, the way the LLM was told to emit it,
    # rather than two competing rows.
    groups: dict[str, dict] = OrderedDict()
    for hz in hazards:
        i = sentence_index(hz.start)
        lo, hi = max(0, i - window), min(len(sents) - 1, i + window)
        idxs = range(lo, hi + 1)

        win_locs = [pair for j in idxs for pair in locs_by_sent.get(j, [])]
        win_dates = [pair for j in idxs for pair in dates_by_sent.get(j, [])]
        if not win_locs or not win_dates:
            continue

        label = join_labels({l for j in idxs for l in hazards_by_sent.get(j, ())})
        g = groups.setdefault(label, {
            "locations": Counter(),
            "loc_labels": {},
            "dates": Counter(),
            "sentences": OrderedDict(),
        })
        for name, label in win_locs:
            g["locations"][name] += 1
            g["loc_labels"].setdefault(name, label)
        for norm, _raw in win_dates:
            g["dates"][norm] += 1
        for j in idxs:
            g["sentences"].setdefault(j, sents[j].text)

    if not groups:
        return []

    events: list[dict] = []
    for label, g in groups.items():
        # Rank by how often the window mentions it, then by first appearance —
        # a corpus-scale geocoding run cannot afford every GPE in the document.
        locations = [n for n, _ in g["locations"].most_common(max_locations)]
        dates = sorted(g["dates"], key=lambda d: (-g["dates"][d], d))[:max_dates]
        dates.sort()
        window_sents = [_truncate(s) for s in g["sentences"].values()]
        impacts = impact_sentences(window_sents)[:max_impacts]

        best_precision = max((date_precision(d) for d in dates), default=0)
        confidence = "high" if best_precision >= 2 and impacts else "medium"

        missing: list[str] = []
        if best_precision == 1:
            missing.append("year-only date")
        if not impacts:
            missing.append("impact statements missing")
        if all(a == "country" for a in (admin_level_for(n, g["loc_labels"][n]) for n in locations)):
            missing.append("only country-level locations")
        if publication_year and dates and all(d[:4] == str(publication_year) for d in dates):
            missing.append("event date equals publication year")

        events.append({
            "event_hazard": label,
            "event_dates": dates,
            "affected_locations": locations,
            "location_admin_levels": [
                admin_level_for(n, g["loc_labels"][n]) for n in locations
            ],
            "key_impacts": impacts,
            "event_confidence": confidence,
            "evidence_snippets": window_sents[:max_snippets],
            "missing_information": missing,
        })
    return events


def to_output_rows(meta: dict, events: list[dict]) -> list[dict]:
    """Render events into `OUTPUT_HEADERS` rows, exactly as the LLM run does."""
    base = {
        "asset_key": meta.get("asset_key"),
        "title": meta.get("title"),
        "publication_year": meta.get("publication_year"),
        "language": meta.get("language"),
        "countries": meta.get("countries"),
        "themes": meta.get("themes"),
        "hazards": meta.get("hazards"),
        "organizations": meta.get("organizations"),
        "content_url": meta.get("content_url"),
    }
    if not events:
        return [{
            **base,
            "event_index": "",
            "event_count": 0,
            "is_single_actual_event": False,
            "is_verifiable_event": False,
            "event_hazard": None,
            "event_dates": "",
            "affected_locations": "",
            "location_admin_levels": "",
            "key_impacts": "",
            "event_confidence": None,
            "event_confidence_logprob": None,
            "event_confidence_prob": None,
            "evidence_snippets": "",
            "missing_information": "no verified reliable event extracted",
        }]

    rows = []
    for idx, e in enumerate(events, start=1):
        rows.append({
            **base,
            "event_index": idx,
            "event_count": len(events),
            # Same minimum-field rule the LLM output is held to in
            # DocumentEventExtractions._keep_verified_unique_events.
            "is_single_actual_event": len(events) == 1,
            "is_verifiable_event": bool(
                e["event_hazard"] and e["event_dates"] and e["affected_locations"]
            ),
            "event_hazard": e["event_hazard"],
            "event_dates": " | ".join(e["event_dates"]),
            "affected_locations": " | ".join(_pipe_safe(x) for x in e["affected_locations"]),
            "location_admin_levels": " | ".join(e["location_admin_levels"]),
            "key_impacts": " | ".join(_pipe_safe(x) for x in e["key_impacts"]),
            "event_confidence": e["event_confidence"],
            "event_confidence_logprob": None,
            "event_confidence_prob": None,
            "evidence_snippets": " | ".join(_pipe_safe(x) for x in e["evidence_snippets"]),
            "missing_information": " | ".join(e["missing_information"]),
        })
    return rows


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def load_nlp(model: str):
    """Load the NER pipeline with sentence boundaries but no parser.

    `senter` gives sentence splits at a fraction of the parser's cost, which
    matters over 10,000 documents. Not every model ships it, so fall back to
    the parser rather than losing sentence windows.
    """
    import spacy
    # `enable=` cannot override the component the model config already lists as
    # disabled (spaCy raises E1042), so exclude the parser at load time and
    # switch senter on afterwards.
    try:
        nlp = spacy.load(model, exclude=["tagger", "attribute_ruler", "lemmatizer", "parser"])
        nlp.enable_pipe("senter")
        LOG.info("Loaded %s with components: %s", model, nlp.pipe_names)
        return nlp
    except Exception as exc:
        LOG.warning("senter unavailable (%s); falling back to the parser.", exc)
        nlp = spacy.load(model, exclude=["lemmatizer", "tagger", "attribute_ruler"])
        LOG.info("Loaded %s with components: %s", model, nlp.pipe_names)
        return nlp


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--docs", type=Path, default=DEFAULT_DOCS,
                   help="documents.parquet from fetch_documents.py")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--model", default="en_core_web_lg", help="spaCy model name.")
    p.add_argument("--limit", type=int, default=None, help="Process only the first N documents.")
    p.add_argument("--window", type=int, default=1,
                   help="Sentences either side of a hazard mention to scan (default 1).")
    p.add_argument("--max-locations", type=int, default=10,
                   help="Cap locations per event. Bounds the geocoding run; the LLM "
                        "run flagged >10 as anomalous.")
    p.add_argument("--max-dates", type=int, default=5)
    p.add_argument("--max-impacts", type=int, default=5)
    p.add_argument("--max-snippets", type=int, default=3)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--n-process", type=int, default=1,
                   help="spaCy worker processes. >1 speeds up the full run markedly.")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if not args.docs.exists():
        LOG.error("Documents not found: %s\nRun: python benchmark_ner/fetch_documents.py",
                  args.docs)
        return 1

    df = pd.read_parquet(args.docs)
    if args.limit:
        df = df.head(args.limit)
    LOG.info("Loaded %d documents from %s", len(df), args.docs)

    nlp = load_nlp(args.model)
    # Documents are already trimmed to 12k chars, but spaCy's default 1M limit
    # can still bite if fetch_documents was run with a larger --max-chars.
    nlp.max_length = max(nlp.max_length, int(df["text"].str.len().max() or 0) + 1000)

    records = df.to_dict("records")
    pairs = [(str(r.get("text") or ""), r) for r in records]

    started = time.perf_counter()
    rows: list[dict] = []
    n_docs_with_events = 0
    n_events = 0
    for i, (spacy_doc, meta) in enumerate(
        nlp.pipe(pairs, as_tuples=True, batch_size=args.batch_size, n_process=args.n_process),
        start=1,
    ):
        events = build_events(
            spacy_doc,
            window=args.window,
            max_locations=args.max_locations,
            max_dates=args.max_dates,
            max_impacts=args.max_impacts,
            max_snippets=args.max_snippets,
            publication_year=meta.get("publication_year"),
        )
        if events:
            n_docs_with_events += 1
            n_events += len(events)
        rows.extend(to_output_rows(meta, events))
        if i % 500 == 0:
            rate = i / (time.perf_counter() - started)
            LOG.info("[%d/%d] %.1f docs/s | %d events in %d docs",
                     i, len(pairs), rate, n_events, n_docs_with_events)

    elapsed = time.perf_counter() - started

    out_dir = args.output_dir
    jsonl_path = out_dir / "ner_extractions.jsonl"
    csv_path = out_dir / "ner_extractions.csv"
    save_jsonl(rows, jsonl_path)
    save_csv(rows, csv_path)

    import spacy
    stats = {
        "model": args.model,
        "spacy_version": spacy.__version__,
        "documents": len(pairs),
        "rows": len(rows),
        "events": n_events,
        "documents_with_events": n_docs_with_events,
        "document_hit_rate": round(n_docs_with_events / len(pairs), 4) if pairs else 0.0,
        "wall_clock_s": round(elapsed, 1),
        "docs_per_second": round(len(pairs) / elapsed, 2) if elapsed else None,
        "api_cost_usd": 0.0,
        "settings": {
            "window": args.window,
            "max_locations": args.max_locations,
            "max_dates": args.max_dates,
            "n_process": args.n_process,
        },
    }
    (out_dir / "ner_run_stats.json").write_text(json.dumps(stats, indent=2))

    LOG.info("Wrote %d rows -> %s", len(rows), jsonl_path)
    LOG.info("  %d events across %d / %d documents (%.1f%%) in %.1fs (%.1f docs/s)",
             n_events, n_docs_with_events, len(pairs),
             100 * n_docs_with_events / len(pairs) if pairs else 0.0,
             elapsed, len(pairs) / elapsed if elapsed else 0.0)
    LOG.info("Next: python benchmark_ner/geocode_preflight.py --input %s", jsonl_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
