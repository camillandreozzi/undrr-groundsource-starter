# What the validation against human annotation showed

**Annotations:** `eval/human_annotations.csv` — 167 documents, all `done`, single
annotator, median 70 s per document.
**Runs scored:** 13 OpenRouter runs of prompt 5 + the spaCy NER baseline.
**Scored by:** `eval/score_against_human.py`, document level, error-aware
(`--error-policy exclude`). Full output: `benchmark_openrouter/MODEL_SCORES.md`.
**The prompt-5 / `gpt-5` / Azure production run is excluded from every
comparison** — §1 gives the two reasons.
**This summary:** 2026-09-06, regenerated after the scorer was corrected (§8).

---

## 0. Headline

1. **No run demonstrated any ability to tell an event-bearing document from a
   non-event-bearing one.** Balanced accuracy runs 47.5–55.7% and MCC runs
   −0.06 to +0.15 across every working run. The 85–94% "accuracy" in the
   earlier tables was the 94% prevalence of the set, not a skill.
2. **Detection recall is saturated and undifferentiated.** 94.9–98.1% over all
   167 documents for every full-coverage frontier model, with no significant
   pairwise difference.
3. **Field extraction is where runs separate**, and the ordering is stable
   across hazard, locations and dates. Taking all three together per document
   (§5), the best working run is right about a document *completely* 45% of the
   time and most sit near a third — F1 in the eighties, exact match in the
   thirties.
4. **The metric was doing more of the ranking than the models were.** Fixing
   location matching moves runs by up to 40 points and reorders them; fixing
   date granularity moves everyone 10–20 points.
5. **Three runs are void and two have partial coverage.** Gemini 2.5 Pro/Flash
   and Qwen3 235B errored on 167/167 documents. DeepSeek returned only 113 of
   167, so its two recall figures — 65.6% over all documents, 97.2% over the
   ones it processed — are both reported, and §2 says which to quote when.

---

## 1. Why the prompt-5 Azure run is excluded

**Selection.** The 167 documents are the human-annotation queue, drawn from the
events the prompt-5 production run emitted. That run finds an event in 100% of
them by construction.

