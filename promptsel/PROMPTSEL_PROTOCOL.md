# Experiment D — The prompt-5 selection, assessed after the fact: pre-registered protocol

**Status:** frozen at the commit that adds this file, `promptsel/FROZEN.json`
and the scorer, before any prompt is run on an evaluation window. The runner
refuses to spend until all three are committed, every hash in `FROZEN.json`
matches the code and files, and Experiment B's own preflight still passes
(`promptsel/runner.py`, `preflight_problems`). `promptsel/PROMPTSEL_SCORES.md`
prints the commit it ran against and flags uncommitted edits. Any change after
freezing goes in [§14 Deviations](#14-deviations-log), appended and dated,
never edited in place.

Drafted 2026-11-02.

## 0. Question

> Judged against a blind human reference rather than on the yield that
> selected it, was prompt 5 a better choice than prompts 1–4?

This answers the first reviewer, who notes that the production prompt was
chosen mainly on extraction and geocoding yield, and that more extracted events
need not mean more valid ones.

Two things are kept apart throughout:

1. **The operational selection** (§1): what was actually done on 2026-06-01,
   recorded from files and commits. This experiment does not revise it.
2. **The retrospective accuracy assessment** (§2–§11): the five prompts scored
   after the fact against Experiment A's blind gold.

No human-reference accuracy figure for prompt 5 existed when it was chosen.
Nothing written from this experiment may say or imply that human validation
drove the selection.

**This is not an estimate of generalisation.** The windows were selected on
prompt 5's production output (§3), which favours p5 by construction. The
reading rules (§10) are asymmetric for that reason: a result against p5 is
robust; a result for p5 is only consistent with the selection.

**Primary outcomes.** For each predecessor pk (k = 1..4), Δ = pk − p5 over all
80 windows:
1. Event detection F1 under the evidence-blind reading R2 (§6).
2. Pooled document attribute F1 (§8), which needs no matching.

Detection precision and recall are reported beside them, because the
precision/recall trade-off is what the reviewer asks about (§10).

**Secondary outcomes.** Everything else in §8, for every prompt and every group.

## 1. Operational selection record

| Date | What happened | Where it is recorded |
|---|---|---|
| 2026-05-09 to 05-12 | p1–p4 run on 400 documents, Azure GPT-5, medium and high reasoning effort. Single-event texts: "Extract ONE best candidate per document". One row per document. | `outputs/test_400_gpt5_{medium,high}_prompt0{1..4}/` (gitignored); texts at commit `9ed213e` |
| 2026-05-19 | p1–p4 rewritten to return every distinct event as a top-level `events` list. | commit `d0dcd71` |
| 2026-05-20 | Multi-event p1–p4 run on the first 200 of those documents. | `outputs/test_200_gpt5_medium_prompt0{1..4}/` |
| 2026-06-01 | p5 written and run on the same 400 documents, then compared with the **May single-event medium-effort** p1–p4 runs. | commit `6f6f5b1` adds p5 and `scripts/compare_resolution_filtered_runs.py`; results in `outputs/test_400_gpt5_medium_prompt05_vs_prompt01_04_resolution_confidence_070_098/` |
| 2026-07-06 | `DEFAULT_PROMPT_ID` changed from 1 to 5. | commit `554e7b6` |

**The criterion** (`compare_resolution_filtered_runs.py`, defaults at
L51–62, filter at L162–173):
- Each prompt's geocoded event-locations are kept when 0.70 ≤
  `resolution_confidence` ≤ 0.98, inclusive at both ends.
- For each prompt: the rows kept, the documents they cover, and their mean
  confidence.
- p1–p4 are merged into one union, deduplicated on
  asset‖hazard‖location‖start date‖end date.
- The union's exact-key overlap with p5 is computed.

**The June figures**, from `selection_summary.csv` and
`retrieval_overlap_summary.csv`:

| Prompt | Rows in band | Documents | Mean confidence |
|---|---:|---:|---:|
| prompt01 | 58 | 33 | 0.813 |
| prompt02 | 67 | 51 | 0.834 |
| prompt03 | 64 | 40 | 0.839 |
| prompt04 | 61 | 37 | 0.833 |
| prompt05 | 134 | 56 | 0.853 |
| union of 01–04 | 150 | 62 | 0.826 |

Union 150, p5 134, both 70, p5 only 64, union only 80, Jaccard 0.327.

**What that comparison could not show:**
- **Validity.** It counted and scored geocoded rows. No row was checked
  against its source or a human label.
- **The prompt alone.** p5 ran multi-event; p1–p4 ran single-event. Part of
  p5's roughly twofold in-band yield is the schema, not the prompt.
- **Noise.** One run per prompt, no replicates, no intervals.

**What survives.** The p5 extraction run behind the June figures
(`outputs/test_400_gpt5_medium_prompt05/`) is lost; only its filtered layer
remains (`map_layers/prompt05/`). The stored p1–p4 runs overlap Experiment A's
blind gold on 2 windows only. So the June runs cannot be re-scored against a
common human reference, and this experiment reruns the prompts instead.

**No human-reference accuracy figure for p5 existed at the freeze.** The
first human verdicts on p5 output are in `eval/gold_validation.csv`. That file
was created on 2026-06-25 from the separate `outputs/gold` run
(`eval/README.md`, "The `gold-*` equivalents") and first committed in
`554e7b6`. Experiment B's protocol (§2) describes those verdicts as "made
during prompt selection"; the file dates do not support that. This is noted
here, and Experiment B stays frozen.

## 2. Configurations

| Config | Prompt | June label | `system_sha16` | System chars |
|---|---|---|---|---:|
| `p1` | `baseline_strict_location` | prompt01 | `fc32dc937842cbbe` | 14,493 |
| `p2` | `case_study_high_recall` | prompt02 | `817d7ac69ce27db3` | 5,942 |
| `p3` | `verification_first` | prompt03 | `e04eead4d4dfa804` | 5,858 |
| `p4` | `compact_schema_focused` | prompt04 | `7dc36a745e810ca0` | 4,651 |
| `p5` | `unified_verification_recall` | prompt05 | `cfbf35634b527da4` | 7,358 |

- **p1–p4** are `get_prompt(1..4)` from `src/fonte/prompts.py`. Their texts
  are byte-identical at `d0dcd71`, at the p5 freeze (`6f6f5b1`) and today.
- **All five** use the production response schema `DocumentEventExtractions`
  (`schema_sha256` `12d454a0bfc2…`) and its post-filter. Only the system
  prompt and the user instruction differ.
- **p5** is Experiment B's `full`: the same `PromptSpec` object and the same
  schema class. Its rendered files equal `ablation/prompts/full/` byte for
  byte (`tests/test_promptsel.py`).
- **Every request** is built by `ablation.runner.extract_one`. A test checks
  it equals `run_openrouter.extract_document`'s request for the same prompt.

**Why the current texts and not the June ones.** The single-event June texts
return at most one record per window. On the 34 multi-event windows that caps
recall, so p5 would win by construction. The multi-event versions existed two
weeks before p5 and share its schema, so only the prompt varies. The
consequence: this experiment assesses the prompts. It is not a re-run of the
June comparison.

**Held fixed in every configuration**, as in Experiment B §1:
- Model `openai/gpt-5` on OpenRouter, reasoning effort `medium`.
- Structured output pinned to `json_schema`. A failure is an error row, never
  the `json_object` fallback.
- The `document_metadata` payload and the 12,000-character window.
- The post-filter: `_keep_verified_unique_events` and `_align_admin_levels`.

GPT-5 takes no temperature or seed, so every configuration runs **2
replicates**.

## 3. Windows and gold

Experiment B §2, unchanged and read in place:
- **Windows:** `ablation/windows.csv` (sha256 `384e684ce93ccbe0…`).
- **Gold:** Experiment A's `eval/event_level_gold.csv` (sha256
  `5c66d9f9305e0be6…`).

