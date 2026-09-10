# Extraction runs scored against human annotations

Annotations: `eval/human_annotations_document_sample.csv` — 50 annotated rows over 50 documents, 14 of which carry a verifiable event (28.0% prevalence).

All metrics are per document; see the module docstring for why. Error policy: **exclude** — documents a run returned only error rows for are excluded from its denominator and reported as coverage below.

## 1. Documents processed, and the score relative to them

A run cannot be credited or blamed for a document it never got back, so every score in this report is computed over the documents that run actually returned. This table says how many that was, and then gives the two readings of its score side by side.

**On what it processed** is the model comparison: quality per document returned, which is the only basis on which runs with different failure rates can be ranked against each other. **Over the whole set** is the pipeline reading: the same quality discounted by coverage, which is what you would actually get from this run over all 50 documents. They differ only where a run failed calls.

The composite is a weighted mean of detection F1, hazard F1, location F1 and date F1 (weights 1.0 / 1.5 / 1.5 / 0.5, carried over from `eval/score_against_gold.py` so the two scorers rank on the same priorities), computed on the corrected matching rules.

| Run | Processed | Coverage | Recall (all docs) | Composite × coverage | Recall (processed) | Composite (processed) | Errored | Absent |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude Opus 5 | 50/50 | 100.0% | 71.4% | 73.4% | 71.4% | 73.4% | 0 | 0 |
| Claude Sonnet 5 | 50/50 | 100.0% | 78.6% | 76.1% | 78.6% | 76.1% | 0 | 0 |
| DeepSeek V3.1 | 32/50 | 64.0% | 42.9% | 52.2% | 66.7% | 81.6% | 18 | 0 |
| Gemini 2.5 Pro | 0/50 | 0.0% | 0.0% | 0.0% | – | – | 50 | 0 |
| Llama 4 Maverick | 50/50 | 100.0% | 92.9% | 68.5% | 92.9% | 68.5% | 0 | 0 |
| Mistral Large | 50/50 | 100.0% | 71.4% | 53.8% | 71.4% | 53.8% | 0 | 0 |
| GPT-5 (OpenRouter) | 50/50 | 100.0% | 78.6% | 80.0% | 78.6% | 80.0% | 0 | 0 |
| GPT-5.4 | 50/50 | 100.0% | 78.6% | 86.1% | 78.6% | 86.1% | 0 | 0 |
| Qwen3 235B | 0/50 | 0.0% | 0.0% | 0.0% | – | – | 50 | 0 |
| Grok 4.6 | 50/50 | 100.0% | 78.6% | 77.1% | 78.6% | 77.1% | 0 | 0 |
| prompt 5 (gpt-5, Azure) | 50/50 | 100.0% | 78.6% | 93.1% | 78.6% | 93.1% | 0 | 0 |
| NER baseline | 50/50 | 100.0% | 78.6% | 54.5% | 78.6% | 54.5% | 0 | 0 |

_`Recall (processed)` is over the gold-positive documents the run returned; `Recall (all docs)` is over all 14 gold-positive documents in the set, so the gap between the two columns is exactly what the run's failed calls cost. A run at 100% coverage has identical pairs._

> **Gemini 2.5 Pro, Qwen3 235B** returned nothing on every annotated document. No score in this report is a statement about these models — the zeroes in the right-hand columns are the pipeline's, not the model's.

## 2. Event detection

`Recall, all docs` divides by every gold-positive document in the set; `Recall, processed` divides by the ones this run returned. They are equal at full coverage and differ by exactly the run's failure rate otherwise. `Specificity` is over the gold-negative documents returned. Accuracy is shown for continuity but is dominated by the 28% prevalence of this set — balanced accuracy and MCC are the ones to rank on.

