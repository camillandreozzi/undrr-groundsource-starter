"""Run prompt 5 across a roster of OpenRouter models over the same 167 documents.

    python -m benchmark_openrouter.run_openrouter --check-models     # no spend
    python -m benchmark_openrouter.run_openrouter --all --dry-run    # no spend
    python -m benchmark_openrouter.run_openrouter --model deepseek/deepseek-chat-v3.1 --limit 3
    python -m benchmark_openrouter.run_openrouter --all --workers 4 --resume

WHAT IS HELD FIXED
------------------
Prompt 5's system and user messages, the document metadata payload, the 12,000
character input window, and the Pydantic post-filter are all imported from
`fonte` — not copied. Whatever production runs, this runs. The only
variable is the model.

That matters most for the post-filter: `DocumentEventExtractions` drops every
non-verifiable, low-confidence, under-specified or duplicate event before it is
written. Both structured-output paths below land in that same model, so a
chatty model does not get to inflate its event count.

WHAT DIFFERS FROM THE AZURE ARM
-------------------------------
No logprobs. Support is inconsistent across OpenRouter providers and requesting
them fragments routing, so `event_confidence_logprob` / `_prob` are written as
null here while the Azure production run has them populated. Nothing downstream
depends on those columns.

OUTPUT
------
`outputs/<model_slug>/event_extractions.{jsonl,csv}` in the exact
`OUTPUT_HEADERS` schema, so `eval/score_against_human.py`,
`fonte-polygons` and the review apps all accept a run from here
unchanged. Plus `run_stats.json` with cost, tokens, timing and — importantly —
which structured-output mode the model ended up using.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from openai import OpenAI  # noqa: E402
from openai.lib._parsing._completions import type_to_response_format_param  # noqa: E402

from benchmark_openrouter.documents import SnapshotError, load_documents  # noqa: E402
from benchmark_openrouter.models import ROSTER, ModelSpec, select  # noqa: E402
from fonte.app_event_focus import (  # noqa: E402
    DocumentEventExtractions,
    DocumentRow,
    _env_float,
    _env_int,
    append_progress_rows,
    build_prompt_payload,
    error_output_rows,
    extraction_to_output_rows,
    format_duration,
    is_error_row,
    load_completed_rows,
    require_env,
    save_csv,
    save_jsonl,
)
from fonte.prompts import PromptSpec, build_user_prompt, get_prompt  # noqa: E402

LOG = logging.getLogger("benchmark_openrouter.run")

BASE_URL = "https://openrouter.ai/api/v1"
OUT_ROOT = REPO_ROOT / "benchmark_openrouter" / "outputs"
PROMPT_ID = 5
MAX_CHARS = 12_000


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def build_client() -> OpenAI:
    """OpenRouter is OpenAI-compatible, so the stock SDK does the work.

    Retries and timeout reuse the same env knobs as the Azure pipeline, and the
    default is likewise generous: a 167-document run behind concurrency will
    meet 429s from at least one provider.
    """
    headers = {}
    if site := os.getenv("OPENROUTER_SITE_URL"):
        headers["HTTP-Referer"] = site
    if app := os.getenv("OPENROUTER_APP_NAME"):
        headers["X-Title"] = app
    return OpenAI(
        base_url=BASE_URL,
        api_key=require_env("OPENROUTER_API_KEY"),
        max_retries=_env_int("OPENAI_MAX_RETRIES", 8),
        timeout=_env_float("OPENAI_TIMEOUT", 300.0),
        default_headers=headers or None,
    )


def fetch_catalogue() -> dict[str, dict]:
    """OpenRouter's live model list. Public — no key needed."""
    response = httpx.get(f"{BASE_URL}/models", timeout=30.0)
    response.raise_for_status()
    return {m["id"]: m for m in response.json().get("data", [])}


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


def _strip_descriptions(node):
    """Drop `description` keys from a JSON Schema, keeping the structure."""
    if isinstance(node, dict):
        return {k: _strip_descriptions(v) for k, v in node.items() if k != "description"}
    if isinstance(node, list):
        return [_strip_descriptions(v) for v in node]
    return node


def fallback_schema_text() -> str:
    """The compact schema handed to models that cannot enforce one themselves.

    Descriptions are stripped: they triple the size (4.9k chars to 1.5k) and
    every rule they state is already in prompt 5's system prompt, in prose the
    model is more likely to follow. The full version measurably derailed a
    reasoning model, which spent its budget restating field docs and returned a
    fragment of one as its answer.
    """
    schema = type_to_response_format_param(DocumentEventExtractions)
    return json.dumps(_strip_descriptions(schema["json_schema"]["schema"]),
                      ensure_ascii=False)


