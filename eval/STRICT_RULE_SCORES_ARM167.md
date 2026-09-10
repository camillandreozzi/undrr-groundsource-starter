# Stricter rules over the same runs (arm 167)

Annotations: `human_annotations.csv`; runs: `outputs/`. No re-judging, no re-running — the published scorer's objects re-pooled.

| Model | Haz-fam F1 | Haz-label F1 | Loc-fz F1 | Loc-strict F1 | Subset matches | Pooled P (pos only) | Pooled P (+neg) | Pooled F1 (+neg) |
|---|---|---|---|---|---|---|---|---|
| GPT-5.4 | 92.2 | 90.3 | 82.8 | 65.8 | 125 | 86.5 | 80.6 | 83.5 |
| GPT-5 | 92.7 | 91.2 | 80.5 | 69.1 | 88 | 84.4 | 79.2 | 83.5 |
| Claude Opus 5 | 90.4 | 89.7 | 77.0 | 61.8 | 119 | 79.3 | 74.2 | 78.8 |
| Grok 4.6 | 89.5 | 87.7 | 74.8 | 59.8 | 120 | 75.1 | 70.6 | 78.7 |
| Claude Sonnet 5 | 89.9 | 88.9 | 76.5 | 61.1 | 119 | 79.5 | 73.8 | 78.2 |
| DeepSeek V3.1 | 87.1 | 86.2 | 73.9 | 63.2 | 82 | 78.2 | 72.7 | 76.9 |
| GPT-5 mini | 89.4 | 87.6 | 70.4 | 31.3 | 287 | 75.4 | 69.1 | 75.5 |
| Claude Haiku 4.5 | 85.7 | 83.3 | 75.1 | 61.5 | 92 | 83.6 | 79.0 | 76.8 |
| Llama 4 Maverick | 79.4 | 76.5 | 57.3 | 44.6 | 115 | 58.8 | 54.4 | 65.3 |
| Mistral Large | 74.0 | 71.3 | 47.8 | 38.6 | 79 | 54.5 | 50.3 | 55.0 |
| NER baseline | 67.6 | 65.0 | 30.0 | 20.2 | 99 | 36.0 | 33.4 | 42.0 |

Gold-negative documents in the denominator of the `+neg` columns: 10.

| Model | Fired on neg docs | Spurious items | Matched pairs | Identical | Subset (type word) | Subset (place name) | Variant | Subset share |
|---|---|---|---|---|---|---|---|---|
| GPT-5.4 | 10/10 | 99 | 575 | 445 | 34 | 91 | 5 | 21.7 |
| GPT-5 | 10/10 | 93 | 563 | 469 | 29 | 59 | 6 | 15.6 |
| Claude Opus 5 | 9/10 | 100 | 559 | 432 | 33 | 86 | 8 | 21.3 |
| Grok 4.6 | 10/10 | 102 | 583 | 460 | 55 | 65 | 3 | 20.6 |
| Claude Sonnet 5 | 9/10 | 110 | 546 | 421 | 36 | 83 | 6 | 21.8 |
| DeepSeek V3.1 | 9/10 | 106 | 519 | 433 | 22 | 60 | 4 | 15.8 |
| GPT-5 mini | 10/10 | 136 | 512 | 220 | 23 | 264 | 5 | 56.1 |
| Claude Haiku 4.5 | 8/10 | 71 | 497 | 400 | 33 | 59 | 5 | 18.5 |
| Llama 4 Maverick | 10/10 | 153 | 490 | 372 | 39 | 76 | 3 | 23.5 |
| Mistral Large | 8/10 | 128 | 375 | 294 | 17 | 62 | 2 | 21.1 |
| NER baseline | 9/10 | 168 | 287 | 186 | 29 | 70 | 2 | 34.5 |