| Run | n | Recall, all docs (95% CI) | Recall, processed (95% CI) | Specificity (95% CI) | Balanced acc. | MCC | Accuracy (95% CI) |
|---|---:|---|---|---|---:|---:|---|
| Claude Opus 5 | 50 | 71.4% (45.4%–88.3%, n=14) | 71.4% (45.4%–88.3%, n=14) | 94.4% (81.9%–98.5%, n=36) | 82.9% | 0.693 | 88.0% (76.2%–94.4%) |
| Claude Sonnet 5 | 50 | 78.6% (52.4%–92.4%, n=14) | 78.6% (52.4%–92.4%, n=14) | 94.4% (81.9%–98.5%, n=36) | 86.5% | 0.747 | 90.0% (78.6%–95.7%) |
| DeepSeek V3.1 | 32 | 42.9% (21.4%–67.4%, n=14) | 66.7% (35.4%–87.9%, n=9) | 95.7% (79.0%–99.2%, n=23) | 81.2% | 0.678 | 87.5% (71.9%–95.0%) |
| Gemini 2.5 Pro | 0 | 0.0% (n=14) | – | – | – | – | – |
| Llama 4 Maverick | 50 | 92.9% (68.5%–98.7%, n=14) | 92.9% (68.5%–98.7%, n=14) | 83.3% (68.1%–92.1%, n=36) | 88.1% | 0.705 | 86.0% (73.8%–93.0%) |
| Mistral Large | 50 | 71.4% (45.4%–88.3%, n=14) | 71.4% (45.4%–88.3%, n=14) | 83.3% (68.1%–92.1%, n=36) | 77.4% | 0.527 | 80.0% (67.0%–88.8%) |
| GPT-5 (OpenRouter) | 50 | 78.6% (52.4%–92.4%, n=14) | 78.6% (52.4%–92.4%, n=14) | 97.2% (85.8%–99.5%, n=36) | 87.9% | 0.797 | 92.0% (81.2%–96.8%) |
| GPT-5.4 | 50 | 78.6% (52.4%–92.4%, n=14) | 78.6% (52.4%–92.4%, n=14) | 97.2% (85.8%–99.5%, n=36) | 87.9% | 0.797 | 92.0% (81.2%–96.8%) |
| Qwen3 235B | 0 | 0.0% (n=14) | – | – | – | – | – |
| Grok 4.6 | 50 | 78.6% (52.4%–92.4%, n=14) | 78.6% (52.4%–92.4%, n=14) | 91.7% (78.2%–97.1%, n=36) | 85.1% | 0.702 | 88.0% (76.2%–94.4%) |
| prompt 5 (gpt-5, Azure) | 50 | 78.6% (52.4%–92.4%, n=14) | 78.6% (52.4%–92.4%, n=14) | 100.0% (90.4%–100.0%, n=36) | 89.3% | 0.852 | 94.0% (83.8%–97.9%) |
| NER baseline | 50 | 78.6% (52.4%–92.4%, n=14) | 78.6% (52.4%–92.4%, n=14) | 72.2% (56.0%–84.2%, n=36) | 75.4% | 0.462 | 74.0% (60.4%–84.1%) |

### Confusion matrices

| Run | TP | FP | FN | TN | Precision | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Claude Opus 5 | 10 | 2 | 4 | 34 | 83.3% | 76.9% |
| Claude Sonnet 5 | 11 | 2 | 3 | 34 | 84.6% | 81.5% |
| DeepSeek V3.1 | 6 | 1 | 3 | 22 | 85.7% | 75.0% |
| Gemini 2.5 Pro | – | – | – | – | – | – |
| Llama 4 Maverick | 13 | 6 | 1 | 30 | 68.4% | 78.8% |
| Mistral Large | 10 | 6 | 4 | 30 | 62.5% | 66.7% |
| GPT-5 (OpenRouter) | 11 | 1 | 3 | 35 | 91.7% | 84.6% |
| GPT-5.4 | 11 | 1 | 3 | 35 | 91.7% | 84.6% |
| Qwen3 235B | – | – | – | – | – | – |
| Grok 4.6 | 11 | 3 | 3 | 33 | 78.6% | 78.6% |
| prompt 5 (gpt-5, Azure) | 11 | 0 | 3 | 36 | 100.0% | 88.0% |
| NER baseline | 11 | 10 | 3 | 26 | 52.4% | 62.9% |

