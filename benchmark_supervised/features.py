"""Candidates, feature templates and gold labels. Pure functions over `Parsed`.

CANDIDATES (fixed, never learned)
---------------------------------
  trigger   a hazard-lexicon match (`benchmark_ner.hazard_lexicon`: prompt 5's
            own PreventionWeb vocabulary, unchanged). It carries its label.
  year      a four-digit year 1900–2035 in the text, not inside a longer
            number and not a decade ("1990s").
  place     a GPE / LOC / FAC entity from either NER model, cleaned with the
            NER baseline's `clean_location`. Mentions with the same casefolded
            string are one candidate *value*.

Everything a classifier sees is computed from the text alone, so the same
function serves training and test windows. Gold is read only by
`gold_assignment` and the two `*_label` functions, and only for training
windows (`model.py` enforces that).

FEATURE TEMPLATES
-----------------
Dicts for `DictVectorizer`: numbers stay numeric, strings become one-hot
indicators ("prev=in"). They are the classic MaxEnt event-extraction templates
— lexical context, distance in sentences and characters, dependency-path
length, intervening competitors — plus NER type and agreement between the two
models for places.
"""
from __future__ import annotations

import math
import re
from bisect import bisect_right
from itertools import accumulate
from dataclasses import dataclass, field
from typing import Iterable

from benchmark_ner.hazard_lexicon import find_hazards
from benchmark_ner.ner_extract import clean_location, is_country
from benchmark_supervised.parse import PRIMARY_MODEL, SECONDARY_MODEL, Parsed
from eval.event_matching import GoldEvent, Window, _loc_match, gold_hazard_keys, hazard_key

PLACE_LABELS = frozenset({"GPE", "LOC", "FAC"})
YEAR_MIN, YEAR_MAX = 1900, 2035
#: Last year a reported event can have happened in: the corpus was extracted in
#: 2026. A later year is a target or a projection.
LAST_EVENT_YEAR = 2026
_YEAR = re.compile(r"(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)(?!['’]?s\b)")
_RANGE_GLUE = re.compile(r"^\s*(?:-|–|—|to|/|and|until|till)\s*$", re.I)
_IMPACT = re.compile(
    r"\b(?:kill\w*|death\w*|died|fatalit\w*|casualt\w*|injur\w*|missing|displac\w*"
    r"|evacuat\w*|homeless|affected|destroy\w*|destruction|damag\w*|collaps\w*"
    r"|loss\w*|inundat\w*|submerged|washed away|struck|hit)\b", re.I)
_ADMIN = re.compile(r"\b(?:province|district|county|state|region|city|municipality|"
                    r"prefecture|department|island|islands|valley|river|coast|basin)\b", re.I)
#: Head of the window: title, cover page, opening summary.
HEAD_CHARS = 300
#: Tokens either side of a trigger whose words become bag-of-words features.
#: PDF text often has no full stops for a page, so the sentence is too loose.
BOW_REACH = 15
#: Distances are capped: beyond this, further apart tells the model nothing new.
SENT_CAP = 10
DEP_CAP = 12
SNIPPET_MAX = 300


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Trigger:
    idx: int
    start: int
    end: int
    label: str
    key: str
    surface: str
    sent: int


@dataclass(frozen=True)
class Mention:
    start: int
    end: int
    sent: int
    ner: str = ""                       # OntoNotes label (places)
    models: frozenset = frozenset()     # which NER models found it (places)
    in_date: bool = False               # inside an NER DATE entity (years)
    in_range: bool = False              # one end of "1999-2001" (years)


@dataclass
class Candidate:
    """A candidate value — a year, or a place string — and every mention of it."""
    kind: str
    value: str
    mentions: list[Mention] = field(default_factory=list)


