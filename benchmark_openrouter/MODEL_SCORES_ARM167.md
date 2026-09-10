# Extraction runs scored against human annotations

Annotations: `eval/human_annotations.csv` — 167 annotated rows over 167 documents, 157 of which carry a verifiable event (94.0% prevalence).

All metrics are per document; see the module docstring for why. Error policy: **exclude** — documents a run returned only error rows for are excluded from its denominator and reported as coverage below.

## 1. Documents processed, and the score relative to them

A run cannot be credited or blamed for a document it never got back, so every score in this report is computed over the documents that run actually returned. This table says how many that was, and then gives the two readings of its score side by side.

**On what it processed** is the model comparison: quality per document returned, which is the only basis on which runs with different failure rates can be ranked against each other. **Over the whole set** is the pipeline reading: the same quality discounted by coverage, which is what you would actually get from this run over all 167 documents. They differ only where a run failed calls.

The composite is a weighted mean of detection F1, hazard F1, location F1 and date F1 (weights 1.0 / 1.5 / 1.5 / 0.5, carried over from `eval/score_against_gold.py` so the two scorers rank on the same priorities), computed on the corrected matching rules.

| Run | Processed | Coverage | Recall (all docs) | Composite × coverage | Recall (processed) | Composite (processed) | Errored | Absent |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude Opus 5 | 167/167 | 100.0% | 94.9% | 86.2% | 94.9% | 86.2% | 0 | 0 |
| Claude Sonnet 5 | 167/167 | 100.0% | 94.9% | 85.9% | 94.9% | 85.9% | 0 | 0 |
| DeepSeek V3.1 | 167/167 | 100.0% | 96.8% | 84.4% | 96.8% | 84.4% | 0 | 0 |
| Gemini 2.5 Pro | 0/167 | 0.0% | 0.0% | 0.0% | – | – | 167 | 0 |
| Llama 4 Maverick | 167/167 | 100.0% | 98.1% | 76.0% | 98.1% | 76.0% | 0 | 0 |
| Mistral Large | 167/167 | 100.0% | 79.6% | 67.1% | 79.6% | 67.1% | 0 | 0 |
| GPT-5 (OpenRouter) | 167/167 | 100.0% | 98.1% | 89.3% | 98.1% | 89.3% | 0 | 0 |
| GPT-5.4 | 167/167 | 100.0% | 97.5% | 89.5% | 97.5% | 89.5% | 0 | 0 |
| Qwen3 235B | 0/167 | 0.0% | 0.0% | 0.0% | – | – | 167 | 0 |
| Grok 4.6 | 167/167 | 100.0% | 94.9% | 85.5% | 94.9% | 85.5% | 0 | 0 |
| prompt 5 (gpt-5, Azure) | 167/167 | 100.0% | 100.0% | 97.0% | 100.0% | 97.0% | 0 | 0 |
| NER baseline | 167/167 | 100.0% | 90.4% | 59.4% | 90.4% | 59.4% | 0 | 0 |

_`Recall (processed)` is over the gold-positive documents the run returned; `Recall (all docs)` is over all 157 gold-positive documents in the set, so the gap between the two columns is exactly what the run's failed calls cost. A run at 100% coverage has identical pairs._

> **Gemini 2.5 Pro, Qwen3 235B** returned nothing on every annotated document. No score in this report is a statement about these models — the zeroes in the right-hand columns are the pipeline's, not the model's.

## 2. Event detection

`Recall, all docs` divides by every gold-positive document in the set; `Recall, processed` divides by the ones this run returned. They are equal at full coverage and differ by exactly the run's failure rate otherwise. `Specificity` is over the gold-negative documents returned. Accuracy is shown for continuity but is dominated by the 94% prevalence of this set — balanced accuracy and MCC are the ones to rank on.

