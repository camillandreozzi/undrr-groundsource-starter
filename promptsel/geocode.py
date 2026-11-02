"""Geocode every record of every run on the 80 windows, once per distinct place.

    python -m promptsel.geocode --preflight                       # how much is cached? writes nothing
    python -m promptsel.geocode --resolve --user-agent "..."      # -> promptsel/geocode/resolutions.csv

This is the production geocoder (`fonte.polygon_resolver.NominatimResolver`,
production defaults) applied the way `fonte-polygons` applies it: the same
(asset, location) explosion, the same country hint, the same confidence score
and overshoot cap. What differs is bookkeeping only:

  pairs        `explode_rows` is `explode_extractions` keeping `event_index`, so
               a location can be traced back to the record it came from. A guard
               checks it yields exactly production's rows on every run file.
  once         each distinct (location, country hint) is resolved once and the
               result is shared by every run, so geocoder variance cannot differ
               between prompts.
  cache        the 622 MB root `.nominatim_cache.json` is only ever read. The
               keys the resolver will look up are copied to a local cache
               (`promptsel/geocode/nominatim_cache.json`, gitignored), and only
               that file is written; a cache miss goes to the public endpoint.
  record       `resolutions.csv` keeps every field the confidence score reads,
               without geometry, so the scorer needs neither the network nor
               the cache, and the result is pinned in git.

Geocoding success here is the resolver's own success and confidence. Nobody
has judged these geometries; success is not correctness.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT / "src", REPO_ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from ablation.runner import read_windows  # noqa: E402
from ablation.score_ablation import AZURE, SEPTEMBER  # noqa: E402
from fonte.geometry_postprocess import is_sub_national_hazard  # noqa: E402
from fonte.polygon_resolver import NominatimResolver  # noqa: E402
from fonte.run_polygon_resolution import (  # noqa: E402
    _country_hint_from_countries, _split_pipes, confidence_score, explode_extractions,
)
from promptsel.configs import CONFIGS  # noqa: E402
from promptsel.runner import GEOCODE, RUNS  # noqa: E402

LOG = logging.getLogger("promptsel.geocode")

GEO_DIR = REPO_ROOT / "promptsel" / "geocode"
RESOLUTIONS = GEO_DIR / "resolutions.csv"
CACHE_MANIFEST = GEO_DIR / "cache_manifest.json"
LOCAL_CACHE = GEO_DIR / "nominatim_cache.json"
ROOT_CACHE = REPO_ROOT / ".nominatim_cache.json"
ABLATION_RUNS = REPO_ROOT / "ablation" / "runs"
SECONDS_PER_REQUEST = GEOCODE["min_interval_s"]
BAND = tuple(GEOCODE["band"])
WIDE = (BAND[0], 1.0)                       # sensitivity S5: no upper bound

RESOLUTION_FIELDS = (
    "location_text", "country_hint", "resolved", "query", "used_fallback", "osm_type",
    "admin_level", "geometry_source", "is_polygon", "is_country_fallback", "importance",
    "display_name", "error", "fetched_from",
)


class GeocodeError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Which runs, which pairs
# ---------------------------------------------------------------------------

def run_inputs(runs_root: Path = RUNS) -> list[tuple[str, Path]]:
    """Every run the scorer reads: this experiment's, Experiment B's `full`, the references."""
    out = []
    for config in CONFIGS:
        for path in sorted((runs_root / config).glob("r*/*/event_extractions.jsonl")):
            out.append((f"{config} {path.parent.parent.name}", path))
    for path in sorted((ABLATION_RUNS / "full").glob("r*/*/event_extractions.jsonl")):
        out.append((f"Exp B full {path.parent.parent.name}", path))
    out += [(SEPTEMBER[0], SEPTEMBER[1]), (AZURE[0], AZURE[1])]
    return [(label, path) for label, path in out if path.exists()]


def explode_rows(jsonl_path: Path) -> list[dict]:
    """`explode_extractions`, line for line, with the record's `event_index` kept."""
    out = []
    with jsonl_path.open() as fh:
        for ln in fh:
            row = json.loads(ln)
            if not row.get("is_verifiable_event"):
                continue
            locs = _split_pipes(row.get("affected_locations"))
            if not locs:
                continue
            admin_levels = _split_pipes(row.get("location_admin_levels"))
            if len(admin_levels) < len(locs):
                admin_levels = admin_levels + ["unknown"] * (len(locs) - len(admin_levels))
            elif len(admin_levels) > len(locs):
                admin_levels = admin_levels[: len(locs)]
            event_dates_raw = (row.get("event_dates") or "").strip()
            dates = sorted(_split_pipes(event_dates_raw))
            if not dates:
                continue
            countries_raw = (row.get("countries") or "").strip()
            country_hint = _country_hint_from_countries(countries_raw)
            for loc, lvl in zip(locs, admin_levels):
                out.append({
                    "asset_key": row.get("asset_key"),
                    "title": row.get("title"),
                    "content_url": row.get("content_url"),
                    "hazard": row.get("event_hazard"),
                    "location_text": loc,
                    "extractor_admin_level": lvl,
                    "country_hint": country_hint,
                    "countries_raw": countries_raw,
                    "start_date": dates[0],
                    "end_date": dates[-1],
                    "event_dates_raw": event_dates_raw,
                    "event_index": row.get("event_index"),
                })
    return out


