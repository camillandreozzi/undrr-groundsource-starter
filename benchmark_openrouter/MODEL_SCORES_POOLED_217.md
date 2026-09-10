# Extraction runs scored against human annotations

Annotations: `eval/human_annotations_pooled.csv` — 217 annotated rows over 217 documents, 171 of which carry a verifiable event (78.8% prevalence).

All metrics are per document; see the module docstring for why. Error policy: **exclude** — documents a run returned only error rows for are excluded from its denominator and reported as coverage below.

## 1. Documents processed, and the score relative to them

A run cannot be credited or blamed for a document it never got back, so every score in this report is computed over the documents that run actually returned. This table says how many that was, and then gives the two readings of its score side by side.

**On what it processed** is the model comparison: quality per document returned, which is the only basis on which runs with different failure rates can be ranked against each other. **Over the whole set** is the pipeline reading: the same quality discounted by coverage, which is what you would actually get from this run over all 217 documents. They differ only where a run failed calls.

The composite is a weighted mean of detection F1, hazard F1, location F1 and date F1 (weights 1.0 / 1.5 / 1.5 / 0.5, carried over from `eval/score_against_gold.py` so the two scorers rank on the same priorities), computed on the corrected matching rules.

| Run | Processed | Coverage | Recall (all docs) | Composite × coverage | Recall (processed) | Composite (processed) | Errored | Absent |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | 217/217 | 100.0% | 87.1% | 82.3% | 87.1% | 82.3% | 0 | 0 |
| Claude Opus 5 | 217/217 | 100.0% | 93.0% | 85.5% | 93.0% | 85.5% | 0 | 0 |
| Claude Sonnet 5 | 217/217 | 100.0% | 93.6% | 85.3% | 93.6% | 85.3% | 0 | 0 |
| DeepSeek V3.1 | 199/217 | 91.7% | 92.4% | 77.2% | 95.2% | 84.2% | 18 | 0 |
| Gemini 2.5 Pro | 0/217 | 0.0% | 0.0% | 0.0% | – | – | 217 | 0 |
| Llama 4 Maverick | 217/217 | 100.0% | 97.7% | 75.5% | 97.7% | 75.5% | 0 | 0 |
| Mistral Large | 217/217 | 100.0% | 78.9% | 66.2% | 78.9% | 66.2% | 0 | 0 |
| GPT-5 (OpenRouter) | 217/217 | 100.0% | 96.5% | 88.8% | 96.5% | 88.8% | 0 | 0 |
| GPT-5.4 | 217/217 | 100.0% | 95.9% | 89.3% | 95.9% | 89.3% | 0 | 0 |
| GPT-5 mini | 217/217 | 100.0% | 98.2% | 83.8% | 98.2% | 83.8% | 0 | 0 |
| Qwen3 235B | 0/217 | 0.0% | 0.0% | 0.0% | – | – | 217 | 0 |
| Grok 4.6 | 217/217 | 100.0% | 93.6% | 85.0% | 93.6% | 85.0% | 0 | 0 |
| prompt 5 (gpt-5, Azure) | 217/217 | 100.0% | 98.2% | 96.8% | 98.2% | 96.8% | 0 | 0 |
| NER baseline | 217/217 | 100.0% | 89.5% | 58.8% | 89.5% | 58.8% | 0 | 0 |

_`Recall (processed)` is over the gold-positive documents the run returned; `Recall (all docs)` is over all 171 gold-positive documents in the set, so the gap between the two columns is exactly what the run's failed calls cost. A run at 100% coverage has identical pairs._

> **Gemini 2.5 Pro, Qwen3 235B** returned nothing on every annotated document. No score in this report is a statement about these models — the zeroes in the right-hand columns are the pipeline's, not the model's.

## 2. Event detection

`Recall, all docs` divides by every gold-positive document in the set; `Recall, processed` divides by the ones this run returned. They are equal at full coverage and differ by exactly the run's failure rate otherwise. `Specificity` is over the gold-negative documents returned. Accuracy is shown for continuity but is dominated by the 79% prevalence of this set — balanced accuracy and MCC are the ones to rank on.

