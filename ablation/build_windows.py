"""Freeze the ablation's reference windows -> ablation/windows.csv.

    python -m ablation.build_windows            # refuses to overwrite
    python -m ablation.build_windows --force

No new annotation. Two sources, each with gold that already exists:

  event-present + 1   Experiment A's 45 windows, with their blind event-level
                      gold (`eval/event_level_gold.csv`, read in place). 44 have
                      a verifiable event; 583badf1 has none and joins the
                      event-absent group.
  event-absent        Validation 2 documents judged `gold_is_event == "no"`
                      (`eval/human_annotations_pooled.csv`) that are not
                      already Experiment A windows. "No" there means "no
                      specific, verifiable event in the first 12,000
                      characters" — the same window the models see — so their
                      event-level gold is the empty set.

The negatives pass the same language rule Experiment A applied to its frame
(`citation_quality.guess_language(window) == "en"`, protocol §2); `unclear`
verdicts are left out. Exclusions are written to `windows_summary.json`.

Every window's text is checked against the benchmark snapshot the runner will
send, so the gold and the model input are the same 12,000 characters.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from benchmark_openrouter.citation_quality import guess_language  # noqa: E402
from eval.human_annotation_app import load_document_store, read_csv  # noqa: E402

EVAL = REPO_ROOT / "eval"
ABLATION = REPO_ROOT / "ablation"
OUT = ABLATION / "windows.csv"
SUMMARY = ABLATION / "windows_summary.json"

EXPA_WINDOWS = EVAL / "event_level_windows.csv"
EXPA_QUEUE = EVAL / "event_level_queue.csv"
EXPA_GOLD = EVAL / "event_level_gold.csv"
V2_FRAME = EVAL / "human_annotations_pooled.csv"
GOLD_VALIDATION = EVAL / "gold_validation.csv"
STORES = (EVAL / "annotation_documents.json", EVAL / "annotation_documents_document_sample.json")
SNAPSHOTS = (REPO_ROOT / "benchmark_openrouter" / "documents.json",
             REPO_ROOT / "benchmark_openrouter" / "documents_docsample.json")
# The 400-document development pool prompt 5 was compared on (git-ignored, local).
DEV_POOL = REPO_ROOT / "outputs" / "test_400_gpt5_medium_prompt01" / "event_extractions.jsonl"

COLUMNS = (
    "ablation_rank", "asset_key", "group", "subgroup", "source", "sample_arm",
    "expA_stratum", "expA_review_rank", "v2_review_rank", "v2_seed_event_count",
    "window_language", "window_chars", "text_sha256", "snapshot", "dev_pool_400",
    "gold_validation", "title",
)
RANDOM_ARM = "document_sample_50"


class WindowError(RuntimeError):
    pass


def _jsonl_keys(path: Path) -> set[str]:
    if not path.exists():
        raise WindowError(f"Not found: {path} (the dev-pool flag needs it)")
    with path.open(encoding="utf-8") as f:
        return {json.loads(line)["asset_key"] for line in f if line.strip()}


def _texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    for path in STORES:
        documents, _ = load_document_store(path)
        texts.update({k: v.get("text", "") for k, v in documents.items()})
    return texts


def _snapshots() -> dict[str, tuple[str, str]]:
    """asset_key -> (snapshot file name, text the runner will send)."""
    out: dict[str, tuple[str, str]] = {}
    for path in SNAPSHOTS:
        docs = json.loads(path.read_text(encoding="utf-8"))["documents"]
        out.update({k: (path.name, v.get("text") or "") for k, v in docs.items()})
    return out


def _verifiable_counts() -> Counter:
    _, rows = read_csv(EXPA_GOLD)
    return Counter(r["asset_key"] for r in rows
                   if str(r.get("verifiable", "")).strip().lower() in {"yes", "y", "true"})


def build_windows() -> tuple[list[dict], dict]:
    texts, snapshots = _texts(), _snapshots()
    dev_pool = _jsonl_keys(DEV_POOL)
    _, gv_rows = read_csv(GOLD_VALIDATION)
    gold_validation = {r["asset_key"] for r in gv_rows}
    verifiable = _verifiable_counts()

    _, queue = read_csv(EXPA_QUEUE)
    queue_by_key = {r["asset_key"]: r for r in queue}
    _, expa_rows = read_csv(EXPA_WINDOWS)
    expa = sorted((r for r in expa_rows if r.get("window_status") == "done"),
                  key=lambda r: int(r["review_rank"]))
    if len(expa) != len(queue):
        raise WindowError(f"Experiment A has {len(expa)} done windows of {len(queue)} queued")
    expa_keys = {r["asset_key"] for r in expa}

    _, frame = read_csv(V2_FRAME)
    excluded: list[dict] = []
    negatives: list[dict] = []
    for r in sorted(frame, key=lambda r: r["asset_key"]):
        key = r["asset_key"]
        if key in expa_keys:
            continue
        verdict = r.get("gold_is_event")
        if verdict != "no":
            excluded.append({"asset_key": key, "reason": f"v2_verdict_{verdict or 'blank'}",
                             "sample_arm": r.get("sample_arm")})
            continue
        lang = guess_language(texts.get(key, ""))
        if lang != "en":
            excluded.append({"asset_key": key, "reason": f"not_english:{lang}",
                             "sample_arm": r.get("sample_arm")})
            continue
        negatives.append(r)

    rows: list[dict] = []

    def add(key: str, group: str, subgroup: str, source: str, **extra) -> None:
        text = texts.get(key, "")
        snap_name, snap_text = snapshots.get(key, ("", ""))
        if not text:
            raise WindowError(f"{key[:12]}: no window text in the annotation stores")
        if snap_text != text:
            raise WindowError(f"{key[:12]}: snapshot text differs from the annotated window")
        rows.append({
            "ablation_rank": len(rows) + 1, "asset_key": key, "group": group,
            "subgroup": subgroup, "source": source,
            "window_language": guess_language(text), "window_chars": len(text),
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "snapshot": snap_name, "dev_pool_400": "Y" if key in dev_pool else "",
            "gold_validation": "Y" if key in gold_validation else "", **extra,
        })

    for r in expa:
        key = r["asset_key"]
        q = queue_by_key[key]
        n = verifiable.get(key, 0)
        subgroup = "single" if n == 1 else "multi" if n > 1 else "expA_none"
        add(key, "event_present" if n else "event_absent", subgroup, "expA",
            sample_arm=q.get("sample_arm", ""), expA_stratum=q.get("stratum", ""),
            expA_review_rank=r["review_rank"], v2_review_rank="",
            v2_seed_event_count=q.get("seed_event_count", ""), title=r.get("title", ""))
    for r in negatives:
        arm = r.get("sample_arm", "")
        add(r["asset_key"], "event_absent",
            "random_negative" if arm == RANDOM_ARM else "hard_negative", "v2_negative",
            sample_arm=arm, expA_stratum="", expA_review_rank="",
            v2_review_rank=r.get("review_rank", ""),
            v2_seed_event_count=r.get("seed_event_count", ""), title=r.get("title", ""))

    summary = {
        "windows": len(rows),
        "groups": dict(Counter(r["group"] for r in rows)),
        "subgroups": dict(Counter(r["subgroup"] for r in rows)),
        "dev_pool_400": [r["asset_key"] for r in rows if r["dev_pool_400"]],
        "gold_validation": [r["asset_key"] for r in rows if r["gold_validation"]],
        "excluded_counts": dict(Counter(e["reason"].split(":")[0] for e in excluded)),
        "excluded": excluded,
        "sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (EXPA_WINDOWS, EXPA_QUEUE, EXPA_GOLD, V2_FRAME, GOLD_VALIDATION)},
    }
    return rows, summary


def write_windows(rows: list[dict], summary: dict, out: Path = OUT,
                  summary_path: Path = SUMMARY) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--force", action="store_true", help="overwrite ablation/windows.csv")
    args = p.parse_args(argv)
    if OUT.exists() and not args.force:
        raise SystemExit(f"{OUT.relative_to(REPO_ROOT)} exists; pass --force to rebuild")
    rows, summary = build_windows()
    write_windows(rows, summary)
    print(f"{summary['windows']} windows -> {OUT.relative_to(REPO_ROOT)}")
    print(f"  groups    {summary['groups']}")
    print(f"  subgroups {summary['subgroups']}")
    print(f"  excluded  {summary['excluded_counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
