# Prompt 5 across models — agreement, not accuracy

15 runs over 167 shared documents (the human annotation queue's set).

> Every figure on this page is **agreement between models**. None of it is accuracy — there is no ground truth here. Two models can be wrong in the same way, and on prompt 5's location rules that is the likely failure mode. For accuracy see `MODEL_SCORES.md`.

> **The document set is not neutral.** These 167 documents are the ones behind the review queue, and that queue was built from events the prompt-5 / gpt-5 production run itself emitted. So that arm finds an event in 100% of them *by construction*, and every other model's detection rate is being measured against a set selected in gpt-5's favour. It says how well a model reproduces gpt-5's finds, not how well it does on the corpus. Only the human annotations settle which of them was right.

## Behaviour per model

| Model | Covered | Docs w/ event | Events | Ev/doc | Loc/ev | Errors | Mode | Cost $ | Min |
|---|---:|---|---:|---:|---:|---:|---|---:|---:|
| Claude Haiku 4.5 | 167 | 88.6% (82.9%–92.6%, n=167) | 438 | 2.62 | 1.67 | 0 | json_schema | 0.00 | 62 |
| Claude Opus 5 | 167 | 94.6% (90.1%–97.1%, n=167) | 498 | 2.98 | 1.83 | 0 | json_schema | 12.81 | 10 |
| Claude Sonnet 5 | 167 | 94.6% (90.1%–97.1%, n=167) | 517 | 3.10 | 1.72 | 0 | json_schema | 5.72 | 11 |
| DeepSeek V3.1 | 167 | 96.4% (92.4%–98.3%, n=167) | 565 | 3.38 | 1.53 | 0 | none | 0.00 | — |
| Gemini 2.5 Flash | 167 | 0.0% (0.0%–2.2%, n=167) | 0 | 0.00 | 0.00 | 167 | none | 0.00 | 0 |
| Gemini 2.5 Pro | 167 | 0.0% (0.0%–2.2%, n=167) | 0 | 0.00 | 0.00 | 167 | none | 0.00 | 0 |
| Llama 4 Maverick | 167 | 98.2% (94.9%–99.4%, n=167) | 747 | 4.47 | 1.67 | 0 | json_schema | 0.28 | 21 |
| Mistral Large | 167 | 79.6% (72.9%–85.0%, n=167) | 520 | 3.11 | 2.10 | 0 | json_schema | 0.49 | 6 |
| GPT-5 (OpenRouter) | 167 | 98.2% (94.9%–99.4%, n=167) | 561 | 3.36 | 1.54 | 0 | json_schema | 8.41 | 45 |
| GPT-5.4 | 167 | 97.6% (94.0%–99.1%, n=167) | 547 | 3.28 | 1.62 | 0 | json_schema | 9.20 | 18 |
| GPT-5 mini | 167 | 99.4% (96.7%–99.9%, n=167) | 587 | 3.51 | 1.56 | 0 | json_schema | 0.04 | 2 |
| Qwen3 235B | 167 | 0.0% (0.0%–2.2%, n=167) | 0 | 0.00 | 0.00 | 167 | none | 0.00 | 56 |
| Grok 4.6 | 167 | 95.2% (90.8%–97.6%, n=167) | 625 | 3.74 | 1.80 | 0 | json_schema | 6.90 | 55 |
| prompt 5 (gpt-5, Azure) | 167 | 100.0% (97.8%–100.0%, n=167) | 572 | 3.43 | 1.52 | — | — | — | — |
| NER baseline | 167 | 90.4% (85.0%–94.0%, n=167) | 343 | 2.05 | 4.84 | — | — | — | — |

## Location granularity — did the sub-national rule land?

Prompt 5 forbids a bare country for sub-national hazards. A high `country` share is a model ignoring that rule; a high `unknown` share is a model unable to self-tag. Neither needs gold to read.

| Model | Sub-national | country | unknown |
|---|---:|---:|---:|
| Claude Haiku 4.5 | 95.1% | 4.5% | 0.4% |
| Claude Opus 5 | 93.2% | 5.9% | 0.9% |
| Claude Sonnet 5 | 91.4% | 7.4% | 1.1% |
| DeepSeek V3.1 | 86.0% | 10.0% | 4.1% |
| Gemini 2.5 Flash | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | 0.0% | 0.0% | 0.0% |
| Llama 4 Maverick | 58.6% | 37.2% | 4.2% |
| Mistral Large | 76.9% | 22.5% | 0.5% |
| GPT-5 (OpenRouter) | 92.6% | 3.6% | 3.8% |
| GPT-5.4 | 86.5% | 2.8% | 10.6% |
| GPT-5 mini | 84.2% | 14.0% | 1.8% |
| Qwen3 235B | 0.0% | 0.0% | 0.0% |
| Grok 4.6 | 83.5% | 5.4% | 11.0% |
| prompt 5 (gpt-5, Azure) | 89.1% | 4.7% | 6.2% |
| NER baseline | 24.7% | 34.2% | 41.1% |

## Hazard families found, per model

| Model | cyclone | drought | earthquake | flood | heat | landslide | other | volcano | wildfire |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude Haiku 4.5 | 37 | 16 | 73 | 48 | 5 | 12 | 22 | 12 | 11 |
| Claude Opus 5 | 42 | 19 | 77 | 70 | 6 | 16 | 27 | 14 | 14 |
| Claude Sonnet 5 | 41 | 22 | 75 | 62 | 7 | 15 | 27 | 14 | 16 |
| DeepSeek V3.1 | 51 | 20 | 78 | 63 | 9 | 15 | 29 | 14 | 17 |
| Gemini 2.5 Flash | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Gemini 2.5 Pro | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Llama 4 Maverick | 62 | 29 | 89 | 85 | 12 | 21 | 42 | 16 | 21 |
| Mistral Large | 53 | 16 | 74 | 70 | 7 | 20 | 28 | 8 | 18 |
| GPT-5 (OpenRouter) | 43 | 16 | 83 | 62 | 5 | 15 | 31 | 15 | 13 |
| GPT-5.4 | 38 | 14 | 85 | 62 | 6 | 16 | 28 | 14 | 12 |
| GPT-5 mini | 44 | 22 | 77 | 66 | 11 | 17 | 31 | 15 | 16 |
| Qwen3 235B | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Grok 4.6 | 44 | 20 | 82 | 65 | 8 | 19 | 30 | 16 | 14 |
| prompt 5 (gpt-5, Azure) | 40 | 17 | 82 | 62 | 7 | 15 | 29 | 15 | 12 |
| NER baseline | 60 | 34 | 84 | 82 | 10 | 29 | 37 | 20 | 19 |

## Pairwise agreement on event detection

κ corrects for chance: most documents yield no event, so raw agreement is high by default and only κ says whether two models agree for a reason. κ is 0 when one run flags everything — there are then no true negatives for chance agreement to be corrected against, which is exactly the case for the gpt-5 arm on this selected set.

| A | B | n | Agreement | κ | Both | A only | B only |
|---|---|---:|---:|---:|---:|---:|---:|
| Claude Opus 5 | Claude Sonnet 5 | 167 | 95.2% | 0.530 | 154 | 4 | 4 |
| GPT-5.4 | Grok 4.6 | 167 | 96.4% | 0.484 | 158 | 5 | 1 |
| Claude Haiku 4.5 | Claude Opus 5 | 167 | 91.6% | 0.461 | 146 | 2 | 12 |
| Claude Opus 5 | GPT-5.4 | 167 | 95.8% | 0.443 | 157 | 1 | 6 |
| Claude Opus 5 | Grok 4.6 | 167 | 94.6% | 0.442 | 154 | 4 | 5 |
| Claude Haiku 4.5 | Claude Sonnet 5 | 167 | 90.4% | 0.383 | 145 | 3 | 13 |
| Llama 4 Maverick | Grok 4.6 | 167 | 95.8% | 0.347 | 158 | 6 | 1 |
| Claude Haiku 4.5 | Grok 4.6 | 167 | 89.8% | 0.325 | 145 | 3 | 14 |
| Llama 4 Maverick | GPT-5 (OpenRouter) | 167 | 97.6% | 0.321 | 162 | 2 | 2 |
| Claude Sonnet 5 | GPT-5.4 | 167 | 94.6% | 0.284 | 156 | 2 | 7 |
| Llama 4 Maverick | GPT-5.4 | 167 | 97.0% | 0.271 | 161 | 3 | 2 |
| GPT-5 (OpenRouter) | GPT-5.4 | 167 | 97.0% | 0.271 | 161 | 3 | 2 |
| DeepSeek V3.1 | Grok 4.6 | 167 | 94.0% | 0.255 | 155 | 6 | 4 |
| Claude Haiku 4.5 | GPT-5.4 | 167 | 89.8% | 0.230 | 147 | 1 | 16 |
| Claude Haiku 4.5 | Mistral Large | 167 | 79.0% | 0.227 | 123 | 25 | 10 |
| DeepSeek V3.1 | Llama 4 Maverick | 167 | 95.8% | 0.203 | 159 | 2 | 5 |
| Claude Sonnet 5 | Grok 4.6 | 167 | 92.2% | 0.194 | 152 | 6 | 7 |
| GPT-5 (OpenRouter) | Grok 4.6 | 167 | 94.6% | 0.160 | 157 | 7 | 2 |
| Claude Haiku 4.5 | Llama 4 Maverick | 167 | 89.2% | 0.156 | 147 | 1 | 17 |
| DeepSeek V3.1 | Mistral Large | 167 | 80.8% | 0.148 | 131 | 30 | 2 |
| Claude Opus 5 | Llama 4 Maverick | 167 | 94.0% | 0.144 | 156 | 2 | 8 |
| Claude Opus 5 | GPT-5 (OpenRouter) | 167 | 94.0% | 0.144 | 156 | 2 | 8 |
| Claude Sonnet 5 | Llama 4 Maverick | 167 | 94.0% | 0.144 | 156 | 2 | 8 |
| Claude Sonnet 5 | GPT-5 (OpenRouter) | 167 | 94.0% | 0.144 | 156 | 2 | 8 |
| Llama 4 Maverick | Mistral Large | 167 | 81.4% | 0.134 | 133 | 31 | 0 |
| Mistral Large | GPT-5 (OpenRouter) | 167 | 81.4% | 0.134 | 133 | 0 | 31 |
| Mistral Large | GPT-5.4 | 167 | 80.8% | 0.120 | 132 | 1 | 31 |
| GPT-5 mini | NER baseline | 167 | 91.0% | 0.108 | 151 | 15 | 0 |
| Claude Opus 5 | DeepSeek V3.1 | 167 | 92.2% | 0.094 | 153 | 5 | 8 |
| Claude Sonnet 5 | DeepSeek V3.1 | 167 | 92.2% | 0.094 | 153 | 5 | 8 |
| Claude Haiku 4.5 | NER baseline | 167 | 82.6% | 0.075 | 135 | 13 | 16 |
| Mistral Large | Grok 4.6 | 167 | 78.4% | 0.071 | 128 | 5 | 31 |
| Claude Haiku 4.5 | GPT-5 (OpenRouter) | 167 | 88.0% | 0.062 | 146 | 2 | 18 |
| Claude Opus 5 | Mistral Large | 167 | 77.8% | 0.059 | 127 | 31 | 6 |
| Claude Haiku 4.5 | DeepSeek V3.1 | 167 | 86.2% | 0.027 | 143 | 5 | 18 |
| Grok 4.6 | NER baseline | 167 | 86.8% | 0.021 | 144 | 15 | 7 |
| Claude Sonnet 5 | Mistral Large | 167 | 76.6% | 0.009 | 126 | 32 | 7 |
| Claude Haiku 4.5 | Gemini 2.5 Flash | 167 | 11.4% | 0.000 | 0 | 148 | 0 |
| Claude Haiku 4.5 | Gemini 2.5 Pro | 167 | 11.4% | 0.000 | 0 | 148 | 0 |
| Claude Haiku 4.5 | Qwen3 235B | 167 | 11.4% | 0.000 | 0 | 148 | 0 |
| Claude Haiku 4.5 | prompt 5 (gpt-5, Azure) | 167 | 88.6% | 0.000 | 148 | 0 | 19 |
| Claude Opus 5 | Gemini 2.5 Flash | 167 | 5.4% | 0.000 | 0 | 158 | 0 |
| Claude Opus 5 | Gemini 2.5 Pro | 167 | 5.4% | 0.000 | 0 | 158 | 0 |
| Claude Opus 5 | Qwen3 235B | 167 | 5.4% | 0.000 | 0 | 158 | 0 |
| Claude Opus 5 | prompt 5 (gpt-5, Azure) | 167 | 94.6% | 0.000 | 158 | 0 | 9 |
| Claude Sonnet 5 | Gemini 2.5 Flash | 167 | 5.4% | 0.000 | 0 | 158 | 0 |
| Claude Sonnet 5 | Gemini 2.5 Pro | 167 | 5.4% | 0.000 | 0 | 158 | 0 |
| Claude Sonnet 5 | Qwen3 235B | 167 | 5.4% | 0.000 | 0 | 158 | 0 |
| Claude Sonnet 5 | prompt 5 (gpt-5, Azure) | 167 | 94.6% | 0.000 | 158 | 0 | 9 |
| DeepSeek V3.1 | Gemini 2.5 Flash | 167 | 3.6% | 0.000 | 0 | 161 | 0 |
| DeepSeek V3.1 | Gemini 2.5 Pro | 167 | 3.6% | 0.000 | 0 | 161 | 0 |
| DeepSeek V3.1 | Qwen3 235B | 167 | 3.6% | 0.000 | 0 | 161 | 0 |
| DeepSeek V3.1 | prompt 5 (gpt-5, Azure) | 167 | 96.4% | 0.000 | 161 | 0 | 6 |
| Gemini 2.5 Flash | Gemini 2.5 Pro | 167 | 100.0% | 0.000 | 0 | 0 | 0 |
| Gemini 2.5 Flash | Llama 4 Maverick | 167 | 1.8% | 0.000 | 0 | 0 | 164 |
| Gemini 2.5 Flash | Mistral Large | 167 | 20.4% | 0.000 | 0 | 0 | 133 |
| Gemini 2.5 Flash | GPT-5 (OpenRouter) | 167 | 1.8% | 0.000 | 0 | 0 | 164 |
| Gemini 2.5 Flash | GPT-5.4 | 167 | 2.4% | 0.000 | 0 | 0 | 163 |
| Gemini 2.5 Flash | GPT-5 mini | 167 | 0.6% | 0.000 | 0 | 0 | 166 |
| Gemini 2.5 Flash | Qwen3 235B | 167 | 100.0% | 0.000 | 0 | 0 | 0 |
| Gemini 2.5 Flash | Grok 4.6 | 167 | 4.8% | 0.000 | 0 | 0 | 159 |
| Gemini 2.5 Flash | prompt 5 (gpt-5, Azure) | 167 | 0.0% | 0.000 | 0 | 0 | 167 |
| Gemini 2.5 Flash | NER baseline | 167 | 9.6% | 0.000 | 0 | 0 | 151 |
| Gemini 2.5 Pro | Llama 4 Maverick | 167 | 1.8% | 0.000 | 0 | 0 | 164 |
| Gemini 2.5 Pro | Mistral Large | 167 | 20.4% | 0.000 | 0 | 0 | 133 |
| Gemini 2.5 Pro | GPT-5 (OpenRouter) | 167 | 1.8% | 0.000 | 0 | 0 | 164 |
| Gemini 2.5 Pro | GPT-5.4 | 167 | 2.4% | 0.000 | 0 | 0 | 163 |
| Gemini 2.5 Pro | GPT-5 mini | 167 | 0.6% | 0.000 | 0 | 0 | 166 |
| Gemini 2.5 Pro | Qwen3 235B | 167 | 100.0% | 0.000 | 0 | 0 | 0 |
| Gemini 2.5 Pro | Grok 4.6 | 167 | 4.8% | 0.000 | 0 | 0 | 159 |
| Gemini 2.5 Pro | prompt 5 (gpt-5, Azure) | 167 | 0.0% | 0.000 | 0 | 0 | 167 |
| Gemini 2.5 Pro | NER baseline | 167 | 9.6% | 0.000 | 0 | 0 | 151 |
| Llama 4 Maverick | Qwen3 235B | 167 | 1.8% | 0.000 | 0 | 164 | 0 |
| Llama 4 Maverick | prompt 5 (gpt-5, Azure) | 167 | 98.2% | 0.000 | 164 | 0 | 3 |
| Mistral Large | Qwen3 235B | 167 | 20.4% | 0.000 | 0 | 133 | 0 |
| Mistral Large | prompt 5 (gpt-5, Azure) | 167 | 79.6% | 0.000 | 133 | 0 | 34 |
| GPT-5 (OpenRouter) | Qwen3 235B | 167 | 1.8% | 0.000 | 0 | 164 | 0 |
| GPT-5 (OpenRouter) | prompt 5 (gpt-5, Azure) | 167 | 98.2% | 0.000 | 164 | 0 | 3 |
| GPT-5.4 | Qwen3 235B | 167 | 2.4% | 0.000 | 0 | 163 | 0 |
| GPT-5.4 | prompt 5 (gpt-5, Azure) | 167 | 97.6% | 0.000 | 163 | 0 | 4 |
| GPT-5 mini | Qwen3 235B | 167 | 0.6% | 0.000 | 0 | 166 | 0 |
| GPT-5 mini | prompt 5 (gpt-5, Azure) | 167 | 99.4% | 0.000 | 166 | 0 | 1 |
| Qwen3 235B | Grok 4.6 | 167 | 4.8% | 0.000 | 0 | 0 | 159 |
| Qwen3 235B | prompt 5 (gpt-5, Azure) | 167 | 0.0% | 0.000 | 0 | 0 | 167 |
| Qwen3 235B | NER baseline | 167 | 9.6% | 0.000 | 0 | 0 | 151 |
| Grok 4.6 | prompt 5 (gpt-5, Azure) | 167 | 95.2% | 0.000 | 159 | 0 | 8 |
| prompt 5 (gpt-5, Azure) | NER baseline | 167 | 90.4% | 0.000 | 151 | 16 | 0 |
| Llama 4 Maverick | GPT-5 mini | 167 | 97.6% | -0.009 | 163 | 1 | 3 |
| GPT-5 (OpenRouter) | GPT-5 mini | 167 | 97.6% | -0.009 | 163 | 1 | 3 |
| GPT-5.4 | GPT-5 mini | 167 | 97.0% | -0.010 | 162 | 1 | 4 |
| DeepSeek V3.1 | GPT-5 mini | 167 | 95.8% | -0.010 | 160 | 1 | 6 |
| GPT-5 mini | Grok 4.6 | 167 | 94.6% | -0.011 | 158 | 8 | 1 |
| Claude Opus 5 | GPT-5 mini | 167 | 94.0% | -0.011 | 157 | 1 | 9 |
| Claude Sonnet 5 | GPT-5 mini | 167 | 94.0% | -0.011 | 157 | 1 | 9 |
| Claude Haiku 4.5 | GPT-5 mini | 167 | 88.0% | -0.012 | 147 | 1 | 19 |
| Mistral Large | GPT-5 mini | 167 | 79.0% | -0.012 | 132 | 1 | 34 |
| DeepSeek V3.1 | GPT-5 (OpenRouter) | 167 | 94.6% | -0.025 | 158 | 3 | 6 |
| DeepSeek V3.1 | GPT-5.4 | 167 | 94.0% | -0.030 | 157 | 4 | 6 |
| Llama 4 Maverick | NER baseline | 167 | 88.6% | -0.031 | 148 | 16 | 3 |
| GPT-5 (OpenRouter) | NER baseline | 167 | 88.6% | -0.031 | 148 | 16 | 3 |
| GPT-5.4 | NER baseline | 167 | 88.0% | -0.040 | 147 | 16 | 4 |
| DeepSeek V3.1 | NER baseline | 167 | 86.8% | -0.055 | 145 | 16 | 6 |
| Mistral Large | NER baseline | 167 | 72.5% | -0.058 | 119 | 14 | 32 |
| Claude Opus 5 | NER baseline | 167 | 85.0% | -0.074 | 142 | 16 | 9 |
| Claude Sonnet 5 | NER baseline | 167 | 85.0% | -0.074 | 142 | 16 | 9 |

## Pairwise field agreement (F1), on documents where both found an event

| A | B | Hazard | Locations | Locations (fuzzy) | Dates |
|---|---|---:|---:|---:|---:|
| GPT-5 (OpenRouter) | prompt 5 (gpt-5, Azure) | 94.8% | 69.7% | 78.5% | 79.4% |
| GPT-5 (OpenRouter) | Grok 4.6 | 93.9% | 67.3% | 77.9% | 77.4% |
| Claude Haiku 4.5 | Grok 4.6 | 90.8% | 68.5% | 77.7% | 69.5% |
| Claude Haiku 4.5 | DeepSeek V3.1 | 90.0% | 70.3% | 77.2% | 71.3% |
| GPT-5.4 | prompt 5 (gpt-5, Azure) | 94.2% | 66.9% | 75.8% | 77.4% |
| Claude Haiku 4.5 | GPT-5 (OpenRouter) | 92.2% | 67.9% | 75.2% | 71.5% |
| DeepSeek V3.1 | Grok 4.6 | 90.5% | 65.6% | 74.9% | 73.0% |
| Claude Haiku 4.5 | prompt 5 (gpt-5, Azure) | 91.5% | 64.5% | 74.5% | 67.5% |
| Claude Opus 5 | Claude Sonnet 5 | 92.3% | 64.9% | 73.3% | 79.1% |
| Grok 4.6 | prompt 5 (gpt-5, Azure) | 92.4% | 62.4% | 72.9% | 78.4% |
| GPT-5.4 | Grok 4.6 | 93.8% | 62.4% | 72.2% | 80.6% |
| DeepSeek V3.1 | prompt 5 (gpt-5, Azure) | 89.2% | 63.7% | 72.1% | 70.3% |
| Claude Haiku 4.5 | GPT-5.4 | 91.5% | 64.8% | 72.0% | 70.7% |
| Claude Sonnet 5 | Grok 4.6 | 92.8% | 60.0% | 71.4% | 72.0% |
| Claude Haiku 4.5 | Claude Sonnet 5 | 90.7% | 64.2% | 71.4% | 67.5% |
| Claude Opus 5 | Grok 4.6 | 94.7% | 62.1% | 71.3% | 71.0% |
| GPT-5 (OpenRouter) | GPT-5.4 | 94.8% | 65.9% | 71.2% | 77.1% |
| Claude Sonnet 5 | GPT-5 (OpenRouter) | 91.8% | 64.1% | 70.4% | 70.6% |
| DeepSeek V3.1 | GPT-5 (OpenRouter) | 90.5% | 63.4% | 70.4% | 74.7% |
| Claude Sonnet 5 | prompt 5 (gpt-5, Azure) | 92.3% | 60.6% | 70.3% | 69.5% |
| Claude Opus 5 | prompt 5 (gpt-5, Azure) | 93.5% | 61.9% | 70.1% | 69.7% |
| Claude Haiku 4.5 | Claude Opus 5 | 90.6% | 62.4% | 69.0% | 65.1% |
| Claude Opus 5 | GPT-5.4 | 93.1% | 62.4% | 68.7% | 67.7% |
| Claude Sonnet 5 | GPT-5.4 | 91.1% | 62.2% | 68.5% | 68.2% |
| Claude Opus 5 | DeepSeek V3.1 | 90.3% | 61.9% | 67.8% | 70.0% |
| Claude Opus 5 | GPT-5 (OpenRouter) | 93.3% | 58.9% | 67.3% | 70.3% |
| DeepSeek V3.1 | GPT-5.4 | 88.9% | 61.6% | 67.3% | 70.8% |
| Claude Sonnet 5 | DeepSeek V3.1 | 90.0% | 61.5% | 66.9% | 69.1% |
| Llama 4 Maverick | Mistral Large | 91.6% | 56.0% | 63.5% | 62.2% |
| DeepSeek V3.1 | Llama 4 Maverick | 85.9% | 53.8% | 60.3% | 64.2% |
| Claude Opus 5 | Mistral Large | 86.4% | 53.2% | 59.9% | 55.8% |
| Mistral Large | Grok 4.6 | 85.4% | 51.3% | 59.4% | 52.2% |
| Llama 4 Maverick | Grok 4.6 | 83.6% | 50.9% | 58.3% | 61.6% |
| DeepSeek V3.1 | Mistral Large | 86.9% | 52.8% | 58.2% | 54.1% |
| Claude Haiku 4.5 | Llama 4 Maverick | 81.3% | 51.0% | 57.9% | 60.1% |
| Claude Sonnet 5 | Mistral Large | 86.3% | 48.5% | 57.2% | 57.3% |
| Claude Sonnet 5 | Llama 4 Maverick | 84.3% | 47.4% | 56.8% | 63.1% |
| Claude Opus 5 | Llama 4 Maverick | 84.1% | 47.6% | 55.7% | 64.5% |
| Claude Haiku 4.5 | Mistral Large | 81.2% | 48.1% | 55.6% | 49.6% |
| Mistral Large | GPT-5.4 | 82.2% | 46.2% | 54.8% | 48.4% |
| Llama 4 Maverick | GPT-5 (OpenRouter) | 82.4% | 44.4% | 54.2% | 62.7% |
| Mistral Large | prompt 5 (gpt-5, Azure) | 82.5% | 45.0% | 53.0% | 50.3% |
| Claude Sonnet 5 | GPT-5 mini | 91.6% | 36.0% | 52.8% | 65.7% |
| GPT-5 mini | Grok 4.6 | 89.9% | 31.1% | 52.2% | 69.4% |
| Mistral Large | GPT-5 (OpenRouter) | 83.3% | 43.9% | 51.7% | 50.2% |
| Llama 4 Maverick | prompt 5 (gpt-5, Azure) | 80.9% | 42.0% | 51.4% | 59.1% |
| Claude Opus 5 | GPT-5 mini | 91.7% | 32.7% | 51.2% | 64.7% |
| Llama 4 Maverick | GPT-5.4 | 80.7% | 41.5% | 50.6% | 58.3% |
| Llama 4 Maverick | GPT-5 mini | 84.4% | 31.5% | 50.4% | 62.8% |
| DeepSeek V3.1 | GPT-5 mini | 88.4% | 31.6% | 49.0% | 68.9% |
| Claude Haiku 4.5 | GPT-5 mini | 88.1% | 29.0% | 48.0% | 67.3% |
| GPT-5.4 | GPT-5 mini | 88.4% | 33.0% | 47.9% | 69.8% |
| GPT-5 (OpenRouter) | GPT-5 mini | 89.1% | 32.0% | 47.3% | 74.8% |
| Mistral Large | GPT-5 mini | 87.0% | 24.8% | 45.6% | 49.9% |
| GPT-5 mini | prompt 5 (gpt-5, Azure) | 89.8% | 30.5% | 45.1% | 71.5% |
| Llama 4 Maverick | NER baseline | 79.5% | 37.7% | 43.5% | 43.9% |
| Mistral Large | NER baseline | 80.9% | 29.2% | 38.4% | 33.7% |
| GPT-5 mini | NER baseline | 72.3% | 12.0% | 32.2% | 39.6% |
| Grok 4.6 | NER baseline | 74.1% | 25.7% | 31.9% | 40.8% |
| Claude Sonnet 5 | NER baseline | 73.5% | 20.4% | 31.6% | 39.7% |
| DeepSeek V3.1 | NER baseline | 74.0% | 23.4% | 31.4% | 41.0% |
| Claude Opus 5 | NER baseline | 74.4% | 22.4% | 31.3% | 41.0% |
| GPT-5.4 | NER baseline | 72.5% | 19.5% | 29.8% | 39.4% |
| Claude Haiku 4.5 | NER baseline | 69.9% | 22.7% | 29.5% | 37.0% |
| GPT-5 (OpenRouter) | NER baseline | 72.7% | 20.2% | 28.6% | 40.0% |
| prompt 5 (gpt-5, Azure) | NER baseline | 71.0% | 19.9% | 28.3% | 39.5% |
| Claude Haiku 4.5 | Gemini 2.5 Flash | 0.0% | 0.0% | 0.0% | 0.0% |
| Claude Haiku 4.5 | Gemini 2.5 Pro | 0.0% | 0.0% | 0.0% | 0.0% |
| Claude Haiku 4.5 | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Claude Opus 5 | Gemini 2.5 Flash | 0.0% | 0.0% | 0.0% | 0.0% |
| Claude Opus 5 | Gemini 2.5 Pro | 0.0% | 0.0% | 0.0% | 0.0% |
| Claude Opus 5 | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Claude Sonnet 5 | Gemini 2.5 Flash | 0.0% | 0.0% | 0.0% | 0.0% |
| Claude Sonnet 5 | Gemini 2.5 Pro | 0.0% | 0.0% | 0.0% | 0.0% |
| Claude Sonnet 5 | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| DeepSeek V3.1 | Gemini 2.5 Flash | 0.0% | 0.0% | 0.0% | 0.0% |
| DeepSeek V3.1 | Gemini 2.5 Pro | 0.0% | 0.0% | 0.0% | 0.0% |
| DeepSeek V3.1 | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Flash | Gemini 2.5 Pro | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Flash | Llama 4 Maverick | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Flash | Mistral Large | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Flash | GPT-5 (OpenRouter) | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Flash | GPT-5.4 | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Flash | GPT-5 mini | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Flash | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Flash | Grok 4.6 | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Flash | prompt 5 (gpt-5, Azure) | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Flash | NER baseline | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | Llama 4 Maverick | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | Mistral Large | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | GPT-5 (OpenRouter) | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | GPT-5.4 | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | GPT-5 mini | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | Grok 4.6 | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | prompt 5 (gpt-5, Azure) | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | NER baseline | 0.0% | 0.0% | 0.0% | 0.0% |
| Llama 4 Maverick | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Mistral Large | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| GPT-5 (OpenRouter) | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| GPT-5.4 | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| GPT-5 mini | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Qwen3 235B | Grok 4.6 | 0.0% | 0.0% | 0.0% | 0.0% |
| Qwen3 235B | prompt 5 (gpt-5, Azure) | 0.0% | 0.0% | 0.0% | 0.0% |
| Qwen3 235B | NER baseline | 0.0% | 0.0% | 0.0% | 0.0% |

## Where to annotate next

167 of 167 documents split the roster on whether they carry a verifiable event. Those are where a human judgement is worth the most, ranked in `benchmark_openrouter/outputs/disagreement_queue.csv`.
