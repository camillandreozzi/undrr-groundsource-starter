# Event-level scores — complete records, not pooled attributes

> **Targeted stress test.** The windows were drawn to over-represent multi-event documents (protocol §2). Nothing here is weighted back to the corpus, and no figure in this file estimates archive-wide accuracy.

- Gold: `event_level_gold.csv` sha256 `5c66d9f9305e0be6…` — 172 gold events (170 verifiable) over 45 windows: 10 single-event, 34 multi-event, 1 with no verifiable event.
- Protocol: `EVENT_LEVEL_PROTOCOL.md` at commit `09f5da1` **with uncommitted edits since**.
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
| prompt 5 (gpt-5, Azure) | 113 | 170 | 82.3% | 54.1% | 60.2% (50.0%–70.8%) | 51.0%–68.7% | 39.4% | 56.4% | 67.1% | +10.7 pp |
| NER baseline | 106 | 170 | 69.8% | 43.5% | 1.9% (0.0%–5.0%) | 0.5%–6.6% | 1.2% | 28.9% | 50.7% | +21.8 pp |
| Claude Haiku 4.5 | 92 | 170 | 79.3% | 42.4% | 56.5% (41.1%–75.3%) | 46.3%–66.2% | 30.0% | 47.4% | 58.3% | +11.0 pp |
| Claude Opus 5 | 126 | 170 | 82.5% | 60.0% | 57.9% (44.2%–71.8%) | 49.2%–66.2% | 42.4% | 61.6% | 69.6% | +8.1 pp |
| Claude Sonnet 5 | 133 | 170 | 75.9% | 58.8% | 54.9% (39.5%–72.6%) | 46.4%–63.1% | 42.4% | 57.5% | 67.7% | +10.2 pp |
| DeepSeek V3.1 | 134 | 170 | 75.4% | 58.8% | 61.2% (47.8%–75.7%) | 52.7%–69.0% | 47.6% | 57.4% | 68.1% | +10.7 pp |
| Llama 4 Maverick | 183 | 170 | 77.6% | 82.9% | 60.7% (50.6%–70.6%) | 53.4%–67.4% | 65.3% | 71.1% | 78.2% | +7.0 pp |
| Mistral Large | 121 | 170 | 80.2% | 55.9% | 49.6% (40.0%–56.3%) | 40.8%–58.4% | 34.7% | 55.0% | 60.3% | +5.2 pp |
| GPT-5 (OpenRouter) | 123 | 170 | 77.2% | 55.3% | 53.7% (40.6%–68.9%) | 44.9%–62.2% | 38.2% | 54.8% | 67.4% | +12.6 pp |
| GPT-5.4 | 112 | 170 | 78.6% | 51.2% | 53.6% (40.4%–68.2%) | 44.4%–62.5% | 34.7% | 51.3% | 63.0% | +11.8 pp |
| GPT-5 mini | 130 | 170 | 83.8% | 63.5% | 61.5% (48.5%–72.5%) | 53.0%–69.5% | 46.5% | 62.1% | 69.4% | +7.2 pp |
| Grok 4.6 | 135 | 170 | 79.3% | 62.4% | 57.0% (45.5%–70.2%) | 48.6%–65.1% | 44.7% | 59.9% | 70.9% | +11.0 pp |

## 3. Single-event vs multi-event windows

Windows are classed by the gold's own count of verifiable events, not by the sampling stratum.

