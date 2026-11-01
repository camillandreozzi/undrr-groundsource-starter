# Event-level scores — complete records, not pooled attributes

> **Targeted stress test.** The windows were drawn to over-represent multi-event documents (protocol §2). Nothing here is weighted back to the corpus, and no figure in this file estimates archive-wide accuracy.

- Gold: `event_level_gold.csv` sha256 `0b519b58df4d7849…` — 171 gold events (169 verifiable) over 45 windows: 11 single-event, 33 multi-event, 1 with no verifiable event.
- Protocol: `EVENT_LEVEL_PROTOCOL.md` at commit `09f5da1`.
- Matching: evidence-anchored one-to-one (protocol §4); field rules protocol §5. Intervals: 95% cluster bootstrap over windows (2,000 resamples, seed 42).

## 1. Coverage

| System | Windows returned | Errored | Absent | Records on the sample |
|---|---:|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | 45/45 | 0 | 0 | 113 |
| NER baseline | 45/45 | 0 | 0 | 106 |
| Claude Haiku 4.5 | 45/45 | 0 | 0 | 92 |
| Claude Opus 5 | 45/45 | 0 | 0 | 126 |
| Claude Sonnet 5 | 45/45 | 0 | 0 | 133 |
| DeepSeek V3.1 | 45/45 | 0 | 0 | 134 |
| Gemini 2.5 Pro | 0/45 | 45 | 0 | – |
| Llama 4 Maverick | 45/45 | 0 | 0 | 183 |
| Mistral Large | 45/45 | 0 | 0 | 121 |
| GPT-5 (OpenRouter) | 45/45 | 0 | 0 | 123 |
| GPT-5.4 | 45/45 | 0 | 0 | 112 |
| GPT-5 mini | 45/45 | 0 | 0 | 130 |
| Qwen3 235B | 0/45 | 45 | 0 | – |
| Grok 4.6 | 45/45 | 0 | 0 | 135 |

_A system is scored only on the windows it returned (error policy `exclude`, as in `score_against_human.py`). Systems with none returned are not scored._

## 2. Headline

`Complete-record correctness` = records matched to a gold event **and** carrying its hazard, year and locations, over **all** records — a record with no gold event stays in the denominator. `Complete-record recall` = verifiable gold events recovered by such a record. `Pooling gap` = document-level pooled F1 minus event-level attribute F1 on the same windows and value rules: what pooling hid.

| System | Records | Gold events | Detection P | Detection R | Complete-record correctness (95% CI) | Wilson | Complete-record recall | Event-level attribute F1 | Pooled document F1 | Pooling gap |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | 113 | 169 | 81.4% | 53.8% | 58.4% (48.2%–68.9%) | 49.2%–67.1% | 38.5% | 55.6% | 66.7% | +11.1 pp |
| NER baseline | 106 | 169 | 69.8% | 43.8% | 1.9% (0.0%–5.0%) | 0.5%–6.6% | 1.2% | 28.9% | 50.6% | +21.6 pp |
| Claude Haiku 4.5 | 92 | 169 | 79.3% | 42.6% | 56.5% (41.1%–75.3%) | 46.3%–66.2% | 30.2% | 47.5% | 58.4% | +10.9 pp |
| Claude Opus 5 | 126 | 169 | 81.7% | 59.8% | 56.3% (42.9%–70.0%) | 47.6%–64.7% | 41.4% | 61.0% | 69.2% | +8.2 pp |
| Claude Sonnet 5 | 133 | 169 | 75.9% | 59.2% | 54.9% (39.5%–72.6%) | 46.4%–63.1% | 42.6% | 57.6% | 67.8% | +10.2 pp |
| DeepSeek V3.1 | 134 | 169 | 74.6% | 58.6% | 59.7% (46.6%–73.9%) | 51.2%–67.6% | 46.7% | 56.8% | 67.7% | +10.8 pp |
| Llama 4 Maverick | 183 | 169 | 77.0% | 82.8% | 59.6% (49.4%–69.8%) | 52.3%–66.4% | 64.5% | 70.7% | 77.8% | +7.1 pp |
| Mistral Large | 121 | 169 | 79.3% | 55.6% | 49.6% (40.0%–56.3%) | 40.8%–58.4% | 34.9% | 54.5% | 59.9% | +5.4 pp |
| GPT-5 (OpenRouter) | 123 | 169 | 76.4% | 55.0% | 52.0% (39.2%–67.3%) | 43.3%–60.7% | 37.3% | 54.2% | 67.0% | +12.8 pp |
| GPT-5.4 | 112 | 169 | 77.7% | 50.9% | 51.8% (39.0%–66.1%) | 42.6%–60.8% | 33.7% | 50.5% | 62.6% | +12.1 pp |
| GPT-5 mini | 130 | 169 | 83.1% | 63.3% | 60.8% (47.5%–71.3%) | 52.2%–68.7% | 46.2% | 61.7% | 69.2% | +7.4 pp |
| Grok 4.6 | 135 | 169 | 78.5% | 62.1% | 55.6% (43.8%–68.5%) | 47.1%–63.7% | 43.8% | 59.2% | 70.5% | +11.3 pp |

