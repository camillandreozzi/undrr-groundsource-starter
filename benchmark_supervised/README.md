# Supervised event extractor — a trained, non-LLM baseline

## Why this exists

Experiment A (`eval/EVENT_LEVEL_SCORES.md`) scores complete event records:
hazard, year and places that belong to the same occurrence. Its only non-LLM
system is the NER baseline (`benchmark_ner/`): spaCy `en_core_web_lg` and a
hazard regex, assembled by a ±1-sentence heuristic. It reaches 1.9%
complete-record correctness. That is weak enough to be called a strawman: it
has no learned component, so it cannot tell a reported occurrence from a
generic mention, and it cannot tell which place and year go with which hazard.

This folder adds the standard stronger alternative, a **supervised event
extractor**. It has a transformer NER and classifiers trained on human
event-level labels for each decision the heuristic got wrong. It is scored on
the same 45 windows, by the same scorer, beside every other system.

## Architecture

A pipeline of maximum-entropy classifiers in the style of Ahn (2006), *The
stages of event extraction*: trigger detection, then argument identification,
then event coreference. The candidates and features are classic
feature-engineered event-extraction templates. No LLM is used to train or run
it.

```
window text (first 12,000 chars, whitespace-normalised)
  │
  ├─ spaCy en_core_web_trf ── tokens, sentences, dependency parse, morphology, NER
  ├─ spaCy en_core_web_lg  ── NER (second opinion)
  └─ hazard lexicon        ── trigger candidates (prompt 5's PreventionWeb vocabulary)
  │
  ├─ [1] trigger classifier   P(mention reports a concrete occurrence)    > 0.5 kept
  ├─ [2] coref classifier     P(two kept mentions = same occurrence)      average-linkage clustering, cut at 0.5
  ├─ [3] year classifier      P(year ∈ event's span | event's mentions)   > 0.5 kept
  └─ [4] place classifier     P(place directly affected | mentions)       > 0.5 kept, ≤ 10
  │
  └─ record = cluster with ≥ 1 year and ≥ 1 place (prompt 5's verifiability bar);
     evidence = the trigger sentences, verbatim
```

### NER models

| | `en_core_web_trf` 3.8.0 (primary) | `en_core_web_lg` 3.8.0 (secondary) |
|---|---|---|
| Encoder | RoBERTa-base (transformer, via `spacy-curated-transformers` 0.3.0, torch 2.15.0) | CNN tok2vec + static word vectors |
| Training corpus | OntoNotes 5.0 (NER, tagger), ClearNLP dependency conversion (parser) | same |
| NER P / R / F1 (OntoNotes, all 18 types) | 0.897 / 0.901 / **0.899** | 0.855 F1 |
| GPE F1 | 0.949 | 0.915 |
| LOC F1 | 0.833 | 0.666 |
| FAC F1 | 0.682 | 0.347 |
| DATE F1 | 0.897 | 0.874 |
| Also used | dependency parse (LAS 0.938), sentence boundaries (F1 0.886), past-tense morphology | entities only |

The figures are the models' own evaluation scores (`nlp.meta["performance"]`).
OntoNotes labels used: **GPE** (countries, cities, states), **LOC** (non-GPE
places such as regions, seas and rivers) and **FAC** (named facilities) as place
candidates. **DATE** is used as context for year mentions. Place-candidate
recall against the gold locations is 87.3% with `lg` alone, 95.6% with `trf`
alone and 97.5% with both. Which model found a candidate is a feature, not a
filter.

### Candidates (fixed, not learned)

| Candidate | Source | Ceiling on the gold |
|---|---|---|
| Trigger | `benchmark_ner.hazard_lexicon`, unchanged: the label vocabulary prompt 5 was given | 141 / 170 verifiable events (82.9%) have one in their support quotes |
| Year | four-digit 1900–2035, not inside a longer number, not a decade | 179 / 182 gold year endpoints |
| Place | GPE/LOC/FAC from either model, `benchmark_ner.ner_extract.clean_location` | 268 / 275 gold locations (97.5%) |

The lexicon was deliberately **not** extended. The missed events are in tables
("2008 - FF in Hazrat Sultan district") or use words outside the vocabulary
("Camp Fire", "rainstorm"). Writing rules after reading them would leak the test
set into a cross-validated model.

