"""The five ablation configurations, built from prompt 5 rather than retyped.

    python -m ablation.configs --write      # render -> ablation/prompts/ (refuses to clobber)
    python -m ablation.configs --check      # rendered files still match the code?

Prompt 5's system message is cut at its own section headers into an ordered set
of parts that join back to the production text byte for byte. Each ablation is
a transform on those parts, so what a configuration removes is exactly the text
it names and nothing else:

  full            prompt 5 and the production schema, untouched.
  no_evidence     no `evidence_snippets` field; the two sentences that mention
                  evidence lose that mention.
  no_vocab        the PreventionWeb vocabulary block (and the "no exact label ->
                  drop the event" gate inside it) becomes a free-text hazard line.
  reduced_rules   the output structure stays; the task-specific disambiguation
                  rules (search scope, what is not an event, metadata and
                  passing mentions, date, location, confidence and single-event
                  rules) go, in the prompt and in the schema descriptions.
  bare            all three.

The transforms commute: an edit whose target section another transform has
already removed is skipped and logged, so `bare` is the same text whichever
order they run in (`tests/test_ablation.py` checks all six orders).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from openai.lib._parsing._completions import type_to_response_format_param  # noqa: E402

from ablation.schemas import build_schema  # noqa: E402
from fonte.prompts import (  # noqa: E402
    PREVENTIONWEB_HAZARD_INSTRUCTION,
    UNIFIED_VERIFICATION_RECALL_SYSTEM_PROMPT,
    UNIFIED_VERIFICATION_RECALL_USER_INSTRUCTION,
    PromptSpec,
    get_prompt,
)

PROMPTS_DIR = REPO_ROOT / "ablation" / "prompts"
CONFIGS = ("full", "no_evidence", "no_vocab", "reduced_rules", "bare")

# Section name -> the header that opens it. `role` opens the prompt.
SECTION_HEADERS = (
    ("preamble", "Use prompt 3 / prompt 4 style"),
    ("search_scope", "Search scope:\n"),
    ("evidence", "Evidence discipline:\n"),
    ("hazard", "Hazard classification:\n"),
    ("date", "Date rules:\n"),
    ("location", "Location rules:\n"),
    ("admin", "Admin-level tags:\n"),
    ("confidence", "Confidence and verifiability:\n"),
    ("single_event", "is_single_actual_event:\n"),
    ("return", "Return JSON matching the schema exactly"),
)

NO_VOCAB_HAZARD = (
    "Hazard classification:\n"
    "For each returned event, set event_hazard to a short description of the hazard as\n"
    "the source describes it. If one event involves several hazards, name each of them.\n\n"
)
NEUTRAL_TASK = (
    "Extract every disaster or hazard event reported in the document. Return one event\n"
    "object per event.\n\n"
)
NEUTRAL_RETURN = (
    "Return JSON matching the schema exactly, with a top-level events list. Return events=[]\n"
    "when the document reports no event."
)
NEUTRAL_USER_INSTRUCTION = (
    "Extract every disaster or hazard event reported in this metadata and document text."
    " Return JSON matching the schema exactly."
)
REDUCED_DROPPED = ("preamble", "date", "location", "confidence", "single_event")


class AblationError(RuntimeError):
    pass


@dataclass
class Parts:
    """A prompt in flight: ordered sections, the user instruction, the schema knobs."""
    sections: dict[str, str]
    user_instruction: str
    drop_evidence: bool = False
    neutral: bool = False
    log: list[str] = field(default_factory=list)

    def system_prompt(self) -> str:
        return "".join(self.sections.values())


def parse_sections(prompt: str = UNIFIED_VERIFICATION_RECALL_SYSTEM_PROMPT) -> dict[str, str]:
    """Cut the prompt at its headers. Each part keeps its trailing blank line."""
    starts = [("role", 0)]
    for name, header in SECTION_HEADERS:
        if prompt.count(header) != 1:
            raise AblationError(f"header {header!r} occurs {prompt.count(header)} times")
        starts.append((name, prompt.index(header)))
    if [s for _, s in starts] != sorted(s for _, s in starts):
        raise AblationError("prompt 5 sections are out of the expected order")
    bounds = [s for _, s in starts[1:]] + [len(prompt)]
    sections = {name: prompt[start:end] for (name, start), end in zip(starts, bounds)}

    if "".join(sections.values()) != prompt:
        raise AblationError("sections do not join back to prompt 5")
    if sections["hazard"] != f"Hazard classification:\n{PREVENTIONWEB_HAZARD_INSTRUCTION}\n\n":
        raise AblationError("the hazard section is not exactly the PreventionWeb block")
    return sections


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AblationError(f"{old!r} occurs {text.count(old)} times, expected once")
    return text.replace(old, new)


def _edit(parts: Parts, section: str, old: str, new: str, op: str) -> None:
    if section not in parts.sections:
        parts.log.append(f"{op}: skipped, section {section!r} already removed")
        return
    parts.sections[section] = _replace_once(parts.sections[section], old, new)
    parts.log.append(f"{op}: applied")


def apply_no_evidence(parts: Parts) -> None:
    _edit(parts, "evidence", "key_impacts and evidence_snippets must be grounded",
          "key_impacts must be grounded", "no_evidence.grounding")
    _edit(parts, "confidence", "impact or evidence item.", "impact.",
          "no_evidence.confidence")
    parts.drop_evidence = True


def apply_no_vocab(parts: Parts) -> None:
    _edit(parts, "hazard", parts.sections.get("hazard", ""), NO_VOCAB_HAZARD,
          "no_vocab.hazard")


def apply_reduced_rules(parts: Parts) -> None:
    s = parts.sections
    for name in REDUCED_DROPPED:
        s.pop(name, None)
    s["search_scope"] = NEUTRAL_TASK
    # Keep the grounding bullet, as it stands after any no_evidence edit.
    bullets = [b for b in s["evidence"].split("\n- ") if b.startswith("key_impacts")]
    if len(bullets) != 1:
        raise AblationError("expected exactly one key_impacts bullet under Evidence discipline")
    s["evidence"] = "Evidence discipline:\n- " + bullets[0].rstrip("\n") + "\n\n"
    # Points at the country-level rule, which is gone.
    s["admin"] = _replace_once(
        s["admin"], "- Use country only when the country-level rule above allows it.\n", "")
    s["return"] = NEUTRAL_RETURN
    parts.user_instruction = NEUTRAL_USER_INSTRUCTION
    parts.neutral = True
    parts.log.append("reduced_rules: applied")


TRANSFORMS = {
    "no_evidence": apply_no_evidence,
    "no_vocab": apply_no_vocab,
    "reduced_rules": apply_reduced_rules,
}
RECIPES = {
    "full": (),
    "no_evidence": ("no_evidence",),
    "no_vocab": ("no_vocab",),
    "reduced_rules": ("reduced_rules",),
    "bare": ("no_evidence", "no_vocab", "reduced_rules"),
}


@dataclass(frozen=True)
class AblationConfig:
    name: str
    transforms: tuple[str, ...]
    prompt: PromptSpec
    schema: type
    log: tuple[str, ...]

    def response_format(self) -> dict:
        """Exactly what the SDK sends as `response_format`."""
        return type_to_response_format_param(self.schema)


def build_config(name: str, order: tuple[str, ...] | None = None) -> AblationConfig:
    """`order` overrides the recipe's transform order (the commutation test)."""
    if name not in RECIPES:
        raise AblationError(f"unknown configuration {name!r}; known: {', '.join(CONFIGS)}")
    transforms = order if order is not None else RECIPES[name]
    if name == "full":
        return AblationConfig(name, (), get_prompt(5),
                              build_schema(drop_evidence=False, neutral=False), ())

    parts = Parts(parse_sections(), UNIFIED_VERIFICATION_RECALL_USER_INSTRUCTION)
    for t in transforms:
        TRANSFORMS[t](parts)
    prompt = PromptSpec(id=5, name=f"unified_verification_recall__{name}",
                        system_prompt=parts.system_prompt(),
                        user_instruction=parts.user_instruction)
    return AblationConfig(name, tuple(transforms), prompt,
                          build_schema(drop_evidence=parts.drop_evidence, neutral=parts.neutral),
                          tuple(parts.log))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _schema_text(cfg: AblationConfig) -> str:
    return json.dumps(cfg.response_format(), indent=2, ensure_ascii=False) + "\n"