| Run | n | Recall, all docs (95% CI) | Recall, processed (95% CI) | Specificity (95% CI) | Balanced acc. | MCC | Accuracy (95% CI) |
|---|---:|---|---|---|---:|---:|---|
| Claude Opus 5 | 167 | 94.9% (90.3%–97.4%, n=157) | 94.9% (90.3%–97.4%, n=157) | 10.0% (1.8%–40.4%, n=10) | 52.5% | 0.052 | 89.8% (84.3%–93.5%) |
| Claude Sonnet 5 | 167 | 94.9% (90.3%–97.4%, n=157) | 94.9% (90.3%–97.4%, n=157) | 10.0% (1.8%–40.4%, n=10) | 52.5% | 0.052 | 89.8% (84.3%–93.5%) |
| DeepSeek V3.1 | 167 | 96.8% (92.8%–98.6%, n=157) | 96.8% (92.8%–98.6%, n=157) | 10.0% (1.8%–40.4%, n=10) | 53.4% | 0.087 | 91.6% (86.4%–94.9%) |
| Gemini 2.5 Pro | 0 | 0.0% (n=157) | – | – | – | – | – |
| Llama 4 Maverick | 167 | 98.1% (94.5%–99.3%, n=157) | 98.1% (94.5%–99.3%, n=157) | 0.0% (0.0%–27.8%, n=10) | 49.0% | -0.034 | 92.2% (87.1%–95.4%) |
| Mistral Large | 167 | 79.6% (72.6%–85.2%, n=157) | 79.6% (72.6%–85.2%, n=157) | 20.0% (5.7%–51.0%, n=10) | 49.8% | -0.002 | 76.0% (69.0%–81.9%) |
| GPT-5 (OpenRouter) | 167 | 98.1% (94.5%–99.3%, n=157) | 98.1% (94.5%–99.3%, n=157) | 0.0% (0.0%–27.8%, n=10) | 49.0% | -0.034 | 92.2% (87.1%–95.4%) |
| GPT-5.4 | 167 | 97.5% (93.6%–99.0%, n=157) | 97.5% (93.6%–99.0%, n=157) | 0.0% (0.0%–27.8%, n=10) | 48.7% | -0.040 | 91.6% (86.4%–94.9%) |
| Qwen3 235B | 0 | 0.0% (n=157) | – | – | – | – | – |
| Grok 4.6 | 167 | 94.9% (90.3%–97.4%, n=157) | 94.9% (90.3%–97.4%, n=157) | 0.0% (0.0%–27.8%, n=10) | 47.5% | -0.057 | 89.2% (83.6%–93.1%) |
| prompt 5 (gpt-5, Azure) | 167 | 100.0% (97.6%–100.0%, n=157) | 100.0% (97.6%–100.0%, n=157) | 0.0% (0.0%–27.8%, n=10) | 50.0% | – | 94.0% (89.3%–96.7%) |
| NER baseline | 167 | 90.4% (84.8%–94.1%, n=157) | 90.4% (84.8%–94.1%, n=157) | 10.0% (1.8%–40.4%, n=10) | 50.2% | 0.004 | 85.6% (79.5%–90.1%) |

### Confusion matrices

| Run | TP | FP | FN | TN | Precision | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Claude Opus 5 | 149 | 9 | 8 | 1 | 94.3% | 94.6% |
| Claude Sonnet 5 | 149 | 9 | 8 | 1 | 94.3% | 94.6% |
| DeepSeek V3.1 | 152 | 9 | 5 | 1 | 94.4% | 95.6% |
| Gemini 2.5 Pro | – | – | – | – | – | – |
| Llama 4 Maverick | 154 | 10 | 3 | 0 | 93.9% | 96.0% |
| Mistral Large | 125 | 8 | 32 | 2 | 94.0% | 86.2% |
| GPT-5 (OpenRouter) | 154 | 10 | 3 | 0 | 93.9% | 96.0% |
| GPT-5.4 | 153 | 10 | 4 | 0 | 93.9% | 95.6% |
| Qwen3 235B | – | – | – | – | – | – |
| Grok 4.6 | 149 | 10 | 8 | 0 | 93.7% | 94.3% |
| prompt 5 (gpt-5, Azure) | 157 | 10 | 0 | 0 | 94.0% | 96.9% |
| NER baseline | 142 | 9 | 15 | 1 | 94.0% | 92.2% |