## 3. Single-event vs multi-event windows

Windows are classed by the gold's own count of verifiable events, not by the sampling stratum.

| System | Class | Windows | Records | Gold events | Detection P | Detection R | Complete-record correctness (95% CI) | Event-level attribute F1 | Pooled F1 | Gap |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | single-event | 11 | 19 | 11 | 63.2% | 100.0% | 36.8% (15.8%–64.3%) | 59.1% | 71.2% | +12.0 pp |
| prompt 5 (gpt-5, Azure) | multi-event | 33 | 93 | 158 | 86.0% | 50.6% | 63.4% (52.3%–75.9%) | 55.3% | 66.3% | +10.9 pp |
| NER baseline | single-event | 11 | 14 | 11 | 64.3% | 81.8% | 7.1% (0.0%–22.2%) | 39.3% | 42.5% | +3.2 pp |
| NER baseline | multi-event | 33 | 91 | 158 | 71.4% | 41.1% | 1.1% (0.0%–3.9%) | 27.8% | 52.3% | +24.5 pp |
| Claude Haiku 4.5 | single-event | 11 | 9 | 11 | 88.9% | 63.6% | 55.6% (16.7%–87.5%) | 58.8% | 57.8% | -1.0 pp |
| Claude Haiku 4.5 | multi-event | 33 | 82 | 158 | 79.3% | 41.1% | 57.3% (40.7%–78.1%) | 46.6% | 58.8% | +12.2 pp |
| Claude Opus 5 | single-event | 11 | 18 | 11 | 55.6% | 81.8% | 27.8% (5.9%–71.4%) | 58.5% | 67.3% | +8.8 pp |
| Claude Opus 5 | multi-event | 33 | 107 | 158 | 86.9% | 58.2% | 61.7% (47.3%–74.5%) | 61.6% | 69.9% | +8.3 pp |
| Claude Sonnet 5 | single-event | 11 | 16 | 11 | 56.2% | 72.7% | 37.5% (14.3%–87.5%) | 61.8% | 67.3% | +5.5 pp |
| Claude Sonnet 5 | multi-event | 33 | 116 | 158 | 79.3% | 58.2% | 57.8% (41.0%–77.1%) | 57.4% | 68.2% | +10.8 pp |
| DeepSeek V3.1 | single-event | 11 | 15 | 11 | 73.3% | 90.9% | 46.7% (22.2%–71.4%) | 69.2% | 71.3% | +2.1 pp |
| DeepSeek V3.1 | multi-event | 33 | 118 | 158 | 75.4% | 56.3% | 61.9% (47.0%–78.0%) | 55.7% | 67.4% | +11.7 pp |
| Llama 4 Maverick | single-event | 11 | 20 | 11 | 55.0% | 100.0% | 35.0% (12.5%–83.3%) | 68.3% | 75.7% | +7.4 pp |
| Llama 4 Maverick | multi-event | 33 | 162 | 158 | 80.2% | 81.6% | 63.0% (52.9%–72.2%) | 71.2% | 78.6% | +7.4 pp |
| Mistral Large | single-event | 11 | 12 | 11 | 83.3% | 81.8% | 50.0% (25.0%–77.8%) | 70.9% | 73.1% | +2.2 pp |
| Mistral Large | multi-event | 33 | 108 | 158 | 79.6% | 53.8% | 50.0% (39.4%–57.2%) | 53.0% | 58.3% | +5.3 pp |
| GPT-5 (OpenRouter) | single-event | 11 | 22 | 11 | 54.5% | 100.0% | 31.8% (14.8%–61.5%) | 55.1% | 67.3% | +12.2 pp |
| GPT-5 (OpenRouter) | multi-event | 33 | 100 | 158 | 82.0% | 51.9% | 57.0% (42.3%–73.0%) | 54.4% | 67.4% | +13.0 pp |
| GPT-5.4 | single-event | 11 | 21 | 11 | 52.4% | 90.9% | 28.6% (11.1%–61.1%) | 50.8% | 62.4% | +11.6 pp |
| GPT-5.4 | multi-event | 33 | 90 | 158 | 84.4% | 48.1% | 57.8% (44.0%–73.2%) | 50.7% | 63.0% | +12.4 pp |
| GPT-5 mini | single-event | 11 | 21 | 11 | 57.1% | 100.0% | 33.3% (10.7%–75.0%) | 59.4% | 67.3% | +7.9 pp |
| GPT-5 mini | multi-event | 33 | 108 | 158 | 88.9% | 60.8% | 66.7% (55.9%–75.8%) | 62.4% | 70.0% | +7.6 pp |
| Grok 4.6 | single-event | 11 | 19 | 11 | 57.9% | 90.9% | 42.1% (20.0%–88.9%) | 60.2% | 67.9% | +7.7 pp |
| Grok 4.6 | multi-event | 33 | 115 | 158 | 82.6% | 60.1% | 58.3% (45.8%–73.2%) | 59.3% | 71.2% | +11.9 pp |