| System | Class | Windows | Records | Gold events | Detection P | Detection R | Complete-record correctness (95% CI) | Event-level attribute F1 | Pooled F1 | Gap |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | single-event | 10 | 17 | 10 | 64.7% | 100.0% | 41.2% (20.0%–71.4%) | 62.3% | 72.2% | +9.9 pp |
| prompt 5 (gpt-5, Azure) | multi-event | 34 | 95 | 160 | 86.3% | 51.2% | 64.2% (54.1%–76.6%) | 55.9% | 66.7% | +10.8 pp |
| NER baseline | single-event | 10 | 13 | 10 | 61.5% | 80.0% | 7.7% (0.0%–25.0%) | 38.6% | 41.8% | +3.3 pp |
| NER baseline | multi-event | 34 | 92 | 160 | 71.7% | 41.2% | 1.1% (0.0%–4.0%) | 27.8% | 52.5% | +24.6 pp |
| Claude Haiku 4.5 | single-event | 10 | 9 | 10 | 88.9% | 70.0% | 55.6% (20.0%–87.5%) | 61.0% | 60.0% | -1.0 pp |
| Claude Haiku 4.5 | multi-event | 34 | 82 | 160 | 79.3% | 40.6% | 57.3% (40.3%–78.4%) | 46.3% | 58.4% | +12.1 pp |
| Claude Opus 5 | single-event | 10 | 16 | 10 | 56.2% | 80.0% | 31.2% (5.9%–77.8%) | 59.6% | 68.0% | +8.4 pp |
| Claude Opus 5 | multi-event | 34 | 109 | 160 | 87.2% | 58.8% | 62.4% (48.1%–75.5%) | 62.0% | 70.2% | +8.2 pp |
| Claude Sonnet 5 | single-event | 10 | 16 | 10 | 56.2% | 80.0% | 37.5% (13.9%–87.5%) | 63.6% | 69.5% | +5.9 pp |
| Claude Sonnet 5 | multi-event | 34 | 116 | 160 | 79.3% | 57.5% | 57.8% (40.1%–76.0%) | 57.0% | 67.8% | +10.8 pp |
| DeepSeek V3.1 | single-event | 10 | 13 | 10 | 76.9% | 90.0% | 53.8% (28.6%–80.0%) | 71.4% | 72.3% | +0.9 pp |
| DeepSeek V3.1 | multi-event | 34 | 120 | 160 | 75.8% | 56.9% | 62.5% (47.2%–78.5%) | 56.2% | 67.8% | +11.6 pp |
| Llama 4 Maverick | single-event | 10 | 17 | 10 | 58.8% | 100.0% | 41.2% (14.7%–90.0%) | 71.4% | 77.7% | +6.2 pp |
| Llama 4 Maverick | multi-event | 34 | 165 | 160 | 80.0% | 81.9% | 63.0% (53.3%–72.4%) | 71.4% | 78.7% | +7.3 pp |
| Mistral Large | single-event | 10 | 10 | 10 | 90.0% | 80.0% | 60.0% (33.3%–87.5%) | 74.7% | 75.0% | +0.3 pp |
| Mistral Large | multi-event | 34 | 110 | 160 | 80.0% | 54.4% | 49.1% (38.0%–56.2%) | 53.4% | 58.7% | +5.3 pp |
| GPT-5 (OpenRouter) | single-event | 10 | 20 | 10 | 55.0% | 100.0% | 35.0% (15.8%–71.4%) | 55.9% | 68.0% | +12.0 pp |
| GPT-5 (OpenRouter) | multi-event | 34 | 102 | 160 | 82.4% | 52.5% | 57.8% (43.1%–73.4%) | 54.9% | 67.7% | +12.8 pp |
| GPT-5.4 | single-event | 10 | 19 | 10 | 52.6% | 90.0% | 31.6% (12.5%–69.2%) | 53.0% | 62.7% | +9.8 pp |
| GPT-5.4 | multi-event | 34 | 92 | 160 | 84.8% | 48.8% | 58.7% (44.7%–74.7%) | 51.3% | 63.5% | +12.2 pp |
| GPT-5 mini | single-event | 10 | 19 | 10 | 57.9% | 100.0% | 31.6% (7.7%–76.9%) | 58.8% | 66.0% | +7.2 pp |
| GPT-5 mini | multi-event | 34 | 110 | 160 | 89.1% | 61.3% | 67.3% (56.4%–76.5%) | 62.8% | 70.4% | +7.5 pp |
| Grok 4.6 | single-event | 10 | 17 | 10 | 58.8% | 90.0% | 47.1% (23.3%–100.0%) | 63.2% | 68.6% | +5.5 pp |
| Grok 4.6 | multi-event | 34 | 117 | 160 | 82.9% | 60.6% | 59.0% (46.6%–73.6%) | 59.8% | 71.5% | +11.8 pp |

## 4. Field agreement on matched events

