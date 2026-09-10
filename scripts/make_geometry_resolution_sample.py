"""
make_geometry_resolution_sample.py
----------------------------------

Draw a review sample for **geometry resolution checking** — the narrow question
of whether the polygon Nominatim returned actually corresponds to the location
text the extractor produced.

This is deliberately *not* `make_polygon_validation_sample.py`. That script
builds a stratified sample that judges the whole pipeline (did the extractor
pick a real place? were the dates right? is the polygon right?) across three
strata including unresolved rows. This one judges **only the resolver**, over
**only rows that actually have a geometry**, with a **uniform random** draw so
the resulting rate is an unbiased estimate over the resolved population.

Output
------
`geometry_resolution_sample.csv` — one row per sampled location, carrying the
source context, everything Nominatim decided, the geometry itself as GeoJSON
(simplified for display), and blank reviewer columns:

* `geometry_correct`  — Y / Partial / N
* `failure_mode`      — which way it went wrong (blank when Y)
* `notes`             — free text

The GeoJSON is embedded in the CSV so the review app needs nothing but this one
file — no 628 MB parquet, no network round-trip to Nominatim.

Usage
-----

    python scripts/make_geometry_resolution_sample.py

    python scripts/make_geometry_resolution_sample.py \
      --geometries outputs/event_extractions/event_geometries.parquet \
      --output-dir outputs/event_extractions_geometry_resolution \
      --n 75 --seed 42
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping

LOG = logging.getLogger("geometry_resolution_sample")

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_GEOMETRIES = REPO_ROOT / "outputs" / "event_extractions" / "event_geometries.parquet"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "event_extractions_geometry_resolution"

# Columns pulled from the resolver output. Deliberately excludes the columns
# that describe the *extractor's* choices beyond what is needed to judge the
# geometry, so the reviewer stays on one question.
SOURCE_COLUMNS = [
    "uuid",
    "asset_key",
    "title",
    "content_url",
    "hazard",
    "start_date",
    "end_date",
    "location_text",
    "country_hint",
    "countries_raw",
    "extractor_admin_level",
    "area_km2",
    "resolution_query",
    "resolution_display_name",
    "resolution_admin_level",
    "resolution_geometry_source",
    "resolution_used_fallback",
    "resolution_confidence",
    "geometry_overshoot",
    "geometry_postprocess",
    "geometry_pre_postprocess_area_km2",
]

LABEL_COLUMNS = ["geometry_correct", "failure_mode", "notes"]


# ---------------------------------------------------------------------------
# Geometry -> compact GeoJSON for the review app
# ---------------------------------------------------------------------------

def simplify_for_display(geom, max_vertices: int = 1500):
    """Shrink a polygon to something a browser can draw instantly.

    Tolerance is scaled to the geometry's own bbox, so a country and a
    neighbourhood both keep their recognisable outline. We only simplify when
    the geometry is actually heavy — small polygons pass through untouched.
    """
    if geom is None or geom.is_empty:
        return geom

    def vertex_count(g) -> int:
        return len(json.dumps(mapping(g))) // 20  # cheap proxy, avoids a walk

    if vertex_count(geom) <= max_vertices:
        return geom

    minx, miny, maxx, maxy = geom.bounds
    span = max(maxx - minx, maxy - miny)
    tolerance = span / 2000.0  # ~1/2000th of the shape's own extent
    for _ in range(6):
        simplified = geom.simplify(tolerance, preserve_topology=True)
        if simplified.is_empty:
            return geom
        if vertex_count(simplified) <= max_vertices:
            return simplified
        tolerance *= 2.5
    return simplified


def geometry_payload(geom) -> tuple[str, str, str]:
    """Return (geojson, bounds_json, centroid_json) as compact strings."""
    if geom is None or geom.is_empty:
        return "", "", ""
    display = simplify_for_display(geom)
    minx, miny, maxx, maxy = display.bounds
    c = display.centroid
    return (
        json.dumps(mapping(display), separators=(",", ":")),
        json.dumps([[miny, minx], [maxy, maxx]], separators=(",", ":")),
        json.dumps([c.y, c.x], separators=(",", ":")),
    )


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def draw_sample(g: gpd.GeoDataFrame, n: int, seed: int) -> gpd.GeoDataFrame:
    """Uniform random draw over rows that have a usable geometry."""
    usable = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
    LOG.info("resolved rows with geometry: %d", len(usable))
    if len(usable) <= n:
        LOG.warning("population (%d) <= requested n (%d); taking all", len(usable), n)
        return usable
    return usable.sample(n=n, random_state=seed)


def build_rows(sample: gpd.GeoDataFrame) -> pd.DataFrame:
    records = []
    for rank, (_, row) in enumerate(sample.iterrows(), start=1):
        geojson, bounds, centroid = geometry_payload(row.geometry)
        record = {"review_id": rank}
        for col in SOURCE_COLUMNS:
            value = row.get(col)
            if value is None or (isinstance(value, float) and pd.isna(value)):
                value = ""
            record[col] = value
        record["geometry_geojson"] = geojson
        record["geometry_bounds"] = bounds
        record["geometry_centroid"] = centroid
        for col in LABEL_COLUMNS:
            record[col] = ""
        records.append(record)
    return pd.DataFrame.from_records(records)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--geometries", type=Path, default=DEFAULT_GEOMETRIES,
                   help="event_geometries.parquet from the polygon resolver")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--n", type=int, default=75, help="how many locations to sample")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing sample (destroys reviews in it)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    out_dir = args.output_dir
    out_csv = out_dir / "geometry_resolution_sample.csv"
    if out_csv.exists() and not args.force:
        LOG.error("%s already exists. Re-run with --force to overwrite "
                  "(this destroys any reviews already in it).", out_csv)
        return 1

    LOG.info("reading %s", args.geometries)
    g = gpd.read_parquet(args.geometries)
    LOG.info("total resolver rows: %d", len(g))

    sample = draw_sample(g, args.n, args.seed)
    LOG.info("sampled %d rows (seed=%d)", len(sample), args.seed)

    frame = build_rows(sample)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out_csv, index=False)
    LOG.info("wrote %s (%.1f MB)", out_csv, out_csv.stat().st_size / 1e6)

    resolved_pop = int((g.geometry.notna() & ~g.geometry.is_empty).sum())
    summary = {
        "geometries": str(args.geometries),
        "population": {"resolver_rows": int(len(g)), "with_geometry": resolved_pop},
        "params": {"n": args.n, "seed": args.seed, "sampling": "uniform_random"},
        "sample_composition": {
            "geometry_source": frame["resolution_geometry_source"]
            .value_counts().to_dict(),
            "admin_level": frame["resolution_admin_level"].value_counts().to_dict(),
            "used_fallback": frame["resolution_used_fallback"]
            .value_counts().to_dict(),
        },
    }
    out_json = out_dir / "geometry_resolution_summary.json"
    out_json.write_text(json.dumps(summary, indent=2, default=str))
    LOG.info("wrote %s", out_json)
    LOG.info("\nReview it with:\n    streamlit run eval/geometry_resolution_app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
