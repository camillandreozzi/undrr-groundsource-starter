"""The model roster.

Every entry runs prompt 5 unchanged. What varies is the model, so anything that
would give one arm a different prompt, a different input window or a different
post-filter belongs somewhere else.

`id` values are OpenRouter model slugs and they move: models are added, renamed
and retired continuously. Nothing here is trusted blind — run

    python -m benchmark_openrouter.run_openrouter --check-models

first. It resolves every id against OpenRouter's live catalogue, prints
near-misses for the ones that no longer exist, and shows context length and
price so the roster can be corrected before any money is spent.

TIERS
-----
frontier  the apples-to-apples comparison against the gpt-5 Azure production arm
open      cheap / open-weight — "how much is the frontier model actually buying?"
small     small and fast — does the prompt-5 rule set survive at 10k+ scale prices?
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

Tier = Literal["frontier", "open", "small"]
StructuredMode = Literal["auto", "json_schema", "json_object"]


def slugify(model_id: str) -> str:
    """`anthropic/claude-opus-5` -> `anthropic-claude-opus-5`, for a directory name."""
    slug = model_id.strip().lower().replace(".", "-")
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    return re.sub(r"-{2,}", "-", slug).strip("-")


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    tier: Tier
    #: Passed as extra_body={"reasoning": {"effort": ...}}. None disables it.
    #: `medium` matches the production Azure arm's AZURE_OPENAI_REASONING_EFFORT.
    reasoning_effort: Optional[str] = None
    #: `auto` tries strict json_schema and falls back to json_object on refusal.
    #: Pin it when a model is known to only do one, to save a wasted call per doc.
    structured_output: StructuredMode = "auto"

    @property
    def slug(self) -> str:
        return slugify(self.id)


# Ordered frontier -> open -> small; report tables preserve this order.
#
# `reasoning_effort` and `structured_output` below are set from each model's
# advertised `supported_parameters` as of 2026-09-06, not from assumption.
# `--check-models` re-verifies both against the live catalogue and warns when a
# spec has drifted out of line with what the model actually supports.
#
# "medium" effort matches AZURE_OPENAI_REASONING_EFFORT on the production arm,
# so reasoning-capable models are compared on the production setting rather than
# on their own defaults. It is a choice, and it is a confound: the two models
# below that cannot reason are not being handicapped deliberately, they simply
# have no equivalent knob.
ROSTER: tuple[ModelSpec, ...] = (
    # --- frontier ----------------------------------------------------------
    ModelSpec("anthropic/claude-opus-5", "Claude Opus 5", "frontier",
              reasoning_effort="medium"),
    ModelSpec("anthropic/claude-sonnet-5", "Claude Sonnet 5", "frontier",
              reasoning_effort="medium"),
    # Same model the Azure production arm runs, reached a different way: a
    # control on whether routing/provider alone moves the numbers.
    ModelSpec("openai/gpt-5", "GPT-5 (OpenRouter)", "frontier",
              reasoning_effort="medium"),
    ModelSpec("openai/gpt-5.4", "GPT-5.4", "frontier", reasoning_effort="medium"),
    ModelSpec("google/gemini-2.5-pro", "Gemini 2.5 Pro", "frontier",
              reasoning_effort="medium"),
    ModelSpec("x-ai/grok-4.6", "Grok 4.6", "frontier", reasoning_effort="medium"),
    # --- cheap / open-weight ----------------------------------------------
    ModelSpec("deepseek/deepseek-chat-v3.1", "DeepSeek V3.1", "open",
              reasoning_effort="medium"),
    # Advertises response_format but not structured_outputs: pinning it saves a
    # doomed strict call on every document.
    ModelSpec("qwen/qwen3-235b-a22b", "Qwen3 235B", "open",
              reasoning_effort="medium", structured_output="json_object"),
    ModelSpec("meta-llama/llama-4-maverick", "Llama 4 Maverick", "open"),
    ModelSpec("mistralai/mistral-large-2512", "Mistral Large", "open"),
    # --- small / fast ------------------------------------------------------
    ModelSpec("anthropic/claude-haiku-4.5", "Claude Haiku 4.5", "small",
              reasoning_effort="medium"),
    ModelSpec("openai/gpt-5-mini", "GPT-5 mini", "small", reasoning_effort="medium"),
    ModelSpec("google/gemini-2.5-flash", "Gemini 2.5 Flash", "small",
              reasoning_effort="medium"),
)

BY_ID = {m.id: m for m in ROSTER}
BY_SLUG = {m.slug: m for m in ROSTER}


def select(models: list[str] | None = None, tier: str | None = None) -> list[ModelSpec]:
    """Resolve a --model / --tier selection to roster entries.

    A `--model` id that is not on the roster is accepted and wrapped in a
    default spec, so a one-off model can be tried without editing this file.
    """
    if models:
        return [BY_ID.get(m) or ModelSpec(m, m, "frontier") for m in models]
    if tier:
        return [m for m in ROSTER if m.tier == tier]
    return list(ROSTER)
