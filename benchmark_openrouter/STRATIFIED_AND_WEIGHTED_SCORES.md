# Per-stratum scores and corpus-weighted estimates

Annotations: `eval/human_annotations_pooled.csv` — 217 documents over two sampling arms. Every score here uses the corrected matching rules (hazard family; locations fuzzy ≥90 normalised; dates year-set) and the **exclude** error policy: a document a run returned only error rows for is dropped from that run's denominator in the stratum it belongs to.

| Stratum | Sampled | Gold-positive | Prevalence | Corpus documents | Weight |
|---|---:|---:|---:|---:|---:|
| Event stratum (GPT-5 flagged) | 167 | 157 | 94.0% | 1,913 | 11.46 |
| Remaining stratum (random draw) | 50 | 14 | 28.0% | 8,087 | 161.74 |
| **Corpus** | **217** | | | **10,000** | |

_The event stratum is the 1,913 documents the production GPT-5 run flagged; the remaining stratum is the 8,087 it declined. The 94.0% / 28.0% prevalence split is the whole reason a pooled number is hard to read: the pool's 78.8% is an artefact of the mixture and describes no real population._

## 1. Detection, per stratum

The question this answers: does a model that looks strong overall stay strong on the documents GPT-5 declined? Recall in the remaining stratum is exactly "of the events GPT-5 missed, how many did this model find". Specificity is only estimable in the remaining stratum — the event stratum's 10 gold-negatives are the production run's own false positives, an adversarial set, not an ordinary one.

| Run | n (event) | Recall (event) | Prec. (event) | Spec. (event) | n (remaining) | Recall (remaining) | Prec. (remaining) | Spec. (remaining) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | 167 | 89.2% | 94.6% | 20.0% | 50 | 64.3% | 90.0% | 97.2% |
| Claude Opus 5 | 167 | 94.9% | 94.3% | 10.0% | 50 | 71.4% | 83.3% | 94.4% |
| Claude Sonnet 5 | 167 | 94.9% | 94.3% | 10.0% | 50 | 78.6% | 84.6% | 94.4% |
| DeepSeek V3.1 | 167 | 96.8% | 94.4% | 10.0% | 50 | 71.4% | 83.3% | 94.4% |
| Llama 4 Maverick | 167 | 98.1% | 93.9% | 0.0% | 50 | 92.9% | 68.4% | 83.3% |
| Mistral Large | 167 | 79.6% | 94.0% | 20.0% | 50 | 71.4% | 62.5% | 83.3% |
| GPT-5 (OpenRouter) | 167 | 98.1% | 93.9% | 0.0% | 50 | 78.6% | 91.7% | 97.2% |
| GPT-5.4 | 167 | 97.5% | 93.9% | 0.0% | 50 | 78.6% | 91.7% | 97.2% |
| GPT-5 mini | 167 | 99.4% | 94.0% | 0.0% | 50 | 85.7% | 75.0% | 88.9% |
| Grok 4.6 | 167 | 94.9% | 93.7% | 0.0% | 50 | 78.6% | 78.6% | 91.7% |
| prompt 5 (gpt-5, Azure) | 167 | 100.0% | 94.0% | 0.0% | 50 | 78.6% | 100.0% | 100.0% |
| NER baseline | 167 | 90.4% | 94.0% | 10.0% | 50 | 78.6% | 52.4% | 72.2% |

_`n` is the documents that run returned in that stratum. Recall divides by the gold-positive documents among them — 157 at most in the event stratum, **14 at most in the remaining stratum**, so a single document moves the right-hand recall by about 7 points and small differences there are noise._

### Detection confusion matrices, per stratum

