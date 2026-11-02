"""Run prompts 1-5 over Experiment B's frozen windows on OpenRouter GPT-5.

    python -m promptsel.runner --dry-run              # hashes, catalogue, cost estimate; no spend
    python -m promptsel.runner --smoke 3              # 3 non-evaluation docs x 5 configs
    python -m promptsel.runner --workers 4            # 5 configs x 2 replicates x 80 windows

Experiment B's runner with its configurations swapped for `promptsel.configs`
and its own job seed. The request (`ablation.runner.extract_one`), the window
loading and text checks, the progress/resume files and `finalise` are
Experiment B's, imported unchanged, so p5 here sends exactly the request
Experiment B's `full` sent. Only `run` is copied, because Experiment B's builds
its configurations by name and seeds its queue with 46.

OUTPUT
------
`promptsel/runs/<config>/r<k>/openai-gpt-5/`, laid out as Experiment B's runs.

The full run refuses to start until the protocol, the frozen hashes and the
scorer are committed (`preflight`), and until Experiment B's own preflight
still passes — so nothing is spent on an unregistered design, and Experiment B
is provably untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from dotenv import load_dotenv  # noqa: E402

from ablation import runner as ablation_runner  # noqa: E402
from ablation.normalise_hazards import LEXICON_SHA256  # noqa: E402
from ablation.runner import (  # noqa: E402
    COST_PER_CALL, COST_PER_EVENT, EXPA_GOLD, REPLICATES, SEPTEMBER_RUN, SPEC, WINDOWS, Job,
    _append, extract_one, finalise, load_window_documents, plan_jobs, run_dir, smoke_documents,
)
from benchmark_openrouter.models import ModelSpec  # noqa: E402
from benchmark_openrouter.run_openrouter import build_client, fetch_catalogue  # noqa: E402
from fonte.app_event_focus import (  # noqa: E402
    DocumentRow, error_output_rows, extraction_to_output_rows, format_duration,
)
from promptsel.configs import CONFIGS, build_config, check_prompts, manifest  # noqa: E402

LOG = logging.getLogger("promptsel.runner")

PROMPTSEL = REPO_ROOT / "promptsel"
FROZEN = PROMPTSEL / "FROZEN.json"
PROTOCOL = PROMPTSEL / "PROMPTSEL_PROTOCOL.md"
RUNS = PROMPTSEL / "runs"
ABLATION_FROZEN = REPO_ROOT / "ablation" / "FROZEN.json"

JOB_SEED = 47                      # 42-45 are Experiment A's, 46 Experiment B's

# The geocoding rule of the June comparison (`compare_resolution_filtered_runs.py`
# defaults), applied by `promptsel.geocode` and the scorer.
GEOCODE = {
    "band": [0.70, 0.98], "band_inclusive": "both", "cache_version": 2,
    "allow_non_polygon": False, "min_interval_s": 1.1,
    "endpoint": "https://nominatim.openstreetmap.org/search",
}

# Code this experiment imports but does not own: pinned by hash.
SOURCES = (
    "ablation/configs.py", "ablation/runner.py", "ablation/schemas.py",
    "ablation/normalise_hazards.py", "ablation/score_ablation.py",
    "eval/event_matching.py", "eval/score_event_level.py", "eval/score_against_human.py",
    "benchmark_openrouter/run_openrouter.py", "benchmark_openrouter/citation_quality.py",
    "src/fonte/prompts.py", "src/fonte/app_event_focus.py", "src/fonte/polygon_resolver.py",
    "src/fonte/run_polygon_resolution.py", "src/fonte/geometry_postprocess.py",
    "scripts/compare_resolution_filtered_runs.py",
)

# What the full run must find committed and unchanged before it spends.
REGISTERED = ("promptsel/PROMPTSEL_PROTOCOL.md", "promptsel/FROZEN.json", "promptsel/prompts",
              "promptsel/configs.py", "promptsel/runner.py", "promptsel/geocode.py",
              "promptsel/score_promptsel.py", "tests/test_promptsel.py",
              "ablation/windows.csv", "ablation/FROZEN.json", *SOURCES)


class PromptSelRunError(RuntimeError):
    pass


def _file_sha(rel: str) -> str:
    return hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def run(configs: list[str], reps: int, docs: list[DocumentRow], *, out_root: Path,
        workers: int, spec: ModelSpec = SPEC, client_factory=build_client,
        seed: int = JOB_SEED) -> dict:
    """`ablation.runner.run` with this experiment's configurations and seed."""
    cfgs = {name: build_config(name) for name in configs}
    jobs = plan_jobs(configs, reps, docs, out_root, seed=seed)
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