### Features (`features.py`)

- **Trigger:** hazard label, surface form, plural, previous/next words,
  bag of words within ±15 tokens, sentence distance to the nearest year and
  place, past-tense verb and modal in the sentence, digits, impact words,
  position, and how many triggers and labels the window has.
- **Coreference:** same label or family, the hazard-family pair, sentence and
  character distance, the anaphor cue before the second mention, and whether
  the two sentences (±1) share or contradict years and places. Also counts the
  years, triggers and other hazard families between the two mentions.
- **Argument (year/place given an event):** the closest
  mention pair's sentence and character distance, direction, and
  dependency-path length. Also the mention count, rank among same-kind
  candidates by distance, whether this event is the nearest event to the
  candidate, intervening triggers and candidates, and previous/next words.
  - Years add: inside an NER DATE, part of a range, after 2026, latest in the
    window.
  - Places add: NER label, which model(s) found it, country (pycountry),
    administrative word, token count.

### Learning

Every classifier is L2 logistic regression: scikit-learn 1.9, lbfgs, `C = 1`,
`DictVectorizer` features, max-abs scaled. There is one threshold, 0.5,
everywhere. **No hyperparameter was tuned.** The gold is the only labelled
data, so any tuning would be tuning on the test set.

**Labels** come from Experiment A's blind gold only (`eval/event_level_gold.csv`):

- A trigger is positive when it sits inside an event's support quotes, or in
  the surrounding sentence and naming that event's hazard.
- Coreference pairs: same gold event or not.
- A year is positive when it lies inside the event's span.
- A place is positive when it matches one of the event's gold locations under
  the scorer's own rule (`event_matching._loc_match`).

Gold support spans index the matcher's casefolded "hay". `Doc.to_hay` maps
parse offsets onto it, because PDF ligatures (ﬁ → fi) lengthen the text when
casefolded; 7 of the 45 windows contain them.

## Evaluation protocol

- **Same test set as every other system.** Experiment A's 45 windows (170
  verifiable gold events), scored by `eval/score_event_level.py` unchanged:
  same matcher, field rules and cluster bootstrap. Re-running it reproduces
  every existing row of `eval/EVENT_LEVEL_SCORES.md` exactly.
- **Cross-validated, so no window predicts itself.**
  - Primary: leave-one-window-out. Each window is predicted by a model
    trained on the other 44. Deterministic; there is no seed anywhere.
  - Sensitivity: 5-fold over windows with seeds 48, 49 and 50, each model
    trained on about 36 windows.
- **Frozen before scoring.** `FROZEN.json` holds the code hashes,
  hyperparameters, NER model versions and the gold sha256, written at
  2026-11-04 07:20 UTC. The runner refuses to write a scored run that differs
  from it. The in-sample (resubstitution) wiring check goes to `runs_smoke/`,
  is git-ignored and is never a result.

## Results

From `SUPERVISED_SCORES.md` (§2, §4, §9, §12, §13). Complete-record
correctness (CRC) is complete records over all records, with 95% cluster
bootstrap intervals.

| System | Records | Detection P | Detection R | Detection F1 | CRC (95% CI) | Complete-record recall |
|---|---:|---:|---:|---:|---|---:|
| prompt 5 (GPT-5) | 113 | 82.3% | 54.1% | 65.3% | 60.2% (50.0–70.8) | 39.4% |
| NER baseline | 106 | 69.8% | 43.5% | 53.6% | 1.9% (0.0–5.0) | 1.2% |
| **Supervised (LOWO)** | 86 | 64.0% | 32.4% | 43.0% | **22.1% (14.3–29.4)** | 11.2% |
| Supervised (5-fold ×3 seeds) | 67–70 | 64.3–68.7% | 26.5–28.2% | – | 20.0–32.8% | 8.2–12.9% |

| Paired difference in CRC (LOWO) | All windows | Single-event | Multi-event |
|---|---|---|---|
| vs NER baseline | **+20.2 pp (+12.1 to +27.3)** | +20.9 pp (+0.0 to +40.9) | +20.4 pp (+11.9 to +28.0) |
| vs prompt 5 | **−38.1 pp (−50.7 to −26.9)** | −12.6 pp (−58.3 to +30.0) | −42.7 pp (−55.1 to −31.4) |