def check_explosion(jsonl_path: Path, rows: list[dict] | None = None) -> None:
    """Refuse unless `explode_rows` minus `event_index` is production's explosion."""
    rows = explode_rows(jsonl_path) if rows is None else rows
    mine = [{k: v for k, v in r.items() if k != "event_index"} for r in rows]
    if mine != list(explode_extractions(jsonl_path)):
        raise GeocodeError(f"{jsonl_path}: explode_rows differs from explode_extractions")


def window_pairs(inputs: list[tuple[str, Path]], keys: set[str] | None = None,
                 check: bool = True) -> dict[str, list[dict]]:
    """label -> exploded rows on the frozen windows."""
    keys = keys if keys is not None else {w["asset_key"] for w in read_windows()}
    out = {}
    for label, path in inputs:
        rows = explode_rows(path)
        if check:
            check_explosion(path, rows)
        out[label] = [r for r in rows if r["asset_key"] in keys]
    return out


def distinct_pairs(by_run: dict[str, list[dict]]) -> list[tuple[str, str | None]]:
    pairs = {(r["location_text"], r["country_hint"]) for rows in by_run.values() for r in rows}
    return sorted(pairs, key=lambda p: (p[0], p[1] or ""))


# ---------------------------------------------------------------------------
# Cache: read the root, write only a local copy
# ---------------------------------------------------------------------------

class CacheMiss(Exception):
    pass


class OfflineResolver(NominatimResolver):
    """The production resolver answering from a dict; a miss raises instead of fetching.

    The ladder catches the miss and moves on, as it would a network error, so
    `touched` collects every key an online walk could need: on a miss it can
    only stop earlier, never visit a key the offline walk did not.
    """

    def __init__(self, cache: dict):
        super().__init__(user_agent="promptsel-offline/0.1 (undrr prompt selection)",
                         cache_path=None)
        self._cache = cache
        self.touched: set[str] = set()
        self.missing: set[str] = set()

    def _search_one(self, q, country_hint):
        key = self._cache_key(q, country_hint)
        self.touched.add(key)
        if key in self._cache:
            cached = self._cache[key]
            return cached if cached else None
        self.missing.add(key)
        raise CacheMiss(key)


def _stat(path: Path) -> tuple[int, int]:
    st = path.stat()
    return st.st_size, st.st_mtime_ns


def load_root_cache(path: Path = ROOT_CACHE) -> dict:
    if not path.exists():
        LOG.warning("No cache at %s; every lookup will hit the network.", path)
        return {}
    LOG.info("Reading %s (%.0f MB) read-only...", path, path.stat().st_size / 1e6)
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@dataclass
class Walk:
    touched: set[str]
    missing: set[str]
    uncached_pairs: list[tuple[str, str | None]]