# ---------------------------------------------------------------------------
# Preflight and dry run
# ---------------------------------------------------------------------------

def frozen_hashes() -> dict:
    """What FROZEN.json must hold for the current code and files."""
    prompts = {name: manifest(build_config(name)) for name in CONFIGS}
    ablation_full = json.loads(ABLATION_FROZEN.read_text(encoding="utf-8"))["prompts"]["full"]
    p5_is_full = {k: v for k, v in prompts["p5"].items() if k != "config"} == {
        k: v for k, v in ablation_full.items() if k != "config"}
    return {
        "prompts": prompts,
        "p5_equals_ablation_full": p5_is_full,
        "ablation_frozen_sha256": hashlib.sha256(ABLATION_FROZEN.read_bytes()).hexdigest(),
        "windows_sha256": hashlib.sha256(WINDOWS.read_bytes()).hexdigest(),
        "expA_gold_sha256": hashlib.sha256(EXPA_GOLD.read_bytes()).hexdigest(),
        "lexicon_sha256": LEXICON_SHA256,
        "model": SPEC.id, "reasoning_effort": SPEC.reasoning_effort,
        "structured_output": SPEC.structured_output,
        "replicates": REPLICATES, "job_seed": JOB_SEED,
        "geocode": GEOCODE,
        "sources": {rel: _file_sha(rel) for rel in SOURCES},
        "packages": {name: metadata.version(name)
                     for name in ("openai", "pydantic", "numpy", "pycountry", "shapely")},
    }


def freeze(force: bool = False) -> dict:
    if FROZEN.exists() and not force:
        raise SystemExit(f"{FROZEN.relative_to(REPO_ROOT)} exists; pass --force to re-freeze "
                         "(and log it as a deviation)")
    if check_prompts():
        raise SystemExit("Rendered prompts are stale; run make promptsel-prompts FORCE=1 first")
    frozen = frozen_hashes()
    if not frozen["p5_equals_ablation_full"]:
        raise SystemExit("p5 no longer equals Experiment B's frozen `full`")
    FROZEN.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    return frozen


def preflight_problems() -> list[str]:
    problems = [f"rendered prompt out of sync: {p}" for p in check_prompts()]
    if not FROZEN.exists():
        problems.append("promptsel/FROZEN.json is missing")
    else:
        frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
        current = frozen_hashes()
        problems += [f"FROZEN.json disagrees on {k}" for k, v in current.items()
                     if frozen.get(k) != v]
        if not current["p5_equals_ablation_full"]:
            problems.append("p5 is not Experiment B's frozen `full`")
    if not PROTOCOL.exists():
        problems.append("promptsel/PROMPTSEL_PROTOCOL.md is missing")
    for rel in REGISTERED:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=REPO_ROOT,
                                 capture_output=True, text=True)
        if tracked.returncode != 0:
            problems.append(f"not committed: {rel}")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *REGISTERED], cwd=REPO_ROOT,
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        problems.append("uncommitted changes:\n" + dirty)
    problems += [f"Experiment B: {p}" for p in ablation_runner.preflight_problems()]
    return problems


def dry_run(docs: list[DocumentRow], reps: int) -> None:
    print(f"model {SPEC.id} | effort {SPEC.reasoning_effort} | structured {SPEC.structured_output}"
          f" | job seed {JOB_SEED}")
    for name in CONFIGS:
        m = manifest(build_config(name))
        print(f"  {name:3s} {m['prompt_name']:28s} system {m['system_chars']:5d} chars"
              f"  sha16 {m['system_sha16']}  schema {m['schema_sha256'][:12]}")
    calls = len(CONFIGS) * reps * len(docs)
    # Events GPT-5 emitted on these windows in September, as the per-event term.
    keys = {d.asset_key for d in docs}
    with SEPTEMBER_RUN.open(encoding="utf-8") as f:
        events = sum(1 for line in f if line.strip()
                     and (r := json.loads(line))["asset_key"] in keys and r.get("event_index"))
    est = len(CONFIGS) * reps * (COST_PER_CALL * len(docs) + COST_PER_EVENT * events)
    print(f"{len(docs)} windows x {len(CONFIGS)} configs x {reps} replicates = {calls} calls;"
          f" estimate ${est:.0f} at production event rates (more if a prompt emits more)")
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
    p.add_argument("--freeze", action="store_true", help="write promptsel/FROZEN.json")
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
        out_root = args.out_root or PROMPTSEL / "runs_smoke"
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
            print(f"{name:3s} r{rep}  {s['documents_finished']}/{s['documents_total']} done"
                  f"  {s['documents_errored']} errored  {s['events']} events  ${s['cost_usd']:.2f}"
                  f"  providers {s['providers']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
