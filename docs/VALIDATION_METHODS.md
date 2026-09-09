# Validation methods — protocol, unit of comparison, and matching rules

Answers to the reviewer queries on the human-annotation validation, each traced
to the code that implements it. Where the honest answer is "this was not done",
it says so; those are collected in §5.

**Updated 2026-09-06.** Three of the defects this document recorded have since
been fixed in the scorer — failed API calls are no longer scored as findings,
and both the location and date matching rules are now reported under a corrected
variant beside the published one. Sections 4.6–4.8 describe current behaviour and
mark what changed; §5 marks which limitations are closed.

Companion to [HUMAN_VALIDATION_SUMMARY.md](HUMAN_VALIDATION_SUMMARY.md), which
reports what the validation found.

---

## 1. Document selection

**The annotation set is not a document sample. It is the document footprint of an
event sample**, and that distinction drives every caveat below.

The chain is three steps:

1. **Population.** The prompt-5 / `gpt-5` / Azure production run over 10,000
   documents, which emitted 3,572 verifiable events across 1,913 documents
   ([Makefile:132](../Makefile#L132)).
2. **Event sample, n=175.** `eval/prefill_gold_validation.py --target 175`,
   default `--sampling random`, seed 42
   ([prefill_gold_validation.py:184](../eval/prefill_gold_validation.py#L184)).
   Allocation across the nine hazard families is proportional to each family's
   share of the 3,572 under largest-remainder rounding; the draw within a family
   is uniform without replacement. The queue is written to
   `eval/production_validation.csv` with `in_queue = Y` on the 175 sampled rows.
3. **Document set, n=167.** The distinct `asset_key`s behind those 175 events
   ([prefetch_annotation_documents.py:44](../eval/prefetch_annotation_documents.py#L44)).
   168 would be 175 minus duplicates; 7 documents contributed 2 queued events
   each, giving 167.

### What this makes the set

- **Every document contains at least one event the production run found.** A
  document the run declined could not enter the sample at any step. The set
  therefore contains no true negatives by construction, and the 10 documents the
  annotator ultimately marked `no`/`unclear` are the production run's own false
  positives, not a negative control.
- **Stratification is on `event_hazard` (the raw label), not on document type,
  language, length, or publication year.** Those dimensions are whatever the
  hazard-proportional event draw happened to produce: 165 of 167 documents are
  English, 2 Japanese.
- **Documents with many events are over-represented** relative to a uniform
  document sample, because the sampling unit is the event. A 40-event document
  had 40 chances to enter; a 1-event document had one.
- **The sampling is seeded and deterministic.** `--sampling random --seed 42`
  regenerates the identical queue. The alternative mode, `--sampling risk`,
  ranks by a label-free heuristic and was **not** used for this queue.

The consequence for reported metrics: **recall is estimable on this set,
precision is not.** See §3 of the summary.

## 2. Annotation protocol

| | |
|---|---|
| Annotators | **1** |
| Adjudication | **none** — no second pass, no arbitration, no overlap set |
| Inter-annotator agreement | **not measurable** — no second rater |
| Written guidelines | **none as a standalone document**; the instructions are the app's in-line prompts, quoted below |
| Interface | `eval/human_annotation_app.py` (Streamlit) |
| Unit annotated | one document (not one queue event) |
| Rows | 167, all `annotation_status = done` |
| Time | median 70 s/document, mean 855 s (long tail from sessions left open); 38 documents saved in under 30 s |
| Self-flagged uncertainty | `gold_uncertain` is empty on all 167 rows — the "🚩 not confident" checkbox ([human_annotation_app.py:719](../eval/human_annotation_app.py#L719)) was never used |
| Free-text notes | 0 of 167 rows |

### The instructions, verbatim

There is no guidelines document. The complete annotation guidance is three
strings in the app:

- The task: *"Does this document report at least one specific, verifiable
  event?"* — answer space `yes` / `no` / `unclear`
  ([:111](../eval/human_annotation_app.py#L111), [:709](../eval/human_annotation_app.py#L709)).
- The scope rule: *"Everything **this document** reports, not just the event the
  queue sampled — gold has to be complete or precision is measuring the
  sampling."* ([:701](../eval/human_annotation_app.py#L701))
- Four free-text fields, pipe-separated: hazards (multiselect over the
  PreventionWeb vocabulary, plus a free-text escape), dates, locations, impacts.

"Specific, verifiable event" is nowhere defined further. No rule distinguishes a
document *reporting* an event from one *citing* it as an example — which is
exactly the boundary all ten model runs get wrong (§3 of the summary), so the
protocol leaves the hardest judgement in the study undefined.

### Seeding, and the anchoring it produces

The annotation form is not blank-slate. The right-hand pane shows the *seed*: the
union of every verifiable event the prompt-5 production run found in the
document, with its evidence snippets highlighted in the document text. A single
button, **"⤵ Accept seed as gold"**
([:689](../eval/human_annotation_app.py#L689)), copies all four seed fields into
the form.

The form fields themselves start empty, so accepting the seed is an action rather
than a default. The measured effect is nonetheless large — over the 157
gold-positive documents, gold is byte-identical to the seed for hazards in 91%,
dates 84%, locations 76%, impacts 75%; 101 of 157 documents were saved with no
edit to hazard, date or location at all. This is a single-run anchor on the gold
standard and it is why that run is excluded from all reported comparisons.

## 3. Annotation covered the extraction window, not the full document

**The annotator saw the same 12,000-character prefix the models were given, and
nothing beyond it.**

The document store is built from `benchmark_ner/outputs/documents.parquet`
([human_annotation_app.py:268](../eval/human_annotation_app.py#L268)), whose
`text` column was already truncated at fetch time — `--max-chars` default 12,000
([fetch_documents.py:78](../benchmark_ner/fetch_documents.py#L78)) — using the
same `trim_text` the extractor uses
([app_event_focus.py:465-468](../src/fonte/app_event_focus.py#L465-L468)).
That function is a **head truncation**, `text[:max_chars]`: a prefix, not a
summary, not a head-and-tail window.

Measured over the 167 documents in `eval/annotation_documents.json`:

| | |
|---|---|
| Documents truncated | **134 of 167 (80%)** |
| Documents seen in full | 33 |
| Median stored text | 12,000 chars |
| Median true `char_count` | 51,025 chars (max 1,228,988) |
| **Median share of document visible** | **23.5%** (p10 5.4%, p25 11.0%, p75 81.7%) |

The app states this to the annotator on every screen — *"12,000 characters — the
window the models were given (source document is 51,025)"*
([:645](../eval/human_annotation_app.py#L645)).

**How to read this.** The design makes model and annotator information-equivalent,
which is the right call for scoring extraction rather than retrieval: a model
cannot be charged with missing an event it was never shown. It also means the
gold standard is **gold for the window, not for the document**. Two claims are
therefore out of reach: (a) recall against everything the source document
reports, and (b) any statement that a document contains no event — a `gold_is_event
= no` verdict means "no event in the first 12,000 characters". For the truncated
80% that is a materially weaker claim, and it is the same 12,000 characters for
every run, so it does not bias the between-run comparison.

## 4. Scoring: unit, averaging, duplicates, and matching

Implemented in [`eval/score_against_human.py`](../eval/score_against_human.py).

### 4.1 Unit of comparison — the document

`asset_key`, not the event ([:224](../eval/score_against_human.py#L224)). Gold
and run are each collapsed to one record per document: gold hazards/dates/
locations are the union over that document's annotated rows, a run's are the
union over its verifiable events for the same document
([:100-108](../eval/score_against_human.py#L100-L108),
[:157-180](../eval/score_against_human.py#L157-L180)).

The reason is that `event_index` is not a shared key. The LLM's single
`Earthquake | Tsunami` event is the NER baseline's two candidates, and prompt 5
emits 572 events over the same 167 documents the queue sampled 175 from. Joining
on event index would score segmentation, not extraction. No alignment,
bipartite matching or clustering is attempted between event sets: a run is not
credited or penalised for how it splits a document.

The report also carries a **combined per-document record** — hazard, location
and date pooled into one content set, each field under its own rule — which
supports an exact-match rate: the share of gold-positive documents where a run
produced every gold item and nothing else. That is the strictest statistic in
the report and the one that speaks to whether output could be ingested without
review. It is defined only on what a run processed, since a document never
returned cannot be exactly matched or not.

**A consequence to state plainly:** because both sides are unioned to the
document, the scores are blind to event individuation. A run that emits one
correct event and a run that fragments it into eleven rows across eleven
districts (taxonomy class B1) receive identical field scores. The 11.7%
fragmentation rate measured in the failure taxonomy is invisible to every number
in the summary.

### 4.2 Averaging — micro, pooled over documents

**Confirmed micro** for the headline figure. TP/FP/FN are accumulated per
document and pooled, and precision/recall/F1 are computed once from the pooled
totals, so documents contribute in proportion to how many locations/dates/hazards
they carry.

**Macro F1 is now reported beside it** — the unweighted mean of per-document F1
over documents with a non-empty gold set, so a one-location document counts as
much as a thirty-location one. The two agree on ordering; macro runs 1–7 points
higher for most runs, because dense documents are the hard ones. GPT-5 mini
inverts this (macro 76.7% against micro 70.0%), which is diagnostic: it does well
on typical documents and badly on dense ones.

**Micro F1 now carries a 95% percentile bootstrap interval** over 2,000
document-level resamples (seed 42). The document is the resampling unit because
locations within one document are not independent draws. This is what lets a
reader see that GPT-5 (80.5%, 71.3–86.8) and GPT-5.4 (82.8%, 79.7–85.3) are not
separable on locations at this sample size.

No per-family or per-language breakdown is produced by this scorer.

Event **detection** is separately a per-document accuracy over all 167, with a
95% Wilson score interval; the paired test between two runs is an exact McNemar
on the discordant pairs ([:214](../eval/score_against_human.py#L214)), which is
the correct test here because the same documents are judged once by both runs.

### 4.3 Set metrics are computed only on gold-positive documents

`if not g: continue` ([:241](../eval/score_against_human.py#L241)) — field
metrics run over the 157 documents gold says carry an event. A run's field output
on the 10 gold-negative documents is not counted as a false positive anywhere.
The detection metric is the only thing that sees those 10.

### 4.4 Duplicate handling — silent set collapse

Every field is a Python `set`, on both sides. Duplicates within a document
collapse before matching, and the collapse is not reported. Measured: GPT-5
emits 864 location mentions across the 157 documents and is scored on 764
distinct ones — 100 discarded; Grok 4.6 emits 1,124 and is scored on 938 — 186
discarded. Repeating a location across fragmented events is free; it is neither
rewarded nor penalised.

Empty strings are dropped by the splitter — fields are split on `|`, stripped,
and empties discarded ([:65](../eval/score_against_human.py#L65)).

### 4.5 Hazard matching — family, not label

**Scored at family level, not label level.** Both sides pass through
`fonte.hazard_families.hazard_family`, which maps a free-text hazard onto
one of nine buckets by ordered regex, first match wins:

| Family | Pattern |
|---|---|
| flood | `flood\|inundation\|deluge` |
| earthquake | `earthquake\|seismic\|quake\|tsunami` |
| cyclone | `cyclone\|hurricane\|typhoon\|storm` |
| drought | `drought\|famine\|water scarcity` |
| wildfire | `wildfire\|bushfire\|forest fire\|fire` |
| landslide | `landslide\|mudslide\|rockfall` |
| volcano | `volcan\|eruption\|lahar` |
| heat | `heat ?wave\|extreme heat` |
| *other* | (no pattern matched) |

with `geomagnetic storm`, `space weather`, `sand and dust storm` and `dust storm`
stripped before matching so they do not fall into `cyclone`.

Compounds are **split on `|` before folding**, on both sides
([:157-164](../eval/score_against_human.py#L157-L164)): `Earthquake | Tsunami`
contributes `{earthquake}` (both components map to the same family), while
`Cyclone | Flood` contributes `{cyclone, flood}`. Order within a compound is
therefore irrelevant to the score, which neutralises the label-order
non-determinism recorded as taxonomy class B3.

**What family scoring buys and costs.** It stops near-synonyms reading as errors
— an annotator's `Tsunami` against a model's `Earthquake | Tsunami` is a match.
It also means the reported 85–93% hazard F1 is a *family* figure: distinguishing
`Cyclone, Hurricane and Typhoon` from `Storm surge`, both of which fold to
`cyclone`, is not measured. No label-level hazard score is computed anywhere in
this pipeline. Note also that `earthquake` absorbs `tsunami`, and the `fire`
alternative in `wildfire` is broad enough to catch any hazard string containing
the substring "fire".

### 4.6 Date matching — exact string equality, no parsing

Dates are compared as **raw strings after `.strip()` only**
([:172-180](../eval/score_against_human.py#L172-L180)). Specifically:

- **No date parsing.** Nothing is converted to a date object at any point.
- **No case folding** — unlike locations, dates are not `.casefold()`ed. This is
  a latent asymmetry rather than an active problem: 8 of 493 gold dates contain
  an uppercase character and zero of GPT-5's 108 date false negatives are
  case-only.
- **No range handling.** `2005-08-25 to 2005-08-30` is one opaque string. It does
  not match `2005-08-25`, and it is not expanded, split, or interval-compared.
- **No partial-date credit.** `2010` and `2010-01-12` do not match, and the pair
  costs two errors (one FP, one FN). Gold itself is mostly coarse: of 493 gold
  dates, 253 are bare `YYYY`, 111 `YYYY-MM-DD`, 63 `YYYY-MM`, 66 free phrases.
- **Free phrases are compared verbatim.** `summer 2007`, `2017 Atlantic hurricane
  season`, `past two years before 2010-10` match only themselves.

This was deliberate — the module docstring called it "deliberately strict", on
the grounds that the runs share a date convention and normalising would hide a
real difference. The cost is quantifiable, so **a year-set column is now reported
beside the exact one** rather than the reader having to take the strict rule on
faith. Re-scoring with two looser rules:

| Run | Exact (reported) | Prefix-compatible | Year-set |
|---|---:|---:|---:|
| GPT-5 (OpenRouter) | 78.3% | 80.1% | **91.9%** |
| Grok 4.6 | 77.8% | 80.1% | 88.4% |
| GPT-5.4 | 75.6% | 77.6% | 89.6% |
| Claude Opus 5 | 70.2% | 76.0% | 84.5% |
| Claude Sonnet 5 | 70.1% | 75.6% | 84.5% |
| Claude Haiku 4.5 | 66.1% | 67.9% | 81.4% |
| Mistral Large | 46.6% | 57.4% | 66.1% |

*Prefix-compatible* = one string is a prefix of the other (`2010` ≍ `2010-01-12`),
greedy 1-to-1. *Year-set* = compare the sets of 4-digit years appearing anywhere
in each side; this is the variant now shipped in the report. Everyone gains 10–20
points under year granularity and the ordering is unchanged, so the strict rule
costs level but not rank — which is the argument for keeping both columns rather
than switching.

### 4.7 Location matching — two rules, both reported

**Exact.** `.casefold()` and nothing else
([:107](../eval/score_against_human.py#L107),
[:169](../eval/score_against_human.py#L169)). No Unicode normalisation (no NFKD,
no diacritic folding), no punctuation stripping, no whitespace collapsing beyond
the splitter's `.strip()`, no article or administrative-suffix removal. Set
intersection over the document.

**Fuzzy (as published).** `rapidfuzz.fuzz.token_set_ratio` with a **threshold of
90**, greedy 1-to-1, highest-scoring pair first, each string usable once
([`fuzzy_matched`](../eval/score_against_human.py)). All
candidate pairs are scored, filtered at ≥90, sorted descending, then consumed
greedily — so it is a greedy approximation to a maximum matching, not an optimal
assignment. Ties break on string order. **If `rapidfuzz` is not installed the
function silently falls back to exact intersection** and the "fuzzy" column
becomes a duplicate of the exact one; reproducing the published numbers requires
rapidfuzz present (3.14.5 here).

**Fuzzy (corrected, now reported beside it).** The same rule with the strings
NFKD-folded and combining marks stripped, and rapidfuzz handed its
`default_process` (lowercase, non-alphanumerics to spaces). Both columns appear
in the report so the change is auditable rather than silent.

**Aliases, substrings, administrative containment: none of the three is
implemented, in either variant.** There is no gazetteer, no alias table, no ISO
or admin-code resolution, and no containment rule. Any credit for `Louisville` ≍
`Louisville, Kentucky` has to come out of `token_set_ratio` — and under the
published rule it does not, because **`token_set_ratio` was called with no
`processor`, so rapidfuzz tokenises on whitespace without stripping
punctuation**. The comma stays welded to the token:

| Pair | `token_set_ratio` (as called) | with `processor=utils.default_process` |
|---|---:|---:|
| `louisville` / `louisville, kentucky` | **66.7** ✗ | **100.0** ✓ |
| `gujarat` / `gujarat, india` | 66.7 ✗ | 100.0 ✓ |
| `tohoku` / `tohoku, japan` | 63.2 ✗ | 100.0 ✓ |
| `new orleans` / `new orleans, louisiana, usa` | 57.9 ✗ | 100.0 ✓ |
| `kathmandu valley` / `kathmandu` | 100.0 ✓ | 100.0 ✓ |
| `uttarakhand` / `uttarakhand state, india` | 100.0 ✓ | 100.0 ✓ |
| `male, maldives` / `malé` | 33.3 ✗ | 35.3 ✗ |
| `haiti` / `port-au-prince` | 21.1 ✗ | 31.6 ✗ |

The rule that emerges is positional, not semantic: a qualifier is absorbed only
when the punctuation lands on a token other than the matching one. `Uttarakhand
state, india` ≍ `Uttarakhand` scores 100 because the comma attaches to `state,`;
`Louisville, Kentucky` ≍ `Louisville` scores 66.7 because it attaches to
`louisville,` itself, destroying the token-subset relation. Since the qualifier
convention in the data is `Place, Parent`, the common case is the failing one. It
does not absorb spelling variation either: the taxonomy's own example, `bijnor` against
the source's `bijnaour`, scores 85.7 and falls below the threshold. That is
why the published fuzzy column adds only ~1 point over exact for prompt 5 while
the corrected rule adds 9.8–40.3 points to every other run (§6 of the summary).
The corrected variant applies `processor=default_process` for the comma class and
NFKD folding for the diacritic class (`malé`). Correctly, neither rule matches
`Haiti` to `Port-au-Prince` (31.6) — a containment or admin-hierarchy rule would
have to be argued for separately, and is still not implemented.

**This change reorders the field**, which the date change does not: GPT-5 mini
moves from tenth to eighth on locations, from 29.7% to 70.0%. That is the
strongest available evidence that the exact-match column was ranking surface
conventions rather than extraction quality.

### 4.8 Runs, coverage, and what is excluded

A run contributes only documents present in its own output; documents absent are
dropped rather than scored as misses.

**Error rows are now detected** (this was the third defect, and it changed
published numbers). A document whose every row is an error row — detected with
`fonte.app_event_focus.is_error_row`, imported rather than re-implemented,
so the scorer and the runner agree on what an error is — was never extracted. The
run made no claim about it, and scoring the absence of a claim as "found no
event" measures the transport, not the model. Such documents are excluded from
that run's denominator and reported as coverage; `--error-policy count-as-miss`
restores the old behaviour, which is right only when grading a pipeline
end-to-end rather than comparing models.

A document with *some* error rows and at least one successful row is still
scored — only wholly-failed documents are excluded.

What this changed:

| Run | Errored docs | Recall before | Recall after | Hazard F1 before | after |
|---|---:|---:|---:|---:|---:|
| DeepSeek V3.1 | 54 | 65.6% | **97.2%** | 71.5% | **87.5%** |
| GPT-5 mini | 6 | 96.2% | **100.0%** | 88.2% | 89.5% |
| Gemini 2.5 Flash / Pro, Qwen3 235B | 167 each | 0.0% | *not scored* | 0.0% | *not scored* |

Coverage is not free, and the report says so. Its first table prints the
processed-document count beside both readings of each run's score — quality on
what it processed (the model comparison) and the same quality discounted by
coverage (the pipeline reading) — so neither can be quoted without the other.

**Both denominators are carried through every recall figure in the report.**
Detection recall appears as `Recall, all docs` (divided by all 157 gold-positive
documents) and `Recall, processed` (divided by the gold-positive documents that
run returned). Each field's recall appears the same way, `Recall (all)` dividing
by every gold hazard, location or date in the 157 gold-positive documents,
including those on documents the run never returned. At full coverage the pairs
are identical; they diverge by exactly the run's failure rate otherwise —
DeepSeek's hazard recall is 91.7% processed against 62.3% over all gold items.

Precision, specificity, balanced accuracy, MCC and F1 have no all-documents
form: they need the run's own output in the numerator *and* denominator, and a
document that was never returned supplies neither. Those are reported on what
was processed, and the coverage column is what tells the reader how much of the
set that was.
The pairwise McNemar tests are paired on the intersection of the two runs'
returned documents, and `n` is printed for every pair.

The composite in that table is a weighted mean of detection, hazard, location
and date F1 with the weights from `eval/score_against_gold.py` (1.0 / 1.5 / 1.5 /
0.5), reused rather than reinvented so the two scorers rank on the same
priorities. It inherits every weakness of its parts — notably that detection F1
is prevalence-driven here — and is a sort key, not an evaluation.

`--exclude-uncertain` drops rows flagged `gold_uncertain = Y`; it changes nothing
here, since no row was ever flagged.

## 5. Limitations to state in the paper

1. **Single annotator, no adjudication, no overlap set.** No κ or any other
   agreement statistic can be reported. The `gold_uncertain` flag exists and was
   never used, so there is not even a self-reported difficulty signal.
2. **No written annotation guidelines.** "Specific, verifiable event" is
   undefined, and it is the boundary the evaluation turns on.
3. **Gold is anchored to one run** — byte-identical on 76–91% of fields — via a
   one-click "accept seed" affordance. That run cannot be evaluated on this set.
4. **Annotation is window-scoped**, covering a median 23.5% of each source
   document. `gold_is_event = no` means "no event in the first 12,000
   characters".
5. **No true negatives by construction.** Every document was selected because the
   reference run found an event in it.
6. **Event individuation is not measured.** Document-level union scoring is blind
   to fragmentation and duplication.
7. **Hazard accuracy is family-level**, over nine buckets; label-level accuracy
   is not measured. *(Open.)*
8. **Detection is not measurable on this set.** Balanced accuracy is 47.5–55.7%
   and MCC −0.06 to +0.15 for every run — at chance. With 10 negatives no run
   demonstrated discrimination, and the accuracy column reflects the 94%
   prevalence. This is now reported explicitly rather than implied away by an
   accuracy figure. *(Open — needs a negative set, not a code change.)*
9. **Exact-string date matching** remains the headline, with no parsing or range
   handling. *(Mitigated — a year-set column is now reported beside it; the
   strict rule costs 10–20 points without changing rank.)*
10. **Location fuzzy matching did not do what its name implied** — no
    preprocessing, so the dominant surface variant (comma-qualified parents)
    failed at threshold 90. *(Fixed — a corrected variant is reported beside the
    published one; it moves runs by up to 40 points and reorders them.)*
11. **Failed API calls were scored as negative findings.** *(Fixed — errored
    documents are excluded from the denominator and reported as coverage.)*

## 6. Minimal changes that would answer the reviewers with data

### Done — landed 2026-09-06

| # | Change | Effect on published numbers |
|---|---|---|
| 1 | Corrected fuzzy location rule (`default_process` + NFKD), reported beside the published one | +9.8 to +40.3 pp; reorders the field |
| 2 | Year-set date column beside exact | +10.6 to +19.5 pp; rank unchanged |
| 3 | `is_error_row` detection, errored documents excluded from the denominator and reported as coverage | DeepSeek recall 65.6% → 97.2%; three runs correctly report no score |
| 4 | Specificity, balanced accuracy and MCC on detection, with Wilson intervals on each denominator | showed detection to be at chance for every run |
| 5 | Document-level bootstrap intervals on every field F1; macro F1 beside micro | showed the top runs to be mutually inseparable |
| 6 | McNemar paired on the documents both runs returned, with `n` printed | DeepSeek pairs now honest at n=113 |

### Still open — these need annotation, not code

| # | Change | Cost | What it buys |
|---|---|---|---|
| 7 | Annotate ~100 documents no run flagged | new sampling script + ~2 h | makes specificity, precision and MCC measurable — currently the most important number in the study rests on 10 documents |
| 8 | Second annotator on a 30-document overlap, blind (no seed pane) | ~1 h | a κ to quote, and an estimate of the anchoring effect |
| 9 | Annotate the full text of a 20-document subset | re-fetch at a larger `--max-chars` | bounds what the 12,000-character window loses |
| 10 | Specify a location surface form in prompt 5 | prompt edit + re-run | makes exact-match location F1 a real metric rather than a dialect test |