Of the records matched to a gold event, how many carry that event's value. `Association` is the primary rule (protocol §5); `exact` additionally requires every gold location, the full year span and the exact hazard labels.

| System | Matched | Hazard | Year | Location | All three | Exact hazard | Exact year | Exact location | Exact all |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | 93 | 92.5% | 98.9% | 79.6% | 73.1% | 88.2% | 97.8% | 63.4% | 58.1% |
| NER baseline | 74 | 45.9% | 27.0% | 6.8% | 2.7% | 39.2% | 27.0% | 2.7% | 1.4% |
| Claude Haiku 4.5 | 73 | 93.2% | 98.6% | 75.3% | 71.2% | 90.4% | 97.3% | 58.9% | 54.8% |
| Claude Opus 5 | 104 | 91.3% | 98.1% | 75.0% | 70.2% | 90.4% | 97.1% | 67.3% | 63.5% |
| Claude Sonnet 5 | 101 | 96.0% | 99.0% | 73.3% | 72.3% | 93.1% | 97.0% | 63.4% | 61.4% |
| DeepSeek V3.1 | 101 | 95.0% | 99.0% | 82.2% | 81.2% | 92.1% | 99.0% | 69.3% | 67.3% |
| Llama 4 Maverick | 142 | 93.7% | 95.8% | 84.5% | 78.2% | 91.5% | 93.0% | 73.9% | 64.8% |
| Mistral Large | 97 | 88.7% | 95.9% | 68.0% | 61.9% | 83.5% | 95.9% | 59.8% | 53.6% |
| GPT-5 (OpenRouter) | 95 | 89.5% | 96.8% | 74.7% | 69.5% | 86.3% | 95.8% | 62.1% | 58.9% |
| GPT-5.4 | 88 | 92.0% | 92.0% | 73.9% | 68.2% | 87.5% | 90.9% | 59.1% | 53.4% |
| GPT-5 mini | 109 | 93.6% | 96.3% | 78.9% | 73.4% | 90.8% | 95.4% | 68.8% | 64.2% |
| Grok 4.6 | 107 | 86.9% | 97.2% | 82.2% | 72.0% | 86.0% | 96.3% | 68.2% | 62.6% |

## 5. Event-level attribute P / R / F1, per field