_Precision is reported for continuity only. With 10 gold-negative documents in the set it is pinned near the prevalence for any run that flags most documents, and it separates nothing._

## 3. Field extraction, on documents gold says carry an event

`Recall (all)` divides by every gold item in the set — including those on documents the run never returned — so it is comparable across runs with different coverage. `Recall (processed)` divides only by the documents the run returned, and is the recall the F1 column uses. Micro F1 pools TP/FP/FN over documents; macro F1 averages per-document F1 so a one-location document counts as much as a thirty-location one. The interval is a 95% percentile bootstrap over 2,000 document-level resamples (seed 42); overlapping intervals mean the difference is not resolvable at this sample size.

| Run | Field | Precision | Recall (all) | Recall (processed) | Micro F1 (95% CI) | Macro F1 | TP | FP | FN |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| Claude Opus 5 | Hazard family | 87.5% | 93.5% | 93.5% | 90.4% (87.6%–92.8%) | 88.7% | 231 | 33 | 16 |
| Claude Opus 5 | Locations (exact) | 56.7% | 63.8% | 63.8% | 60.1% (51.4%–67.3%) | 58.8% | 436 | 333 | 247 |
| Claude Opus 5 | Locations (fuzzy ≥90, raw) | 64.9% | 73.1% | 73.1% | 68.7% (61.0%–75.2%) | 67.6% | 499 | 270 | 184 |
| Claude Opus 5 | Locations (fuzzy ≥90, normalised) | 72.7% | 81.8% | 81.8% | 77.0% (72.1%–81.1%) | 75.7% | 559 | 210 | 124 |
| Claude Opus 5 | Dates (exact) | 69.0% | 71.4% | 71.4% | 70.2% (62.5%–78.2%) | 76.9% | 352 | 158 | 141 |
| Claude Opus 5 | Dates (year-set) | 86.6% | 82.2% | 82.2% | 84.3% (79.0%–88.9%) | 85.7% | 350 | 54 | 76 |
| Claude Sonnet 5 | Hazard family | 88.3% | 91.5% | 91.5% | 89.9% (87.2%–92.4%) | 88.6% | 226 | 30 | 21 |
| Claude Sonnet 5 | Locations (exact) | 56.8% | 61.9% | 61.9% | 59.2% (51.1%–66.1%) | 57.3% | 423 | 322 | 260 |
| Claude Sonnet 5 | Locations (fuzzy ≥90, raw) | 66.2% | 72.2% | 72.2% | 69.0% (63.1%–74.4%) | 66.0% | 493 | 252 | 190 |
| Claude Sonnet 5 | Locations (fuzzy ≥90, normalised) | 73.3% | 79.9% | 79.9% | 76.5% (71.4%–80.9%) | 76.7% | 546 | 199 | 137 |
| Claude Sonnet 5 | Dates (exact) | 70.3% | 69.8% | 69.8% | 70.1% (63.3%–77.2%) | 73.0% | 344 | 145 | 149 |
| Claude Sonnet 5 | Dates (year-set) | 85.4% | 83.6% | 83.6% | 84.5% (78.6%–89.5%) | 85.2% | 356 | 61 | 70 |
| DeepSeek V3.1 | Hazard family | 82.8% | 91.9% | 91.9% | 87.1% (84.2%–90.0%) | 88.1% | 227 | 47 | 20 |
| DeepSeek V3.1 | Locations (exact) | 60.4% | 63.8% | 63.8% | 62.1% (55.0%–68.1%) | 60.3% | 436 | 286 | 247 |
| DeepSeek V3.1 | Locations (fuzzy ≥90, raw) | 67.7% | 71.6% | 71.6% | 69.6% (63.3%–74.9%) | 68.7% | 489 | 233 | 194 |
| DeepSeek V3.1 | Locations (fuzzy ≥90, normalised) | 71.9% | 76.0% | 76.0% | 73.9% (68.0%–78.8%) | 75.4% | 519 | 203 | 164 |
| DeepSeek V3.1 | Dates (exact) | 70.9% | 69.6% | 69.6% | 70.2% (62.4%–77.1%) | 71.5% | 343 | 141 | 150 |
| DeepSeek V3.1 | Dates (year-set) | 86.0% | 84.7% | 84.7% | 85.3% (80.5%–89.4%) | 85.8% | 361 | 59 | 65 |
| Llama 4 Maverick | Hazard family | 68.1% | 95.1% | 95.1% | 79.4% (75.8%–82.8%) | 82.8% | 235 | 110 | 12 |
| Llama 4 Maverick | Locations (exact) | 36.3% | 54.5% | 54.5% | 43.5% (34.6%–51.6%) | 43.8% | 372 | 654 | 311 |
| Llama 4 Maverick | Locations (fuzzy ≥90, raw) | 44.2% | 66.3% | 66.3% | 53.0% (44.8%–60.4%) | 55.3% | 453 | 573 | 230 |
| Llama 4 Maverick | Locations (fuzzy ≥90, normalised) | 47.8% | 71.7% | 71.7% | 57.3% (48.9%–64.4%) | 60.4% | 490 | 536 | 193 |
| Llama 4 Maverick | Dates (exact) | 54.3% | 72.4% | 72.4% | 62.0% (54.3%–69.0%) | 65.0% | 357 | 301 | 136 |
| Llama 4 Maverick | Dates (year-set) | 74.3% | 90.4% | 90.4% | 81.6% (77.3%–85.2%) | 80.8% | 385 | 133 | 41 |
| Mistral Large | Hazard family | 71.6% | 76.5% | 76.5% | 74.0% (69.1%–78.1%) | 68.5% | 189 | 75 | 58 |
| Mistral Large | Locations (exact) | 33.7% | 43.6% | 43.6% | 38.0% (31.4%–44.7%) | 37.3% | 298 | 587 | 385 |
| Mistral Large | Locations (fuzzy ≥90, raw) | 39.8% | 51.5% | 51.5% | 44.9% (37.6%–52.0%) | 44.6% | 352 | 533 | 331 |
| Mistral Large | Locations (fuzzy ≥90, normalised) | 42.4% | 54.9% | 54.9% | 47.8% (40.4%–54.9%) | 47.4% | 375 | 510 | 308 |
| Mistral Large | Dates (exact) | 47.7% | 45.6% | 45.6% | 46.6% (39.3%–53.7%) | 45.1% | 225 | 247 | 268 |
| Mistral Large | Dates (year-set) | 71.8% | 61.0% | 61.0% | 66.0% (58.9%–72.4%) | 63.8% | 260 | 102 | 166 |
| GPT-5 (OpenRouter) | Hazard family | 90.1% | 95.5% | 95.5% | 92.7% (90.5%–94.8%) | 92.6% | 236 | 26 | 11 |
| GPT-5 (OpenRouter) | Locations (exact) | 65.6% | 68.7% | 68.7% | 67.1% (57.8%–74.3%) | 64.0% | 469 | 246 | 214 |
| GPT-5 (OpenRouter) | Locations (fuzzy ≥90, raw) | 73.4% | 76.9% | 76.9% | 75.1% (65.9%–81.7%) | 73.3% | 525 | 190 | 158 |
| GPT-5 (OpenRouter) | Locations (fuzzy ≥90, normalised) | 78.7% | 82.4% | 82.4% | 80.5% (71.3%–86.8%) | 82.2% | 563 | 152 | 120 |
| GPT-5 (OpenRouter) | Dates (exact) | 78.4% | 78.1% | 78.1% | 78.3% (72.2%–84.2%) | 79.2% | 385 | 106 | 108 |
| GPT-5 (OpenRouter) | Dates (year-set) | 90.1% | 93.7% | 93.7% | 91.8% (89.1%–94.1%) | 89.7% | 399 | 44 | 27 |
| GPT-5.4 | Hazard family | 90.9% | 93.5% | 93.5% | 92.2% (89.8%–94.5%) | 92.0% | 231 | 23 | 16 |
| GPT-5.4 | Locations (exact) | 63.5% | 65.6% | 65.6% | 64.5% (56.8%–71.5%) | 63.9% | 448 | 258 | 235 |
| GPT-5.4 | Locations (fuzzy ≥90, raw) | 71.8% | 74.2% | 74.2% | 73.0% (65.1%–79.0%) | 71.7% | 507 | 199 | 176 |
| GPT-5.4 | Locations (fuzzy ≥90, normalised) | 81.4% | 84.2% | 84.2% | 82.8% (79.7%–85.3%) | 80.5% | 575 | 131 | 108 |
| GPT-5.4 | Dates (exact) | 75.2% | 76.1% | 76.1% | 75.6% (70.0%–81.2%) | 75.0% | 375 | 124 | 118 |
| GPT-5.4 | Dates (year-set) | 92.7% | 86.6% | 86.6% | 89.6% (86.0%–92.7%) | 86.9% | 369 | 29 | 57 |
| Grok 4.6 | Hazard family | 84.8% | 94.7% | 94.7% | 89.5% (86.9%–91.9%) | 87.9% | 234 | 42 | 13 |
| Grok 4.6 | Locations (exact) | 52.5% | 67.3% | 67.3% | 59.0% (47.5%–68.9%) | 59.3% | 460 | 416 | 223 |
| Grok 4.6 | Locations (fuzzy ≥90, raw) | 62.2% | 79.8% | 79.8% | 69.9% (59.9%–77.3%) | 68.1% | 545 | 331 | 138 |
| Grok 4.6 | Locations (fuzzy ≥90, normalised) | 66.6% | 85.4% | 85.4% | 74.8% (64.5%–82.3%) | 76.7% | 583 | 293 | 100 |
| Grok 4.6 | Dates (exact) | 72.2% | 84.4% | 84.4% | 77.8% (73.4%–82.1%) | 77.8% | 416 | 160 | 77 |
| Grok 4.6 | Dates (year-set) | 85.7% | 91.3% | 91.3% | 88.4% (84.9%–91.5%) | 86.4% | 389 | 65 | 37 |
| prompt 5 (gpt-5, Azure) | Hazard family | 95.3% | 98.8% | 98.8% | 97.0% (95.4%–98.4%) | 97.7% | 244 | 12 | 3 |
| prompt 5 (gpt-5, Azure) | Locations (exact) | 94.4% | 96.0% | 96.0% | 95.2% (92.8%–97.0%) | 91.2% | 656 | 39 | 27 |
| prompt 5 (gpt-5, Azure) | Locations (fuzzy ≥90, raw) | 94.5% | 96.2% | 96.2% | 95.4% (93.1%–97.1%) | 91.3% | 657 | 38 | 26 |
| prompt 5 (gpt-5, Azure) | Locations (fuzzy ≥90, normalised) | 96.0% | 97.7% | 97.7% | 96.8% (95.1%–98.1%) | 94.9% | 667 | 28 | 16 |
| prompt 5 (gpt-5, Azure) | Dates (exact) | 94.5% | 97.0% | 97.0% | 95.7% (93.6%–97.4%) | 92.2% | 478 | 28 | 15 |
| prompt 5 (gpt-5, Azure) | Dates (year-set) | 97.5% | 98.8% | 98.8% | 98.1% (96.9%–99.1%) | 96.6% | 421 | 11 | 5 |
| NER baseline | Hazard family | 58.0% | 81.0% | 81.0% | 67.6% (63.2%–71.9%) | 67.9% | 200 | 145 | 47 |
| NER baseline | Locations (exact) | 15.6% | 28.0% | 28.0% | 20.0% (16.3%–23.5%) | 18.1% | 191 | 1037 | 492 |
| NER baseline | Locations (fuzzy ≥90, raw) | 22.6% | 40.6% | 40.6% | 29.0% (25.1%–32.6%) | 27.6% | 277 | 951 | 406 |
| NER baseline | Locations (fuzzy ≥90, normalised) | 23.4% | 42.0% | 42.0% | 30.0% (26.1%–33.7%) | 28.5% | 287 | 941 | 396 |
| NER baseline | Dates (exact) | 35.0% | 46.0% | 46.0% | 39.8% (33.5%–46.1%) | 37.8% | 227 | 421 | 266 |
| NER baseline | Dates (year-set) | 50.4% | 65.7% | 65.7% | 57.0% (51.6%–62.1%) | 54.7% | 280 | 276 | 146 |

