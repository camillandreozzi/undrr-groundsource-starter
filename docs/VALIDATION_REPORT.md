# Event extraction — validation report

**Run:** `outputs/event_extractions/` (prompt 5, `gpt-5`, `make extract --limit 10000`)
**Extraction date:** 2026-08-07 · **This report:** 2026-09-05
**Status:** counts and methodology final; accuracy figures pending the judging pass.

> **Unit of analysis.** This report describes **10,000 documents**. The output
> file carries 11,659 rows because a multi-event document contributes one row
> per event — 1,659 rows more than there are documents. Every corpus statistic
> below is therefore stated **per document (N = 10,000)**; figures that are
> intrinsically per event are labelled **(events, n = 3,572)** and figures that
> are per location mention are labelled as such. No statistic in this report is
> computed over the raw row count.

---

## 1. What was measured

This run had never been validated. The QA statistics on file described a
different, earlier file (11,628 rows, both boolean columns unparsed), and the
previous gold review targeted `outputs/gold` — a separate 2,000-document run —
where 3 of 100 queued events were ever judged.

Three things were rebuilt against the current output:

1. **Counts** — regenerated from the actual CSV, at document level.
2. **Event validation** — a 175-event representative sample, queued for a
   correct / partial / wrong verdict.
3. **Polygon validation** — a 60-row representative sample of resolved and
   unresolved locations.

## 2. Corpus and extraction counts

| | |
|---|---|
| **Documents processed** | **10,000** |
| Rows in `event_extractions.csv` | 11,659 (one row per event) |
| Columns | 23 |
| **Verifiable events extracted** | **3,572** |
| Documents yielding ≥1 event | 1,913 (**19.1%**) |
| Documents yielding none | 8,087 (80.9%) |

Four fifths of the corpus produces no event. That is expected — the corpus is
largely guidance, frameworks and reports rather than event reporting — but it
means the extraction rate is a property of the corpus, not a quality signal.
Every zero-event document carries the same reason string,
`no verified reliable event extracted`.

### Events per document

| Events | Documents | Share |
|---|---:|---:|
| 0 | 8,087 | 80.9% |
| 1 | 1,187 | 11.9% |
| 2 | 385 | 3.9% |
| 3 | 158 | 1.6% |
| 4 | 71 | 0.7% |
| 5–10 | 101 | 1.0% |
| >10 | 11 | 0.1% |

Mean 1.87 events per event-bearing document; maximum 40.

### Source-metadata coverage (documents)

`language`, `countries`, `themes`, `hazards`, `organizations` and
`publication_year` are upstream Databricks fields, not extraction outputs. They
describe the corpus.

| Field | Documents with a value | Share | Distinct values | Mean values/doc |
|---|---:|---:|---:|---:|
| `language` | 10,000 | 100.0% | 5 | 1.00 |
| `themes` | 9,271 | 92.7% | 47 | 3.14 |
| `organizations` | 7,615 | 76.1% | ~2,346 | 1.42 |
| `countries` | 7,046 | 70.5% | 256 | 2.51 |
| `publication_year` | 6,426 | 64.3% | 38 | 1.00 |
| `hazards` | 2,740 | 27.4% | 23 | 1.75 |

Document length (`char_count`): mean 83,422 · median 30,040 · p10 3,722 ·
p90 205,465 · max 18,213,518.

Most-frequent values, as a share of the 10,000 documents:

| Theme | | Source hazard tag | | Country tag | |
|---|---:|---|---:|---|---:|
| Governance | 39.0% | Flood | 10.7% | Asia | 6.5% |
| Preparedness | 37.4% | Earthquake | 7.3% | Europe | 5.8% |
| Climate change | 26.4% | Drought | 6.0% | Africa | 4.9% |
| Risk identification and assessment | 14.9% | Cyclone/Hurricane/Typhoon | 4.5% | India | 4.8% |
| Capacity development | 13.5% | Tsunami | 4.3% | United States of America | 3.9% |

Top organizations: UNDRR 8.0%, World Bank 3.6%, FAO 1.8%, ADPC 1.7%,
GFDRR 1.7%. See limitation 4 on the reliability of these fields.

### Language (documents)

English 9,891 (**98.9%**), Spanish 52, Arabic 27, Japanese 16, French 14. The
non-English tail is too small to support per-language quality claims.

### Content type (documents)

| Type | Documents | Share | With ≥1 event | Extraction rate |
|---|---:|---:|---:|---:|
| publication | 6,758 | 67.6% | 1,580 | 23.4% |
| event (meeting/conference page) | 2,086 | 20.9% | 185 | 8.9% |
| news | 718 | 7.2% | 141 | 19.6% |
| vacancy | 431 | 4.3% | 7 | 1.6% |
| unknown | 7 | 0.1% | 0 | 0.0% |

By domain: preventionweb.net 7,263 (72.6%), undrr.org 2,696 (27.0%),
recovery.preventionweb.net 32 (0.3%), unknown 7 (0.1%).

The 4.3% vacancy slice is noise for this purpose — job adverts cannot contain
events — and the 1.6% extraction rate on it is consistent with that.