| Run | n | Recall, all docs (95% CI) | Recall, processed (95% CI) | Specificity (95% CI) | Balanced acc. | MCC | Accuracy (95% CI) |
|---|---:|---|---|---|---:|---:|---|
| Claude Haiku 4.5 | 217 | 87.1% (81.3%–91.3%, n=171) | 87.1% (81.3%–91.3%, n=171) | 80.4% (66.8%–89.3%, n=46) | 83.8% | 0.621 | 85.7% (80.4%–89.7%) |
| Claude Opus 5 | 217 | 93.0% (88.1%–95.9%, n=171) | 93.0% (88.1%–95.9%, n=171) | 76.1% (62.1%–86.1%, n=46) | 84.5% | 0.685 | 89.4% (84.6%–92.8%) |
| Claude Sonnet 5 | 217 | 93.6% (88.8%–96.4%, n=171) | 93.6% (88.8%–96.4%, n=171) | 76.1% (62.1%–86.1%, n=46) | 84.8% | 0.697 | 89.9% (85.1%–93.2%) |
| DeepSeek V3.1 | 199 | 92.4% (87.4%–95.5%, n=171) | 95.2% (90.8%–97.5%, n=166) | 69.7% (52.7%–82.6%, n=33) | 82.4% | 0.665 | 91.0% (86.2%–94.2%) |
| Gemini 2.5 Pro | 0 | 0.0% (n=171) | – | – | – | – | – |
| Llama 4 Maverick | 217 | 97.7% (94.1%–99.1%, n=171) | 97.7% (94.1%–99.1%, n=171) | 65.2% (50.8%–77.3%, n=46) | 81.4% | 0.707 | 90.8% (86.2%–94.0%) |
| Mistral Large | 217 | 78.9% (72.2%–84.4%, n=171) | 78.9% (72.2%–84.4%, n=171) | 69.6% (55.2%–80.9%, n=46) | 74.3% | 0.427 | 77.0% (70.9%–82.1%) |
| GPT-5 (OpenRouter) | 217 | 96.5% (92.6%–98.4%, n=171) | 96.5% (92.6%–98.4%, n=171) | 76.1% (62.1%–86.1%, n=46) | 86.3% | 0.758 | 92.2% (87.8%–95.1%) |
| GPT-5.4 | 217 | 95.9% (91.8%–98.0%, n=171) | 95.9% (91.8%–98.0%, n=171) | 76.1% (62.1%–86.1%, n=46) | 86.0% | 0.745 | 91.7% (87.3%–94.7%) |
| GPT-5 mini | 217 | 98.2% (95.0%–99.4%, n=171) | 98.2% (95.0%–99.4%, n=171) | 69.6% (55.2%–80.9%, n=46) | 83.9% | 0.754 | 92.2% (87.8%–95.1%) |
| Qwen3 235B | 0 | 0.0% (n=171) | – | – | – | – | – |
| Grok 4.6 | 217 | 93.6% (88.8%–96.4%, n=171) | 93.6% (88.8%–96.4%, n=171) | 71.7% (57.5%–82.7%, n=46) | 82.7% | 0.664 | 88.9% (84.1%–92.5%) |
| prompt 5 (gpt-5, Azure) | 217 | 98.2% (95.0%–99.4%, n=171) | 98.2% (95.0%–99.4%, n=171) | 78.3% (64.4%–87.7%, n=46) | 88.3% | 0.814 | 94.0% (90.0%–96.5%) |
| NER baseline | 217 | 89.5% (84.0%–93.2%, n=171) | 89.5% (84.0%–93.2%, n=171) | 58.7% (44.3%–71.7%, n=46) | 74.1% | 0.486 | 82.9% (77.4%–87.4%) |

### Confusion matrices

| Run | TP | FP | FN | TN | Precision | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | 149 | 9 | 22 | 37 | 94.3% | 90.6% |
| Claude Opus 5 | 159 | 11 | 12 | 35 | 93.5% | 93.3% |
| Claude Sonnet 5 | 160 | 11 | 11 | 35 | 93.6% | 93.6% |
| DeepSeek V3.1 | 158 | 10 | 8 | 23 | 94.0% | 94.6% |
| Gemini 2.5 Pro | – | – | – | – | – | – |
| Llama 4 Maverick | 167 | 16 | 4 | 30 | 91.3% | 94.4% |
| Mistral Large | 135 | 14 | 36 | 32 | 90.6% | 84.4% |
| GPT-5 (OpenRouter) | 165 | 11 | 6 | 35 | 93.8% | 95.1% |
| GPT-5.4 | 164 | 11 | 7 | 35 | 93.7% | 94.8% |
| GPT-5 mini | 168 | 14 | 3 | 32 | 92.3% | 95.2% |
| Qwen3 235B | – | – | – | – | – | – |
| Grok 4.6 | 160 | 13 | 11 | 33 | 92.5% | 93.0% |
| prompt 5 (gpt-5, Azure) | 168 | 10 | 3 | 36 | 94.4% | 96.3% |
| NER baseline | 153 | 19 | 18 | 27 | 89.0% | 89.2% |

_Precision is reported for continuity only. With 46 gold-negative documents in the set it is pinned near the prevalence for any run that flags most documents, and it separates nothing._

## 3. Field extraction, on documents gold says carry an event

