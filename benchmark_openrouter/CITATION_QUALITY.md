# Citation quality — are the evidence snippets in the document?

Documents: **217** (arms: 167, 50), matched against the 12,000-character window the model was given, not the full source.
Non-Latin-script documents: 8 (3×ARABIC, 4×CJK, 1×CYRILLIC). No human annotation is used anywhere in this file.

Source language, by function-word profile: 188×en, 10×es, 7×fr, 4×CJK, 3×ARABIC, 2×unplaced, 1×pt, 1×CYRILLIC, 1×it. The 29 documents not confirmed English have their weak and unsupported snippets held out: the roster answers in English regardless of source language, so a failed lexical match there is as likely to be a translation as an invention.

`quotable` = the snippet can be located in the text (verbatim, elided or near-verbatim). `grounded` = quotable, or every word of it is in the document. Prompt 5 asks for "snippets **or paraphrases**", so `grounded` is the obedience-aware rate and `quotable` is the auditor's rate — the one that says whether a record can be traced back to a line of source. Held out of every denominator: `cross_script` and `cross_language` (a translation and an invention look identical to a lexical test) and `no_content`.

## Found or not found

Raw counts first. `found` is a snippet located in the document text; `not found` is everything else the test applies to, paraphrases included.

| run | events | snippets | judged | found | not found | found rate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Claude Haiku 4.5 | 449 | 952 | 842 | 434 | 408 | 51.5% (48.2%–54.9%, n=842) |
| Claude Opus 5 | 518 | 823 | 801 | 686 | 115 | 85.6% (83.0%–87.9%, n=801) |
| Claude Sonnet 5 | 540 | 843 | 828 | 752 | 76 | 90.8% (88.7%–92.6%, n=828) |
| DeepSeek V3.1 | 582 | 832 | 815 | 771 | 44 | 94.6% (92.8%–96.0%, n=815) |
| Llama 4 Maverick | 791 | 1085 | 1071 | 989 | 82 | 92.3% (90.6%–93.8%, n=1071) |
| Mistral Large | 554 | 1149 | 1135 | 951 | 184 | 83.8% (81.5%–85.8%, n=1135) |
| GPT-5 (OpenRouter) | 581 | 1117 | 1052 | 757 | 295 | 72.0% (69.2%–74.6%, n=1052) |
| GPT-5.4 | 570 | 1377 | 1095 | 517 | 578 | 47.2% (44.3%–50.2%, n=1095) |
| GPT-5 mini | 613 | 1106 | 1077 | 915 | 162 | 85.0% (82.7%–87.0%, n=1077) |
| Grok 4.6 | 648 | 1324 | 1092 | 502 | 590 | 46.0% (43.0%–48.9%, n=1092) |
| prompt 5 (gpt-5, Azure) | 591 | 1315 | 1138 | 928 | 210 | 81.5% (79.2%–83.7%, n=1138) |
| NER baseline | 381 | 1118 | 1115 | 1115 | 0 | 100.0% (99.7%–100.0%, n=1115) |

## Rates

| run | with snippet | quotable | grounded | unsupported |
| --- | ---: | --- | --- | --- |
| Claude Haiku 4.5 | 100.0% | 51.5% (48.2%–54.9%, n=842) | 91.0% (88.8%–92.7%, n=842) | 9.0% (7.3%–11.2%, n=842) |
| Claude Opus 5 | 100.0% | 85.6% (83.0%–87.9%, n=801) | 99.9% (99.3%–100.0%, n=801) | 0.1% (0.0%–0.7%, n=801) |
| Claude Sonnet 5 | 100.0% | 90.8% (88.7%–92.6%, n=828) | 100.0% (99.5%–100.0%, n=828) | 0.0% (0.0%–0.5%, n=828) |
| DeepSeek V3.1 | 100.0% | 94.6% (92.8%–96.0%, n=815) | 99.9% (99.3%–100.0%, n=815) | 0.1% (0.0%–0.7%, n=815) |
| Llama 4 Maverick | 100.0% | 92.3% (90.6%–93.8%, n=1071) | 99.7% (99.2%–99.9%, n=1071) | 0.3% (0.1%–0.8%, n=1071) |
| Mistral Large | 100.0% | 83.8% (81.5%–85.8%, n=1135) | 96.9% (95.7%–97.8%, n=1135) | 3.1% (2.2%–4.3%, n=1135) |
| GPT-5 (OpenRouter) | 100.0% | 72.0% (69.2%–74.6%, n=1052) | 97.7% (96.6%–98.5%, n=1052) | 2.3% (1.5%–3.4%, n=1052) |
| GPT-5.4 | 100.0% | 47.2% (44.3%–50.2%, n=1095) | 87.4% (85.3%–89.2%, n=1095) | 12.6% (10.8%–14.7%, n=1095) |
| GPT-5 mini | 100.0% | 85.0% (82.7%–87.0%, n=1077) | 97.4% (96.3%–98.2%, n=1077) | 2.6% (1.8%–3.7%, n=1077) |
| Grok 4.6 | 100.0% | 46.0% (43.0%–48.9%, n=1092) | 93.5% (91.9%–94.8%, n=1092) | 6.5% (5.2%–8.1%, n=1092) |
| prompt 5 (gpt-5, Azure) | 100.0% | 81.5% (79.2%–83.7%, n=1138) | 96.2% (94.9%–97.2%, n=1138) | 3.8% (2.8%–5.1%, n=1138) |
| NER baseline | 100.0% | 100.0% (99.7%–100.0%, n=1115) | 100.0% (99.7%–100.0%, n=1115) | 0.0% (0.0%–0.3%, n=1115) |

