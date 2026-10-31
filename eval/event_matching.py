"""
Event-level matching: which predicted record describes which gold event.

Pure functions, no I/O. `eval/score_event_level.py` drives them; the rules are
the ones pre-registered in `eval/EVENT_LEVEL_PROTOCOL.md` §4–§5, and every
threshold below is quoted there. Changing one changes the experiment: log it in
the protocol's deviations section, do not just edit the number.

WHY NOT MATCH ON THE FIELDS
---------------------------
The question is whether a record's hazard, year and locations belong to *one*
occurrence. A matcher that pairs records with gold events by how many fields
agree answers a different question — it picks, for every record, the gold
event that makes it look best, and a record carrying one event's hazard and
another's year and place gets paired with whichever side flatters it. So
identity comes from the record's own evidence text, and the fields are scored
only after the pairing is fixed:

  Tier A, anchored     the record's evidence snippet is located in the window
                       and lies mostly inside the sentences holding the gold
                       event's support quotes.
  Tier B, paraphrase   the snippet is not locatable (prompt 5 allows
                       paraphrase), but its content words are covered by the
                       sentences around the gold event's support quotes.
  Tier C, context      the record has no usable evidence at all: it is linked
                       only if its years overlap the gold event's span AND at
                       least one location matches. Hazard alone never links.

A field-maximising alignment is computed too (`optimistic_alignment`), but only
as a labelled sensitivity bound: how much a lenient matcher would have hidden.

COORDINATES
-----------
All spans index `window_hay(text)`: the window whitespace-normalised and
casefolded — the same string `human_annotation_app.locate_snippet` searches, so
a gold support quote and a predicted snippet land in one coordinate space.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_openrouter.citation_quality import (  # noqa: E402
    NEAR_VERBATIM, WEAK_COVERAGE, content_words, word_list,
)
from eval.human_annotation_app import _normalise_ws, locate_snippet  # noqa: E402
from eval.score_against_human import _fold, _split, _years  # noqa: E402
from eval.score_strict_rules import _greedy, _norm_score  # noqa: E402
from fonte.hazard_families import OTHER, hazard_family  # noqa: E402

#: Tier A: share of a located snippet's span that must fall inside the gold
#: event's support context — its support quotes widened to their sentences, so
#: a record quoting the clause next to the annotator's quote still anchors.
#: Half, so a snippet straddling two events' sentences goes to the one it
#: mostly quotes. Among eligible pairs, overlap with the raw quotes ranks.
ANCHOR_MIN = 0.5
#: Tier B: content-word coverage of an unlocated snippet by the gold event's
#: support sentences. `citation_quality.WEAK_COVERAGE` — the bar at which that
#: audit stops calling a snippet unsupported.
PARAPHRASE_MIN = WEAK_COVERAGE
#: How far a support quote is widened, each way, to its sentence boundary.
#: PDF text often has no full stops for pages; this stops a "sentence" from
#: swallowing the window.
SENTENCE_REACH = 400
#: Anchored links come first, lexicographically: weights for tier A sit above
#: the largest possible sum of tier-B weights in any window.
_ANCHOR_BONUS = 100.0
#: Identity scores equal to this precision are ties.
_SCORE_DECIMALS = 3
#: First tie-break: occurrence context — years overlap, a location matches
#: (0–2 per pair; never the hazard). Small enough that a window's whole sum
#: stays under one unit of the rounded score.
_CONTEXT_EPS = 1e-5
#: Last tie-break, so the result never depends on solver internals: the i-th
#: record by event_index goes with the i-th gold event by id. Convex in the
#: rank distance — a linear penalty sums to the same total for every pairing.
_ORDER_EPS = 1e-10

_QUOTE_CHARS = "\"'“”‘’«»`"
_SENTENCE_END = re.compile(r"[.!?;](?=\s)")


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GoldEvent:
    asset_key: str
    gold_event_id: int
    hazard_primary: str
    hazard_secondary: tuple[str, ...]
    year_start: Optional[int]
    year_end: Optional[int]
    locations: tuple[str, ...]
    support_quotes: tuple[str, ...]
    verifiable: bool

    @classmethod
    def from_row(cls, row: dict) -> "GoldEvent":
        start = _int_or_none(row.get("year_start"))
        end = _int_or_none(row.get("year_end"))
        if start is not None and end is None:
            end = start
        return cls(
            asset_key=row["asset_key"],
            gold_event_id=int(row["gold_event_id"]),
            hazard_primary=str(row.get("hazard_primary") or "").strip(),
            hazard_secondary=tuple(_split(row.get("hazard_secondary"))),
            year_start=start,
            year_end=end,
            locations=tuple(_split(row.get("locations"))),
            support_quotes=tuple(_lines(row.get("support_quotes"))),
            verifiable=str(row.get("verifiable", "")).strip().lower() in {"yes", "y", "true"},
        )


@dataclass(frozen=True)
class PredEvent:
    asset_key: str
    event_index: int
    hazards: tuple[str, ...]
    years: tuple[int, ...]
    dates: str
    locations: tuple[str, ...]
    snippets: tuple[str, ...]

    @classmethod
    def from_row(cls, row: dict, fallback_index: int) -> "PredEvent":
        index = _int_or_none(row.get("event_index"))
        dates = str(row.get("event_dates") or "")
        return cls(
            asset_key=row["asset_key"],
            event_index=index if index is not None else fallback_index,
            hazards=tuple(_split(row.get("event_hazard"))),
            years=tuple(sorted({int(y) for y in _years([dates])})),
            dates=dates,
            locations=tuple(_split(row.get("affected_locations"))),
            snippets=tuple(_split(row.get("evidence_snippets"))),
        )


def _int_or_none(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _lines(value) -> list[str]:
    """Support quotes are stored one per line: a quote may contain `|`."""
    return [p.strip() for p in str(value or "").splitlines() if p.strip()]


# ---------------------------------------------------------------------------
# Hazards
# ---------------------------------------------------------------------------

def hazard_key(label: str) -> str:
    """The family, except inside `other`, which keeps the label.

    `hazard_family` puts 13 PreventionWeb labels in `other`. Scoring at family
    level would then call Epidemic for Cold Wave a correct hazard, so inside
    `other` the folded label is the key.
    """
    family = hazard_family(label)
    return family if family != OTHER else f"{OTHER}:{_fold(label).strip()}"


def gold_hazard_keys(gold: GoldEvent) -> set[str]:
    labels = ([gold.hazard_primary] if gold.hazard_primary else []) + list(gold.hazard_secondary)
    return {hazard_key(h) for h in labels}


def pred_hazard_keys(pred: PredEvent) -> set[str]:
    return {hazard_key(h) for h in pred.hazards}


# ---------------------------------------------------------------------------
# Locating text in the window
# ---------------------------------------------------------------------------

def window_hay(text: str) -> str:
    return _normalise_ws(text or "").casefold()


def _strip_quotes(snippet: str) -> str:
    """Prompt-5 snippets often arrive wrapped in quote marks, which
    `locate_snippet` would otherwise search for as part of the text."""
    return str(snippet or "").strip().strip(_QUOTE_CHARS).strip()


def locate_evidence(text: str, hay: str, snippet: str) -> tuple[list[tuple[int, int]], str]:
    """Spans of `snippet` in `hay`, and how it was found: exact, partial, near, none.

    `locate_snippet` first (verbatim, whitespace-tolerant, ellipsis-aware). If
    that finds nothing, a near-verbatim alignment: rapidfuzz
    `partial_ratio_alignment` at `citation_quality.NEAR_VERBATIM`.
    """
    cleaned = _strip_quotes(snippet)
    spans, kind = locate_snippet(text, cleaned)
    if spans:
        return spans, kind
    needle = _normalise_ws(cleaned).casefold()
    if len(needle) < 12 or not hay:
        return [], "none"
    from rapidfuzz import fuzz
    hit = fuzz.partial_ratio_alignment(needle, hay)
    if hit is not None and hit.score >= NEAR_VERBATIM and hit.dest_end > hit.dest_start:
        return [(hit.dest_start, hit.dest_end)], "near"
    return [], "none"


def _merge(spans: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return [(s, e) for s, e in out]


def _overlap(spans: Sequence[tuple[int, int]], target: Sequence[tuple[int, int]]) -> float:
    """Share of `spans`' characters that fall inside `target`."""
    total = sum(e - s for s, e in spans)
    if total <= 0:
        return 0.0
    covered = 0
    for s, e in spans:
        for ts, te in target:
            covered += max(0, min(e, te) - max(s, ts))
    return covered / total