`Recall (all)` divides by every gold item in the set — including those on documents the run never returned — so it is comparable across runs with different coverage. `Recall (processed)` divides only by the documents the run returned, and is the recall the F1 column uses. Micro F1 pools TP/FP/FN over documents; macro F1 averages per-document F1 so a one-location document counts as much as a thirty-location one. The interval is a 95% percentile bootstrap over 2,000 document-level resamples (seed 42); overlapping intervals mean the difference is not resolvable at this sample size.

| Run | Field | Precision | Recall (all) | Recall (processed) | Micro F1 (95% CI) | Macro F1 | TP | FP | FN |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| Claude Haiku 4.5 | Hazard family | 90.9% | 79.8% | 79.8% | 85.0% (81.2%–88.3%) | 80.5% | 210 | 21 | 53 |
| Claude Haiku 4.5 | Locations (exact) | 61.8% | 57.5% | 57.5% | 59.5% (51.7%–66.3%) | 51.0% | 407 | 252 | 301 |
| Claude Haiku 4.5 | Locations (fuzzy ≥90, raw) | 72.4% | 67.4% | 67.4% | 69.8% (63.9%–74.6%) | 62.0% | 477 | 182 | 231 |
| Claude Haiku 4.5 | Locations (fuzzy ≥90, normalised) | 77.2% | 71.9% | 71.9% | 74.5% (68.8%–78.8%) | 68.6% | 509 | 150 | 199 |
| Claude Haiku 4.5 | Dates (exact) | 74.1% | 58.9% | 58.9% | 65.7% (56.5%–73.6%) | 62.5% | 303 | 106 | 211 |
| Claude Haiku 4.5 | Dates (year-set) | 90.1% | 73.3% | 73.3% | 80.8% (75.2%–85.5%) | 75.9% | 326 | 36 | 119 |
| Claude Opus 5 | Hazard family | 87.4% | 92.4% | 92.4% | 89.8% (87.3%–92.3%) | 87.3% | 243 | 35 | 20 |
| Claude Opus 5 | Locations (exact) | 55.6% | 63.1% | 63.1% | 59.1% (50.9%–66.3%) | 57.2% | 447 | 357 | 261 |
| Claude Opus 5 | Locations (fuzzy ≥90, raw) | 64.2% | 72.9% | 72.9% | 68.3% (60.7%–74.4%) | 66.4% | 516 | 288 | 192 |
| Claude Opus 5 | Locations (fuzzy ≥90, normalised) | 71.9% | 81.6% | 81.6% | 76.5% (71.5%–80.6%) | 74.4% | 578 | 226 | 130 |
| Claude Opus 5 | Dates (exact) | 68.9% | 71.0% | 71.0% | 69.9% (62.6%–77.1%) | 75.8% | 365 | 165 | 149 |
| Claude Opus 5 | Dates (year-set) | 86.6% | 81.6% | 81.6% | 84.0% (79.1%–88.4%) | 84.5% | 363 | 56 | 82 |
| Claude Sonnet 5 | Hazard family | 88.5% | 90.9% | 90.9% | 89.7% (87.0%–92.2%) | 87.9% | 239 | 31 | 24 |
| Claude Sonnet 5 | Locations (exact) | 55.3% | 61.2% | 61.2% | 58.1% (50.2%–65.1%) | 56.0% | 433 | 350 | 275 |
| Claude Sonnet 5 | Locations (fuzzy ≥90, raw) | 65.0% | 71.9% | 71.9% | 68.3% (62.2%–73.4%) | 65.1% | 509 | 274 | 199 |
| Claude Sonnet 5 | Locations (fuzzy ≥90, normalised) | 72.2% | 79.8% | 79.8% | 75.8% (70.7%–80.2%) | 75.4% | 565 | 218 | 143 |
| Claude Sonnet 5 | Dates (exact) | 69.4% | 69.3% | 69.3% | 69.3% (62.7%–75.7%) | 70.8% | 356 | 157 | 158 |
| Claude Sonnet 5 | Dates (year-set) | 85.3% | 83.4% | 83.4% | 84.3% (78.7%–89.0%) | 84.6% | 371 | 64 | 74 |
| DeepSeek V3.1 | Hazard family | 83.1% | 89.7% | 91.5% | 87.1% (84.2%–89.9%) | 87.3% | 236 | 48 | 22 |
| DeepSeek V3.1 | Locations (exact) | 60.5% | 62.7% | 63.3% | 61.9% (54.6%–67.9%) | 60.3% | 444 | 290 | 257 |
| DeepSeek V3.1 | Locations (fuzzy ≥90, raw) | 68.3% | 70.8% | 71.5% | 69.8% (63.5%–74.9%) | 68.9% | 501 | 233 | 200 |
| DeepSeek V3.1 | Locations (fuzzy ≥90, normalised) | 72.3% | 75.0% | 75.7% | 74.0% (68.2%–78.8%) | 75.3% | 531 | 203 | 170 |
| DeepSeek V3.1 | Dates (exact) | 71.5% | 68.7% | 69.5% | 70.5% (62.9%–77.2%) | 71.5% | 353 | 141 | 155 |
| DeepSeek V3.1 | Dates (year-set) | 86.3% | 83.4% | 84.5% | 85.4% (80.8%–89.2%) | 85.2% | 371 | 59 | 68 |
| Llama 4 Maverick | Hazard family | 68.2% | 94.7% | 94.7% | 79.3% (75.7%–82.5%) | 83.0% | 249 | 116 | 14 |
| Llama 4 Maverick | Locations (exact) | 35.9% | 54.2% | 54.2% | 43.2% (34.3%–51.6%) | 44.6% | 384 | 687 | 324 |
| Llama 4 Maverick | Locations (fuzzy ≥90, raw) | 43.9% | 66.4% | 66.4% | 52.8% (44.5%–60.2%) | 56.3% | 470 | 601 | 238 |
| Llama 4 Maverick | Locations (fuzzy ≥90, normalised) | 47.3% | 71.6% | 71.6% | 57.0% (49.0%–63.9%) | 61.1% | 507 | 564 | 201 |
| Llama 4 Maverick | Dates (exact) | 54.0% | 72.2% | 72.2% | 61.8% (54.6%–68.5%) | 64.6% | 371 | 316 | 143 |
| Llama 4 Maverick | Dates (year-set) | 74.4% | 90.1% | 90.1% | 81.5% (77.6%–85.2%) | 81.3% | 401 | 138 | 44 |
| Mistral Large | Hazard family | 71.3% | 75.7% | 75.7% | 73.4% (68.9%–77.6%) | 67.9% | 199 | 80 | 64 |
| Mistral Large | Locations (exact) | 32.5% | 43.4% | 43.4% | 37.2% (30.6%–43.9%) | 36.3% | 307 | 637 | 401 |
| Mistral Large | Locations (fuzzy ≥90, raw) | 38.6% | 51.4% | 51.4% | 44.1% (36.7%–51.0%) | 43.6% | 364 | 580 | 344 |
| Mistral Large | Locations (fuzzy ≥90, normalised) | 41.1% | 54.8% | 54.8% | 47.0% (39.9%–54.0%) | 46.3% | 388 | 556 | 320 |
| Mistral Large | Dates (exact) | 46.9% | 44.9% | 44.9% | 45.9% (39.2%–52.6%) | 44.3% | 231 | 262 | 283 |
| Mistral Large | Dates (year-set) | 72.2% | 60.7% | 60.7% | 65.9% (59.6%–72.4%) | 64.1% | 270 | 104 | 175 |
| GPT-5 (OpenRouter) | Hazard family | 89.9% | 94.7% | 94.7% | 92.2% (90.1%–94.3%) | 91.5% | 249 | 28 | 14 |
| GPT-5 (OpenRouter) | Locations (exact) | 64.8% | 67.9% | 67.9% | 66.3% (57.5%–73.7%) | 63.1% | 481 | 261 | 227 |
| GPT-5 (OpenRouter) | Locations (fuzzy ≥90, raw) | 73.2% | 76.7% | 76.7% | 74.9% (66.0%–81.3%) | 72.7% | 543 | 199 | 165 |
| GPT-5 (OpenRouter) | Locations (fuzzy ≥90, normalised) | 78.4% | 82.2% | 82.2% | 80.3% (71.4%–86.3%) | 81.1% | 582 | 160 | 126 |
| GPT-5 (OpenRouter) | Dates (exact) | 78.2% | 77.6% | 77.6% | 77.9% (71.9%–83.5%) | 78.2% | 399 | 111 | 115 |
| GPT-5 (OpenRouter) | Dates (year-set) | 90.0% | 92.8% | 92.8% | 91.4% (88.8%–93.7%) | 88.7% | 413 | 46 | 32 |
| GPT-5.4 | Hazard family | 90.7% | 93.2% | 93.2% | 91.9% (89.6%–94.3%) | 91.1% | 245 | 25 | 18 |
| GPT-5.4 | Locations (exact) | 63.2% | 65.4% | 65.4% | 64.3% (56.3%–71.1%) | 62.5% | 463 | 270 | 245 |
| GPT-5.4 | Locations (fuzzy ≥90, raw) | 71.9% | 74.4% | 74.4% | 73.1% (65.6%–78.9%) | 71.4% | 527 | 206 | 181 |
| GPT-5.4 | Locations (fuzzy ≥90, normalised) | 81.4% | 84.3% | 84.3% | 82.9% (79.9%–85.3%) | 80.1% | 597 | 136 | 111 |
| GPT-5.4 | Dates (exact) | 75.2% | 76.1% | 76.1% | 75.6% (70.2%–80.9%) | 74.7% | 391 | 129 | 123 |
| GPT-5.4 | Dates (year-set) | 92.6% | 86.7% | 86.7% | 89.6% (85.9%–92.3%) | 86.6% | 386 | 31 | 59 |
| GPT-5 mini | Hazard family | 85.4% | 93.2% | 93.2% | 89.1% (86.5%–91.7%) | 90.6% | 245 | 42 | 18 |
| GPT-5 mini | Locations (exact) | 28.0% | 32.2% | 32.2% | 30.0% (22.0%–38.1%) | 35.7% | 228 | 586 | 480 |
| GPT-5 mini | Locations (fuzzy ≥90, raw) | 41.2% | 47.3% | 47.3% | 44.0% (35.7%–51.6%) | 47.9% | 335 | 479 | 373 |
| GPT-5 mini | Locations (fuzzy ≥90, normalised) | 65.2% | 75.0% | 75.0% | 69.8% (62.6%–76.7%) | 75.6% | 531 | 283 | 177 |
| GPT-5 mini | Dates (exact) | 68.1% | 72.2% | 72.2% | 70.1% (62.4%–77.1%) | 73.2% | 371 | 174 | 143 |
| GPT-5 mini | Dates (year-set) | 84.9% | 89.7% | 89.7% | 87.2% (83.5%–90.3%) | 87.1% | 399 | 71 | 46 |
| Grok 4.6 | Hazard family | 84.6% | 93.9% | 93.9% | 89.0% (86.5%–91.4%) | 86.9% | 247 | 45 | 16 |
| Grok 4.6 | Locations (exact) | 52.3% | 67.2% | 67.2% | 58.8% (48.0%–68.6%) | 58.5% | 476 | 435 | 232 |
| Grok 4.6 | Locations (fuzzy ≥90, raw) | 62.1% | 79.9% | 79.9% | 69.9% (60.2%–77.1%) | 68.1% | 566 | 345 | 142 |
| Grok 4.6 | Locations (fuzzy ≥90, normalised) | 66.3% | 85.3% | 85.3% | 74.6% (64.7%–81.5%) | 76.1% | 604 | 307 | 104 |
| Grok 4.6 | Dates (exact) | 72.0% | 83.5% | 83.5% | 77.3% (73.0%–81.4%) | 76.4% | 429 | 167 | 85 |
| Grok 4.6 | Dates (year-set) | 85.8% | 90.8% | 90.8% | 88.2% (84.6%–91.1%) | 85.9% | 404 | 67 | 41 |
| prompt 5 (gpt-5, Azure) | Hazard family | 95.6% | 98.1% | 98.1% | 96.8% (95.0%–98.3%) | 96.7% | 258 | 12 | 5 |
| prompt 5 (gpt-5, Azure) | Locations (exact) | 94.6% | 95.9% | 95.9% | 95.2% (92.8%–97.0%) | 90.7% | 679 | 39 | 29 |
| prompt 5 (gpt-5, Azure) | Locations (fuzzy ≥90, raw) | 94.7% | 96.0% | 96.0% | 95.4% (93.0%–97.1%) | 90.8% | 680 | 38 | 28 |
| prompt 5 (gpt-5, Azure) | Locations (fuzzy ≥90, normalised) | 96.1% | 97.5% | 97.5% | 96.8% (95.0%–98.0%) | 94.1% | 690 | 28 | 18 |
| prompt 5 (gpt-5, Azure) | Dates (exact) | 94.5% | 96.5% | 96.5% | 95.5% (93.3%–97.2%) | 91.0% | 496 | 29 | 18 |
| prompt 5 (gpt-5, Azure) | Dates (year-set) | 97.6% | 98.4% | 98.4% | 98.0% (96.8%–99.0%) | 95.7% | 438 | 11 | 7 |
| NER baseline | Hazard family | 57.7% | 81.0% | 81.0% | 67.4% (63.4%–71.5%) | 67.6% | 213 | 156 | 50 |
| NER baseline | Locations (exact) | 15.4% | 28.7% | 28.7% | 20.1% (16.7%–23.5%) | 18.5% | 203 | 1111 | 505 |
| NER baseline | Locations (fuzzy ≥90, raw) | 22.5% | 41.8% | 41.8% | 29.3% (25.8%–32.7%) | 28.1% | 296 | 1018 | 412 |
| NER baseline | Locations (fuzzy ≥90, normalised) | 23.3% | 43.2% | 43.2% | 30.3% (26.7%–33.7%) | 28.9% | 306 | 1008 | 402 |
| NER baseline | Dates (exact) | 35.2% | 47.3% | 47.3% | 40.4% (34.4%–46.5%) | 38.6% | 243 | 447 | 271 |
| NER baseline | Dates (year-set) | 50.6% | 66.5% | 66.5% | 57.5% (52.7%–62.4%) | 55.0% | 296 | 289 | 149 |

