# Stricter rules over the same runs (arm 217)

Annotations: `human_annotations_pooled.csv`; runs: `outputs_pooled/`. No re-judging, no re-running — the published scorer's objects re-pooled.

| Model | Haz-fam F1 | Haz-label F1 | Loc-fz F1 | Loc-strict F1 | Subset matches | Pooled P (pos only) | Pooled P (+neg) | Pooled F1 (+neg) |
|---|---|---|---|---|---|---|---|---|
| GPT-5.4 | 91.9 | 90.1 | 82.9 | 65.5 | 132 | 86.5 | 80.7 | 83.6 |
| GPT-5 | 92.2 | 90.3 | 80.3 | 68.7 | 92 | 84.2 | 79.0 | 83.2 |
| Grok 4.6 | 89.0 | 87.1 | 74.6 | 59.7 | 125 | 75.0 | 70.3 | 78.4 |
| Claude Opus 5 | 89.8 | 88.9 | 76.5 | 61.0 | 127 | 78.9 | 73.7 | 78.3 |
| Claude Sonnet 5 | 89.7 | 88.5 | 75.8 | 59.8 | 129 | 79.0 | 73.3 | 77.8 |
| DeepSeek V3.1 | 86.8 | 85.7 | 73.7 | 62.7 | 87 | 78.4 | 72.7 | 76.6 |
| GPT-5 mini | 89.1 | 87.2 | 69.8 | 31.1 | 298 | 74.8 | 68.2 | 74.9 |
| Claude Haiku 4.5 | 85.0 | 82.4 | 74.5 | 60.7 | 96 | 83.5 | 78.8 | 76.2 |
| Llama 4 Maverick | 79.3 | 76.6 | 57.0 | 44.2 | 120 | 58.6 | 53.7 | 64.8 |
| Mistral Large | 73.4 | 70.8 | 47.0 | 37.9 | 83 | 53.7 | 48.1 | 53.6 |
| NER baseline | 67.4 | 65.0 | 30.3 | 20.3 | 108 | 35.9 | 32.1 | 41.2 |

Gold-negative documents in the denominator of the `+neg` columns: 46.

| Model | Fired on neg docs | Spurious items | Matched pairs | Identical | Subset (type word) | Subset (place name) | Variant | Subset share |
|---|---|---|---|---|---|---|---|---|
| GPT-5.4 | 11/46 | 102 | 597 | 460 | 37 | 95 | 5 | 22.1 |
| GPT-5 | 11/46 | 96 | 582 | 481 | 30 | 62 | 9 | 15.8 |
| Grok 4.6 | 13/46 | 112 | 604 | 476 | 58 | 67 | 3 | 20.7 |
| Claude Opus 5 | 11/46 | 106 | 578 | 443 | 35 | 92 | 8 | 22.0 |
| Claude Sonnet 5 | 11/46 | 116 | 565 | 430 | 39 | 90 | 6 | 22.8 |
| DeepSeek V3.1 | 11/46 | 114 | 534 | 443 | 23 | 64 | 4 | 16.3 |
| GPT-5 mini | 14/46 | 151 | 531 | 228 | 23 | 275 | 5 | 56.1 |
| Claude Haiku 4.5 | 9/46 | 74 | 509 | 408 | 36 | 60 | 5 | 18.9 |
| Llama 4 Maverick | 16/46 | 181 | 507 | 384 | 41 | 79 | 3 | 23.7 |
| Mistral Large | 14/46 | 184 | 388 | 303 | 19 | 64 | 2 | 21.4 |
| NER baseline | 19/46 | 270 | 306 | 196 | 30 | 78 | 2 | 35.3 |
