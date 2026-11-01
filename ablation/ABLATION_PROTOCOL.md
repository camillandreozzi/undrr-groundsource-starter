# Experiment B — Controlled ablation of prompt 5: pre-registered protocol

**Status:** frozen at the commit that adds this file and `ablation/FROZEN.json`,
before any configuration is run on an evaluation window. The runner refuses to
spend until both are committed and every hash in `FROZEN.json` matches the code
and files (`ablation/runner.py`, `preflight_problems`).
`ablation/ABLATION_SCORES.md` prints the commit it ran against and flags
uncommitted edits. Any change after freezing goes in
[§10 Deviations](#10-deviations-log), appended and dated, never edited in place.

Drafted 2026-11-01.

## 0. Question

> Which of prompt 5's constraints contribute to accuracy, consistency and
> verifiability, rather than treating the whole prompt as one indivisible method?

This answers the second reviewer's request for an ablation. One constraint is
removed at a time, and all three are also removed together. The model, document
text and metadata, decoding, post-filter and scoring stay fixed.

**This is a retrospective diagnostic ablation, not an estimate of
generalisation.** Prompt 5's text was frozen on 2026-06-01 (`6f6f5b1`), before
any of these windows was annotated, and none of them is among the 75
dev-labelled documents (`eval/gold.csv`). But the windows were selected on
production output (§2), so the comparison favours `full` by construction.

**Primary outcomes.** Each configuration minus `full`, over all 80 windows:
1. Event detection F1 under the evidence-blind reading R2 (§5).
2. Pooled document attribute F1 (§6), which needs no matching.

**Secondary outcomes.** Everything else in §6, for every configuration and
every group.

## 1. Configurations

Each configuration is built in code from prompt 5's text, never retyped
(`ablation/configs.py`). The system prompt is cut at its own section headers
into parts that join back to production byte for byte. Each ablation is a
transform on those parts. The transforms commute, so `bare` is the same text in
any order (`tests/test_ablation.py`). The rendered messages and schemas, with
their sha256, are in `ablation/prompts/<config>/`.

| Config | System prompt and user instruction | Response schema |
|---|---|---|
| `full` | Prompt 5 unchanged (`system_sha16` `cfbf35634b527da4`, the hash in the September run's `run_stats.json`) | Production `DocumentEventExtractions` |
| `no_evidence` | "key_impacts **and evidence_snippets** must be grounded…" loses the bold words. The `high` confidence rule's "at least one impact **or evidence item**" loses the bold words. Nothing else changes. | `evidence_snippets` removed from the schema the model sees. The class still carries it, defaulting to `[]` and ignoring any value sent. |
| `no_vocab` | The "Hazard classification" section — the whole `PREVENTIONWEB_HAZARD_INSTRUCTION` block — becomes: "For each returned event, set event_hazard to a short description of the hazard as the source describes it. If one event involves several hazards, name each of them." | Production |
| `reduced_rules` | See below | Neutral descriptions (below). The evidence description is kept. |
| `bare` | All three transforms | Neutral, without `evidence_snippets` |

**What `reduced_rules` keeps and drops.**
- **Keeps:**
  - the role line;
  - the evidence-grounding bullet;
  - the hazard vocabulary block, unchanged;
  - the admin-level value list and "use unknown only as a last resort".
- **Replaces:**
  - The search-scope section becomes the task line "Extract every disaster or
    hazard event reported in the document. Return one event object per event."
  - The return line becomes "…with a top-level events list. Return events=[]
    when the document reports no event."
  - The user instruction becomes "Extract every disaster or hazard event
    reported in this metadata and document text. Return JSON matching the
    schema exactly."
- **Drops:**
  - the "prompt 3 / prompt 4" preamble (meaningless to the model);
  - search scope, including rejecting forecasts, simulations, exercises and
    scenarios;
  - the metadata-as-hints and passing-mention bullets;
  - the date rules and the location rules;
  - the confidence and verifiability definitions;
  - the `is_single_actual_event` definition;
  - the admin-level line pointing to the deleted country rule.

**Neutral schema descriptions.** Names, types, defaults and field order stay
the same as production. Descriptions state format and allowed values only:
- dates: "Prefer YYYY-MM-DD; allow YYYY-MM, YYYY, or a short source phrase."
- admin levels: one tag per location, same order, the ten allowed values.
- impacts: "Up to 5 concise impact statements."
- confidence: "Allowed values: high, medium, low."
- the two booleans, hazard, locations and `missing_information`: no
  description.

Rules carried in production descriptions are gone: "Phase 2 location rules",
"NOT publication / workshop / report dates", the Chernobyl rule, and "explicitly
stated in the text".

**Held fixed in every configuration:**
- Model `openai/gpt-5` on OpenRouter, reasoning effort `medium`.
- Structured output pinned to `json_schema`. A failure is an error row, never
  the `json_object` fallback, which would paste the schema into the system
  prompt.
- The `document_metadata` payload and the 12,000-character window.
- The post-filter: `_keep_verified_unique_events` and `_align_admin_levels`.
  Every variant class subclasses production.

GPT-5 takes no temperature or seed, so every configuration runs **2
replicates**. The request for `full` is the same as
`run_openrouter.extract_document`'s (a test compares the two calls).

## 2. Windows and gold

**80 windows, frozen in `ablation/windows.csv`** by `ablation/build_windows.py`.
Every window text equals the benchmark snapshot the runner sends, byte for byte.

| Group | Windows | Source | Gold |
|---|---:|---|---|
| Event-present, single | 10 | Experiment A | blind event-level, `eval/event_level_gold.csv`, read in place (sha256 `5c66d9f9…`) |
| Event-present, multi | 34 | Experiment A | same |
| Event-absent, hard negatives | 6 | Experiment A's window `583badf1` (no verifiable event in blind gold), plus 5 event-arm documents where production emitted an event and Validation 2 said "no" | empty |
| Event-absent, random negatives | 30 | `document_sample_50` (a random corpus sample) documents judged "no" in Validation 2 | empty |

**Why Validation 2 "no" stands as event-level gold.** In
`eval/human_annotations_pooled.csv`, "no" means "no specific, verifiable event
in the first 12,000 characters". That is the same window the models see, so the
event-level gold of such a window is the empty set.

**Excluded candidates:**
- 4 `unclear` verdicts.
- 7 documents that fail Experiment A's language rule:
  `citation_quality.guess_language(window) != "en"` (four Spanish, one
  Norwegian, one Arabic, one Russian).
- The 9 random-arm documents with events, which have no event-level gold.

The list is in `ablation/windows_summary.json`.

**Each window also records two flags:**
- membership of the 400-document development pool (2 windows); and
- membership of `eval/gold_validation.csv` (5 windows), which holds verdicts on
  prompt-5 output rows made during prompt selection.

## 3. Runs

`ablation/runner.py`:
- One seeded queue (seed 46) interleaves all configuration × replicate × window
  jobs, so drift over the run (provider routing, load) falls on every
  configuration alike.
- Every call is logged in `attempts.jsonl` with the served model, provider,
  finish reason, tokens and cost.
- The model's raw JSON before the post-filter is kept in `raw/`.
- A window that ends in an error is retried by re-running. Contrasts use the
  windows that every one of the 10 runs returned, and any window dropped is
  listed.

**Reference rows, never contrasted.**
- The September OpenRouter GPT-5 prompt-5 run
  (`benchmark_openrouter/outputs_pooled/openai-gpt-5/`).
- The Azure production run (`outputs/event_extractions/`).

Both are scored on the same windows. The Azure run is the one the windows were
selected on, which is why contrasts are only ever against the fresh `full`
replicates.

## 4. Hazard normalisation

The rule is in `ablation/normalise_hazards.py` (`LEXICON_SHA256`
`aec7441915b955d2…`). It runs on **every** run before scoring. On the 24 exact
PreventionWeb labels it is the identity, so it is defined before any `no_vocab`
output exists and changes nothing for a configuration that obeys the vocabulary.

Per `|`-separated component:
1. An exact label (folded) is kept as is.
2. Otherwise the component is scanned, with hyphens read as spaces, using:
   - the NER baseline's lexicon (`benchmark_ner/hazard_lexicon.py`, false
     friends blanked first);
   - prompt 5's normalisation-table terms that the lexicon lacks;
   - patterns for Fall armyworm and Human-induced earthquakes;
   - a few unambiguous synonyms (cholera, cold spell, bushfire, …).
3. Where matches overlap, the longest span wins.
4. Labels are kept in order of first occurrence.
5. Anything unmatched passes through and is counted and listed (§6).

The scorer's `hazard_key` then applies Experiment A's family rules unchanged.
Its family regex is a second roll-up that the report discloses: a bare "storm"
lands in the cyclone family, "fire" in wildfire.

## 5. Matching readings

Experiment A's matcher (`eval/event_matching.py`) is used unchanged.

- **R2, evidence-blind (primary).** Every record's snippets are stripped before
  matching, so identity rests on overlapping years and at least one matching
  place (tier C) for all five configurations.
  - This is the only rule that compares all five: `no_evidence` and `bare` emit
    no snippets, so they cannot link through tiers A/B.
  - Under R1, their Δ would mix the model's change with the matcher's.
- **R1, anchored.** Experiment A's rules as written. Reported for `full`,
  `no_vocab` and `reduced_rules` as sensitivity S4, for continuity with
  Experiment A.
- **Pooled document F1** does not use the matching. It is identical under both
  readings and comparable across all five.

Field rules are those of Experiment A §5.

## 6. Metrics and reporting (`ablation/score_ablation.py`)

**Reused from Experiment A** (same definitions, `eval/score_event_level.py`):
- detection P, R and F1;
- complete-record correctness and recall;
- event-level attribute F1, per field and pooled;
- pooled document attribute F1, per field and pooled.

**Added:**

| Metric | Definition |
|---|---|
| False-alarm rate | event-absent windows with ≥1 record / event-absent windows |
| Records per event-absent window | records on event-absent windows / those windows |
| S3 bound | the same detection P/F1 and false-alarm rate with "literal" false positives set aside: records on event-absent windows whose every place and a year appear in the window, and whose evidence (if any) is quotable |
| Snippet traceability | `citation_quality.classify` grade of each snippet against the window: quotable and grounded rates, held-out grades out of the denominator. **Unavailable by design** for `no_evidence` and `bare` — reported as unavailable, not zero |
| Attribute traceability | records whose every place appears word-bounded in the window (or every comma-separated part does), whose dates carry a year that appears in it, and both. All five configurations |
| Schema compliance | from raw JSON before the post-filter: raw events per window; share dropped, by reason (not verifiable, confidence not high/medium, missing field, duplicate); admin-level length mismatches and invalid tags; exact-vocabulary hazard rate (descriptive for `no_vocab`/`bare`); ISO date rate; error rows and failed calls |
| Hazard normalisation | records relabelled; records with an unmapped component; the unmapped strings |

**Groups:**
- all 80;
- event-present 44, split into single 10 and multi 34;
- event-absent 36, split into random negatives 30 and hard negatives 6;
- sensitivity S1, without the 2 dev-pool windows;
- sensitivity S2, without the 5 `gold_validation` windows.

**Uncertainty:**
- **Bootstrap.** 95% percentile window-cluster bootstrap, 2,000 resamples. The
  weight matrix is seeded from 42 and the group's name, and the **same** matrix
  is used for every configuration, reading and contrast, so differences are
  paired. The overall, S1 and S2 groups are resampled within event-present and
  event-absent windows, whose sizes are fixed by design.
- **Pooling replicates.** A configuration's estimate uses its two replicates'
  counts, pooled. Δ = configuration − `full`.
- **Noise floor.** Replicate 2 − replicate 1 for each configuration, with the
  same bootstrap.
- **Reading rule.** An effect is described as a difference only when its
  interval excludes 0, and its size is read against `full`'s replicate noise.
- **Multiplicity.** Contrasts are uncorrected, and the report says so. `bare`
  against the single removals is a partial factorial, so interactions are
  described, not estimated.

**Self-check.** Before scoring, the scorer re-scores the September and Azure
runs on Experiment A's 45 windows under R1. Every counter must equal
`eval/event_level_scores.json`, or it refuses. Its loop re-implements
`score_system`, and this check proves the two agree.

**Outputs:**

| File | Contents |
|---|---|
| `ablation/ABLATION_SCORES.md` | the report; the header carries the protocol commit, the windows/gold/lexicon hashes and the self-check result |
| `ablation/ablation_pairs.csv` | every link and every unmatched record or event, per run and reading |
| `ablation/ablation_scores.json` | everything, for the paper tables |

## 7. Commitments

- Every configuration, group and reading is reported, including results that
  favour removing a constraint.
- The primary outcomes are quoted with their paired intervals and next to the
  replicate noise. A configuration-level figure is never quoted without its Δ
  against `full`.
- No rule above is changed after the first evaluation run without an entry in
  §10. If a rule changes, results under the original rule are reported
  alongside.
- The scorer refuses to run until all 10 runs exist. `--allow-partial` is for
  previews only.

## 8. Limitations to disclose

- **Selection favours `full`.**
  - Every Experiment A window entered the frame because production found an
    event there, which conditions detection recall on prompt 5's own output.
  - The 5 Validation 2 hard negatives are windows where production emitted an
    event and the annotator rejected it.
  - The 30 random negatives were judged with production's empty output
    visible.
- **Event-absent gold has no written guideline.** Validation 2's "no" means "no
  specific, verifiable event". Experiment A counts any stated hazard, year and
  place, including passing mentions. A configuration that reports passing
  mentions can therefore be charged false positives that Experiment A's
  guideline would have accepted. S3 bounds this.
- **Gold is bounded by the vocabulary.** An event with no PreventionWeb label
  is not in the gold. `no_vocab` drops the "no exact label → drop the event"
  gate, so such events become false positives by construction. The unmapped
  list shows them.
- **Residual vocabulary exposure in `no_vocab`.**
  - The location rules still name hazard types.
  - The production `event_hazard` description gives "Flood or Earthquake" as
    examples.
  - The document metadata carries PreventionWeb hazard tags for many windows.
- **`reduced_rules` keeps some generic discipline.** It keeps "Do not invent…
  dates, locations", the vocabulary block's "Do not infer beyond the source",
  and the "verification analyst" role line.
- **R2 couples detection with fields.** A record whose years or places are
  wrong cannot link at all, so under R2 detection F1 partly measures year and
  place accuracy. R1 (S4) and pooled F1 show the other readings.
- **Single annotator and English only,** as in Experiment A.
- **Small groups.** 6 hard negatives and 10 single-event windows have wide
  intervals.
- **Two replicates** estimate run-to-run noise only coarsely.

## 9. Procedure

```
make ablation-prompts      # render the five configurations -> ablation/prompts/
make ablation-windows      # freeze the 80 windows -> ablation/windows.csv
make ablation-dry-run      # hashes, catalogue check, cost estimate, preflight; no spend
make ablation-smoke        # 3 non-evaluation documents x 5 configurations
make ablation-freeze       # pin everything -> ablation/FROZEN.json; then commit (= pre-registration)
make ablation-run          # 5 configurations x 2 replicates x 80 windows; re-run to retry errors
make ablation-score        # -> ablation/ABLATION_SCORES.md (refuses until all 10 runs exist)
```

**Before freezing** (development, recorded for transparency):
- **Smoke run.** The smoke run (3 non-evaluation documents × 5 configurations,
  $0.73) showed every configuration returning json_schema output from the
  OpenAI provider, and no `evidence_snippets` key in `no_evidence`'s raw JSON.
- **Hyphen rule.** The smoke run surfaced "heat-wave" as unmapped, so the
  normaliser reads hyphens as spaces. That rule was added before freezing.
- **Scorer test.** While testing the scorer, the two reference runs (September,
  Azure) were scored on the 80 windows, and a mock ablation was assembled from
  their rows. No configuration had yet been run on an evaluation window.

## 10. Deviations log

_None yet. Append dated entries below; do not edit entries above._
