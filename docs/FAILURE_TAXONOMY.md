# Event extraction — failure taxonomy

**Run:** `outputs/event_extractions/` (prompt 5, `gpt-5`, 10,000 documents, 12,000-char window)
**Extraction date:** 2026-08-07 · **This audit:** 2026-09-05
**Scope:** the 3,572 verifiable event rows, plus the 175 human-adjudicated events
in `eval/production_validation.csv` and the 35 fully annotated documents in
`eval/human_annotations.csv`.

Every class below carries a measured rate and at least one exemplar traceable to
an `asset_key` and its source text. Classes are grouped by where in the pipeline
the failure originates, because that is what determines the fix.

---

## 0. Headline

| | |
|---|---|
| Verifiable events | 3,572 (from 1,913 of 10,000 documents) |
| Human verdicts | 119 correct / 44 partial / 12 wrong (n=175) |
| Location strings emitted | 5,463, of which 1,028 (18.8%) never resolved |
| **Confirmed fabricated impact figures** | **0 of 2,598 numeric claims** |

The most consequential finding is negative. Across all 3,572 rows there is no
content hallucination: no invented figures, no hazard labels outside the
controlled vocabulary, no violations of the technological-hazard footprint rule.
The failures are **schema, scope and normalisation failures**, which means the
guardrails belong in post-processing and prompt scope, not in fact-checking.
Section 7 records what was checked and held.

### Class summary

| Code | Class | Rate | Basis |
|---|---|---:|---|
| A1 | Illustrative-catalogue mining | 207 rows · 5.8% | counted |
| A2 | Passing-mention harvesting | — | exemplar |
| A3 | Aggregate impact bound to one event | — | exemplar |
| A4 | Slow-onset process typed as an event | — | exemplar |
| B1 | Event fragmentation across locations | 418 rows · 11.7% | counted |
| B2 | Deduplication escape | 222 rows · 84 groups | counted |
| B3 | Compound-label order non-determinism | 5 hazard sets | counted |
| C1 | Non-normalisable date forms | 548 rows · 15.3% | counted |
| C2 | Deictic dates with no anchor | 78 rows · 2.2% | counted |
| C3 | Event name written into the date field | 6 rows | counted |
| C4 | Synthesised relative anchors | 9 rows | counted |
| C5 | Dates outside any plausible event window | ~8 rows | counted |
| C6 | Publication-year indistinguishability | 96 rows · 2.7% | counted |
| D1 | Surface-form non-determinism | 105 places in >1 form | counted |
| D2 | Silent canonicalisation from world knowledge | 647 strings · 12.6% | counted |
| D3 | Descriptive phrases in place of place names | 462 strings · 8.5% | counted |
| D4 | Hazard source conflated with impact footprint | 74 rows | counted |
| D5 | Net effect: geocoding attrition | 1,028 · 18.8% | counted |
| E1 | Evidence snippets are silent translations | 84.8% ungrounded in non-Latin docs | counted |
| E2 | Numeral normalisation breaks string provenance | 45 of 2,598 | adjudicated |
| E3 | Language metadata does not describe the attachment | ≥3 documents | exemplar |
| F1 | Document hit rate and its language skew | 19.1% of documents | counted |
| F2 | Within-document recall gaps | R = 0.928 on locations | counted |

---

## A. Selection failures — what got counted as an event

The model decided that something was a concrete disaster occurrence when it was
an illustration, a list entry, or a slow-onset process. The schema cannot catch
these: every field is well-formed and source-supported. All four exemplars were
marked **wrong** by the human reviewer.

### A1 — Illustrative-catalogue mining · 207 rows (5.8%)

Pedagogical documents that list historical events as *examples of a hazard type*
are read as multi-event reports. The tell is in the evidence field: 207 rows cite
a snippet containing "Examples:", "such as", "Table n", or "Annex". The impact
statements are then copied from the surrounding definition, so they describe what
the hazard class does in general, not what this event did.