def manifest(cfg: AblationConfig) -> dict:
    schema_text = _schema_text(cfg)
    return {
        "config": cfg.name,
        "transforms": list(cfg.transforms),
        "log": list(cfg.log),
        "prompt_name": cfg.prompt.name,
        # The 16-character form is what `run_stats.json` records for production.
        "system_sha16": _sha(cfg.prompt.system_prompt)[:16],
        "system_sha256": _sha(cfg.prompt.system_prompt),
        "user_instruction_sha256": _sha(cfg.prompt.user_instruction),
        "schema_sha256": _sha(schema_text),
        "system_chars": len(cfg.prompt.system_prompt),
    }


def rendered_files(cfg: AblationConfig) -> dict[str, str]:
    return {
        "system.txt": cfg.prompt.system_prompt + "\n",
        "user_instruction.txt": cfg.prompt.user_instruction + "\n",
        "schema.json": _schema_text(cfg),
        "manifest.json": json.dumps(manifest(cfg), indent=2) + "\n",
    }


def write_prompts(out_dir: Path = PROMPTS_DIR, *, force: bool = False) -> dict:
    if (out_dir / "MANIFEST.json").exists() and not force:
        raise AblationError(f"{out_dir} already rendered; pass --force to overwrite")
    overall = {}
    for name in CONFIGS:
        cfg = build_config(name)
        target = out_dir / name
        target.mkdir(parents=True, exist_ok=True)
        for fname, text in rendered_files(cfg).items():
            (target / fname).write_text(text, encoding="utf-8")
        overall[name] = manifest(cfg)
    (out_dir / "MANIFEST.json").write_text(json.dumps(overall, indent=2) + "\n", encoding="utf-8")
    return overall


def check_prompts(out_dir: Path = PROMPTS_DIR) -> list[str]:
    """Every rendered file that no longer matches the code. Empty means in sync."""
    stale = []
    for name in CONFIGS:
        for fname, text in rendered_files(build_config(name)).items():
            path = out_dir / name / fname
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path.relative_to(REPO_ROOT)))
    return stale


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true", help="render to ablation/prompts/")
    g.add_argument("--check", action="store_true", help="verify the rendered files")
    p.add_argument("--force", action="store_true", help="overwrite rendered prompts")
    args = p.parse_args(argv)

    if args.write:
        for name, m in write_prompts(force=args.force).items():
            print(f"{name:14s} system {m['system_chars']:5d} chars  sha16 {m['system_sha16']}"
                  f"  schema {m['schema_sha256'][:12]}")
        return 0
    stale = check_prompts()
    for path in stale:
        print(f"stale: {path}")
    print("in sync" if not stale else f"{len(stale)} stale file(s)")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