| Group | Windows | Gold |
|---|---:|---|
| Event-present, single | 10 | blind event-level (Experiment A) |
| Event-present, multi | 34 | same |
| Event-absent, hard negatives | 6 | empty |
| Event-absent, random negatives | 30 | empty |

Each window also carries two flags:
- `dev_pool_400` (2 windows): in the June 400-document pool.
- `gold_validation` (5 windows): holds verdicts on p5 output.

## 4. Runs

`promptsel/runner.py` runs 5 configurations × 2 replicates × 80 windows = 800
calls.
- **Order:** one seeded queue (seed 47; 42–45 belong to Experiment A, 46 to
  Experiment B) interleaves every job, so drift over the run falls on every
  prompt alike.
- **Logging:** as in Experiment B §3. Every call is in `attempts.jsonl`, the
  raw JSON before the post-filter is in `raw/`, and an errored window is
  retried by re-running.
- **Common windows:** contrasts use the windows every one of the 10 runs
  returned, and any window dropped is listed.

**Baseline and reference rows:**
- The **fresh p5 replicates** are the contrast baseline.
- **Experiment B's `full` r1/r2** (2026-11-01, the same request) are reported
  as a reference. They also give the cross-session drift p5 − `full`. They are
  never a baseline.
- **The September OpenRouter run and the Azure production run** are scored on
  the same windows and not contrasted.