## 4. All fields together, per document

Hazard, location and date treated as one content set per document, each field under its own corrected rule (hazard family; locations fuzzy ≥90 normalised; dates year-set). This is the joint question — did the run get this document right? — which no single-field row answers, because a run can be strong on hazards and weak on dates and each field's F1 hides the other.

`Exact match` is the share of gold-positive documents where the run produced every gold item and nothing else: no false positive and no false negative across all three fields. It is the strictest reading here and the one closest to "a reviewer would have accepted this row unedited".

| Run | Docs | Exact match (95% CI) | Precision | Recall | F1 (95% CI) | Macro F1 | Recall (all docs) | Exact match (all docs) |
|---|---:|---|---:|---:|---|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | 171 | 74.3% (67.2%–80.2%) | 96.5% | 97.9% | 97.2% (95.9%–98.1%) | 95.3% | 97.9% | 74.3% |
| GPT-5.4 | 171 | 38.0% (31.1%–45.5%) | 86.5% | 86.7% | 86.6% (84.3%–88.6%) | 84.6% | 86.7% | 38.0% |
| GPT-5 (OpenRouter) | 171 | 44.4% (37.2%–51.9%) | 84.2% | 87.9% | 86.0% (81.1%–89.5%) | 85.6% | 87.9% | 44.4% |
| Grok 4.6 | 171 | 32.2% (25.6%–39.5%) | 75.0% | 88.6% | 81.2% (75.8%–85.4%) | 80.8% | 88.6% | 32.2% |
| Claude Opus 5 | 171 | 31.6% (25.1%–38.9%) | 78.9% | 83.6% | 81.2% (77.5%–84.2%) | 79.4% | 83.6% | 31.6% |
| Claude Sonnet 5 | 171 | 37.4% (30.5%–44.9%) | 79.0% | 83.0% | 80.9% (76.9%–84.2%) | 80.0% | 83.0% | 37.4% |
| DeepSeek V3.1 | 166 | 31.3% (24.8%–38.7%) | 78.6% | 81.4% | 80.0% (76.1%–83.3%) | 80.3% | 80.4% | 30.4% |
| GPT-5 mini | 171 | 33.3% (26.7%–40.7%) | 74.8% | 83.0% | 78.7% (73.8%–83.2%) | 81.9% | 83.0% | 33.3% |
| Claude Haiku 4.5 | 171 | 31.6% (25.1%–38.9%) | 83.5% | 73.8% | 78.3% (73.9%–82.0%) | 72.9% | 73.8% | 31.6% |
| Llama 4 Maverick | 171 | 13.5% (9.1%–19.4%) | 58.6% | 81.7% | 68.2% (63.1%–72.4%) | 70.7% | 81.7% | 13.5% |
| Mistral Large | 171 | 8.2% (4.9%–13.3%) | 53.7% | 60.5% | 56.9% (50.7%–62.6%) | 53.8% | 60.5% | 8.2% |
| NER baseline | 171 | 1.2% (0.3%–4.2%) | 35.9% | 57.6% | 44.2% (41.3%–47.5%) | 42.9% | 57.6% | 1.2% |
| Gemini 2.5 Pro | 0 | – | – | – | – | – | 0.0% | 0.0% |
| Qwen3 235B | 0 | – | – | – | – | – | 0.0% | 0.0% |

