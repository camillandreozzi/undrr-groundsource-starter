"""benchmark_ner/geocode_preflight.py — size the Nominatim run before launching it.

Geocoding is the long pole of this benchmark. The public endpoint is throttled
to ~1.1 s per request, and the NER baseline emits more distinct location
strings than the LLM run's 5,463. This script answers the only question that
matters before starting: **how many of those lookups are already cached?**

It reuses the real machinery — `explode_extractions` for the (asset, location)
pairs, `fallback_ladder` for the query the resolver would actually send, and
`NominatimResolver._cache_key` for the key it would look under — so the count
reflects what the resolver will do, not an approximation of it.

    python benchmark_ner/geocode_preflight.py \
        --input benchmark_ner/outputs/ner_extractions.jsonl

Note: reading the 583 MB cache takes a minute and a few GB of RAM.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from fonte.polygon_resolver import NominatimResolver, fallback_ladder
from fonte.run_polygon_resolution import explode_extractions

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "benchmark_ner" / "outputs" / "ner_extractions.jsonl"
DEFAULT_CACHE = REPO_ROOT / ".nominatim_cache.json"

LOG = logging.getLogger("benchmark_ner.preflight")

# Nominatim's usage policy, as enforced by NominatimResolver.min_interval_s.
SECONDS_PER_REQUEST = 1.1


def _cache_keys(cache_path: Path) -> set[str]:
    if not cache_path.exists():
        LOG.warning("No cache at %s — every lookup will hit the network.", cache_path)
        return set()
    LOG.info("Reading cache %s (%.0f MB)...", cache_path, cache_path.stat().st_size / 1e6)
    with cache_path.open() as fh:
        return set(json.load(fh).keys())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                   help="An event_extractions-schema JSONL.")
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    if not args.input.exists():
        LOG.error("Input not found: %s", args.input)
        return 1

    rows = list(explode_extractions(args.input))
    pairs = {(r["location_text"], r["country_hint"]) for r in rows}
    LOG.info("%d (asset, location) pairs -> %d distinct (location, country_hint)",
             len(rows), len(pairs))

    keys = _cache_keys(args.cache)
    # A shim purely to reach the private key format the resolver uses; no
    # network, no cache file of its own.
    keyer = NominatimResolver(user_agent="preflight/0.1 (undrr benchmark)", cache_path=None)

    cached_first_step = 0
    fully_uncached = 0
    for text, hint in pairs:
        ladder = fallback_ladder(text)
        if not ladder:
            continue
        first_q, override, _ = ladder[0]
        effective = override if override is not None else hint
        if keyer._cache_key(first_q, effective) in keys:
            cached_first_step += 1
        elif not any(
            keyer._cache_key(q, (ov if ov is not None else hint)) in keys
            for q, ov, _ in ladder
        ):
            fully_uncached += 1

    partly = len(pairs) - cached_first_step - fully_uncached
    # Each uncached location costs at least one request, and more if the ladder
    # has to descend — so this is a floor, not an estimate.
    min_requests = fully_uncached + partly
    hours = min_requests * SECONDS_PER_REQUEST / 3600

    print()
    print(f"distinct locations            {len(pairs):>8,}")
    print(f"  first ladder step cached    {cached_first_step:>8,}  (free)")
    print(f"  partially cached            {partly:>8,}")
    print(f"  no ladder step cached       {fully_uncached:>8,}")
    print()
    print(f"minimum network requests      {min_requests:>8,}")
    print(f"minimum wall clock at {SECONDS_PER_REQUEST}s/req  {hours:>7.1f} h")
    print()
    print("This is a floor: a location whose first ladder step misses costs one")
    print("request per additional step tried. Use fonte-polygons --limit")
    print("for a first pass if the number is large.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