| System | Field | Precision | Recall | F1 (95% CI) | Pooled F1 | Gap |
|---|---|---:|---:|---|---:|---:|
| prompt 5 (gpt-5, Azure) | hazard | 77.9% | 53.4% | 63.3% (56.4%–72.3%) | 82.4% | +19.1 pp |
| prompt 5 (gpt-5, Azure) | year | 82.5% | 54.1% | 65.3% (56.9%–75.4%) | 78.8% | +13.5 pp |
| prompt 5 (gpt-5, Azure) | location | 59.6% | 37.0% | 45.6% (37.4%–56.8%) | 54.9% | +9.2 pp |
| NER baseline | hazard | 34.9% | 42.9% | 38.5% (34.6%–43.3%) | 74.9% | +36.4 pp |
| NER baseline | year | 33.1% | 30.8% | 31.9% (25.4%–38.2%) | 53.4% | +21.5 pp |
| NER baseline | location | 17.4% | 33.5% | 22.9% (19.3%–26.6%) | 42.2% | +19.3 pp |
| Claude Haiku 4.5 | hazard | 75.8% | 42.1% | 54.2% (44.1%–64.9%) | 71.2% | +17.1 pp |
| Claude Haiku 4.5 | year | 77.9% | 40.4% | 53.2% (42.2%–65.0%) | 67.0% | +13.8 pp |
| Claude Haiku 4.5 | location | 51.8% | 31.9% | 39.5% (31.6%–49.6%) | 49.5% | +10.0 pp |
| Claude Opus 5 | hazard | 77.9% | 60.9% | 68.3% (60.6%–76.8%) | 83.1% | +14.8 pp |
| Claude Opus 5 | year | 81.1% | 58.5% | 67.9% (59.6%–76.8%) | 80.4% | +12.4 pp |
| Claude Opus 5 | location | 61.4% | 46.6% | 53.0% (44.3%–63.1%) | 59.4% | +6.4 pp |
| Claude Sonnet 5 | hazard | 73.6% | 57.9% | 64.8% (57.4%–73.1%) | 80.5% | +15.7 pp |
| Claude Sonnet 5 | year | 75.7% | 57.9% | 65.6% (57.1%–74.7%) | 78.5% | +12.8 pp |
| Claude Sonnet 5 | location | 53.1% | 43.1% | 47.6% (38.1%–59.2%) | 58.0% | +10.4 pp |
| DeepSeek V3.1 | hazard | 72.5% | 57.9% | 64.4% (57.4%–72.6%) | 81.2% | +16.8 pp |
| DeepSeek V3.1 | year | 75.2% | 57.9% | 65.4% (58.4%–73.3%) | 78.3% | +12.8 pp |
| DeepSeek V3.1 | location | 54.5% | 42.0% | 47.4% (39.4%–58.4%) | 58.2% | +10.8 pp |
| Llama 4 Maverick | hazard | 73.7% | 80.3% | 76.9% (68.6%–84.3%) | 86.3% | +9.4 pp |
| Llama 4 Maverick | year | 79.2% | 77.5% | 78.3% (69.4%–86.5%) | 83.2% | +4.8 pp |
| Llama 4 Maverick | location | 63.5% | 61.2% | 62.4% (51.8%–71.8%) | 72.7% | +10.4 pp |
| Mistral Large | hazard | 71.1% | 53.6% | 61.1% (48.7%–71.2%) | 75.0% | +13.9 pp |
| Mistral Large | year | 76.8% | 52.5% | 62.3% (47.8%–73.9%) | 66.3% | +4.0 pp |
| Mistral Large | location | 51.1% | 43.3% | 46.9% (35.8%–57.5%) | 52.7% | +5.8 pp |
| GPT-5 (OpenRouter) | hazard | 70.1% | 52.8% | 60.3% (52.0%–68.3%) | 82.4% | +22.2 pp |
| GPT-5 (OpenRouter) | year | 76.7% | 54.1% | 63.5% (53.5%–73.2%) | 79.4% | +16.0 pp |
| GPT-5 (OpenRouter) | location | 54.5% | 39.1% | 45.6% (38.2%–55.2%) | 55.6% | +10.0 pp |
| GPT-5.4 | hazard | 74.2% | 50.0% | 59.7% (50.8%–69.9%) | 81.0% | +21.3 pp |
| GPT-5.4 | year | 75.0% | 45.9% | 56.9% (48.3%–67.4%) | 73.5% | +16.5 pp |
| GPT-5.4 | location | 52.7% | 35.1% | 42.2% (32.4%–55.0%) | 51.0% | +8.8 pp |
| GPT-5 mini | hazard | 79.6% | 61.2% | 69.2% (59.0%–79.5%) | 83.4% | +14.2 pp |
| GPT-5 mini | year | 82.0% | 59.6% | 69.0% (58.2%–79.7%) | 79.4% | +10.4 pp |
| GPT-5 mini | location | 63.9% | 44.9% | 52.8% (42.8%–62.6%) | 59.4% | +6.6 pp |
| Grok 4.6 | hazard | 70.6% | 60.7% | 65.3% (57.7%–73.6%) | 82.8% | +17.6 pp |
| Grok 4.6 | year | 77.7% | 59.0% | 67.1% (58.3%–75.9%) | 77.9% | +10.8 pp |
| Grok 4.6 | location | 55.0% | 49.6% | 52.2% (44.0%–62.6%) | 63.5% | +11.3 pp |

## 6. Misassociation — wrong values that belong to another event

Wrong values in matched records, split into those that are correct for a *different* gold event in the same window (the attribute swap a pooled metric credits) and those that belong to no event in the window.