_Precision is reported for continuity only. With 36 gold-negative documents in the set it is pinned near the prevalence for any run that flags most documents, and it separates nothing._

## 3. Field extraction, on documents gold says carry an event

`Recall (all)` divides by every gold item in the set — including those on documents the run never returned — so it is comparable across runs with different coverage. `Recall (processed)` divides only by the documents the run returned, and is the recall the F1 column uses. Micro F1 pools TP/FP/FN over documents; macro F1 averages per-document F1 so a one-location document counts as much as a thirty-location one. The interval is a 95% percentile bootstrap over 2,000 document-level resamples (seed 42); overlapping intervals mean the difference is not resolvable at this sample size.

| Run | Field | Precision | Recall (all) | Recall (processed) | Micro F1 (95% CI) | Macro F1 | TP | FP | FN |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| Claude Opus 5 | Hazard family | 85.7% | 75.0% | 75.0% | 80.0% (64.5%–90.9%) | 70.3% | 12 | 2 | 4 |
| Claude Opus 5 | Locations (exact) | 31.4% | 44.0% | 44.0% | 36.7% (20.0%–56.6%) | 37.9% | 11 | 24 | 14 |
| Claude Opus 5 | Locations (fuzzy ≥90, raw) | 48.6% | 68.0% | 68.0% | 56.7% (35.6%–74.6%) | 52.9% | 17 | 18 | 8 |
| Claude Opus 5 | Locations (fuzzy ≥90, normalised) | 54.3% | 76.0% | 76.0% | 63.3% (47.3%–79.2%) | 58.7% | 19 | 16 | 6 |
| Claude Opus 5 | Dates (exact) | 65.0% | 61.9% | 61.9% | 63.4% (50.7%–83.3%) | 62.5% | 13 | 7 | 8 |
| Claude Opus 5 | Dates (year-set) | 86.7% | 68.4% | 68.4% | 76.5% (62.5%–92.3%) | 70.5% | 13 | 2 | 6 |
| Claude Sonnet 5 | Hazard family | 92.9% | 81.2% | 81.2% | 86.7% (73.3%–97.0%) | 79.5% | 13 | 1 | 3 |
| Claude Sonnet 5 | Locations (exact) | 26.3% | 40.0% | 40.0% | 31.7% (12.3%–57.1%) | 40.5% | 10 | 28 | 15 |
| Claude Sonnet 5 | Locations (fuzzy ≥90, raw) | 42.1% | 64.0% | 64.0% | 50.8% (38.0%–65.5%) | 53.3% | 16 | 22 | 9 |
| Claude Sonnet 5 | Locations (fuzzy ≥90, normalised) | 50.0% | 76.0% | 76.0% | 60.3% (42.7%–77.4%) | 59.5% | 19 | 19 | 6 |
| Claude Sonnet 5 | Dates (exact) | 50.0% | 57.1% | 57.1% | 53.3% (26.7%–71.2%) | 45.2% | 12 | 12 | 9 |
| Claude Sonnet 5 | Dates (year-set) | 83.3% | 78.9% | 78.9% | 81.1% (68.6%–92.7%) | 76.7% | 15 | 3 | 4 |
| DeepSeek V3.1 | Hazard family | 90.0% | 56.2% | 81.8% | 85.7% (62.5%–96.6%) | 70.8% | 9 | 1 | 2 |
| DeepSeek V3.1 | Locations (exact) | 66.7% | 32.0% | 44.4% | 53.3% (25.6%–88.9%) | 58.8% | 8 | 4 | 10 |
| DeepSeek V3.1 | Locations (fuzzy ≥90, raw) | 100.0% | 48.0% | 66.7% | 80.0% (53.3%–96.8%) | 72.5% | 12 | 0 | 6 |
| DeepSeek V3.1 | Locations (fuzzy ≥90, normalised) | 100.0% | 48.0% | 66.7% | 80.0% (53.3%–96.8%) | 72.5% | 12 | 0 | 6 |
| DeepSeek V3.1 | Dates (exact) | 100.0% | 47.6% | 66.7% | 80.0% (55.6%–96.6%) | 71.9% | 10 | 0 | 5 |
| DeepSeek V3.1 | Dates (year-set) | 100.0% | 52.6% | 76.9% | 87.0% (66.7%–97.1%) | 73.2% | 10 | 0 | 3 |
| Llama 4 Maverick | Hazard family | 70.0% | 87.5% | 87.5% | 77.8% (66.7%–92.9%) | 85.2% | 14 | 6 | 2 |
| Llama 4 Maverick | Locations (exact) | 26.7% | 48.0% | 48.0% | 34.3% (18.2%–63.4%) | 54.9% | 12 | 33 | 13 |
| Llama 4 Maverick | Locations (fuzzy ≥90, raw) | 37.8% | 68.0% | 68.0% | 48.6% (25.0%–74.2%) | 68.7% | 17 | 28 | 8 |
| Llama 4 Maverick | Locations (fuzzy ≥90, normalised) | 37.8% | 68.0% | 68.0% | 48.6% (25.0%–74.2%) | 68.7% | 17 | 28 | 8 |
| Llama 4 Maverick | Dates (exact) | 48.3% | 66.7% | 66.7% | 56.0% (37.8%–75.0%) | 60.4% | 14 | 15 | 7 |
| Llama 4 Maverick | Dates (year-set) | 76.2% | 84.2% | 84.2% | 80.0% (70.8%–93.3%) | 86.9% | 16 | 5 | 3 |
| Mistral Large | Hazard family | 66.7% | 62.5% | 62.5% | 64.5% (45.5%–82.8%) | 60.8% | 10 | 5 | 6 |
| Mistral Large | Locations (exact) | 15.3% | 36.0% | 36.0% | 21.4% (10.2%–36.9%) | 24.0% | 9 | 50 | 16 |
| Mistral Large | Locations (fuzzy ≥90, raw) | 20.3% | 48.0% | 48.0% | 28.6% (16.3%–44.0%) | 31.7% | 12 | 47 | 13 |
| Mistral Large | Locations (fuzzy ≥90, normalised) | 22.0% | 52.0% | 52.0% | 31.0% (20.0%–45.3%) | 33.6% | 13 | 46 | 12 |
| Mistral Large | Dates (exact) | 28.6% | 28.6% | 28.6% | 28.6% (12.8%–50.0%) | 34.9% | 6 | 15 | 15 |
| Mistral Large | Dates (year-set) | 83.3% | 52.6% | 52.6% | 64.5% (42.1%–86.7%) | 67.9% | 10 | 2 | 9 |
| GPT-5 (OpenRouter) | Hazard family | 86.7% | 81.2% | 81.2% | 83.9% (71.4%–94.1%) | 77.9% | 13 | 2 | 3 |
| GPT-5 (OpenRouter) | Locations (exact) | 44.4% | 48.0% | 48.0% | 46.2% (26.7%–71.0%) | 52.0% | 12 | 15 | 13 |
| GPT-5 (OpenRouter) | Locations (fuzzy ≥90, raw) | 66.7% | 72.0% | 72.0% | 69.2% (52.6%–83.9%) | 66.1% | 18 | 9 | 7 |
| GPT-5 (OpenRouter) | Locations (fuzzy ≥90, normalised) | 70.4% | 76.0% | 76.0% | 73.1% (60.0%–84.2%) | 67.6% | 19 | 8 | 6 |
| GPT-5 (OpenRouter) | Dates (exact) | 73.7% | 66.7% | 66.7% | 70.0% (51.3%–83.3%) | 66.2% | 14 | 5 | 7 |
| GPT-5 (OpenRouter) | Dates (year-set) | 87.5% | 73.7% | 73.7% | 80.0% (66.7%–91.9%) | 76.7% | 14 | 2 | 5 |
| GPT-5.4 | Hazard family | 87.5% | 87.5% | 87.5% | 87.5% (75.0%–97.0%) | 80.5% | 14 | 2 | 2 |
| GPT-5.4 | Locations (exact) | 55.6% | 60.0% | 60.0% | 57.7% (32.4%–73.2%) | 45.1% | 15 | 12 | 10 |
| GPT-5.4 | Locations (fuzzy ≥90, raw) | 74.1% | 80.0% | 80.0% | 76.9% (56.2%–89.8%) | 68.1% | 20 | 7 | 5 |
| GPT-5.4 | Locations (fuzzy ≥90, normalised) | 81.5% | 88.0% | 88.0% | 84.6% (71.4%–93.6%) | 74.5% | 22 | 5 | 3 |
| GPT-5.4 | Dates (exact) | 76.2% | 76.2% | 76.2% | 76.2% (62.1%–93.8%) | 71.4% | 16 | 5 | 5 |
| GPT-5.4 | Dates (year-set) | 89.5% | 89.5% | 89.5% | 89.5% (78.7%–100.0%) | 83.1% | 17 | 2 | 2 |
| Grok 4.6 | Hazard family | 81.2% | 81.2% | 81.2% | 81.2% (69.2%–91.4%) | 75.4% | 13 | 3 | 3 |
| Grok 4.6 | Locations (exact) | 45.7% | 64.0% | 64.0% | 53.3% (25.6%–74.6%) | 48.4% | 16 | 19 | 9 |
| Grok 4.6 | Locations (fuzzy ≥90, raw) | 60.0% | 84.0% | 84.0% | 70.0% (52.6%–85.3%) | 68.3% | 21 | 14 | 4 |
| Grok 4.6 | Locations (fuzzy ≥90, normalised) | 60.0% | 84.0% | 84.0% | 70.0% (52.6%–85.3%) | 68.3% | 21 | 14 | 4 |
| Grok 4.6 | Dates (exact) | 65.0% | 61.9% | 61.9% | 63.4% (44.4%–80.9%) | 59.9% | 13 | 7 | 8 |
| Grok 4.6 | Dates (year-set) | 88.2% | 78.9% | 78.9% | 83.3% (70.0%–96.0%) | 79.2% | 15 | 2 | 4 |
| prompt 5 (gpt-5, Azure) | Hazard family | 100.0% | 87.5% | 87.5% | 93.3% (80.0%–100.0%) | 84.6% | 14 | 0 | 2 |
| prompt 5 (gpt-5, Azure) | Locations (exact) | 100.0% | 92.0% | 92.0% | 95.8% (86.7%–100.0%) | 84.6% | 23 | 0 | 2 |
| prompt 5 (gpt-5, Azure) | Locations (fuzzy ≥90, raw) | 100.0% | 92.0% | 92.0% | 95.8% (86.7%–100.0%) | 84.6% | 23 | 0 | 2 |
| prompt 5 (gpt-5, Azure) | Locations (fuzzy ≥90, normalised) | 100.0% | 92.0% | 92.0% | 95.8% (86.7%–100.0%) | 84.6% | 23 | 0 | 2 |
| prompt 5 (gpt-5, Azure) | Dates (exact) | 94.7% | 85.7% | 85.7% | 90.0% (71.0%–100.0%) | 76.9% | 18 | 1 | 3 |
| prompt 5 (gpt-5, Azure) | Dates (year-set) | 100.0% | 89.5% | 89.5% | 94.4% (82.8%–100.0%) | 84.6% | 17 | 0 | 2 |
| NER baseline | Hazard family | 54.2% | 81.2% | 81.2% | 65.0% (50.0%–80.0%) | 63.1% | 13 | 11 | 3 |
| NER baseline | Locations (exact) | 14.0% | 48.0% | 48.0% | 21.6% (11.0%–33.3%) | 23.3% | 12 | 74 | 13 |
| NER baseline | Locations (fuzzy ≥90, raw) | 22.1% | 76.0% | 76.0% | 34.2% (22.0%–48.9%) | 33.9% | 19 | 67 | 6 |
| NER baseline | Locations (fuzzy ≥90, normalised) | 22.1% | 76.0% | 76.0% | 34.2% (22.0%–48.9%) | 33.9% | 19 | 67 | 6 |
| NER baseline | Dates (exact) | 38.1% | 76.2% | 76.2% | 50.8% (38.6%–63.6%) | 48.1% | 16 | 26 | 5 |
| NER baseline | Dates (year-set) | 55.2% | 84.2% | 84.2% | 66.7% (57.8%–74.1%) | 58.3% | 16 | 13 | 3 |

