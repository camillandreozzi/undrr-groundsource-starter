# Multi-model benchmark — prompt 5, held fixed, across 13 models

## Why this exists

`outputs/event_extractions/` is one model: prompt 5 through `gpt-5` on Azure,
10,000 documents. `benchmark_ner/` answers *"how much is the LLM buying over a
classical pipeline?"* Nothing answers **"how much is _this_ model buying over any
other model?"**

That question matters here more than usual. Prompt 5 is not a light instruction —
it pins hazards to the PreventionWeb vocabulary, forbids bare countries for
sub-national hazards, carves out the technological/downwind exclusion, demands a
parallel admin-level tag per location, and sets a verifiability bar that a
Pydantic validator then enforces in code. Whether that whole apparatus survives
on a different model family, or on a model 50× cheaper, is unknown, and the
answer decides whether the pipeline is portable or married to one deployment.

## The design decision everything rests on

`run_openrouter.py` writes the **exact `event_extractions` schema**
(`fonte.app_event_focus.OUTPUT_HEADERS` — identical CSV header, identical
JSONL keys), the same decision `benchmark_ner/` rests on. So every downstream
tool takes a run from here unchanged:

| Tool | Used unchanged? |
|---|---|
| `eval/score_against_human.py` | yes — this is the whole point |
| `fonte-polygons` | yes — same resolver, ladder, confidence |
| `eval/gold_validation_app.py` | yes — via `GOLD_VALIDATION_CSV` |
| `scripts/visualize_event_extractions.py` | yes |

The prompt and the schema are **imported** from `src/fonte`, never copied.
Whatever production runs, this runs. `run_stats.json` records a hash of the
system prompt, so if `prompts.py` changes under you, the runs say so.

The post-filter matters most. `DocumentEventExtractions._keep_verified_unique_events`
drops every non-verifiable, low-confidence, under-specified and duplicate event
before anything is written. Both response paths below land in that same model, so
a chatty model cannot inflate its event count past the bar.

## Runbook

Add your key to `.env` first: `OPENROUTER_API_KEY=sk-or-...`

```bash
make or-check-models    # 1. validate every model id. No spend.
make or-build-docs      # 2. freeze the 167 documents. Needs Databricks.
make or-dry-run         # 3. estimate the bill from live pricing. No spend.
make or-smoke           # 4. 3 documents on the cheapest model. ~$0.01.
make or-run             # 5. the run. ~$37 for all 13. Resumable.
make or-agreement       # 6. cross-model stats. Needs no annotation.
make or-score           # 7. accuracy vs human annotations. Needs 167/167.
```

Steps 1–4 spend nothing and catch everything that usually goes wrong. Do them.

`or-run` is always safe to re-run: `--resume` skips finished documents and
retries the ones whose last attempt errored. Narrow it with
`--tier frontier` or `--model <id>`.

## The 167 documents

The set is the annotation queue's: `in_queue == Y` in
`eval/production_validation.csv`, 167 distinct `asset_key`s. `build_documents.py`
freezes them into `documents.json` (2.2 MB, tracked) so a clean checkout can
reproduce the benchmark without Databricks access.

The snapshot carries the **full `DocumentRow`**, not just text, because prompt 5
is given a `document_metadata` block and reads it. `eval/annotation_documents.json`
holds text only; the NER parquet lacks five metadata fields. Feeding a different
metadata block than the production run saw would confound a model comparison with
an input comparison, so Databricks is the default source. `--from-parquet` works
without it and records in the snapshot which fields it had to null.

Text is trimmed to 12,000 characters at snapshot time — the window
`--max-chars` gave the production run, so nothing is lost and the tracked file
stays at 2 MB rather than 19 MB. Verified byte-identical to the text the
annotation app shows reviewers.

## Two ways a model can answer

1. **`json_schema`** — `chat.completions.parse` with the Pydantic model, plus
   `provider.require_parameters` so OpenRouter only routes to providers that
   honour it.
2. **`json_object`** — for models with no strict-output support. The schema goes
   into the system message (descriptions stripped: they triple its size and every
   rule is already in prompt 5's prose) and we validate the reply ourselves,
   recovering JSON from markdown fences and surrounding chatter.

`auto` tries the first and remembers the fallback for the rest of the run, so the
wasted call is paid once, not 167 times. `run_stats.json` records which mode a
model actually used — it is a real confound and belongs in the report.

## Read the reports with these caveats

**`MODEL_AGREEMENT.md` is agreement, not accuracy.** There is no ground truth in
it. Two models agreeing can be two models wrong the same way, which on prompt 5's
location rules is the likely failure mode.

**The 167 documents are not a neutral sample.** The review queue was built from
events the prompt-5 / `gpt-5` run itself emitted, so that arm finds an event in
100% of them *by construction*. Another model's detection rate here measures how
well it reproduces gpt-5's finds, not how well it does on the corpus. Only
`eval/human_annotations.csv` settles who was right — which is why `score_all.py`
refuses to run until all 167 are annotated rather than reporting on whichever
subset was finished first.

**Prompt 5 was iterated against `gpt-5`.** Some of any gap is prompt-fit, not
capability. That is the right experiment for "can I swap the model?" and the
wrong one for "which model is better".

**No logprobs.** Support is inconsistent across OpenRouter providers and asking
for them fragments routing, so `event_confidence_logprob` / `_prob` are null
here while the Azure arm has them. Nothing downstream reads those columns.

## What the agreement report gives you without any annotation

* a behavioural profile per model — detection rate with Wilson intervals, events
  per document, and the **admin-level mix**, which is the most direct read
  available on whether the sub-national location rule landed, and needs no gold
  at all;
* measured cost and throughput per model;
* `outputs/disagreement_queue.csv` — the 167 ranked by how evenly the roster
  splits on "does this document carry a verifiable event?". Those are where a
  human judgement is worth the most, so it doubles as an annotation order.

## Notes on the roster

`models.py` sets `reasoning_effort` and `structured_output` from each model's
advertised `supported_parameters`, not from assumption, and `--check-models`
re-verifies both against the live catalogue and warns when a spec has drifted.
Model ids move constantly — run it before every campaign.

`medium` reasoning effort matches `AZURE_OPENAI_REASONING_EFFORT` on the
production arm, so reasoning models are compared on the production setting rather
than their own defaults. The two models that cannot reason simply have no
equivalent knob; that is a confound, not a handicap applied on purpose.

**Some models will fail, and that is a result.** `qwen/qwen3-235b-a22b` in
particular degenerates into a repetition loop under this prompt and hits the
token cap without producing a JSON object. It is not special-cased. Failures land
as `ERROR:` rows and surface in the report's error column, which is where a
model that cannot hold the format belongs.
