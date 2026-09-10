#!/usr/bin/env python3
"""Read-only audit of the finalized production snapshot; standard library only.

Run from any directory: python3 /path/to/scripts/recover_production_operations.py
Counts describe saved results, never inferred API attempts or session boundaries.
Hashes identify the exact artifacts inspected. No environment files or APIs read.
"""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/event_extractions"


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def canonical(row):
    return json.dumps(row, sort_keys=True, ensure_ascii=False)


def is_error(row):
    return str(row.get("key_impacts") or "").startswith("ERROR:")


def main():
    final = read_rows(OUT / "event_extractions.jsonl")
    progress = read_rows(OUT / "event_extractions_progress.jsonl")
    with (OUT / "event_extractions.csv").open(newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    # CSV has two extra empty confidence-probability columns. Compare every
    # column, normalizing JSON null/absent fields to CSV empty strings.
    def csv_form(row, fields):
        return {k: "" if row.get(k) is None else str(row[k]) for k in fields}
    assert len(final) == len(csv_rows), "CSV/JSONL row counts differ"
    assert all(csv_form(a, b) == b for a, b in zip(final, csv_rows)), "CSV/JSONL differ"
    grouped = defaultdict(list)
    for row in final:
        assert row.get("asset_key"), "Missing document identifier"
        grouped[row["asset_key"]].append(row)
    errors = {k for k, rows in grouped.items() if any(map(is_error, rows))}
    events = [r for r in final if r.get("is_verifiable_event") is True]
    event_docs = {r["asset_key"] for r in events}
    zero_docs = set(grouped) - event_docs - errors
    # Positive evidence of a completed empty extraction, not absence of errors.
    assert all(len(grouped[k]) == 1 and grouped[k][0]["event_count"] == 0
               and grouped[k][0]["is_verifiable_event"] is False
               and grouped[k][0]["missing_information"] == "no verified reliable event extracted"
               for k in zero_docs), "Unclassified zero-event result"
    for key in event_docs:
        rows = grouped[key]
        assert all(r["is_verifiable_event"] is True and r["event_count"] == len(rows)
                   for r in rows), "Inconsistent event group"
        assert sorted(r["event_index"] for r in rows) == list(range(1, len(rows) + 1))
    fc, pc = Counter(map(canonical, final)), Counter(map(canonical, progress))
    summary = json.loads((OUT / "visualisation_checks/summary.json").read_text())
    measured = {
        "finalized_documents": len(grouped),
        "saved_successful_document_results": len(grouped) - len(errors),
        "successful_documents_without_retained_events": len(zero_docs),
        "documents_with_retained_events": len(event_docs),
        "retained_event_records": len(events),
        "document_event_yield_percent": 100 * len(event_docs) / len(grouped),
        "output_rows_including_zero_event_placeholders": len(final),
        "documents_with_saved_error_rows": len(errors),
    }
    assert summary["n_unique_asset_key"] == len(grouped)
    assert summary["n_verifiable_events"] == len(events)
    assert summary["n_documents_with_event"] == len(event_docs)
    logs = []
    completion_lines = Counter()
    for path in sorted((ROOT / "outputs").rglob("*.log")):
        lines = path.read_text(errors="replace").splitlines()
        completed = [line for line in lines if re.search(r"Completed prompt .*asset_key=", line)]
        completion_lines.update(completed)
        http = [line for line in lines if "HTTP Request:" in line]
        logs.append({
            "path": str(path.relative_to(ROOT)),
            "scope_lines": [line for line in lines if re.search(
                r"Fetched .*documents|Running prompt|Skipping .*completed|Retrying .*failed|Finished prompt|Total run time", line)],
            "deployment_names": sorted(set(re.findall(r"/deployments/([^/]+)", "\n".join(lines)))),
            "completion_entries": len(completed),
            # Identical HTTP lines are ambiguous without unique request IDs:
            # these counts are not deduplicated API request totals.
            "repeated_identical_http_lines": len(http) - len(set(http)),
            "sdk_retry_log_lines_not_unique_attempts": sum("Retrying request to" in line for line in lines),
        })
    files = [OUT / name for name in ("event_extractions.jsonl", "event_extractions.csv",
             "event_extractions_progress.jsonl", "visualisation_checks/summary.json")]
    print(json.dumps({
        "scope": "Finalized saved output only; not an execution or billing ledger",
        "measured": measured,
        "provenance": {
            "reported_date": "2026-08-07",
            "reported_model": "gpt-5 (Azure)",
            "source": "docs/VALIDATION_REPORT.md:3-4; not timestamped execution metadata",
            "prompt": "5 / unified_verification_recall (documented, no saved prompt hash)",
            "document_text_cap_chars": "12000 (documented/default, not per-request measured)",
        },
        "progress_audit": {
            "rows": len(progress), "documents": len({r['asset_key'] for r in progress}),
            "final_is_exact_prefix": progress[:len(final)] == final,
            "missing_final_rows": sum((fc - pc).values()),
            "extra_rows": sum((pc - fc).values()),
            "extra_documents": len({r['asset_key'] for r in progress} - set(grouped)),
            "error_rows_outside_final": sum(is_error(r) and r['asset_key'] not in grouped for r in progress),
            "exact_duplicate_final_rows": sum(v - 1 for v in fc.values()),
            "exact_duplicate_progress_rows": sum(v - 1 for v in pc.values()),
        },
        "not_recoverable_for_production_execution": [
            "independent selected/submitted/unique-attempted document counts",
            "run start/end, pauses, resumed-session boundaries and effective workers",
            "extraction and end-to-end wall time; successful documents/hour",
            "input/output/cached/reasoning tokens including failed/retried calls",
            "recorded or estimated extraction cost; cost/unique attempted document",
            "production document or request latency observations, median and p95",
            "total/retry attempts, documents retried, terminal failure count and rates",
        ],
        "sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "log_inventory_excluded_from_production_metrics": logs,
        "repeated_identical_completion_lines_across_logs": sum(v - 1 for v in completion_lines.values()),
    }, indent=2))


if __name__ == "__main__":
    main()