def strip_to_json(text: str) -> str:
    """Recover the JSON object from a json_object-mode response.

    Models on the fallback path wrap their output in markdown fences or bracket
    it with prose often enough that not handling it costs real documents. Strip
    fences first, then take the outermost balanced object, so trailing
    commentary does not break the parse.
    """
    cleaned = _FENCE.sub("", (text or "").strip())
    start = cleaned.find("{")
    if start == -1:
        return cleaned
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return cleaned[start:i + 1]
    return cleaned[start:]


def _usage_dict(completion) -> dict:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return {}
    raw = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
    return {
        "prompt_tokens": raw.get("prompt_tokens") or 0,
        "completion_tokens": raw.get("completion_tokens") or 0,
        # OpenRouter returns generation cost in USD when usage.include is set.
        "cost": float(raw.get("cost") or 0.0),
    }


def _extra_body(spec: ModelSpec, *, require_structured: bool) -> dict:
    body: dict = {"usage": {"include": True}}
    if require_structured:
        # Route only to providers that actually honour response_format,
        # otherwise a provider that ignores it returns unparseable prose.
        body["provider"] = {"require_parameters": True}
    if spec.reasoning_effort:
        body["reasoning"] = {"effort": spec.reasoning_effort}
    return body


def extract_document(
    client: OpenAI,
    doc: DocumentRow,
    spec: ModelSpec,
    prompt: PromptSpec,
    mode_state: dict,
) -> tuple[DocumentEventExtractions, dict, str, Optional[str]]:
    """Returns (extraction, usage, mode_used, raw_text).

    `mode_state` is shared across threads and caches which structured-output
    mode this model settled on, so we pay the failed-strict-call penalty once
    per run rather than once per document.
    """
    payload = build_prompt_payload(doc, max_chars=MAX_CHARS)
    user_message = build_user_prompt(prompt, payload)

    mode = mode_state.get("mode") or spec.structured_output
    if mode == "auto":
        mode = "json_schema"

    if mode == "json_schema":
        try:
            completion = client.chat.completions.parse(
                model=spec.id,
                messages=[
                    {"role": "system", "content": prompt.system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format=DocumentEventExtractions,
                extra_body=_extra_body(spec, require_structured=True),
            )
            extraction = completion.choices[0].message.parsed
            if extraction is None:
                raise ValueError("model returned no parsed content (refusal or truncation)")
            mode_state.setdefault("mode", "json_schema")
            raw = completion.choices[0].message.content
            return extraction, _usage_dict(completion), "json_schema", raw
        except Exception as exc:  # noqa: BLE001
            if spec.structured_output == "json_schema":
                raise  # pinned: a failure here is a real failure, not a routing hint
            LOG.warning("%s: strict json_schema unavailable (%s) — falling back to "
                        "json_object for the rest of this run.", spec.id, exc)
            mode_state["mode"] = "json_object"
            mode = "json_object"

    # Fallback: no schema enforcement from the provider, so hand the model the
    # schema in the system message and validate it ourselves. Same Pydantic
    # model either way, so the post-filter is identical.
    completion = client.chat.completions.create(
        model=spec.id,
        messages=[
            {"role": "system",
             "content": f"{prompt.system_prompt}\n\nReturn a single JSON object "
                        f"conforming to this JSON Schema, and nothing else:\n"
                        f"{fallback_schema_text()}"},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        extra_body=_extra_body(spec, require_structured=False),
    )
    message = completion.choices[0].message
    raw = message.content
    if not (raw or "").strip():
        raise ValueError(
            "model returned empty content"
            + (" (it wrote only reasoning tokens)" if getattr(message, "reasoning", None)
               else ""))
    parsed = json.loads(strip_to_json(raw))
    if not isinstance(parsed, dict):
        # A bare string or number parses as valid JSON and would otherwise
        # surface as an opaque Pydantic type error.
        raise ValueError(f"model returned {type(parsed).__name__}, not a JSON object: "
                         f"{str(parsed)[:120]!r}")
    extraction = DocumentEventExtractions.model_validate(parsed)
    return extraction, _usage_dict(completion), "json_object", raw


# ---------------------------------------------------------------------------
# Run one model
# ---------------------------------------------------------------------------

def run_model(
    spec: ModelSpec,
    documents: list[DocumentRow],
    prompt: PromptSpec,
    *,
    out_root: Path,
    workers: int,
    resume: bool,
    save_raw: bool,
    snapshot_meta: dict,
) -> dict:
    """Mirrors `app_event_focus.process_documents`: per-thread clients, an
    append-only progress log, and a resume that retries error rows rather than
    treating a failed asset as done."""
    output_dir = out_root / spec.slug
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_path = output_dir / "event_extractions_progress.jsonl"
    progress_lock = threading.Lock()
    thread_local = threading.local()
    mode_state: dict = {}

    completed_by_asset = load_completed_rows(output_dir) if resume else {}
    if not resume:
        progress_path.write_text("", encoding="utf-8")

    def asset_succeeded(asset_key: str) -> bool:
        rows = completed_by_asset.get(asset_key)
        return bool(rows) and not any(is_error_row(row) for row in rows)

    pending = [d for d in documents if not asset_succeeded(d.asset_key)]
    skipped = len(documents) - len(pending)
    retries = sum(1 for d in pending if d.asset_key in completed_by_asset)
    LOG.info("%s — %d document(s) to run (%d already done, %d being retried), workers=%d",
             spec.label, len(pending), skipped, retries, workers)

    def get_client() -> OpenAI:
        client = getattr(thread_local, "client", None)
        if client is None:
            client = build_client()
            thread_local.client = client
        return client

    totals = {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
    totals_lock = threading.Lock()
    started_at = time.perf_counter()

    def process_one(doc: DocumentRow) -> tuple[list[dict], float, bool]:
        t0 = time.perf_counter()
        try:
            extraction, usage, mode, raw = extract_document(
                get_client(), doc, spec, prompt, mode_state)
            rows = extraction_to_output_rows(doc, extraction)
            if save_raw and raw:
                raw_dir = output_dir / "raw"
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / f"{doc.asset_key}.json").write_text(raw, encoding="utf-8")
            with totals_lock:
                for k in ("prompt_tokens", "completion_tokens"):
                    totals[k] += usage.get(k, 0)
                totals["cost"] += usage.get("cost", 0.0)
                mode_state.setdefault("observed", set()).add(mode)
            return rows, time.perf_counter() - t0, False
        except Exception as exc:  # noqa: BLE001
            LOG.warning("%s failed on asset_key=%s: %s", spec.id, doc.asset_key[:16], exc)
            return error_output_rows(doc, exc), time.perf_counter() - t0, True

    done = failures = 0
    interrupted = False

    def record(rows: list[dict], elapsed: float, failed: bool) -> None:
        nonlocal done, failures
        completed_by_asset[rows[0]["asset_key"]] = rows
        append_progress_rows(rows, progress_path, progress_lock)
        done += 1
        failures += int(failed)
        LOG.info("%s %d/%d in %.1fs | %s | %s", spec.slug, done, len(pending), elapsed,
                 rows[0]["asset_key"][:16], "error" if failed else "ok")

    try:
        if pending and workers > 1:
            executor = ThreadPoolExecutor(max_workers=workers)
            try:
                futures = {executor.submit(process_one, d): d for d in pending}
                for future in as_completed(futures):
                    doc = futures[future]
                    try:
                        record(*future.result())
                    except Exception as exc:  # noqa: BLE001
                        record(error_output_rows(doc, exc), 0.0, True)
            except KeyboardInterrupt:
                interrupted = True
                LOG.warning("Stop requested — waiting for in-flight requests...")
                executor.shutdown(wait=True, cancel_futures=True)
            else:
                executor.shutdown(wait=True)
        else:
            for doc in pending:
                record(*process_one(doc))
    except KeyboardInterrupt:
        interrupted = True
        LOG.warning("Stop requested — writing what completed.")

    output_rows = [row for doc in documents
                   for row in completed_by_asset.get(doc.asset_key, [])]
    save_jsonl(output_rows, output_dir / "event_extractions.jsonl")
    save_csv(output_rows, output_dir / "event_extractions.csv")
    # Compact the append-only log so the next resume sees one record per asset.
    save_jsonl(output_rows, progress_path)

    elapsed = time.perf_counter() - started_at
    error_rows = sum(1 for r in output_rows if is_error_row(r))
    stats = {
        "model": spec.id,
        "label": spec.label,
        "tier": spec.tier,
        "reasoning_effort": spec.reasoning_effort,
        "structured_output_mode": sorted(mode_state.get("observed", [])) or ["none"],
        "prompt_id": prompt.id,
        "prompt_name": prompt.name,
        # Detects silent drift in src/fonte/prompts.py across runs.
        "prompt_sha256": hashlib.sha256(prompt.system_prompt.encode()).hexdigest()[:16],
        "max_chars": MAX_CHARS,
        "documents_snapshot": snapshot_meta.get("built_at"),
        "metadata_source": snapshot_meta.get("metadata_source"),
        "documents_total": len(documents),
        "documents_run_now": done,
        "documents_skipped": skipped,
        "error_rows": error_rows,
        "output_rows": len(output_rows),
        "events": sum(1 for r in output_rows if r.get("event_index")),
        "prompt_tokens": totals["prompt_tokens"],
        "completion_tokens": totals["completion_tokens"],
        "cost_usd": round(totals["cost"], 4),
        "wall_seconds": round(elapsed, 1),
        "docs_per_min": round(done / elapsed * 60.0, 2) if elapsed > 0 else 0.0,
        "interrupted": interrupted,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (output_dir / "run_stats.json").write_text(
        json.dumps(stats, indent=2) + "\n", encoding="utf-8")

    LOG.info("%s done in %s | %d events | %d error rows | $%.4f",
             spec.label, format_duration(elapsed), stats["events"], error_rows,
             stats["cost_usd"])
    if interrupted:
        raise KeyboardInterrupt
    return stats


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def check_models(specs: list[ModelSpec]) -> int:
    """Resolve every roster id against the live catalogue before spending."""
    try:
        catalogue = fetch_catalogue()
    except Exception as exc:  # noqa: BLE001
        LOG.error("Could not reach the OpenRouter model catalogue: %s", exc)
        return 2

    LOG.info("%-32s %-8s %8s %8s %9s %-8s %s",
             "MODEL", "STATUS", "$/Min", "$/Mout", "CONTEXT", "STRUCT", "NOTES")
    bad = 0
    warnings: list[str] = []
    for spec in specs:
        entry = catalogue.get(spec.id)
        if entry is None:
            bad += 1
            near = get_close_matches(spec.id, catalogue, n=3, cutoff=0.6)
            LOG.info("%-32s %-8s %s", spec.id, "MISSING",
                     f"did you mean: {', '.join(near)}" if near else "no close match")
            continue

        pricing = entry.get("pricing") or {}
        p_in = float(pricing.get("prompt") or 0) * 1e6
        p_out = float(pricing.get("completion") or 0) * 1e6
        ctx = entry.get("context_length") or 0
        params = set(entry.get("supported_parameters") or [])
        strict = "structured_outputs" in params
        can_reason = "reasoning" in params

        notes = []
        if ctx and ctx < 16000:
            notes.append("context too small for a 12k-char window")
        # The spec claims something the model does not advertise. Not fatal —
        # the runner falls back at runtime — but it costs a wasted call per
        # document, so it is worth fixing in models.py.
        if spec.structured_output == "json_schema" and not strict:
            notes.append("pinned to json_schema but strict output not advertised")
        if spec.structured_output == "auto" and not strict:
            notes.append("no strict output: will fall back to json_object")
        if spec.reasoning_effort and not can_reason:
            notes.append("reasoning_effort set but model does not reason")
        if not spec.reasoning_effort and can_reason:
            notes.append("reasons, but reasoning_effort is unset")
        if notes:
            warnings.append(f"{spec.id}: {'; '.join(notes)}")

        LOG.info("%-32s %-8s %8.2f %8.2f %9s %-8s %s", spec.id, "ok", p_in, p_out, ctx,
                 "strict" if strict else "json_obj", "; ".join(notes))

    if warnings:
        LOG.warning("\n%d model(s) have a spec that does not match advertised "
                    "capability:", len(warnings))
        for w in warnings:
            LOG.warning("  - %s", w)
    if bad:
        LOG.error("\n%d model id(s) do not exist. Fix benchmark_openrouter/models.py "
                  "before running.", bad)
    return 2 if bad else 0


def dry_run(specs: list[ModelSpec], documents: list[DocumentRow]) -> int:
    """Estimate cost from live pricing, without making a single inference call."""
    try:
        catalogue = fetch_catalogue()
    except Exception as exc:  # noqa: BLE001
        LOG.error("Could not reach the OpenRouter model catalogue: %s", exc)
        return 2

    prompt = get_prompt(PROMPT_ID)
    # ~4 chars per token is crude but the right order of magnitude, and the
    # output estimate is the uncertain half anyway (reasoning tokens bill as
    # completion and are not visible up front).
    in_chars = sum(len(prompt.system_prompt)
                   + len(build_user_prompt(prompt, build_prompt_payload(d, MAX_CHARS)))
                   for d in documents)
    est_in = in_chars / 4
    est_out = len(documents) * 1500

    LOG.info("%d documents | ~%.2fM input tokens | ~%.2fM output tokens assumed "
             "(reasoning models will exceed this)", len(documents), est_in / 1e6, est_out / 1e6)
    LOG.info("%-38s %10s", "MODEL", "EST $")
    total = 0.0
    for spec in specs:
        entry = catalogue.get(spec.id)
        if entry is None:
            LOG.info("%-38s %10s", spec.id, "MISSING")
            continue
        pricing = entry.get("pricing") or {}
        cost = est_in * float(pricing.get("prompt") or 0) + est_out * float(pricing.get("completion") or 0)
        total += cost
        LOG.info("%-38s %10.2f", spec.id, cost)
    LOG.info("%-38s %10.2f", "TOTAL", total)
    LOG.info("\nEstimate only. Smoke-test with --limit 3 before committing to a full run.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--model", action="append", default=[],
                     help="OpenRouter model id; repeatable. Off-roster ids are allowed.")
    sel.add_argument("--tier", choices=("frontier", "open", "small"))
    sel.add_argument("--all", action="store_true", help="every model on the roster")
    p.add_argument("--limit", type=int, help="first N documents only (smoke tests)")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--resume", action="store_true",
                   help="skip completed assets, retry ones whose rows are errors")
    p.add_argument("--save-raw", action="store_true",
                   help="dump raw responses to outputs/<slug>/raw/ for debugging")
    p.add_argument("--check-models", action="store_true",
                   help="validate roster ids against OpenRouter; no inference calls")
    p.add_argument("--dry-run", action="store_true",
                   help="estimate cost from live pricing; no inference calls")
    p.add_argument("--out-root", type=Path, default=OUT_ROOT)
    p.add_argument("--snapshot", type=Path, default=None)
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s | %(levelname)s | %(message)s")
    load_dotenv(REPO_ROOT / ".env")
    args = parse_args()

    specs = list(ROSTER) if args.all else select(args.model or None, args.tier)
    if not specs:
        LOG.error("No models selected. Pass --all, --tier, or --model.")
        return 2

    if args.check_models:
        return check_models(specs)

    try:
        kwargs = {"limit": args.limit}
        if args.snapshot:
            kwargs["path"] = args.snapshot
        documents, snapshot_meta = load_documents(**kwargs)
    except SnapshotError as exc:
        LOG.error("%s", exc)
        return 2

    if args.dry_run:
        return dry_run(specs, documents)

    if snapshot_meta.get("metadata_source") == "parquet":
        LOG.warning("Snapshot metadata came from parquet — %s are null, so payloads "
                    "differ slightly from the Azure production run.",
                    ", ".join(snapshot_meta.get("null_fields", [])))

    prompt = get_prompt(PROMPT_ID)
    LOG.info("Prompt %02d (%s) | %d documents | %d model(s)",
             prompt.id, prompt.name, len(documents), len(specs))

    summaries = []
    for spec in specs:
        try:
            summaries.append(run_model(
                spec, documents, prompt,
                out_root=args.out_root, workers=args.workers, resume=args.resume,
                save_raw=args.save_raw, snapshot_meta=snapshot_meta,
            ))
        except KeyboardInterrupt:
            LOG.warning("Interrupted during %s. Rerun with --resume to continue.", spec.id)
            return 130
        except Exception as exc:  # noqa: BLE001 - one bad model must not sink the roster
            LOG.error("%s failed entirely: %s", spec.id, exc)

    if summaries:
        LOG.info("\n%-28s %8s %8s %10s %10s", "MODEL", "EVENTS", "ERRORS", "COST $", "MIN")
        for s in summaries:
            LOG.info("%-28s %8d %8d %10.4f %10.1f", s["label"], s["events"],
                     s["error_rows"], s["cost_usd"], s["wall_seconds"] / 60)
        LOG.info("\nNext: python -m benchmark_openrouter.agreement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