### Publication year and events per year

`publication_year` is populated for 95% of `/publication/` pages and for **0%**
of event, news and vacancy pages, so the 35.7% missing rate is structural
rather than an extraction failure.

Two readings of "events per year" are given: by the year the event occurred
(parsed from `event_dates`) and by the publication year of the source document.

| Year | Documents published | Doc share | Events (by doc pub. year) | Events (by event date) |
|---|---:|---:|---:|---:|
| pre-1900 | 0 | – | 0 | 76 |
| 1900–1949 | 0 | – | 0 | 89 |
| 1950–1979 | 0 | – | 0 | 141 |
| 1980–1989 | 2 | 0.0% | 0 | 133 |
| 1990 | 1 | 0.0% | 0 | 14 |
| 1991 | 1 | 0.0% | 1 | 26 |
| 1992 | 2 | 0.0% | 0 | 16 |
| 1993 | 4 | 0.0% | 4 | 18 |
| 1994 | 14 | 0.1% | 0 | 24 |
| 1995 | 4 | 0.0% | 2 | 60 |
| 1996 | 2 | 0.0% | 0 | 12 |
| 1997 | 10 | 0.1% | 2 | 28 |
| 1998 | 11 | 0.1% | 0 | 61 |
| 1999 | 16 | 0.2% | 8 | 80 |
| 2000 | 33 | 0.3% | 29 | 46 |
| 2001 | 57 | 0.6% | 31 | 86 |
| 2002 | 37 | 0.4% | 70 | 50 |
| 2003 | 63 | 0.6% | 28 | 121 |
| 2004 | 111 | 1.1% | 48 | **231** |
| 2005 | 196 | 2.0% | 113 | 157 |
| 2006 | 195 | 1.9% | 80 | 80 |
| 2007 | 245 | 2.5% | 124 | 98 |
| 2008 | 259 | 2.6% | 104 | 155 |
| 2009 | 434 | 4.3% | 172 | 122 |
| 2010 | 394 | 3.9% | 185 | 236 |
| 2011 | 375 | 3.8% | 103 | **322** |
| 2012 | 369 | 3.7% | 172 | 114 |
| 2013 | 430 | 4.3% | 173 | 141 |
| 2014 | 612 | 6.1% | 153 | 100 |
| 2015 | 389 | 3.9% | 177 | 122 |
| 2016 | 301 | 3.0% | 163 | 94 |
| 2017 | 454 | 4.5% | 224 | 133 |
| 2018 | 411 | 4.1% | 183 | 99 |
| 2019 | 359 | 3.6% | 249 | 80 |
| 2020 | 393 | 3.9% | 224 | 109 |
| 2021 | 210 | 2.1% | 87 | 11 |
| 2022–2025 | 32 | 0.3% | 1 | 0 |
| No / unparsable year | 3,574 | 35.7% | 662 | 87 |
| **Total** | **10,000** | **100%** | **3,572** | **3,572** |

Event-date peaks fall where expected: 2004 (Indian Ocean tsunami), 2010
(Haiti), 2011 (Tōhoku). Coverage effectively ends in 2021. One event date
parses to 2072 — `2072 Baishakh 12`, a Nepali-calendar string — and is counted
in the unparsable row.

### Confidence (events, n = 3,572)

| Level | Events | Share |
|---|---:|---:|
| high | 1,955 | 54.7% |
| medium | 1,617 | 45.3% |
| low | 0 | 0% |

The model never emits `low`, so confidence is a two-level signal here.

### Hazard families (events, n = 3,572)

| Family | Events | Share |
|---|---:|---:|
| earthquake (incl. tsunami) | 1,227 | 34.4% |
| flood | 838 | 23.5% |
| cyclone / storm | 384 | 10.8% |
| other | 358 | 10.0% |
| drought | 262 | 7.3% |
| volcano | 163 | 4.6% |
| wildfire | 162 | 4.5% |
| landslide | 101 | 2.8% |
| heat | 77 | 2.2% |

Rolled up from 50 distinct `event_hazard` values via
`fonte.hazard_families`. Compound hazards resolve to their first
matching family, so `Earthquake | Tsunami` counts as earthquake.

### Geocoding (location mentions)

| | |
|---|---|
| Location mentions (in the 3,572 events) | 5,463 |
| Resolved to a geometry | 4,435 (**81.2%**) |
| Unresolved | 1,028 (18.8%) |
| **Documents with at least one geometry** | **1,686 (16.9% of 10,000)** |
| Mean resolver confidence | 0.772 |
| Used a fallback query | 171 |
| Flagged as geometry overshoot | 20 |

Admin levels skew usefully specific: city 1,586, admin1 1,331, other 784,
country 314, admin2 301, neighbourhood 119.

### QA flags (documents)

The previous version of this report quoted "2,391 of 11,659 rows flagged", of
which 2,385 were `duplicate_asset_key`. That flag fires on every row of a
multi-event document — it is a restatement of the 1,659 extra rows, not a
defect, and it disappears entirely at document level.