**Preflight.** The full run refuses unless all of the following hold:
- this file, `FROZEN.json`, the rendered prompts, `configs.py`, `runner.py`,
  `geocode.py`, `score_promptsel.py` and `tests/test_promptsel.py` are
  committed and clean;
- every hash in `FROZEN.json` matches, including those of the Experiment B,
  Experiment A and production geocoder sources this experiment imports;
- Experiment B's preflight still returns no problems.

## 5. Hazard normalisation

Experiment B §4, unchanged (`LEXICON_SHA256` `aec7441915b955d2…`), applied to
every run before scoring. All five prompts carry the PreventionWeb vocabulary
block, so the rule is expected to be close to the identity.

## 6. Matching readings

Experiment A's matcher (`eval/event_matching.py`) is used unchanged.

- **R2, evidence-blind (primary).** Snippets are stripped before matching, so
  records link by overlapping years and at least one matching place (tier C).
  - All five prompts emit snippets, but p1–p4 allow paraphrase ("no long
    quotes") while p5 requires grounded evidence.
  - Under R1's evidence tiers, a contrast would therefore partly measure
    snippet style. R2 also continues Experiment B's primary reading.
- **R1, anchored.** Experiment A's rules as written, for all five prompts
  (sensitivity S4).
- **Pooled document F1** does not use the matching. It is identical under both
  readings.

Field rules are those of Experiment A §5.

## 7. Geocoding

**What is resolved.** Each record's places, as `fonte-polygons` would resolve
them:
- `explode_extractions` gives one pair per location of each verifiable record
  that has locations and dates. The country hint is used only when the
  document names exactly one country.
- `NominatimResolver` runs with production defaults: polygons preferred; bbox
  accepted only for admin and populated-place classes; 1.1 s between requests.
- `resolution_confidence` is `confidence_score` with the overshoot cap
  (`src/fonte/run_polygon_resolution.py` L184–215, L302–307).

**In band** means 0.70 ≤ confidence ≤ 0.98, inclusive at both ends: the June
rule.

**Once per place.** Each distinct (location, hint) is resolved once, and the
result is shared by every run, so geocoder variance cannot differ between
prompts.

**Cache:**
- The root `.nominatim_cache.json` is only read.
- The keys the resolver needs are copied to `promptsel/geocode/nominatim_cache.json`
  (gitignored).
- A miss goes to the public endpoint.
- Every field the confidence score reads, but no geometry, is committed in
  `promptsel/geocode/resolutions.csv`.

**Self-checks; the scorer refuses if either fails:**
- `explode_rows`, with `event_index` dropped, equals production's
  `explode_extractions` on every run file.
- The Azure production run on these windows reproduces
  `outputs/event_extractions/event_geometries.parquet` exactly: every resolved
  (uuid, confidence). The `--accept-geo-drift` override exists only to be
  logged in §14.

Geocoding success is the resolver's own success and confidence. Nobody has
judged these geometries; **success is not correctness**.

## 8. Metrics and reporting (`promptsel/score_promptsel.py`)

Experiment B's scorer (`ablation/score_ablation.py`: `score_run`,
`extra_counts`, `groups_for`, `shared_weights`) does the extraction side
unchanged.