## 4. Field agreement on matched events

Of the records matched to a gold event, how many carry that event's value. `Association` is the primary rule (protocol §5); `exact` additionally requires every gold location, the full year span and the exact hazard labels.

| System | Matched | Hazard | Year | Location | All three | Exact hazard | Exact year | Exact location | Exact all |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | 92 | 92.4% | 97.8% | 78.3% | 71.7% | 88.0% | 96.7% | 62.0% | 56.5% |
| NER baseline | 74 | 45.9% | 27.0% | 6.8% | 2.7% | 39.2% | 27.0% | 2.7% | 1.4% |
| Claude Haiku 4.5 | 73 | 93.2% | 98.6% | 75.3% | 71.2% | 90.4% | 97.3% | 58.9% | 54.8% |
| Claude Opus 5 | 103 | 91.3% | 98.1% | 73.8% | 68.9% | 90.3% | 97.1% | 66.0% | 62.1% |
| Claude Sonnet 5 | 101 | 96.0% | 99.0% | 73.3% | 72.3% | 93.1% | 97.0% | 63.4% | 61.4% |
| DeepSeek V3.1 | 100 | 95.0% | 99.0% | 81.0% | 80.0% | 92.0% | 99.0% | 68.0% | 66.0% |
| Llama 4 Maverick | 141 | 93.6% | 95.7% | 83.7% | 77.3% | 91.5% | 92.9% | 73.0% | 63.8% |
| Mistral Large | 96 | 88.5% | 95.8% | 68.8% | 62.5% | 83.3% | 95.8% | 60.4% | 54.2% |
| GPT-5 (OpenRouter) | 94 | 89.4% | 96.8% | 73.4% | 68.1% | 86.2% | 95.7% | 60.6% | 57.4% |
| GPT-5.4 | 87 | 92.0% | 90.8% | 72.4% | 66.7% | 87.4% | 89.7% | 57.5% | 51.7% |
| GPT-5 mini | 108 | 93.5% | 96.3% | 78.7% | 73.1% | 90.7% | 95.4% | 68.5% | 63.9% |
| Grok 4.6 | 106 | 86.8% | 96.2% | 81.1% | 70.8% | 85.8% | 95.3% | 67.0% | 61.3% |

## 5. Event-level attribute P / R / F1, per field