| System | Field | Wrong values | Another event's | Unsupported | Share misassociated | Multi-event windows: wrong | another event's |
|---|---|---:|---:|---:|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | hazard | 6 | 2 | 4 | 33.3% | 5 | 2 |
| prompt 5 (gpt-5, Azure) | year | 0 | 0 | 0 | – | 0 | 0 |
| prompt 5 (gpt-5, Azure) | location | 24 | 4 | 20 | 16.7% | 18 | 4 |
| NER baseline | hazard | 86 | 57 | 29 | 66.3% | 85 | 57 |
| NER baseline | year | 68 | 28 | 40 | 41.2% | 62 | 28 |
| NER baseline | location | 302 | 113 | 189 | 37.4% | 278 | 113 |
| Claude Haiku 4.5 | hazard | 5 | 1 | 4 | 20.0% | 4 | 1 |
| Claude Haiku 4.5 | year | 1 | 0 | 1 | 0.0% | 1 | 0 |
| Claude Haiku 4.5 | location | 29 | 6 | 23 | 20.7% | 24 | 6 |
| Claude Opus 5 | hazard | 8 | 3 | 5 | 37.5% | 5 | 3 |
| Claude Opus 5 | year | 2 | 2 | 0 | 100.0% | 2 | 2 |
| Claude Opus 5 | location | 36 | 4 | 32 | 11.1% | 30 | 4 |
| Claude Sonnet 5 | hazard | 3 | 2 | 1 | 66.7% | 3 | 2 |
| Claude Sonnet 5 | year | 1 | 1 | 0 | 100.0% | 1 | 1 |
| Claude Sonnet 5 | location | 41 | 8 | 33 | 19.5% | 36 | 8 |
| DeepSeek V3.1 | hazard | 4 | 2 | 2 | 50.0% | 3 | 2 |
| DeepSeek V3.1 | year | 1 | 1 | 0 | 100.0% | 1 | 1 |
| DeepSeek V3.1 | location | 28 | 4 | 24 | 14.3% | 22 | 4 |
| Llama 4 Maverick | hazard | 9 | 3 | 6 | 33.3% | 8 | 3 |
| Llama 4 Maverick | year | 6 | 6 | 0 | 100.0% | 6 | 6 |
| Llama 4 Maverick | location | 28 | 15 | 13 | 53.6% | 26 | 15 |
| Mistral Large | hazard | 11 | 7 | 4 | 63.6% | 10 | 7 |
| Mistral Large | year | 5 | 3 | 2 | 60.0% | 5 | 3 |
| Mistral Large | location | 56 | 13 | 43 | 23.2% | 49 | 13 |
| GPT-5 (OpenRouter) | hazard | 9 | 4 | 5 | 44.4% | 8 | 4 |
| GPT-5 (OpenRouter) | year | 2 | 1 | 1 | 50.0% | 2 | 1 |
| GPT-5 (OpenRouter) | location | 32 | 5 | 27 | 15.6% | 25 | 5 |
| GPT-5.4 | hazard | 6 | 1 | 5 | 16.7% | 5 | 1 |
| GPT-5.4 | year | 4 | 3 | 1 | 75.0% | 4 | 3 |
| GPT-5.4 | location | 31 | 7 | 24 | 22.6% | 23 | 7 |
| GPT-5 mini | hazard | 5 | 3 | 2 | 60.0% | 5 | 3 |
| GPT-5 mini | year | 1 | 1 | 0 | 100.0% | 1 | 1 |
| GPT-5 mini | location | 31 | 8 | 23 | 25.8% | 26 | 8 |
| Grok 4.6 | hazard | 15 | 8 | 7 | 53.3% | 14 | 8 |
| Grok 4.6 | year | 3 | 2 | 1 | 66.7% | 3 | 2 |
| Grok 4.6 | location | 27 | 5 | 22 | 18.5% | 21 | 5 |

## 7. Matcher diagnostics

Links by tier (A anchored on located evidence, B paraphrase, C year + location fallback). False positives: `split` — the record's identity points at a gold event another record took; `no event` — nothing in the gold it could be. False negatives: `merged` — a record matched elsewhere also carries this event's evidence; `missed` — no record does.

