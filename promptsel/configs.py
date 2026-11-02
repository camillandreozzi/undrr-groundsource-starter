"""The five Experiment D configurations: prompts 1-4 as they stand, and prompt 5.

    python -m promptsel.configs --write      # render -> promptsel/prompts/ (refuses to clobber)
    python -m promptsel.configs --check      # rendered files still match the code?

Nothing is retyped or edited. p1-p4 are `get_prompt(1..4)` from
`src/fonte/prompts.py` — the multi-event texts of commit d0dcd71 — with the
production response schema, so they share prompt 5's schema and post-filter
and only the prompt text varies. p5 is Experiment B's `full`: the same
PromptSpec object and the same schema class.

These are not the texts behind the June yield comparison. Those runs used the
single-event versions of 9ed213e ("Extract ONE best candidate per document");
`PROMPTSEL_PROTOCOL.md` §1 records the difference.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from ablation import configs as ablation_configs  # noqa: E402
from ablation.configs import AblationConfig, manifest, rendered_files  # noqa: E402
from ablation.schemas import build_schema  # noqa: E402
from fonte.prompts import get_prompt  # noqa: E402

PROMPTS_DIR = REPO_ROOT / "promptsel" / "prompts"
CONFIGS = ("p1", "p2", "p3", "p4", "p5")
BASELINE = "p5"
PROMPT_IDS = {"p1": 1, "p2": 2, "p3": 3, "p4": 4, "p5": 5}
# The labels the June comparison used for the same prompt ids.
JUNE_LABELS = {"p1": "prompt01", "p2": "prompt02", "p3": "prompt03", "p4": "prompt04",
               "p5": "prompt05"}


class PromptSelError(RuntimeError):
    pass


def build_config(name: str) -> AblationConfig:
    if name not in PROMPT_IDS:
        raise PromptSelError(f"unknown configuration {name!r}; known: {', '.join(CONFIGS)}")
    if name == "p5":
        return dataclasses.replace(ablation_configs.build_config("full"), name="p5")
    return AblationConfig(name, (), get_prompt(PROMPT_IDS[name]),
                          build_schema(drop_evidence=False, neutral=False), ())


def write_prompts(out_dir: Path = PROMPTS_DIR, *, force: bool = False) -> dict:
    if (out_dir / "MANIFEST.json").exists() and not force:
        raise PromptSelError(f"{out_dir} already rendered; pass --force to overwrite")
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
    g.add_argument("--write", action="store_true", help="render to promptsel/prompts/")
    g.add_argument("--check", action="store_true", help="verify the rendered files")
    p.add_argument("--force", action="store_true", help="overwrite rendered prompts")
    args = p.parse_args(argv)

    if args.write:
        for name, m in write_prompts(force=args.force).items():
            print(f"{name:3s} {m['prompt_name']:28s} system {m['system_chars']:5d} chars"
                  f"  sha16 {m['system_sha16']}  schema {m['schema_sha256'][:12]}")
        return 0
    stale = check_prompts()
    for path in stale:
        print(f"stale: {path}")
    print("in sync" if not stale else f"{len(stale)} stale file(s)")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