`15d214469346edd4` — *Volcano daily* — 18 events, one per entry in a glossary of
eruption phenomena. Human verdict: **wrong** (idx 18), **partial** (idx 11).

```
evidence [1]     Examples: Galunggung, Indonesia, 1982
key_impacts [1]  The volcano covers houses and crops under coarse or finer ash
key_impacts [3]  The volcano covers villages and fields under a river of fire
                 that burns everything
```

The impact text is the glossary's *definition* of ash fall and lava flow, reused
verbatim across events 1–2 and 3–5 respectively. It is not an impact of
Galunggung 1982. 36 rows in this one document carry catalogue-marker evidence.

### A2 — Passing-mention harvesting from proceedings

Conference declarations enumerate recent disasters in a single sentence to
justify a policy position. The prompt bans passing mentions; the model instead
emits one event per name in the list, each inheriting the same synthesised date.

`3090f7dd140e14b7` — *Five-year roadmap to cope with weather-related hazards in
Asia* — 7 events, all medium confidence.

```
evidence [1]  "Typhoon Morakot in Taiwan Province of China"
              The declaration lists these disasters as occurring "in the past two years"
evidence [4]  "the 'dzud' in Mongolia"
              The declaration frames it as one of the disasters in "the past two years"
event_dates   past two years before 2010-10     (on 6 of 7 events)
```

The model's own evidence admits the source gives no event timing. It supplies one
anyway by fusing the relative phrase with the document's date — precisely what
the prompt's evidence-discipline rule forbids ("metadata cannot supply a missing
date"). See also C4.

### A3 — Aggregate impact bound to a single event

Where a source reports a total across many disasters, the model attaches that
total to whichever event it extracted, and flags the problem in
`missing_information` rather than declining the event.

`e757f526ff42fe56` — *International Conference on the Health Aspects of the
Sendai Framework* — human verdict: **wrong**.

```
event_hazard         Volcano · Mount Kelud · 2014-01 to 2014-02
key_impacts          Part of disasters causing total economic damage of
                     $2.3 billion during Jan-Feb 2014
missing_information  Specific impact for this event not broken out from aggregate
```

The row is emitted at `event_confidence = medium` and passes
`_keep_verified_unique_events`, so a downstream loss database would ingest
$2.3 bn as Kelud's damage.

### A4 — Slow-onset process typed as a discrete event

Coral bleaching, coastal erosion and similar multi-decade processes are forced
into the nearest PreventionWeb hazard label and given an event date. The
vocabulary constraint makes this worse: with no label for the actual phenomenon,
the model picks the closest driver rather than dropping the event as instructed.

- `f42eb42f7230c527` — *Queensland climate adaptation strategy* — hazard
  `Heatwave and Extreme Heat`, date `2017-02`, location `Great Barrier Reef`
  (feature), impact "Widespread coral bleaching observed". Verdict: **wrong**.
- `6c3b4eb8b5735cb0` — *Coastal erosion hazard and risk assessment* — hazard
  `Sea level rise`, dates `1600-1850`, impact "Over 250 m of land lost along the
  coast". Verdict: **wrong**. A 250-year erosion record is not an event.

---

## B. Individuation failures — how events were split and merged

One real-world occurrence becomes several rows, or several become one. These are
the highest-volume failures in the run and they corrupt every count downstream —
event totals, per-hazard frequencies, and the stratum weights used to draw
validation samples.

### B1 — Event fragmentation across locations · 418 rows (11.7%)

When a document narrates one episode district by district, the model emits one
event per passage. 418 rows fall into 170 groups that share a document, a hazard
and a year while having *pairwise disjoint* location sets — the signature of a
single event cut into pieces.

`3d46c98a726cb91b` — *Climate change and disaster in the Hindukush Himalayan
region* — human verdict: **partial** (idx 2).

```
event 1  Flood · 2010 · Almora district                       high
event 2  Flood · 2010 · Uttarakhand                           high
event 3  Flood · 2010 · Bijnor | Moradabad | Bulandshahr      high
event 4  Flood · 2010 · Leh                                   medium
```