| System | Tier A | Tier B | Tier C | FP: split | FP: no event | FN: merged | FN: missed |
|---|---:|---:|---:|---:|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | 79 | 7 | 7 | 8 | 12 | 21 | 57 |
| NER baseline | 48 | 0 | 26 | 9 | 23 | 27 | 69 |
| Claude Haiku 4.5 | 44 | 25 | 4 | 10 | 9 | 13 | 85 |
| Claude Opus 5 | 92 | 8 | 4 | 8 | 14 | 22 | 46 |
| Claude Sonnet 5 | 96 | 2 | 3 | 13 | 19 | 19 | 51 |
| DeepSeek V3.1 | 97 | 1 | 3 | 16 | 17 | 23 | 47 |
| Llama 4 Maverick | 127 | 4 | 11 | 13 | 28 | 13 | 16 |
| Mistral Large | 91 | 1 | 5 | 8 | 16 | 9 | 66 |
| GPT-5 (OpenRouter) | 79 | 11 | 5 | 8 | 20 | 20 | 56 |
| GPT-5.4 | 54 | 31 | 3 | 7 | 17 | 32 | 51 |
| GPT-5 mini | 98 | 7 | 4 | 7 | 14 | 21 | 41 |
| Grok 4.6 | 67 | 38 | 2 | 10 | 18 | 30 | 34 |

## 8. What the matching rule costs

The same records under a field-maximising alignment that ignores evidence and pairs records with gold events to maximise complete records. It is the most generous one-to-one reading possible — an upper bound, never the result.

| System | Complete-record correctness, evidence-anchored | Field-maximising bound | Δ |
|---|---:|---:|---:|
| prompt 5 (gpt-5, Azure) | 60.2% | 62.8% | +2.7 pp |
| NER baseline | 1.9% | 2.8% | +0.9 pp |
| Claude Haiku 4.5 | 56.5% | 60.9% | +4.3 pp |
| Claude Opus 5 | 57.9% | 60.3% | +2.4 pp |
| Claude Sonnet 5 | 54.9% | 58.6% | +3.8 pp |
| DeepSeek V3.1 | 61.2% | 64.9% | +3.7 pp |
| Llama 4 Maverick | 60.7% | 64.5% | +3.8 pp |
| Mistral Large | 49.6% | 56.2% | +6.6 pp |
| GPT-5 (OpenRouter) | 53.7% | 56.9% | +3.3 pp |
| GPT-5.4 | 53.6% | 59.8% | +6.2 pp |
| GPT-5 mini | 61.5% | 63.8% | +2.3 pp |
| Grok 4.6 | 57.0% | 63.0% | +5.9 pp |

## 9. Paired difference against prompt 5 (gpt-5, Azure)

Complete-record correctness, system minus baseline, on the windows both returned; 95% paired cluster bootstrap.

| System | Windows | All windows | Single-event | Multi-event |
|---|---:|---|---|---|
| NER baseline | 45 | -58.3 pp (-69.1 to -47.1) | -33.5 pp (-68.4 to -2.7) | -63.1 pp (-75.4 to -51.9) |
| Claude Haiku 4.5 | 45 | -3.7 pp (-13.7 to +9.6) | +14.4 pp (-10.0 to +33.3) | -6.9 pp (-17.6 to +7.5) |
| Claude Opus 5 | 45 | -2.2 pp (-10.4 to +6.3) | -9.9 pp (-22.6 to +16.2) | -1.8 pp (-10.4 to +6.9) |
| Claude Sonnet 5 | 45 | -5.3 pp (-15.7 to +6.8) | -3.7 pp (-15.8 to +26.7) | -6.5 pp (-18.0 to +6.7) |
| DeepSeek V3.1 | 45 | +1.0 pp (-8.0 to +11.4) | +12.7 pp (+0.0 to +20.8) | -1.7 pp (-11.2 to +9.4) |
| Llama 4 Maverick | 45 | +0.5 pp (-9.4 to +10.2) | +0.0 pp (-22.0 to +49.2) | -1.2 pp (-11.8 to +9.2) |
| Mistral Large | 45 | -10.6 pp (-22.8 to -0.6) | +18.8 pp (-11.6 to +50.0) | -15.1 pp (-28.8 to -3.7) |
| GPT-5 (OpenRouter) | 45 | -6.5 pp (-13.3 to +1.0) | -6.2 pp (-12.5 to +8.2) | -6.4 pp (-13.8 to +2.4) |
| GPT-5.4 | 45 | -6.6 pp (-14.8 to +2.0) | -9.6 pp (-20.0 to +5.0) | -5.5 pp (-14.6 to +3.9) |
| GPT-5 mini | 45 | +1.4 pp (-7.3 to +8.4) | -9.6 pp (-18.9 to +12.1) | +3.1 pp (-4.7 to +9.5) |
| Grok 4.6 | 45 | -3.1 pp (-10.9 to +5.4) | +5.9 pp (-8.0 to +42.0) | -5.2 pp (-13.4 to +3.7) |

