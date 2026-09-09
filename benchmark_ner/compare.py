"""benchmark_ner/compare.py — automatic LLM-vs-NER agreement.

Compares the two runs on the documents they share. There is no ground truth at
this scale, so **every number here is agreement, not accuracy** — the LLM run
is the reference only in the arithmetic sense. Accuracy comes from the paired
human queue (`prefill_paired_validation.py` / `score_paired.py`).

Reported:
  * document level — does the document yield an event? (2x2, P/R/F1, kappa)
  * hazard        — do the hazard families agree, per document?
  * locations     — per-document set P/R/F1, exact and fuzzy
  * dates         — exact and year-only agreement
  * geocoding     — resolution rate, admin-level mix, confidence, polygon IoU
  * cost/runtime  — measured for NER; stated as unrecorded for the LLM run

    python benchmark_ner/compare.py
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from fonte.hazard_families import hazard_family
from fonte.run_polygon_resolution import explode_extractions
from fonte.stats import format_rate

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "benchmark_ner" / "outputs"
DEFAULT_LLM = REPO_ROOT / "outputs" / "event_extractions" / "event_extractions.jsonl"
DEFAULT_NER = OUT_DIR / "ner_extractions.jsonl"
DEFAULT_LLM_GEOM = REPO_ROOT / "outputs" / "event_extractions" / "event_geometries.parquet"
DEFAULT_NER_GEOM = OUT_DIR / "event_geometries.parquet"

LOG = logging.getLogger("benchmark_ner.compare")

FUZZY_THRESHOLD = 90
EQUAL_AREA_EPSG = 6933


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def _split(s: Optional[str]) -> list[str]:
    return [p.strip() for p in str(s or "").split("|") if p.strip()]


def _is_verifiable(obj: dict) -> bool:
    v = obj.get("is_verifiable_event")
    return v is True or str(v).strip().lower() == "true"


class Run:
    """One extraction run, indexed by asset_key."""

    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path
        self.docs: set[str] = set()
        self.events: dict[str, list[dict]] = defaultdict(list)
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                key = obj.get("asset_key")
                if not key:
                    continue
                self.docs.add(key)
                if _is_verifiable(obj):
                    self.events[key].append(obj)

    def has_event(self, key: str) -> bool:
        return bool(self.events.get(key))

    def families(self, key: str) -> set[str]:
        return {hazard_family(e.get("event_hazard") or "") for e in self.events.get(key, [])}

    def locations(self, key: str) -> set[str]:
        out: set[str] = set()
        for e in self.events.get(key, []):
            out.update(l.lower() for l in _split(e.get("affected_locations")))
        return out

    def dates(self, key: str) -> set[str]:
        out: set[str] = set()
        for e in self.events.get(key, []):
            out.update(_split(e.get("event_dates")))
        return out

    def event_count(self) -> int:
        return sum(len(v) for v in self.events.values())


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def cohen_kappa(tp: int, fp: int, fn: int, tn: int) -> float:
    """Agreement corrected for what chance alone would produce.

    With 80% of this corpus yielding no event, raw agreement is high by
    default; kappa is what says whether the two pipelines agree for a reason.
    """
    n = tp + fp + fn + tn
    if n == 0:
        return 0.0
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    return (po - pe) / (1 - pe) if pe != 1 else 0.0


def fuzzy_match_sets(a: set[str], b: set[str], threshold: int) -> int:
    """Greedy 1-to-1 matches between two location sets above `threshold`.

    Greedy on the best available pair each round: "Port-au-Prince" should match
    "Port au Prince" rather than being blocked by an earlier weaker pairing.
    """
    if not a or not b:
        return 0
    from rapidfuzz import fuzz

    pairs = []
    for x in a:
        for y in b:
            score = fuzz.token_set_ratio(x, y)
            if score >= threshold:
                pairs.append((score, x, y))
    pairs.sort(reverse=True)
    used_a: set[str] = set()
    used_b: set[str] = set()
    matched = 0
    for _score, x, y in pairs:
        if x in used_a or y in used_b:
            continue
        used_a.add(x)
        used_b.add(y)
        matched += 1
    return matched


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 0.0


# --------------------------------------------------------------------------
# Geocoding
# --------------------------------------------------------------------------

def geometry_summary(jsonl: Path, parquet: Path) -> Optional[dict]:
    """Resolution rate and geometry mix for one run."""
    if not parquet.exists():
        LOG.warning("No geometries at %s — skipping that run's geocoding block.", parquet)
        return None
    import geopandas as gpd

    gdf = gpd.read_parquet(parquet)
    attempted = len(list(explode_extractions(jsonl))) if jsonl.exists() else None
    return {
        "gdf": gdf,
        "attempted": attempted,
        "resolved": len(gdf),
        "admin_levels": Counter(gdf["resolution_admin_level"].fillna("none")),
        "mean_confidence": float(gdf["resolution_confidence"].mean()) if len(gdf) else None,
        "mean_area_km2": float(gdf["area_km2"].mean()) if len(gdf) else None,
        "country_fallback": int(gdf.get("resolution_country_fallback", 0).sum())
        if "resolution_country_fallback" in gdf else None,
    }


def polygon_iou(llm_gdf, ner_gdf, common: set[str]) -> dict:
    """IoU for (asset_key, location) pairs both runs resolved.

    Areas in EPSG:6933, the equal-area projection `compute_area_km2` already
    uses — IoU on raw lat/lon would be distorted by latitude.
    """
    def keyed(gdf):
        g = gdf.copy()
        g = g[g["asset_key"].isin(common)]
        g["_k"] = g["asset_key"] + "\x1f" + g["location_text"].str.lower().str.strip()
        return g.drop_duplicates("_k").set_index("_k")

    a, b = keyed(llm_gdf), keyed(ner_gdf)
    shared = a.index.intersection(b.index)
    if len(shared) == 0:
        return {"pairs": 0}

    ga = a.loc[shared].to_crs(EQUAL_AREA_EPSG)
    gb = b.loc[shared].to_crs(EQUAL_AREA_EPSG)
    inter = ga.geometry.intersection(gb.geometry, align=True).area
    union = ga.geometry.union(gb.geometry, align=True).area
    iou = (inter / union).where(union > 0, 0.0)
    return {
        "pairs": int(len(shared)),
        "mean_iou": float(iou.mean()),
        "median_iou": float(iou.median()),
        "identical": int((iou > 0.99).sum()),
        "disjoint": int((iou < 0.01).sum()),
    }


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--llm", type=Path, default=DEFAULT_LLM)
    p.add_argument("--ner", type=Path, default=DEFAULT_NER)
    p.add_argument("--llm-geometries", type=Path, default=DEFAULT_LLM_GEOM)
    p.add_argument("--ner-geometries", type=Path, default=DEFAULT_NER_GEOM)
    p.add_argument("--ner-stats", type=Path, default=OUT_DIR / "ner_run_stats.json")
    p.add_argument("--out-md", type=Path, default=REPO_ROOT / "benchmark_ner" / "COMPARISON.md")
    p.add_argument("--out-csv", type=Path, default=OUT_DIR / "comparison.csv")
    p.add_argument("--skip-geometry", action="store_true",
                   help="Skip the geocoding block (the parquet files are large).")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    for path in (args.llm, args.ner):
        if not path.exists():
            LOG.error("Missing input: %s", path)
            return 1

    llm = Run("llm", args.llm)
    ner = Run("ner", args.ner)
    common = sorted(llm.docs & ner.docs)
    LOG.info("LLM %d docs, NER %d docs, common %d", len(llm.docs), len(ner.docs), len(common))
    if not common:
        LOG.error("No shared documents — nothing to compare.")
        return 1

    metrics: list[dict] = []

    def record(section: str, metric: str, value, note: str = "") -> None:
        metrics.append({"section": section, "metric": metric, "value": value, "note": note})

    # ---- document level ---------------------------------------------------
    tp = fp = fn = tn = 0
    for k in common:
        l, n = llm.has_event(k), ner.has_event(k)
        if l and n:
            tp += 1
        elif n and not l:
            fp += 1
        elif l and not n:
            fn += 1
        else:
            tn += 1
    p, r, f1 = prf(tp, fp, fn)
    kappa = cohen_kappa(tp, fp, fn, tn)

    # ---- hazard / locations / dates ---------------------------------------
    both = [k for k in common if llm.has_event(k) and ner.has_event(k)]
    fam_exact = sum(1 for k in both if llm.families(k) == ner.families(k))
    fam_overlap = sum(1 for k in both if llm.families(k) & ner.families(k))
    fam_jaccard = (sum(jaccard(llm.families(k), ner.families(k)) for k in both) / len(both)) if both else 0.0
    fam_recall: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for k in both:
        nf = ner.families(k)
        for fam in llm.families(k):
            fam_recall[fam][1] += 1
            if fam in nf:
                fam_recall[fam][0] += 1

    loc_tp = loc_fp = loc_fn = 0
    floc_tp = floc_fp = floc_fn = 0
    date_tp = date_fp = date_fn = 0
    year_tp = year_fp = year_fn = 0
    for k in both:
        la, na = llm.locations(k), ner.locations(k)
        loc_tp += len(la & na)
        loc_fp += len(na - la)
        loc_fn += len(la - na)
        m = fuzzy_match_sets(la, na, FUZZY_THRESHOLD)
        floc_tp += m
        floc_fp += len(na) - m
        floc_fn += len(la) - m

        ld, nd = llm.dates(k), ner.dates(k)
        date_tp += len(ld & nd)
        date_fp += len(nd - ld)
        date_fn += len(ld - nd)
        ly, ny = {d[:4] for d in ld}, {d[:4] for d in nd}
        year_tp += len(ly & ny)
        year_fp += len(ny - ly)
        year_fn += len(ly - ny)

    record("corpus", "common_documents", len(common))
    record("corpus", "llm_events", llm.event_count())
    record("corpus", "ner_events", ner.event_count())
    for name, (a, b, c) in {
        "document_prf": (p, r, f1),
        "location_prf_exact": prf(loc_tp, loc_fp, loc_fn),
        "location_prf_fuzzy": prf(floc_tp, floc_fp, floc_fn),
        "date_prf_exact": prf(date_tp, date_fp, date_fn),
        "date_prf_year_only": prf(year_tp, year_fp, year_fn),
    }.items():
        record(name.split("_")[0], f"{name}_precision", round(a, 3))
        record(name.split("_")[0], f"{name}_recall", round(b, 3))
        record(name.split("_")[0], f"{name}_f1", round(c, 3))
    record("document", "cohen_kappa", round(kappa, 3))
    record("hazard", "family_set_exact_match", round(fam_exact / len(both), 3) if both else "")
    record("hazard", "family_any_overlap", round(fam_overlap / len(both), 3) if both else "")
    record("hazard", "family_mean_jaccard", round(fam_jaccard, 3))

    # ---- geocoding --------------------------------------------------------
    geo_llm = geo_ner = None
    iou = None
    if not args.skip_geometry:
        geo_llm = geometry_summary(args.llm, args.llm_geometries)
        geo_ner = geometry_summary(args.ner, args.ner_geometries)
        if geo_llm and geo_ner:
            iou = polygon_iou(geo_llm["gdf"], geo_ner["gdf"], set(common))
            for kk, vv in iou.items():
                record("geocoding", f"iou_{kk}", vv)

    # ---- cost / runtime ---------------------------------------------------
    stats = {}
    if args.ner_stats.exists():
        stats = json.loads(args.ner_stats.read_text())
        record("runtime", "ner_wall_clock_s", stats.get("wall_clock_s"))
        record("runtime", "ner_docs_per_second", stats.get("docs_per_second"))
        record("runtime", "ner_api_cost_usd", 0.0)

    # ---- write ------------------------------------------------------------
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["section", "metric", "value", "note"])
        w.writeheader()
        w.writerows(metrics)

    L: list[str] = []
    A = L.append
    A("# NER baseline vs LLM extraction — automatic comparison")
    A("")
    A(f"**LLM run:** `{args.llm}`  ")
    A(f"**NER baseline:** `{args.ner}`  ")
    A(f"**Generated:** {datetime.now():%Y-%m-%d %H:%M}")
    A("")
    A("> Every figure below is **agreement between two unlabelled runs**, not")
    A("> accuracy. The LLM output is the reference only arithmetically. For")
    A("> accuracy, see `benchmark_ner/PAIRED_VALIDATION.md`.")
    A("")
    A("## 1. Corpus")
    A("")
    A("| | |")
    A("|---|---:|")
    A(f"| Documents in LLM run | {len(llm.docs):,} |")
    A(f"| Documents in NER run | {len(ner.docs):,} |")
    A(f"| **Common documents (the denominator)** | **{len(common):,}** |")
    A(f"| Verifiable events — LLM | {llm.event_count():,} |")
    A(f"| Verifiable events — NER | {ner.event_count():,} |")
    A("")
    A("## 2. Does the document yield an event?")
    A("")
    A("| | NER: yes | NER: no |")
    A("|---|---:|---:|")
    A(f"| **LLM: yes** | {tp:,} | {fn:,} |")
    A(f"| **LLM: no** | {fp:,} | {tn:,} |")
    A("")
    A(f"- NER recall of LLM-positive documents: {format_rate(tp, tp + fn)}")
    A(f"- NER precision against LLM: {format_rate(tp, tp + fp)}")
    A(f"- F1: {f1:.3f} · Cohen's kappa: {kappa:.3f}")
    A("")
    A("Kappa matters more than raw agreement here: four fifths of the corpus")
    A("yields no event, so two pipelines that both mostly say \"no\" agree")
    A("often by construction.")
    A("")
    A("## 3. Hazard (documents where both found something)")
    A("")
    A(f"n = {len(both):,} documents")
    A("")
    A(f"- Identical hazard-family set: {format_rate(fam_exact, len(both))}")
    A(f"- At least one family in common: {format_rate(fam_overlap, len(both))}")
    A(f"- Mean Jaccard over family sets: {fam_jaccard:.3f}")
    A("")
    A("| Family (LLM) | Also found by NER | Documents |")
    A("|---|---:|---:|")
    for fam, (hit, tot) in sorted(fam_recall.items(), key=lambda x: -x[1][1]):
        A(f"| {fam} | {format_rate(hit, tot)} | {tot} |")
    A("")
    A("## 4. Locations and dates")
    A("")
    A("Pooled over the same documents, comparing the per-document sets.")
    A("")
    A("| | Precision | Recall | F1 |")
    A("|---|---:|---:|---:|")
    for label, (a_, b_, c_) in (
        ("Locations, exact string", prf(loc_tp, loc_fp, loc_fn)),
        (f"Locations, fuzzy (token_set ≥ {FUZZY_THRESHOLD})", prf(floc_tp, floc_fp, floc_fn)),
        ("Dates, exact", prf(date_tp, date_fp, date_fn)),
        ("Dates, year only", prf(year_tp, year_fp, year_fn)),
    ):
        A(f"| {label} | {a_:.3f} | {b_:.3f} | {c_:.3f} |")
    A("")
    if geo_llm and geo_ner:
        A("## 5. Geocoding")
        A("")
        A("Both runs went through the same `fonte-polygons` resolver,")
        A("fallback ladder and coastal post-processing.")
        A("")
        A("| | LLM | NER |")
        A("|---|---:|---:|")
        A(f"| Location mentions attempted | {geo_llm['attempted']:,} | {geo_ner['attempted']:,} |")
        A(f"| Resolved to a geometry | {geo_llm['resolved']:,} | {geo_ner['resolved']:,} |")
        if geo_llm["attempted"] and geo_ner["attempted"]:
            A(f"| Resolution rate | {geo_llm['resolved'] / geo_llm['attempted']:.1%} "
              f"| {geo_ner['resolved'] / geo_ner['attempted']:.1%} |")
        A(f"| Mean resolver confidence | {geo_llm['mean_confidence']:.3f} "
          f"| {geo_ner['mean_confidence']:.3f} |")
        A(f"| Mean geometry area (km²) | {geo_llm['mean_area_km2']:,.0f} "
          f"| {geo_ner['mean_area_km2']:,.0f} |")
        A("")
        A("Admin levels:")
        A("")
        A("| Level | LLM | NER |")
        A("|---|---:|---:|")
        for lvl in sorted(set(geo_llm["admin_levels"]) | set(geo_ner["admin_levels"])):
            A(f"| {lvl} | {geo_llm['admin_levels'].get(lvl, 0):,} "
              f"| {geo_ner['admin_levels'].get(lvl, 0):,} |")
        A("")
        if iou and iou.get("pairs"):
            A(f"Polygon overlap on the {iou['pairs']:,} (document, location) pairs both")
            A("runs resolved, in equal-area EPSG:6933:")
            A("")
            A(f"- Mean IoU {iou['mean_iou']:.3f}, median {iou['median_iou']:.3f}")
            A(f"- Effectively identical (IoU > 0.99): {iou['identical']:,}")
            A(f"- Disjoint (IoU < 0.01): {iou['disjoint']:,}")
            A("")
    A("## 6. Cost and runtime")
    A("")
    if stats:
        A(f"- **NER:** {stats.get('documents', 0):,} documents in "
          f"{stats.get('wall_clock_s', 0):,.0f}s "
          f"({stats.get('docs_per_second')} docs/s), **$0 API cost**, "
          f"model `{stats.get('model')}` (spaCy {stats.get('spacy_version')}).")
    else:
        A("- **NER:** stats file not found; re-run `ner_extract.py`.")
    A("- **LLM:** the 10,000-document run's wall clock and token spend were not")
    A("  recorded — no run log survives and the extractor does not persist token")
    A("  counts. Rather than back-estimate them, treat the LLM cost as *unknown*")
    A("  and take it from Azure billing for the extraction window, or re-run both")
    A("  pipelines over an identical small sample for a measured head-to-head.")
    A("")

    args.out_md.write_text("\n".join(L))
    LOG.info("Wrote %s and %s", args.out_md, args.out_csv)
    print("\n".join(L[:40]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