_Sorted by F1. `Docs` is the gold-positive documents the run returned; the two right-hand columns divide by all 171 instead, so they read as pipeline yield. Precision, macro F1 and the intervals have no all-documents form — a document the run never returned supplies neither a numerator nor a denominator._

## 5. What the matching rule costs

The same run under different matching rules. A gap here is a property of the metric, not of the model — and where it is larger than the gap between two models, the metric is what is being ranked.

| Run | Loc exact | Loc fuzzy raw | Loc fuzzy normalised | Δ norm−exact | Date exact | Date year-set | Δ year−exact |
|---|---:|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | 59.5% | 69.8% | 74.5% | +14.9 pp | 65.7% | 80.8% | +15.1 pp |
| Claude Opus 5 | 59.1% | 68.3% | 76.5% | +17.3 pp | 69.9% | 84.0% | +14.1 pp |
| Claude Sonnet 5 | 58.1% | 68.3% | 75.8% | +17.7 pp | 69.3% | 84.3% | +15.0 pp |
| DeepSeek V3.1 | 61.9% | 69.8% | 74.0% | +12.1 pp | 70.5% | 85.4% | +14.9 pp |
| Llama 4 Maverick | 43.2% | 52.8% | 57.0% | +13.8 pp | 61.8% | 81.5% | +19.7 pp |
| Mistral Large | 37.2% | 44.1% | 47.0% | +9.8 pp | 45.9% | 65.9% | +20.1 pp |
| GPT-5 (OpenRouter) | 66.3% | 74.9% | 80.3% | +13.9 pp | 77.9% | 91.4% | +13.4 pp |
| GPT-5.4 | 64.3% | 73.1% | 82.9% | +18.6 pp | 75.6% | 89.6% | +13.9 pp |
| GPT-5 mini | 30.0% | 44.0% | 69.8% | +39.8 pp | 70.1% | 87.2% | +17.1 pp |
| Grok 4.6 | 58.8% | 69.9% | 74.6% | +15.8 pp | 77.3% | 88.2% | +10.9 pp |
| prompt 5 (gpt-5, Azure) | 95.2% | 95.4% | 96.8% | +1.5 pp | 95.5% | 98.0% | +2.5 pp |
| NER baseline | 20.1% | 29.3% | 30.3% | +10.2 pp | 40.4% | 57.5% | +17.1 pp |