## 10. By sampling stratum

Strata are the pre-annotation proxies the sample was drawn on (protocol §2).

| System | Stratum | Windows | Records | Detection P | Detection R | Complete-record correctness |
|---|---|---:|---:|---:|---:|---|
| prompt 5 (gpt-5, Azure) | multi_hazard_multi_year | 10 | 47 | 74.5% | 59.3% | 51.1% (36.2%–68.1%) |
| prompt 5 (gpt-5, Azure) | multi_hazard_same_year | 10 | 22 | 81.8% | 31.6% | 45.5% (21.0%–65.0%) |
| prompt 5 (gpt-5, Azure) | same_hazard_multi_year | 10 | 26 | 92.3% | 82.1% | 84.6% (68.2%–96.7%) |
| prompt 5 (gpt-5, Azure) | single | 15 | 18 | 88.9% | 61.5% | 66.7% (42.8%–86.7%) |
| NER baseline | multi_hazard_multi_year | 10 | 28 | 75.0% | 35.6% | 0.0% (0.0%–0.0%) |
| NER baseline | multi_hazard_same_year | 10 | 29 | 82.8% | 42.1% | 3.4% (0.0%–15.8%) |
| NER baseline | same_hazard_multi_year | 10 | 20 | 60.0% | 42.9% | 0.0% (0.0%–0.0%) |
| NER baseline | single | 15 | 29 | 58.6% | 65.4% | 3.4% (0.0%–11.4%) |
| Claude Haiku 4.5 | multi_hazard_multi_year | 10 | 42 | 66.7% | 47.5% | 42.9% (25.0%–77.8%) |
| Claude Haiku 4.5 | multi_hazard_same_year | 10 | 16 | 93.8% | 26.3% | 62.5% (37.5%–87.5%) |
| Claude Haiku 4.5 | same_hazard_multi_year | 10 | 15 | 86.7% | 42.9% | 73.3% (38.5%–100.0%) |
| Claude Haiku 4.5 | single | 15 | 19 | 89.5% | 65.4% | 68.4% (46.7%–85.7%) |
| Claude Opus 5 | multi_hazard_multi_year | 10 | 60 | 73.3% | 74.6% | 46.7% (23.9%–72.0%) |
| Claude Opus 5 | multi_hazard_same_year | 10 | 23 | 91.3% | 35.1% | 52.2% (33.3%–64.0%) |
| Claude Opus 5 | same_hazard_multi_year | 10 | 24 | 91.7% | 75.0% | 83.3% (67.9%–100.0%) |
| Claude Opus 5 | single | 15 | 19 | 89.5% | 65.4% | 68.4% (42.9%–85.0%) |
| Claude Sonnet 5 | multi_hazard_multi_year | 10 | 70 | 62.9% | 74.6% | 45.7% (25.5%–75.9%) |
| Claude Sonnet 5 | multi_hazard_same_year | 10 | 24 | 87.5% | 36.8% | 50.0% (28.6%–68.4%) |
| Claude Sonnet 5 | same_hazard_multi_year | 10 | 22 | 90.9% | 67.9% | 81.8% (56.2%–100.0%) |
| Claude Sonnet 5 | single | 15 | 17 | 94.1% | 61.5% | 64.7% (36.4%–82.4%) |
| DeepSeek V3.1 | multi_hazard_multi_year | 10 | 64 | 67.2% | 72.9% | 57.8% (38.5%–85.4%) |
| DeepSeek V3.1 | multi_hazard_same_year | 10 | 27 | 81.5% | 38.6% | 55.6% (28.0%–78.9%) |
| DeepSeek V3.1 | same_hazard_multi_year | 10 | 25 | 84.0% | 71.4% | 72.0% (52.0%–90.0%) |
| DeepSeek V3.1 | single | 15 | 18 | 83.3% | 57.7% | 66.7% (47.1%–84.2%) |
| Llama 4 Maverick | multi_hazard_multi_year | 10 | 79 | 64.6% | 86.4% | 46.8% (29.3%–61.6%) |
| Llama 4 Maverick | multi_hazard_same_year | 10 | 46 | 91.3% | 71.9% | 73.9% (50.0%–85.4%) |
| Llama 4 Maverick | same_hazard_multi_year | 10 | 28 | 85.7% | 85.7% | 64.3% (50.0%–78.6%) |
| Llama 4 Maverick | single | 15 | 30 | 83.3% | 96.2% | 73.3% (61.5%–88.0%) |
| Mistral Large | multi_hazard_multi_year | 10 | 38 | 68.4% | 44.1% | 50.0% (31.0%–63.8%) |
| Mistral Large | multi_hazard_same_year | 10 | 47 | 85.1% | 68.4% | 51.1% (27.8%–58.9%) |
| Mistral Large | same_hazard_multi_year | 10 | 14 | 100.0% | 46.4% | 42.9% (9.1%–59.1%) |
| Mistral Large | single | 15 | 22 | 77.3% | 65.4% | 50.0% (27.3%–70.0%) |
| GPT-5 (OpenRouter) | multi_hazard_multi_year | 10 | 58 | 70.7% | 69.5% | 50.0% (29.5%–79.7%) |
| GPT-5 (OpenRouter) | multi_hazard_same_year | 10 | 23 | 78.3% | 31.6% | 34.8% (14.3%–51.9%) |
| GPT-5 (OpenRouter) | same_hazard_multi_year | 10 | 23 | 87.0% | 67.9% | 78.3% (55.0%–100.0%) |
| GPT-5 (OpenRouter) | single | 15 | 19 | 84.2% | 61.5% | 57.9% (38.9%–76.5%) |
| GPT-5.4 | multi_hazard_multi_year | 10 | 52 | 71.2% | 62.7% | 48.1% (27.8%–71.7%) |
| GPT-5.4 | multi_hazard_same_year | 10 | 21 | 90.5% | 33.3% | 47.6% (25.0%–76.5%) |
| GPT-5.4 | same_hazard_multi_year | 10 | 19 | 84.2% | 53.6% | 78.9% (50.0%–100.0%) |
| GPT-5.4 | single | 15 | 20 | 80.0% | 61.5% | 50.0% (27.8%–73.9%) |
| GPT-5 mini | multi_hazard_multi_year | 10 | 60 | 78.3% | 79.7% | 55.0% (31.0%–72.5%) |
| GPT-5 mini | multi_hazard_same_year | 10 | 28 | 82.1% | 40.4% | 60.7% (30.0%–76.3%) |
| GPT-5 mini | same_hazard_multi_year | 10 | 21 | 95.2% | 67.9% | 81.0% (53.3%–100.0%) |
| GPT-5 mini | single | 15 | 21 | 90.5% | 73.1% | 61.9% (35.3%–82.1%) |
| Grok 4.6 | multi_hazard_multi_year | 10 | 67 | 68.7% | 78.0% | 52.2% (34.3%–75.5%) |
| Grok 4.6 | multi_hazard_same_year | 10 | 25 | 92.0% | 40.4% | 40.0% (21.4%–68.4%) |
| Grok 4.6 | same_hazard_multi_year | 10 | 22 | 90.9% | 67.9% | 77.3% (54.5%–100.0%) |
| Grok 4.6 | single | 15 | 21 | 85.7% | 69.2% | 71.4% (53.3%–86.7%) |

## 11. Link audit

A seeded sample of the matcher's decisions, judged by the annotator after scoring. It checks the matcher; it does not change any figure above.

| Decision | Judged | Annotator agrees | Pending |
|---|---:|---|---:|
| link_AB | 25 | 88.0% (22/25) | 0 |
| link_C | 77 | 97.4% (75/77) | 0 |
| fp | 15 | 80.0% (12/15) | 0 |