| Reviewer's item | Metric |
|---|---|
| Event detection precision and recall | detection P, R and F1 (Experiment A's definitions) |
| Pooled attribute F1 | pooled document F1, and per field (hazard, year, location) |
| Candidate yield per document | records per window; raw pre-filter events per window; post-filter drop reasons; false-alarm rate on event-absent windows |
| Evidence support | snippet grades from `citation_quality.classify` (quotable, grounded, unsupported); records with a quotable snippet; attribute traceability (every place and a year literally in the window) |
| Geocoding success | places per window, resolved rate, in-band rate, mean confidence of resolved and of in-band places |

**The bridge between yield and validity** (R2, and R1 in S4):

| Metric | Definition |
|---|---|
| In band / window | in-band event-locations per window: June's statistic |
| Valid in band / window | in-band event-locations whose record links to a gold event |
| Invalid in band / window | in band − valid: an unmatched record, or any record on an event-absent window |
| Yield precision | valid in band / in band |
| Record yield precision | records with a valid in-band place / records with an in-band place |

**Also reported, descriptively:**
- **The June criterion recomputed on these windows, per replicate:** rows in
  band, windows, mean confidence, the p1–p4 union deduplicated on June's key,
  its Jaccard overlap with p5, and the valid share of the p5-only and
  union-only keys. These are quoted next to June's figures, with the caveat
  that the two differ in documents, schema and provider.
- **Ranks:** the five prompts ranked by in-band yield, records per window,
  detection F1, pooled F1 and yield precision.
- **Replicate noise and drift:** r2 − r1 for each prompt, and the
  cross-session drift p5 − Experiment B `full`.

**Groups:** as in Experiment B:
- all 80 windows;
- event-present 44, split into single 10 and multi 34;
- event-absent 36, split into random 30 and hard 6;
- S1, without the 2 dev-pool windows;
- S2, without the 5 `gold_validation` windows.

**Sensitivities:**
- **S3:** the literal-false-alarm bound, as in Experiment B.
- **S4:** R1 for all five prompts.
- **S5:** the band without its upper bound, [0.70, 1.0], and any resolved
  place.
- **S6:** "valid" read as a complete record, or as correct places.

**Outputs:**

| File | Contents |
|---|---|
| `promptsel/PROMPTSEL_SCORES.md` | the report; the header carries the protocol commit, the hashes and the self-checks |
| `promptsel/promptsel_scores.json` | everything, for the paper tables |
| `promptsel/promptsel_pairs.csv` | every link and every unmatched record or event, per run and reading |
| `promptsel/promptsel_geocode_pairs.csv` | every (record, place) with its confidence, band and validity, per run and reading |

## 9. Uncertainty

Experiment B §6, unchanged:
- **Bootstrap:** 95% percentile window-cluster bootstrap, 2,000 resamples. One
  weight matrix per group is shared by every prompt, reading and contrast. The
  overall, S1 and S2 groups are resampled within event-present and
  event-absent windows.
- **Pooling:** a prompt's estimate pools its two replicates' counts.
  Δ = pk − p5.
- **Noise:** replicate 2 − replicate 1 for each prompt, on the same bootstrap.

**Multiplicity.** Contrasts are uncorrected, and the report says so.
- A "supported" verdict (§10) needs p5 to be better than **each**
  predecessor. As an intersection–union test it needs no correction.
- "Contradicted" can be reached by any one of 4 predecessors × 2 primaries.
  Uncorrected, that is easier to reach by chance. The error therefore falls
  against p5, not in its favour.

## 10. Pre-registered reading rules

A difference is **resolved** when its 95% interval excludes 0. Δ is always
pk − p5.

**Precision/recall cell** for each predecessor, from p5's side:

| ΔP \ ΔR | p5 higher recall | not resolved | pk higher recall |
|---|---|---|---|
| **p5 more precise** | p5 dominates | p5 more precise, no detectable recall cost | trade-off: p5 trades recall for precision |
| **not resolved** | p5 higher recall, no detectable precision cost | not distinguishable | pk higher recall, no detectable precision cost |
| **pk more precise** | trade-off: p5 trades precision for recall | pk more precise, no detectable recall cost | pk dominates p5 |

**Selection verdict** (R2, all windows; S4 is reported the same way):
- ***Contradicted*** if any of these holds for any pk:
  - pk is resolved-better than p5 on either primary F1;
  - pk falls in "pk dominates p5";
  - pk falls in "pk … no detectable … cost".
- ***Supported*** if not contradicted, and p5 is resolved-better than **every**
  pk on at least one primary F1.
- ***Not contradicted*** otherwise. Every trade-off cell is named explicitly.
- ***Equivalent*** is said of a pk and a primary only when the whole Δ
  interval lies within ±5 pp. Experiment B's `full` replicate noise was about
  ±4 pp.

**Asymmetry.** The windows were selected on p5's production output:
- *Contradicted* is a robust finding.
- *Supported* reads as "consistent with the selection", never as
  confirmation.
- p5's recall on event-present windows is the most inflated quantity.

**Bridge**, for each pk against p5:
- ***More extracted ≠ more valid*** when one prompt has resolved-higher in-band
  yield, but its valid in-band yield is not resolved-higher, or its yield
  precision is resolved-lower.
- ***Yield tracked validity*** when in-band and valid in-band yield are
  resolved in the same direction and yield precision is not resolved.
- The report also states whether June's ordering, with p5 highest on in-band
  yield, recurs here.

**Framing commitments for the paper.** Wording about the selection is taken
from these templates and chosen before the results are seen:
- **A precision/recall trade-off** (e.g. "a higher-recall prompt suited to
  human-reviewed candidate discovery") may be described only if the
  corresponding cell is observed. p5 may be called the higher-recall prompt
  only against predecessors over which its recall is resolved-higher.
- **If the verdict is *contradicted***, the paper says so and names the
  predecessor and the outcome.
- **The original selection** is described only as in §1: chosen on
  resolver-filtered yield, before any human reference for p5 existed.

## 11. Commitments

- Every prompt, group and reading is reported, including results that favour
  a predecessor.
- The primary outcomes are quoted with their paired intervals and beside the
  replicate noise. A prompt-level figure is never quoted without its Δ against
  p5.
- No rule above is changed after the first evaluation run without an entry in
  §14. If a rule changes, results under the original rule are reported
  alongside.
- The scorer refuses to run until all 10 runs and `resolutions.csv` exist.
  `--allow-partial` is for previews only.

## 12. Limitations to disclose

- **Selection favours p5.**
  - Every event-present window entered because production p5 found an event
    there.
  - The 30 random negatives were judged with p5's empty output visible.
  - The 6 hard negatives are windows where production p5 emitted an event
    that was then rejected, so they count against p5.
- **Not the June prompts or harness.**
  - The texts are the multi-event p1–p4, not the single-event versions
    compared in June.
  - The provider is OpenRouter, not Azure.
  - The documents are 80 windows, not 400.
  - The June figures and these cannot be compared figure for figure.
- **The predecessors were superseded, not tuned.** p5 was developed after p1–p4
  and partly from them. p1–p4 received no further revision.
- **Geocoding success ≠ correctness.**
  - The confidence score is an uncalibrated heuristic (its own docstring says
    so).
  - No geometry on these windows has been judged.
  - Nominatim entries fetched for this experiment reflect the endpoint on the
    day; `resolutions.csv` pins them.
- **Event-absent gold has no written guideline.** Validation 2's "no" is
  stricter than Experiment A's guideline; S3 bounds this.
- **R2 couples detection with fields.** A record whose years or places are
  wrong cannot link at all.
- **Single annotator, English only**, as in Experiment A.
- **Small groups and 2 replicates.** Intervals on the single and
  hard-negative groups are wide. Run-to-run noise is estimated only coarsely.

## 13. Procedure

```
make promptsel-prompts            # render the five prompts -> promptsel/prompts/
make promptsel-dry-run            # hashes, catalogue check, cost estimate, preflight; no spend
make promptsel-smoke              # 3 non-evaluation documents x 5 prompts (~$0.75)
make promptsel-freeze             # pin everything -> promptsel/FROZEN.json; then commit (= pre-registration)
make promptsel-run                # 5 prompts x 2 replicates x 80 windows; re-run to retry errors
make promptsel-geocode-preflight  # how many place lookups the root cache already answers
make promptsel-geocode            # resolve every distinct place once -> promptsel/geocode/resolutions.csv
make promptsel-score              # -> promptsel/PROMPTSEL_SCORES.md (refuses until all 10 runs exist)
```

**Before freezing** (development, recorded for transparency):
- **Rehearsal.**
  - The scorer was run on Experiment B's runs relabelled as p1–p5
    (`reduced_rules`, `bare`, `no_vocab`, `no_evidence`, `full`), with
    geocoding answered offline from the root cache.
  - It reproduced Experiment B's published figures exactly; for example, the
    relabelled `reduced_rules` Δ detection F1 was +13.9 pp.
  - The production geocoding check passed: every place of the Azure run on
    these windows was already cached.
  - No prompt of this experiment had yet been run on an evaluation window.
- **Geocoding preflight on the reference runs.** 271 distinct places, 187
  answered from the root cache, at most 104 network requests.
- **Smoke run.** 3 non-evaluation documents × 5 prompts, 1 replicate, $0.67
  (`promptsel/runs_smoke/`):
  - all 15 calls returned json_schema output, served as `openai/gpt-5` by the
    OpenAI provider, with finish reason `stop`;
  - every run recorded its prompt's pinned `system_sha16`;
  - every hazard was an exact PreventionWeb label.

## 14. Deviations log

_None yet. Append dated entries below; do not edit entries above._