## 6. Paired comparison — exact McNemar on event detection

Paired over the documents **both** runs returned, so a run is never charged for the other's failed calls. `n` is that intersection.

| A | B | n | A only | B only | p |
|---|---|---:|---:|---:|---:|
| Claude Haiku 4.5 | Claude Opus 5 | 217 | 4 | 12 | 0.0768 |
| Claude Haiku 4.5 | Claude Sonnet 5 | 217 | 5 | 14 | 0.0636 |
| Claude Haiku 4.5 | DeepSeek V3.1 | 199 | 7 | 18 | **0.0433** |
| Claude Haiku 4.5 | Llama 4 Maverick | 217 | 8 | 19 | 0.0522 |
| Claude Haiku 4.5 | Mistral Large | 217 | 32 | 13 | **0.0066** |
| Claude Haiku 4.5 | GPT-5 (OpenRouter) | 217 | 4 | 18 | **0.0043** |
| Claude Haiku 4.5 | GPT-5.4 | 217 | 3 | 16 | **0.0044** |
| Claude Haiku 4.5 | GPT-5 mini | 217 | 6 | 20 | **0.0094** |
| Claude Haiku 4.5 | Grok 4.6 | 217 | 7 | 14 | 0.1892 |
| Claude Haiku 4.5 | prompt 5 (gpt-5, Azure) | 217 | 2 | 20 | **0.0001** |
| Claude Haiku 4.5 | NER baseline | 217 | 25 | 19 | 0.4514 |
| Claude Opus 5 | Claude Sonnet 5 | 217 | 4 | 5 | 1.0000 |
| Claude Opus 5 | DeepSeek V3.1 | 199 | 6 | 10 | 0.4545 |
| Claude Opus 5 | Llama 4 Maverick | 217 | 7 | 10 | 0.6291 |
| Claude Opus 5 | Mistral Large | 217 | 37 | 10 | **0.0001** |
| Claude Opus 5 | GPT-5 (OpenRouter) | 217 | 3 | 9 | 0.1460 |
| Claude Opus 5 | GPT-5.4 | 217 | 2 | 7 | 0.1797 |
| Claude Opus 5 | GPT-5 mini | 217 | 4 | 10 | 0.1796 |
| Claude Opus 5 | Grok 4.6 | 217 | 7 | 6 | 1.0000 |
| Claude Opus 5 | prompt 5 (gpt-5, Azure) | 217 | 1 | 11 | **0.0063** |
| Claude Opus 5 | NER baseline | 217 | 27 | 13 | **0.0385** |
| Claude Sonnet 5 | DeepSeek V3.1 | 199 | 6 | 10 | 0.4545 |
| Claude Sonnet 5 | Llama 4 Maverick | 217 | 7 | 9 | 0.8036 |
| Claude Sonnet 5 | Mistral Large | 217 | 38 | 10 | **0.0001** |
| Claude Sonnet 5 | GPT-5 (OpenRouter) | 217 | 4 | 9 | 0.2668 |
| Claude Sonnet 5 | GPT-5.4 | 217 | 4 | 8 | 0.3877 |
| Claude Sonnet 5 | GPT-5 mini | 217 | 5 | 10 | 0.3018 |
| Claude Sonnet 5 | Grok 4.6 | 217 | 10 | 8 | 0.8145 |
| Claude Sonnet 5 | prompt 5 (gpt-5, Azure) | 217 | 2 | 11 | **0.0225** |
| Claude Sonnet 5 | NER baseline | 217 | 27 | 12 | **0.0237** |
| DeepSeek V3.1 | Llama 4 Maverick | 199 | 6 | 6 | 1.0000 |
| DeepSeek V3.1 | Mistral Large | 199 | 33 | 5 | **0.0000** |
| DeepSeek V3.1 | GPT-5 (OpenRouter) | 199 | 4 | 6 | 0.7539 |
| DeepSeek V3.1 | GPT-5.4 | 199 | 5 | 6 | 1.0000 |
| DeepSeek V3.1 | GPT-5 mini | 199 | 3 | 7 | 0.3438 |
| DeepSeek V3.1 | Grok 4.6 | 199 | 7 | 4 | 0.5488 |
| DeepSeek V3.1 | prompt 5 (gpt-5, Azure) | 199 | 1 | 7 | 0.0703 |
| DeepSeek V3.1 | NER baseline | 199 | 22 | 8 | **0.0161** |
| Llama 4 Maverick | Mistral Large | 217 | 35 | 5 | **0.0000** |
| Llama 4 Maverick | GPT-5 (OpenRouter) | 217 | 4 | 7 | 0.5488 |
| Llama 4 Maverick | GPT-5.4 | 217 | 5 | 7 | 0.7744 |
| Llama 4 Maverick | GPT-5 mini | 217 | 2 | 5 | 0.4531 |
| Llama 4 Maverick | Grok 4.6 | 217 | 8 | 4 | 0.3877 |
| Llama 4 Maverick | prompt 5 (gpt-5, Azure) | 217 | 2 | 9 | 0.0654 |
| Llama 4 Maverick | NER baseline | 217 | 23 | 6 | **0.0023** |
| Mistral Large | GPT-5 (OpenRouter) | 217 | 4 | 37 | **0.0000** |
| Mistral Large | GPT-5.4 | 217 | 5 | 37 | **0.0000** |
| Mistral Large | GPT-5 mini | 217 | 6 | 39 | **0.0000** |
| Mistral Large | Grok 4.6 | 217 | 10 | 36 | **0.0002** |
| Mistral Large | prompt 5 (gpt-5, Azure) | 217 | 3 | 40 | **0.0000** |
| Mistral Large | NER baseline | 217 | 24 | 37 | 0.1237 |
| GPT-5 (OpenRouter) | GPT-5.4 | 217 | 3 | 2 | 1.0000 |
| GPT-5 (OpenRouter) | GPT-5 mini | 217 | 4 | 4 | 1.0000 |
| GPT-5 (OpenRouter) | Grok 4.6 | 217 | 9 | 2 | 0.0654 |
| GPT-5 (OpenRouter) | prompt 5 (gpt-5, Azure) | 217 | 0 | 4 | 0.1250 |
| GPT-5 (OpenRouter) | NER baseline | 217 | 26 | 6 | **0.0005** |
| GPT-5.4 | GPT-5 mini | 217 | 4 | 5 | 1.0000 |
| GPT-5.4 | Grok 4.6 | 217 | 7 | 1 | 0.0703 |
| GPT-5.4 | prompt 5 (gpt-5, Azure) | 217 | 0 | 5 | 0.0625 |
| GPT-5.4 | NER baseline | 217 | 26 | 7 | **0.0013** |
| GPT-5 mini | Grok 4.6 | 217 | 9 | 2 | 0.0654 |
| GPT-5 mini | prompt 5 (gpt-5, Azure) | 217 | 1 | 5 | 0.2188 |
| GPT-5 mini | NER baseline | 217 | 23 | 3 | **0.0001** |
| Grok 4.6 | prompt 5 (gpt-5, Azure) | 217 | 0 | 11 | **0.0010** |
| Grok 4.6 | NER baseline | 217 | 23 | 10 | **0.0351** |
| prompt 5 (gpt-5, Azure) | NER baseline | 217 | 27 | 3 | **0.0000** |

_'A only' counts documents A got right and B got wrong. p is two-sided; the concordant pairs carry no information. Bold marks p < 0.05, uncorrected for multiple comparisons — with 66 pairs, expect some by chance._

## 7. Coverage gaps in detail

- **DeepSeek V3.1**: 18 returned only error rows — excluded from its denominator.
- **Gemini 2.5 Pro**: 217 returned only error rows — excluded from its denominator.
- **Qwen3 235B**: 217 returned only error rows — excluded from its denominator.