## Grade counts

| run | verbatim | verbatim_elided | near_verbatim | paraphrase | weak | unsupported | cross_script | cross_language | no_content |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Claude Haiku 4.5 | 347 | 1 | 86 | 332 | 73 | 3 | 36 | 74 | 0 |
| Claude Opus 5 | 584 | 53 | 49 | 114 | 1 | 0 | 5 | 17 | 0 |
| Claude Sonnet 5 | 664 | 44 | 44 | 76 | 0 | 0 | 3 | 12 | 0 |
| DeepSeek V3.1 | 720 | 8 | 43 | 43 | 1 | 0 | 10 | 7 | 0 |
| Llama 4 Maverick | 914 | 27 | 48 | 79 | 2 | 1 | 3 | 11 | 0 |
| Mistral Large | 829 | 34 | 88 | 149 | 18 | 17 | 0 | 14 | 0 |
| GPT-5 (OpenRouter) | 601 | 81 | 75 | 271 | 21 | 3 | 16 | 49 | 0 |
| GPT-5.4 | 387 | 16 | 114 | 440 | 131 | 7 | 162 | 120 | 0 |
| GPT-5 mini | 775 | 56 | 84 | 134 | 23 | 5 | 3 | 26 | 0 |
| Grok 4.6 | 389 | 4 | 109 | 519 | 67 | 4 | 23 | 209 | 0 |
| prompt 5 (gpt-5, Azure) | 721 | 143 | 64 | 167 | 41 | 2 | 128 | 49 | 0 |
| NER baseline | 1115 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 |

## Figures quoted in snippets

A snippet is clean when every digit string in it also occurs in the document. This survives paraphrase, which is why it is reported apart from the grade.

| run | snippets with a figure | clean | figures matched |
| --- | ---: | --- | --- |
| Claude Haiku 4.5 | 677 | 97.3% (95.8%–98.3%, n=677) | 98.1% (1192) |
| Claude Opus 5 | 648 | 98.0% (96.6%–98.8%, n=648) | 98.8% (1201) |
| Claude Sonnet 5 | 647 | 97.5% (96.0%–98.5%, n=647) | 98.5% (1144) |
| DeepSeek V3.1 | 654 | 98.9% (97.8%–99.5%, n=654) | 99.1% (1323) |
| Llama 4 Maverick | 914 | 96.2% (94.7%–97.2%, n=914) | 98.2% (2024) |
| Mistral Large | 804 | 96.5% (95.0%–97.6%, n=804) | 97.6% (1600) |
| GPT-5 (OpenRouter) | 806 | 98.1% (97.0%–98.9%, n=806) | 98.6% (1400) |
| GPT-5.4 | 871 | 97.5% (96.2%–98.3%, n=871) | 98.5% (1516) |
| GPT-5 mini | 886 | 98.9% (97.9%–99.4%, n=886) | 99.4% (1860) |
| Grok 4.6 | 968 | 97.8% (96.7%–98.6%, n=968) | 98.6% (1844) |
| prompt 5 (gpt-5, Azure) | 860 | 98.1% (97.0%–98.9%, n=860) | 98.6% (1520) |
| NER baseline | 723 | 98.6% (97.5%–99.2%, n=723) | 99.5% (2000) |

## Null check

Every snippet re-scored against a random *other* document in the set (seed 42). This is the floor the rates above are measured from: what the matcher finds in text that cannot contain the answer.

- snippets re-scored: 13041
- called quotable anyway: 14 (0.1%)
- called grounded anyway: 44 (0.3%)