**Gold anchoring.** The annotation app seeds the gold form from the prompt-5
extraction and offers an *"Accept seed as gold"* button
([human_annotation_app.py:689](../eval/human_annotation_app.py#L689)). Over the
157 gold-positive documents, gold is byte-identical to that run's output for
hazards in 91%, dates 84%, locations 76%, impacts 75%; 101 of 157 documents were
saved with no edit to hazard, date or location at all.

The corrected scorer adds a third piece of evidence for the anchoring. Relaxing
location matching from exact to normalised-fuzzy is worth +9.8 to +40.3 points
to every other run — and **+1.6 points to prompt 5**, because gold is already
written in its surface form. A run that has nothing to gain from surface-form
tolerance is a run whose surface form *is* the gold standard.

**Consequence.** The gold is in prompt-5's dialect, so every other run's field
score is a floor. Relative comparisons among the non-excluded runs are
unaffected — they all pay the same penalty.

---

## 2. Documents processed, and the score relative to them

Every score in this report is computed over the documents a run actually
returned — a run cannot be credited or blamed for a document it never got back.
This table says how many that was, and gives the two readings side by side.

**On what it processed** is the model comparison: quality per document returned,
the only basis on which runs with different failure rates can be ranked against
each other. **Over the whole set** is the pipeline reading: the same quality
discounted by coverage — what this run would actually deliver across all 167
documents. The two differ only where a run failed calls.

The composite is a weighted mean of detection F1, hazard F1, location F1 and
date F1 (weights 1.0 / 1.5 / 1.5 / 0.5, carried over from
`eval/score_against_gold.py` so both scorers rank on the same priorities), on the
corrected matching rules.

| Run | Processed | Coverage | Recall (all docs) | Composite × coverage | Recall (processed) | Composite (processed) |
|---|---:|---:|---:|---:|---:|---:|
| GPT-5 (OpenRouter) | 167/167 | 100.0% | **98.1%** | 89.3% | 98.1% | 89.3% |
| Llama 4 Maverick | 167/167 | 100.0% | 98.1% | 76.0% | 98.1% | 76.0% |
| GPT-5.4 | 167/167 | 100.0% | 97.5% | **89.5%** | 97.5% | 89.5% |
| GPT-5 mini | 161/167 | 96.4% | 96.2% | 81.3% | 100.0% | 84.3% |
| Claude Opus 5 | 167/167 | 100.0% | 94.9% | 86.2% | 94.9% | 86.2% |
| Claude Sonnet 5 | 167/167 | 100.0% | 94.9% | 85.9% | 94.9% | 85.9% |
| Grok 4.6 | 167/167 | 100.0% | 94.9% | 85.5% | 94.9% | 85.5% |
| NER baseline | 167/167 | 100.0% | 90.4% | 59.4% | 90.4% | 59.4% |
| Claude Haiku 4.5 | 167/167 | 100.0% | 89.2% | 83.0% | 89.2% | 83.0% |
| Mistral Large | 167/167 | 100.0% | 79.6% | 67.1% | 79.6% | 67.1% |
| DeepSeek V3.1 | 113/167 | 67.7% | **65.6%** | **57.6%** | **97.2%** | 85.2% |
| Gemini 2.5 Flash | 0/167 | 0.0% | 0.0% | 0.0% | – | – |
| Gemini 2.5 Pro | 0/167 | 0.0% | 0.0% | 0.0% | – | – |
| Qwen3 235B | 0/167 | 0.0% | 0.0% | 0.0% | – | – |
| *prompt 5 (excluded)* | *167/167* | *100.0%* | *100.0%* | *97.0%* | *100.0%* | *97.0%* |

Sorted by recall over all 167 documents — the end-to-end column. Eleven of the
fourteen runs have identical left and right pairs, because they processed
everything; the table only does work on the three that did not.

**DeepSeek is the whole argument for the table.** It is the best run in the set
at finding events in the documents it processed (97.2%) and, on the
all-documents column, the worst working run (65.6%). Both numbers are true. The
first is a statement about the model, the second about a run with a 32% API
failure rate. Note that `Recall (all docs)` reproduces the previously published
figure exactly — the old discrepancy was never an arithmetic error, it was an
unlabelled denominator.

**Which column to quote depends on the question.** "Which model should we use?"
is answered by the processed columns, because a provider outage on the day of
the benchmark is not a property of the model. "What will this run give us over
the corpus?" is answered by the all-documents columns, because an event the
pipeline never returned is missing whatever the reason. Quoting either one alone
is defensible; quoting one while implying the other is not, which is why they sit
side by side.

**The three void runs get zeroes in the right-hand columns and dashes in the
left.** That is the correct shape: there is no model-quality reading for a run
that never reached the model, but there is a perfectly good pipeline reading, and
it is zero.

**A caution on the composite.** It compresses four metrics into one number and
inherits everything wrong with each — most importantly, detection F1 is
prevalence-driven on this set (§3), so a quarter of the composite's weight is
carried by a metric that separates nothing. Use it to sort the table, not to
claim GPT-5.4 beats GPT-5 by 0.2 points.

## 3. Event detection — and why accuracy was the wrong statistic

157 of 167 documents carry an event: **94% prevalence**. A run that flags
everything scores 94% accuracy and 94% precision without discriminating at all,
which is roughly what happened.

| Run | n | Recall, all docs (95% CI) | Recall, processed | Specificity (95% CI) | Balanced acc. | MCC |
|---|---:|---|---:|---|---:|---:|
| GPT-5 (OpenRouter) | 167 | 98.1% (94.5–99.3) | 98.1% | 0.0% (0.0–27.8) | 49.0% | −0.034 |
| Llama 4 Maverick | 167 | 98.1% (94.5–99.3) | 98.1% | 0.0% (0.0–27.8) | 49.0% | −0.034 |
| GPT-5.4 | 167 | 97.5% (93.6–99.0) | 97.5% | 0.0% (0.0–27.8) | 48.7% | −0.040 |
| GPT-5 mini † | 161 | 96.2% (91.9–98.2) | 100.0% | 0.0% (0.0–27.8) | 50.0% | – |
| Claude Opus 5 | 167 | 94.9% (90.3–97.4) | 94.9% | 10.0% (1.8–40.4) | 52.5% | 0.052 |
| Claude Sonnet 5 | 167 | 94.9% (90.3–97.4) | 94.9% | 10.0% (1.8–40.4) | 52.5% | 0.052 |
| Grok 4.6 | 167 | 94.9% (90.3–97.4) | 94.9% | 0.0% (0.0–27.8) | 47.5% | −0.057 |
| NER baseline | 167 | 90.4% (84.8–94.1) | 90.4% | 10.0% (1.8–40.4) | 50.2% | 0.004 |
| Claude Haiku 4.5 | 167 | 89.2% (83.3–93.1) | 89.2% | 20.0% (5.7–51.0) | 54.6% | 0.069 |
| Mistral Large | 167 | 79.6% (72.6–85.2) | 79.6% | 20.0% (5.7–51.0) | 49.8% | −0.002 |
| DeepSeek V3.1 † | 113 | 65.6% (57.9–72.6) | 97.2% | 14.3% (2.6–51.3) | 55.7% | 0.149 |
| Gemini 2.5 Flash / Pro, Qwen3 235B | 0 | 0.0% | — | — | — | — |

† coverage below 100%: the two recall columns differ by exactly that run's failure rate. `Recall, all docs` divides by all 157 gold-positive documents; `Recall, processed` by the ones the run returned. Specificity, balanced accuracy and MCC are on what was processed — there is no other option, since a document the run never returned cannot be a true negative. See §2 and §7.

**Read the last two columns first.** Balanced accuracy sits at chance (50%) for
every run, and MCC is indistinguishable from zero — three runs are *negative*.
On this set, **detection output is uncorrelated with human judgement**. Recall
is high because almost everything is positive; specificity is 0–20% because
almost nothing is negative and no run declines anything.

This is not a claim that the models cannot detect events. It is a claim that
**this set cannot measure detection**, and that the earlier accuracy column
implied a discrimination that was never demonstrated. Ten negatives support no
useful interval — note the specificity CIs, which span 0–28% at their narrowest.

**What the 10 negatives are.** A statistical yearbook, a policy roadmap listing
disasters to justify itself, a conference programme, a climate outlook, a crop
bulletin — the taxonomy's class-A failures. Every model reads "disasters cited
as evidence for a policy claim" as a report of those disasters. All ten working
runs share prompt 5 and all ten fail the same way, so this is a prompt property,
not a model property.

**Recall differences are not significant among frontier models.** Exact McNemar,
paired on documents both runs returned: GPT-5 vs Grok p=0.18, GPT-5 vs Opus
p=0.34, Opus vs Sonnet p=1.00, GPT-5 vs GPT-5.4 p=1.00. Significant only against
the weak runs and the baseline (GPT-5 vs NER 15/4, p=0.019).

**Misses are idiosyncratic.** Of the 84 gold-positive documents any model missed,
55 were missed by exactly one of ten runs; one document was missed by 9 of 10;
73 were found by all ten. There is no shared class of events the models cannot
see.

---

## 4. Field extraction — the corrected comparison

Micro F1 with a 95% document-level bootstrap interval (2,000 resamples, seed 42).
Locations under the corrected rule (NFKD + `default_process`, `token_set_ratio`
≥ 90); dates at year granularity, which is what gold actually carries — 253 of
493 gold dates are a bare year.

| Run | Hazard family | Locations (normalised) | Dates (year-set) |
|---|---|---|---|
| GPT-5 (OpenRouter) | **92.7%** (90.5–94.8) | 80.5% (71.3–86.8) | **91.8%** (89.1–94.1) |
| GPT-5.4 | 92.2% (89.8–94.5) | **82.8%** (79.7–85.3) | 89.6% (86.0–92.7) |
| Claude Opus 5 | 90.4% (87.6–92.8) | 77.0% (72.1–81.1) | 84.3% (79.0–88.9) |
| Claude Sonnet 5 | 89.9% (87.2–92.4) | 76.5% (71.4–80.9) | 84.5% (78.6–89.5) |
| Grok 4.6 | 89.5% (86.9–91.9) | 74.8% (64.5–82.3) | 88.4% (84.9–91.5) |
| GPT-5 mini | 89.5% (86.7–92.4) | 70.0% (62.5–77.7) | 87.2% (83.5–90.5) |
| DeepSeek V3.1 † | 87.5% (83.8–91.0) | 75.4% (68.9–80.5) | 86.3% (82.5–89.8) |
| Claude Haiku 4.5 | 85.7% (82.1–89.0) | 75.1% (69.9–79.6) | 81.4% (75.7–86.3) |
| Llama 4 Maverick | 79.4% (75.8–82.8) | 57.3% (48.9–64.4) | 81.6% (77.3–85.2) |
| Mistral Large | 74.0% (69.1–78.1) | 47.8% (40.4–54.9) | 66.0% (58.9–72.4) |
| NER baseline | 67.6% (63.2–71.9) | 30.0% (26.1–33.7) | 57.0% (51.6–62.1) |

† over the 106 gold-positive documents DeepSeek returned, not 157 — a different
and smaller subset, so its row is not strictly commensurable with the others.

**What the intervals say.** GPT-5 and GPT-5.4 are not separable on locations
(80.5% [71.3–86.8] vs 82.8% [79.7–85.3] — heavy overlap), nor Opus from Sonnet
anywhere. The resolvable statements are: the two GPT-5 variants lead, the
mid-field (Opus, Sonnet, Grok, GPT-5 mini, DeepSeek, Haiku) is one undifferentiated
band, Llama and Mistral are clearly behind, and the NER baseline is not in the
same class on any field.

**Field recall over all documents.** The F1 columns above divide by what each
run returned. For the eleven full-coverage runs that is the whole set and the
distinction is empty; for the two partial runs it is not:

| Run | Field | Recall (processed) | Recall (all gold items) |
|---|---|---:|---:|
| DeepSeek V3.1 | Hazard family | 91.7% | **62.3%** |
| DeepSeek V3.1 | Locations (normalised) | 79.0% | **60.2%** |
| DeepSeek V3.1 | Dates (year-set) | 86.6% | **60.8%** |
| GPT-5 mini | Hazard family | 93.8% | 91.1% |
| GPT-5 mini | Locations (normalised) | 74.5% | 72.5% |
| GPT-5 mini | Dates (year-set) | 90.0% | 86.9% |

`Recall (all gold items)` divides by every gold hazard, location and date in the
157 gold-positive documents, including those on documents the run never
returned. It is the field-level analogue of the all-documents column in §2, and
the only recall figure that is directly comparable across runs with different
coverage. The full report carries it for every run and field.

**Macro vs micro.** The report carries both. They agree on ordering; macro is
1–7 points higher for most runs, because the documents carrying thirty locations
are the ones runs do worst on. GPT-5 mini is the exception — macro 76.7% against
micro 70.0% — meaning it does well on typical documents and poorly on dense ones.

---

## 5. All fields together, per document

Hazard, location and date as one content set per document — each field under its
own corrected rule (hazard family; locations fuzzy ≥90 normalised; dates
year-set). This is the joint question the per-field table cannot answer: a run
can be strong on hazards and weak on dates, and each field's F1 hides the other.

**Accuracy** here is exact match: the share of gold-positive documents where the
run produced every gold item and nothing else — no false positive and no false
negative across all three fields. It is the strictest reading available and the
closest thing to "a reviewer would have accepted this row unedited".

| Run | Docs | Accuracy (exact match) | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| GPT-5.4 | 157 | 36.9% | **86.5%** | 86.7% | **86.6%** |
| GPT-5 (OpenRouter) | 157 | **45.2%** | 84.4% | 88.3% | 86.3% |
| Claude Opus 5 | 157 | 30.6% | 79.3% | 84.1% | 81.6% |
| Grok 4.6 | 157 | 31.2% | 75.1% | **88.9%** | 81.4% |
| Claude Sonnet 5 | 157 | 38.2% | 79.5% | 83.2% | 81.3% |
| DeepSeek V3.1 † | 106 | 28.3% | 78.1% | 83.5% | 80.7% |
| Claude Haiku 4.5 | 157 | 31.2% | 83.6% | 74.8% | 78.9% |
| GPT-5 mini † | 151 | 33.1% | 75.1% | 82.9% | 78.8% |
| Llama 4 Maverick | 157 | 11.5% | 58.8% | 81.9% | 68.4% |
| Mistral Large | 157 | 8.3% | 54.5% | 60.8% | 57.5% |
| NER baseline | 157 | 0.6% | 36.0% | 56.6% | 44.0% |
| Gemini 2.5 Flash / Pro, Qwen3 235B | 0 | – | – | – | – |
| *prompt 5 (excluded)* | *157* | *73.2%* | *96.3%* | *98.2%* | *97.3%* |

† partial coverage. On the all-documents denominator DeepSeek's recall is 60.8%
and its accuracy 19.1%; GPT-5 mini's are 80.4% and 31.8%. The other runs'
figures are unchanged, since they processed everything.

**Exact match is where the honest bad news is.** The best working run gets a
document completely right 45% of the time; most sit near a third; the NER
baseline manages one document in 157. F1 in the eighties and accuracy in the
thirties is not a contradiction — it says the runs get most of each document
right and almost always leave something out or add something spurious. For a
pipeline whose output is meant to be ingested without review, exact match is the
number that matters, and it is not close to production quality on any run.

**Precision and recall trade off visibly.** Grok has the best recall in the
table (88.9%) and nearly the worst precision (75.1%) — it emits more of
everything. Haiku is the mirror image: second-best precision (83.6%), worst
recall of the frontier models (74.8%). GPT-5.4 and GPT-5 are the only runs strong
on both, and they are not separable from each other (F1 86.6% vs 86.3%, with
overlapping bootstrap intervals).

**GPT-5 beats GPT-5.4 on exact match by 8 points while losing on F1.** Same
outputs, different question: GPT-5.4 gets marginally more items right overall,
GPT-5 gets more documents *entirely* right. Which one to prefer depends on
whether downstream consumes documents or items.

## 6. The metric was doing more of the ranking than the models were

Same runs, same outputs, three location rules and two date rules:

| Run | Loc exact | Loc fuzzy (as published) | Loc fuzzy (corrected) | Δ | Date exact | Date year-set | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| GPT-5 mini | 29.7% | 43.8% | **70.0%** | **+40.3** | 69.8% | 87.2% | +17.4 |
| GPT-5.4 | 64.5% | 73.0% | 82.8% | +18.3 | 75.6% | 89.6% | +14.0 |
| Claude Sonnet 5 | 59.2% | 69.0% | 76.5% | +17.2 | 70.1% | 84.5% | +14.4 |
| Claude Opus 5 | 60.1% | 68.7% | 77.0% | +16.9 | 70.2% | 84.3% | +14.1 |
| Grok 4.6 | 59.0% | 69.9% | 74.8% | +15.8 | 77.8% | 88.4% | +10.6 |
| Claude Haiku 4.5 | 60.3% | 70.3% | 75.1% | +14.8 | 66.1% | 81.4% | +15.3 |
| Llama 4 Maverick | 43.5% | 53.0% | 57.3% | +13.8 | 62.0% | 81.6% | +19.5 |
| GPT-5 (OpenRouter) | 67.1% | 75.1% | 80.5% | +13.4 | 78.3% | 91.8% | +13.6 |
| DeepSeek V3.1 | 64.8% | 71.6% | 75.4% | +10.6 | 67.8% | 86.3% | +18.5 |
| Mistral Large | 38.0% | 44.9% | 47.8% | +9.8 | 46.6% | 66.0% | +19.4 |
| NER baseline | 20.0% | 29.0% | 30.0% | +10.0 | 39.8% | 57.0% | +17.2 |
| *prompt 5 (excluded)* | *95.2%* | *95.4%* | *96.8%* | *+1.6* | *95.7%* | *98.1%* | *+2.4* |

**The rule change is larger than the model change.** Under exact matching GPT-5
mini ranks last but one on locations (29.7%); under the corrected rule it ranks
eighth (70.0%), ahead of Llama and Mistral by 13 points. Its extract was never
bad — it names the right places and qualifies them differently, and exact
matching charged that twice, once as a false positive and once as a false
negative.

The cause: `rapidfuzz.fuzz.token_set_ratio` was called with no `processor`, so
it tokenises on whitespace without stripping punctuation. `Louisville, Kentucky`
against `Louisville` scored 66.7 and failed the ≥90 threshold, because the comma
welds to the matching token. With `processor=utils.default_process` it scores
100. The convention in the data is `Place, Parent`, so the failing case was the
common one.

Ordering is preserved under the date change and *not* under the location change,
which is the point: a metric that reorders the field is a metric that was being
ranked.

---

## 7. The three void runs

| Run | Errors | Cause |
|---|---:|---|
| Gemini 2.5 Flash | 167/167 | HTTP 403, *"prohibited due to a violation of provider Terms Of Service"* |
| Gemini 2.5 Pro | 167/167 | same |
| Qwen3 235B | 167/167 | returned bare scalars, not a JSON object (`'encoding=UTF-8'`, `'0.0'`) — structured-output mode `none` |
| DeepSeek V3.1 | 54/167 | 53 × empty content (only reasoning tokens), 1 × bare `[]` |
| GPT-5 mini | 6/167 | connection error |

The two Gemini runs never reached the model. Qwen reached it but was run with no
structured-output mode. **None of these is a statement about the model**, and the
corrected scorer now reports them as 0% coverage with dashes rather than 0.0%
accuracy.

---

## 8. What the coverage fix changed

Previously, a document a run never returned was scored as "this run found no
event". The corrected scorer excludes it from that run's denominator and reports
coverage instead — §2 gives both readings for every run; this section isolates
what the fix moved.

The old report published one number per run and did not say which denominator it
used. It was the all-documents one, which is a legitimate figure — it is now the
`Recall (all docs)` column — but it was labelled simply "recall" and printed
beside precision and F1 computed on a different basis, and it was the only
number shown.

| Run | Old (single figure) | Now: all docs | Now: processed |
|---|---:|---:|---:|
| DeepSeek V3.1 — detection recall | 65.6% | 65.6% | **97.2%** |
| DeepSeek V3.1 — hazard F1 | 71.5% | *(recall 62.3%)* | **87.5%** |
| GPT-5 mini — detection recall | 96.2% | 96.2% | **100.0%** |
| GPT-5 mini — hazard F1 | 88.2% | *(recall 91.1%)* | 89.5% |
| Gemini 2.5 Flash / Pro, Qwen3 235B | 0.0% | 0.0% | *no denominator* |

DeepSeek is the substantive case. On what it processed it is a mid-field
extractor, not a weak one — 87.5% hazard F1 against the 71.5% previously
published, and the highest detection recall in the set. On the whole set it is
the weakest working run, because a third of its calls failed. Both are now
visible, and neither is presented as the other.

For the three void runs the all-documents column is a true 0.0% — the pipeline
returned nothing — while the processed column is undefined rather than zero,
because there is no denominator. The old report showed 0.0% accuracy and left the
reader to infer it was a model result.

Two caveats the coverage column makes visible: DeepSeek's processed figures are
over 113 documents (106 gold-positive), so they carry wider intervals and
describe a different subset; and its pairwise tests are paired on that
intersection.

---

## 9. What was changed in the scorer

Three fixes, all in [`eval/score_against_human.py`](../eval/score_against_human.py):

1. **Error-aware coverage.** Documents whose only rows are error rows
   (`fonte.app_event_focus.is_error_row`, now imported rather than
   re-implemented) are excluded from a run's denominator and reported as
   coverage. `--error-policy count-as-miss` restores the old behaviour.
2. **Corrected fuzzy location matching**, reported *beside* the published rule
   rather than replacing it, so the change is auditable.
3. **Year-granularity dates**, likewise reported beside exact.

Plus a **second denominator reported throughout**: every recall figure —
detection and each field — now appears both over the documents a run returned
and over all 167 documents (all 157 gold-positive; all gold hazards, locations
and dates). Neither can be quoted without the other being visible beside it.

And four additions that make the comparison legible rather than just correct:
specificity, balanced accuracy and MCC on detection with Wilson intervals on
each denominator; document-level bootstrap intervals on every field F1; macro F1
beside micro; and McNemar paired on the documents both runs returned.

---

## 10. What this validation does and does not license

**Supported:**
- Prompt 5 recovers ≥95% of human-confirmed events on frontier models; the
  choice among GPT-5, GPT-5.4, Opus 5, Sonnet 5 and Grok is not decidable from
  detection.
- Hazard-family assignment is reliable (85–93% F1) on every working model.
- Field extraction separates models where detection does not, and the two GPT-5
  variants lead on all three fields.
- The NER baseline is not in the same class on any field (30.0% location F1
  against 47.8–82.8%).
- Small models are not uniformly worse: Haiku matches Opus on locations, GPT-5
  mini beats Opus and Sonnet on dates.

**Not supported:**
- **Any claim that a model can decline a non-event document.** MCC ≈ 0 and
  balanced accuracy ≈ 50% for every run. This is the headline limitation.
- **Any precision or false-positive-rate claim.** 10 negatives, all failed.
- **Any corpus-level extraction-rate claim.** The set is 94% positive by
  construction; the corpus is ~19%.
- **Any claim about the prompt-5 Azure run's accuracy** — it wrote most of the
  gold it would be scored against.
- **Absolute location accuracy.** Even corrected, the metric penalises surface
  form, and the gold surface form is one run's convention.
- **Anything language-specific.** 165 of 167 documents are English, 2 Japanese.
- **Annotation reliability.** One annotator, no second pass, no adjudication,
  `gold_uncertain` empty on all 167 rows, 38 documents saved in under 30 s.

## 11. What would make the next round decisive

1. **A negative set.** Sample ~100 documents no run flagged, annotate those.
   Specificity, MCC and precision all become measurable; right now the single
   most important number in §3 rests on ten documents.
2. **Un-anchor the gold.** Annotate a subset blind — no seed pane — and compare
   protocols, to size the anchoring effect in §1.
3. **Fix the void runs.** Route Gemini past the 403, set Qwen's
   structured-output mode, re-run DeepSeek's 54 errors with `--resume`.
4. **Specify a location surface form in prompt 5** ("bare place name, no
   administrative qualifier"), so exact match becomes a real metric instead of a
   dialect test.
5. **Second annotator on a 30-document overlap**, for a κ to quote.

Methods, protocol and matching rules in full:
[VALIDATION_METHODS.md](VALIDATION_METHODS.md).
