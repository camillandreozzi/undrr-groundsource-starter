"""Unit tests for Experiment D: configurations, runner, geocoding bookkeeping, scorer.

A retrospective comparison of prompts is only interpretable if p5 is exactly
what production and Experiment B ran, if p1-p4 differ from it by their text
alone, and if the geocoding rule is production's to the last branch. So the
first tests pin p5 to Experiment B's `full` and p1-p4 to `get_prompt(n)` with
the production schema; the geocoding tests check the explosion, the confidence
score and the band against production code; the scorer tests check the
parameterised bootstrap against Experiment B's and the reading rules cell by
cell.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
for extra in (REPO_ROOT, REPO_ROOT / "src", REPO_ROOT / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from shapely.geometry import Polygon, box  # noqa: E402

from ablation import configs as ablation_configs  # noqa: E402
from ablation.runner import SPEC, extract_one, load_progress, plan_jobs, run_dir  # noqa: E402
from ablation.score_ablation import ALL_COUNTERS, ALL_METRICS, _IDX, delta, estimate, shared_weights  # noqa: E402
from benchmark_openrouter.run_openrouter import extract_document  # noqa: E402
from fonte.app_event_focus import DocumentEventExtractions  # noqa: E402
from fonte.polygon_resolver import ResolutionResult  # noqa: E402
from fonte.prompts import get_prompt  # noqa: E402
from fonte.run_polygon_resolution import confidence_score, explode_extractions  # noqa: E402
from promptsel.configs import CONFIGS, build_config, check_prompts, manifest, rendered_files  # noqa: E402
from promptsel.geocode import (  # noqa: E402
    BAND, GEO_COUNTERS, GeocodeError, RecordStatus, check_explosion, explode_rows,
    geo_window_counts, in_band, load_resolutions, offline_walk, pair_confidence, resolution_row,
    seed_local_cache, statuses_from_rows, write_resolutions,
)
from promptsel.runner import JOB_SEED, frozen_hashes, run  # noqa: E402
from promptsel.score_promptsel import (  # noqa: E402
    COUNTERS_D, IDX_D, METRICS_D, _june_keyer, bridging_verdict, delta_with, estimate_with,
    named_with, selection_verdict, tradeoff_cell,
)
from test_ablation import FakeClient, doc  # noqa: E402

SHA16 = {"p1": "fc32dc937842cbbe", "p2": "817d7ac69ce27db3", "p3": "e04eead4d4dfa804",
         "p4": "7dc36a745e810ca0", "p5": "cfbf35634b527da4"}


# ---------------------------------------------------------------------------
# Configurations
# ---------------------------------------------------------------------------

class ConfigTests(unittest.TestCase):
    def test_p5_is_experiment_b_full(self):
        p5, full = build_config("p5"), ablation_configs.build_config("full")
        self.assertIs(p5.prompt, get_prompt(5))
        self.assertIs(p5.prompt, full.prompt)
        self.assertIs(p5.schema, DocumentEventExtractions)
        self.assertEqual(manifest(p5), {**manifest(full), "config": "p5"})

    def test_p5_renders_exactly_experiment_b_full(self):
        for fname, text in rendered_files(build_config("p5")).items():
            if fname != "manifest.json":
                full = REPO_ROOT / "ablation" / "prompts" / "full" / fname
                self.assertEqual(text, full.read_text(encoding="utf-8"), fname)

    def test_predecessors_are_the_registry_prompts_with_the_production_schema(self):
        for n, name in enumerate(("p1", "p2", "p3", "p4"), 1):
            cfg = build_config(name)
            self.assertIs(cfg.prompt, get_prompt(n))
            self.assertIs(cfg.schema, DocumentEventExtractions)

    def test_hashes_are_pinned(self):
        self.assertEqual({c: manifest(build_config(c))["system_sha16"] for c in CONFIGS}, SHA16)

    def test_only_the_text_varies(self):
        ms = [manifest(build_config(c)) for c in CONFIGS]
        self.assertEqual(len({m["schema_sha256"] for m in ms}), 1)
        self.assertEqual(len({m["system_sha256"] for m in ms}), len(CONFIGS))

    def test_rendered_prompts_are_in_sync(self):
        self.assertEqual(check_prompts(), [])

    def test_frozen_records_p5_as_full(self):
        self.assertTrue(frozen_hashes()["p5_equals_ablation_full"])


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class RunnerTests(unittest.TestCase):
    def test_every_prompt_sends_the_production_request(self):
        for name in CONFIGS:
            a, b = FakeClient(), FakeClient()
            extract_document(a, doc(), SPEC, get_prompt(int(name[1])), {})
            extract_one(b, doc(), SPEC, build_config(name))
            self.assertEqual(a.calls, b.calls, name)
        a, b = FakeClient(), FakeClient()
        extract_one(a, doc(), SPEC, ablation_configs.build_config("full"))
        extract_one(b, doc(), SPEC, build_config("p5"))
        self.assertEqual(a.calls, b.calls)

    def test_job_order_is_seeded_and_not_experiment_b_s(self):
        docs = [doc(k) for k in "abcdef"]
        with tempfile.TemporaryDirectory() as tmp:
            a = plan_jobs(list(CONFIGS), 2, docs, Path(tmp), seed=JOB_SEED)
            b = plan_jobs(list(CONFIGS), 2, docs, Path(tmp), seed=JOB_SEED)
            c = plan_jobs(list(CONFIGS), 2, docs, Path(tmp), seed=46)
        order = lambda jobs: [(j.config, j.rep, j.doc.asset_key) for j in jobs]  # noqa: E731
        self.assertEqual(order(a), order(b))
        self.assertNotEqual(order(a), order(c))
        self.assertEqual(len(a), len(CONFIGS) * 2 * 6)

    def test_run_sends_each_prompt_and_resumes(self):
        shared = FakeClient()
        docs = [doc("a"), doc("b")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run(["p1", "p5"], 1, docs, out_root=root, workers=2, client_factory=lambda: shared)
            systems = {c["messages"][0]["content"] for c in shared.calls}
            self.assertEqual(systems, {get_prompt(1).system_prompt, get_prompt(5).system_prompt})
            stats = json.loads((run_dir(root, "p1", 1) / "run_stats.json").read_text())
            self.assertEqual((stats["prompt_name"], stats["system_sha16"]),
                             ("baseline_strict_location", SHA16["p1"]))
            self.assertEqual(plan_jobs(["p1", "p5"], 1, docs, root, seed=JOB_SEED), [])

            d = run_dir(root, "p1", 1)
            with (d / "progress.jsonl").open("a") as f:
                f.write(json.dumps({"asset_key": "b", "error": True, "rows": []}) + "\n")
            pending = plan_jobs(["p1", "p5"], 1, docs, root, seed=JOB_SEED)
            self.assertEqual([(j.config, j.doc.asset_key) for j in pending], [("p1", "b")])
            run(["p1"], 1, docs, out_root=root, workers=1, client_factory=FakeClient)
            self.assertFalse(load_progress(d)["b"]["error"])


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def out_row(key, idx, *, verifiable=True, locations="Bangkok", levels="city", dates="2020",
            countries="Thailand", hazard="Flood"):
    return {"asset_key": key, "title": "t", "content_url": None, "event_index": idx,
            "is_verifiable_event": verifiable, "event_hazard": hazard, "event_dates": dates,
            "affected_locations": locations, "location_admin_levels": levels,
            "countries": countries}


EDGE_ROWS = [
    out_row("a", 1),
    out_row("a", 2, verifiable=False),
    out_row("a", 0, verifiable=None, locations=""),                       # no-event / error row
    out_row("b", 1, dates=""),                                            # no dates
    out_row("b", 2, locations="Kano | Lagos | Abuja", levels="city"),      # levels padded
    out_row("b", 3, locations="Kano", levels="city | admin1 | country"),  # levels truncated
    out_row("c", 1, countries=""),                                        # no hint
    out_row("c", 2, countries="Thailand, Viet Nam"),                      # two countries: no hint
    out_row("c", 3, dates="2020-01-05 | 2019 | 2021-03"),                 # date range
]


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def result(geometry=None, source=None, *, importance=0.6, fallback=0, country_fallback=False,
           admin="city"):
    return ResolutionResult(query="q", original="q", geometry=geometry,
                            admin_level=admin if geometry is not None else None,
                            osm_type="relation", display_name="d", importance=importance,
                            used_fallback=fallback, geometry_source=source,
                            is_country_fallback=country_fallback,
                            error=None if geometry is not None else "no match")


SQUARE = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
CASES = {
    "polygon": result(SQUARE, "polygon"),
    "bbox": result(box(0, 0, 1, 1), "bbox", importance=0.7),
    "country_fallback": result(SQUARE, "polygon", country_fallback=True, admin="country"),
    "two_fallbacks": result(SQUARE, "polygon", fallback=2),
    "importance_none": result(SQUARE, "polygon", importance=None),
    "importance_zero": result(SQUARE, "polygon", importance=0.0),
    "importance_high": result(SQUARE, "polygon", importance=0.9),
    "country_hit": result(SQUARE, "polygon", admin="country"),
    "unresolved": result(),
}


class ExplosionTests(unittest.TestCase):
    def test_explode_rows_is_production_plus_event_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_jsonl(Path(tmp) / "x.jsonl", EDGE_ROWS)
            rows = explode_rows(path)
            check_explosion(path, rows)                       # raises on any difference
            self.assertEqual(len(rows), len(list(explode_extractions(path))))
            self.assertEqual([(r["asset_key"], r["event_index"]) for r in rows],
                             [("a", 1), ("b", 2), ("b", 2), ("b", 2), ("b", 3),
                              ("c", 1), ("c", 2), ("c", 3)])
            self.assertEqual([r["extractor_admin_level"] for r in rows if r["event_index"] == 2
                              and r["asset_key"] == "b"], ["city", "unknown", "unknown"])
            self.assertEqual([r["country_hint"] for r in rows if r["asset_key"] == "c"],
                             [None, None, "th"])

    def test_a_divergent_explosion_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_jsonl(Path(tmp) / "x.jsonl", EDGE_ROWS)
            rows = explode_rows(path)
            rows[0]["location_text"] = "Chiang Mai"
            with self.assertRaises(GeocodeError):
                check_explosion(path, rows)


class ConfidenceTests(unittest.TestCase):
    def roundtrip(self) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.csv"
            write_resolutions([resolution_row(name, None, res, "cache")
                               for name, res in CASES.items()], path)
            return load_resolutions(path)

    def test_confidence_survives_the_csv(self):
        stored = self.roundtrip()
        for name, res in CASES.items():
            for hazard, level in (("Flood", "city"), ("Earthquake", "city"),
                                  ("Earthquake", "country"), ("Flood", "country")):
                overshoot = res.resolved and hazard == "Earthquake" and (
                    level == "country" or res.admin_level == "country")
                want = confidence_score(res, geometry_overshoot=overshoot)
                got, flag = pair_confidence(stored[(name, "")], hazard, level)
                self.assertEqual(got, want, (name, hazard, level))
                self.assertEqual(flag, bool(overshoot), (name, hazard, level))

    def test_a_bbox_hit_counts_as_a_polygon_as_in_production(self):
        self.assertEqual(self.roundtrip()[("bbox", "")]["is_polygon"], "1")

    def test_overshoot_caps_sub_national_hazards_only(self):
        stored = self.roundtrip()[("polygon", "")]
        self.assertEqual(pair_confidence(stored, "Earthquake", "country")[0], 0.15)
        self.assertGreater(pair_confidence(stored, "Flood", "country")[0], 0.15)

    def test_band_edges_are_inclusive_as_in_june(self):
        values = [0.6999, 0.70, 0.85, 0.98, 0.9801]
        self.assertEqual([in_band(v) for v in values], [False, True, True, True, False])
        june = pd.Series(values).between(BAND[0], BAND[1], inclusive="both").tolist()
        self.assertEqual([in_band(v) for v in values], june)


class CacheTests(unittest.TestCase):
    HIT = {"geojson": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1],
                                                           [0, 0]]]},
           "importance": 0.5, "addresstype": "city", "osm_type": "relation", "display_name": "B"}

    def root(self):
        from fonte.polygon_resolver import NominatimResolver
        key = NominatimResolver(user_agent="t/0.1 (test)", cache_path=None)._cache_key
        # "Bangkok" misses under the wrong hint and hits without one.
        return {key("Bangkok", "dz"): {}, key("Bangkok", None): self.HIT}, key

    def test_the_no_hint_retry_is_seeded_and_the_root_is_never_written(self):
        root, key = self.root()
        walk = offline_walk([("Bangkok", "dz"), ("Lagos", None)], root)
        self.assertIn(key("Bangkok", None), walk.touched)
        self.assertEqual(walk.uncached_pairs, [("Lagos", None)])
        self.assertEqual(walk.missing, {key("Lagos", None)})
        with tempfile.TemporaryDirectory() as tmp:
            root_path, local = Path(tmp) / "root.json", Path(tmp) / "local" / "cache.json"
            root_path.write_text(json.dumps(root))
            before = root_path.read_bytes()
            from promptsel.geocode import _stat
            info = seed_local_cache(root, walk, root_path, local, _stat(root_path))
            self.assertEqual(root_path.read_bytes(), before)
            self.assertEqual(set(json.loads(local.read_text())), set(root))
            self.assertEqual((info["keys_copied"], info["keys_missing_from_root"]), (2, 1))
            with self.assertRaises(GeocodeError):
                seed_local_cache(root, walk, root_path, root_path, _stat(root_path))

    def test_offline_resolution_matches_the_cached_hit(self):
        root, _key = self.root()
        from promptsel.geocode import OfflineResolver
        res = OfflineResolver(root).resolve("Bangkok", country_hint="dz")
        self.assertTrue(res.resolved)
        self.assertEqual((res.query, res.used_fallback, res.importance), ("Bangkok", 0, 0.5))


class GeoCountTests(unittest.TestCase):
    def resolutions(self):
        return {("In", ""): resolution_row("In", None, result(SQUARE, "polygon", importance=0.6),
                                           "cache"),
                ("Low", ""): resolution_row("Low", None, result(SQUARE, "polygon", importance=0.1),
                                            "cache"),
                ("Top", ""): resolution_row("Top", None, result(SQUARE, "polygon", importance=0.9),
                                            "cache"),
                ("None", ""): resolution_row("None", None, result(), "cache")}

    def pairs(self, places: list[tuple[int, str]]):
        return [{"asset_key": "k", "event_index": i, "location_text": loc, "country_hint": None,
                 "hazard": "Flood", "extractor_admin_level": "city", "start_date": "2020",
                 "end_date": "2020"} for i, loc in places]

    def test_valid_and_invalid_add_up_to_the_band(self):
        statuses = {1: RecordStatus(True, True, False), 2: RecordStatus(False, False, False)}
        c, audit = geo_window_counts(
            self.pairs([(1, "In"), (1, "Low"), (1, "None"), (2, "In"), (2, "Top")]),
            statuses, self.resolutions())
        self.assertEqual((c["geo_pairs"], c["geo_resolved"], c["geo_inband"]), (5, 4, 2))
        self.assertEqual((c["geo_inband_valid"], c["geo_inband_complete"], c["geo_inband_locok"]),
                         (1, 1, 0))
        self.assertEqual((c["geo_wide"], c["geo_wide_valid"]), (3, 1))
        self.assertEqual((c["geo_rec"], c["geo_rec_inband"], c["geo_rec_inband_valid"]), (2, 2, 1))
        self.assertEqual(c["geo_win_inband"], 1)
        self.assertEqual(set(c), set(GEO_COUNTERS))
        self.assertEqual(len(audit), 5)

    def test_every_pair_needs_a_scored_record_and_a_resolution(self):
        with self.assertRaises(GeocodeError):
            geo_window_counts(self.pairs([(3, "In")]), {}, self.resolutions())
        with self.assertRaises(GeocodeError):
            geo_window_counts(self.pairs([(1, "Nowhere")]),
                              {1: RecordStatus(True, True, True)}, self.resolutions())

    def test_statuses_come_from_the_scorer_rows(self):
        rows = [{"asset_key": "k", "status": "matched", "event_index": 1, "complete": 1,
                 "ok_location": 0},
                {"asset_key": "k", "status": "false_positive", "event_index": 2, "complete": 0},
                {"asset_key": "k", "status": "false_negative", "gold_event_id": 3}]
        self.assertEqual(statuses_from_rows(rows), {1: RecordStatus(True, True, False),
                                                    2: RecordStatus(False, False, False)})
        with self.assertRaises(GeocodeError):
            statuses_from_rows(rows + rows[:1])


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

def d(point, lo, hi):
    return {"point": point, "lo": lo, "hi": hi}


UP, DOWN, FLAT = d(0.1, 0.02, 0.2), d(-0.1, -0.2, -0.02), d(0.0, -0.05, 0.05)


class BootstrapTests(unittest.TestCase):
    def test_parameterised_bootstrap_is_experiment_b_s(self):
        rng = np.random.default_rng(0)
        a = rng.integers(0, 5, size=(12, len(ALL_COUNTERS))).astype(float)
        b = rng.integers(0, 5, size=(12, len(ALL_COUNTERS))).astype(float)
        w = shared_weights([str(i) for i in range(12)], None, "all")
        mine = estimate_with(a, w, _IDX, ALL_METRICS)
        theirs = estimate(a, w)
        for name in ALL_METRICS:
            np.testing.assert_equal(mine[name], theirs[name], name)
        mine, theirs = delta_with(a, b, w, _IDX, ALL_METRICS), delta(a, b, w)
        for name in ALL_METRICS:
            np.testing.assert_equal(mine[name], theirs[name], name)

    def test_combined_layout_keeps_experiment_b_s_counters_first(self):
        self.assertEqual(COUNTERS_D[:len(ALL_COUNTERS)], ALL_COUNTERS)
        self.assertEqual(COUNTERS_D[len(ALL_COUNTERS):], GEO_COUNTERS)

    def test_metrics_read_only_kept_counters(self):
        totals = named_with(np.ones(len(COUNTERS_D)), IDX_D)
        for name, fn in METRICS_D.items():
            fn(totals)      # a KeyError here is a metric reading a counter that is not kept

    def test_a_prompt_against_itself_is_zero(self):
        rng = np.random.default_rng(1)
        m = rng.integers(0, 5, size=(10, len(COUNTERS_D))).astype(float)
        w = shared_weights([str(i) for i in range(10)], None, "all")
        for name, e in delta_with(m, m, w).items():
            if e["point"] == e["point"]:
                self.assertEqual((e["point"], e["lo"], e["hi"]), (0.0, 0.0, 0.0), name)


class ReadingRuleTests(unittest.TestCase):
    def test_all_nine_cells(self):
        want = [
            ((DOWN, DOWN), "p5 dominates"),
            ((DOWN, FLAT), "p5 more precise, no detectable recall cost"),
            ((DOWN, UP), "trade-off: p5 trades recall for precision"),
            ((FLAT, DOWN), "p5 higher recall, no detectable precision cost"),
            ((FLAT, FLAT), "not distinguishable"),
            ((FLAT, UP), "pk higher recall, no detectable precision cost"),
            ((UP, DOWN), "trade-off: p5 trades precision for recall"),
            ((UP, FLAT), "pk more precise, no detectable recall cost"),
            ((UP, UP), "pk dominates p5"),
        ]
        for (dp, dr), label in want:
            self.assertEqual(tradeoff_cell(dp, dr)[1], label)

    def contrast(self, f1=FLAT, pooled=FLAT, p=FLAT, r=FLAT):
        return {"det_f1": f1, "pooled_f1": pooled, "det_p": p, "det_r": r}

    def test_selection_verdicts(self):
        better = self.contrast(f1=DOWN)
        self.assertEqual(selection_verdict({"p1": better, "p2": better})["verdict"], "supported")
        self.assertEqual(selection_verdict({"p1": better, "p2": self.contrast()})["verdict"],
                         "not contradicted")
        self.assertEqual(selection_verdict({"p1": better, "p2": self.contrast(pooled=UP)})
                         ["verdict"], "contradicted")
        # A cell where pk gains at no detectable cost contradicts, even with F1 unresolved.
        self.assertEqual(selection_verdict({"p1": better, "p2": self.contrast(r=UP)})["verdict"],
                         "contradicted")
        # A trade-off does not.
        self.assertEqual(selection_verdict({"p1": self.contrast(f1=DOWN, p=DOWN, r=UP)})
                         ["verdict"], "supported")
        equivalent = selection_verdict({"p1": self.contrast(f1=d(0.0, -0.04, 0.04))})
        self.assertEqual(equivalent["per_predecessor"]["p1"]["equivalent_on"], ["det_f1"])

    def test_bridging_verdicts(self):
        def c(y, v, p):
            return {"geo_inband_per_window": y, "geo_valid_inband_per_window": v,
                    "geo_yield_precision": p}
        self.assertEqual(bridging_verdict(c(UP, FLAT, FLAT))["verdict"],
                         "more extracted ≠ more valid")
        self.assertEqual(bridging_verdict(c(DOWN, DOWN, UP))["higher_yield"], "p5")
        self.assertEqual(bridging_verdict(c(DOWN, DOWN, UP))["verdict"],
                         "more extracted ≠ more valid")
        self.assertEqual(bridging_verdict(c(UP, UP, FLAT))["verdict"], "yield tracked validity")
        self.assertEqual(bridging_verdict(c(FLAT, UP, UP))["verdict"],
                         "in-band yield not distinguishable")

    def test_june_key_is_the_june_script_s(self):
        df = pd.DataFrame([{"asset_key": "K", "hazard": " Flood ", "location_text": "Bangkok",
                            "start_date": "2020", "end_date": "2020"}])
        self.assertEqual(_june_keyer()(df)["event_location_key"].tolist(),
                         ["k||flood||bangkok||2020||2020"])


if __name__ == "__main__":
    unittest.main()
