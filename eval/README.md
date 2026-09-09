# Evaluation runbooks

Three separate things live in this directory. Pick the one you need:

| | **A. Prompt selection** | **B. Run validation** | **C. Human annotation** |
|---|---|---|---|
| Question | Which prompt × reasoning-effort is best? | How accurate is the run we shipped? | How do models compare, now and later? |
| Unit | 1 document, full field labels | 1 event (or 1 resolved location) | 1 document, everything it reports |
| Records | field labels | a verdict on one run | ground truth, model-independent |
| Reusable for a new model | no | no | **yes — score it, no re-judging** |
| Inputs | the 8 `test_400_*` runs | one production extraction | the queue's 167 documents |
| Status | 75/75 labelled; stages 4–5 never run | 175/175 judged for the 10k run | 0/167 annotated |
| Runbook | [Track A](#track-a--prompt--reasoning-effort-selection) | [Track B](#track-b--validating-a-production-run) | [Track C](#track-c--human-annotation-for-comparing-models) |

**Validating the current extraction output? Track B. Comparing a new model
against the ones already measured? Track C.**

---

# Track B — validating a production run

Two independent passes over one extraction run: events (is the extracted
event right?) and polygons (is the resolved location right?). Both follow the
same shape — build a queue, judge it in a Streamlit app, score it.

### Sampling: random by default, and it matters

Both queue builders default to `--sampling random`, drawing a sample that
mirrors the population (events proportional to hazard-family share; polygons
proportional to stratum pool size). **This is what lets you say "extraction is
X% accurate."**

`--sampling risk` instead ranks by the label-free `auto_risk` heuristic and
deliberately over-weights hard cases. It is the better choice when you are
hunting for failure modes, but its accuracy is a *lower bound*, not an
estimate of population accuracy — do not publish it as one.

Every rate the scorers emit carries a 95% Wilson interval
(`fonte.stats`). At n=175 the margin is roughly ±6pp overall, and
per-hazard-family cells are much wider — read those as indicative.

### Events

```
make prod-prefill-validation    # queue -> eval/production_validation.csv
make prod-validate              # judge: correct / partial / wrong
make prod-validation-score      # -> eval/production_validation_scores.csv
```

Scores report `accuracy` (correct / judged) and `useful_rate`
(correct + partial / judged), at three granularities in the `segment_kind`
column: `ALL`, `family` (the level to report at), and `hazard` (raw
`event_hazard`, for drill-down only — single-digit cells).

Override `PROD_VALIDATION_TARGET` (default 175) to resize the queue, and
`PROD_VALIDATION_CSV` to write elsewhere.

### Polygons

```
make prod-polygon-sample        # stratified sample from event_geometries.parquet
make prod-polygon-prefill       # queue 60, proportional to stratum pool size
make prod-polygon-validate      # judge location / geometry / admin level / dates
make prod-polygon-score         # -> eval/PRODUCTION_POLYGON_VALIDATION.md
```

Strata are `high_confidence`, `low_confidence` and `unresolved` (the
anti-join: locations the resolver never placed). The sample lives under
`outputs/`, which is gitignored — copy the judged CSV into `eval/` if the
labels should be preserved.

### QA counts

```
make qa    # -> outputs/event_extractions/visualisation_checks/
```

Row/event counts, confidence and hazard distributions, QA flags and plots.
Note `make visualisation` is `--map-only` and deliberately skips this.

### The `gold-*` equivalents

`make gold-*` runs the same event flow against `outputs/gold` (a separate
2,000-doc run) and writes `eval/gold_validation.csv`. It predates the
production queue and is kept for continuity.

---

# Track C — human annotation, for comparing models

Tracks A and B record a **verdict about one run**: "prompt 5 got this event
right." A verdict cannot be reused. Judging a second model means judging 175
events again, and the two passes are not on the same scale, because they were
made on different days against different screens.

Track C records what the **document** says, with no reference to which pipeline
produced it. Annotate once; score any number of runs against it afterwards, in
seconds, with no further human time.

```bash
make annotate-prefetch   # pull the queue's documents into a small local store
make annotate            # annotate them (resumable)
make annotate-score      # score prompt 5 and the NER baseline against them
make annotate-score EXTRA_RUN="gpt-x=path/to/run.jsonl"   # add a third model
```

### The unit is the document, not the queue event

`production_validation.csv` is 175 rows over **167 distinct documents**, and it
samples *events*: prompt 5 emits 572 verifiable events across those same 167
documents, so a queue row covers under a third of its document on average.

Annotating per queue row would make gold a partial list of what each document
reports, and every unannotated event a run legitimately found would score as a
false positive. Precision would be measuring the sampling, not the model.

So `human_annotation_app.py` collapses the queue to one item per document, and
asks for **everything that document reports** — not just the sampled event.
Gold is then complete, and precision, recall and F1 all mean what they say for
any run, however it splits a document into events.

That is also why every metric in `score_against_human.py` is computed per
document: `event_index` is not a shared key across pipelines (the LLM's
"Earthquake | Tsunami" is the baseline's two candidates), so joining on it
would score segmentation rather than extraction.

### Documents are prefetched, not read live

`make annotate-prefetch` writes `eval/annotation_documents.json`: only the
queue's 167 documents, about 2 MB, loaded by the app in ~14 ms.

The obvious alternative — reading `benchmark_ner/outputs/documents.parquet` when
the app starts — scanned 57 MB to keep 1.8 MB, cost ~1.9 s on every start, and
tied the reviewer to a **gitignored** bulk artefact that a fresh checkout does
not have. Annotation is a long human session against a fixed set of documents;
there is nothing live about them, so they are resolved once and stored.

The app builds the store itself if it is missing, so the prefetch step is a
convenience rather than a prerequisite, and there is a "Rebuild document store"
button in the sidebar for when the queue changes. Once built, the parquet is
never touched again and nothing is re-read on a rerun — the store is held in
`st.cache_resource` and the evidence highlighting in `st.cache_data`.

Consider committing `annotation_documents.json`. It is derived data, but at 2 MB
it is the difference between "clone and annotate" and "get Databricks access,
re-run a 10,000-document fetch, then annotate", and it pins the exact text the
annotations were made against.

### What is on screen

The left pane is the **fetched document** — the same 12,000-character window the
models were given, not the live URL. What a model could not have read cannot be
held against it, and the page is offline, so review does not depend on a
publisher still serving the document.

Evidence snippets from the seed run are highlighted in it: 🟨 where the quote is
in the document, 🟦 where only part of it is. Quotes are matched fragment by
fragment across `...`, because extractors stitch separated pieces into one
snippet and a strict equality test would report a faithful quote as invented.
A snippet that resolves to neither is worth a note — it is translated (the
Japanese documents), paraphrased, or fabricated.

The right pane starts blank. "Accept seed as gold" copies the reference run's
merged extraction into the form in one click for the common case where it is
already right, but the default costs a decision rather than a nod.

### What comes out

`eval/human_annotations.csv` — one row per document, with `gold_hazards`,
`gold_dates`, `gold_locations`, `gold_impacts`, a `gold_uncertain` flag, and
who annotated it when. Tracked in git: it is human labour, and it is the asset
that outlives any particular model.

`make annotate-score` writes `eval/HUMAN_ANNOTATION_SCORES.md`: event detection
with Wilson intervals, set P/R/F1 for hazard family (compounds split on both
sides), locations (exact and fuzzy ≥90) and dates, and an exact McNemar test on
every pair of runs — the same documents are judged once, so the informative
quantity is the discordant pairs, not two independent proportions.

Runs are read as JSONL or CSV in the `event_extractions` schema, so a new model
needs no adapter: emit that schema and it scores.

`--exclude-uncertain` drops the flagged rows and reports how many it dropped.

# Track A — prompt × reasoning-effort selection

Goal: pick the best prompt + reasoning-effort combination for the
`fonte-extract` extraction step, using the 8 runs already produced
under `outputs/test_400_gpt5_{high,medium}_prompt{01..04}/`.

The strategy is a five-stage funnel. Stages 1–2 are label-free and run
end-to-end in a few minutes. Stage 3 is the half-day hand-labelling pass.
Stages 4–5 score against those labels and emit a recommendation.

> Stages 1–3 have been run (`eval/gold.csv` holds 75/75 labels). Stages 4–5
> have not, so `scores.csv`, `scores_by_segment.csv` and `RECOMMENDATION.md`
> do not exist yet. Note `recommend.py`'s `PROMPT_NAMES` covers prompts 01–04
> only — prompt 05 is the current production default and would render
> unlabelled.

## Stages

### 1. Triage metrics — `triage_metrics.py`

```
python3 eval/triage_metrics.py
```

Writes `eval/triage.csv`: one row per run with `verifiable_event_rate`,
`polygon_resolution_rate`, `country_hallucination_rate` (cross-checks the
LLM's `countries` field against Nominatim's resolved country),
`country_overshoot_rate`, plus a handful of emission-rate columns. Use
this to drop the bottom 2–3 runs from further review.

### 2.1. Unified comparison table — `unified_table.py`

```
python3 eval/unified_table.py
```

Joins all 8 runs by `asset_key` into `eval/unified.parquet`, with a
`disagreement_score` per document measuring how much the runs disagree
on `is_verifiable_event`, `event_hazard`, and pooled `affected_locations`.

### 2.2. Review sample — `sample_for_review.py`

```
python3 eval/sample_for_review.py
```

Writes `eval/review_sample.csv` (75 docs):
50 highest-disagreement + 15 stratified by hazard family + 10 random
low-disagreement. The CSV is wide and meant to be read in a spreadsheet,
with the 8 runs' outputs side-by-side.

### 3. Gold labelling — `gold_template.py`

```
python3 eval/gold_template.py
```

Writes `eval/gold.csv` (refuses to clobber an existing file; pass
`--force` if you really mean to overwrite). Fill in the label columns
(`is_real_event`, `true_hazard`, `true_country`, `true_locations`,
`true_date_start`, `true_date_end`, `notes`) by reading each document
via `content_url`. Use `runs_hazard_summary` as a cheat sheet — but don't
let it bias you.

**Verification before committing all 75:** re-label 5 docs blind and
check stability. If your second-pass labels disagree with the first on
more than 1 doc, write down a rubric before continuing.

### 4. Scoring against gold — `score_against_gold.py`

```
python3 eval/score_against_gold.py
```

Joins gold ↔ unified, writes:

- `eval/scores.csv` — one row per run with overall `quality_score`
  (weighted mean of field F1s) and per-field P/R/F1.
- `eval/scores_by_segment.csv` — same metrics broken down by
  `hazard_family`, `language`, and `region`, with `n_docs_in_segment`.

Field weights are at the top of `score_against_gold.py` (`FIELD_WEIGHTS`)
— tune to project priorities.

### 5. Recommendation — `recommend.py`

```
python3 eval/recommend.py
```

Reads the score CSVs and writes `eval/RECOMMENDATION.md` — a one-page
summary with:

- Best overall run (raw quality).
- Cost-adjusted pick: medium is preferred if it's within 0.05 F1 of
  the best high run (`--cost-margin` to override).
- Per-segment routing suggestions, only when a segment with ≥5 gold
  docs has a winner that beats the global pick by >0.10 F1
  (`--segment-margin`, `--segment-min-docs` to override).

## Cleaning up between iterations

If you re-sample or re-label:

```
rm eval/{unified.parquet,review_sample.csv,gold.csv,scores.csv,scores_by_segment.csv,RECOMMENDATION.md}
```

Then re-run from Stage 1.

## Files

**Track A — prompt selection**

| Stage | Script | Inputs | Outputs |
|-------|--------|--------|---------|
| 1 | `triage_metrics.py` | `outputs/test_400_gpt5_*` | `triage.csv` |
| 2.1 | `unified_table.py` | `outputs/test_400_gpt5_*` | `unified.parquet` |
| 2.2 | `sample_for_review.py` | `unified.parquet` | `review_sample.csv` |
| 3 | `gold_template.py` | `review_sample.csv` | `gold.csv` (template) |
| 4 | `score_against_gold.py` | `gold.csv`, `unified.parquet` | `scores.csv`, `scores_by_segment.csv` |
| 5 | `recommend.py` | `scores.csv`, `scores_by_segment.csv` | `RECOMMENDATION.md` |

**Track C — human annotation**

| Step | Script | Inputs | Outputs |
|------|--------|--------|---------|
| 0 | `prefetch_annotation_documents.py` | `production_validation.csv`, `documents.parquet` | `annotation_documents.json` |
| 1 | `human_annotation_app.py` | `production_validation.csv`, `annotation_documents.json`, a seed run | `human_annotations.csv` |
| 2 | `score_against_human.py` | `human_annotations.csv` + any runs | `HUMAN_ANNOTATION_SCORES.md` |

**Track B — run validation**

| Step | Script | Inputs | Outputs |
|------|--------|--------|---------|
| events 1 | `prefill_gold_validation.py` | `event_extractions.jsonl` | `production_validation.csv` |
| events 2 | `gold_validation_app.py` | the queue | verdicts, in place |
| events 3 | `score_gold_validation.py` | the queue | `production_validation_scores.csv` |
| polygons 1 | `scripts/make_polygon_validation_sample.py` | `.jsonl` + `event_geometries.parquet` | `polygon_validation_sample.csv` |
| polygons 2 | `prefill_polygon_review.py` | the sample | queue columns, in place |
| polygons 3 | `polygon_validation_review_app.py` | the sample | judgements, in place |
| polygons 4 | `score_polygon_validation.py` | the sample | `PRODUCTION_POLYGON_VALIDATION.md` |
| counts | `scripts/visualize_event_extractions.py` | `event_extractions.csv` | `qa_report.md`, `summary.json`, plots |

Shared helpers: `fonte.hazard_families` (the family taxonomy used by
the sampler and both scorers) and `fonte.stats` (Wilson intervals).

Both Track B review apps take a path override — `GOLD_VALIDATION_CSV` /
`POLYGON_VALIDATION_CSV`, or a path after `--` — so you can judge any queue
without editing the scripts. The Track C app takes `HUMAN_ANNOTATIONS_CSV`,
`ANNOTATION_QUEUE_CSV`, `ANNOTATION_DOCUMENTS` (the prefetched store),
`ANNOTATION_DOCUMENTS_PARQUET` (the bulk source it is built from) and
`ANNOTATION_SEED_RUN`.
