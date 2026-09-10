"""
Local Streamlit reviewer for geometry resolution — does the polygon Nominatim
returned actually correspond to the location the extractor named?

Run from the repository root:

    streamlit run eval/geometry_resolution_app.py

By default it edits the uniform-random n=75 sample from the production run:

    outputs/event_extractions_geometry_resolution/geometry_resolution_sample.csv

Point it elsewhere with the GEOMETRY_RESOLUTION_CSV env var, or an argument
after `--`:

    streamlit run eval/geometry_resolution_app.py -- outputs/.../sample.csv

Build the sample first with:

    python scripts/make_geometry_resolution_sample.py

One question per row
--------------------
`geometry_correct` — Y / Partial / N. Judge the RESOLVER only, not the
extractor: given the text in `location_text`, is the drawn shape the right
shape? A location the extractor should never have picked still gets a Y here if
Nominatim mapped it faithfully.

* **Y**       the shape is the place named, at the right granularity
* **Partial** the right general place, wrong extent — a district resolved to
              its seat, a bbox where the coastline matters, a metro area
              standing in for a city
* **N**       a different place, a homonym elsewhere, or an unusable shape

`failure_mode` narrows the Partial/N cases; leave it blank on Y.

The app edits the CSV in place, taking one timestamped backup per session
before the first write, and autosaves the current row on "Save & Next".
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV_PATH = (
    REPO_ROOT
    / "outputs"
    / "event_extractions_geometry_resolution"
    / "geometry_resolution_sample.csv"
)

# Written by scripts/make_geometry_resolution_sample.py; never edited here.
REFERENCE_COLUMNS = (
    "review_id",
    "uuid",
    "location_text",
    "resolution_query",
    "resolution_display_name",
    "resolution_admin_level",
    "resolution_geometry_source",
    "geometry_geojson",
)

LABEL_COLUMNS = ("geometry_correct", "failure_mode", "notes")

# A row counts as reviewed once this is set.
PRIMARY_LABEL = "geometry_correct"

VERDICT_OPTIONS = ("", "Y", "Partial", "N")

VERDICT_HELP = {
    "Y": "Right place, right extent.",
    "Partial": "Right general place, wrong extent or granularity.",
    "N": "Different place, homonym, or unusable shape.",
}

FAILURE_MODES = (
    "",
    "wrong_place",
    "homonym_wrong_country",
    "too_coarse",
    "too_fine",
    "wrong_admin_tier",
    "bbox_artifact",
    "postprocess_damage",
    "text_too_vague",
    "other",
)

FAILURE_MODE_HELP = """
* **wrong_place** — a different place altogether
* **homonym_wrong_country** — same name, wrong country/region
* **too_coarse** — resolved up: a town became its province, a district its state
* **too_fine** — resolved down: a district became its seat, a region a single city
* **wrong_admin_tier** — right name and country, wrong administrative level
* **bbox_artifact** — a rectangle where the real outline matters (coast, island, valley)
* **postprocess_damage** — coastal clip / exclusion zone mangled an otherwise good shape
* **text_too_vague** — the location text cannot pin a shape ("northern parts", "the region")
* **other** — say what in notes
"""


class SampleCsvError(ValueError):
    """Raised when the sample CSV is missing or not reviewable."""


# ---------------------------------------------------------------------------
# CSV IO (atomic, backup-on-first-write) — mirrors eval/polygon_validation_review_app.py
# ---------------------------------------------------------------------------

def _clean(value: object) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() in {"nan", "none"}:
        return ""
    return s


def read_sample_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        raise SampleCsvError(
            f"Sample CSV not found: {path}\n\n"
            "Build it with:  python scripts/make_geometry_resolution_sample.py"
        )

    # The GeoJSON column can be far larger than csv's default field cap.
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        missing = [c for c in REFERENCE_COLUMNS if c not in fieldnames]
        if missing:
            raise SampleCsvError(
                "Sample CSV is missing required columns: " + ", ".join(missing)
            )
        for col in LABEL_COLUMNS:
            if col not in fieldnames:
                fieldnames.append(col)
        rows = [{k: _clean(row.get(k)) for k in fieldnames} for row in reader]

    return fieldnames, rows


def write_sample_csv_atomic(
    path: Path,
    fieldnames: Iterable[str],
    rows: Iterable[dict[str, str]],
) -> None:
    path = path.resolve()
    fieldnames = list(fieldnames)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({c: row.get(c, "") for c in fieldnames})
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        finally:
            raise


def create_backup(path: Path, timestamp: str | None = None) -> Path:
    if not path.exists():
        raise SampleCsvError(f"Cannot back up missing CSV: {path}")
    stamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak.{stamp}")
    counter = 2
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak.{stamp}.{counter}")
        counter += 1
    shutil.copy2(path, backup)
    return backup


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def first_blank_index(rows: list[dict[str, str]]) -> int:
    for i, row in enumerate(rows):
        if not row.get(PRIMARY_LABEL, "").strip():
            return i
    return max(0, len(rows) - 1)


def remaining_blank_count(rows: list[dict[str, str]]) -> int:
    return sum(1 for row in rows if not row.get(PRIMARY_LABEL, "").strip())


def normalize_choice(value: str, options: tuple[str, ...]) -> str:
    value = (value or "").strip()
    return value if value in options else ""


def verdict_tally(rows: list[dict[str, str]]) -> dict[str, int]:
    tally = {v: 0 for v in VERDICT_OPTIONS if v}
    for row in rows:
        v = row.get(PRIMARY_LABEL, "").strip()
        if v in tally:
            tally[v] += 1
    return tally


# ---------------------------------------------------------------------------
# Map rendering — folium, embedded as raw HTML so streamlit_folium isn't needed
# ---------------------------------------------------------------------------

def _parse_json(raw: str, default):
    raw = (raw or "").strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default


def build_map_html(row: dict[str, str]) -> str | None:
    """Render the resolved polygon on an OSM basemap, fitted to its bounds."""
    import folium

    geojson = _parse_json(row.get("geometry_geojson", ""), None)
    if not geojson:
        return None

    bounds = _parse_json(row.get("geometry_bounds", ""), None)
    centroid = _parse_json(row.get("geometry_centroid", ""), None)

    fmap = folium.Map(
        location=centroid or [0, 0],
        zoom_start=5,
        tiles="OpenStreetMap",
        control_scale=True,
    )
    folium.GeoJson(
        geojson,
        name="resolved geometry",
        style_function=lambda _: {
            "fillColor": "#d94801",
            "color": "#d94801",
            "weight": 2,
            "fillOpacity": 0.22,
        },
    ).add_to(fmap)

    if centroid:
        folium.CircleMarker(
            location=centroid,
            radius=4,
            color="#7f2704",
            fill=True,
            fill_opacity=1.0,
            tooltip="centroid",
        ).add_to(fmap)

    if bounds:
        fmap.fit_bounds(bounds, padding=(20, 20))

    return fmap.get_root().render()


# ---------------------------------------------------------------------------
# Streamlit state
# ---------------------------------------------------------------------------

def resolve_csv_path() -> Path:
    env = os.environ.get("GEOMETRY_RESOLUTION_CSV", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    for arg in sys.argv[1:]:
        if arg and not arg.startswith("-"):
            return Path(arg).expanduser().resolve()
    return DEFAULT_CSV_PATH


def _set_row_index(index: int, rows: list[dict[str, str]]) -> None:
    import streamlit as st

    if not rows:
        st.session_state.row_index = 0
        return
    st.session_state.row_index = max(0, min(index, len(rows) - 1))


def _load_state(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    import streamlit as st

    fieldnames, rows = read_sample_csv(path)
    if "row_index" not in st.session_state:
        st.session_state.row_index = first_blank_index(rows)
    return fieldnames, rows


def _ensure_session_backup(path: Path) -> None:
    import streamlit as st

    key = f"backup_path::{path.resolve()}"
    if key not in st.session_state:
        st.session_state[key] = str(create_backup(path))


def _save_current_row(
    *,
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
    row_index: int,
    values: dict[str, str],
) -> None:
    rows[row_index].update(values)
    write_sample_csv_atomic(path, fieldnames, rows)


# ---------------------------------------------------------------------------
# UI panels
# ---------------------------------------------------------------------------

def _fmt_float(value: str, spec: str) -> str:
    try:
        return format(float(value), spec)
    except (TypeError, ValueError):
        return "-"


def _asked_panel(row: dict[str, str]) -> None:
    """What the extractor said the place was — the thing being matched against."""
    import streamlit as st

    st.subheader("What was asked for")
    st.markdown(f"### {row.get('location_text', '') or '(no location text)'}")

    bits = []
    if row.get("country_hint"):
        bits.append(f"**Country hint:** {row['country_hint']}")
    if row.get("extractor_admin_level"):
        bits.append(f"**Extractor called it:** {row['extractor_admin_level']}")
    if row.get("hazard"):
        bits.append(f"**Hazard:** {row['hazard']}")
    if bits:
        st.caption("  \n".join(bits))

    if row.get("title"):
        st.caption("From the document:")
        st.code(row["title"], language=None)

    url = row.get("content_url", "").strip()
    if url:
        st.link_button("Open source document", url)


def _returned_panel(row: dict[str, str]) -> None:
    """What Nominatim gave back."""
    import streamlit as st

    st.subheader("What Nominatim returned")
    st.markdown(f"**{row.get('resolution_display_name', '') or '(no display name)'}**")

    cols = st.columns(4)
    cols[0].metric("Admin level", row.get("resolution_admin_level", "") or "-")
    cols[1].metric("Source", row.get("resolution_geometry_source", "") or "-")
    cols[2].metric("Area (km²)", _fmt_float(row.get("area_km2", ""), ",.0f"))
    cols[3].metric("Confidence", _fmt_float(row.get("resolution_confidence", ""), ".2f"))

    flags = []
    fallback = row.get("resolution_used_fallback", "").strip()
    if fallback and fallback not in {"0", "0.0"}:
        flags.append(f"⚠️ fallback step {fallback} — the raw text did not resolve directly")
    if row.get("geometry_overshoot", "").strip().lower() in {"true", "1"}:
        flags.append("⚠️ overshoot — the shape is far larger than the extractor's tier implies")
    postprocess = row.get("geometry_postprocess", "").strip()
    if postprocess and postprocess != "unchanged":
        pre = _fmt_float(row.get("geometry_pre_postprocess_area_km2", ""), ",.0f")
        flags.append(f"✂️ postprocess `{postprocess}` — was {pre} km² before")
    for flag in flags:
        st.warning(flag)

    query = row.get("resolution_query", "") or "-"
    st.caption(f"**Query sent to Nominatim:** `{query}`")

    if query != "-":
        search = urllib.parse.quote(query)
        st.link_button(
            "Check this query on Nominatim ↗",
            f"https://nominatim.openstreetmap.org/ui/search.html?q={search}&polygon_geojson=1",
        )


def _map_panel(row: dict[str, str]) -> None:
    import streamlit as st
    import streamlit.components.v1 as components

    st.subheader("The shape it drew")
    try:
        html = build_map_html(row)
    except Exception as exc:  # a bad geometry must not kill the review session
        st.error(f"Could not render this geometry: {exc}")
        return

    if html is None:
        st.info("This row carries no geometry. Mark it N with failure_mode = other.")
        return

    components.html(html, height=470, scrolling=False)


def _review_form(row: dict[str, str], row_index: int) -> dict[str, str] | None:
    import streamlit as st

    st.subheader("Does the shape correspond?")
    widget_key = row.get("uuid", "").strip() or str(row_index)

    verdict_idx = VERDICT_OPTIONS.index(
        normalize_choice(row.get("geometry_correct", ""), VERDICT_OPTIONS)
    )
    mode_idx = FAILURE_MODES.index(
        normalize_choice(row.get("failure_mode", ""), FAILURE_MODES)
    )

    with st.form(f"review_form_{widget_key}", clear_on_submit=False):
        geometry_correct = st.radio(
            "geometry_correct",
            VERDICT_OPTIONS,
            index=verdict_idx,
            horizontal=True,
            format_func=lambda x: "blank" if x == "" else x,
            key=f"verdict_{widget_key}",
        )
        st.caption("  \n".join(f"**{k}** — {v}" for k, v in VERDICT_HELP.items()))

        failure_mode = st.selectbox(
            "failure_mode — leave blank when the verdict is Y",
            FAILURE_MODES,
            index=mode_idx,
            format_func=lambda x: "blank" if x == "" else x,
            key=f"mode_{widget_key}",
        )
        with st.expander("What the failure modes mean"):
            st.markdown(FAILURE_MODE_HELP)

        notes = st.text_area(
            "notes — what the right shape would have been",
            value=row.get("notes", ""),
            height=120,
            key=f"notes_{widget_key}",
        )

        submitted = st.form_submit_button("Save & Next", type="primary")

    if not submitted:
        return None

    return {
        "geometry_correct": geometry_correct,
        "failure_mode": failure_mode,
        "notes": notes.strip(),
    }


def _navigation(path: Path, rows: list[dict[str, str]]) -> None:
    import streamlit as st

    row_count = len(rows)
    current = st.session_state.row_index
    blank = remaining_blank_count(rows)
    done = row_count - blank

    st.sidebar.header("Progress")
    st.sidebar.progress(0 if row_count == 0 else done / row_count)
    st.sidebar.write(f"{done} / {row_count} reviewed · {blank} left")

    tally = verdict_tally(rows)
    if done:
        st.sidebar.divider()
        cols = st.sidebar.columns(3)
        cols[0].metric("Y", tally["Y"])
        cols[1].metric("Partial", tally["Partial"])
        cols[2].metric("N", tally["N"])
        st.sidebar.caption(f"Running rate: {tally['Y'] / done:.0%} fully correct")

    st.sidebar.divider()
    jump_to = st.sidebar.number_input(
        "Jump to row",
        min_value=1,
        max_value=max(1, row_count),
        value=min(current + 1, max(1, row_count)),
        step=1,
    )
    if st.sidebar.button("Go to row"):
        _set_row_index(int(jump_to) - 1, rows)
        st.rerun()

    nav_cols = st.sidebar.columns(2)
    if nav_cols[0].button("Previous", disabled=current <= 0):
        _set_row_index(current - 1, rows)
        st.rerun()
    if nav_cols[1].button("Skip", disabled=current >= row_count - 1):
        _set_row_index(current + 1, rows)
        st.rerun()

    if st.sidebar.button("First blank"):
        _set_row_index(first_blank_index(rows), rows)
        st.rerun()

    backup_key = f"backup_path::{path.resolve()}"
    if backup_key in st.session_state:
        st.sidebar.divider()
        st.sidebar.caption(f"Editing: {path}")
        st.sidebar.caption(f"Backup: {st.session_state[backup_key]}")


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Geometry Resolution Reviewer", layout="wide")
    st.title("Geometry Resolution Reviewer")
    st.caption(
        "One question only: given the location text, did Nominatim return the right "
        "shape? Judge the resolver, not the extractor — a location that should never "
        "have been extracted still scores Y if it was mapped faithfully."
    )

    path = resolve_csv_path()
    try:
        _ensure_session_backup(path)
        fieldnames, rows = _load_state(path)
    except SampleCsvError as exc:
        st.error(str(exc))
        st.stop()

    if not rows:
        st.warning(f"No rows found in {path}.")
        st.stop()

    _navigation(path, rows)
    row_index = st.session_state.row_index
    row = rows[row_index]

    verdict = row.get(PRIMARY_LABEL, "").strip()
    st.caption(
        f"Review {row.get('review_id', row_index + 1)} · "
        f"row {row_index + 1} of {len(rows)}"
        + (f" · already marked **{verdict}**" if verdict else "")
    )

    left, mid, right = st.columns([1.0, 1.15, 1.0], gap="large")
    with left:
        _asked_panel(row)
        st.divider()
        _returned_panel(row)
    with mid:
        _map_panel(row)
    with right:
        values = _review_form(row, row_index)

    if values is not None:
        _save_current_row(
            path=path,
            fieldnames=fieldnames,
            rows=rows,
            row_index=row_index,
            values=values,
        )
        _set_row_index(row_index + 1, rows)
        st.success("Saved.")
        st.rerun()


if __name__ == "__main__":
    main()
