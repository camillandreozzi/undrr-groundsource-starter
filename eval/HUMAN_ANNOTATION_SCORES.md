# Extraction runs scored against human annotations

Annotations: `eval/human_annotations.csv` — 167 annotated rows over 167 documents, 157 of which carry a verifiable event (94.0% prevalence).

All metrics are per document; see the module docstring for why. Error policy: **exclude** — documents a run returned only error rows for are excluded from its denominator and reported as coverage below.

## 1. Documents processed, and the score relative to them

A run cannot be credited or blamed for a document it never got back, so every score in this report is computed over the documents that run actually returned. This table says how many that was, and then gives the two readings of its score side by side.

**On what it processed** is the model comparison: quality per document returned, which is the only basis on which runs with different failure rates can be ranked against each other. **Over the whole set** is the pipeline reading: the same quality discounted by coverage, which is what you would actually get from this run over all 167 documents. They differ only where a run failed calls.

The composite is a weighted mean of detection F1, hazard F1, location F1 and date F1 (weights 1.0 / 1.5 / 1.5 / 0.5, carried over from `eval/score_against_gold.py` so the two scorers rank on the same priorities), computed on the corrected matching rules.

| Run | Processed | Coverage | Recall (all docs) | Composite × coverage | Recall (processed) | Composite (processed) | Errored | Absent |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| prompt 5 | 167/167 | 100.0% | 100.0% | 97.0% | 100.0% | 97.0% | 0 | 0 |
| NER baseline | 167/167 | 100.0% | 90.4% | 59.4% | 90.4% | 59.4% | 0 | 0 |

_`Recall (processed)` is over the gold-positive documents the run returned; `Recall (all docs)` is over all 157 gold-positive documents in the set, so the gap between the two columns is exactly what the run's failed calls cost. A run at 100% coverage has identical pairs._

## 2. Event detection

`Recall, all docs` divides by every gold-positive document in the set; `Recall, processed` divides by the ones this run returned. They are equal at full coverage and differ by exactly the run's failure rate otherwise. `Specificity` is over the gold-negative documents returned. Accuracy is shown for continuity but is dominated by the 94% prevalence of this set — balanced accuracy and MCC are the ones to rank on.

| Run | n | Recall, all docs (95% CI) | Recall, processed (95% CI) | Specificity (95% CI) | Balanced acc. | MCC | Accuracy (95% CI) |
|---|---:|---|---|---|---:|---:|---|
| prompt 5 | 167 | 100.0% (97.6%–100.0%, n=157) | 100.0% (97.6%–100.0%, n=157) | 0.0% (0.0%–27.8%, n=10) | 50.0% | – | 94.0% (89.3%–96.7%) |
| NER baseline | 167 | 90.4% (84.8%–94.1%, n=157) | 90.4% (84.8%–94.1%, n=157) | 10.0% (1.8%–40.4%, n=10) | 50.2% | 0.004 | 85.6% (79.5%–90.1%) |

### Confusion matrices

| Run | TP | FP | FN | TN | Precision | F1 |
|---|---:|---:|---:|---:|---:|---:|
| prompt 5 | 157 | 10 | 0 | 0 | 94.0% | 96.9% |
| NER baseline | 142 | 9 | 15 | 1 | 94.0% | 92.2% |

_Precision is reported for continuity only. With 10 gold-negative documents in the set it is pinned near the prevalence for any run that flags most documents, and it separates nothing._

## 3. Field extraction, on documents gold says carry an event

`Recall (all)` divides by every gold item in the set — including those on documents the run never returned — so it is comparable across runs with different coverage. `Recall (processed)` divides only by the documents the run returned, and is the recall the F1 column uses. Micro F1 pools TP/FP/FN over documents; macro F1 averages per-document F1 so a one-location document counts as much as a thirty-location one. The interval is a 95% percentile bootstrap over 2,000 document-level resamples (seed 42); overlapping intervals mean the difference is not resolvable at this sample size.

| Run | Field | Precision | Recall (all) | Recall (processed) | Micro F1 (95% CI) | Macro F1 | TP | FP | FN |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| prompt 5 | Hazard family | 95.3% | 98.8% | 98.8% | 97.0% (95.4%–98.4%) | 97.7% | 244 | 12 | 3 |
| prompt 5 | Locations (exact) | 94.4% | 96.0% | 96.0% | 95.2% (92.8%–97.0%) | 91.2% | 656 | 39 | 27 |
| prompt 5 | Locations (fuzzy ≥90, raw) | 94.5% | 96.2% | 96.2% | 95.4% (93.1%–97.1%) | 91.3% | 657 | 38 | 26 |
| prompt 5 | Locations (fuzzy ≥90, normalised) | 96.0% | 97.7% | 97.7% | 96.8% (95.1%–98.1%) | 94.9% | 667 | 28 | 16 |
| prompt 5 | Dates (exact) | 94.5% | 97.0% | 97.0% | 95.7% (93.6%–97.4%) | 92.2% | 478 | 28 | 15 |
| prompt 5 | Dates (year-set) | 97.5% | 98.8% | 98.8% | 98.1% (96.9%–99.1%) | 96.6% | 421 | 11 | 5 |
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
| prompt 5 | 157 | 73.2% (65.8%–79.6%) | 96.3% | 98.2% | 97.3% (96.1%–98.2%) | 96.2% | 98.2% | 73.2% |
| NER baseline | 157 | 0.6% (0.1%–3.5%) | 36.0% | 56.6% | 44.0% (40.6%–47.2%) | 42.8% | 56.6% | 0.6% |

_Sorted by F1. `Docs` is the gold-positive documents the run returned; the two right-hand columns divide by all 157 instead, so they read as pipeline yield. Precision, macro F1 and the intervals have no all-documents form — a document the run never returned supplies neither a numerator nor a denominator._

## 5. What the matching rule costs

The same run under different matching rules. A gap here is a property of the metric, not of the model — and where it is larger than the gap between two models, the metric is what is being ranked.

| Run | Loc exact | Loc fuzzy raw | Loc fuzzy normalised | Δ norm−exact | Date exact | Date year-set | Δ year−exact |
|---|---:|---:|---:|---:|---:|---:|---:|
| prompt 5 | 95.2% | 95.4% | 96.8% | +1.6 pp | 95.7% | 98.1% | +2.4 pp |
| NER baseline | 20.0% | 29.0% | 30.0% | +10.0 pp | 39.8% | 57.0% | +17.2 pp |

## 6. Paired comparison — exact McNemar on event detection

Paired over the documents **both** runs returned, so a run is never charged for the other's failed calls. `n` is that intersection.

| A | B | n | A only | B only | p |
|---|---|---:|---:|---:|---:|
| prompt 5 | NER baseline | 167 | 15 | 1 | **0.0005** |

_'A only' counts documents A got right and B got wrong. p is two-sided; the concordant pairs carry no information. Bold marks p < 0.05, uncorrected for multiple comparisons — with 1 pairs, expect some by chance._