## 4. All fields together, per document

Hazard, location and date treated as one content set per document, each field under its own corrected rule (hazard family; locations fuzzy ≥90 normalised; dates year-set). This is the joint question — did the run get this document right? — which no single-field row answers, because a run can be strong on hazards and weak on dates and each field's F1 hides the other.

`Exact match` is the share of gold-positive documents where the run produced every gold item and nothing else: no false positive and no false negative across all three fields. It is the strictest reading here and the one closest to "a reviewer would have accepted this row unedited".

| Run | Docs | Exact match (95% CI) | Precision | Recall | F1 (95% CI) | Macro F1 | Recall (all docs) | Exact match (all docs) |
|---|---:|---|---:|---:|---|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | 14 | 85.7% (60.1%–96.0%) | 100.0% | 90.0% | 94.7% (84.2%–100.0%) | 84.6% | 90.0% | 85.7% |
| GPT-5.4 | 14 | 50.0% (26.8%–73.2%) | 85.5% | 88.3% | 86.9% (77.1%–94.7%) | 78.1% | 88.3% | 50.0% |
| DeepSeek V3.1 | 9 | 55.6% (26.7%–81.1%) | 96.9% | 73.8% | 83.8% (60.7%–96.0%) | 71.4% | 51.7% | 35.7% |
| GPT-5 (OpenRouter) | 14 | 35.7% (16.3%–61.2%) | 79.3% | 76.7% | 78.0% (67.3%–86.7%) | 71.6% | 76.7% | 35.7% |
| Grok 4.6 | 14 | 42.9% (21.4%–67.4%) | 72.1% | 81.7% | 76.6% (64.6%–86.8%) | 70.6% | 81.7% | 42.9% |
| Claude Sonnet 5 | 14 | 28.6% (11.7%–54.6%) | 67.1% | 78.3% | 72.3% (59.3%–83.7%) | 66.4% | 78.3% | 28.6% |
| Claude Opus 5 | 14 | 42.9% (21.4%–67.4%) | 68.8% | 73.3% | 71.0% (58.8%–82.7%) | 62.6% | 73.3% | 42.9% |
| Llama 4 Maverick | 14 | 35.7% (16.3%–61.2%) | 54.7% | 78.3% | 64.4% (47.8%–82.2%) | 75.9% | 78.3% | 35.7% |
| NER baseline | 14 | 7.1% (1.3%–31.5%) | 34.5% | 80.0% | 48.2% (36.3%–60.2%) | 44.6% | 80.0% | 7.1% |
| Mistral Large | 14 | 7.1% (1.3%–31.5%) | 38.4% | 55.0% | 45.2% (31.8%–60.0%) | 45.0% | 55.0% | 7.1% |
| Gemini 2.5 Pro | 0 | – | – | – | – | – | 0.0% | 0.0% |
| Qwen3 235B | 0 | – | – | – | – | – | 0.0% | 0.0% |