| Run | Stratum | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | Event stratum (GPT-5 flagged) | 140 | 8 | 17 | 2 | 94.6% | 89.2% | 91.8% |
| Claude Haiku 4.5 | Remaining stratum (random draw) | 9 | 1 | 5 | 35 | 90.0% | 64.3% | 75.0% |
| Claude Opus 5 | Event stratum (GPT-5 flagged) | 149 | 9 | 8 | 1 | 94.3% | 94.9% | 94.6% |
| Claude Opus 5 | Remaining stratum (random draw) | 10 | 2 | 4 | 34 | 83.3% | 71.4% | 76.9% |
| Claude Sonnet 5 | Event stratum (GPT-5 flagged) | 149 | 9 | 8 | 1 | 94.3% | 94.9% | 94.6% |
| Claude Sonnet 5 | Remaining stratum (random draw) | 11 | 2 | 3 | 34 | 84.6% | 78.6% | 81.5% |
| DeepSeek V3.1 | Event stratum (GPT-5 flagged) | 152 | 9 | 5 | 1 | 94.4% | 96.8% | 95.6% |
| DeepSeek V3.1 | Remaining stratum (random draw) | 10 | 2 | 4 | 34 | 83.3% | 71.4% | 76.9% |
| Llama 4 Maverick | Event stratum (GPT-5 flagged) | 154 | 10 | 3 | 0 | 93.9% | 98.1% | 96.0% |
| Llama 4 Maverick | Remaining stratum (random draw) | 13 | 6 | 1 | 30 | 68.4% | 92.9% | 78.8% |
| Mistral Large | Event stratum (GPT-5 flagged) | 125 | 8 | 32 | 2 | 94.0% | 79.6% | 86.2% |
| Mistral Large | Remaining stratum (random draw) | 10 | 6 | 4 | 30 | 62.5% | 71.4% | 66.7% |
| GPT-5 (OpenRouter) | Event stratum (GPT-5 flagged) | 154 | 10 | 3 | 0 | 93.9% | 98.1% | 96.0% |
| GPT-5 (OpenRouter) | Remaining stratum (random draw) | 11 | 1 | 3 | 35 | 91.7% | 78.6% | 84.6% |
| GPT-5.4 | Event stratum (GPT-5 flagged) | 153 | 10 | 4 | 0 | 93.9% | 97.5% | 95.6% |
| GPT-5.4 | Remaining stratum (random draw) | 11 | 1 | 3 | 35 | 91.7% | 78.6% | 84.6% |
| GPT-5 mini | Event stratum (GPT-5 flagged) | 156 | 10 | 1 | 0 | 94.0% | 99.4% | 96.6% |
| GPT-5 mini | Remaining stratum (random draw) | 12 | 4 | 2 | 32 | 75.0% | 85.7% | 80.0% |
| Grok 4.6 | Event stratum (GPT-5 flagged) | 149 | 10 | 8 | 0 | 93.7% | 94.9% | 94.3% |
| Grok 4.6 | Remaining stratum (random draw) | 11 | 3 | 3 | 33 | 78.6% | 78.6% | 78.6% |
| prompt 5 (gpt-5, Azure) | Event stratum (GPT-5 flagged) | 157 | 10 | 0 | 0 | 94.0% | 100.0% | 96.9% |
| prompt 5 (gpt-5, Azure) | Remaining stratum (random draw) | 11 | 0 | 3 | 36 | 100.0% | 78.6% | 88.0% |
| NER baseline | Event stratum (GPT-5 flagged) | 142 | 9 | 15 | 1 | 94.0% | 90.4% | 92.2% |
| NER baseline | Remaining stratum (random draw) | 11 | 10 | 3 | 26 | 52.4% | 78.6% | 62.9% |

## 2. Field extraction, per stratum

Micro P/R/F1 over the gold-positive documents in each stratum, pooling TP/FP/FN across documents. This is conditional on the document carrying an event, so unlike detection it is not distorted by the prevalence gap — but the remaining stratum still rests on at most 14 documents per run.

### Hazard family