All three sensitivity runs also beat the NER baseline: +18.1 to +30.9 pp, every
interval excluding zero.

**Field agreement on matched events** (hazard / year / location / all three):

| System | Hazard | Year | Location | All three |
|---|---:|---:|---:|---:|
| prompt 5 | 92.5% | 98.9% | 79.6% | 73.1% |
| Supervised (LOWO) | 80.0% | 74.5% | 47.3% | 34.5% |
| NER baseline | 45.9% | 27.0% | 6.8% | 2.7% |

### Reading it

1. **Supervision fixes much of the association problem.** On matched events,
   records with all three fields right go from 2.7% (NER heuristic) to 34.5%.
   Complete-record correctness goes from 1.9% to 22.1%. The difference is
   significant in every run.
2. **It still falls far short of prompt 5, mainly on recall.** The losses are
   counted down the pipeline in §13:
   - 141 of 170 gold events have a trigger candidate.
   - The trigger classifier keeps 65 of them.
   - 53 are inside an emitted record.

   With about 230 positive trigger mentions to learn from, the trigger
   classifier is conservative at the fixed 0.5 threshold. Even when it
   matches, it gets the location right much less often than prompt 5 (47.3%
   vs 79.6%).
3. **The comparison is generous to the supervised model.** It was trained on
   the same annotator's labels it is scored against, in the same domain.
   Every LLM ran zero-shot from prompt 5.
4. **It is noisy.** The spread across the 5-fold seeds (20.0–32.8% CRC) is as
   large as the LOWO interval. 44 training windows (LOWO) do no better than
   36 (5-fold), so these runs cannot show whether more labelled data would
   close the gap.

## Limits

- **Training data.** 44 windows per LOWO model (about 230 positive trigger
  mentions, 130 coreferent pairs, 150 year and 300 place positives). That is
  small for supervised IE. It is the human event-level annotation that exists;
  no LLM output was used as silver labels, which would make this an LLM-derived
  baseline.
- **Trigger ceiling.** 17% of gold events have no lexicon trigger and are
  unreachable by construction.
- **Not tuned.** A tuned threshold (for example, chosen by nested
  cross-validation) could raise recall. It was not done because it was not
  pre-specified. If added, it must be reported as post hoc.
- **Inherited from Experiment A.** One annotator, English only, 45 windows
  over-sampled for multi-event documents. This is a stress test, not an
  archive-wide estimate (`eval/EVENT_LEVEL_PROTOCOL.md` §2, §8). The Experiment A
  link audit covers the original systems only, so §11 of the report says so.

## Runbook

```bash
make supervised-setup   # one-off: torch, spacy-curated-transformers, en_core_web_trf, en_core_web_lg
make supervised-parse   # both NER models over the 45 windows -> outputs/parsed/ (~40 s on an M4)
make supervised-freeze  # FROZEN.json, before any scored run (FORCE=1 to re-freeze; log why)
make supervised-run     # LOWO + 5-fold x seeds 48-50 -> runs/ (~15 s)
make supervised-score   # -> SUPERVISED_SCORES.md, supervised_scores.json, supervised_pairs.csv
```

`python -m benchmark_supervised.run --resubstitution` trains and predicts on
all 45 windows, into `runs_smoke/`, as a plumbing check only.

## Files

| File | Purpose |
|---|---|
| `parse.py` | windows → both NER models → JSON parse cache (`outputs/`, git-ignored) |
| `features.py` | candidates, feature templates, gold labels; pure functions |
| `model.py` | the four classifiers, clustering, decoding |
| `run.py` | freeze; LOWO / k-fold runs in the shared `event_extractions` schema |
| `score.py` | Experiment A's scorer + the NER-baseline pairing and recall funnel |
| `FROZEN.json` | code hashes and configuration, fixed before scoring |
| `runs/<scheme>/` | `event_extractions.{jsonl,csv}`, `predictions_detail.jsonl` (per-event probabilities), `run_stats.json` (folds, training counts, ceilings) |
| `SUPERVISED_SCORES.md` | the report; `supervised_scores.json`, `supervised_pairs.csv` hold everything behind it |

Tests: `tests/test_benchmark_supervised.py`, run by `make test`.