## 4. All fields together, per document

Hazard, location and date treated as one content set per document, each field under its own corrected rule (hazard family; locations fuzzy ≥90 normalised; dates year-set). This is the joint question — did the run get this document right? — which no single-field row answers, because a run can be strong on hazards and weak on dates and each field's F1 hides the other.

`Exact match` is the share of gold-positive documents where the run produced every gold item and nothing else: no false positive and no false negative across all three fields. It is the strictest reading here and the one closest to "a reviewer would have accepted this row unedited".

| Run | Docs | Exact match (95% CI) | Precision | Recall | F1 (95% CI) | Macro F1 | Recall (all docs) | Exact match (all docs) |
|---|---:|---|---:|---:|---|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | 157 | 73.2% (65.8%–79.6%) | 96.3% | 98.2% | 97.3% (96.1%–98.2%) | 96.2% | 98.2% | 73.2% |
| GPT-5.4 | 157 | 36.9% (29.8%–44.7%) | 86.5% | 86.7% | 86.6% (84.3%–88.6%) | 85.2% | 86.7% | 36.9% |
| GPT-5 (OpenRouter) | 157 | 45.2% (37.6%–53.0%) | 84.4% | 88.3% | 86.3% (81.1%–90.1%) | 86.8% | 88.3% | 45.2% |
| Claude Opus 5 | 157 | 30.6% (23.9%–38.2%) | 79.3% | 84.1% | 81.6% (77.8%–84.8%) | 80.7% | 84.1% | 30.6% |
| Grok 4.6 | 157 | 31.2% (24.5%–38.8%) | 75.1% | 88.9% | 81.4% (75.8%–85.9%) | 81.7% | 88.9% | 31.2% |
| Claude Sonnet 5 | 157 | 38.2% (31.0%–46.0%) | 79.5% | 83.2% | 81.3% (77.5%–84.8%) | 81.1% | 83.2% | 38.2% |
| DeepSeek V3.1 | 157 | 29.9% (23.3%–37.5%) | 78.2% | 81.6% | 79.9% (75.8%–83.3%) | 80.8% | 81.6% | 29.9% |
| Llama 4 Maverick | 157 | 11.5% (7.4%–17.4%) | 58.8% | 81.9% | 68.4% (63.2%–72.7%) | 70.3% | 81.9% | 11.5% |
| Mistral Large | 157 | 8.3% (4.9%–13.7%) | 54.5% | 60.8% | 57.5% (51.2%–63.2%) | 54.6% | 60.8% | 8.3% |
| NER baseline | 157 | 0.6% (0.1%–3.5%) | 36.0% | 56.6% | 44.0% (40.6%–47.2%) | 42.8% | 56.6% | 0.6% |
| Gemini 2.5 Pro | 0 | – | – | – | – | – | 0.0% | 0.0% |
| Qwen3 235B | 0 | – | – | – | – | – | 0.0% | 0.0% |