def _sentence(hay: str, start: int, end: int) -> tuple[int, int]:
    """Widen [start, end) to the enclosing sentence, at most SENTENCE_REACH each way."""
    lo = max(0, start - SENTENCE_REACH)
    before = [m.end() for m in _SENTENCE_END.finditer(hay, lo, start)]
    left = before[-1] if before else lo
    after = _SENTENCE_END.search(hay, end, min(len(hay), end + SENTENCE_REACH))
    right = after.end() if after else min(len(hay), end + SENTENCE_REACH)
    return left, right


# ---------------------------------------------------------------------------
# A window, prepared once
# ---------------------------------------------------------------------------

@dataclass
class Window:
    """One document window with its gold events' support located."""
    text: str
    gold: list[GoldEvent]
    hay: str = ""
    #: Raw support-quote spans, per gold_event_id.
    support: dict[int, list[tuple[int, int]]] = field(default_factory=dict)
    #: The same spans widened to their sentences.
    context: dict[int, list[tuple[int, int]]] = field(default_factory=dict)
    context_words: dict[int, set[str]] = field(default_factory=dict)
    unlocated_quotes: list[tuple[int, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.hay = window_hay(self.text)
        for g in self.gold:
            spans: list[tuple[int, int]] = []
            for quote in g.support_quotes:
                found, _kind = locate_snippet(self.text, quote)
                if not found:
                    self.unlocated_quotes.append((g.gold_event_id, quote))
                spans.extend(found)
            self.support[g.gold_event_id] = _merge(spans)
            self.context[g.gold_event_id] = _merge(
                _sentence(self.hay, s, e) for s, e in self.support[g.gold_event_id])
            self.context_words[g.gold_event_id] = set(
                word_list(" ".join(self.hay[s:e] for s, e in self.context[g.gold_event_id])))


@dataclass(frozen=True)
class Identity:
    tier: Optional[str]      # "A", "B" or None
    #: A: context overlap + quote overlap (0.5–2). B: coverage (0.5–1). 0 when ineligible.
    score: float


def identity(pred: PredEvent, gold: GoldEvent, window: Window,
             located: Optional[list[tuple[list[tuple[int, int]], str]]] = None) -> Identity:
    """Tier A/B identity of one record with one gold event. Fields are not read.

    A located snippet speaks only through where it sits; an unlocated one only
    through its words. A verbatim quote from elsewhere in the window is not
    given a second chance on vocabulary, which common words would grant.
    """
    if located is None:
        located = [locate_evidence(window.text, window.hay, s) for s in pred.snippets]
    support = window.support.get(gold.gold_event_id, [])
    context = window.context.get(gold.gold_event_id, [])
    best_a = 0.0
    best_b = 0.0
    for snippet, (spans, _kind) in zip(pred.snippets, located):
        if spans:
            in_context = _overlap(spans, context)
            if in_context >= ANCHOR_MIN:
                best_a = max(best_a, in_context + _overlap(spans, support))
        else:
            words = content_words(_strip_quotes(snippet))
            ctx = window.context_words.get(gold.gold_event_id, set())
            if words and ctx:
                best_b = max(best_b, sum(1 for w in words if w in ctx) / len(words))
    if best_a:
        return Identity("A", best_a)
    if best_b >= PARAPHRASE_MIN:
        return Identity("B", best_b)
    return Identity(None, 0.0)


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------

def _loc_match(x: str, y: str) -> bool:
    return _norm_score(x, y) is not None


def _year_endpoints(years: Sequence[int]) -> set[int]:
    return {min(years), max(years)} if years else set()


def _gold_endpoints(gold: GoldEvent) -> set[int]:
    if gold.year_start is None:
        return set()
    return {gold.year_start, gold.year_end if gold.year_end is not None else gold.year_start}


def _in_span(year: int, gold: GoldEvent) -> bool:
    if gold.year_start is None:
        return False
    end = gold.year_end if gold.year_end is not None else gold.year_start
    return gold.year_start <= year <= end


def years_overlap(pred: PredEvent, gold: GoldEvent) -> bool:
    if not pred.years or gold.year_start is None:
        return False
    end = gold.year_end if gold.year_end is not None else gold.year_start
    return min(pred.years) <= end and max(pred.years) >= gold.year_start


FIELDS = ("hazard", "year", "location")


@dataclass
class FieldVerdict:
    """How one record's fields compare with the gold event it was matched to."""
    ok: dict[str, bool]
    exact: dict[str, bool]
    tp: dict[str, int]
    fp: dict[str, int]
    fn: dict[str, int]
    #: Wrong predicted values that belong to *another* gold event in the window.
    misassociated: dict[str, int]
    #: Wrong predicted values that belong to no gold event in the window.
    unsupported: dict[str, int]

    @property
    def complete(self) -> bool:
        return all(self.ok[f] for f in FIELDS)


def judge(pred: PredEvent, gold: GoldEvent, others: Sequence[GoldEvent]) -> FieldVerdict:
    """Score the three fields of a matched pair. `others` are the window's
    remaining gold events, used only to classify wrong values."""
    ok, exact, tp, fp, fn, mis, uns = {}, {}, {}, {}, {}, {}, {}

    # Hazard
    p_keys, g_keys = pred_hazard_keys(pred), gold_hazard_keys(gold)
    primary = hazard_key(gold.hazard_primary) if gold.hazard_primary else None
    ok["hazard"] = primary is not None and primary in p_keys and p_keys <= g_keys
    g_labels = {_fold(h) for h in ([gold.hazard_primary] + list(gold.hazard_secondary)) if h}
    exact["hazard"] = bool(g_labels) and {_fold(h) for h in pred.hazards} == g_labels
    tp["hazard"], fp["hazard"], fn["hazard"] = (
        len(p_keys & g_keys), len(p_keys - g_keys), len(g_keys - p_keys))
    other_keys = set().union(*(gold_hazard_keys(o) for o in others)) if others else set()
    wrong = p_keys - g_keys
    mis["hazard"] = len(wrong & other_keys)
    uns["hazard"] = len(wrong - other_keys)

    # Year: all predicted years inside the gold span; endpoints for the counts.
    ok["year"] = bool(pred.years) and all(_in_span(y, gold) for y in pred.years)
    p_end, g_end = _year_endpoints(pred.years), _gold_endpoints(gold)
    exact["year"] = bool(g_end) and ok["year"] and (
        min(pred.years) == gold.year_start and max(pred.years) == (gold.year_end or gold.year_start))
    tp["year"], fp["year"], fn["year"] = len(p_end & g_end), len(p_end - g_end), len(g_end - p_end)
    wrong_years = [y for y in p_end if y not in g_end]
    mis["year"] = sum(1 for y in wrong_years
                      if not _in_span(y, gold) and any(_in_span(y, o) for o in others))
    uns["year"] = sum(1 for y in wrong_years
                      if not _in_span(y, gold) and not any(_in_span(y, o) for o in others))

    # Location
    p_locs, g_locs = set(pred.locations), set(gold.locations)
    pairs = _greedy(p_locs, g_locs, _norm_score)
    matched_pred = {x for x in p_locs if any(_loc_match(x, y) for y in g_locs)}
    ok["location"] = bool(p_locs) and matched_pred == p_locs
    exact["location"] = ok["location"] and all(
        any(_loc_match(x, y) for x in p_locs) for y in g_locs)
    tp["location"] = len(pairs)
    fp["location"] = len(p_locs) - len(pairs)
    fn["location"] = len(g_locs) - len(pairs)
    other_locs = [y for o in others for y in o.locations]
    stray = p_locs - matched_pred
    mis["location"] = sum(1 for x in stray if any(_loc_match(x, y) for y in other_locs))
    uns["location"] = len(stray) - mis["location"]

    return FieldVerdict(ok, exact, tp, fp, fn, mis, uns)


def pred_value_counts(pred: PredEvent) -> dict[str, int]:
    """What an unmatched record contributes as false positives, per field."""
    return {"hazard": len(pred_hazard_keys(pred)),
            "year": len(_year_endpoints(pred.years)),
            "location": len(set(pred.locations))}


def gold_value_counts(gold: GoldEvent) -> dict[str, int]:
    """What a missed gold event contributes as false negatives, per field."""
    return {"hazard": len(gold_hazard_keys(gold)),
            "year": len(_gold_endpoints(gold)),
            "location": len(set(gold.locations))}


def pooled_counts(preds: Sequence[PredEvent], golds: Sequence[GoldEvent]) -> dict[str, tuple[int, int, int]]:
    """The document-level reading: union every side's values, then compare.

    Same value representations as `judge`, so the gap between this and the
    event-level counts is association and nothing else.
    """
    p_h = set().union(*(pred_hazard_keys(p) for p in preds)) if preds else set()
    g_h = set().union(*(gold_hazard_keys(g) for g in golds)) if golds else set()
    p_y = set().union(*(_year_endpoints(p.years) for p in preds)) if preds else set()
    g_y = set().union(*(_gold_endpoints(g) for g in golds)) if golds else set()
    p_l = {loc for p in preds for loc in p.locations}
    g_l = {loc for g in golds for loc in g.locations}
    loc_tp = len(_greedy(p_l, g_l, _norm_score))
    return {
        "hazard": (len(p_h & g_h), len(p_h - g_h), len(g_h - p_h)),
        "year": (len(p_y & g_y), len(p_y - g_y), len(g_y - p_y)),
        "location": (loc_tp, len(p_l) - loc_tp, len(g_l) - loc_tp),
    }


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

@dataclass
class Link:
    pred: PredEvent
    gold: GoldEvent
    tier: str                # "A", "B" or "C"
    score: float
    verdict: FieldVerdict


@dataclass
class WindowMatch:
    links: list[Link]
    #: Unmatched records and why: "split" (its identity points at a gold event
    #: another record took) or "no_event" (no gold event it could be).
    unmatched_pred: list[tuple[PredEvent, str]]
    #: Unmatched gold events and why: "merge" (a record matched elsewhere also
    #: carries its evidence) or "missed".
    unmatched_gold: list[tuple[GoldEvent, str]]
    #: For every (event_index, gold_event_id) pair with tier-A/B identity.
    identities: dict[tuple[int, int], Identity]


def _assign(weights: list[list[float]],
            context: Optional[list[list[int]]] = None) -> list[tuple[int, int]]:
    """Maximum-weight one-to-one assignment over positive weights.

    Lexicographic: total weight, then total `context` (if given), then rank
    order. Only pairs with positive weight can be assigned.
    """
    if not weights or not weights[0]:
        return []
    from scipy.optimize import linear_sum_assignment
    import numpy as np

    n_pred, n_gold = len(weights), len(weights[0])
    matrix = np.zeros((n_pred, n_gold))
    for i in range(n_pred):
        for j in range(n_gold):
            if weights[i][j] > 0:
                matrix[i, j] = (weights[i][j]
                                + (_CONTEXT_EPS * context[i][j] if context else 0.0)
                                - _ORDER_EPS * (i - j) ** 2)
    rows, cols = linear_sum_assignment(matrix, maximize=True)
    return [(int(i), int(j)) for i, j in zip(rows, cols) if weights[i][j] > 0]


def occurrence_context(pred: PredEvent, gold: GoldEvent) -> int:
    """Years overlap (1) plus at least one location matches (1). Never the hazard."""
    return int(years_overlap(pred, gold)) + int(bool(
        _greedy(set(pred.locations), set(gold.locations), _norm_score)))


def match_window(preds: Sequence[PredEvent], window: Window) -> WindowMatch:
    """The pre-registered matcher. See the module docstring."""
    preds = sorted(preds, key=lambda p: p.event_index)
    golds = sorted(window.gold, key=lambda g: g.gold_event_id)

    located = {p.event_index: [locate_evidence(window.text, window.hay, s) for s in p.snippets]
               for p in preds}
    identities: dict[tuple[int, int], Identity] = {}
    weights: list[list[float]] = []
    for p in preds:
        row = []
        for g in golds:
            ident = identity(p, g, window, located[p.event_index])
            if ident.tier:
                identities[(p.event_index, g.gold_event_id)] = ident
            score = round(ident.score, _SCORE_DECIMALS)
            row.append(_ANCHOR_BONUS + score if ident.tier == "A"
                       else score if ident.tier == "B" else 0.0)
        weights.append(row)
    context = [[occurrence_context(p, g) for g in golds] for p in preds]

    links: list[Link] = []
    taken_pred: set[int] = set()
    taken_gold: set[int] = set()
    for i, j in _assign(weights, context):
        p, g = preds[i], golds[j]
        ident = identities[(p.event_index, g.gold_event_id)]
        links.append(Link(p, g, ident.tier, ident.score, judge(p, g, _others(golds, g))))
        taken_pred.add(i)
        taken_gold.add(j)

    # Tier C: records with no tier-A/B link, in event_index order.
    for i, p in enumerate(preds):
        if i in taken_pred:
            continue
        best: Optional[tuple[int, int]] = None
        for j, g in enumerate(golds):
            if j in taken_gold or not years_overlap(p, g):
                continue
            n_loc = len(_greedy(set(p.locations), set(g.locations), _norm_score))
            if n_loc and (best is None or n_loc > best[0]):
                best = (n_loc, j)
        if best is not None:
            j = best[1]
            g = golds[j]
            links.append(Link(p, g, "C", float(best[0]), judge(p, g, _others(golds, g))))
            taken_pred.add(i)
            taken_gold.add(j)

    unmatched_pred = []
    for i, p in enumerate(preds):
        if i in taken_pred:
            continue
        could_be = any((p.event_index, g.gold_event_id) in identities for g in golds) or any(
            years_overlap(p, g) and _greedy(set(p.locations), set(g.locations), _norm_score)
            for g in golds)
        unmatched_pred.append((p, "split" if could_be else "no_event"))

    matched_preds = [preds[i] for i in taken_pred]
    unmatched_gold = []
    for j, g in enumerate(golds):
        if j in taken_gold:
            continue
        merged = any((p.event_index, g.gold_event_id) in identities for p in matched_preds)
        unmatched_gold.append((g, "merge" if merged else "missed"))

    links.sort(key=lambda link: link.pred.event_index)
    return WindowMatch(links, unmatched_pred, unmatched_gold, identities)


def _others(golds: Sequence[GoldEvent], g: GoldEvent) -> list[GoldEvent]:
    return [o for o in golds if o.gold_event_id != g.gold_event_id]


def optimistic_alignment(preds: Sequence[PredEvent], golds: Sequence[GoldEvent]) -> list[tuple[PredEvent, GoldEvent, FieldVerdict]]:
    """Sensitivity bound, never the result: pair records with gold events to
    maximise complete records first, then agreeing fields, ignoring evidence.

    This is the most generous one-to-one reading any matcher could give, so the
    gap between it and `match_window` is what the matching rule costs.
    """
    preds = sorted(preds, key=lambda p: p.event_index)
    golds = sorted(golds, key=lambda g: g.gold_event_id)
    verdicts = [[judge(p, g, _others(golds, g)) for g in golds] for p in preds]
    weights = [[(10.0 * v.complete + sum(v.ok[f] for f in FIELDS)) for v in row]
               for row in verdicts]
    return [(preds[i], golds[j], verdicts[i][j]) for i, j in _assign(weights)]
