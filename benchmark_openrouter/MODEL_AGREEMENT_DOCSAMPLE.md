# Prompt 5 across models — agreement, not accuracy

12 runs over 50 shared documents (the human annotation queue's set).

> Every figure on this page is **agreement between models**. None of it is accuracy — there is no ground truth here. Two models can be wrong in the same way, and on prompt 5's location rules that is the likely failure mode. For accuracy see `MODEL_SCORES.md`.

> **The document set is not neutral.** These 167 documents are the ones behind the review queue, and that queue was built from events the prompt-5 / gpt-5 production run itself emitted. So that arm finds an event in 100% of them *by construction*, and every other model's detection rate is being measured against a set selected in gpt-5's favour. It says how well a model reproduces gpt-5's finds, not how well it does on the corpus. Only the human annotations settle which of them was right.

## Behaviour per model

| Model | Covered | Docs w/ event | Events | Ev/doc | Loc/ev | Errors | Mode | Cost $ | Min |
|---|---:|---|---:|---:|---:|---:|---|---:|---:|
| Claude Opus 5 | 50 | 24.0% (14.3%–37.4%, n=50) | 20 | 0.40 | 1.95 | 0 | json_schema | 2.55 | 1 |
| Claude Sonnet 5 | 50 | 26.0% (15.9%–39.6%, n=50) | 23 | 0.46 | 1.87 | 0 | json_schema | 1.06 | 1 |
| DeepSeek V3.1 | 50 | 14.0% (7.0%–26.2%, n=50) | 12 | 0.24 | 1.08 | 18 | json_object, json_schema | 0.09 | 9 |
| Gemini 2.5 Pro | 50 | 0.0% (0.0%–7.1%, n=50) | 0 | 0.00 | 0.00 | 50 | none | 0.00 | 0 |
| Llama 4 Maverick | 50 | 38.0% (25.9%–51.8%, n=50) | 44 | 0.88 | 1.36 | 0 | json_schema | 0.05 | 4 |
| Mistral Large | 50 | 32.0% (20.8%–45.8%, n=50) | 34 | 0.68 | 3.06 | 0 | json_schema | 0.10 | 1 |
| GPT-5 (OpenRouter) | 50 | 24.0% (14.3%–37.4%, n=50) | 20 | 0.40 | 1.50 | 0 | json_schema | 0.95 | 6 |
| GPT-5.4 | 50 | 24.0% (14.3%–37.4%, n=50) | 23 | 0.46 | 1.30 | 0 | json_schema | 1.19 | 2 |
| Qwen3 235B | 50 | 0.0% (0.0%–7.1%, n=50) | 0 | 0.00 | 0.00 | 50 | none | 0.00 | 9 |
| Grok 4.6 | 50 | 28.0% (17.5%–41.7%, n=50) | 23 | 0.46 | 1.78 | 0 | json_schema | 1.01 | 6 |
| prompt 5 (gpt-5, Azure) | 50 | 22.0% (12.8%–35.2%, n=50) | 19 | 0.38 | 1.21 | — | — | — | — |
| NER baseline | 50 | 42.0% (29.4%–55.8%, n=50) | 38 | 0.76 | 4.21 | — | — | — | — |

## Location granularity — did the sub-national rule land?

Prompt 5 forbids a bare country for sub-national hazards. A high `country` share is a model ignoring that rule; a high `unknown` share is a model unable to self-tag. Neither needs gold to read.

| Model | Sub-national | country | unknown |
|---|---:|---:|---:|
| Claude Opus 5 | 97.4% | 0.0% | 2.6% |
| Claude Sonnet 5 | 90.7% | 7.0% | 2.3% |
| DeepSeek V3.1 | 100.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | 0.0% | 0.0% | 0.0% |
| Llama 4 Maverick | 51.7% | 46.7% | 1.7% |
| Mistral Large | 62.5% | 34.6% | 2.9% |
| GPT-5 (OpenRouter) | 96.7% | 0.0% | 3.3% |
| GPT-5.4 | 93.3% | 0.0% | 6.7% |
| Qwen3 235B | 0.0% | 0.0% | 0.0% |
| Grok 4.6 | 92.7% | 4.9% | 2.4% |
| prompt 5 (gpt-5, Azure) | 100.0% | 0.0% | 0.0% |
| NER baseline | 38.1% | 24.4% | 37.5% |

## Hazard families found, per model

| Model | cyclone | drought | earthquake | flood | heat | other | volcano | wildfire |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude Opus 5 | 3 | 0 | 7 | 2 | 1 | 2 | 1 | 0 |
| Claude Sonnet 5 | 4 | 0 | 8 | 0 | 1 | 2 | 1 | 0 |
| DeepSeek V3.1 | 2 | 0 | 4 | 1 | 1 | 2 | 1 | 0 |
| Gemini 2.5 Pro | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Llama 4 Maverick | 5 | 1 | 9 | 4 | 1 | 5 | 1 | 0 |
| Mistral Large | 5 | 2 | 6 | 2 | 1 | 5 | 1 | 1 |
| GPT-5 (OpenRouter) | 3 | 0 | 7 | 2 | 1 | 2 | 1 | 0 |
| GPT-5.4 | 4 | 0 | 7 | 2 | 1 | 2 | 1 | 0 |
| Qwen3 235B | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Grok 4.6 | 3 | 0 | 7 | 4 | 1 | 3 | 1 | 0 |
| prompt 5 (gpt-5, Azure) | 4 | 0 | 6 | 1 | 0 | 2 | 1 | 0 |
| NER baseline | 8 | 5 | 10 | 9 | 2 | 6 | 2 | 1 |

## Pairwise agreement on event detection

κ corrects for chance: most documents yield no event, so raw agreement is high by default and only κ says whether two models agree for a reason. κ is 0 when one run flags everything — there are then no true negatives for chance agreement to be corrected against, which is exactly the case for the gpt-5 arm on this selected set.

| A | B | n | Agreement | κ | Both | A only | B only |
|---|---|---:|---:|---:|---:|---:|---:|
| GPT-5 (OpenRouter) | GPT-5.4 | 50 | 100.0% | 1.000 | 12 | 0 | 0 |
| Claude Opus 5 | Claude Sonnet 5 | 50 | 98.0% | 0.947 | 12 | 0 | 1 |
| GPT-5 (OpenRouter) | prompt 5 (gpt-5, Azure) | 50 | 98.0% | 0.944 | 11 | 1 | 0 |
| GPT-5.4 | prompt 5 (gpt-5, Azure) | 50 | 98.0% | 0.944 | 11 | 1 | 0 |
| GPT-5 (OpenRouter) | Grok 4.6 | 50 | 96.0% | 0.896 | 12 | 0 | 2 |
| GPT-5.4 | Grok 4.6 | 50 | 96.0% | 0.896 | 12 | 0 | 2 |
| Claude Opus 5 | GPT-5 (OpenRouter) | 50 | 96.0% | 0.890 | 11 | 1 | 1 |
| Claude Opus 5 | GPT-5.4 | 50 | 96.0% | 0.890 | 11 | 1 | 1 |
| Grok 4.6 | prompt 5 (gpt-5, Azure) | 50 | 94.0% | 0.841 | 11 | 3 | 0 |
| Claude Sonnet 5 | GPT-5 (OpenRouter) | 50 | 94.0% | 0.840 | 11 | 2 | 1 |
| Claude Sonnet 5 | GPT-5.4 | 50 | 94.0% | 0.840 | 11 | 2 | 1 |
| Claude Opus 5 | prompt 5 (gpt-5, Azure) | 50 | 94.0% | 0.831 | 10 | 2 | 1 |
| Claude Opus 5 | Grok 4.6 | 50 | 92.0% | 0.793 | 11 | 1 | 3 |
| Claude Sonnet 5 | prompt 5 (gpt-5, Azure) | 50 | 92.0% | 0.781 | 10 | 3 | 1 |
| Llama 4 Maverick | Grok 4.6 | 50 | 90.0% | 0.776 | 14 | 5 | 0 |
| Claude Sonnet 5 | Grok 4.6 | 50 | 90.0% | 0.746 | 11 | 2 | 3 |
| Claude Sonnet 5 | Llama 4 Maverick | 50 | 88.0% | 0.729 | 13 | 0 | 6 |
| DeepSeek V3.1 | GPT-5 (OpenRouter) | 50 | 90.0% | 0.680 | 7 | 0 | 5 |
| DeepSeek V3.1 | GPT-5.4 | 50 | 90.0% | 0.680 | 7 | 0 | 5 |
| Claude Opus 5 | Llama 4 Maverick | 50 | 86.0% | 0.680 | 12 | 0 | 7 |
| Llama 4 Maverick | GPT-5 (OpenRouter) | 50 | 86.0% | 0.680 | 12 | 7 | 0 |
| Llama 4 Maverick | GPT-5.4 | 50 | 86.0% | 0.680 | 12 | 7 | 0 |
| Llama 4 Maverick | prompt 5 (gpt-5, Azure) | 50 | 84.0% | 0.630 | 11 | 8 | 0 |
| Llama 4 Maverick | Mistral Large | 50 | 82.0% | 0.606 | 13 | 6 | 3 |
| DeepSeek V3.1 | prompt 5 (gpt-5, Azure) | 50 | 88.0% | 0.598 | 6 | 1 | 5 |
| DeepSeek V3.1 | Grok 4.6 | 50 | 86.0% | 0.590 | 7 | 0 | 7 |
| Llama 4 Maverick | NER baseline | 50 | 80.0% | 0.584 | 15 | 4 | 6 |
| Claude Sonnet 5 | Mistral Large | 50 | 82.0% | 0.565 | 10 | 3 | 6 |
| Claude Opus 5 | DeepSeek V3.1 | 50 | 86.0% | 0.552 | 6 | 6 | 1 |
| Mistral Large | prompt 5 (gpt-5, Azure) | 50 | 82.0% | 0.549 | 9 | 7 | 2 |
| Grok 4.6 | NER baseline | 50 | 78.0% | 0.527 | 12 | 2 | 9 |
| Mistral Large | Grok 4.6 | 50 | 80.0% | 0.525 | 10 | 6 | 4 |
| Claude Sonnet 5 | DeepSeek V3.1 | 50 | 84.0% | 0.511 | 6 | 7 | 1 |
| Claude Opus 5 | Mistral Large | 50 | 80.0% | 0.508 | 9 | 3 | 7 |
| Mistral Large | GPT-5 (OpenRouter) | 50 | 80.0% | 0.508 | 9 | 7 | 3 |
| Mistral Large | GPT-5.4 | 50 | 80.0% | 0.508 | 9 | 7 | 3 |
| GPT-5 (OpenRouter) | NER baseline | 50 | 74.0% | 0.433 | 10 | 2 | 11 |
| GPT-5.4 | NER baseline | 50 | 74.0% | 0.433 | 10 | 2 | 11 |
| DeepSeek V3.1 | Llama 4 Maverick | 50 | 76.0% | 0.420 | 7 | 0 | 12 |
| Claude Sonnet 5 | NER baseline | 50 | 72.0% | 0.393 | 10 | 3 | 11 |
| prompt 5 (gpt-5, Azure) | NER baseline | 50 | 72.0% | 0.385 | 9 | 2 | 12 |
| Mistral Large | NER baseline | 50 | 70.0% | 0.363 | 11 | 5 | 10 |
| Claude Opus 5 | NER baseline | 50 | 70.0% | 0.346 | 9 | 3 | 12 |
| DeepSeek V3.1 | Mistral Large | 50 | 74.0% | 0.298 | 5 | 2 | 11 |
| DeepSeek V3.1 | NER baseline | 50 | 64.0% | 0.186 | 5 | 2 | 16 |
| Claude Opus 5 | Gemini 2.5 Pro | 50 | 76.0% | 0.000 | 0 | 12 | 0 |
| Claude Opus 5 | Qwen3 235B | 50 | 76.0% | 0.000 | 0 | 12 | 0 |
| Claude Sonnet 5 | Gemini 2.5 Pro | 50 | 74.0% | 0.000 | 0 | 13 | 0 |
| Claude Sonnet 5 | Qwen3 235B | 50 | 74.0% | 0.000 | 0 | 13 | 0 |
| DeepSeek V3.1 | Gemini 2.5 Pro | 50 | 86.0% | 0.000 | 0 | 7 | 0 |
| DeepSeek V3.1 | Qwen3 235B | 50 | 86.0% | 0.000 | 0 | 7 | 0 |
| Gemini 2.5 Pro | Llama 4 Maverick | 50 | 62.0% | 0.000 | 0 | 0 | 19 |
| Gemini 2.5 Pro | Mistral Large | 50 | 68.0% | 0.000 | 0 | 0 | 16 |
| Gemini 2.5 Pro | GPT-5 (OpenRouter) | 50 | 76.0% | 0.000 | 0 | 0 | 12 |
| Gemini 2.5 Pro | GPT-5.4 | 50 | 76.0% | 0.000 | 0 | 0 | 12 |
| Gemini 2.5 Pro | Qwen3 235B | 50 | 100.0% | 0.000 | 0 | 0 | 0 |
| Gemini 2.5 Pro | Grok 4.6 | 50 | 72.0% | 0.000 | 0 | 0 | 14 |
| Gemini 2.5 Pro | prompt 5 (gpt-5, Azure) | 50 | 78.0% | 0.000 | 0 | 0 | 11 |
| Gemini 2.5 Pro | NER baseline | 50 | 58.0% | 0.000 | 0 | 0 | 21 |
| Llama 4 Maverick | Qwen3 235B | 50 | 62.0% | 0.000 | 0 | 19 | 0 |
| Mistral Large | Qwen3 235B | 50 | 68.0% | 0.000 | 0 | 16 | 0 |
| GPT-5 (OpenRouter) | Qwen3 235B | 50 | 76.0% | 0.000 | 0 | 12 | 0 |
| GPT-5.4 | Qwen3 235B | 50 | 76.0% | 0.000 | 0 | 12 | 0 |
| Qwen3 235B | Grok 4.6 | 50 | 72.0% | 0.000 | 0 | 0 | 14 |
| Qwen3 235B | prompt 5 (gpt-5, Azure) | 50 | 78.0% | 0.000 | 0 | 0 | 11 |
| Qwen3 235B | NER baseline | 50 | 58.0% | 0.000 | 0 | 0 | 21 |

## Pairwise field agreement (F1), on documents where both found an event

| A | B | Hazard | Locations | Locations (fuzzy) | Dates |
|---|---|---:|---:|---:|---:|
| Claude Opus 5 | Grok 4.6 | 96.8% | 70.4% | 95.8% | 73.2% |
| DeepSeek V3.1 | prompt 5 (gpt-5, Azure) | 94.7% | 61.5% | 92.3% | 90.9% |
| GPT-5 (OpenRouter) | Grok 4.6 | 97.0% | 40.6% | 84.4% | 78.0% |
| DeepSeek V3.1 | GPT-5.4 | 95.7% | 38.7% | 83.9% | 71.4% |
| GPT-5 (OpenRouter) | GPT-5.4 | 97.0% | 50.0% | 82.1% | 74.4% |
| GPT-5.4 | prompt 5 (gpt-5, Azure) | 93.3% | 60.0% | 80.0% | 80.0% |
| DeepSeek V3.1 | GPT-5 (OpenRouter) | 90.9% | 42.9% | 78.6% | 64.0% |
| DeepSeek V3.1 | Grok 4.6 | 90.9% | 42.9% | 78.6% | 72.0% |
| Claude Sonnet 5 | Grok 4.6 | 93.3% | 60.3% | 76.7% | 60.5% |
| Claude Opus 5 | Claude Sonnet 5 | 90.3% | 73.7% | 76.3% | 73.9% |
| GPT-5.4 | Grok 4.6 | 94.1% | 62.5% | 75.0% | 72.7% |
| Claude Opus 5 | GPT-5 (OpenRouter) | 93.3% | 28.6% | 73.0% | 70.0% |
| Grok 4.6 | prompt 5 (gpt-5, Azure) | 86.7% | 55.2% | 72.4% | 71.8% |
| GPT-5 (OpenRouter) | prompt 5 (gpt-5, Azure) | 89.7% | 48.0% | 72.0% | 78.9% |
| Claude Opus 5 | DeepSeek V3.1 | 84.2% | 53.8% | 69.2% | 52.2% |
| Claude Opus 5 | GPT-5.4 | 90.3% | 38.1% | 66.7% | 74.4% |
| Claude Sonnet 5 | GPT-5 (OpenRouter) | 96.6% | 21.5% | 64.6% | 61.9% |
| Claude Sonnet 5 | Mistral Large | 88.9% | 55.8% | 62.8% | 62.9% |
| Claude Opus 5 | Mistral Large | 80.0% | 58.5% | 61.0% | 46.7% |
| Claude Opus 5 | prompt 5 (gpt-5, Azure) | 88.9% | 38.6% | 59.6% | 63.2% |
| Claude Sonnet 5 | DeepSeek V3.1 | 94.7% | 35.7% | 57.1% | 50.0% |
| Llama 4 Maverick | GPT-5 (OpenRouter) | 74.3% | 30.6% | 55.6% | 63.8% |
| Llama 4 Maverick | GPT-5.4 | 72.2% | 36.1% | 55.6% | 60.0% |
| Mistral Large | Grok 4.6 | 78.6% | 51.1% | 55.6% | 32.3% |
| Claude Sonnet 5 | GPT-5.4 | 93.3% | 36.9% | 55.4% | 57.8% |
| Claude Sonnet 5 | Llama 4 Maverick | 82.4% | 38.1% | 52.4% | 61.8% |
| Claude Opus 5 | NER baseline | 68.7% | 40.4% | 51.9% | 50.0% |
| Claude Sonnet 5 | prompt 5 (gpt-5, Azure) | 92.3% | 30.5% | 50.8% | 55.0% |
| DeepSeek V3.1 | NER baseline | 70.0% | 25.0% | 50.0% | 48.3% |
| Llama 4 Maverick | Grok 4.6 | 75.0% | 36.4% | 47.7% | 47.5% |
| Claude Sonnet 5 | NER baseline | 64.7% | 34.9% | 47.7% | 35.5% |
| Claude Opus 5 | Llama 4 Maverick | 78.8% | 37.5% | 47.5% | 65.3% |
| Llama 4 Maverick | prompt 5 (gpt-5, Azure) | 75.0% | 30.3% | 45.5% | 57.8% |
| Grok 4.6 | NER baseline | 68.2% | 32.1% | 43.8% | 30.6% |
| GPT-5.4 | NER baseline | 70.3% | 23.8% | 43.6% | 46.7% |
| GPT-5 (OpenRouter) | NER baseline | 66.7% | 17.6% | 43.1% | 38.6% |
| Mistral Large | NER baseline | 70.6% | 33.1% | 42.1% | 21.4% |
| DeepSeek V3.1 | Llama 4 Maverick | 66.7% | 26.7% | 40.0% | 51.6% |
| Mistral Large | GPT-5 (OpenRouter) | 80.0% | 15.8% | 39.5% | 34.5% |
| prompt 5 (gpt-5, Azure) | NER baseline | 68.8% | 23.2% | 37.9% | 47.3% |
| Mistral Large | GPT-5.4 | 76.9% | 26.7% | 34.7% | 33.3% |
| Llama 4 Maverick | NER baseline | 62.7% | 27.2% | 32.1% | 35.6% |
| Llama 4 Maverick | Mistral Large | 89.5% | 29.6% | 31.5% | 63.8% |
| Mistral Large | prompt 5 (gpt-5, Azure) | 72.0% | 21.9% | 30.1% | 32.3% |
| DeepSeek V3.1 | Mistral Large | 66.7% | 19.5% | 24.4% | 40.0% |
| Claude Opus 5 | Gemini 2.5 Pro | 0.0% | 0.0% | 0.0% | 0.0% |
| Claude Opus 5 | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Claude Sonnet 5 | Gemini 2.5 Pro | 0.0% | 0.0% | 0.0% | 0.0% |
| Claude Sonnet 5 | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| DeepSeek V3.1 | Gemini 2.5 Pro | 0.0% | 0.0% | 0.0% | 0.0% |
| DeepSeek V3.1 | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | Llama 4 Maverick | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | Mistral Large | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | GPT-5 (OpenRouter) | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | GPT-5.4 | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | Grok 4.6 | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | prompt 5 (gpt-5, Azure) | 0.0% | 0.0% | 0.0% | 0.0% |
| Gemini 2.5 Pro | NER baseline | 0.0% | 0.0% | 0.0% | 0.0% |
| Llama 4 Maverick | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Mistral Large | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| GPT-5 (OpenRouter) | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| GPT-5.4 | Qwen3 235B | 0.0% | 0.0% | 0.0% | 0.0% |
| Qwen3 235B | Grok 4.6 | 0.0% | 0.0% | 0.0% | 0.0% |
| Qwen3 235B | prompt 5 (gpt-5, Azure) | 0.0% | 0.0% | 0.0% | 0.0% |
| Qwen3 235B | NER baseline | 0.0% | 0.0% | 0.0% | 0.0% |

## Where to annotate next

26 of 50 documents split the roster on whether they carry a verifiable event. Those are where a human judgement is worth the most, ranked in `benchmark_openrouter/outputs_docsample/disagreement_queue.csv`.
