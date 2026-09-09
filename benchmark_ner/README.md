# NER benchmark — a non-LLM baseline for the event extraction

## Why this exists

`outputs/event_extractions/` is the production run: 10,000 documents through
prompt 5 / `gpt-5`, yielding 3,572 verifiable events over 1,913 documents, with
5,463 location mentions geocoded at an 81.2% resolution rate. Its accuracy is
measured — `eval/production_validation.csv` holds a representative 175-event
queue, judged by hand.

What that does not tell you is **how much the LLM is buying**. An accuracy
figure with nothing to compare it against cannot answer "would a classical
pipeline have done as well, for free?" This folder builds that comparison: a
spaCy NER + gazetteer baseline over the same documents, geocoded by the same
Nominatim resolver, and judged in the same review app against the same 175
events.

## The design decision everything rests on

`ner_extract.py` writes the **exact `event_extractions` schema**
(`fonte.app_event_focus.OUTPUT_HEADERS` — identical CSV header, same
JSONL keys). Every downstream tool in the repo therefore runs on the baseline
unchanged:

| Tool | Used unchanged? |
|---|---|
| `fonte-polygons` | yes — same resolver, ladder, coastal clipping, confidence |
| `eval/gold_validation_app.py` | yes — via `GOLD_VALIDATION_CSV` |
| `eval/prefill_gold_validation.py` | yes |
| `scripts/visualize_event_extractions.py` | yes |

That is what makes the comparison fair. Both runs are geocoded and judged by
identical machinery; the only difference is what produced the events.

## What the baseline actually does

1. **Hazards** — regex over the same PreventionWeb label vocabulary the LLM was
   given (`hazard_lexicon.py`, transcribed from
   `fonte.prompts.PREVENTIONWEB_HAZARD_INSTRUCTION`), so `event_hazard`
   strings are directly comparable and roll up through
   `fonte.hazard_families` identically.
2. **Entities** — spaCy `en_core_web_lg`: `GPE`/`LOC`/`FAC` for locations,
   `DATE` for dates.
3. **Event assembly** — a ±1-sentence window around a hazard mention that
   contains at least one location *and* one normalisable date becomes a
   candidate. Candidates are grouped by the hazard labels in their window, so
   "the earthquake and the tsunami that followed" yields one
   `Earthquake | Tsunami` event, matching the LLM's convention.
4. **Same input window** — documents are trimmed to 12,000 characters, exactly
   what `--max-chars` gave the LLM.

Fields the baseline genuinely cannot infer are not faked. `evidence_snippets`
holds the matched sentences (real, and what a reviewer needs on screen);
`key_impacts` holds window sentences with impact language; `missing_information`
records which of hazard/date/location was weak.

## Runbook

```bash
make ner-setup                 # spaCy + en_core_web_lg (one-off)
make ner-fetch                 # same Databricks query, 12k-char window
make ner-extract NER_LIMIT=200 # smoke run first
make ner-extract               # full 10,000
make ner-preflight             # READ THIS before the next step
make ner-polygons              # same resolver, shared Nominatim cache
make ner-compare               # -> benchmark_ner/COMPARISON.md
make ner-prefill-validation    # paired queue + NER-only arm
make ner-validate              # judge the paired 175
make ner-validate-only         # judge the NER-only arm
make ner-score                 # -> benchmark_ner/PAIRED_VALIDATION.md
```

**`make ner-preflight` is not optional.** Geocoding is the long pole: the public
Nominatim endpoint is throttled to ~1.1 s per request and the baseline emits
more distinct location strings than the LLM's 5,463. The pre-flight counts how
many are already in the shared 583 MB `.nominatim_cache.json` and prints a floor
on the wall clock. If that number is large, run
`fonte-polygons --limit N` for a first pass.

## Reading the results

There are two reports and they answer different questions. Do not mix them up.

### `COMPARISON.md` — agreement, **not** accuracy

Produced by `compare.py` on the documents both runs share. The LLM output is the
reference only arithmetically; where the two disagree, this says nothing about
which is right. Contains the document-level 2×2 and Cohen's kappa (raw agreement
is meaningless when four fifths of the corpus yields nothing), hazard-family
agreement, location and date set P/R/F1 (exact and fuzzy), the geocoding
comparison, and polygon IoU in equal-area EPSG:6933.

### `PAIRED_VALIDATION.md` — accuracy, in three arms

Produced by `score_paired.py`.

- **Arm 1** needs no new judging. For LLM events humans have already judged, it
  reports how often the baseline agreed, split by verdict. If agreement is flat
  across correct/partial/wrong, then `COMPARISON.md` is not a quality proxy and
  only Arm 2 can rank the pipelines.
- **Arm 2** is the head-to-head. It joins the two queues on
  `(asset_key, event_index)`, counts only events judged on *both* sides, and
  reports each run's accuracy with Wilson intervals plus an **exact McNemar
  test** on the paired difference. McNemar rather than two independent
  proportion tests: the same events are judged twice, so the informative
  quantity is the discordant pairs.
- **Arm 3** is the baseline's extra-recall arm — events NER found in documents
  the LLM left empty. Without it, every metric would be defined on the LLM's own
  positives and the baseline could only ever look worse.

## Known limits

- **spaCy misses places it does not recognise as places.** "Gonaives" comes back
  as `ORG`, "Artibonite" as `ORG`; both are dropped. This is a real property of
  the baseline, not a bug to paper over — it is part of what the comparison is
  measuring.
- **Locations are capped at 10 per event** (`--max-locations`) to keep the
  geocoding run finite. The LLM run flagged >10 as anomalous, so the cap is not
  binding in normal cases, but it does bound recall on location-dense documents.
- **The corpus may drift.** `fetch_documents.py` re-runs the original
  `LIMIT 10000` query rather than pinning asset_keys, so it reports the overlap
  against the production run and refuses below `--min-overlap` (0.95). All
  comparison is restricted to the intersection.
- **The LLM run's cost is unrecorded.** No run log survives for the 10k
  extraction and the extractor does not persist token counts. `compare.py` says
  so rather than back-estimating; take the figure from Azure billing, or re-run
  both pipelines over an identical small sample.

## Files

| File | Purpose |
|---|---|
| `fetch_documents.py` | Databricks → `outputs/documents.parquet` + overlap check |
| `hazard_lexicon.py` | PreventionWeb labels as regexes |
| `ner_extract.py` | the baseline itself → `outputs/ner_extractions.{jsonl,csv}` |
| `geocode_preflight.py` | how many Nominatim lookups are uncached |
| `compare.py` | automatic agreement → `COMPARISON.md` |
| `prefill_paired_validation.py` | the paired queue + NER-only arm |
| `score_paired.py` | accuracy, McNemar → `PAIRED_VALIDATION.md` |

`outputs/` is gitignored (bulk artefacts). The judged queues
(`ner_paired_validation.csv`, `ner_only_validation.csv`) and both reports live
here in `benchmark_ner/` and are tracked — they are human labour.

Tests: `tests/test_benchmark_ner.py`, run by `make test`.
