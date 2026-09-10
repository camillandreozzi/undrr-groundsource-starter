"""Pool the event-sampled arm (n=167) and the document-sampled arm (n=50).

    python -m benchmark_openrouter.pool_arms

WHAT THIS ASSEMBLES
-------------------
* `eval/human_annotations_pooled.csv` — the 217 annotations, both arms, with a
  `sample_arm` column so any metric can be split back apart.
* `benchmark_openrouter/outputs_pooled/<slug>/event_extractions.jsonl` — each
  model's two runs concatenated, in the schema `score_against_human.py` reads.

Only models present in **both** arms are pooled. A model that ran on 167 but not
on 50 would be scored against 217 annotations while covering 167 documents, and
the 50 it never saw would land in the report as misses. Those models are listed
and skipped rather than silently half-scored.

READ THIS BEFORE QUOTING A POOLED NUMBER
----------------------------------------
The two arms have different sampling designs, so the pool has no single
inclusion probability and its prevalence is an artefact of the mixture:

    arm 167 (event-sampled)     157 of 167 gold-positive   94.0%
    arm  50 (document-sampled)   14 of  50 gold-positive   28.0%
    pooled                      171 of 217 gold-positive   78.8%
    the corpus itself                                      ~19-28%

**Prevalence-dependent metrics on the pool describe no real population.**
Accuracy, precision and MCC all move with the base rate, and 78.8% is a number
the mixture invented. Quote those from the 50 alone.

Balanced accuracy is the exception: it is the mean of sensitivity and
specificity, both conditional on the true class, so it does not move with
prevalence. What it is still exposed to is *which* positives and negatives each
half contributes — see the note below.

Recall is conditional on the positives and so survives pooling arithmetically,
but 157 of the 171 pooled positives come from the enriched arm, so a pooled
recall is still overwhelmingly the 167's recall with a rounding error attached.

The same asymmetry runs through pooled specificity, and it matters more. The 46
gold-negative documents are 36 ordinary non-event documents from the random draw
plus 10 from the event-sampled arm — and those 10 are the production run's own
false positives, documents nearly every model calls positive. Pooled specificity
therefore averages an ordinary negative set with a deliberately adversarial one.
The corpus-representative figure is the 36 alone.

What the pool is legitimately good for is **per-field set F1 on gold-positive
documents** (hazards, locations, dates), where the question is "given a document
that does report an event, how well is it described" — that is conditional on
gold-positive too, and the extra 14 documents are 14 more draws of it.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

LOG = logging.getLogger("benchmark_openrouter.pool_arms")

DEFAULT_ARMS = [
    ("event_sample_167",
     REPO_ROOT / "eval" / "human_annotations.csv",
     REPO_ROOT / "benchmark_openrouter" / "outputs"),
    ("document_sample_50",
     REPO_ROOT / "eval" / "human_annotations_document_sample.csv",
     REPO_ROOT / "benchmark_openrouter" / "outputs_docsample"),
]

DEFAULT_ANNOTATIONS_OUT = REPO_ROOT / "eval" / "human_annotations_pooled.csv"
DEFAULT_RUNS_OUT = REPO_ROOT / "benchmark_openrouter" / "outputs_pooled"


def _display(path: Path) -> str:
    """Repo-relative when it can be, as given otherwise."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def read_annotations(path: Path) -> list[dict]:
    csv.field_size_limit(10 ** 9)
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def merge_annotations(arms: list[tuple[str, Path, Path]], out: Path) -> dict:
    rows: list[dict] = []
    seen: dict[str, str] = {}
    per_arm: dict[str, dict] = {}

    for arm, ann_path, _ in arms:
        arm_rows = read_annotations(ann_path)
        done = [r for r in arm_rows
                if str(r.get("annotation_status", "")).strip().lower() == "done"]
        positives = sum(1 for r in done if r.get("gold_is_event") == "yes")
        per_arm[arm] = {
            "annotations": _display(ann_path),
            "rows": len(arm_rows), "done": len(done), "gold_positive": positives,
        }
        for r in arm_rows:
            key = r.get("asset_key", "")
            if key in seen:
                LOG.warning("Document %s is in both %s and %s — keeping the %s copy.",
                            key[:12], seen[key], arm, seen[key])
                continue
            seen[key] = arm
            r = dict(r)
            r["sample_arm"] = arm
            rows.append(r)

    fieldnames = list(rows[0].keys())
    for r in rows:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c, "") for c in fieldnames})

    return {"per_arm": per_arm, "pooled_rows": len(rows),
            "pooled_documents": len(seen)}