Counting distinct documents, and excluding `duplicate_asset_key`:

| Flag | Documents |
|---|---:|
| too_many_locations (>10) | 8 |
| too_many_dates (>5) | 1 |
| too_many_impacts (>5) | 0 |
| error_in_key_impacts | 0 |
| single_but_not_verifiable | 0 |
| verifiable_but_missing_hazard | 0 |
| missing_title | 0 |

**9 of 10,000 documents (0.09%)** carry a substantive flag.

## 3. Methodology

### Sampling

Both queues are **random samples drawn to mirror the population**, which is
what allows the results to be reported as accuracy estimates rather than as
observations about whichever rows looked suspicious.

- **Events** — 175 of 3,572, allocated across hazard families in proportion to
  their population share and drawn uniformly within family (seed 42). The
  queue matches the population within 0.3pp on every family, and independently
  on dimensions it was not stratified on: 54.9% high-confidence against 54.7%
  in the population, mean `auto_risk` 0.591 against 0.592.
- **Polygons** — 60 rows allocated across `high_confidence` / `low_confidence`
  / `unresolved` in proportion to pool size (29 / 20 / 11), drawn from a 400-row
  stratified sample.

The alternative mode, `--sampling risk`, ranks by a label-free risk heuristic
and over-weights hard cases. It is better at surfacing failure modes but yields
a lower bound rather than an estimate; it was not used here.

### Judging

One verdict per event — **correct** / **partial** / **wrong** — in
`eval/gold_validation_app.py`, which shows the extraction beside the source
document. Two headline rates:

- `accuracy` = correct / judged
- `useful_rate` = (correct + partial) / judged

Polygons are judged per field: location, geometry, admin level, dates.

### Precision

Every rate carries a 95% Wilson score interval. At n=175 the overall margin is
about **±6pp**; per-family cells run from ±10pp (earthquake, n=60) to ±30pp
(heat, n=4). Family-level numbers are directional; the overall figure is the
one to quote.

## 4. Results

**Not yet available — the judging pass has not been run.** Both queues are
built and unjudged (175 events, 60 polygon rows).

```
make prod-validate         # then: make prod-validation-score
make prod-polygon-validate # then: make prod-polygon-score
```

Scoring writes `eval/production_validation_scores.csv` (overall, by hazard
family, by raw hazard) and `eval/PRODUCTION_POLYGON_VALIDATION.md`.

## 5. Limitations

1. **1,956 documents extracted but not in this file.**
   `event_extractions_progress.jsonl` holds 13,899 records across 11,956
   documents; the finalized CSV covers 10,000. A later run was interrupted
   before the compaction step. **The validated population is the 10,000
   documents, and nothing in this report draws on the surplus records.**
2. **No confidence calibration — by construction, not by accident.**
   `event_confidence_logprob` and `event_confidence_prob` are empty for every
   event in the run, so stated confidence cannot be checked against token-level
   probability. The cause is an either/or in the extractor
   (`app_event_focus.py:611-616`): `logprobs=True` is requested *only* when no
   reasoning effort is set, because reasoning models do not return token
   logprobs. `.env` sets `AZURE_OPENAI_REASONING_EFFORT = low` and
   `make extract` does not override it, so every call took the reasoning branch.
   The only run in the repo carrying any logprobs is `outputs/gold` (123 of
   2,393), assembled across resumed invocations where the effort was unset.

   Note `--reasoning-effort none` does **not** re-enable them — the string
   `"none"` is truthy and still takes the reasoning branch. Only
   `--reasoning-effort ""` or an unset env var does. Recovering calibration
   therefore means re-extracting without reasoning, which changes extraction
   behaviour as well: it is a trade-off, not a configuration fix.
3. **Two confidence levels, not three.** No `low` values are emitted.
4. **Source metadata is noisy.** `countries`, `themes`, `hazards` and
   `organizations` come from the upstream Databricks tables, not from
   extraction. `countries` mixes continents with countries (Asia 647 documents,
   Europe 575) and shows implausible ranks (Algeria 379, Andorra 267);
   `organizations` is split naively on `", "`, so names containing a comma
   fragment — the literal token `"the"` appears in 493 documents. These describe
   the corpus, not extraction quality, and the distinct-value counts in §2 are
   upper bounds for that reason.
5. **English-dominated.** 98.9% of documents; other languages cannot be
   assessed separately.
6. **Single judge.** No inter-rater agreement is measured, so verdicts carry
   the judge's interpretation of "partial".

## 6. Reproducing this

```
make qa                      # counts, flags, plots
make prod-prefill-validation # event queue      (seeded, deterministic)
make prod-polygon-sample     # polygon sample   (seeded, deterministic)
make prod-polygon-prefill    # polygon queue
```

All sampling is seeded (42), so the queues regenerate identically. See
`eval/README.md` for the full runbook.

Note that `make qa` (`scripts/visualize_event_extractions.py`) reports at **row**
level, including the `duplicate_asset_key` flag and per-row language counts. The
document-level figures in §2 were derived from the same CSV by collapsing on
`asset_key`; the two will not match line for line, by design.