def offline_walk(pairs: list[tuple[str, str | None]], cache: dict) -> Walk:
    resolver = OfflineResolver(cache)
    uncached = []
    quiet = logging.getLogger("fonte.polygon_resolver")
    level = quiet.level
    quiet.setLevel(logging.ERROR)              # each miss would log a "Nominatim error"
    try:
        for text, hint in pairs:
            before = len(resolver.missing)
            resolver.resolve(text, country_hint=hint)
            if len(resolver.missing) > before:
                uncached.append((text, hint))
    finally:
        quiet.setLevel(level)
    return Walk(resolver.touched, resolver.missing, uncached)


def seed_local_cache(root: dict, walk: Walk, root_path: Path = ROOT_CACHE,
                     local_path: Path = LOCAL_CACHE, root_stat=None) -> dict:
    """Copy the keys the walk touched into the local cache. The root is never written."""
    if local_path.resolve() == root_path.resolve():
        raise GeocodeError("the local cache must not be the root cache")
    local = {}
    if local_path.exists():
        local = json.loads(local_path.read_text(encoding="utf-8"))
    copied = {k: root[k] for k in sorted(walk.touched) if k in root and k not in local}
    local.update(copied)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(json.dumps(local), encoding="utf-8")
    if root_path.exists() and root_stat is not None and _stat(root_path) != root_stat:
        raise GeocodeError(f"{root_path} changed while seeding")
    return {
        "root_bytes": root_stat[0] if root_stat else None,
        "root_mtime_ns": root_stat[1] if root_stat else None,
        "root_keys": len(root),
        "keys_touched": len(walk.touched),
        "keys_copied": len(copied),
        "keys_missing_from_root": len(walk.missing),
        "local_keys": len(local),
    }


# ---------------------------------------------------------------------------
# Resolution records and confidence
# ---------------------------------------------------------------------------

def resolution_row(text: str, hint: str | None, res, fetched_from: str) -> dict:
    return {
        "location_text": text,
        "country_hint": hint or "",
        "resolved": int(res.resolved),
        "query": res.query,
        "used_fallback": res.used_fallback,
        "osm_type": res.osm_type or "",
        "admin_level": res.admin_level or "",
        "geometry_source": res.geometry_source or "",
        # From the live result: a bbox hit is a shapely Polygon, so it counts too.
        "is_polygon": int(res.is_polygon),
        "is_country_fallback": int(bool(res.is_country_fallback)),
        "importance": "" if res.importance is None else repr(float(res.importance)),
        "display_name": res.display_name or "",
        "error": res.error or "",
        "fetched_from": fetched_from,
    }


def resolve_pairs(pairs: list[tuple[str, str | None]], user_agent: str,
                  local_path: Path = LOCAL_CACHE, resolver=None) -> list[dict]:
    resolver = resolver or NominatimResolver(user_agent=user_agent, cache_path=local_path)
    rows = []
    try:
        for i, (text, hint) in enumerate(pairs, 1):
            before = len(resolver._cache)
            res = resolver.resolve(text, country_hint=hint)
            rows.append(resolution_row(text, hint, res,
                                       "network" if len(resolver._cache) > before else "cache"))
            if i % 25 == 0:
                resolver.flush_cache()
                LOG.info("[%d/%d] resolved=%d", i, len(pairs), sum(r["resolved"] for r in rows))
    finally:
        resolver.flush_cache()
    return rows