| Run | n (event) | P (event) | R (event) | F1 (event) | n (remaining) | P (remaining) | R (remaining) | F1 (remaining) | Δ F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | 157 | 90.9% | 81.0% | 85.7% | 14 | 90.9% | 62.5% | 74.1% | -11.6 pp |
| Claude Opus 5 | 157 | 87.5% | 93.5% | 90.4% | 14 | 85.7% | 75.0% | 80.0% | -10.4 pp |
| Claude Sonnet 5 | 157 | 88.3% | 91.5% | 89.9% | 14 | 92.9% | 81.2% | 86.7% | -3.2 pp |
| DeepSeek V3.1 | 157 | 82.8% | 91.9% | 87.1% | 14 | 85.7% | 75.0% | 80.0% | -7.1 pp |
| Llama 4 Maverick | 157 | 68.1% | 95.1% | 79.4% | 14 | 70.0% | 87.5% | 77.8% | -1.6 pp |
| Mistral Large | 157 | 71.6% | 76.5% | 74.0% | 14 | 66.7% | 62.5% | 64.5% | -9.5 pp |
| GPT-5 (OpenRouter) | 157 | 90.1% | 95.5% | 92.7% | 14 | 86.7% | 81.2% | 83.9% | -8.9 pp |
| GPT-5.4 | 157 | 90.9% | 93.5% | 92.2% | 14 | 87.5% | 87.5% | 87.5% | -4.7 pp |
| GPT-5 mini | 157 | 85.6% | 93.5% | 89.4% | 14 | 82.4% | 87.5% | 84.8% | -4.5 pp |
| Grok 4.6 | 157 | 84.8% | 94.7% | 89.5% | 14 | 81.2% | 81.2% | 81.2% | -8.2 pp |
| prompt 5 (gpt-5, Azure) | 157 | 95.3% | 98.8% | 97.0% | 14 | 100.0% | 87.5% | 93.3% | -3.7 pp |
| NER baseline | 157 | 58.0% | 81.0% | 67.6% | 14 | 54.2% | 81.2% | 65.0% | -2.6 pp |

### Locations

| Run | n (event) | P (event) | R (event) | F1 (event) | n (remaining) | P (remaining) | R (remaining) | F1 (remaining) | Δ F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | 157 | 77.7% | 72.8% | 75.1% | 14 | 63.2% | 48.0% | 54.5% | -20.6 pp |
| Claude Opus 5 | 157 | 72.7% | 81.8% | 77.0% | 14 | 54.3% | 76.0% | 63.3% | -13.7 pp |
| Claude Sonnet 5 | 157 | 73.3% | 79.9% | 76.5% | 14 | 50.0% | 76.0% | 60.3% | -16.2 pp |
| DeepSeek V3.1 | 157 | 71.9% | 76.0% | 73.9% | 14 | 78.9% | 60.0% | 68.2% | -5.7 pp |
| Llama 4 Maverick | 157 | 47.8% | 71.7% | 57.3% | 14 | 37.8% | 68.0% | 48.6% | -8.8 pp |
| Mistral Large | 157 | 42.4% | 54.9% | 47.8% | 14 | 22.0% | 52.0% | 31.0% | -16.9 pp |
| GPT-5 (OpenRouter) | 157 | 78.7% | 82.4% | 80.5% | 14 | 70.4% | 76.0% | 73.1% | -7.5 pp |
| GPT-5.4 | 157 | 81.4% | 84.2% | 82.8% | 14 | 81.5% | 88.0% | 84.6% | +1.8 pp |
| GPT-5 mini | 157 | 66.3% | 75.0% | 70.4% | 14 | 45.2% | 76.0% | 56.7% | -13.7 pp |
| Grok 4.6 | 157 | 66.6% | 85.4% | 74.8% | 14 | 60.0% | 84.0% | 70.0% | -4.8 pp |
| prompt 5 (gpt-5, Azure) | 157 | 96.0% | 97.7% | 96.8% | 14 | 100.0% | 92.0% | 95.8% | -1.0 pp |
| NER baseline | 157 | 23.4% | 42.0% | 30.0% | 14 | 22.1% | 76.0% | 34.2% | +4.2 pp |

### Dates

| Run | n (event) | P (event) | R (event) | F1 (event) | n (remaining) | P (remaining) | R (remaining) | F1 (remaining) | Δ F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | 157 | 89.8% | 74.4% | 81.4% | 14 | 100.0% | 47.4% | 64.3% | -17.1 pp |
| Claude Opus 5 | 157 | 86.6% | 82.2% | 84.3% | 14 | 86.7% | 68.4% | 76.5% | -7.9 pp |
| Claude Sonnet 5 | 157 | 85.4% | 83.6% | 84.5% | 14 | 83.3% | 78.9% | 81.1% | -3.4 pp |
| DeepSeek V3.1 | 157 | 86.0% | 84.7% | 85.3% | 14 | 92.9% | 68.4% | 78.8% | -6.6 pp |
| Llama 4 Maverick | 157 | 74.3% | 90.4% | 81.6% | 14 | 76.2% | 84.2% | 80.0% | -1.6 pp |
| Mistral Large | 157 | 71.8% | 61.0% | 66.0% | 14 | 83.3% | 52.6% | 64.5% | -1.5 pp |
| GPT-5 (OpenRouter) | 157 | 90.1% | 93.7% | 91.8% | 14 | 87.5% | 73.7% | 80.0% | -11.8 pp |
| GPT-5.4 | 157 | 92.7% | 86.6% | 89.6% | 14 | 89.5% | 89.5% | 89.5% | -0.1 pp |
| GPT-5 mini | 157 | 84.8% | 90.1% | 87.4% | 14 | 88.2% | 78.9% | 83.3% | -4.0 pp |
| Grok 4.6 | 157 | 85.7% | 91.3% | 88.4% | 14 | 88.2% | 78.9% | 83.3% | -5.1 pp |
| prompt 5 (gpt-5, Azure) | 157 | 97.5% | 98.8% | 98.1% | 14 | 100.0% | 89.5% | 94.4% | -3.7 pp |
| NER baseline | 157 | 50.4% | 65.7% | 57.0% | 14 | 55.2% | 84.2% | 66.7% | +9.6 pp |

