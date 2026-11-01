"""Free-text hazards -> PreventionWeb labels, fixed before any ablation output exists.

`no_vocab` and `bare` are not told the vocabulary, so their `event_hazard` is a
phrase ("flash flooding", "earthquake and tsunami") where the gold has a label
("Flood", "Earthquake | Tsunami"). The scorer's `hazard_key` already rolls
eight families up by regex, but inside `other` it compares folded labels, so
"cold spell" would never meet "Cold Wave". This module maps every component
onto exact labels with a rule written down in advance, and the same rule runs
on every configuration — on exact labels it is the identity, so it changes
nothing for `full` (a test pins that).

Per `|`-separated component:
  1. an exact label (folded, whitespace-collapsed) is kept as that label;
  2. otherwise the component is scanned, hyphens read as spaces, with the NER
     baseline's lexicon (`benchmark_ner/hazard_lexicon.py`, false friends
     blanked first), plus
     the prompt-5 normalisation-table terms it lacks, plus the two collection
     labels it has no pattern for;
  3. overlapping matches go to the longest span ("fall armyworm" is Fall
     armyworm, not Insect infestation), ties to table order;
  4. labels are kept in order of first occurrence, without repeats;
  5. a component that matches nothing passes through unchanged and is counted.

`LEXICON_SHA256` fingerprints the rule; the protocol freezes it.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_ner.hazard_lexicon import _FALSE_FRIENDS, _PATTERNS  # noqa: E402

# The 19 main labels and 5 collection labels of `PREVENTIONWEB_HAZARD_INSTRUCTION`.
VOCABULARY: tuple[str, ...] = (
    "Avalanche", "Cold Wave", "Cyclone, Hurricane and Typhoon",
    "Drought and Desertification", "Earthquake", "Epidemic and pandemic", "Flood",
    "Heatwave and Extreme Heat", "Insect infestation", "Land subsidence", "Landslide",
    "Nuclear, biological, chemical (NBC)", "Sea level rise", "Technological hazard",
    "Thunderstorm", "Tornado", "Tsunami", "Volcano", "Wildfire",
    "Sand and dust storm", "Fall armyworm", "Stampede and crowd collapse",
    "Geomagnetic storm and space weather", "Human-induced earthquakes",
)

# Terms from prompt 5's normalisation table that the NER lexicon does not
# cover, the two labels it has no pattern for, and a few unambiguous synonyms.
_EXTRA: tuple[tuple[str, str], ...] = (
    ("Fall armyworm", r"fall armyworm"),
    ("Human-induced earthquakes", r"human[- ]induced (?:earthquakes?|seismicity)|induced seismicity"),
    ("Technological hazard",
     r"technolog(?:ical|y)|collapse|bridge failure|transport accident|water supply failure"
     r"|ict outage|malware|cyber ?attack"),
    ("Nuclear, biological, chemical (NBC)",
     r"chemical|nuclear|biological|radiological|contamination|\bnbc\b"),
    ("Epidemic and pandemic",
     r"cholera|measles|dengue|influenza|zika|coronavirus|plague"),
    ("Cold Wave", r"cold spell"),
    ("Drought and Desertification", r"dry spell"),
    ("Wildfire", r"wild ?fires?|bush ?fires?|grass ?fires?"),
)

_TABLE: tuple[tuple[str, str], ...] = _PATTERNS + _EXTRA
_COMPILED: tuple[tuple[int, str, re.Pattern], ...] = tuple(
    (rank, label, re.compile(rf"\b(?:{alts})", re.I)) for rank, (label, alts) in enumerate(_TABLE)
)

LEXICON_SHA256 = hashlib.sha256(json.dumps(
    {"vocabulary": VOCABULARY, "table": _TABLE, "false_friends": _FALSE_FRIENDS.pattern,
     "hyphens": "read as spaces"}, ensure_ascii=False).encode("utf-8")).hexdigest()


def _key(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(unicodedata.normalize("NFKC", stripped).casefold().split())


_EXACT = {_key(label): label for label in VOCABULARY}


@dataclass(frozen=True)
class NormalisedHazard:
    value: str                    # " | "-joined, what the scorer reads as event_hazard
    components: tuple[str, ...]   # labels and passed-through components, in order
    unmapped: tuple[str, ...]     # components that matched nothing
    changed: bool                 # value differs from the raw string


def _scan(component: str) -> list[str]:
    # Hyphens read as spaces ("heat-wave", "flash-flood"); same length, so offsets hold.
    cleaned = _FALSE_FRIENDS.sub(lambda m: " " * len(m.group(0)), component.replace("-", " "))
    matches = [(m.start(), m.end(), rank, label)
               for rank, label, pat in _COMPILED for m in pat.finditer(cleaned)]
    chosen: list[tuple[int, int, str]] = []
    for start, end, _rank, label in sorted(matches, key=lambda m: (m[0] - m[1], m[2])):
        if all(end <= s or start >= e for s, e, _ in chosen):
            chosen.append((start, end, label))
    return [label for _s, _e, label in sorted(chosen)]


def normalise_hazard(raw: str | None) -> NormalisedHazard:
    raw = str(raw or "").strip()
    out: list[str] = []
    unmapped: list[str] = []
    for component in (p.strip() for p in raw.split("|")):
        if not component:
            continue
        exact = _EXACT.get(_key(component))
        labels = [exact] if exact else _scan(component)
        if not labels:
            unmapped.append(component)
            labels = [component]
        out.extend(label for label in labels if label not in out)
    value = " | ".join(out)
    return NormalisedHazard(value, tuple(out), tuple(unmapped), value != raw)