| System | Field | Precision | Recall | F1 (95% CI) | Pooled F1 | Gap |
|---|---|---:|---:|---|---:|---:|
| prompt 5 (gpt-5, Azure) | hazard | 77.0% | 53.1% | 62.9% (56.0%–71.7%) | 82.4% | +19.5 pp |
| prompt 5 (gpt-5, Azure) | year | 80.8% | 53.3% | 64.2% (55.9%–74.2%) | 78.2% | +14.0 pp |
| prompt 5 (gpt-5, Azure) | location | 58.5% | 36.4% | 44.8% (36.8%–55.4%) | 54.4% | +9.5 pp |
| NER baseline | hazard | 34.9% | 43.2% | 38.6% (34.7%–43.5%) | 74.9% | +36.3 pp |
| NER baseline | year | 33.1% | 30.9% | 32.0% (25.5%–38.3%) | 52.8% | +20.8 pp |
| NER baseline | location | 17.4% | 33.6% | 22.9% (19.3%–26.6%) | 42.2% | +19.3 pp |
| Claude Haiku 4.5 | hazard | 75.8% | 42.4% | 54.3% (44.3%–65.3%) | 71.2% | +16.9 pp |
| Claude Haiku 4.5 | year | 77.9% | 40.7% | 53.4% (42.3%–65.3%) | 67.4% | +14.0 pp |
| Claude Haiku 4.5 | location | 51.8% | 32.0% | 39.6% (31.6%–49.7%) | 49.5% | +9.9 pp |
| Claude Opus 5 | hazard | 77.1% | 60.7% | 67.9% (60.2%–76.4%) | 83.1% | +15.2 pp |
| Claude Opus 5 | year | 80.3% | 58.2% | 67.5% (59.2%–76.2%) | 79.8% | +12.3 pp |
| Claude Opus 5 | location | 60.5% | 46.0% | 52.3% (43.7%–62.5%) | 59.0% | +6.7 pp |
| Claude Sonnet 5 | hazard | 73.6% | 58.2% | 65.0% (57.5%–73.2%) | 80.5% | +15.5 pp |
| Claude Sonnet 5 | year | 75.7% | 58.2% | 65.8% (57.4%–75.1%) | 78.8% | +13.0 pp |
| Claude Sonnet 5 | location | 53.1% | 43.3% | 47.7% (38.1%–59.3%) | 58.0% | +10.3 pp |
| DeepSeek V3.1 | hazard | 71.8% | 57.6% | 63.9% (57.3%–72.2%) | 81.2% | +17.3 pp |
| DeepSeek V3.1 | year | 74.5% | 57.7% | 65.0% (57.9%–73.1%) | 77.7% | +12.7 pp |
| DeepSeek V3.1 | location | 53.5% | 41.5% | 46.7% (38.8%–57.4%) | 57.7% | +11.0 pp |
| Llama 4 Maverick | hazard | 73.2% | 80.2% | 76.5% (68.2%–84.0%) | 86.3% | +9.8 pp |
| Llama 4 Maverick | year | 78.7% | 77.3% | 78.0% (69.0%–86.0%) | 82.6% | +4.6 pp |
| Llama 4 Maverick | location | 62.8% | 60.7% | 61.7% (51.5%–71.4%) | 72.3% | +10.6 pp |
| Mistral Large | hazard | 70.4% | 53.4% | 60.7% (48.2%–70.9%) | 75.0% | +14.3 pp |
| Mistral Large | year | 76.0% | 52.2% | 61.9% (47.2%–73.5%) | 65.6% | +3.7 pp |
| Mistral Large | location | 50.2% | 42.8% | 46.2% (34.9%–56.9%) | 52.3% | +6.1 pp |
| GPT-5 (OpenRouter) | hazard | 69.4% | 52.5% | 59.8% (51.5%–67.8%) | 82.4% | +22.6 pp |
| GPT-5 (OpenRouter) | year | 76.0% | 53.8% | 63.0% (52.9%–72.8%) | 78.8% | +15.8 pp |
| GPT-5 (OpenRouter) | location | 53.5% | 38.5% | 44.8% (37.7%–54.2%) | 55.1% | +10.3 pp |
| GPT-5.4 | hazard | 73.3% | 49.7% | 59.3% (50.3%–69.4%) | 81.0% | +21.7 pp |
| GPT-5.4 | year | 73.2% | 45.1% | 55.8% (47.3%–66.0%) | 72.8% | +17.0 pp |
| GPT-5.4 | location | 51.6% | 34.5% | 41.4% (31.8%–53.9%) | 50.5% | +9.1 pp |
| GPT-5 mini | hazard | 78.8% | 61.0% | 68.8% (58.6%–79.0%) | 83.4% | +14.6 pp |
| GPT-5 mini | year | 81.2% | 59.3% | 68.6% (58.0%–79.3%) | 78.8% | +10.2 pp |
| GPT-5 mini | location | 63.4% | 44.7% | 52.5% (42.7%–62.2%) | 59.4% | +6.9 pp |
| Grok 4.6 | hazard | 69.9% | 60.5% | 64.8% (57.3%–73.1%) | 82.8% | +18.0 pp |
| Grok 4.6 | year | 76.3% | 58.2% | 66.0% (57.0%–74.6%) | 77.3% | +11.3 pp |
| Grok 4.6 | location | 54.2% | 49.1% | 51.5% (43.5%–61.6%) | 63.1% | +11.6 pp |