### All fields

| Run | n (event) | P (event) | R (event) | F1 (event) | n (remaining) | P (remaining) | R (remaining) | F1 (remaining) | Δ F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | 157 | 83.6% | 74.8% | 78.9% | 14 | 79.5% | 51.7% | 62.6% | -16.3 pp |
| Claude Opus 5 | 157 | 79.3% | 84.1% | 81.6% | 14 | 68.8% | 73.3% | 71.0% | -10.7 pp |
| Claude Sonnet 5 | 157 | 79.5% | 83.2% | 81.3% | 14 | 67.1% | 78.3% | 72.3% | -9.0 pp |
| DeepSeek V3.1 | 157 | 78.2% | 81.6% | 79.9% | 14 | 85.1% | 66.7% | 74.8% | -5.1 pp |
| Llama 4 Maverick | 157 | 58.8% | 81.9% | 68.4% | 14 | 54.7% | 78.3% | 64.4% | -4.0 pp |
| Mistral Large | 157 | 54.5% | 60.8% | 57.5% | 14 | 38.4% | 55.0% | 45.2% | -12.3 pp |
| GPT-5 (OpenRouter) | 157 | 84.4% | 88.3% | 86.3% | 14 | 79.3% | 76.7% | 78.0% | -8.3 pp |
| GPT-5.4 | 157 | 86.5% | 86.7% | 86.6% | 14 | 85.5% | 88.3% | 86.9% | +0.3 pp |
| GPT-5 mini | 157 | 75.4% | 83.1% | 79.1% | 14 | 63.2% | 80.0% | 70.6% | -8.5 pp |
| Grok 4.6 | 157 | 75.1% | 88.9% | 81.4% | 14 | 72.1% | 81.7% | 76.6% | -4.9 pp |
| prompt 5 (gpt-5, Azure) | 157 | 96.3% | 98.2% | 97.3% | 14 | 100.0% | 90.0% | 94.7% | -2.5 pp |
| NER baseline | 157 | 36.0% | 56.6% | 44.0% | 14 | 34.5% | 80.0% | 48.2% | +4.2 pp |

_`Δ F1` is remaining minus event: negative means the model describes the documents GPT-5 missed worse than the ones it found. A large negative gap on a model with high pooled scores means the pooled score is carried by the enriched arm._

## 3. Corpus-weighted estimates (10,000 documents)

Every document is weighted by the inverse of its sampling rate, so the 217-document sample estimates the corpus. Weights are ratio-adjusted for coverage: a run that lost documents in a stratum has its survivors there weighted up to cover the whole stratum. Intervals are a 95% percentile stratified bootstrap (2,000 replicates, seed 42, resampled within stratum with the weights recomputed each time).

### 3a. Detection

