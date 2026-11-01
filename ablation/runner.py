"""Run the five ablation configurations over the frozen windows on OpenRouter GPT-5.

    python -m ablation.runner --dry-run              # hashes, catalogue, cost estimate; no spend
    python -m ablation.runner --smoke 3              # 3 non-evaluation docs x 5 configs
    python -m ablation.runner --workers 4            # 5 configs x 2 replicates x 80 windows

WHAT IS HELD FIXED
------------------
The model (`openai/gpt-5`, reasoning effort medium), the request shape, the
document metadata payload, the 12,000-character window and the post-filter.
The request is `run_openrouter.extract_document`'s json_schema call with two
things swapped in from `ablation.configs`: the system/user messages and the
response schema. Structured output is pinned to json_schema: the json_object
fallback pastes the schema into the system prompt, which would change the very
channel being ablated, so a json_schema failure is an error row here.

GPT-5 takes no temperature or seed, so every configuration runs twice and the
scorer reports replicate-to-replicate differences as the noise floor. All
(configuration, replicate, window) jobs share one seeded queue, so drift over
the run — provider routing, load — falls on every configuration alike.

OUTPUT
------
`ablation/runs/<config>/r<k>/openai-gpt-5/`:
  event_extractions.{jsonl,csv}   OUTPUT_HEADERS rows, window order
  raw/<asset_key>.json            the model's JSON before the post-filter
  progress.jsonl                  one line per finished job; the last per window wins
  attempts.jsonl                  every call, including failures: model, provider,
                                  finish reason, tokens, cost — never compacted
  run_stats.json                  totals, plus the configuration's manifest hashes

The full run refuses to start until the protocol and the frozen hashes are
committed (`preflight`), so nothing is spent on an unregistered design.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import logging
import random
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from importlib import metadata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from dotenv import load_dotenv  # noqa: E402

from ablation.configs import CONFIGS, AblationConfig, build_config, check_prompts, manifest  # noqa: E402
from ablation.normalise_hazards import LEXICON_SHA256  # noqa: E402
from benchmark_openrouter.documents import load_documents  # noqa: E402
from benchmark_openrouter.models import BY_ID, ModelSpec  # noqa: E402
from benchmark_openrouter.run_openrouter import (  # noqa: E402
    MAX_CHARS, _extra_body, _usage_dict, build_client, fetch_catalogue,
)
from fonte.app_event_focus import (  # noqa: E402
    DocumentRow, build_prompt_payload, error_output_rows, extraction_to_output_rows,
    format_duration, is_error_row, save_csv, save_jsonl,
)
from fonte.prompts import build_user_prompt  # noqa: E402

LOG = logging.getLogger("ablation.runner")

ABLATION = REPO_ROOT / "ablation"
WINDOWS = ABLATION / "windows.csv"
FROZEN = ABLATION / "FROZEN.json"
PROTOCOL = ABLATION / "ABLATION_PROTOCOL.md"
RUNS = ABLATION / "runs"
SNAPSHOTS = (REPO_ROOT / "benchmark_openrouter" / "documents.json",
             REPO_ROOT / "benchmark_openrouter" / "documents_docsample.json")
SEPTEMBER_RUN = (REPO_ROOT / "benchmark_openrouter" / "outputs_pooled" / "openai-gpt-5"
                 / "event_extractions.jsonl")
EXPA_GOLD = REPO_ROOT / "eval" / "event_level_gold.csv"

SPEC: ModelSpec = dataclasses.replace(BY_ID["openai/gpt-5"], structured_output="json_schema")
REPLICATES = 2
JOB_SEED = 46                      # 42-45 are taken by Experiment A
# Fitted on the two September GPT-5 arms: cost ~ a + b * events (USD).
COST_PER_CALL, COST_PER_EVENT = 0.0148, 0.0106

# What the full run must find committed and unchanged before it spends.
REGISTERED = ("ablation/ABLATION_PROTOCOL.md", "ablation/FROZEN.json", "ablation/windows.csv",
              "ablation/prompts", "ablation/configs.py", "ablation/schemas.py",
              "ablation/normalise_hazards.py", "ablation/runner.py")


class AblationRunError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot_documents() -> dict[str, DocumentRow]:
    docs: dict[str, DocumentRow] = {}
    for path in SNAPSHOTS:
        rows, _meta = load_documents(path)
        docs.update({d.asset_key: d for d in rows})
    return docs


def read_windows(path: Path = WINDOWS) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return sorted(csv.DictReader(f), key=lambda r: int(r["ablation_rank"]))


def load_window_documents(path: Path = WINDOWS) -> list[DocumentRow]:
    """The frozen windows as the runner will send them, text hashes re-checked."""
    docs = snapshot_documents()
    out = []
    for w in read_windows(path):
        doc = docs.get(w["asset_key"])
        if doc is None:
            raise AblationRunError(f"{w['asset_key'][:12]} is not in either snapshot")
        if _sha(doc.text) != w["text_sha256"]:
            raise AblationRunError(f"{w['asset_key'][:12]}: snapshot text changed since freezing")
        out.append(doc)
    return out


def smoke_documents(n: int, path: Path = WINDOWS) -> list[DocumentRow]:
    """The first n snapshot documents (by key) that are NOT evaluation windows."""
    held = {w["asset_key"] for w in read_windows(path)}
    docs = snapshot_documents()
    return [docs[k] for k in sorted(docs) if k not in held][:n]


# ---------------------------------------------------------------------------
# One call
# ---------------------------------------------------------------------------

def extract_one(client, doc: DocumentRow, spec: ModelSpec, cfg: AblationConfig):
    """(extraction, raw JSON text, call metadata). Raises on any failure."""
    payload = build_prompt_payload(doc, max_chars=MAX_CHARS)
    completion = client.chat.completions.parse(
        model=spec.id,
        messages=[
            {"role": "system", "content": cfg.prompt.system_prompt},
            {"role": "user", "content": build_user_prompt(cfg.prompt, payload)},
        ],
        response_format=cfg.schema,
        extra_body=_extra_body(spec, require_structured=True),
    )
    choice = completion.choices[0]
    extraction = choice.message.parsed
    if extraction is None:
        raise ValueError("model returned no parsed content (refusal or truncation)")
    usage = getattr(completion, "usage", None)
    details = getattr(usage, "completion_tokens_details", None)
    meta = {
        **_usage_dict(completion),
        "reasoning_tokens": getattr(details, "reasoning_tokens", None),
        "served_model": getattr(completion, "model", None),
        "provider": getattr(completion, "provider", None),
        "finish_reason": getattr(choice, "finish_reason", None),
        "generation_id": getattr(completion, "id", None),
    }
    return extraction, choice.message.content, meta


# ---------------------------------------------------------------------------
# Jobs and run directories
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Job:
    config: str
    rep: int
    doc: DocumentRow


def run_dir(out_root: Path, config: str, rep: int, spec: ModelSpec = SPEC) -> Path:
    return out_root / config / f"r{rep}" / spec.slug


def load_progress(directory: Path) -> dict[str, dict]:
    """asset_key -> the last finished job for it (a retry supersedes its error)."""
    path = directory / "progress.jsonl"
    state: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                state[rec["asset_key"]] = rec
    return state


def plan_jobs(configs: list[str], reps: int, docs: list[DocumentRow], out_root: Path,
              seed: int = JOB_SEED) -> list[Job]:
    jobs = []
    for config in configs:
        for rep in range(1, reps + 1):
            done = load_progress(run_dir(out_root, config, rep))
            jobs += [Job(config, rep, d) for d in docs
                     if not (d.asset_key in done and not done[d.asset_key]["error"])]
    jobs.sort(key=lambda j: (j.config, j.rep, j.doc.asset_key))
    random.Random(seed).shuffle(jobs)
    return jobs


def _append(path: Path, record: dict, lock: threading.Lock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock, path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def run(configs: list[str], reps: int, docs: list[DocumentRow], *, out_root: Path,
        workers: int, spec: ModelSpec = SPEC, client_factory=build_client) -> dict:
    cfgs = {name: build_config(name) for name in configs}
    jobs = plan_jobs(configs, reps, docs, out_root)
    LOG.info("%d job(s) pending over %d config(s) x %d replicate(s) x %d window(s), workers=%d",
             len(jobs), len(configs), reps, len(docs), workers)

    locks: dict[Path, threading.Lock] = defaultdict(threading.Lock)
    thread_local = threading.local()
    started = time.perf_counter()

    def client():
        c = getattr(thread_local, "client", None)
        if c is None:
            c = thread_local.client = client_factory()
        return c

    def process(job: Job) -> tuple[Job, bool]:
        directory = run_dir(out_root, job.config, job.rep, spec)
        t0 = time.perf_counter()
        attempt = {"asset_key": job.doc.asset_key, "config": job.config, "rep": job.rep,
                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            extraction, raw, meta = extract_one(client(), job.doc, spec, cfgs[job.config])
            rows = extraction_to_output_rows(job.doc, extraction)
            if raw:
                (directory / "raw").mkdir(parents=True, exist_ok=True)
                (directory / "raw" / f"{job.doc.asset_key}.json").write_text(raw, encoding="utf-8")
            attempt.update(meta, error=None)
            failed = False
        except Exception as exc:  # noqa: BLE001
            LOG.warning("%s r%d failed on %s: %s", job.config, job.rep, job.doc.asset_key[:12], exc)
            rows = error_output_rows(job.doc, exc)
            attempt.update(error=f"{type(exc).__name__}: {exc}")
            failed = True
        attempt["seconds"] = round(time.perf_counter() - t0, 1)
        lock = locks[directory]
        _append(directory / "attempts.jsonl", attempt, lock)
        _append(directory / "progress.jsonl",
                {"asset_key": job.doc.asset_key, "error": failed, "rows": rows}, lock)
        return job, failed

    done = failures = 0
    interrupted = False
    executor = ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        futures = [executor.submit(process, j) for j in jobs]
        for future in as_completed(futures):
            job, failed = future.result()
            done += 1
            failures += int(failed)
            if done % 10 == 0 or done == len(jobs):
                LOG.info("%d/%d jobs | %d failed | %s", done, len(jobs), failures,
                         format_duration(time.perf_counter() - started))
    except KeyboardInterrupt:
        interrupted = True
        LOG.warning("Stop requested — waiting for in-flight requests...")
        executor.shutdown(wait=True, cancel_futures=True)
    else:
        executor.shutdown(wait=True)

    stats = {name: {rep: finalise(run_dir(out_root, name, rep, spec), docs, cfgs[name], rep, spec)
                    for rep in range(1, reps + 1)} for name in configs}
    if interrupted:
        raise KeyboardInterrupt
    return stats


def finalise(directory: Path, docs: list[DocumentRow], cfg: AblationConfig, rep: int,
             spec: ModelSpec = SPEC) -> dict:
    """Compact one run directory into OUTPUT_HEADERS files and run_stats.json."""
    state = load_progress(directory)
    rows = [row for d in docs for row in state.get(d.asset_key, {}).get("rows", [])]
    directory.mkdir(parents=True, exist_ok=True)
    save_jsonl(rows, directory / "event_extractions.jsonl")
    save_csv(rows, directory / "event_extractions.csv")

    attempts = []
    if (directory / "attempts.jsonl").exists():
        attempts = [json.loads(l) for l in
                    (directory / "attempts.jsonl").read_text(encoding="utf-8").splitlines() if l]
    m = manifest(cfg)
    stats = {
        "config": cfg.name, "replicate": rep, "model": spec.id, "label": spec.label,
        "reasoning_effort": spec.reasoning_effort, "structured_output": spec.structured_output,
        "prompt_name": cfg.prompt.name, "system_sha16": m["system_sha16"],
        "system_sha256": m["system_sha256"],
        "user_instruction_sha256": m["user_instruction_sha256"],
        "schema_sha256": m["schema_sha256"], "max_chars": MAX_CHARS,
        "documents_total": len(docs),
        "documents_finished": sum(1 for d in docs if d.asset_key in state),
        "documents_errored": sum(1 for d in docs if state.get(d.asset_key, {}).get("error")),
        "error_rows": sum(1 for r in rows if is_error_row(r)),
        "events": sum(1 for r in rows if r.get("event_index")),
        "attempts": len(attempts),
        "failed_attempts": sum(1 for a in attempts if a.get("error")),
        "prompt_tokens": sum(a.get("prompt_tokens") or 0 for a in attempts),
        "completion_tokens": sum(a.get("completion_tokens") or 0 for a in attempts),
        "reasoning_tokens": sum(a.get("reasoning_tokens") or 0 for a in attempts),
        "cost_usd": round(sum(a.get("cost") or 0.0 for a in attempts), 4),
        "served_models": dict(Counter(a.get("served_model") for a in attempts if not a.get("error"))),
        "providers": dict(Counter(a.get("provider") for a in attempts if not a.get("error"))),
        "finish_reasons": dict(Counter(a.get("finish_reason") for a in attempts
                                       if not a.get("error"))),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (directory / "run_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    return stats


# ---------------------------------------------------------------------------
# Preflight and dry run
# ---------------------------------------------------------------------------

def frozen_hashes() -> dict:
    """What FROZEN.json must hold for the current code and files."""
    return {
        "prompts": {name: manifest(build_config(name)) for name in CONFIGS},
        "windows_sha256": hashlib.sha256(WINDOWS.read_bytes()).hexdigest(),
        "expA_gold_sha256": hashlib.sha256(EXPA_GOLD.read_bytes()).hexdigest(),
        "lexicon_sha256": LEXICON_SHA256,
        "model": SPEC.id, "reasoning_effort": SPEC.reasoning_effort,
        "structured_output": SPEC.structured_output,
        "replicates": REPLICATES, "job_seed": JOB_SEED,
        "packages": {name: metadata.version(name) for name in ("openai", "pydantic")},
    }


def freeze(force: bool = False) -> dict:
    if FROZEN.exists() and not force:
        raise SystemExit(f"{FROZEN.relative_to(REPO_ROOT)} exists; pass --force to re-freeze "
                         "(and log it as a deviation)")
    if check_prompts():
        raise SystemExit("Rendered prompts are stale; run make ablation-prompts FORCE=1 first")
    frozen = frozen_hashes()
    FROZEN.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    return frozen


def preflight_problems() -> list[str]:
    problems = [f"rendered prompt out of sync: {p}" for p in check_prompts()]
    if not FROZEN.exists():
        problems.append("ablation/FROZEN.json is missing")
    else:
        frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
        current = frozen_hashes()
        problems += [f"FROZEN.json disagrees on {k}" for k, v in current.items()
                     if frozen.get(k) != v]
    if not PROTOCOL.exists():
        problems.append("ablation/ABLATION_PROTOCOL.md is missing")
    for rel in REGISTERED:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=REPO_ROOT,
                                 capture_output=True, text=True)
        if tracked.returncode != 0:
            problems.append(f"not committed: {rel}")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *REGISTERED], cwd=REPO_ROOT,
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        problems.append("uncommitted changes:\n" + dirty)
    return problems


def dry_run(docs: list[DocumentRow], reps: int) -> None:
    print(f"model {SPEC.id} | effort {SPEC.reasoning_effort} | structured {SPEC.structured_output}")
    for name in CONFIGS:
        m = manifest(build_config(name))
        print(f"  {name:14s} system {m['system_chars']:5d} chars  sha16 {m['system_sha16']}"
              f"  schema {m['schema_sha256'][:12]}")
    calls = len(CONFIGS) * reps * len(docs)
    # Events GPT-5 emitted on these windows in September, as the per-event term.
    keys = {d.asset_key for d in docs}
    with SEPTEMBER_RUN.open(encoding="utf-8") as f:
        events = sum(1 for line in f if line.strip()
                     and (r := json.loads(line))["asset_key"] in keys and r.get("event_index"))
    est = len(CONFIGS) * reps * (COST_PER_CALL * len(docs) + COST_PER_EVENT * events)
    print(f"{len(docs)} windows x {len(CONFIGS)} configs x {reps} replicates = {calls} calls;"
          f" estimate ${est:.0f} at production event rates (more if ablations emit more)")
    try:
        entry = fetch_catalogue().get(SPEC.id)
    except Exception as exc:  # noqa: BLE001
        print(f"catalogue check failed: {exc}")
    else:
        if entry is None:
            print(f"WARNING: {SPEC.id} is not in the OpenRouter catalogue")
        else:
            params = set(entry.get("supported_parameters") or [])
            for need in ("structured_outputs", "reasoning"):
                print(f"  catalogue {need:18s} {'yes' if need in params else 'NO'}")
    problems = preflight_problems()
    print("preflight: ok" if not problems else "preflight (full run would refuse):")
    for p in problems:
        print(f"  - {p}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true", help="no spend")
    p.add_argument("--freeze", action="store_true", help="write ablation/FROZEN.json")
    p.add_argument("--force", action="store_true", help="with --freeze: overwrite")
    p.add_argument("--smoke", type=int, metavar="N",
                   help="N non-evaluation documents, 1 replicate, no preflight")
    p.add_argument("--configs", nargs="+", choices=CONFIGS, default=list(CONFIGS))
    p.add_argument("--reps", type=int, default=REPLICATES)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out-root", type=Path, default=None)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv(REPO_ROOT / ".env")

    if args.freeze:
        frozen = freeze(force=args.force)
        print(f"-> {FROZEN.relative_to(REPO_ROOT)} (windows {frozen['windows_sha256'][:12]}, "
              f"lexicon {frozen['lexicon_sha256'][:12]}, packages {frozen['packages']})")
        return 0
    if args.dry_run:
        dry_run(load_window_documents(), args.reps)
        return 0
    if args.smoke:
        docs = smoke_documents(args.smoke)
        out_root = args.out_root or ABLATION / "runs_smoke"
        stats = run(args.configs, 1, docs, out_root=out_root, workers=args.workers)
    else:
        problems = preflight_problems()
        if problems:
            raise SystemExit("Refusing to spend before the design is registered:\n  - "
                             + "\n  - ".join(problems))
        docs = load_window_documents()
        stats = run(args.configs, args.reps, docs, out_root=args.out_root or RUNS,
                    workers=args.workers)
    for name, by_rep in stats.items():
        for rep, s in by_rep.items():
            print(f"{name:14s} r{rep}  {s['documents_finished']}/{s['documents_total']} done"
                  f"  {s['documents_errored']} errored  {s['events']} events  ${s['cost_usd']:.2f}"
                  f"  providers {s['providers']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