## 6. Misassociation — wrong values that belong to another event

Wrong values in matched records, split into those that are correct for a *different* gold event in the same window (the attribute swap a pooled metric credits) and those that belong to no event in the window.

| System | Field | Wrong values | Another event's | Unsupported | Share misassociated | Multi-event windows: wrong | another event's |
|---|---|---:|---:|---:|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | hazard | 6 | 2 | 4 | 33.3% | 5 | 2 |
| prompt 5 (gpt-5, Azure) | year | 1 | 0 | 1 | 0.0% | 0 | 0 |
| prompt 5 (gpt-5, Azure) | location | 25 | 4 | 21 | 16.0% | 18 | 4 |
| NER baseline | hazard | 86 | 57 | 29 | 66.3% | 85 | 57 |
| NER baseline | year | 68 | 27 | 41 | 39.7% | 61 | 27 |
| NER baseline | location | 302 | 113 | 189 | 37.4% | 277 | 113 |
| Claude Haiku 4.5 | hazard | 5 | 1 | 4 | 20.0% | 4 | 1 |
| Claude Haiku 4.5 | year | 1 | 0 | 1 | 0.0% | 1 | 0 |
| Claude Haiku 4.5 | location | 29 | 6 | 23 | 20.7% | 24 | 6 |
| Claude Opus 5 | hazard | 8 | 3 | 5 | 37.5% | 5 | 3 |
| Claude Opus 5 | year | 2 | 2 | 0 | 100.0% | 2 | 2 |
| Claude Opus 5 | location | 37 | 4 | 33 | 10.8% | 30 | 4 |
| Claude Sonnet 5 | hazard | 3 | 2 | 1 | 66.7% | 3 | 2 |
| Claude Sonnet 5 | year | 1 | 1 | 0 | 100.0% | 1 | 1 |
| Claude Sonnet 5 | location | 41 | 8 | 33 | 19.5% | 36 | 8 |
| DeepSeek V3.1 | hazard | 4 | 2 | 2 | 50.0% | 3 | 2 |
| DeepSeek V3.1 | year | 1 | 1 | 0 | 100.0% | 1 | 1 |
| DeepSeek V3.1 | location | 29 | 4 | 25 | 13.8% | 22 | 4 |
| Llama 4 Maverick | hazard | 9 | 3 | 6 | 33.3% | 8 | 3 |
| Llama 4 Maverick | year | 6 | 6 | 0 | 100.0% | 6 | 6 |
| Llama 4 Maverick | location | 29 | 15 | 14 | 51.7% | 26 | 15 |
| Mistral Large | hazard | 11 | 7 | 4 | 63.6% | 10 | 7 |
| Mistral Large | year | 5 | 3 | 2 | 60.0% | 5 | 3 |
| Mistral Large | location | 56 | 13 | 43 | 23.2% | 47 | 13 |
| GPT-5 (OpenRouter) | hazard | 9 | 4 | 5 | 44.4% | 8 | 4 |
| GPT-5 (OpenRouter) | year | 2 | 1 | 1 | 50.0% | 2 | 1 |
| GPT-5 (OpenRouter) | location | 33 | 5 | 28 | 15.2% | 25 | 5 |
| GPT-5.4 | hazard | 6 | 1 | 5 | 16.7% | 5 | 1 |
| GPT-5.4 | year | 5 | 3 | 2 | 60.0% | 4 | 3 |
| GPT-5.4 | location | 32 | 7 | 25 | 21.9% | 23 | 7 |
| GPT-5 mini | hazard | 5 | 3 | 2 | 60.0% | 5 | 3 |
| GPT-5 mini | year | 1 | 1 | 0 | 100.0% | 1 | 1 |
| GPT-5 mini | location | 31 | 8 | 23 | 25.8% | 26 | 8 |
| Grok 4.6 | hazard | 15 | 8 | 7 | 53.3% | 14 | 8 |
| Grok 4.6 | year | 4 | 2 | 2 | 50.0% | 3 | 2 |
| Grok 4.6 | location | 28 | 5 | 23 | 17.9% | 21 | 5 |