_Sorted by F1. `Docs` is the gold-positive documents the run returned; the two right-hand columns divide by all 14 instead, so they read as pipeline yield. Precision, macro F1 and the intervals have no all-documents form — a document the run never returned supplies neither a numerator nor a denominator._

## 5. What the matching rule costs

The same run under different matching rules. A gap here is a property of the metric, not of the model — and where it is larger than the gap between two models, the metric is what is being ranked.

| Run | Loc exact | Loc fuzzy raw | Loc fuzzy normalised | Δ norm−exact | Date exact | Date year-set | Δ year−exact |
|---|---:|---:|---:|---:|---:|---:|---:|
| Claude Opus 5 | 36.7% | 56.7% | 63.3% | +26.7 pp | 63.4% | 76.5% | +13.1 pp |
| Claude Sonnet 5 | 31.7% | 50.8% | 60.3% | +28.6 pp | 53.3% | 81.1% | +27.7 pp |
| DeepSeek V3.1 | 53.3% | 80.0% | 80.0% | +26.7 pp | 80.0% | 87.0% | +7.0 pp |
| Llama 4 Maverick | 34.3% | 48.6% | 48.6% | +14.3 pp | 56.0% | 80.0% | +24.0 pp |
| Mistral Large | 21.4% | 28.6% | 31.0% | +9.5 pp | 28.6% | 64.5% | +35.9 pp |
| GPT-5 (OpenRouter) | 46.2% | 69.2% | 73.1% | +26.9 pp | 70.0% | 80.0% | +10.0 pp |
| GPT-5.4 | 57.7% | 76.9% | 84.6% | +26.9 pp | 76.2% | 89.5% | +13.3 pp |
| Grok 4.6 | 53.3% | 70.0% | 70.0% | +16.7 pp | 63.4% | 83.3% | +19.9 pp |
| prompt 5 (gpt-5, Azure) | 95.8% | 95.8% | 95.8% | +0.0 pp | 90.0% | 94.4% | +4.4 pp |
| NER baseline | 21.6% | 34.2% | 34.2% | +12.6 pp | 50.8% | 66.7% | +15.9 pp |

