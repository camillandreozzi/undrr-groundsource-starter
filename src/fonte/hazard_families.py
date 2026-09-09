"""Hazard family taxonomy shared by the sampling, scoring and QA scripts.

The extractor emits free-text hazards (50 distinct values in the 10k
production run, including compounds like "Earthquake | Tsunami"), which is
too granular to segment a few hundred judgements by. These patterns roll
them up into a handful of families that carry enough rows to report on.

Order matters: the first pattern to match wins, so "Earthquake | Tsunami"
lands in `earthquake` rather than splitting.
"""
from __future__ import annotations

import re

HAZARD_FAMILIES: tuple[tuple[str, re.Pattern], ...] = (
    ("flood", re.compile(r"flood|inundation|deluge", re.I)),
    ("earthquake", re.compile(r"earthquake|seismic|quake|tsunami", re.I)),
    ("cyclone", re.compile(r"cyclone|hurricane|typhoon|storm", re.I)),
    ("drought", re.compile(r"drought|famine|water scarcity", re.I)),
    ("wildfire", re.compile(r"wildfire|bushfire|forest fire|fire", re.I)),
    ("landslide", re.compile(r"landslide|mudslide|rockfall", re.I)),
    ("volcano", re.compile(r"volcan|eruption|lahar", re.I)),
    ("heat", re.compile(r"heat ?wave|extreme heat", re.I)),
)

OTHER = "other"

# The `storm` alternative in the cyclone pattern otherwise swallows hazards
# that have nothing to do with tropical cyclones. Strip these phrases before
# matching, so "Geomagnetic storm and space weather" lands in `other` while a
# genuine compound like "Cyclone, Hurricane and Typhoon | Sand and dust storm"
# still resolves to `cyclone` on its remaining text.
_NOT_CYCLONE = re.compile(r"geomagnetic storm|space weather|sand and dust storm|dust storm", re.I)


def hazard_family(text: str) -> str:
    """Map a hazard string to its family, or `other` when nothing matches."""
    if not text:
        return OTHER
    cleaned = _NOT_CYCLONE.sub(" ", str(text))
    for fam, pat in HAZARD_FAMILIES:
        if pat.search(cleaned):
            return fam
    return OTHER