## 7. Matcher diagnostics

Links by tier (A anchored on located evidence, B paraphrase, C year + location fallback). False positives: `split` — the record's identity points at a gold event another record took; `no event` — nothing in the gold it could be. False negatives: `merged` — a record matched elsewhere also carries this event's evidence; `missed` — no record does.

| System | Tier A | Tier B | Tier C | FP: split | FP: no event | FN: merged | FN: missed |
|---|---:|---:|---:|---:|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | 79 | 6 | 7 | 9 | 12 | 21 | 57 |
| NER baseline | 48 | 0 | 26 | 9 | 23 | 26 | 69 |
| Claude Haiku 4.5 | 44 | 25 | 4 | 10 | 9 | 13 | 84 |
| Claude Opus 5 | 92 | 7 | 4 | 9 | 14 | 22 | 46 |
| Claude Sonnet 5 | 96 | 2 | 3 | 13 | 19 | 19 | 50 |
| DeepSeek V3.1 | 96 | 1 | 3 | 17 | 17 | 23 | 47 |
| Llama 4 Maverick | 126 | 4 | 11 | 14 | 28 | 13 | 16 |
| Mistral Large | 90 | 1 | 5 | 9 | 16 | 9 | 66 |
| GPT-5 (OpenRouter) | 78 | 11 | 5 | 9 | 20 | 20 | 56 |
| GPT-5.4 | 54 | 30 | 3 | 8 | 17 | 32 | 51 |
| GPT-5 mini | 97 | 7 | 4 | 8 | 14 | 21 | 41 |
| Grok 4.6 | 67 | 37 | 2 | 11 | 18 | 30 | 34 |

## 8. What the matching rule costs

The same records under a field-maximising alignment that ignores evidence and pairs records with gold events to maximise complete records. It is the most generous one-to-one reading possible — an upper bound, never the result.

| System | Complete-record correctness, evidence-anchored | Field-maximising bound | Δ |
|---|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | 58.4% | 61.1% | +2.7 pp |
| NER baseline | 1.9% | 2.8% | +0.9 pp |
| Claude Haiku 4.5 | 56.5% | 60.9% | +4.3 pp |
| Claude Opus 5 | 56.3% | 58.7% | +2.4 pp |
| Claude Sonnet 5 | 54.9% | 58.6% | +3.8 pp |
| DeepSeek V3.1 | 59.7% | 63.4% | +3.7 pp |
| Llama 4 Maverick | 59.6% | 63.4% | +3.8 pp |
| Mistral Large | 49.6% | 56.2% | +6.6 pp |
| GPT-5 (OpenRouter) | 52.0% | 55.3% | +3.3 pp |
| GPT-5.4 | 51.8% | 58.0% | +6.2 pp |
| GPT-5 mini | 60.8% | 63.1% | +2.3 pp |
| Grok 4.6 | 55.6% | 61.5% | +5.9 pp |

## 9. Paired difference against prompt 5 (gpt-5, Azure)

Complete-record correctness, system minus baseline, on the windows both returned; 95% paired cluster bootstrap.

| System | Windows | All windows | Single-event | Multi-event |
|---|---:|---|---|---|
| NER baseline | 45 | -56.5 pp (-67.4 to -44.9) | -29.7 pp (-61.5 to -2.9) | -62.3 pp (-74.4 to -51.4) |
| Claude Haiku 4.5 | 45 | -1.9 pp (-12.5 to +11.1) | +18.7 pp (-8.1 to +39.4) | -6.1 pp (-16.7 to +8.2) |
| Claude Opus 5 | 45 | -2.1 pp (-10.2 to +6.5) | -9.1 pp (-21.0 to +11.0) | -1.8 pp (-11.3 to +7.1) |
| Claude Sonnet 5 | 45 | -3.5 pp (-13.8 to +9.0) | +0.7 pp (-12.5 to +34.9) | -5.7 pp (-17.2 to +7.7) |
| DeepSeek V3.1 | 45 | +1.3 pp (-7.4 to +11.5) | +9.8 pp (+0.0 to +17.4) | -1.6 pp (-11.4 to +9.2) |
| Llama 4 Maverick | 45 | +1.2 pp (-8.6 to +10.9) | -1.8 pp (-21.2 to +36.9) | -0.5 pp (-11.5 to +10.0) |
| Mistral Large | 45 | -8.8 pp (-20.3 to +0.7) | +13.2 pp (-11.9 to +42.5) | -13.4 pp (-25.9 to -2.5) |
| GPT-5 (OpenRouter) | 45 | -6.4 pp (-13.2 to +1.1) | -5.0 pp (-11.3 to +5.6) | -6.4 pp (-14.0 to +2.4) |
| GPT-5.4 | 45 | -6.6 pp (-14.6 to +2.1) | -8.3 pp (-17.6 to +3.3) | -5.7 pp (-15.8 to +3.9) |
| GPT-5 mini | 45 | +2.4 pp (-6.5 to +9.5) | -3.5 pp (-16.7 to +21.9) | +3.2 pp (-4.7 to +10.1) |
| Grok 4.6 | 45 | -2.9 pp (-10.7 to +5.4) | +5.3 pp (-6.7 to +35.6) | -5.2 pp (-13.7 to +3.9) |

