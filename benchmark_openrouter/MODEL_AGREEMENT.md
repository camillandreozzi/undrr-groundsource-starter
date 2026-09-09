# Prompt 5 across models — agreement, not accuracy

3 runs over 167 shared documents (the human annotation queue's set).

> Every figure on this page is **agreement between models**. None of it is accuracy — there is no ground truth here. Two models can be wrong in the same way, and on prompt 5's location rules that is the likely failure mode. For accuracy see `MODEL_SCORES.md`.

> **The document set is not neutral.** These 167 documents are the ones behind the review queue, and that queue was built from events the prompt-5 / gpt-5 production run itself emitted. So that arm finds an event in 100% of them *by construction*, and every other model's detection rate is being measured against a set selected in gpt-5's favour. It says how well a model reproduces gpt-5's finds, not how well it does on the corpus. Only the human annotations settle which of them was right.

> **Incomplete runs.** Llama 4 Maverick covered 3/167. Their rates are over what they attempted, and pairwise rows use only documents both runs attempted — but small coverage means wide uncertainty. Finish them with `--resume`.

## Behaviour per model

| Model | Covered | Docs w/ event | Events | Ev/doc | Loc/ev | Errors | Mode | Cost $ | Min |
|---|---:|---|---:|---:|---:|---:|---|---:|---:|
| Llama 4 Maverick | **3**/167 | 100.0% (43.9%–100.0%, n=3) | 9 | 3.00 | 1.67 | 0 | json_schema | 0.01 | 0 |
| prompt 5 (gpt-5, Azure) | 167 | 100.0% (97.8%–100.0%, n=167) | 572 | 3.43 | 1.52 | — | — | — | — |
| NER baseline | 167 | 90.4% (85.0%–94.0%, n=167) | 343 | 2.05 | 4.84 | — | — | — | — |

## Location granularity — did the sub-national rule land?

Prompt 5 forbids a bare country for sub-national hazards. A high `country` share is a model ignoring that rule; a high `unknown` share is a model unable to self-tag. Neither needs gold to read.

| Model | Sub-national | country | unknown |
|---|---:|---:|---:|
| Llama 4 Maverick | 33.3% | 26.7% | 40.0% |
| prompt 5 (gpt-5, Azure) | 89.1% | 4.7% | 6.2% |
| NER baseline | 24.7% | 34.2% | 41.1% |

## Hazard families found, per model

| Model | cyclone | drought | earthquake | flood | heat | landslide | other | volcano | wildfire |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Llama 4 Maverick | 1 | 2 | 1 | 2 | 1 | 0 | 0 | 0 | 0 |
| prompt 5 (gpt-5, Azure) | 40 | 17 | 82 | 62 | 7 | 15 | 29 | 15 | 12 |
| NER baseline | 60 | 34 | 84 | 82 | 10 | 29 | 37 | 20 | 19 |

## Pairwise agreement on event detection

κ corrects for chance: most documents yield no event, so raw agreement is high by default and only κ says whether two models agree for a reason. κ is 0 when one run flags everything — there are then no true negatives for chance agreement to be corrected against, which is exactly the case for the gpt-5 arm on this selected set.

| A | B | n | Agreement | κ | Both | A only | B only |
|---|---|---:|---:|---:|---:|---:|---:|
| Llama 4 Maverick | prompt 5 (gpt-5, Azure) | 3 | 100.0% | 0.000 | 3 | 0 | 0 |
| Llama 4 Maverick | NER baseline | 3 | 100.0% | 0.000 | 3 | 0 | 0 |
| prompt 5 (gpt-5, Azure) | NER baseline | 167 | 90.4% | 0.000 | 151 | 16 | 0 |

## Pairwise field agreement (F1), on documents where both found an event

| A | B | Hazard | Locations | Locations (fuzzy) | Dates |
|---|---|---:|---:|---:|---:|
| Llama 4 Maverick | prompt 5 (gpt-5, Azure) | 83.3% | 52.6% | 52.6% | 66.7% |
| Llama 4 Maverick | NER baseline | 80.0% | 35.9% | 41.0% | 18.2% |
| prompt 5 (gpt-5, Azure) | NER baseline | 71.0% | 19.9% | 28.3% | 39.5% |

## Where to annotate next

16 of 167 documents split the roster on whether they carry a verifiable event. Those are where a human judgement is worth the most, ranked in `benchmark_openrouter/outputs/disagreement_queue.csv`.