def write_resolutions(rows: list[dict], path: Path = RESOLUTIONS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESOLUTION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def load_resolutions(path: Path = RESOLUTIONS) -> dict[tuple[str, str], dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return {(r["location_text"], r["country_hint"]): r for r in csv.DictReader(f)}


def pair_key(row: dict) -> tuple[str, str]:
    return row["location_text"], row["country_hint"] or ""


def pair_confidence(res: dict, hazard: str | None, extractor_admin_level: str | None
                    ) -> tuple[float, bool]:
    """(resolution_confidence, overshoot) exactly as `fonte-polygons` computes them."""
    shim = SimpleNamespace(
        resolved=res["resolved"] in (1, "1"),
        is_country_fallback=res["is_country_fallback"] in (1, "1"),
        importance=float(res["importance"]) if res["importance"] != "" else None,
        is_polygon=res["is_polygon"] in (1, "1"),
        used_fallback=int(res["used_fallback"]),
    )
    overshoot = shim.resolved and is_sub_national_hazard(hazard) and (
        (extractor_admin_level or "").lower() == "country" or res["admin_level"] == "country")
    return confidence_score(shim, geometry_overshoot=overshoot), bool(overshoot)


def in_band(conf: float, band=BAND) -> bool:
    return band[0] <= conf <= band[1]


# ---------------------------------------------------------------------------
# Per-window counts
# ---------------------------------------------------------------------------

GEO_COUNTERS = (
    "geo_pairs", "geo_resolved", "geo_conf_sum", "geo_resolved_valid",
    "geo_inband", "geo_inband_conf_sum", "geo_inband_valid", "geo_inband_complete",
    "geo_inband_locok", "geo_wide", "geo_wide_valid", "geo_overshoot", "geo_country_fallback",
    "geo_rec", "geo_rec_inband", "geo_rec_inband_valid", "geo_win_inband",
)


@dataclass(frozen=True)
class RecordStatus:
    valid: bool          # linked to a gold event under the reading
    complete: bool       # ... and every field of the link correct
    location_ok: bool    # ... and its places correct


def statuses_from_rows(rows: list[dict]) -> dict[int, RecordStatus]:
    """event_index -> status, from one run's `score_window` rows on one window and reading."""
    out: dict[int, RecordStatus] = {}
    for r in rows:
        if r["status"] not in ("matched", "false_positive"):
            continue
        idx = int(r["event_index"])
        if idx in out:
            raise GeocodeError(f"{r['asset_key'][:12]} event {idx} has two statuses")
        matched = r["status"] == "matched"
        out[idx] = RecordStatus(matched, matched and bool(r.get("complete")),
                                matched and bool(r.get("ok_location")))
    return out


def geo_window_counts(pairs: list[dict], statuses: dict[int, RecordStatus],
                      resolutions: dict[tuple[str, str], dict]) -> tuple[dict, list[dict]]:
    """Counts for one run on one window and reading, and one audit row per pair."""
    c = dict.fromkeys(GEO_COUNTERS, 0)
    audit = []
    per_record: dict[int, list[bool]] = {}
    for p in pairs:
        idx = int(p["event_index"])
        if idx not in statuses:
            raise GeocodeError(f"{p['asset_key'][:12]} event {idx} was not scored")
        status = statuses[idx]
        res = resolutions.get(pair_key(p))
        if res is None:
            raise GeocodeError(f"no resolution for {pair_key(p)!r}; run make promptsel-geocode")
        conf, overshoot = pair_confidence(res, p["hazard"], p["extractor_admin_level"])
        resolved = res["resolved"] in (1, "1")
        band, wide = resolved and in_band(conf), resolved and in_band(conf, WIDE)
        c["geo_pairs"] += 1
        if resolved:
            c["geo_resolved"] += 1
            c["geo_conf_sum"] += conf
            c["geo_resolved_valid"] += status.valid
            c["geo_overshoot"] += overshoot
            c["geo_country_fallback"] += res["is_country_fallback"] in (1, "1")
        if band:
            c["geo_inband"] += 1
            c["geo_inband_conf_sum"] += conf
            c["geo_inband_valid"] += status.valid
            c["geo_inband_complete"] += status.complete
            c["geo_inband_locok"] += status.location_ok
        if wide:
            c["geo_wide"] += 1
            c["geo_wide_valid"] += status.valid
        per_record.setdefault(idx, []).append(band)
        audit.append({"asset_key": p["asset_key"], "event_index": idx,
                      "location_text": p["location_text"], "country_hint": p["country_hint"] or "",
                      "hazard": p["hazard"], "start_date": p["start_date"],
                      "end_date": p["end_date"], "resolved": int(resolved),
                      "confidence": round(conf, 6), "in_band": int(band),
                      "overshoot": int(overshoot), "valid": int(status.valid)})
    c["geo_rec"] = len(per_record)
    c["geo_rec_inband"] = sum(any(b) for b in per_record.values())
    c["geo_rec_inband_valid"] = sum(any(b) and statuses[i].valid for i, b in per_record.items())
    c["geo_win_inband"] = int(c["geo_inband"] > 0)
    return c, audit


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--preflight", action="store_true", help="count uncached lookups; no writes")
    g.add_argument("--resolve", action="store_true",
                   help="seed the local cache, resolve every pair, write resolutions.csv")
    p.add_argument("--user-agent", default=None, help="required with --resolve")
    p.add_argument("--offline", action="store_true",
                   help="with --resolve: no network and no cache writes; a pair that would need "
                        "a request is recorded unresolved (rehearsal only)")
    p.add_argument("--runs-root", type=Path, default=RUNS)
    p.add_argument("--root-cache", type=Path, default=ROOT_CACHE)
    p.add_argument("--resolutions", type=Path, default=RESOLUTIONS)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    inputs = run_inputs(args.runs_root)
    by_run = window_pairs(inputs)
    pairs = distinct_pairs(by_run)
    for label, rows in by_run.items():
        LOG.info("%-40s %4d (record, location) pairs on the windows", label, len(rows))
    LOG.info("%d distinct (location, country hint) over %d runs", len(pairs), len(by_run))

    root_stat = _stat(args.root_cache) if args.root_cache.exists() else None
    root = load_root_cache(args.root_cache)
    walk = offline_walk(pairs, root)
    hours = len(walk.missing) * SECONDS_PER_REQUEST / 3600
    print(f"distinct (location, hint)       {len(pairs):>6,}")
    print(f"  answered from the root cache  {len(pairs) - len(walk.uncached_pairs):>6,}")
    print(f"  need >= 1 network request     {len(walk.uncached_pairs):>6,}")
    print(f"distinct uncached ladder keys   {len(walk.missing):>6,}  (upper bound on requests,"
          f" {hours:.2f} h at {SECONDS_PER_REQUEST}s)")
    if args.preflight:
        for text, hint in walk.uncached_pairs[:40]:
            print(f"  uncached: {text!r} [{hint or '-'}]")
        return 0
    if args.offline:
        uncached = set(walk.uncached_pairs)
        offline = OfflineResolver(root)
        quiet = logging.getLogger("fonte.polygon_resolver")
        quiet.setLevel(logging.ERROR)
        rows = [resolution_row(t, h, offline.resolve(t, country_hint=h),
                               "uncached" if (t, h) in uncached else "cache") for t, h in pairs]
        write_resolutions(rows, args.resolutions)
        print(f"-> {args.resolutions} (offline: {len(uncached)} pair(s) recorded unresolved)")
        return 0

    if not args.user_agent:
        raise SystemExit("--resolve needs --user-agent (Nominatim policy)")
    seeded = seed_local_cache(root, walk, args.root_cache, LOCAL_CACHE, root_stat)
    del root
    rows = resolve_pairs(pairs, args.user_agent)
    if args.root_cache.exists() and root_stat is not None and _stat(args.root_cache) != root_stat:
        raise GeocodeError(f"{args.root_cache} changed during the run")
    write_resolutions(rows, args.resolutions)
    manifest = {
        "resolved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runs": [label for label, _ in inputs],
        "pairs": len(rows), "resolved": sum(r["resolved"] for r in rows),
        "fetched_from_network": sum(r["fetched_from"] == "network" for r in rows),
        "seed": seeded,
        "local_cache_sha256": hashlib.sha256(LOCAL_CACHE.read_bytes()).hexdigest(),
        "resolutions_sha256": hashlib.sha256(args.resolutions.read_bytes()).hexdigest(),
        **{k: GEOCODE[k] for k in ("band", "cache_version", "allow_non_polygon",
                                   "min_interval_s", "endpoint")},
    }
    CACHE_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"-> {args.resolutions}: {manifest['resolved']}/{manifest['pairs']} "
          f"resolved, {manifest['fetched_from_network']} fetched from the network")
    return 0


if __name__ == "__main__":
    sys.exit(main())