def model_slugs(out_dir: Path) -> set[str]:
    if not out_dir.exists():
        return set()
    return {d.name for d in out_dir.iterdir()
            if d.is_dir() and (d / "event_extractions.jsonl").exists()}


def merge_runs(arms: list[tuple[str, Path, Path]], out_dir: Path) -> dict:
    per_arm_slugs = {arm: model_slugs(runs) for arm, _, runs in arms}
    shared = set.intersection(*per_arm_slugs.values()) if per_arm_slugs else set()
    skipped = {arm: sorted(s - shared) for arm, s in per_arm_slugs.items()}

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    pooled: dict[str, dict] = {}
    for slug in sorted(shared):
        dest = out_dir / slug
        dest.mkdir()
        rows = 0
        docs: set[str] = set()
        errors = 0
        with (dest / "event_extractions.jsonl").open("w", encoding="utf-8") as sink:
            for arm, _, runs in arms:
                src = runs / slug / "event_extractions.jsonl"
                for line in src.open(encoding="utf-8"):
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    docs.add(obj.get("asset_key"))
                    if str(obj.get("key_impacts", "")).startswith("ERROR:"):
                        errors += 1
                    rows += 1
                    sink.write(line + "\n")

        # discover_runs() reads only `label` from this file. Carrying the 167
        # arm's cost and token totals into a pooled directory would misreport
        # them, so it is rebuilt rather than copied.
        label = slug
        src_stats = arms[0][2] / slug / "run_stats.json"
        if src_stats.exists():
            label = json.loads(src_stats.read_text()).get("label") or slug
        (dest / "run_stats.json").write_text(json.dumps({
            "label": label,
            "pooled_from": [arm for arm, _, _ in arms],
            "documents": len(docs),
            "rows": rows,
            "error_rows": errors,
            "note": "Pooled directory. Cost/token stats live in the per-arm runs.",
        }, indent=2))
        pooled[slug] = {"label": label, "documents": len(docs),
                        "rows": rows, "error_rows": errors}

    return {"pooled": pooled, "skipped": skipped}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--annotations-out", type=Path, default=DEFAULT_ANNOTATIONS_OUT)
    p.add_argument("--runs-out", type=Path, default=DEFAULT_RUNS_OUT)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    ann = merge_annotations(DEFAULT_ARMS, args.annotations_out)
    runs = merge_runs(DEFAULT_ARMS, args.runs_out)

    LOG.info("Annotations -> %s", _display(args.annotations_out))
    for arm, info in ann["per_arm"].items():
        LOG.info("  %-20s %3d done, %3d gold-positive", arm, info["done"],
                 info["gold_positive"])
    LOG.info("  pooled              %3d documents", ann["pooled_documents"])

    LOG.info("")
    LOG.info("Runs -> %s", _display(args.runs_out))
    for slug, info in runs["pooled"].items():
        flag = f"  ⚠️ {info['error_rows']} error rows" if info["error_rows"] else ""
        LOG.info("  %-34s %3d docs, %4d rows%s", slug, info["documents"],
                 info["rows"], flag)
    for arm, missing in runs["skipped"].items():
        if missing:
            LOG.warning("  skipped (absent from the other arm): %s", ", ".join(missing))

    manifest = args.runs_out / "pool_manifest.json"
    manifest.write_text(json.dumps({"annotations": ann, "runs": runs}, indent=2))
    LOG.info("")
    LOG.info("Wrote %s", _display(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