| Run | Weighted precision (95% CI) | Weighted recall (95% CI) | F1 | Est. events in corpus | Est. corpus recall base |
|---|---|---|---:|---:|---:|
| Claude Haiku 4.5 | 92.4% (81.4%–98.7%) | 75.3% (61.0%–89.1%) | 83.0% | 3,313 | 4,063 |
| Claude Opus 5 | 88.6% (75.4%–98.1%) | 81.8% (67.9%–94.4%) | 85.1% | 3,751 | 4,063 |
| Claude Sonnet 5 | 89.1% (76.2%–98.2%) | 85.8% (72.9%–97.7%) | 87.4% | 3,913 | 4,063 |
| DeepSeek V3.1 | 88.7% (76.5%–98.1%) | 82.7% (68.4%–94.7%) | 85.6% | 3,785 | 4,063 |
| Llama 4 Maverick | 78.1% (64.1%–91.4%) | 95.2% (86.0%–99.7%) | 85.8% | 4,952 | 4,063 |
| Mistral Large | 74.2% (58.0%–89.8%) | 75.1% (60.8%–87.4%) | 74.6% | 4,111 | 4,063 |
| GPT-5 (OpenRouter) | 92.8% (83.0%–98.4%) | 87.2% (73.9%–99.0%) | 89.9% | 3,820 | 4,063 |
| GPT-5.4 | 92.7% (83.0%–98.3%) | 86.9% (73.7%–98.7%) | 89.7% | 3,808 | 4,063 |
| GPT-5 mini | 83.0% (69.7%–94.8%) | 91.8% (80.9%–100.0%) | 87.2% | 4,489 | 4,063 |
| Grok 4.6 | 85.3% (72.1%–97.3%) | 85.8% (72.8%–97.5%) | 85.6% | 4,086 | 4,063 |
| prompt 5 (gpt-5, Azure) | 96.9% (94.4%–98.6%) | 88.1% (75.0%–100.0%) | 92.3% | 3,692 | 4,063 |
| NER baseline | 66.4% (51.7%–81.1%) | 83.8% (71.0%–95.1%) | 74.1% | 5,126 | 4,063 |

_`Est. events in corpus` is how many of the 10,000 documents this run would flag; `Est. corpus recall base` is how many actually carry an event by gold, which is the same for every run up to its coverage and is the corpus prevalence estimate this design produces._

### 3b. Fields