## 6. Paired comparison — exact McNemar on event detection

Paired over the documents **both** runs returned, so a run is never charged for the other's failed calls. `n` is that intersection.

| A | B | n | A only | B only | p |
|---|---|---:|---:|---:|---:|
| Claude Opus 5 | Claude Sonnet 5 | 50 | 0 | 1 | 1.0000 |
| Claude Opus 5 | DeepSeek V3.1 | 32 | 1 | 2 | 1.0000 |
| Claude Opus 5 | Llama 4 Maverick | 50 | 4 | 3 | 1.0000 |
| Claude Opus 5 | Mistral Large | 50 | 7 | 3 | 0.3438 |
| Claude Opus 5 | GPT-5 (OpenRouter) | 50 | 0 | 2 | 0.5000 |
| Claude Opus 5 | GPT-5.4 | 50 | 0 | 2 | 0.5000 |
| Claude Opus 5 | Grok 4.6 | 50 | 2 | 2 | 1.0000 |
| Claude Opus 5 | prompt 5 (gpt-5, Azure) | 50 | 0 | 3 | 0.2500 |
| Claude Opus 5 | NER baseline | 50 | 11 | 4 | 0.1185 |
| Claude Sonnet 5 | DeepSeek V3.1 | 32 | 1 | 2 | 1.0000 |
| Claude Sonnet 5 | Llama 4 Maverick | 50 | 4 | 2 | 0.6875 |
| Claude Sonnet 5 | Mistral Large | 50 | 7 | 2 | 0.1797 |
| Claude Sonnet 5 | GPT-5 (OpenRouter) | 50 | 1 | 2 | 1.0000 |
| Claude Sonnet 5 | GPT-5.4 | 50 | 1 | 2 | 1.0000 |
| Claude Sonnet 5 | Grok 4.6 | 50 | 3 | 2 | 1.0000 |
| Claude Sonnet 5 | prompt 5 (gpt-5, Azure) | 50 | 1 | 3 | 0.6250 |
| Claude Sonnet 5 | NER baseline | 50 | 11 | 3 | 0.0574 |
| DeepSeek V3.1 | Llama 4 Maverick | 32 | 3 | 2 | 1.0000 |
| DeepSeek V3.1 | Mistral Large | 32 | 4 | 2 | 0.6875 |
| DeepSeek V3.1 | GPT-5 (OpenRouter) | 32 | 0 | 1 | 1.0000 |
| DeepSeek V3.1 | GPT-5.4 | 32 | 0 | 1 | 1.0000 |
| DeepSeek V3.1 | Grok 4.6 | 32 | 0 | 1 | 1.0000 |
| DeepSeek V3.1 | prompt 5 (gpt-5, Azure) | 32 | 0 | 2 | 0.5000 |
| DeepSeek V3.1 | NER baseline | 32 | 6 | 2 | 0.2891 |
| Llama 4 Maverick | Mistral Large | 50 | 6 | 3 | 0.5078 |
| Llama 4 Maverick | GPT-5 (OpenRouter) | 50 | 2 | 5 | 0.4531 |
| Llama 4 Maverick | GPT-5.4 | 50 | 2 | 5 | 0.4531 |
| Llama 4 Maverick | Grok 4.6 | 50 | 2 | 3 | 1.0000 |
| Llama 4 Maverick | prompt 5 (gpt-5, Azure) | 50 | 2 | 6 | 0.2891 |
| Llama 4 Maverick | NER baseline | 50 | 8 | 2 | 0.1094 |
| Mistral Large | GPT-5 (OpenRouter) | 50 | 2 | 8 | 0.1094 |
| Mistral Large | GPT-5.4 | 50 | 2 | 8 | 0.1094 |
| Mistral Large | Grok 4.6 | 50 | 3 | 7 | 0.3438 |
| Mistral Large | prompt 5 (gpt-5, Azure) | 50 | 1 | 8 | **0.0391** |
| Mistral Large | NER baseline | 50 | 9 | 6 | 0.6072 |
| GPT-5 (OpenRouter) | GPT-5.4 | 50 | 0 | 0 | 1.0000 |
| GPT-5 (OpenRouter) | Grok 4.6 | 50 | 2 | 0 | 0.5000 |
| GPT-5 (OpenRouter) | prompt 5 (gpt-5, Azure) | 50 | 0 | 1 | 1.0000 |
| GPT-5 (OpenRouter) | NER baseline | 50 | 11 | 2 | **0.0225** |
| GPT-5.4 | Grok 4.6 | 50 | 2 | 0 | 0.5000 |
| GPT-5.4 | prompt 5 (gpt-5, Azure) | 50 | 0 | 1 | 1.0000 |
| GPT-5.4 | NER baseline | 50 | 11 | 2 | **0.0225** |
| Grok 4.6 | prompt 5 (gpt-5, Azure) | 50 | 0 | 3 | 0.2500 |
| Grok 4.6 | NER baseline | 50 | 9 | 2 | 0.0654 |
| prompt 5 (gpt-5, Azure) | NER baseline | 50 | 12 | 2 | **0.0129** |

_'A only' counts documents A got right and B got wrong. p is two-sided; the concordant pairs carry no information. Bold marks p < 0.05, uncorrected for multiple comparisons — with 45 pairs, expect some by chance._

## 7. Coverage gaps in detail

- **DeepSeek V3.1**: 18 returned only error rows — excluded from its denominator.
- **Gemini 2.5 Pro**: 50 returned only error rows — excluded from its denominator.
- **Qwen3 235B**: 50 returned only error rows — excluded from its denominator.
