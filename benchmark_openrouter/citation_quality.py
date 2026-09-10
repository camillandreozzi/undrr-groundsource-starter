"""Is the evidence snippet actually in the document? A label-free citation audit.

    python -m benchmark_openrouter.citation_quality
    python -m benchmark_openrouter.citation_quality --arm 167
    python -m benchmark_openrouter.citation_quality --run "my run=path/to/rows.jsonl"

Every extracted event carries up to three `evidence_snippets` that are supposed
to justify it. This locates each one in the source text and reports how often
that succeeds. No human annotation is involved and none is needed: the document
is on disk, the snippet is on disk, and containment is decidable. That makes
this the one accuracy-adjacent number in the benchmark that can be computed for
every model over every document rather than over a judged sample.

WHAT THE PROMPT ASKED FOR, AND WHY THAT SHAPES THE METRIC
---------------------------------------------------------
Prompt 5 says "up to 3 short snippets **or paraphrases** (<= 25 words each)".
So a snippet that is not verbatim is not automatically a defect — it is the
prompt being obeyed. A single found/not-found rate would therefore score
obedience as failure, which is why the verdict is graded:

    verbatim         the snippet's character stream occurs in the document
    verbatim_elided  every fragment either side of an ellipsis occurs, in order
    near_verbatim    partial_ratio >= 90 — a quote with light edits or a typo
    paraphrase       not locatable, but >= 80% of its words are in the document
    weak             50-80% of its words are in the document
    unsupported      < 50% — the document does not contain what the snippet says
    cross_script     a script the source barely contains: a translation
    cross_language   a source not confirmed English: translation or invention,
                     and no way to tell which
    no_content       no letters or digits in it at all — "©", "["

`verbatim + verbatim_elided + near_verbatim` is the **quotable** rate: the
snippet can be pointed at in the source, which is what an auditor following a
record back to its origin actually needs. `+ paraphrase` is the **grounded**
rate. `weak + unsupported` is the failure mass.

WHAT THIS DOES NOT MEASURE
--------------------------
Lexical support is not entailment. A paraphrase built entirely from words that
appear in the document can still assert something the document never said, and
this will score it `paraphrase`. Read the grade as "could this have been read
off the page", not "is this true". The sharper signal is the numeric check
below, and the honest reading of the `paraphrase` band is that it is unaudited.

Nor does a found snippet make the *event* correct: the snippet can be a real
sentence about a different event in the same document. Event correctness is
`eval/score_against_human.py`, against human labels.

THREE THINGS THAT WOULD OTHERWISE BE MISCOUNTED
-----------------------------------------------
*Trimming.* Snippets are matched against the same 12,000-character window the
model was given, not the full document — a snippet quoted from character 40,000
would be a hallucination as far as the model's input is concerned, and a match
against untrimmed text would hide that. `documents.json` stores the trimmed
window for exactly this reason.

*PDF text.* The corpus is pymupdf output, so words break across lines
("retrac-\nted") and headings arrive one character per line. Containment is
therefore tested on the alphanumeric stream with all whitespace, punctuation,
case and diacritics removed, which makes line-break damage invisible to the
test. The false-positive risk this buys — a 25-word snippet matching by
coincidence — is negligible.

*Language.* Several sources are Arabic, Japanese, Spanish or French while every
model answers in English, so their snippets are translations — grounded and
unquotable at once, and not separable from fabrication by any lexical means. A
snippet in a script the source barely contains is `cross_script`; a failed match
against a source not confirmed to be in English is `cross_language`. Both are
held out of the denominator and reported on their own lines, so the failure mass
is what the test can actually stand behind.

POOLING THE TWO ARMS IS LEGITIMATE HERE
---------------------------------------
`pool_arms.py` warns that the 167 and the 50 have different inclusion
probabilities, so anything prevalence-dependent on the pool describes no real
population. Every rate in this file is conditional on a snippet existing, not on
a document carrying an event, so the mixture does not distort it. What pooling
does buy is small: the enriched arm contributes roughly 95% of the snippets, so
the pooled figure is the 167's figure with a correction attached. `--arm 50`
reads the document-sampled arm on its own.

ONE FAILURE MODE THIS TEST CANNOT SEE
-------------------------------------
A few sources reach the corpus with a broken font encoding, so pymupdf returns
a shifted alphabet: `7b4674fa394f` contains "TISTPI[IVIEJJIGXIH", which is
"people were affected" moved four letters along. Models that decode it — some
do — produce a snippet that is a faithful quotation of a document whose stored
text does not contain it, and this scores that as a miss. It is rare, it is a
corpus defect rather than a model one, and it biases every rate here downward
by the same small amount. It is not corrected for: guessing at cipher shifts
would put a decoder in the middle of an audit whose whole value is that it does
nothing clever.

NUMBERS
-------
Separately from the grade, every figure in a snippet (digit strings, with
thousands separators folded) is looked for in the document. An invented
casualty count is the failure mode that matters most in this corpus and it
survives paraphrase, so it is reported as its own rate over snippets that
contain a figure at all.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_openrouter.agreement import REFERENCE_RUNS, discover_runs  # noqa: E402
from eval.score_against_human import Run, _split  # noqa: E402
from fonte.stats import format_rate  # noqa: E402

LOG = logging.getLogger("benchmark_openrouter.citation_quality")

OUT_DIR = REPO_ROOT / "benchmark_openrouter" / "outputs_pooled"
DEFAULT_REPORT = REPO_ROOT / "benchmark_openrouter" / "CITATION_QUALITY.md"
DEFAULT_SNIPPET_CSV = REPO_ROOT / "benchmark_openrouter" / "outputs" / "citation_quality_snippets.csv"

#: Trimmed document windows, by arm. Both files store `text` already cut to the
#: 12,000 characters the prompt receives (see build_documents.MAX_CHARS).
DOCUMENT_SETS = {
    "167": REPO_ROOT / "benchmark_openrouter" / "documents.json",
    "50": REPO_ROOT / "benchmark_openrouter" / "documents_docsample.json",
}

NEAR_VERBATIM = 90.0   # rapidfuzz partial_ratio
PARAPHRASE_COVERAGE = 0.80
WEAK_COVERAGE = 0.50
#: Below this many characters an ellipsis fragment is not evidence of anything —
#: "the" occurs in every document.
MIN_FRAGMENT_CHARS = 12

GRADES = ("verbatim", "verbatim_elided", "near_verbatim",
          "paraphrase", "weak", "unsupported")
QUOTABLE = ("verbatim", "verbatim_elided", "near_verbatim")
GROUNDED = QUOTABLE + ("paraphrase",)
#: Graded, but not a finding either way, so out of every denominator.
HELD_OUT = ("cross_script", "cross_language", "no_content")

_ELLIPSIS = re.compile(r"(?:…|\.\s*\.\s*\.|\[\s*\.{2,}\s*\])")
#: A grouped figure — `12,000`, `12 000`, `12.000`. Tried first, so a run of
#: digits only counts as grouped when the groups are exactly three long.
_GROUPED_RUN = r"\d{1,3}(?:[.,\u00a0\u202f\u2009 ]\d{3})+(?!\d)"
#: Anything else, decimal point included: `2018`, `7.2`, `80`.
_PLAIN_RUN = r"\d+(?:[.,]\d+)?"
_DIGITS = re.compile(f"{_GROUPED_RUN}|{_PLAIN_RUN}")
_GROUPED = re.compile(f"^{_GROUPED_RUN}$")
#: `7.2` / `7,2` — a decimal, which must NOT become `72` and match a year.
_DECIMAL = re.compile(r"^(\d+)[.,](\d{1,2})$")


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _fold(s: str) -> str:
    """NFKD, combining marks dropped, casefolded — matches `score_against_human`."""
    decomposed = unicodedata.normalize("NFKD", str(s or ""))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return unicodedata.normalize("NFKC", stripped).casefold()


def char_stream(s: str) -> str:
    """Alphanumerics only. Whitespace, punctuation and PDF line breaks vanish."""
    return "".join(c for c in _fold(s) if c.isalnum())


def word_list(s: str) -> list[str]:
    """Folded whitespace tokens, stripped to alphanumerics, empties dropped."""
    out = []
    for token in re.split(r"\s+", _fold(s)):
        cleaned = "".join(c for c in token if c.isalnum())
        if cleaned:
            out.append(cleaned)
    return out


def numbers(s: str) -> set[str]:
    """Figures in a comparable form.

    Grouping separators are dropped, so `12,000` and `12 000` both become
    `12000`. A decimal point is kept, because folding `magnitude 7.2` to `72`
    would let it match any year ending in 72 that happens to be in the document.
    """
    found = set()
    for match in _DIGITS.findall(str(s or "")):
        token = match.strip(" .,'\u00a0\u202f\u2009")
        if not token:
            continue
        if _GROUPED.match(token):
            token = re.sub(r"[.,\u00a0\u202f\u2009 ']", "", token)
        else:
            decimal = _DECIMAL.match(token)
            if decimal:
                found.add(f"{decimal.group(1).lstrip('0') or '0'}."
                          f"{decimal.group(2)}")
                continue
            token = re.sub(r"[^0-9]", "", token)
        if token:
            found.add(token.lstrip("0") or "0")
    return found


_SCRIPT_ALIASES = {"HIRAGANA": "CJK", "KATAKANA": "CJK", "HANGUL": "CJK",
                   "KATAKANA-HIRAGANA": "CJK", "IDEOGRAPHIC": "CJK"}
#: A snippet is only called cross-script when its script is this close to absent
#: from the document. Several sources are Arabic bodies with an English abstract,
#: and an English snippet from one of those is checkable against the abstract.
SCRIPT_PRESENCE = 0.05
#: Under this many letters, "which script is this" is not a question worth asking.
MIN_SCRIPT_CHARS = 8


def script_counts(s: str) -> Counter:
    """Alphabetic characters by coarse script label."""
    counts: Counter[str] = Counter()
    for ch in str(s or ""):
        if not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch).split()[0]
        except ValueError:
            continue
        counts[_SCRIPT_ALIASES.get(name, name)] += 1
    return counts


def dominant_script(s: str) -> str:
    """The most common alphabetic script, as a coarse label. `''` if none."""
    counts = script_counts(s)
    return counts.most_common(1)[0][0] if counts else ""


#: Scripts written without spaces between words, where whitespace tokens are not
#: words and word-coverage would read 0 on a perfectly good paraphrase.
SPACE_FREE_SCRIPTS = {"CJK", "THAI", "LAO", "MYANMAR", "KHMER"}

#: Function-word profiles for the Latin-script languages this corpus actually
#: contains. The roster answers in English whatever the source language, so a
#: snippet from a Spanish or French document is usually a translation — grounded
#: and unquotable at once, and indistinguishable by any lexical test from an
#: invention. Those are held out rather than scored either way.
#:
#: The corpus metadata cannot do this job: its `language` column reads "English"
#: for the Arabic, Japanese, Spanish and French sources in this sample alike.
LANGUAGE_PROFILES = {
    "en": {"the", "and", "of", "to", "in", "that", "is", "for", "with", "are",
           "this", "was", "were", "from", "which", "has", "have", "been",
           "their", "its", "by", "on", "as", "at", "not", "but", "more", "than",
           "other", "these", "when", "after", "during", "between", "under",
           "within", "will", "would", "also", "only", "such", "there", "who",
           "about", "into", "over"},
    "es": {"el", "la", "los", "las", "de", "del", "que", "en", "por", "para",
           "con", "una", "uno", "como", "es", "son", "se", "su", "sus", "al",
           "lo", "pero", "mas", "este", "esta", "estos", "entre", "sobre",
           "desde", "hasta", "cuando", "donde", "ser", "han", "hay", "fue",
           "tambien", "todo", "todos", "cada", "ademas", "segun", "durante"},
    "fr": {"le", "la", "les", "des", "de", "du", "que", "qui", "en", "dans",
           "pour", "par", "avec", "une", "un", "est", "sont", "sur", "au",
           "aux", "ce", "cette", "ces", "ou", "mais", "plus", "comme", "entre",
           "depuis", "lors", "leur", "leurs", "ils", "elles", "nous", "vous",
           "etre", "ete", "fait", "tous", "toutes", "aussi", "selon", "pendant"},
    "pt": {"o", "a", "os", "as", "de", "do", "da", "dos", "das", "que", "em",
           "para", "por", "com", "uma", "um", "nao", "se", "sua", "seu", "seus",
           "suas", "ao", "mais", "como", "entre", "sobre", "desde", "quando",
           "onde", "ser", "foi", "sao", "tambem", "todos", "cada", "alem",
           "segundo", "durante", "pelo", "pela", "este", "esta"},
    "it": {"il", "lo", "la", "i", "gli", "le", "di", "del", "della", "che",
           "in", "per", "con", "una", "un", "non", "si", "sono", "alla", "al",
           "come", "piu", "tra", "sopra", "dopo", "quando", "dove", "essere",
           "stato", "anche", "tutti", "ogni", "inoltre", "secondo", "durante",
           "dal", "nel", "nella"},
    "de": {"der", "die", "das", "und", "den", "dem", "des", "ein", "eine",
           "einer", "ist", "sind", "von", "zu", "mit", "auf", "fur", "im",
           "nicht", "auch", "als", "aus", "bei", "nach", "werden", "wurde",
           "wird", "durch", "bis", "oder", "aber", "mehr", "zwischen", "uber",
           "unter", "diese", "dieser", "alle"},
}
#: On documents the winning language scores 0.12-0.41 and the runner-up far
#: below; the four sources that land under this are slide decks and a Norwegian
#: report, and they fall through to "unknown", which is graded exactly like
#: English. The floor can only cost signal, never invent a hold-out.
LANGUAGE_FLOOR = 0.10
MIN_LANGUAGE_TOKENS = 50
#: A snippet is <= 25 words, too short for a ratio, so one function word decides
#: it. Below this many tokens even that is noise.
MIN_SNIPPET_TOKENS = 5
#: A document more than half written in a non-Latin script is labelled by the
#: script. Romaji and English boilerplate in a Japanese or Arabic report would
#: otherwise carry the vote.
NON_LATIN_MAJORITY = 0.5


def guess_language(text: str, min_tokens: int = MIN_LANGUAGE_TOKENS,
                   floor: float = LANGUAGE_FLOOR,
                   script_share: dict | None = None) -> str:
    """Coarse language label, or `''` for "no idea". Script first, then profile."""
    if script_share is None:
        counts = script_counts(text)
        total = sum(counts.values()) or 1
        script_share = {k: v / total for k, v in counts.items()}
    for script, share in script_share.items():
        if script != "LATIN" and share >= NON_LATIN_MAJORITY:
            return script
    tokens = re.findall(r"[a-z']+", _fold(text))
    if len(tokens) < min_tokens:
        return ""
    scores = {lang: sum(1 for t in tokens if t in words) / len(tokens)
              for lang, words in LANGUAGE_PROFILES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= floor else ""


def snippet_language(snippet: str) -> str:
    """Same call, tuned for one sentence: any function word is enough."""
    return guess_language(snippet, min_tokens=MIN_SNIPPET_TOKENS,
                          floor=1e-9)


def ngrams(stream: str, n: int = 3) -> set[str]:
    return {stream[i:i + n] for i in range(len(stream) - n + 1)}


#: Function words in every profiled language, pooled. Coverage counts content
#: words only: "the", "of" and "in" are in every document ever written, and
#: counting them puts a fabricated English sentence at 50% support before it
#: says anything at all.
STOPWORDS = frozenset().union(*LANGUAGE_PROFILES.values())


def content_words(snippet: str) -> list[str]:
    """Words that carry the claim. Falls back to everything if none survive."""
    words = word_list(snippet)
    content = [w for w in words if len(w) > 2 and w not in STOPWORDS]
    return content or words


# ---------------------------------------------------------------------------
# The document side, normalised once
# ---------------------------------------------------------------------------

@dataclass
class Document:
    key: str
    text: str
    stream: str = ""
    words: set[str] = field(default_factory=set)
    normalised: str = ""
    script: str = ""
    script_share: dict = field(default_factory=dict)
    figures: set[str] = field(default_factory=set)
    trigrams: set[str] = field(default_factory=set)
    language: str = ""

    @classmethod
    def build(cls, key: str, text: str) -> "Document":
        words = word_list(text)
        counts = script_counts(text)
        total = sum(counts.values()) or 1
        share = {k: v / total for k, v in counts.items()}
        return cls(key=key, text=text, stream=char_stream(text), words=set(words),
                   normalised=" ".join(words),
                   script=(counts.most_common(1)[0][0] if counts else ""),
                   script_share=share, figures=numbers(text),
                   trigrams=ngrams(char_stream(text)),
                   language=guess_language(text, script_share=share))


def load_documents(paths: list[Path]) -> dict[str, Document]:
    docs: dict[str, Document] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload.get("documents", payload)
        for key, row in entries.items():
            text = (row.get("text") or "") if isinstance(row, dict) else str(row)
            if not text.strip():
                # No text means nothing to match against; scoring it would post
                # every snippet as a fabrication.
                LOG.warning("Document %s has no cached text, excluded", key[:12])
                continue
            docs[key] = Document.build(key, text)
        LOG.info("%-28s %4d documents with text", path.name, len(entries))
    return docs


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------

def _rapidfuzz_partial(snippet_norm: str, doc_norm: str) -> float:
    try:
        from rapidfuzz import fuzz
    except ImportError:  # pragma: no cover - environment guard
        return 0.0
    return float(fuzz.partial_ratio(snippet_norm, doc_norm))


def _elided_match(snippet: str, doc: Document) -> bool:
    """Fragments either side of an ellipsis, each found, in document order."""
    fragments = [char_stream(f) for f in _ELLIPSIS.split(snippet)]
    fragments = [f for f in fragments if len(f) >= MIN_FRAGMENT_CHARS]
    if len(fragments) < 2:
        return False
    cursor = 0
    for fragment in fragments:
        found = doc.stream.find(fragment, cursor)
        if found < 0:
            return False
        cursor = found + len(fragment)
    return True


def _hold_out(grade: str, doc: Document) -> str:
    """In a source that is not in the model's answer language, a snippet that
    fails the lexical test has two explanations — a translation the test cannot
    see, and an invention — and no way to separate them. Calling it unsupported
    would post the first as the second, so the whole accusatory band is held out
    for those documents and counted where it can be read.

    The test is *confirmed* English, not "not confirmed foreign": a document the
    profile cannot place (a slide deck of noun phrases, a Norwegian report the
    profiles do not cover) is held out too. That costs real findings on English
    documents the profile happens to miss, which is the direction to err in when
    the alternative is publishing a translation as a fabrication."""
    if grade in ("weak", "unsupported") and doc.language != "en":
        return "cross_language"
    return grade


@dataclass
class Verdict:
    grade: str
    coverage: float
    partial_ratio: float
    figures: int = 0
    figures_found: int = 0

    @property
    def cross_script(self) -> bool:
        return self.grade == "cross_script"


def classify(snippet: str, doc: Document) -> Verdict:
    """Grade one snippet against one document. See the module docstring."""
    stream = char_stream(snippet)
    if not stream:
        # A snippet with no letters or digits in it — "©", "[". It cites nothing,
        # so there is nothing to find; graded apart rather than called a
        # fabrication.
        return Verdict("no_content", 0.0, 0.0)

    figures = numbers(snippet)
    found_figures = len(figures & doc.figures)

    if stream in doc.stream:
        return Verdict("verbatim", 1.0, 100.0, len(figures), found_figures)
    if _elided_match(snippet, doc):
        return Verdict("verbatim_elided", 1.0, 100.0, len(figures), found_figures)

    letters = script_counts(snippet)
    if sum(letters.values()) >= MIN_SCRIPT_CHARS:
        script = letters.most_common(1)[0][0]
        if doc.script_share.get(script, 0.0) < SCRIPT_PRESENCE:
            # The model answered in a script the source barely contains: a
            # translation. Lexical containment cannot adjudicate it either way.
            return Verdict("cross_script", 0.0, 0.0, len(figures), found_figures)

    words = word_list(snippet)
    ratio = _rapidfuzz_partial(" ".join(words), doc.normalised)
    if ratio >= NEAR_VERBATIM:
        return Verdict("near_verbatim", 1.0, ratio, len(figures), found_figures)

    snippet_lang = snippet_language(snippet)
    if doc.language and snippet_lang and snippet_lang != doc.language:
        # The model answered in a different language from the source, and this
        # is not a quote from any part of it that shares the model's language:
        # a translation. Same standing as cross_script — the lexical test cannot
        # decide it, so it does not vote.
        return Verdict("cross_language", 0.0, ratio, len(figures), found_figures)

    if dominant_script(snippet) in SPACE_FREE_SCRIPTS:
        # No whitespace to tokenise on, so coverage is measured over character
        # trigrams of the same normalised stream.
        grams = ngrams(stream)
        coverage = (len(grams & doc.trigrams) / len(grams)) if grams else 0.0
        grade = ("paraphrase" if coverage >= PARAPHRASE_COVERAGE
                 else "weak" if coverage >= WEAK_COVERAGE else "unsupported")
        return Verdict(_hold_out(grade, doc), coverage, ratio,
                       len(figures), found_figures)

    content = content_words(snippet)
    coverage = (sum(1 for w in content if w in doc.words) / len(content)) if content else 0.0
    if coverage >= PARAPHRASE_COVERAGE:
        grade = "paraphrase"
    elif coverage >= WEAK_COVERAGE:
        grade = "weak"
    else:
        grade = "unsupported"
    return Verdict(_hold_out(grade, doc), coverage, ratio, len(figures), found_figures)


# ---------------------------------------------------------------------------
# Scoring a run
# ---------------------------------------------------------------------------

@dataclass
class RunReport:
    label: str
    documents: int = 0
    events: int = 0
    events_with_snippet: int = 0
    snippets: int = 0
    grades: Counter = field(default_factory=Counter)
    figure_snippets: int = 0
    figure_snippets_clean: int = 0
    figures: int = 0
    figures_found: int = 0
    worst: list[tuple[float, str, str, str]] = field(default_factory=list)

    @property
    def judged(self) -> int:
        """Snippets the lexical test applies to. Cross-script and contentless
        snippets are neither found nor missing, so they leave the denominator."""
        return self.snippets - sum(self.grades[g] for g in HELD_OUT)

    def rate(self, grades) -> tuple[int, int]:
        return sum(self.grades[g] for g in grades), self.judged


def score_run(run: Run, docs: dict[str, Document], keep_examples: int = 8) -> RunReport:
    report = RunReport(run.label)
    seen_docs = set()
    for key, events in run.events.items():
        doc = docs.get(key)
        if doc is None:
            continue
        seen_docs.add(key)
        for event in events:
            report.events += 1
            snippets = _split(event.get("evidence_snippets"))
            if snippets:
                report.events_with_snippet += 1
            for snippet in snippets:
                verdict = classify(snippet, doc)
                report.snippets += 1
                report.grades[verdict.grade] += 1
                if verdict.figures:
                    report.figure_snippets += 1
                    report.figures += verdict.figures
                    report.figures_found += verdict.figures_found
                    if verdict.figures_found == verdict.figures:
                        report.figure_snippets_clean += 1
                if verdict.grade in ("weak", "unsupported"):
                    report.worst.append((verdict.coverage, key, snippet,
                                         verdict.grade))
    report.documents = len(seen_docs)
    report.worst.sort(key=lambda r: r[0])
    report.worst = report.worst[:keep_examples]
    return report


# ---------------------------------------------------------------------------
# The null: how often does a snippet match a document it did not come from?
# ---------------------------------------------------------------------------

DECOY_SEED = 42


def decoy_check(runs: list[Run], docs: dict[str, Document],
                seed: int = DECOY_SEED) -> tuple[int, int, int]:
    """Re-score every snippet against a random *other* document.

    This is the test's false-positive floor. Normalising away punctuation and
    whitespace makes containment more forgiving, and the fair question about a
    more forgiving test is how much it would find in text that cannot contain
    the answer. `(n, quotable, grounded)`.
    """
    rng = random.Random(seed)
    keys = list(docs)
    n = quotable = grounded = 0
    for run in runs:
        for key, events in run.events.items():
            if key not in docs:
                continue
            for event in events:
                for snippet in _split(event.get("evidence_snippets")):
                    decoy = key
                    while decoy == key and len(keys) > 1:
                        decoy = rng.choice(keys)
                    verdict = classify(snippet, docs[decoy])
                    n += 1
                    quotable += verdict.grade in QUOTABLE
                    grounded += verdict.grade in GROUNDED
    return n, quotable, grounded


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _pct(n: int, d: int) -> str:
    return f"{n / d:.1%}" if d else "–"


def render(reports: list[RunReport], docs: dict[str, Document],
           arms: list[str], examples: int,
           decoy: tuple[int, int, int] | None = None) -> str:
    empty = [r for r in reports if not r.snippets]
    reports = [r for r in reports if r.snippets]
    non_latin = sorted(d.script for d in docs.values()
                       if d.script and d.script != "LATIN")
    languages = Counter(d.language or "unplaced" for d in docs.values())
    lines = [
        "# Citation quality — are the evidence snippets in the document?",
        "",
        f"Documents: **{len(docs)}** (arms: {', '.join(arms)}), matched against the "
        "12,000-character window the model was given, not the full source.",
        f"Non-Latin-script documents: {len(non_latin)} "
        f"({', '.join(f'{c}×{s}' for s, c in sorted(Counter(non_latin).items()))}). "
        "No human annotation is used anywhere in this file.",
        "",
        "Source language, by function-word profile: "
        + ", ".join(f"{n}×{lang}" for lang, n in languages.most_common())
        + f". The {sum(n for l, n in languages.items() if l != 'en')} documents "
        "not confirmed English have their weak and unsupported snippets held "
        "out: the roster answers in English regardless of source language, so "
        "a failed lexical match there is as likely to be a translation as an "
        "invention.",
        "",
        "`quotable` = the snippet can be located in the text (verbatim, elided "
        "or near-verbatim). `grounded` = quotable, or every word of it is in "
        "the document. Prompt 5 asks for \"snippets **or paraphrases**\", so "
        "`grounded` is the obedience-aware rate and `quotable` is the auditor's "
        "rate — the one that says whether a record can be traced back to a line "
        "of source. Held out of every denominator: `cross_script` and "
        "`cross_language` (a translation and an invention look identical to a "
        "lexical test) and `no_content`.",
        "",
        "## Found or not found",
        "",
        "Raw counts first. `found` is a snippet located in the document text; "
        "`not found` is everything else the test applies to, paraphrases "
        "included.",
        "",
        "| run | events | snippets | judged | found | not found | found rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in reports:
        q_n, q_d = r.rate(QUOTABLE)
        lines.append(
            f"| {r.label} | {r.events} | {r.snippets} | {q_d} | {q_n} | {q_d - q_n} "
            f"| {format_rate(q_n, q_d)} |")

    lines += ["", "## Rates", "",
              "| run | with snippet | quotable | grounded | unsupported |",
              "| --- | ---: | --- | --- | --- |"]
    for r in reports:
        q_n, q_d = r.rate(QUOTABLE)
        g_n, _ = r.rate(GROUNDED)
        u_n, _ = r.rate(("weak", "unsupported"))
        lines.append(
            f"| {r.label} | {_pct(r.events_with_snippet, r.events)} "
            f"| {format_rate(q_n, q_d)} "
            f"| {format_rate(g_n, q_d)} | {format_rate(u_n, q_d)} |")

    lines += ["", "## Grade counts", "",
              "| run | " + " | ".join(GRADES + HELD_OUT) + " |",
              "| --- | " + " | ".join("---:" for _ in GRADES + HELD_OUT) + " |"]
    for r in reports:
        cells = " | ".join(str(r.grades[g]) for g in GRADES + HELD_OUT)
        lines.append(f"| {r.label} | {cells} |")

    lines += ["", "## Figures quoted in snippets", "",
              "A snippet is clean when every digit string in it also occurs in the "
              "document. This survives paraphrase, which is why it is reported "
              "apart from the grade.", "",
              "| run | snippets with a figure | clean | figures matched |",
              "| --- | ---: | --- | --- |"]
    for r in reports:
        lines.append(
            f"| {r.label} | {r.figure_snippets} "
            f"| {format_rate(r.figure_snippets_clean, r.figure_snippets)} "
            f"| {_pct(r.figures_found, r.figures)} ({r.figures}) |")

    if decoy:
        n, quotable, grounded = decoy
        lines += ["", "## Null check", "",
                  "Every snippet re-scored against a random *other* document in "
                  f"the set (seed {DECOY_SEED}). This is the floor the rates "
                  "above are measured from: what the matcher finds in text that "
                  "cannot contain the answer.", "",
                  f"- snippets re-scored: {n}",
                  f"- called quotable anyway: {quotable} ({_pct(quotable, n)})",
                  f"- called grounded anyway: {grounded} ({_pct(grounded, n)})"]

    if examples:
        lines += ["", "## Lowest-coverage snippets", "",
                  "The bottom of each run, by content-word coverage. These are "
                  "the candidate fabrications; a document id is given so each "
                  "can be checked by hand. Two classes dominate them: "
                  "meta-commentary written in place of evidence (\"Explicit "
                  "date, location, and impact\"), and quotations from sources "
                  "whose stored text is encoding-damaged.", ""]
        for r in reports:
            if not r.worst:
                continue
            lines.append(f"**{r.label}**")
            lines.append("")
            for coverage, key, snippet, grade in r.worst[:examples]:
                text = snippet.replace("|", "\\|")[:160]
                lines.append(f"- `{key[:12]}` {grade}, coverage {coverage:.0%} — {text}")
            lines.append("")
    if empty:
        lines += ["## Runs with no snippets to score", "",
                  "These returned nothing over these documents — an errored run "
                  "has no citations to audit, which is not the same as citing "
                  "badly.", ""]
        lines += [f"- {r.label}" for r in empty] + [""]
    return "\n".join(lines) + "\n"


def write_snippet_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "run", "asset_key", "event_index", "snippet", "grade",
            "coverage", "partial_ratio", "figures", "figures_found"])
        writer.writeheader()
        writer.writerows(rows)


def collect_snippet_rows(run: Run, docs: dict[str, Document]) -> list[dict]:
    rows = []
    for key, events in run.events.items():
        doc = docs.get(key)
        if doc is None:
            continue
        for event in events:
            for snippet in _split(event.get("evidence_snippets")):
                v = classify(snippet, doc)
                rows.append({"run": run.label, "asset_key": key,
                             "event_index": event.get("event_index"),
                             "snippet": snippet, "grade": v.grade,
                             "coverage": f"{v.coverage:.3f}",
                             "partial_ratio": f"{v.partial_ratio:.1f}",
                             "figures": v.figures,
                             "figures_found": v.figures_found})
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR,
                   help="directory of <slug>/event_extractions.jsonl runs")
    p.add_argument("--arm", action="append", choices=sorted(DOCUMENT_SETS),
                   default=[], help="document arm to score; repeatable, "
                                    "default both (the pooled 217)")
    p.add_argument("--run", action="append", default=[], metavar="LABEL=PATH",
                   help="extra run to score; repeatable")
    p.add_argument("--no-references", action="store_true",
                   help="omit the gpt-5 Azure production and NER baseline arms")
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--snippet-csv", type=Path, default=DEFAULT_SNIPPET_CSV)
    p.add_argument("--examples", type=int, default=5)
    p.add_argument("--no-decoy", action="store_true",
                   help="skip the random-other-document null check")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()

    arms = args.arm or sorted(DOCUMENT_SETS)
    docs = load_documents([DOCUMENT_SETS[a] for a in arms])
    if not docs:
        LOG.error("No documents with text; nothing to match against.")
        return 1

    runs: list[Run] = [Run(label, path)
                       for label, path, _stats in discover_runs(args.out_dir)]
    if not args.no_references:
        for label, path in REFERENCE_RUNS:
            if path.exists():
                runs.append(Run(label, path))
            else:
                LOG.warning("Reference run missing, skipping: %s", path)
    for spec in args.run:
        label, _, path = spec.partition("=")
        runs.append(Run(label.strip(), Path(path.strip())))

    reports, csv_rows = [], []
    for run in runs:
        report = score_run(run, docs)
        if not report.snippets:
            LOG.warning("%s produced no snippets over these documents", run.label)
        reports.append(report)
        csv_rows.extend(collect_snippet_rows(run, docs))
        q_n, q_d = report.rate(QUOTABLE)
        LOG.info("%-32s %5d snippets  quotable %s", run.label, report.snippets,
                 _pct(q_n, q_d))

    decoy = None if args.no_decoy else decoy_check(runs, docs)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render(reports, docs, arms, args.examples, decoy),
                           encoding="utf-8")
    write_snippet_csv(args.snippet_csv, csv_rows)
    LOG.info("Wrote %s and %s", args.report, args.snippet_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