## Lowest-coverage snippets

The bottom of each run, by content-word coverage. These are the candidate fabrications; a document id is given so each can be checked by hand. Two classes dominate them: meta-commentary written in place of evidence ("Explicit date, location, and impact"), and quotations from sources whose stored text is encoding-damaged.

**Claude Haiku 4.5**

- `197f7322c358` unsupported, coverage 31% — Baseline comparison showing greater fatality toll prior to implementation of inclusive communication and community preparedness strategies.
- `6949e79462e5` unsupported, coverage 43% — Case study for space-based technology in disaster assessment applications
- `d79139dbf7f9` unsupported, coverage 43% — Bab El Oued floods cited as catalyst for legislative reforms
- `197f7322c358` weak, coverage 50% — Historical example illustrating gendered vulnerability to disasters.

**Claude Opus 5**

- `8b41892a88c5` weak, coverage 71% — Section titled 'The Alabama Tornado Outbreak of April 27, 2011'

**DeepSeek V3.1**

- `9168470c06bc` weak, coverage 71% — Text references wildfires in California including Woolsey Fire.

**Llama 4 Maverick**

- `7b4674fa394f` unsupported, coverage 44% — more than 50 million people were affected by a record number of floods, droughts, wildfires and storms
- `7b4674fa394f` weak, coverage 67% — Evacuating populations from the path of cyclones, hurricanes and wildfires, for example, became far more dangerous with the threat of contagion.
- `68764ca1e162` weak, coverage 71% — The Waldo Canyon Fire occurred on June 26-27, 2012.

**Mistral Large**

- `e757f526ff42` unsupported, coverage 0% — 2004 event explicitly mentioned with impacts
- `e757f526ff42` unsupported, coverage 0% — Explicit date and location with impact numbers
- `e757f526ff42` unsupported, coverage 0% — Explicit date, location, and impact details
- `e757f526ff42` unsupported, coverage 0% — Explicit date, location, and impact

**GPT-5 (OpenRouter)**

- `e757f526ff42` unsupported, coverage 0% — 2004 appears on the timeline for this event
- `e757f526ff42` unsupported, coverage 0% — 2006 appears on the timeline for this event
- `e757f526ff42` unsupported, coverage 0% — 2009 appears on the timeline for this event
- `36e764048b3f` weak, coverage 50% — Vrancea and Balkan seismic zones noted as regional risk context

**GPT-5.4**

- `ef3284a19a8c` unsupported, coverage 14% — Croatian text says the earthquake had "catastrophic consequences"
- `3d46c98a726c` unsupported, coverage 29% — Nearby text explicitly frames these incidents as occurring in 2010.
- `3fafceebee26` unsupported, coverage 33% — The text discusses casualties and vulnerability in relation to this event.
- `ef3284a19a8c` unsupported, coverage 40% — Port-au-Prince is explicitly identified as an affected city

**GPT-5 mini**

- `2afe9b949a70` unsupported, coverage 40% — Included in the document's significant events listing.
- `2afe9b949a70` unsupported, coverage 43% — Included in the document's table of significant natural catastrophes 1980–2010.
- `2afe9b949a70` unsupported, coverage 43% — Listed among the document's significant catastrophes worldwide 1980–2010.
- `2afe9b949a70` unsupported, coverage 43% — Included in the document's list of significant natural catastrophes 1980–2010.

**Grok 4.6**

- `2afe9b949a70` unsupported, coverage 33% — Listed first among the 10 deadliest events 1980–2010.
- `75798f8af1db` unsupported, coverage 38% — 60% of women reported difficulty maintaining rent and utilities if restrictions continued.
- `2afe9b949a70` unsupported, coverage 40% — Also listed among the 10 deadliest events 1980–2010.
- `2afe9b949a70` unsupported, coverage 40% — Listed among the 10 deadliest events 1980–2010.

**prompt 5 (gpt-5, Azure)**

- `eee30cae2a71` unsupported, coverage 29% — Section title: "The Sichuan earthquake" indicates hazard and location
- `eee30cae2a71` unsupported, coverage 33% — Document issue context makes timing "this year" relative to the publication year
- `197f7322c358` weak, coverage 50% — Example provided to illustrate gender-differentiated disaster impacts
- `8b09ac233a8b` weak, coverage 50% — Document dated "27 August, 2012" supporting that "last December" refers to December 2011.

## Runs with no snippets to score

These returned nothing over these documents — an errored run has no citations to audit, which is not the same as citing badly.

- Gemini 2.5 Pro
- Qwen3 235B