class Doc:
    """One window's candidates and lookups, built once from its parse."""

    def __init__(self, parsed: Parsed):
        self.parsed = parsed
        self.key = parsed.key
        self.text = parsed.text
        self.sent_starts = [s for s, _ in parsed.sents]
        self.tok_starts = [t[0] for t in parsed.tokens]
        self.triggers = [
            Trigger(i, h.start, h.end, h.label, hazard_key(h.label), h.text, self.sent_of(h.start))
            for i, h in enumerate(find_hazards(self.text))]
        dates = [(s, e) for s, e, label, model in parsed.ents
                 if label == "DATE" and model == PRIMARY_MODEL]
        self.years = self._years(dates)
        self.places = self._places()
        self.sent_tokens: dict[int, list[int]] = {}
        for i, tok in enumerate(parsed.tokens):
            self.sent_tokens.setdefault(self.sent_of(tok[0]), []).append(i)
        # Gold spans index the matcher's hay: this text casefolded, which can
        # lengthen a character (ﬁ -> fi). Casefolding is per character, so a
        # running sum of folded lengths maps one coordinate onto the other.
        self._hay_at = list(accumulate((len(ch.casefold()) for ch in self.text), initial=0))

    # -- lookups ------------------------------------------------------------

    def to_hay(self, char: int) -> int:
        return self._hay_at[char]

    def sent_of(self, char: int) -> int:
        return max(0, bisect_right(self.sent_starts, char) - 1)

    def tok_of(self, char: int) -> int:
        return max(0, bisect_right(self.tok_starts, char) - 1)

    def word_before(self, char: int, n: int = 1) -> str:
        i = self.tok_of(char)
        if self.parsed.tokens and self.parsed.tokens[i][0] >= char:
            i -= 1
        words = [self.parsed.tokens[j][2] for j in range(max(0, i - n + 1), i + 1)] if i >= 0 else []
        return " ".join(words) or "<s>"

    def word_after(self, char: int) -> str:
        i = bisect_right(self.tok_starts, char - 1)
        return self.parsed.tokens[i][2] if i < len(self.parsed.tokens) else "</s>"

    def tree_distance(self, a_char: int, b_char: int) -> int:
        """Dependency-path length between the tokens at two offsets (same sentence)."""
        a, b = self.tok_of(a_char), self.tok_of(b_char)
        chain_a = self._ancestors(a)
        depth = {tok: d for d, tok in enumerate(chain_a)}
        for d_b, tok in enumerate(self._ancestors(b)):
            if tok in depth:
                return min(DEP_CAP, depth[tok] + d_b)
        return DEP_CAP

    def _ancestors(self, i: int) -> list[int]:
        out = [i]
        while len(out) <= DEP_CAP + 1:
            head = self.parsed.tokens[out[-1]][5]
            if head == out[-1]:
                break
            out.append(head)
        return out

    # -- candidate extraction ----------------------------------------------

    def _years(self, dates: list[tuple[int, int]]) -> list[Candidate]:
        hits = [m for m in _YEAR.finditer(self.text) if YEAR_MIN <= int(m.group(1)) <= YEAR_MAX]
        ranged: set[int] = set()
        for a, b in zip(hits, hits[1:]):
            gap = self.text[a.end():b.start()]
            if len(gap) <= 8 and _RANGE_GLUE.match(gap):
                ranged.update((a.start(), b.start()))
        by_value: dict[str, Candidate] = {}
        for m in hits:
            mention = Mention(m.start(), m.end(), self.sent_of(m.start()),
                              in_date=any(s <= m.start() and m.end() <= e for s, e in dates),
                              in_range=m.start() in ranged)
            by_value.setdefault(m.group(1), Candidate("year", m.group(1))).mentions.append(mention)
        return list(by_value.values())

    def _places(self) -> list[Candidate]:
        spans: dict[tuple[int, int], dict] = {}
        for start, end, label, model in self.parsed.ents:
            if label not in PLACE_LABELS:
                continue
            slot = spans.setdefault((start, end), {"labels": {}, "models": set()})
            slot["labels"][model] = label
            slot["models"].add(model)
        by_value: dict[str, Candidate] = {}
        for (start, end), slot in sorted(spans.items()):
            name = clean_location(self.text[start:end])
            if not name:
                continue
            ner = slot["labels"].get(PRIMARY_MODEL) or slot["labels"][SECONDARY_MODEL]
            mention = Mention(start, end, self.sent_of(start), ner=ner,
                              models=frozenset(slot["models"]))
            by_value.setdefault(name.casefold(), Candidate("place", name)).mentions.append(mention)
        return list(by_value.values())

    # -- neighbourhood sets -------------------------------------------------

    def values_near(self, kind: str, sent: int, reach: int = 0) -> set[str]:
        pool = self.years if kind == "year" else self.places
        return {c.value.casefold() for c in pool
                if any(abs(m.sent - sent) <= reach for m in c.mentions)}

    def snippet(self, trig: Trigger) -> str:
        """Verbatim evidence: the trigger's sentence, or a window around it if
        the "sentence" is a run-on PDF page. Pipes would split the field."""
        s, e = self.parsed.sents[trig.sent] if self.parsed.sents else (0, len(self.text))
        if e - s > SNIPPET_MAX:
            mid = (trig.start + trig.end) // 2
            s = max(s, mid - SNIPPET_MAX // 2)
            e = min(e, s + SNIPPET_MAX)
            s = self.text.rfind(" ", 0, s) + 1 if s > 0 else s
            space = self.text.find(" ", e)
            e = space if 0 < space < e + 40 else e
        return self.text[s:e].strip().replace("|", "/")


# ---------------------------------------------------------------------------
# Feature templates
# ---------------------------------------------------------------------------

def _log(n: float) -> float:
    return math.log1p(max(0.0, n))


def _nearest_sent(doc: Doc, pool: list[Candidate], sent: int) -> int:
    return min([abs(m.sent - sent) for c in pool for m in c.mentions] + [SENT_CAP])


def trigger_features(doc: Doc, t: Trigger) -> dict:
    """Is this hazard mention a concrete, reported occurrence?"""
    toks = doc.parsed.tokens
    sent_toks = doc.sent_tokens.get(t.sent, [])
    i = doc.tok_of(t.start)
    reach = [toks[j][2] for j in range(max(0, i - BOW_REACH), min(len(toks), i + BOW_REACH + 1))]
    s, e = doc.parsed.sents[t.sent] if doc.parsed.sents else (0, len(doc.text))
    sentence = doc.text[s:e]
    labels_in_window = {x.label for x in doc.triggers}
    f = {
        "bias": 1.0,
        "label": t.label,
        "surface": t.surface.lower(),
        "plural": float(t.surface.lower().endswith("s") and not t.surface.lower().endswith("ss")),
        "prev": doc.word_before(t.start),
        "prev2": doc.word_before(t.start, 2),
        "next": doc.word_after(t.end),
        "d_year": _nearest_sent(doc, doc.years, t.sent),
        "d_place": _nearest_sent(doc, doc.places, t.sent),
        "sent_past": float(any(toks[j][6] for j in sent_toks)),
        "sent_modal": float(any(toks[j][3] == "MD" for j in sent_toks)),
        "sent_digits": _log(sum(1 for j in sent_toks if any(ch.isdigit() for ch in toks[j][2]))),
        "sent_impact": float(bool(_IMPACT.search(sentence))),
        "sent_len": _log(len(sent_toks)),
        "rel_pos": t.start / max(1, len(doc.text)),
        "in_head": float(t.start < HEAD_CHARS),
        "win_triggers": _log(len(doc.triggers)),
        "win_labels": float(len(labels_in_window)),
        "label_mentions": _log(sum(1 for x in doc.triggers if x.label == t.label)),
        "first_of_label": float(all(x.start >= t.start for x in doc.triggers if x.label == t.label)),
    }
    for w in reach:
        if w.isalpha() and len(w) > 2:
            f[f"w={w}"] = 1.0
    return f


def coref_features(doc: Doc, a: Trigger, b: Trigger) -> dict:
    """Do two event mentions report the same occurrence? `a` precedes `b`."""
    if b.start < a.start:
        a, b = b, a
    f = {
        "bias": 1.0,
        "same_label": float(a.label == b.label),
        "same_key": float(a.key == b.key),
        "pair": "|".join(sorted((a.key, b.key))),
        "d_sent": float(min(SENT_CAP, b.sent - a.sent)),
        "same_sent": float(a.sent == b.sent),
        "d_char": _log(b.start - a.end),
        "prev_b": doc.word_before(b.start),
    }
    for kind in ("year", "place"):
        for reach in (0, 1):
            va, vb = doc.values_near(kind, a.sent, reach), doc.values_near(kind, b.sent, reach)
            f[f"{kind}{reach}_overlap"] = float(bool(va & vb))
            f[f"{kind}{reach}_disjoint"] = float(bool(va) and bool(vb) and not va & vb)
    between_years = {c.value for c in doc.years for m in c.mentions if a.end <= m.start < b.start}
    f["years_between"] = _log(len(between_years))
    between = [x for x in doc.triggers if a.end <= x.start < b.start]
    f["triggers_between"] = _log(len(between))
    f["other_keys_between"] = _log(len({x.key for x in between} - {a.key, b.key}))
    return f


def argument_features(doc: Doc, cluster: list[Trigger], cand: Candidate,
                      clusters: list[list[Trigger]], pool: list[Candidate]) -> dict:
    """Is this year / place an argument of this event (a cluster of mentions)?

    `clusters` is every event in the window and `pool` every candidate of the
    same kind, so the features can say whether a nearer event or a nearer
    candidate competes for this one.
    """
    in_cluster = {t.idx for t in cluster}
    pairs = [(abs(t.start - m.start), t, m) for t in cluster for m in cand.mentions]
    d_char, t0, m0 = min(pairs, key=lambda x: (x[0], x[2].start))
    d_sent = min(abs(t.sent - m.sent) for t in cluster for m in cand.mentions)
    same = [(t, m) for t in cluster for m in cand.mentions if t.sent == m.sent]
    lo, hi = sorted((t0.start, m0.start))

    def dist(c: Candidate, cl: list[Trigger]) -> int:
        return min(abs(t.start - m.start) for t in cl for m in c.mentions)

    rank = 1 + sum(1 for other in pool if other is not cand and dist(other, cluster) < d_char)
    f = {
        "bias": 1.0,
        "d_sent": float(min(SENT_CAP, d_sent)),
        "same_sent": float(d_sent == 0),
        "d_char": _log(d_char),
        "before": float(m0.start < t0.start),
        "dep": float(min((doc.tree_distance(t.start, m.start) for t, m in same), default=DEP_CAP)),
        "mentions": _log(len(cand.mentions)),
        "near": _log(sum(1 for m in cand.mentions if any(abs(t.sent - m.sent) <= 1 for t in cluster))),
        "rank": float(min(SENT_CAP, rank)),
        "is_closest": float(rank == 1),
        "closest_event": float(all(dist(cand, cl) >= d_char for cl in clusters)),
        "events": _log(len(clusters)),
        "cluster_size": _log(len(cluster)),
        "triggers_between": _log(sum(1 for x in doc.triggers
                                     if lo <= x.start < hi and x.idx not in in_cluster)),
        "same_kind_between": _log(sum(1 for other in pool if other is not cand
                                      and any(lo < m.start < hi for m in other.mentions))),
        "in_head": float(any(m.start < HEAD_CHARS for m in cand.mentions)),
        "prev": doc.word_before(m0.start),
        "next": doc.word_after(m0.end),
        "hazard": t0.key,
    }
    if cand.kind == "year":
        year = int(cand.value)
        f.update({
            "in_date": float(any(m.in_date for m in cand.mentions)),
            "in_range": float(any(m.in_range for m in cand.mentions)),
            "future": float(year > LAST_EVENT_YEAR),
            "latest_in_window": float(year == max(int(c.value) for c in pool)),
        })
    else:
        f.update({
            "ner": m0.ner,
            "models": "+".join(sorted(m0.models)),
            "both_models": float(any(len(m.models) > 1 for m in cand.mentions)),
            "country": float(is_country(cand.value)),
            "admin_word": float(bool(_ADMIN.search(cand.value))),
            "n_tokens": float(min(6, len(cand.value.split()))),
            "places_in_window": _log(len(pool)),
        })
    return f


# ---------------------------------------------------------------------------
# Gold labels (training windows only)
# ---------------------------------------------------------------------------

def _inside(start: int, spans: Iterable[tuple[int, int]]) -> bool:
    return any(s <= start < e for s, e in spans)


def gold_assignment(doc: Doc, gold: list[GoldEvent]) -> dict[int, int]:
    """Trigger idx -> gold_event_id, for triggers that report a gold event.

    A trigger reports event g when it sits inside g's support quotes, or in the
    sentence around them and names one of g's hazards. A trigger claimed by two
    events goes to one whose hazards it names, then to the one whose raw quote
    holds it, then to the lowest id. Everything else is a negative.
    """
    window = Window(doc.parsed.text, gold)
    if len(window.hay) != doc.to_hay(len(doc.text)):
        raise ValueError(f"{doc.key[:12]}: parse text and matcher hay are out of step")
    out: dict[int, int] = {}
    for t in doc.triggers:
        at = doc.to_hay(t.start)
        claims = []
        for g in gold:
            in_quote = _inside(at, window.support.get(g.gold_event_id, []))
            names_it = t.key in gold_hazard_keys(g)
            if in_quote or (names_it and _inside(at, window.context.get(g.gold_event_id, []))):
                claims.append((not names_it, not in_quote, g.gold_event_id))
        if claims:
            out[t.idx] = min(claims)[2]
    return out


def year_label(cand: Candidate, g: GoldEvent) -> int:
    if g.year_start is None:
        return 0
    return int(g.year_start <= int(cand.value) <= (g.year_end or g.year_start))


def place_label(cand: Candidate, g: GoldEvent) -> int:
    """The scorer's own location rule (`event_matching._loc_match`)."""
    return int(any(_loc_match(cand.value, loc) for loc in g.locations))


def gold_clusters(doc: Doc, assignment: dict[int, int]) -> dict[int, list[Trigger]]:
    out: dict[int, list[Trigger]] = {}
    for t in doc.triggers:
        if t.idx in assignment:
            out.setdefault(assignment[t.idx], []).append(t)
    return out
