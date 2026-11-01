"""The response schemas the ablation sends to the model.

In json_schema mode the field descriptions travel inside the schema, so they
are a second prompt channel: "Phase 2 location rules", "NOT publication /
workshop / report dates" and the evidence format live there, not in the system
prompt. An ablation that edits only the prompt would leave those rules in
place, so every configuration names its schema as well.

Two knobs, nothing else:

  drop_evidence   `evidence_snippets` is hidden from the schema the model sees
                  (`SkipJsonSchema`), but stays on the class with a `[]`
                  default, so `extraction_to_output_rows` still finds it.
  neutral         every description that carries a rule is removed; what is
                  left states format and allowed values only. Names, types,
                  defaults and field order are unchanged.

Every variant subclasses the production classes, so `_align_admin_levels` and
`_keep_verified_unique_events` run unchanged — the post-filter is held fixed.
The classes keep the production names because the schema's `name`, its `$defs`
key and its `title` are derived from them.
"""
from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from pydantic import Field, create_model, model_validator  # noqa: E402
from pydantic.json_schema import SkipJsonSchema  # noqa: E402

from fonte import app_event_focus as prod  # noqa: E402


class _WithoutEvidence(prod.EventExtraction):
    """Hides `evidence_snippets` from the schema and ignores it if sent anyway.

    Strict decoding (`additionalProperties: false`) already stops the model
    emitting the key; discarding it here means a configuration without evidence
    can never carry any into the scored rows. The raw JSON is kept regardless.
    """
    evidence_snippets: SkipJsonSchema[List[str]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _discard_evidence(cls, data):
        if isinstance(data, dict) and "evidence_snippets" in data:
            data = {k: v for k, v in data.items() if k != "evidence_snippets"}
        return data

ADMIN_LEVELS_TEXT = ", ".join(prod.LOCATION_ADMIN_LEVELS)

# Format and allowed values only. Confidence values are lowercase because the
# post-filter compares them case-sensitively (`app_event_focus.py` L222).
NEUTRAL_FIELDS = {
    "is_single_actual_event": (bool, Field()),
    "is_verifiable_event": (bool, Field()),
    "event_hazard": (Optional[str], Field(default=None)),
    "event_dates": (List[str], Field(
        default_factory=list,
        description="Prefer YYYY-MM-DD; allow YYYY-MM, YYYY, or a short source phrase.")),
    "affected_locations": (List[str], Field(default_factory=list)),
    "location_admin_levels": (List[str], Field(
        default_factory=list,
        description=("One tag per entry of affected_locations, in the same order."
                     f" Allowed values: {ADMIN_LEVELS_TEXT}."))),
    "key_impacts": (List[str], Field(
        default_factory=list, description="Up to 5 concise impact statements.")),
    "event_confidence": (Optional[str], Field(
        default=None, description="Allowed values: high, medium, low.")),
    "missing_information": (List[str], Field(default_factory=list)),
}


@functools.cache
def build_schema(*, drop_evidence: bool, neutral: bool) -> type[prod.DocumentEventExtractions]:
    """The document-level response model for one configuration."""
    if not (drop_evidence or neutral):
        return prod.DocumentEventExtractions          # the production object itself

    fields = dict(NEUTRAL_FIELDS) if neutral else {}
    base = _WithoutEvidence if drop_evidence else prod.EventExtraction
    event = create_model("EventExtraction", __base__=base, **fields)

    events_kw = {} if neutral else {
        "description": prod.DocumentEventExtractions.model_fields["events"].description}
    return create_model(
        "DocumentEventExtractions", __base__=prod.DocumentEventExtractions,
        events=(List[event], Field(default_factory=list, **events_kw)))
