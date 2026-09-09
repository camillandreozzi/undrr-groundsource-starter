"""PreventionWeb hazard labels as regexes, for the NER baseline.

The LLM was told to emit only exact PreventionWeb labels, and was given a
normalisation table mapping common source terms onto them
(`fonte.prompts.PREVENTIONWEB_HAZARD_INSTRUCTION`). This module encodes
the same table as patterns so the baseline emits the *same label vocabulary*.
That is what makes `event_hazard` comparable between the two runs, and what
lets `fonte.hazard_families.hazard_family` segment both identically.

Order matters only for readability; every pattern is tried and all matches are
kept, joined with " | " the way the LLM joins compound hazards.
"""
from __future__ import annotations

import re
from typing import Iterator, NamedTuple

# Exact PreventionWeb labels -> alternation of surface forms.
#
# Patterns are deliberately conservative: a term earns a match only when it is
# specific enough that a false positive is unlikely in a corpus that is mostly
# policy and guidance documents. "risk", "hazard", "disaster" and "emergency"
# are NOT triggers — four fifths of this corpus talks about them in the
# abstract, and matching those would flood the baseline with non-events.
_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Avalanche", r"avalanche"),
    ("Cold Wave", r"cold ?wave|cold snap|extreme cold|freeze event"),
    (
        "Cyclone, Hurricane and Typhoon",
        r"cyclone|hurricane|typhoon|tropical storm|tropical depression|storm surge",
    ),
    (
        "Drought and Desertification",
        r"drought|desertification|water scarcity|famine",
    ),
    ("Earthquake", r"earthquake|seismic event|tremor|quake"),
    (
        "Epidemic and pandemic",
        r"epidemic|pandemic|disease outbreak|cholera outbreak|ebola|covid[- ]?19",
    ),
    (
        "Flood",
        r"flood(?:s|ing|ed)?|flash flood|inundation|glacial lake outburst|gl[oa]f\b",
    ),
    (
        "Heatwave and Extreme Heat",
        r"heat ?wave|extreme heat|heat stress|record heat",
    ),
    (
        "Insect infestation",
        r"locust|insect infestation|pest infestation|armyworm|swarm of locusts",
    ),
    ("Land subsidence", r"land subsidence|ground subsidence|sinkhole"),
    ("Landslide", r"landslide|mudslide|mud ?flow|debris flow|rockfall|rock fall"),
    (
        "Nuclear, biological, chemical (NBC)",
        r"nuclear (?:accident|disaster|incident)|radiolog|radioactive release"
        r"|chemical (?:spill|leak|accident|release)|gas leak|toxic release"
        r"|contamination incident|natech",
    ),
    ("Sea level rise", r"sea[- ]level rise|rising sea level"),
    (
        "Technological hazard",
        r"dam (?:failure|burst|collapse)|bridge collapse|building collapse"
        r"|industrial accident|oil spill|rail(?:way)? accident|train derail"
        r"|plane crash|aircraft crash|ferry (?:sinking|capsiz)|mine (?:collapse|disaster)"
        r"|power (?:outage|blackout)|urban fire|factory fire|explosion",
    ),
    ("Thunderstorm", r"thunderstorm|lightning strike|hailstorm|hail event"),
    ("Tornado", r"tornado|twister"),
    ("Tsunami", r"tsunami|tidal wave"),
    ("Volcano", r"volcan(?:o|ic|ism)|eruption|lahar|ash ?fall|lava flow|pyroclastic"),
    ("Wildfire", r"wildfire|bushfire|forest fire|wildland fire|veld ?fire"),
    # "Other PreventionWeb hazard collection labels", per the prompt.
    ("Sand and dust storm", r"sand ?storm|dust storm|sand and dust storm|haboob"),
    ("Stampede and crowd collapse", r"stampede|crowd (?:crush|collapse)"),
    (
        "Geomagnetic storm and space weather",
        r"geomagnetic storm|solar (?:flare|storm)|space weather",
    ),
)

HAZARD_PATTERNS: tuple[tuple[str, re.Pattern], ...] = tuple(
    (label, re.compile(rf"\b(?:{alts})", re.I)) for label, alts in _PATTERNS
)

# Volcano's `eruption` and Technological's `explosion` are common metaphors
# ("an eruption of interest", "population explosion"). Blank these phrases
# before matching rather than complicating every pattern.
_FALSE_FRIENDS = re.compile(
    r"population explosion|explosion (?:of|in) (?:interest|growth|demand|data)"
    r"|eruption of (?:interest|violence|conflict)"
    r"|urban heat island",
    re.I,
)

ALL_LABELS: tuple[str, ...] = tuple(label for label, _ in _PATTERNS)


class HazardMatch(NamedTuple):
    label: str
    start: int
    end: int
    text: str


def find_hazards(text: str) -> list[HazardMatch]:
    """Every hazard mention in `text`, in document order.

    Overlapping matches from different labels are all kept — "earthquake and
    tsunami" legitimately yields two. Repeated mentions of the same label are
    all kept too, because the caller needs their positions to decide which
    sentence window an event belongs to.
    """
    if not text:
        return []
    # Blank false friends in place so offsets stay valid against the original.
    cleaned = _FALSE_FRIENDS.sub(lambda m: " " * len(m.group(0)), text)
    out: list[HazardMatch] = []
    for label, pat in HAZARD_PATTERNS:
        for m in pat.finditer(cleaned):
            out.append(HazardMatch(label, m.start(), m.end(), m.group(0)))
    out.sort(key=lambda h: (h.start, h.label))
    return out


def join_labels(labels: Iterator[str] | list[str]) -> str:
    """Compound hazard string in the LLM's format: unique labels, " | " joined.

    Order follows ALL_LABELS so the same set always renders the same way,
    which matters when comparing strings between the two runs.
    """
    seen = {l for l in labels}
    return " | ".join(l for l in ALL_LABELS if l in seen)