| Run | Field | Weighted precision (95% CI) | Weighted recall (95% CI) | F1 |
|---|---|---|---|---:|
| Claude Haiku 4.5 | Hazard family | 90.9% (83.7%–96.3%) | 72.1% (61.1%–82.7%) | 80.4% |
| Claude Haiku 4.5 | Locations | 73.4% (59.7%–84.3%) | 64.3% (53.8%–75.0%) | 68.6% |
| Claude Haiku 4.5 | Dates | 92.5% (89.3%–95.3%) | 64.0% (53.4%–76.0%) | 75.6% |
| Claude Haiku 4.5 | All fields | 82.3% (74.0%–89.0%) | 65.9% (56.2%–76.4%) | 73.2% |
| Claude Opus 5 | Hazard family | 86.7% (80.0%–92.9%) | 84.7% (74.2%–94.3%) | 85.7% |
| Claude Opus 5 | Locations | 65.5% (55.2%–76.4%) | 79.9% (72.3%–86.8%) | 72.0% |
| Claude Opus 5 | Dates | 86.6% (80.2%–92.7%) | 76.9% (67.6%–86.4%) | 81.5% |
| Claude Opus 5 | All fields | 75.2% (68.7%–82.3%) | 79.9% (71.7%–87.6%) | 77.5% |
| Claude Sonnet 5 | Hazard family | 90.3% (84.0%–94.8%) | 86.6% (77.3%–95.2%) | 88.4% |
| Claude Sonnet 5 | Locations | 63.5% (51.9%–75.2%) | 78.6% (70.1%–86.7%) | 70.3% |
| Claude Sonnet 5 | Dates | 84.6% (78.8%–91.0%) | 81.8% (71.7%–91.5%) | 83.2% |
| Claude Sonnet 5 | All fields | 74.5% (67.1%–81.5%) | 81.3% (73.3%–89.2%) | 77.7% |
| DeepSeek V3.1 | Hazard family | 84.0% (75.1%–91.1%) | 83.8% (72.1%–93.3%) | 83.9% |
| DeepSeek V3.1 | Locations | 73.8% (64.5%–81.3%) | 70.5% (60.3%–80.0%) | 72.1% |
| DeepSeek V3.1 | Dates | 88.2% (81.5%–92.9%) | 78.4% (67.9%–88.1%) | 83.0% |
| DeepSeek V3.1 | All fields | 80.4% (73.5%–86.1%) | 75.9% (66.1%–84.6%) | 78.1% |
| Llama 4 Maverick | Hazard family | 69.0% (60.3%–78.8%) | 91.5% (84.5%–98.1%) | 78.6% |
| Llama 4 Maverick | Locations | 43.9% (31.4%–56.1%) | 70.5% (60.4%–79.6%) | 54.1% |
| Llama 4 Maverick | Dates | 75.0% (69.9%–80.4%) | 88.0% (79.9%–95.5%) | 81.0% |
| Llama 4 Maverick | All fields | 57.2% (47.1%–65.9%) | 80.5% (73.6%–87.2%) | 66.8% |
| Mistral Large | Hazard family | 69.4% (59.6%–80.9%) | 69.8% (57.0%–82.0%) | 69.6% |
| Mistral Large | Locations | 32.5% (25.2%–42.2%) | 53.9% (39.8%–69.0%) | 40.6% |
| Mistral Large | Dates | 75.5% (68.8%–82.1%) | 57.8% (45.0%–71.6%) | 65.5% |
| Mistral Large | All fields | 47.3% (39.3%–56.3%) | 58.5% (45.8%–71.7%) | 52.3% |
| GPT-5 (OpenRouter) | Hazard family | 88.6% (82.0%–94.7%) | 88.7% (79.2%–97.3%) | 88.6% |
| GPT-5 (OpenRouter) | Locations | 75.8% (68.0%–83.9%) | 80.2% (69.7%–88.7%) | 78.0% |
| GPT-5 (OpenRouter) | Dates | 89.2% (83.5%–94.6%) | 85.9% (76.5%–94.6%) | 87.5% |
| GPT-5 (OpenRouter) | All fields | 82.5% (77.6%–87.9%) | 83.9% (75.3%–91.6%) | 83.2% |
| GPT-5.4 | Hazard family | 89.3% (82.6%–95.6%) | 90.6% (81.5%–97.4%) | 90.0% |
| GPT-5.4 | Locations | 81.5% (75.4%–86.7%) | 85.5% (79.5%–90.2%) | 83.4% |
| GPT-5.4 | Dates | 91.4% (85.4%–96.6%) | 87.7% (79.9%–93.7%) | 89.5% |
| GPT-5.4 | All fields | 86.1% (81.6%–90.7%) | 87.3% (80.4%–92.2%) | 86.7% |
| GPT-5 mini | Hazard family | 84.0% (78.0%–90.6%) | 90.6% (82.6%–97.4%) | 87.2% |
| GPT-5 mini | Locations | 57.2% (47.0%–69.1%) | 75.3% (65.7%–85.7%) | 65.0% |
| GPT-5 mini | Dates | 86.0% (81.4%–90.4%) | 85.8% (77.3%–94.2%) | 85.9% |
| GPT-5 mini | All fields | 70.3% (63.0%–78.1%) | 81.9% (73.8%–90.2%) | 75.7% |
| Grok 4.6 | Hazard family | 83.2% (76.7%–90.4%) | 88.3% (78.8%–97.0%) | 85.7% |
| Grok 4.6 | Locations | 64.2% (54.1%–74.5%) | 84.9% (74.7%–93.3%) | 73.1% |
| Grok 4.6 | Dates | 86.6% (81.2%–91.9%) | 86.5% (77.2%–94.8%) | 86.6% |
| Grok 4.6 | All fields | 74.0% (67.7%–80.5%) | 86.1% (77.7%–93.8%) | 79.6% |
| prompt 5 (gpt-5, Azure) | Hazard family | 97.4% (95.5%–98.8%) | 93.4% (84.5%–99.6%) | 95.3% |
| prompt 5 (gpt-5, Azure) | Locations | 97.3% (95.4%–98.7%) | 95.7% (91.1%–98.7%) | 96.5% |
| prompt 5 (gpt-5, Azure) | Dates | 98.4% (97.0%–99.4%) | 95.2% (88.7%–99.5%) | 96.8% |
| prompt 5 (gpt-5, Azure) | All fields | 97.6% (96.4%–98.6%) | 95.1% (89.0%–99.1%) | 96.3% |
| NER baseline | Hazard family | 56.1% (48.4%–65.0%) | 81.1% (68.7%–91.4%) | 66.3% |
| NER baseline | Locations | 22.7% (17.6%–29.0%) | 53.6% (43.0%–64.2%) | 31.9% |
| NER baseline | Dates | 52.4% (47.4%–57.7%) | 72.9% (64.7%–80.5%) | 61.0% |
| NER baseline | All fields | 35.3% (29.8%–41.5%) | 65.6% (56.3%–74.2%) | 45.9% |

