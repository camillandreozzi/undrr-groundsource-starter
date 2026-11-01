# Experiment A — Event-level evaluation: pre-registered protocol

**Status:** frozen at the commit that adds this file, before any window is
annotated or scored. `eval/EVENT_LEVEL_SCORES.md` prints the commit it ran
against and flags uncommitted edits. Any change after freezing goes in
[§10 Deviations](#10-deviations-log), appended and dated, never edited in place.

Drafted 2026-10-31.

## 0. Question

> Does the pipeline correctly associate hazard, time and affected locations with
> the same reported event?

The published evaluation (`eval/score_against_human.py`) cannot answer this. It
unions each document's gold hazards, dates and locations, and compares them with
the union of a run's events. Take a document reporting *Flood / 2020 / Thailand*
and *Drought / 2022 / India*. A run that emits *Flood / 2022 / India* and
*Drought / 2020 / Thailand* scores 100% on every field there, although neither
record is right.

The existing gold cannot be reused. It is one row per document, with three
unlinked lists. It was also annotated with the production run's output shown
as a seed, and it is byte-identical to that seed on 76–91% of fields
(`docs/VALIDATION_METHODS.md`).

**Primary outcome.** Complete-record correctness of prompt 5 (production run,
GPT-5 on Azure), reported separately for single-event and multi-event windows.

**Secondary outcomes.**
- Event detection precision and recall.
- Complete-record recall.
- Event-level attribute F1.
- The pooling gap.
- The misassociation share.
- All of the above for every other system.

## 1. Unit and annotation guideline

**Unit.** One *window* is the first 12,000 characters of a document: exactly
the text every system was given (`app_event_focus.trim_text`). The texts are
read from `eval/annotation_documents.json` and
`eval/annotation_documents_document_sample.json`. They are byte-identical to
the OpenRouter snapshot.

**Blind annotation.** The annotation app (`eval/event_annotation_app.py`) shows
the window, its title and a link to the source. It does not show:
- any model output;
- the earlier annotation;
- the sampling stratum.

**What counts as an event.** One event is one concrete past or current
occurrence of a hazard.
- **Cascades.** A cascade from one trigger that the text tells as one
  occurrence (earthquake → tsunami, cyclone → flood/landslide) is **one** event.
  Its primary hazard is the trigger; the cascade hazards are secondary.
- **Same hazard, different years** → **separate** events.
- **Same hazard and year, separate occurrences.** If the text tells them as
  separate occurrences in unconnected places, they are **separate** events. One
  named event over many places ("the 2010 Pakistan floods") is **one** event.
- **Multi-year events.** A multi-year drought or epidemic is one event with a
  year span.
- **Not events:** forecasts, scenarios, simulations, exercises, projects,
  meetings, and generic recurrence ("floods hit X every year"). This mirrors
  prompt 5 (`src/fonte/prompts.py`).

**Fields per event.**

| Field | Rule |
|---|---|
| `hazard_primary` | One label from the PreventionWeb vocabulary (`benchmark_ner.hazard_lexicon.ALL_LABELS`), the list the models were given. |
| `hazard_secondary` | Cascade hazards, same vocabulary. |
| `year_start`, `year_end` | Four-digit years stated in the window, never the publication year. A single year is entered as the start year alone. Timing coarser than a year (a decade, "recently") → leave blank. |
| `date_text` | Optional: the date as written. Not scored. |
| `locations` | Every place the window names as directly affected by *this* event, at every level it names (country and sub-national), as written, one per line. Downwind or receiving regions are excluded (prompt 5's location rule). |
| `support_quotes` | Verbatim quotes from the window, one per line. Quote every passage that reports this occurrence, up to 5; at minimum the one that names it. The app refuses a quote it cannot find verbatim. |
| `verifiable` | `yes` when the window states the hazard, a time (at least a year) and at least one directly affected place: prompt 5's own bar. Concrete events that miss one are still recorded, as `no`. |

**Per window.**
- The annotator records whether the window reports any concrete event.
- If it does, the annotator confirms that every event is listed.
- Time spent is logged.

## 2. Sampling

**Frame.** The 217 documents already annotated at document level
(`eval/human_annotations_pooled.csv`: the 167-document event arm plus the
50-document random arm).

**Exclusions**, in order, with counts computed from the frame before the draw:

| Exclusion | Rule | Documents |
|---|---|---:|
| No event in the earlier annotation | `gold_is_event != yes` | 46 |
| Not English | `citation_quality.guess_language(window) != "en"` | 22 |
| Workload cap | more than 8 distinct years in the earlier annotation | 3 |
| **Eligible** | | **146** |

**Strata.** Strata come from the earlier human annotation only, never from model
output. They use the scorer's rules: hazards via `event_matching.hazard_key`,
years via `score_against_human._years`. The pooled annotation does not say
which year goes with which hazard, so these are proxies. Results are reported
both by stratum and by the new gold's own event count.

| Stratum | Earlier annotation | Purpose | Eligible | Drawn |
|---|---|---|---:|---:|
| `single` | ≤1 hazard key, ≤1 year | control | 60 | 15 |
| `same_hazard_multi_year` | 1 hazard key, ≥2 years | matching on hazard fails here | 32 | 10 |
| `multi_hazard_same_year` | ≥2 hazard keys, ≤1 year | hazard and place can swap | 11 | 10 |
| `multi_hazard_multi_year` | ≥2 hazard keys, ≥2 years | the reviewers' example | 43 | 10 |

**Draw.**
- Uniform within each stratum, over eligible windows sorted by `asset_key`.
- Seed 44 (42 and 43 drew the earlier samples).
- The combined queue is then shuffled, so the annotator meets the strata
  interleaved.
- If a stratum has fewer eligible windows than its allocation, all are taken
  and the shortfall moves to `multi_hazard_multi_year`.
- Script: `eval/sample_event_level_windows.py`. It writes
  `eval/event_level_queue.csv` and `…_summary.json`, and refuses to overwrite
  an existing queue.

**Framing.** Multi-event windows are deliberately over-sampled, so this is a
**targeted stress test**. No figure is weighted back to the corpus, and none is
reported as an estimate of archive-wide accuracy. Two further limits:
- 157 of the 171 event-bearing documents in the frame come from the event arm,
  which entered the earlier evaluation *because* prompt 5 found an event in
  them. Detection recall here is therefore conditional on the document having
  been found.
- The annotator has seen these documents before, in the earlier seeded pass.

## 3. Systems

Every run over the frame is scored with no new inference:

| Group | Systems | Source |
|---|---|---|
| Production | prompt 5 (GPT-5, Azure) | `outputs/event_extractions/event_extractions.jsonl` |
| Non-LLM baseline | NER baseline | `benchmark_ner/outputs/ner_extractions.jsonl` |
| OpenRouter, prompt 5 held fixed | every run in `benchmark_openrouter/outputs_pooled/` | one folder per model |

**Rules.**
- Only rows with `is_verifiable_event == true` are records.
- A window a system returned only error rows for is excluded from that system's
  denominator and reported as coverage. This is error policy `exclude`, as in
  `score_against_human.py`.
- A system that returned no window is listed and not scored. At freezing,
  Gemini 2.5 Pro and Qwen3 235B errored on every document, and Gemini 2.5 Flash
  is absent from the pooled runs.

## 4. Matching (`eval/event_matching.py`)

Each predicted record is paired with **at most one** gold event, and each gold
event with at most one record. The record's hazard is **never** used to
establish identity. Fields are scored only after the pairing is fixed.

**Locating text.**
- All spans index the window after whitespace normalisation and casefolding.
- Gold support quotes are located with `human_annotation_app.locate_snippet`.
- A predicted evidence snippet first has wrapping quote marks stripped. It is
  then located with `locate_snippet`, or failing that with rapidfuzz
  `partial_ratio_alignment` ≥ 90 (`citation_quality.NEAR_VERBATIM`).
- Each gold event's *support context* is its quote spans, widened to the
  enclosing sentence and by at most 400 characters each way.

**Identity tiers**, per (record, gold event):

| Tier | When | Eligible if | Score |
|---|---|---|---|
| **A**, anchored | a located snippet | ≥ 0.5 of the snippet's characters lie inside the gold event's support context | context share + share inside the raw quotes (max over snippets) |
| **B**, paraphrase | a snippet that cannot be located | ≥ 0.5 of its content words (`citation_quality.content_words`) occur in the support context (`WEAK_COVERAGE`) | the coverage |
| **C**, context | a record with no A/B link after assignment | its years overlap the gold span **and** ≥ 1 location matches (§5 location rule) | — |

A located snippet is judged only by where it sits. It never gets a second
chance on vocabulary.

**Assignment.**
- Per window, `scipy.optimize.linear_sum_assignment` maximises over tier-A/B
  pairs, lexicographically:
  1. the number of tier-A links;
  2. the summed identity score, rounded to 0.001;
  3. the summed *occurrence context* — years overlap (+1) and a location
     matches (+1), never the hazard;
  4. rank order (the i-th record by `event_index` with the i-th gold event by
     id).
- Then tier C: records still unmatched, in `event_index` order, each take the
  free gold event with the most matching locations among those that qualify.
  Ties go to the lowest id.

**Unmatched records and events.**
- An unmatched record is a **false positive**. A record with no corresponding
  gold event always counts.
- An unmatched `verifiable=yes` gold event is a **false negative**.
- A `verifiable=no` gold event can be matched (the record is then not a false
  positive), but is never required (it is never a false negative).

**Diagnostics.** These are reported and change no score.

| Label | Applies to | Meaning |
|---|---|---|
| `split` | false positive | Its identity points at a gold event another record took. |
| `no_event` | false positive | No gold event it could be. |
| `merge` | false negative | A record matched elsewhere carries its evidence. |
| `missed` | false negative | No record does. |

## 5. Field rules

Each field has a primary *association* reading and a secondary *exact* reading.
A field is association-correct when it carries this event's values and nothing
that belongs elsewhere.

| Field | Values compared | Association-correct (primary) | Exact (secondary) |
|---|---|---|---|
| Hazard | Labels split on `\|`, mapped by `hazard_key` (the `hazard_family`, except that inside `other` the label itself is kept, so Epidemic ≠ Cold Wave) | the primary hazard's key is among the record's keys, and every record key belongs to the event (primary ∪ secondary) | label sets equal |
| Year | Four-digit years in `event_dates` (`_years`) | at least one year, and all inside [`year_start`, `year_end`] | min = start and max = end |
| Location | rapidfuzz `token_set_ratio` ≥ 90 after accent folding and `default_process` (the published normalised rule; an appended parent such as "Louisville, Kentucky" matches "Louisville") | at least one location, and every record location matches one of this event's gold locations | also every gold location matched |

**Complete record** = matched, and all three fields association-correct.

**Attribute counts** (TP/FP/FN, for F1):
- **Hazard:** key sets.
- **Year:** the endpoint sets {min, max} against {start, end}.
- **Location:** greedy one-to-one pairs (`score_strict_rules._greedy`).
- An unmatched record contributes all its values as FP. A missed verifiable
  event contributes all of its values as FN.

**Misassociation.** A wrong value in a matched record is *misassociated* if it
is correct for another gold event in the same window: a hazard key in that
event's keys, a year inside its span, or a location matching one of its
locations. Otherwise it is *unsupported*. A predicted year that falls inside
the right span but is not an endpoint is an imprecision and counts as neither.

## 6. Metrics and reporting (`eval/score_event_level.py`)

**Per system:**

| Metric | Definition |
|---|---|
| Detection P | matched records / records |
| Detection R | matched verifiable gold events / verifiable gold events |
| Detection F1 | harmonic mean of P and R |
| **Complete-record correctness** | complete records / **all** records |
| Complete-record recall | verifiable gold events with a complete record / verifiable gold events |
| Event-level attribute F1 | per field, and pooled over the three fields |
| Field agreement conditional on match | association and exact rates over matched pairs |
| **Pooling gap** | document-level pooled F1 (union of all gold events' values against the union of all records' values, same value rules) minus event-level attribute F1, on the same windows |
| Misassociation share | misassociated / (misassociated + unsupported), per field |

**Groups.**
- **Single-event** windows (exactly 1 verifiable gold event) and **multi-event**
  windows (≥2) are always reported side by side.
- Windows with no verifiable gold event appear in the overall figure only.
- Each sampling stratum is reported separately.

**Uncertainty.**
- 95% percentile cluster bootstrap over windows: 2,000 resamples, seeded
  from 42 and the system and group names.
- Wilson intervals are shown beside the record-denominated rates; they treat
  records as independent and are narrower.
- Paired difference against prompt 5 in complete-record correctness, on the
  windows both returned, with a paired cluster bootstrap.

**Sensitivity bound.** The same metrics under a field-maximising one-to-one
alignment that ignores evidence and maximises complete records first, then
agreeing fields. This is the most generous reading any matcher could give. It
is labelled as such and never quoted as the result.

**Link audit.**
- After scoring, `make event-audit-sample` draws every tier-C link, 25 tier-A/B
  links and 15 false positives, pooled across systems with seed 45.
- The annotator marks each `agree` or `disagree`.
- Agreement is reported by decision type. It checks the matcher and changes no
  figure.

**Outputs.**

| File | Contents |
|---|---|
| `eval/EVENT_LEVEL_SCORES.md` | the report; its header carries the gold file's sha256 and this file's commit |
| `eval/event_level_pairs.csv` | every link and every unmatched record or event: the audit trail |
| `eval/event_level_scores.json` | everything, for the paper tables |

## 7. Commitments

- Every system, every group and every stratum is reported, including those
  that look bad.
- The primary outcome is quoted as single-event against multi-event for
  prompt 5. A pooled figure is never quoted without that split.
- No rule above is changed after annotation begins without an entry in §10. If
  a change is made, results under the original rule are reported alongside.
- The scorer refuses to run until all queued windows are annotated
  (`--allow-partial` is for previews only and stamps the report PARTIAL).

## 8. Limitations to disclose

- **Single annotator.** No inter-annotator agreement is reported.
  - Optional mitigation: blind re-annotation of 8 seeded windows, at least 7
    days later, scored gold-against-gold with the same matcher, as
    intra-annotator agreement.
  - The annotator has seen these documents before, in the earlier seeded pass.
- **Sampling bias.** A stress test over-sampled for multi-event windows; and
  for the event arm, conditional on prompt 5 having found an event (§2).
- **English only.** English windows only.
- **Small sample.** 45 windows; small strata have wide intervals.
- **Matcher depends on evidence.** A record whose evidence is a translation or
  a loose paraphrase can only link through tier C. Tier counts and the link
  audit show how often this happens.

## 9. Procedure

```
make event-sample          # draw the queue (seed 44); refuses to redraw
make event-annotate        # blind annotation, 45 windows
make event-score           # all systems -> EVENT_LEVEL_SCORES.md (refuses until complete)
make event-audit-sample    # draw the link audit; mark verdicts; re-run make event-score
```

## 10. Deviations log

_None yet. Append dated entries below; do not edit entries above._

### 2026-11-01 — Gold correction in one window (`823c2dca5fb0…`, review rank 29)

**What changed.** Two annotation errors in the gold for the Terranova di
Pollino local progress report:
1. Gold event 1 (Earthquake, 1980): the location was misspelt "Tarranova di
   Pollino". It now reads "Terranova di Pollino", as the window spells it.
   Nothing else in the row changed.
2. The window reports a second earthquake, in 1998 ("coped with the emergency
   caused by the earthquake occurred in 1998"). It was omitted at annotation.
   It is added as gold event 2: Earthquake, 1998, the same locations as event 1,
   verifiable, with that sentence as its support quote.

**How it was found.** Through the link audit (§6), decision #80: a system's
1998 record had been linked to the 1980 event. The omission was therefore
found through a model's output, not by re-reading the window blind. A check of
the whole gold that uses no model output was run the same day: locations
written as in the window, years stated in the window, support quotes located.
It flagged further entries. This entry changes none of them.

**Files.**
- `eval/event_level_gold.csv`: sha256
  `0b519b58df4d78493fa27578110e7626723aa8867f7656e94618cd2d25003440` →
  `5c66d9f9305e0be698a3414fb363ba70634e407e18953d2fe434254eb4d91c7c`.
  The original, with the scores it produced, is in commit `153bdf8`.
- `eval/event_level_windows.csv`: `n_events` 1 → 2 for this window.

**Consequences.**
- The window moves from single-event to multi-event. Windows: 11 single /
  33 multi → 10 / 34. Verifiable gold events: 169 → 170.
- The link audit (§11) was judged on links made against the original gold.

**Effect, original gold → corrected gold** (§7: both are reported).

| Prompt 5 (primary outcome) | Original | Corrected |
|---|---:|---:|
| Complete-record correctness, all windows | 58.4% (48.2–68.9) | 60.2% (50.0–70.8) |
| Single-event windows | 36.8% (15.8–64.3) | 41.2% (20.0–71.4) |
| Multi-event windows | 63.4% (52.3–75.9) | 64.2% (54.1–76.6) |

Other systems: complete-record correctness changes by 0.0 to +1.8 pp. The NER
baseline is unchanged at 1.9%.