_Sorted by F1. `Docs` is the gold-positive documents the run returned; the two right-hand columns divide by all 157 instead, so they read as pipeline yield. Precision, macro F1 and the intervals have no all-documents form — a document the run never returned supplies neither a numerator nor a denominator._

## 5. What the matching rule costs

The same run under different matching rules. A gap here is a property of the metric, not of the model — and where it is larger than the gap between two models, the metric is what is being ranked.

| Run | Loc exact | Loc fuzzy raw | Loc fuzzy normalised | Δ norm−exact | Date exact | Date year-set | Δ year−exact |
|---|---:|---:|---:|---:|---:|---:|---:|
| Claude Opus 5 | 60.1% | 68.7% | 77.0% | +16.9 pp | 70.2% | 84.3% | +14.1 pp |
| Claude Sonnet 5 | 59.2% | 69.0% | 76.5% | +17.2 pp | 70.1% | 84.5% | +14.4 pp |
| DeepSeek V3.1 | 62.1% | 69.6% | 73.9% | +11.8 pp | 70.2% | 85.3% | +15.1 pp |
| Llama 4 Maverick | 43.5% | 53.0% | 57.3% | +13.8 pp | 62.0% | 81.6% | +19.5 pp |
| Mistral Large | 38.0% | 44.9% | 47.8% | +9.8 pp | 46.6% | 66.0% | +19.4 pp |
| GPT-5 (OpenRouter) | 67.1% | 75.1% | 80.5% | +13.4 pp | 78.3% | 91.8% | +13.6 pp |
| GPT-5.4 | 64.5% | 73.0% | 82.8% | +18.3 pp | 75.6% | 89.6% | +14.0 pp |
| Grok 4.6 | 59.0% | 69.9% | 74.8% | +15.8 pp | 77.8% | 88.4% | +10.6 pp |
| prompt 5 (gpt-5, Azure) | 95.2% | 95.4% | 96.8% | +1.6 pp | 95.7% | 98.1% | +2.4 pp |
| NER baseline | 20.0% | 29.0% | 30.0% | +10.0 pp | 39.8% | 57.0% | +17.2 pp |