## 10. By sampling stratum

Strata are the pre-annotation proxies the sample was drawn on (protocol §2).

| System | Stratum | Windows | Records | Detection P | Detection R | Complete-record correctness |
|---|---|---:|---:|---:|---:|---|
| prompt 5 (gpt-5, Azure) | multi_hazard_multi_year | 10 | 47 | 74.5% | 59.3% | 51.1% (36.2%–68.1%) |
| prompt 5 (gpt-5, Azure) | multi_hazard_same_year | 10 | 22 | 81.8% | 31.6% | 45.5% (21.0%–65.0%) |
| prompt 5 (gpt-5, Azure) | same_hazard_multi_year | 10 | 26 | 88.5% | 81.5% | 76.9% (54.5%–95.0%) |
| prompt 5 (gpt-5, Azure) | single | 15 | 18 | 88.9% | 61.5% | 66.7% (42.8%–86.7%) |
| NER baseline | multi_hazard_multi_year | 10 | 28 | 75.0% | 35.6% | 0.0% (0.0%–0.0%) |
| NER baseline | multi_hazard_same_year | 10 | 29 | 82.8% | 42.1% | 3.4% (0.0%–15.8%) |
| NER baseline | same_hazard_multi_year | 10 | 20 | 60.0% | 44.4% | 0.0% (0.0%–0.0%) |
| NER baseline | single | 15 | 29 | 58.6% | 65.4% | 3.4% (0.0%–11.4%) |
| Claude Haiku 4.5 | multi_hazard_multi_year | 10 | 42 | 66.7% | 47.5% | 42.9% (25.0%–77.8%) |
| Claude Haiku 4.5 | multi_hazard_same_year | 10 | 16 | 93.8% | 26.3% | 62.5% (37.5%–87.5%) |
| Claude Haiku 4.5 | same_hazard_multi_year | 10 | 15 | 86.7% | 44.4% | 73.3% (38.5%–100.0%) |
| Claude Haiku 4.5 | single | 15 | 19 | 89.5% | 65.4% | 68.4% (46.7%–85.7%) |
| Claude Opus 5 | multi_hazard_multi_year | 10 | 60 | 73.3% | 74.6% | 46.7% (23.9%–72.0%) |
| Claude Opus 5 | multi_hazard_same_year | 10 | 23 | 91.3% | 35.1% | 52.2% (33.3%–64.0%) |
| Claude Opus 5 | same_hazard_multi_year | 10 | 24 | 87.5% | 74.1% | 75.0% (54.2%–93.8%) |
| Claude Opus 5 | single | 15 | 19 | 89.5% | 65.4% | 68.4% (42.9%–85.0%) |
| Claude Sonnet 5 | multi_hazard_multi_year | 10 | 70 | 62.9% | 74.6% | 45.7% (25.5%–75.9%) |
| Claude Sonnet 5 | multi_hazard_same_year | 10 | 24 | 87.5% | 36.8% | 50.0% (28.6%–68.4%) |
| Claude Sonnet 5 | same_hazard_multi_year | 10 | 22 | 90.9% | 70.4% | 81.8% (56.2%–100.0%) |
| Claude Sonnet 5 | single | 15 | 17 | 94.1% | 61.5% | 64.7% (36.4%–82.4%) |
| DeepSeek V3.1 | multi_hazard_multi_year | 10 | 64 | 67.2% | 72.9% | 57.8% (38.5%–85.4%) |
| DeepSeek V3.1 | multi_hazard_same_year | 10 | 27 | 81.5% | 38.6% | 55.6% (28.0%–78.9%) |
| DeepSeek V3.1 | same_hazard_multi_year | 10 | 25 | 80.0% | 70.4% | 64.0% (39.1%–85.2%) |
| DeepSeek V3.1 | single | 15 | 18 | 83.3% | 57.7% | 66.7% (47.1%–84.2%) |
| Llama 4 Maverick | multi_hazard_multi_year | 10 | 79 | 64.6% | 86.4% | 46.8% (29.3%–61.6%) |
| Llama 4 Maverick | multi_hazard_same_year | 10 | 46 | 91.3% | 71.9% | 73.9% (50.0%–85.4%) |
| Llama 4 Maverick | same_hazard_multi_year | 10 | 28 | 82.1% | 85.2% | 57.1% (37.9%–76.0%) |
| Llama 4 Maverick | single | 15 | 30 | 83.3% | 96.2% | 73.3% (61.5%–88.0%) |
| Mistral Large | multi_hazard_multi_year | 10 | 38 | 68.4% | 44.1% | 50.0% (31.0%–63.8%) |
| Mistral Large | multi_hazard_same_year | 10 | 47 | 85.1% | 68.4% | 51.1% (27.8%–58.9%) |
| Mistral Large | same_hazard_multi_year | 10 | 14 | 92.9% | 44.4% | 42.9% (9.1%–59.1%) |
| Mistral Large | single | 15 | 22 | 77.3% | 65.4% | 50.0% (27.3%–70.0%) |
| GPT-5 (OpenRouter) | multi_hazard_multi_year | 10 | 58 | 70.7% | 69.5% | 50.0% (29.5%–79.7%) |
| GPT-5 (OpenRouter) | multi_hazard_same_year | 10 | 23 | 78.3% | 31.6% | 34.8% (14.3%–51.9%) |
| GPT-5 (OpenRouter) | same_hazard_multi_year | 10 | 23 | 82.6% | 66.7% | 69.6% (40.9%–92.3%) |
| GPT-5 (OpenRouter) | single | 15 | 19 | 84.2% | 61.5% | 57.9% (38.9%–76.5%) |
| GPT-5.4 | multi_hazard_multi_year | 10 | 52 | 71.2% | 62.7% | 48.1% (27.8%–71.7%) |
| GPT-5.4 | multi_hazard_same_year | 10 | 21 | 90.5% | 33.3% | 47.6% (25.0%–76.5%) |
| GPT-5.4 | same_hazard_multi_year | 10 | 19 | 78.9% | 51.9% | 68.4% (35.3%–92.9%) |
| GPT-5.4 | single | 15 | 20 | 80.0% | 61.5% | 50.0% (27.8%–73.9%) |
| GPT-5 mini | multi_hazard_multi_year | 10 | 60 | 78.3% | 79.7% | 55.0% (31.0%–72.5%) |
| GPT-5 mini | multi_hazard_same_year | 10 | 28 | 82.1% | 40.4% | 60.7% (30.0%–76.3%) |
| GPT-5 mini | same_hazard_multi_year | 10 | 21 | 90.5% | 66.7% | 76.2% (47.4%–95.5%) |
| GPT-5 mini | single | 15 | 21 | 90.5% | 73.1% | 61.9% (35.3%–82.1%) |
| Grok 4.6 | multi_hazard_multi_year | 10 | 67 | 68.7% | 78.0% | 52.2% (34.3%–75.5%) |
| Grok 4.6 | multi_hazard_same_year | 10 | 25 | 92.0% | 40.4% | 40.0% (21.4%–68.4%) |
| Grok 4.6 | same_hazard_multi_year | 10 | 22 | 86.4% | 66.7% | 68.2% (41.7%–90.9%) |
| Grok 4.6 | single | 15 | 21 | 85.7% | 69.2% | 71.4% (53.3%–86.7%) |

## 11. Link audit

A seeded sample of the matcher's decisions, judged by the annotator after scoring. It checks the matcher; it does not change any figure above.

| Decision | Judged | Annotator agrees | Pending |
|---|---:|---|---:|
| link_AB | 0 | – | 25 |
| link_C | 0 | – | 77 |
| fp | 0 | – | 15 |