Worst cases in the run:

| Document | Pattern | n |
|---|---|---:|
| `48b59d5c8b2d8467` | Epidemic and pandemic / 2020, one row per country | 17 |
| `c3fd556422ba7e83` | Flood / 2017 and again / 2018, one row per US coastal city | 11 each |
| `75798f8af1dbda1b` | Epidemic and pandemic / 2020, one row per country | 10 |
| `38e70ed747db82e4` | Insect infestation / 2021, one row per country cluster | 6 |

### B2 — Deduplication escape · 222 rows in 84 groups

The identity key in `_keep_verified_unique_events`
([app_event_focus.py:218-224](../src/fonte/app_event_focus.py#L218-L224))
is `(hazard, dates, locations)`. Because locations are part of the key, two rows
describing the same event with different location spellings or different subsets
both survive.

- `779edfae9ce50070` — Flood / 2013 emitted ×3
- `0aa6c5fb71181674` — Flood / 2005 emitted ×3
- `451197d414e1d009` — Flood / "earlier this year in 2012" ×2

### B3 — Compound-label order non-determinism · 5 hazard sets

The prompt asks for joined labels "in order of source prominence", which is not a
deterministic function of the event. The same hazard set therefore appears under
several surface strings, each of which is a distinct `stratum` and a distinct
identity key — so B2's dedup cannot see through it.

| Hazard set | Dominant form | n | Variant | n |
|---|---|---:|---|---:|
| {Earthquake, Tsunami} | `Earthquake \| Tsunami` | 161 | `Tsunami \| Earthquake` | 3 |
| {Flood, Landslide} | `Flood \| Landslide` | 35 | `Landslide \| Flood` | 2 |
| {EQ, Tsunami, NBC} | `Earthquake \| Tsunami \| NBC` | 16 | `NBC \| Tsunami \| Earthquake` | 1 |
| {Cyclone, Flood, Landslide} | `Cyclone \| Flood \| Landslide` | 6 | `Flood \| Landslide \| Cyclone` | 1 |
| {Technological, Flood} | `Technological \| Flood` | 2 | `Flood \| Technological` | 1 |

---

## C. Temporal failures

The date field is the loosest part of the contract. The schema accepts any
string, and the prompt explicitly sanctions "a short event-timing phrase" — so
most of what follows is *permitted* output that no downstream consumer can parse.

| Form of first date | Rows | Share | Downstream |
|---|---:|---:|---|
| `YYYY-MM-DD` | 759 | 21.2% | parses |
| `YYYY-MM` | 566 | 15.8% | parses |
| `YYYY` | 1,699 | 47.6% | parses, no within-year resolution |
| free phrase | 548 | 15.3% | 428 distinct surface forms |

Only 21.2% of events carry a day-precision date.

### C1 — Non-normalisable date forms · 548 rows (15.3%)

The 548 phrase-form dates resolve into four recurring shapes, none forbidden by
the schema and none accepted by a date parser.

| Sub-kind | Observed values | Top n |
|---|---|---:|
| Interval | `2005-08-25 to 2005-08-30` · `1997–1998` · `2008-2011` | 5 |
| Season | `summer 2007` · `spring 2019` · `2017 Atlantic hurricane season` | 6 |
| Meteorological year | `2017 (meteorological year: May 2017 – April 2018)` | 11 |
| Decade | `1970s` · `late 1990s` | 3 |

The meteorological-year form is worth singling out: the model is writing a
parenthetical *gloss* into a date field, a category error the schema description
invites by permitting "a short source phrase".

### C2 — Deictic dates with no anchor · 78 rows (2.2%)

78 event rows contain no four-digit year anywhere in `event_dates`. The model
faithfully copies the source's deixis and loses the referent, sometimes at `high`
confidence on events it has clearly identified correctly.

`e52229275afd38fb` — *IFRC mid-year report* — confidence **high**:

```
event_dates       January
hazard/location   Earthquake · Port-au-Prince
publication_year  2010
```

The event is unambiguously the 2010-01-12 Haiti earthquake, and the metadata
carries 2010 — but the prompt bars metadata from supplying dates, so the model
correctly refuses to anchor and the row is unusable either way. `8f927952aae8ecfd`
produces the same event as `12 January`.

Others: `last month` (`86375f9e8277f6a8`, Bangkok flood) · `this year` ·
`twenty-five years ago` · `at the time of writing this Working Paper` ·
`al final de la década` · `most recently`

### C3 — Event name written into the date field · 6 rows

Where the source dates an event by naming a storm, the model puts the storm's
name in `event_dates`. The value is a well-typed string, so nothing rejects it.

`4ea76b5a1df284df` — *Three case stories from the CBDRR project*:

```
event 1 dates  during Cyclone Sidr
event 2 dates  during Cyclone Aila
locations      Uttor Chouta | Mirzagonj Upazila   (both events)
```

Others: `Cyclone Winston` ×2, `aftermath of Hurricane Irma`.

### C4 — Synthesised relative anchors · 9 rows

Rather than emit the source's relative phrase alone, the model manufactures a
composite that *looks* partially normalised: `past two years before 2010-10`,
`most recently before 2010-10`, `earlier this year in 2012`, `past month before
Earth Day 2010`. The embedded ISO fragment comes from the document's own date,
which the evidence-discipline rule prohibits. A naive parser will extract
`2010-10` and treat it as the event date.

### C5 — Dates outside any plausible event window · ~8 rows

The schema imposes no lower bound on the year. The NER baseline hard-codes
`_YEAR_MIN = 1900` in
[ner_extract.py:85](../benchmark_ner/ner_extract.py#L85); the LLM path has no
equivalent guard, so archaeological events enter a contemporary DRR loss corpus.

- `651c0f9323cd4e4c` — Drought · `about 2200 BC` · northeast Syria
- `b5d7a2ddf2847163` — Tsunami · `seventeenth century B.C.` · Santorini
- `144d22dbd67b64ea` — `Earthquake | Tsunami` · `AD 365` · Alexandria and Haifa
- `6579816914d9d2182` — Earthquake · `1356-10-18` · Basel and Bern — **wrong**

### C6 — Publication-year indistinguishability · 96 rows (2.7%)

96 rows carry only year-precision dates, all equal to the document's
`publication_year`. Many are legitimate — a 2017 report on the 2017 hurricane
season — but the output gives no way to separate those from a model that
defaulted to the publication year, which is exactly the failure the prompt's date
rule targets. The NER baseline emits `event date equals publication year` into
`missing_information` for this case
([ner_extract.py:412-413](../benchmark_ner/ner_extract.py#L412-L413)); the LLM
emits nothing.

- `7260abd2fda7c13c` — Drought · 2018 · Cape Town, in a 2018 report. The Day Zero
  drought spans 2015–2018.
- `2377b7cef31ab9ff` — Flood · 2017 · Logan, Queensland, in a 2017 report.

---

## D. Location failures

The locations are substantively correct — precision against human gold is 0.949 —
but their *surface form* is not a function of the source. That variance is what
fails the geocoder.

### D1 — Surface-form non-determinism · 105 places in >1 form

The same place is emitted bare in one row and hierarchically qualified in
another, with no rule governing which. 17.6% of location strings append an
administrative type word, 6.6% concatenate a parent, 2.4% add a parenthetical
gloss. Each variant is a distinct gazetteer query and a distinct dedup key.

| Emitted as | …and also as |
|---|---|
| `Christchurch` | `Christchurch, New Zealand` |
| `Gujarat` | `Gujarat, India` |
| `Tohoku` | `Tohoku, Japan` |
| `Kashmir` | `Kashmir, Pakistan` |
| `Eyjafjallajökull volcano` | `Eyjafjallajökull volcano, Iceland` |

**Consequence for evaluation.** On `a75cfb62b2052132` the model emitted
`Louisville, Kentucky` and the human gold recorded `Louisville`. Exact-match
scoring counts this once as a false positive and once as a false negative — a
single formatting choice costing two errors. The measured location P/R of
0.949 / 0.928 is therefore a **floor, not an estimate**.

### D2 — Silent canonicalisation from world knowledge · 647 strings (12.6%)

647 location strings in Latin-script documents do not appear verbatim in the
12,000-character window the model was given. Sampling shows these are
overwhelmingly *corrections and expansions*, not inventions: the model normalises
to its own gazetteer knowledge without recording that it did so.

`3d46c98a726cb91b` emits `Bijnor | Moradabad | Bulandshahr`. Source text,
verbatim:

> …entire area including cities like **Bijnaour**, Moradabad and **Bulandshahar**
> witnessed the worst experiences of flood.

Both misspellings were silently corrected to their gazetteer forms. This is
*helpful* for geocoding and *fatal* for provenance — no field records that the
output differs from the source.

- `Whakaari / White Island volcano` — Māori name supplied from world knowledge;
  the slash-joined pair matches no gazetteer entry and does not resolve
- `United Kingdom of Great Britain and Northern Ireland` — expanded to the formal
  ISO name
- `Chernobyl Exclusion Zone` — designation appended
- `Agastyamuni (spelled Agostyamuni), Rudraprayag district` — the model
  documenting its own correction inline, in the location field

### D3 — Descriptive phrases in place of place names · 462 strings (8.5%)

Where the source describes an affected area rather than naming it, the model
emits the description. These are faithful and unresolvable.

`coasts of Guatemala` · `coastal areas of Nias` · `Mekong River floodplains` ·
`Texas–Louisiana border area` · `Colchester area` · `Southwest Florida` ·
`Brisbane River catchment area` · `Tōhoku-region of Japan` · `Praslin (east coast)`

### D4 — Hazard source conflated with impact footprint · 74 rows

The prompt defines `affected_locations` as places "flooded, damaged, hit,
evacuated, cut off, contaminated". In 74 rows the model instead emits the
hazard's *origin* — an epicentre, a fault, a facility, a river. Downstream this
is a direct cause of geometry overshoot, since a fault or river resolves to a
line spanning hundreds of kilometres.

- `d29de93e0db0f994` — Earthquake · `off the coast of Sumatra, Indonesia`
- `10fea7a69d549bb8` — Earthquake · `Motagua Fault`
- `b7a109e614530d13` — Landslide · `Hunza River`
- `e5eedfa575b5a560` — Earthquake · `off the coast of Chile`

`80d28a2163122619` — *USA: A national report card on protecting children during
disasters* — human gold rejected both source-side locations:

```
model emitted  Louisiana | Mississippi | Alabama | Deep Horizon oil rig
               | Louisiana's coastal waters
human gold     Louisiana | Mississippi | Alabama
also dropped   the Technological hazard label attached alongside the cyclone
```

### D5 — Net effect: geocoding attrition · 1,028 of 5,463 (18.8%)

D1–D4 compound at the polygon stage. The resolution pools recorded in
`outputs/event_extractions_polygon_validation/polygon_validation_summary.json`
partition the location strings exactly:

| Pool | Strings | Share | Dominant cause |
|---|---:|---:|---|
| Resolved, confidence ≥ 0.7 | 2,607 | 47.7% | — |
| Resolved, confidence < 0.7 | 1,828 | 33.5% | D1 qualifiers, D3 phrases |
| Unresolved | 1,028 | 18.8% | D2 aliases, D3 phrases, D4 features |

Unresolved strings, sampled: `Colchester area` · `Whakaari / White Island
volcano` · `Deepwater Horizon oil drilling platform` · `Onagawa town` ·
`Chao Phraya basin` · `Indian Kashmir` · `Chumchon Baan Sanchampa (CBS) School` ·
`Texas–Louisiana border area` · `Sindhupalchowk District` · `Montagne Pelée`

---

## E. Auditability failures

This class contains no incorrect content. It exists because the output is correct
in ways that cannot be *checked* — which for a validation pipeline is its own
defect, and the reason the grounding statistics above must be read carefully.

### E1 — Evidence snippets are silent translations

| Document script | Locations verbatim in source |
|---|---:|
| Latin | 4,501 / 5,148 (87.4%) |
| Non-Latin | 48 / 315 (15.2%) |

The cause is not fabrication. The model reads the source in its own language and
presents an English rendering in `evidence_snippets`, a field whose description
asks for "snippets or paraphrases … from the source". A reviewer who does not
read the source language cannot verify the row, and no automated string check
can either.

`26fcf8ef39025f97` — *Implementation of the International Strategy for Disaster
Reduction* (A/65/388), source language **Chinese**:

```
evidence [1]  On 14 April 2010, Iceland's Eyjafjallajökull volcano began
              erupting, ash caused a seven-day closure of European airspace.
key_impacts   Over 100,000 flights canceled | About 10 million travelers
              affected | Estimated business losses of US$3.3 billion
```

Source text, verbatim:

> 2010 年4 月14 日，冰岛埃亚菲亚德拉冰盖火山开始爆发，喷出的火山灰导致欧洲空域暂时关闭七天，迫使10 多万个航班取消，影响约1 000 万名旅客，使欧洲的商业损失达到33 亿美元。

Every figure checks out — 10多万 = over 100,000, 1000万 = 10 million,
33亿 = 3.3 billion. The extraction is **exactly right**. It is simply
unverifiable by any tool that matches strings, and the word "Eyjafjallajökull"
appears nowhere in the source.

Two further cases resolve the same way:

- `e6279db7ecdca366` — Russian, A/69/364 — "эвакуация с побережья свыше 900 тыс.
  человек" → "Over 900,000 people evacuated"
- `51c5a0e44893dcdb` — Arabic, A/RES/69/219 — "٠٠٠ ٠٤٢" → "About 240,000 people
  killed", read correctly through right-to-left PDF digit reversal

### E2 — Numeral normalisation breaks string provenance · 45 of 2,598

The model converts every numeric notation it meets into Western
thousands-separated digits. Substantively correct in all 45 flagged cases, but
each one defeats a naive grounding check.

| Source form | Emitted | Document |
|---|---|---|
| One hundred ninety-eight | `198` | `d45cae8a45e8418c` |
| Four hundred health facilities | `400 health facilities` | `9025cf08e06bf6d7` |
| over 24 thousand | `Over 24,000` | `095ed39d5ae3960f` |
| `1 万8,430 人` (JP myriad) | `18,430` | `7bad2880a4588284` |
| `230’000` (Swiss separator) | `230,000` | `2ccadfcb54b6694e` |

### E3 — Language metadata does not describe the attachment

All three documents in E1 carry `language = "English"` in the Databricks metadata
while the attachment text is Chinese, Russian and Arabic respectively — these are
UN documents whose *original* was English. Any language-stratified analysis of
the run inherits this error, including the coverage figures in F1.

---

## F. Coverage failures

### F1 — Document hit rate and its language skew · 19.1%

1,913 of 10,000 documents yield at least one event, against 3,950 (39.5%) for the
spaCy baseline over the identical corpus and window. Most of that gap is the LLM
correctly declining guidance and framework documents — but not all of it.

| Language | Docs | With ≥1 event | Rate |
|---|---:|---:|---:|
| English | 9,891 | 1,895 | 19.2% |
| Spanish | 52 | 9 | 17.3% |
| Japanese | 16 | 8 | 50.0% |
| Arabic | 27 | 1 | 3.7% |
| French | 14 | 0 | 0.0% |

The counts are too small to be conclusive and the language field is unreliable
(E3), but 0/14 French and 1/27 Arabic against 19.2% English is worth a targeted
check before the run is described as language-agnostic.

### F2 — Within-document recall gaps · R = 0.928 on locations

Against the 35 fully annotated documents:

| | Precision | Recall | tp | fp | fn |
|---|---:|---:|---:|---:|---:|
| Locations | 0.949 | 0.928 | 129 | 7 | 10 |
| Hazards | 0.952 | 0.984 | 60 | 3 | 1 |

Excluding the D1 formatting artefacts (`Louisville`, `Malé, Maldives`), the
residue is genuine omission:

- `fec623a3538f1744` — missed the **1991 Bangladesh cyclone**; emitted only the
  2005 and 2008 events
- `95aa14d1fba7d15f` — missed `Mandakini river` and `Uttarakhand`
- `9025cf08e06bf6d7` — missed `Gorkha`, the epicentre district, while emitting
  Kathmandu Valley
- `6db5c60bf827039b` — missed `northwest and west Africa`

Hazard false positives are all over-typing rather than invention:
`71a170bff0360da1` labelled a wildfire `Technological hazard`;
`80d28a2163122619` and `cc4d64d96e0aa54d` each added a hazard the annotator
dropped.

---

## 7. What held

A taxonomy that only lists defects misrepresents where the risk sits. Five
constraints that a generative extractor might be expected to violate were checked
across all 3,572 rows and were not violated at all.

| Constraint checked | Violations | Of |
|---|---:|---|
| Hazard label outside the PreventionWeb vocabulary | 0 | 3,572 rows / 3,760 label components |
| Bare-country footprint for a strictly sub-national hazard | 0 | 200 all-country rows |
| Country emitted alongside its own sub-regions | 4 | 3,572 rows (0.1%) |
| Technological / NBC event given a downwind or country footprint | 0 | 163 rows |
| `confidence = high` with no impact statement | 0 | 1,955 high-confidence rows |
| Fabricated impact figure | 0 | 2,598 numeric claims |

The NBC result is worth stating plainly. Across 163 technological and nuclear
rows the admin-level mix is 87 city, 76 point, 16 admin1, 12 feature — and zero
country. Chernobyl resolves to `Chernobyl Nuclear Power Plant | Pripyat |
Chernobyl Exclusion Zone`, with no receiving countries. The most elaborate rule
in the prompt is also its most reliably obeyed.

---

## 8. Method and caveats

**Sources.** Rates are computed over the 3,572 verifiable event rows in
`outputs/event_extractions/event_extractions.jsonl`. Human verdicts come from the
175 adjudicated rows in `eval/production_validation.csv` and the 35 fully
annotated documents in `eval/human_annotations.csv`. Grounding checks match
extracted strings against the same 12,000-character window, taken from
`benchmark_ner/outputs/documents.parquet`, after Unicode NFKD folding and
separator stripping.

**Confidence in each rate.** Classes marked *counted* in the class summary are
computed programmatically over all 3,572 rows and are exact for the stated
detector. Classes marked *exemplar* (A2, A3, A4, E3) are established by human
verdict on specific rows and were **not** counted corpus-wide — their true rates
are unknown, and the sampled sizes are too small to extrapolate.

**Where the detectors over- and under-count.**

- D2's 647 counts every location not verbatim in the window, which includes
  legitimate paraphrase as well as canonicalisation.
- C6's 96 rows are a *risk marker*, not confirmed errors — the point is that the
  output does not let you tell the two apart.
- B1 requires pairwise-disjoint location sets and so undercounts fragmentation
  wherever the split passages share a place name.
- A1 counts catalogue-marker evidence, which will include some legitimate events
  that happen to be cited in a table.

**Adjudication of the fabrication check.** The 45 impact figures that failed the
string check were checked one by one against source text. All resolved to
notation variance (E2) or cross-lingual rendering (E1). An initial pass had
flagged `9025cf08e06bf6d7` as a number-to-entity misbinding — the source reads
"Four hundred health facilities, 9,000 classrooms", so the extraction is correct
and that flag is withdrawn.

**Not covered.** This audit does not assess polygon geometry correctness: the
400-row sample in `outputs/event_extractions_polygon_validation/` has
`location_correct`, `geometry_correct` and `date_correct` unpopulated on all 400
rows, so D5 reports resolution *attrition* only, not resolution *accuracy*.