## 6. Paired comparison — exact McNemar on event detection

Paired over the documents **both** runs returned, so a run is never charged for the other's failed calls. `n` is that intersection.

| A | B | n | A only | B only | p |
|---|---|---:|---:|---:|---:|
| Claude Opus 5 | Claude Sonnet 5 | 167 | 4 | 4 | 1.0000 |
| Claude Opus 5 | DeepSeek V3.1 | 167 | 5 | 8 | 0.5811 |
| Claude Opus 5 | Llama 4 Maverick | 167 | 3 | 7 | 0.3438 |
| Claude Opus 5 | Mistral Large | 167 | 30 | 7 | **0.0002** |
| Claude Opus 5 | GPT-5 (OpenRouter) | 167 | 3 | 7 | 0.3438 |
| Claude Opus 5 | GPT-5.4 | 167 | 2 | 5 | 0.4531 |
| Claude Opus 5 | Grok 4.6 | 167 | 5 | 4 | 1.0000 |
| Claude Opus 5 | prompt 5 (gpt-5, Azure) | 167 | 1 | 8 | **0.0391** |
| Claude Opus 5 | NER baseline | 167 | 16 | 9 | 0.2295 |
| Claude Sonnet 5 | DeepSeek V3.1 | 167 | 5 | 8 | 0.5811 |
| Claude Sonnet 5 | Llama 4 Maverick | 167 | 3 | 7 | 0.3438 |
| Claude Sonnet 5 | Mistral Large | 167 | 31 | 8 | **0.0003** |
| Claude Sonnet 5 | GPT-5 (OpenRouter) | 167 | 3 | 7 | 0.3438 |
| Claude Sonnet 5 | GPT-5.4 | 167 | 3 | 6 | 0.5078 |
| Claude Sonnet 5 | Grok 4.6 | 167 | 7 | 6 | 1.0000 |
| Claude Sonnet 5 | prompt 5 (gpt-5, Azure) | 167 | 1 | 8 | **0.0391** |
| Claude Sonnet 5 | NER baseline | 167 | 16 | 9 | 0.2295 |
| DeepSeek V3.1 | Llama 4 Maverick | 167 | 3 | 4 | 1.0000 |
| DeepSeek V3.1 | Mistral Large | 167 | 29 | 3 | **0.0000** |
| DeepSeek V3.1 | GPT-5 (OpenRouter) | 167 | 4 | 5 | 1.0000 |
| DeepSeek V3.1 | GPT-5.4 | 167 | 5 | 5 | 1.0000 |
| DeepSeek V3.1 | Grok 4.6 | 167 | 7 | 3 | 0.3438 |
| DeepSeek V3.1 | prompt 5 (gpt-5, Azure) | 167 | 1 | 5 | 0.2188 |
| DeepSeek V3.1 | NER baseline | 167 | 16 | 6 | 0.0525 |
| Llama 4 Maverick | Mistral Large | 167 | 29 | 2 | **0.0000** |
| Llama 4 Maverick | GPT-5 (OpenRouter) | 167 | 2 | 2 | 1.0000 |
| Llama 4 Maverick | GPT-5.4 | 167 | 3 | 2 | 1.0000 |
| Llama 4 Maverick | Grok 4.6 | 167 | 6 | 1 | 0.1250 |
| Llama 4 Maverick | prompt 5 (gpt-5, Azure) | 167 | 0 | 3 | 0.2500 |
| Llama 4 Maverick | NER baseline | 167 | 15 | 4 | **0.0192** |
| Mistral Large | GPT-5 (OpenRouter) | 167 | 2 | 29 | **0.0000** |
| Mistral Large | GPT-5.4 | 167 | 3 | 29 | **0.0000** |
| Mistral Large | Grok 4.6 | 167 | 7 | 29 | **0.0003** |
| Mistral Large | prompt 5 (gpt-5, Azure) | 167 | 2 | 32 | **0.0000** |
| Mistral Large | NER baseline | 167 | 15 | 31 | **0.0259** |
| GPT-5 (OpenRouter) | GPT-5.4 | 167 | 3 | 2 | 1.0000 |
| GPT-5 (OpenRouter) | Grok 4.6 | 167 | 7 | 2 | 0.1797 |
| GPT-5 (OpenRouter) | prompt 5 (gpt-5, Azure) | 167 | 0 | 3 | 0.2500 |
| GPT-5 (OpenRouter) | NER baseline | 167 | 15 | 4 | **0.0192** |
| GPT-5.4 | Grok 4.6 | 167 | 5 | 1 | 0.2188 |
| GPT-5.4 | prompt 5 (gpt-5, Azure) | 167 | 0 | 4 | 0.1250 |
| GPT-5.4 | NER baseline | 167 | 15 | 5 | **0.0414** |
| Grok 4.6 | prompt 5 (gpt-5, Azure) | 167 | 0 | 8 | **0.0078** |
| Grok 4.6 | NER baseline | 167 | 14 | 8 | 0.2863 |
| prompt 5 (gpt-5, Azure) | NER baseline | 167 | 15 | 1 | **0.0005** |

_'A only' counts documents A got right and B got wrong. p is two-sided; the concordant pairs carry no information. Bold marks p < 0.05, uncorrected for multiple comparisons — with 45 pairs, expect some by chance._

## 7. Coverage gaps in detail

- **Gemini 2.5 Pro**: 167 returned only error rows — excluded from its denominator.
- **Qwen3 235B**: 167 returned only error rows — excluded from its denominator.