## 4. Sensitivity — the arm is not exactly the stratum

The 50 were drawn uniformly over the 9,833 documents not already annotated, not over the 8,087 the production run declined. Eleven of them are documents GPT-5 *did* flag, and §3 gives those a remaining-stratum weight of 161.74 when they belong to a stratum whose weight is 11.46. Post-stratifying on what the production run actually did puts each of the 217 in its true stratum — 178 flagged at 10.75, 39 declined at 207.36 — and both schemes still partition the corpus exactly.

| Run | Detection P (arm) | Detection P (flag) | Δ | Detection R (arm) | Detection R (flag) | Δ |
|---|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | 92.4% | 84.5% | -7.8 pp | 75.3% | 66.0% | -9.3 pp |
| Claude Opus 5 | 88.6% | 77.0% | -11.7 pp | 81.8% | 70.4% | -11.4 pp |
| Claude Sonnet 5 | 89.1% | 78.9% | -10.2 pp | 85.8% | 78.9% | -6.9 pp |
| DeepSeek V3.1 | 88.7% | 77.3% | -11.4 pp | 82.7% | 71.7% | -10.9 pp |
| Llama 4 Maverick | 78.1% | 61.8% | -16.3 pp | 95.2% | 90.1% | -5.0 pp |
| Mistral Large | 74.2% | 55.3% | -18.8 pp | 75.1% | 67.9% | -7.2 pp |
| GPT-5 (OpenRouter) | 92.8% | 84.9% | -7.8 pp | 87.2% | 73.0% | -14.2 pp |
| GPT-5.4 | 92.7% | 84.8% | -7.9 pp | 86.9% | 72.6% | -14.3 pp |
| GPT-5 mini | 83.0% | 68.1% | -14.9 pp | 91.8% | 82.5% | -9.3 pp |
| Grok 4.6 | 85.3% | 70.2% | -15.1 pp | 85.8% | 70.8% | -15.0 pp |
| prompt 5 (gpt-5, Azure) | 96.9% | 94.4% | -2.5 pp | 88.1% | 74.4% | -13.7 pp |
| NER baseline | 66.4% | 48.4% | -18.0 pp | 83.8% | 83.9% | +0.1 pp |

| Run | All-fields P (arm) | All-fields P (flag) | Δ | All-fields R (arm) | All-fields R (flag) | Δ |
|---|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | 82.3% | 83.5% | +1.2 pp | 65.9% | 68.5% | +2.6 pp |
| Claude Opus 5 | 75.2% | 78.9% | +3.6 pp | 79.9% | 77.6% | -2.3 pp |
| Claude Sonnet 5 | 74.5% | 78.8% | +4.3 pp | 81.3% | 80.6% | -0.7 pp |
| DeepSeek V3.1 | 80.4% | 78.4% | -2.0 pp | 75.9% | 75.2% | -0.7 pp |
| Llama 4 Maverick | 57.2% | 60.2% | +3.1 pp | 80.5% | 83.0% | +2.5 pp |
| Mistral Large | 47.3% | 54.6% | +7.3 pp | 58.5% | 59.8% | +1.2 pp |
| GPT-5 (OpenRouter) | 82.5% | 84.2% | +1.7 pp | 83.9% | 81.5% | -2.3 pp |
| GPT-5.4 | 86.1% | 86.5% | +0.4 pp | 87.3% | 80.5% | -6.8 pp |
| GPT-5 mini | 70.3% | 75.6% | +5.4 pp | 81.9% | 80.6% | -1.3 pp |
| Grok 4.6 | 74.0% | 75.0% | +1.0 pp | 86.1% | 82.3% | -3.9 pp |
| prompt 5 (gpt-5, Azure) | 97.6% | 96.5% | -1.2 pp | 95.1% | 90.8% | -4.2 pp |
| NER baseline | 35.3% | 34.9% | -0.4 pp | 65.6% | 59.4% | -6.2 pp |

_Where the two columns agree, the approximation in §3 costs nothing. Where they do not, the `flag` figure is the better estimate._

