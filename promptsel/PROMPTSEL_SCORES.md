# Experiment D — retrospective accuracy assessment of the prompt-5 selection

> **This is not how prompt 5 was chosen.** On 2026-06-01 prompt 5 was selected on resolver-filtered yield (resolved event-locations at confidence 0.70–0.98, their mean confidence, and overlap with the union of prompts 1–4); no human-reference accuracy figure for it existed then (`PROMPTSEL_PROTOCOL.md` §1). This report scores the five prompts after the fact against Experiment A's blind gold on Experiment B's 80 windows. The windows were selected on prompt 5's production output, which favours p5: a deficit for p5 here is robust, an advantage is only consistent with the selection.

- Protocol: `promptsel/PROMPTSEL_PROTOCOL.md` at commit `acd5455`.
- Windows: `ablation/windows.csv` sha256 `384e684ce93ccbe0…` — all 80, event_present 44, single 10, multi 34, event_absent 36, random_negative 30, hard_negative 6, S1_no_dev_pool 78, S2_no_gold_validation 75.
- Gold: Experiment A `event_level_gold.csv` sha256 `5c66d9f9305e0be6…`, read in place; event-absent windows carry no gold events.
- Hazard normaliser `LEXICON_SHA256` `aec7441915b955d2…`, applied to every run.
- Model `openai/gpt-5`, reasoning effort medium, structured output json_schema; 2 replicates per prompt, pooled.
- Prompts: `p1` baseline_strict_location (`fc32dc937842cbbe`); `p2` case_study_high_recall (`817d7ac69ce27db3`); `p3` verification_first (`e04eead4d4dfa804`); `p4` compact_schema_focused (`7dc36a745e810ca0`); `p5` unified_verification_recall (`cfbf35634b527da4`). p1–p4 are the current multi-event texts, not the single-event texts of June.
- Experiment A reproduction (September and Azure runs on its 45 windows, R1, every counter): **ok**.
- `explode_rows` equals production's `explode_extractions` on every run: **ok**.
- Production geocoding reproduced on these windows (Azure run, every resolved uuid and confidence): **ok**.
- Runs scored: p1 r1, p1 r2, p2 r1, p2 r2, p3 r1, p3 r2, p4 r1, p4 r2, p5 r1, p5 r2. Windows in every contrast: 80.

_Intervals: 95% percentile window-cluster bootstrap, 2,000 resamples, one weight matrix per group shared by every prompt (paired). Δ = pk − p5. ◆ = interval excludes 0. Uncorrected for multiple comparisons. Judge every Δ against the replicate noise in §12._

## 1. Coverage and cost

| Run | Returned | Errored | Absent | Events | Failed calls | Cost | Providers |
|---|---:|---:|---:|---:|---:|---:|---|
| p1 r1 | 80 | 0 | 0 | 136 | 0 | $2.52 | OpenAI 80 |
| p1 r2 | 80 | 0 | 0 | 141 | 0 | $2.63 | OpenAI 80 |
| p2 r1 | 80 | 0 | 0 | 133 | 0 | $2.52 | OpenAI 80 |
| p2 r2 | 80 | 0 | 0 | 135 | 0 | $2.73 | OpenAI 80 |
| p3 r1 | 80 | 0 | 0 | 108 | 0 | $2.56 | OpenAI 80 |
| p3 r2 | 80 | 0 | 0 | 104 | 0 | $2.60 | OpenAI 80 |
| p4 r1 | 80 | 0 | 0 | 135 | 0 | $2.65 | OpenAI 80 |
| p4 r2 | 80 | 0 | 0 | 138 | 0 | $2.62 | OpenAI 80 |
| p5 r1 | 80 | 0 | 0 | 133 | 0 | $2.80 | OpenAI 80 |
| p5 r2 | 80 | 0 | 0 | 136 | 0 | $2.78 | OpenAI 80 |
| Exp B full r1 | 80 | 0 | 0 | – | – | – | – |
| Exp B full r2 | 80 | 0 | 0 | – | – | – | – |
| GPT-5 Sept (OpenRouter) | 80 | 0 | 0 | – | – | – | – |
| prompt 5 (gpt-5, Azure) — production | 80 | 0 | 0 | – | – | – | – |

## 2. Primary outcomes (R2, all windows)

| Prompt | Detection F1 | Δ Detection F1 | Pooled attribute F1 | Δ Pooled attribute F1 |
|---|---|---|---|---|
| `p1` | 53.8% (45.2%–62.6%) | +0.4 pp (-3.4 to +3.9) | 61.6% (55.6%–68.3%) | +0.5 pp (-2.6 to +3.2) |
| `p2` | 53.6% (46.0%–61.8%) | +0.2 pp (-3.7 to +4.4) | 61.2% (55.5%–67.7%) | +0.2 pp (-3.5 to +3.5) |
| `p3` | 48.9% (41.9%–56.3%) | -4.4 pp (-10.1 to +0.0) | 56.7% (51.3%–62.4%) | -4.3 pp (-9.1 to -0.6) ◆ |
| `p4` | 56.4% (50.2%–63.4%) | +3.1 pp (-1.1 to +7.5) | 63.4% (58.3%–68.8%) | +2.3 pp (-0.9 to +5.4) |
| `p5` | 53.3% (45.2%–62.1%) | — | 61.0% (55.1%–67.9%) | — |

| Prompt | Detection P | Δ Detection P | Detection R | Δ Detection R |
|---|---|---|---|---|
| `p1` | 60.3% (47.1%–73.5%) | -0.3 pp (-3.4 to +3.3) | 48.5% (39.1%–60.3%) | +0.9 pp (-3.6 to +4.9) |
| `p2` | 61.2% (48.1%–75.7%) | +0.6 pp (-5.1 to +7.0) | 47.6% (39.1%–58.2%) | +0.0 pp (-4.1 to +4.1) |
| `p3` | 63.7% (50.7%–77.2%) | +3.1 pp (-2.5 to +8.4) | 39.7% (32.6%–48.6%) | -7.9 pp (-14.7 to -3.2) ◆ |
| `p4` | 63.7% (52.1%–76.0%) | +3.1 pp (-1.8 to +8.8) | 50.6% (44.0%–60.2%) | +2.9 pp (-2.3 to +7.5) |
| `p5` | 60.6% (48.2%–73.3%) | — | 47.6% (38.6%–59.5%) | — |

## 3. Reading rules (protocol §10)

**Selection verdict: not contradicted.**

| Predecessor | Precision/recall cell | p5 resolved-better on | pk resolved-better on | Equivalent (±5 pp) on | Bridge |
|---|---|---|---|---|---|
| `p1` | not distinguishable | – | – | det_f1, pooled_f1 | in-band yield not distinguishable: in-band yield difference not resolved |
| `p2` | not distinguishable | – | – | det_f1, pooled_f1 | in-band yield not distinguishable: in-band yield difference not resolved |
| `p3` | p5 higher recall, no detectable precision cost | pooled_f1 | – | – | yield tracked validity: p5 has resolved-higher in-band and valid in-band yield; yield precision not resolved |
| `p4` | not distinguishable | – | – | – | in-band yield not distinguishable: in-band yield difference not resolved |

Under R1 (S4) the selection verdict is **not contradicted**.

## 4. Event-level detail (R2, all windows)

| Prompt | CRC | Δ CRC | CRR | Δ CRR | Attribute F1 | Δ Attribute F1 |
|---|---|---|---|---|---|---|
| `p1` | 52.7% (40.3%–65.5%) | +0.3 pp (-4.1 to +5.0) | 42.4% (32.6%–54.0%) | +1.2 pp (-3.6 to +6.3) | 49.7% (41.9%–58.0%) | +1.5 pp (-2.1 to +4.6) |
| `p2` | 53.0% (39.5%–67.6%) | +0.6 pp (-4.9 to +7.4) | 41.2% (33.3%–50.5%) | +0.0 pp (-4.1 to +4.0) | 48.9% (42.1%–56.9%) | +0.7 pp (-2.5 to +4.1) |
| `p3` | 55.2% (42.9%–68.6%) | +2.8 pp (-4.1 to +9.1) | 34.4% (28.2%–41.9%) | -6.8 pp (-14.2 to -1.1) ◆ | 44.6% (38.7%–51.0%) | -3.7 pp (-9.7 to +1.1) |
| `p4` | 54.6% (42.1%–67.0%) | +2.2 pp (-3.0 to +7.9) | 43.2% (36.8%–51.9%) | +2.1 pp (-4.1 to +7.1) | 51.4% (45.0%–58.5%) | +3.2 pp (-0.6 to +6.9) |
| `p5` | 52.4% (40.2%–65.3%) | — | 41.2% (31.9%–52.5%) | — | 48.2% (40.5%–56.5%) | — |

| Prompt | Pooled hazard | Δ Pooled hazard | Pooled year | Δ Pooled year | Pooled location | Δ Pooled location |
|---|---|---|---|---|---|---|
| `p1` | 74.1% (67.6%–80.3%) | -2.4 pp (-6.3 to +0.9) | 72.7% (64.1%–81.4%) | +0.7 pp (-4.1 to +5.0) | 51.1% (44.2%–58.6%) | +1.6 pp (-1.6 to +4.4) |
| `p2` | 73.3% (67.3%–79.4%) | -3.1 pp (-7.2 to +0.5) | 71.9% (64.0%–80.1%) | -0.2 pp (-4.8 to +4.5) | 51.4% (45.2%–58.3%) | +1.9 pp (-1.6 to +5.1) |
| `p3` | 73.0% (66.8%–78.9%) | -3.5 pp (-8.5 to +1.1) | 64.5% (54.9%–73.2%) | -7.5 pp (-15.9 to -0.8) ◆ | 46.4% (40.8%–52.5%) | -3.1 pp (-7.2 to +0.1) |
| `p4` | 76.1% (70.1%–81.9%) | -0.4 pp (-3.3 to +2.0) | 73.3% (65.6%–81.4%) | +1.2 pp (-2.6 to +5.0) | 53.4% (47.3%–59.7%) | +3.9 pp (-0.7 to +8.1) |
| `p5` | 76.4% (70.5%–82.6%) | — | 72.0% (63.9%–80.6%) | — | 49.5% (42.9%–57.3%) | — |

## 5. By window group (R2)

**event_present**

| Prompt | Detection P | Δ Detection P | Detection R | Δ Detection R | Pooled F1 | Δ Pooled F1 |
|---|---|---|---|---|---|---|
| `p1` | 72.0% (60.0%–83.6%) | +0.5 pp (-2.6 to +4.1) | 48.5% (38.5%–60.6%) | +0.9 pp (-3.4 to +5.0) | 65.9% (59.7%–72.8%) | +0.9 pp (-2.4 to +3.5) |
| `p2` | 74.9% (64.4%–86.1%) | +3.4 pp (-2.1 to +10.2) | 47.6% (38.8%–58.1%) | +0.0 pp (-4.1 to +4.1) | 65.9% (60.9%–71.7%) | +0.9 pp (-2.4 to +4.0) |
| `p3` | 73.8% (62.4%–84.8%) | +2.3 pp (-3.3 to +7.0) | 39.7% (32.8%–48.7%) | -7.9 pp (-14.4 to -3.2) ◆ | 59.4% (53.9%–65.2%) | -5.6 pp (-10.4 to -1.7) ◆ |
| `p4` | 74.7% (63.6%–85.7%) | +3.2 pp (-3.0 to +10.4) | 50.6% (43.6%–60.3%) | +2.9 pp (-2.1 to +7.3) | 67.5% (62.8%–72.9%) | +2.5 pp (-0.9 to +5.6) |
| `p5` | 71.5% (59.2%–83.7%) | — | 47.6% (38.2%–59.4%) | — | 65.0% (58.6%–72.1%) | — |

**single**

| Prompt | Detection P | Δ Detection P | Detection R | Δ Detection R | Pooled F1 | Δ Pooled F1 |
|---|---|---|---|---|---|---|
| `p1` | 42.1% (21.4%–88.9%) | -1.5 pp (-9.9 to +3.2) | 70.0% (40.0%–100.0%) | -10.0 pp (-30.0 to +0.0) | 67.0% (51.5%–84.0%) | -0.7 pp (-12.6 to +5.7) |
| `p2` | 62.1% (39.0%–100.0%) | +18.5 pp (-2.9 to +26.9) | 80.0% (50.0%–100.0%) | +0.0 pp (+0.0 to +0.0) | 70.2% (57.1%–83.8%) | +2.5 pp (-8.0 to +11.1) |
| `p3` | 56.0% (32.0%–100.0%) | +12.4 pp (+2.9 to +26.2) ◆ | 70.0% (40.0%–100.0%) | -10.0 pp (-30.0 to +0.0) | 65.1% (51.4%–76.9%) | -2.6 pp (-20.4 to +7.2) |
| `p4` | 59.3% (35.7%–90.9%) | +15.7 pp (-1.1 to +21.5) | 70.0% (40.0%–100.0%) | -10.0 pp (-30.0 to +0.0) | 68.1% (54.1%–81.3%) | +0.5 pp (-14.3 to +8.4) |
| `p5` | 43.6% (23.5%–90.0%) | — | 80.0% (50.0%–100.0%) | — | 67.7% (54.3%–83.2%) | — |

**multi**

| Prompt | Detection P | Δ Detection P | Detection R | Δ Detection R | Pooled F1 | Δ Pooled F1 |
|---|---|---|---|---|---|---|
| `p1` | 77.8% (67.6%–87.9%) | +0.6 pp (-2.7 to +4.9) | 47.2% (37.3%–59.0%) | +1.6 pp (-2.7 to +5.8) | 65.7% (59.6%–73.0%) | +1.1 pp (-2.6 to +3.9) |
| `p2` | 76.8% (65.9%–88.7%) | -0.4 pp (-3.8 to +4.9) | 45.6% (36.8%–55.6%) | +0.0 pp (-4.3 to +4.2) | 65.3% (59.7%–71.5%) | +0.6 pp (-2.9 to +4.0) |
| `p3` | 76.6% (65.5%–86.7%) | -0.7 pp (-6.2 to +4.0) | 37.8% (30.6%–46.4%) | -7.8 pp (-14.7 to -2.9) ◆ | 58.7% (53.0%–65.0%) | -6.0 pp (-11.0 to -2.2) ◆ |
| `p4` | 76.7% (65.5%–88.1%) | -0.5 pp (-5.0 to +5.2) | 49.4% (42.5%–58.9%) | +3.8 pp (-1.2 to +8.3) | 67.4% (62.7%–73.1%) | +2.8 pp (-0.6 to +6.1) |
| `p5` | 77.2% (66.7%–87.2%) | — | 45.6% (36.1%–56.9%) | — | 64.6% (57.8%–72.1%) | — |

## 6. Event-absent windows

Every record on an event-absent window is a false positive. `S3` sets aside records whose places and year (and any evidence) are literally in the window, as a bound on how much of the false-alarm rate could be gold error. The 30 random negatives were judged with p5's empty production output visible (favours p5); the 6 hard negatives are windows where production p5 emitted an event that was rejected (counts against p5).

**event_absent**

| Prompt | False-alarm windows | Δ False-alarm windows | False-alarm S3 | Δ False-alarm S3 |
|---|---|---|---|---|
| `p1` | 18.1% (6.9%–30.6%) | +0.0 pp (-4.2 to +4.2) | 9.7% (1.4%–19.4%) | +0.0 pp (-4.2 to +4.2) |
| `p2` | 18.1% (6.9%–30.6%) | +0.0 pp (-4.2 to +4.2) | 8.3% (1.4%–18.1%) | -1.4 pp (-4.2 to +0.0) |
| `p3` | 13.9% (4.2%–25.0%) | -4.2 pp (-11.1 to +0.0) | 5.6% (0.0%–13.9%) | -4.2 pp (-11.1 to +0.0) |
| `p4` | 18.1% (6.9%–30.6%) | +0.0 pp (-4.2 to +4.2) | 9.7% (2.8%–19.4%) | +0.0 pp (-4.2 to +4.2) |
| `p5` | 18.1% (6.9%–30.6%) | — | 9.7% (2.8%–19.4%) | — |

**random_negative**

| Prompt | False-alarm windows | Δ False-alarm windows | False-alarm S3 | Δ False-alarm S3 |
|---|---|---|---|---|
| `p1` | 1.7% (0.0%–5.0%) | -1.7 pp (-5.0 to +0.0) | 0.0% (0.0%–0.0%) | +0.0 pp (+0.0 to +0.0) |
| `p2` | 1.7% (0.0%–5.0%) | -1.7 pp (-5.0 to +0.0) | 0.0% (0.0%–0.0%) | +0.0 pp (+0.0 to +0.0) |
| `p3` | 0.0% (0.0%–0.0%) | -3.3 pp (-10.0 to +0.0) | 0.0% (0.0%–0.0%) | +0.0 pp (+0.0 to +0.0) |
| `p4` | 1.7% (0.0%–5.0%) | -1.7 pp (-5.0 to +0.0) | 0.0% (0.0%–0.0%) | +0.0 pp (+0.0 to +0.0) |
| `p5` | 3.3% (0.0%–10.0%) | — | 0.0% (0.0%–0.0%) | — |

**hard_negative**

| Prompt | False-alarm windows | Δ False-alarm windows | False-alarm S3 | Δ False-alarm S3 |
|---|---|---|---|---|
| `p1` | 100.0% (100.0%–100.0%) | +8.3 pp (+0.0 to +25.0) | 58.3% (16.7%–91.7%) | +0.0 pp (-25.0 to +25.0) |
| `p2` | 100.0% (100.0%–100.0%) | +8.3 pp (+0.0 to +25.0) | 50.0% (16.7%–83.3%) | -8.3 pp (-25.0 to +0.0) |
| `p3` | 83.3% (66.7%–100.0%) | -8.3 pp (-25.0 to +0.0) | 33.3% (0.0%–66.7%) | -25.0 pp (-58.3 to +0.0) |
| `p4` | 100.0% (100.0%–100.0%) | +8.3 pp (+0.0 to +25.0) | 58.3% (16.7%–91.7%) | +0.0 pp (-25.0 to +25.0) |
| `p5` | 91.7% (75.0%–100.0%) | — | 58.3% (16.7%–91.7%) | — |

Detection with the S3 bound, all windows:

| Prompt | Detection P (S3) | Δ Detection P (S3) | Detection F1 (S3) | Δ Detection F1 (S3) |
|---|---|---|---|---|
| `p1` | 67.1% (54.8%–78.7%) | -0.8 pp (-5.8 to +3.9) | 56.3% (47.8%–65.1%) | +0.3 pp (-3.8 to +4.0) |
| `p2` | 70.1% (59.3%–81.4%) | +2.2 pp (-4.5 to +9.6) | 56.7% (49.6%–64.7%) | +0.7 pp (-3.2 to +5.0) |
| `p3` | 69.2% (56.8%–81.6%) | +1.3 pp (-6.3 to +8.2) | 50.5% (43.3%–57.9%) | -5.5 pp (-11.6 to -0.7) ◆ |
| `p4` | 71.3% (60.8%–81.5%) | +3.4 pp (-2.8 to +10.4) | 59.2% (53.1%–66.2%) | +3.2 pp (-1.3 to +7.9) |
| `p5` | 67.9% (56.0%–79.5%) | — | 56.0% (47.6%–64.8%) | — |

## 7. Candidate yield

| Prompt | Records / window | Δ Records / window | Raw events / window | Δ Raw events / window |
|---|---|---|---|---|
| `p1` | 1.73 (1.29–2.26) | +0.05 (-0.04 to +0.14) | 1.73 (1.29–2.26) | +0.05 (-0.04 to +0.14) |
| `p2` | 1.68 (1.20–2.24) | -0.01 (-0.19 to +0.19) | 1.68 (1.20–2.24) | -0.01 (-0.19 to +0.19) |
| `p3` | 1.32 (0.95–1.74) | -0.36 (-0.51 to -0.22) ◆ | 1.32 (0.95–1.74) | -0.36 (-0.51 to -0.22) ◆ |
| `p4` | 1.71 (1.25–2.24) | +0.03 (-0.15 to +0.21) | 1.72 (1.26–2.25) | +0.04 (-0.14 to +0.23) |
| `p5` | 1.68 (1.27–2.17) | — | 1.68 (1.27–2.17) | — |

| Prompt | Dropped by the post-filter | not verifiable | low confidence | missing field | duplicate | Exact-vocabulary hazard | ISO date |
|---|---|---|---|---|---|---|---|
| `p1` | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 85.5% |
| `p2` | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 85.1% |
| `p3` | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 86.0% |
| `p4` | 0.7% | 0.0% | 0.0% | 0.0% | 0.7% | 100.0% | 87.5% |
| `p5` | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 78.3% |

## 8. Evidence support

Snippet grades are `citation_quality.classify` against the window; held-out grades are out of the denominator. p1–p4 allow paraphrased snippets ("no long quotes"), so snippet grades partly measure style. Attribute traceability — every place word-bounded in the window, and a year that appears in it — does not depend on snippets.

| Prompt | Quotable snippets | Δ Quotable snippets | Records with a quotable snippet | Δ Records with a quotable snippet | Unsupported snippets | Δ Unsupported snippets |
|---|---|---|---|---|---|---|
| `p1` | 67.6% (59.7%–75.4%) | -3.7 pp (-9.8 to +2.8) | 83.4% (75.7%–89.9%) | -0.6 pp (-7.7 to +6.2) | 0.0% (0.0%–0.0%) | -0.2 pp (-0.7 to +0.0) |
| `p2` | 69.4% (61.8%–76.6%) | -1.9 pp (-6.9 to +3.7) | 84.3% (78.5%–90.1%) | +0.3 pp (-4.8 to +6.1) | 0.2% (0.0%–0.7%) | +0.0 pp (-0.6 to +0.6) |
| `p3` | 65.7% (55.2%–75.7%) | -5.6 pp (-13.6 to +2.4) | 79.2% (66.4%–90.9%) | -4.8 pp (-16.2 to +7.1) | 0.0% (0.0%–0.0%) | -0.2 pp (-0.7 to +0.0) |
| `p4` | 68.8% (59.9%–76.3%) | -2.5 pp (-8.4 to +3.7) | 82.8% (76.0%–88.9%) | -1.2 pp (-7.0 to +4.6) | 0.4% (0.0%–1.3%) | +0.2 pp (-0.6 to +1.2) |
| `p5` | 71.3% (63.3%–78.5%) | — | 84.0% (77.0%–89.9%) | — | 0.2% (0.0%–0.7%) | — |

| Prompt | Places literal | Δ Places literal | Year literal | Δ Year literal | Both | Δ Both |
|---|---|---|---|---|---|---|
| `p1` | 85.6% (78.1%–92.5%) | -0.7 pp (-6.2 to +4.2) | 98.2% (95.9%–99.7%) | +0.8 pp (-1.3 to +3.8) | 84.1% (76.8%–90.9%) | +0.1 pp (-5.8 to +5.8) |
| `p2` | 80.6% (68.7%–89.7%) | -5.6 pp (-10.2 to -0.7) ◆ | 98.1% (95.8%–100.0%) | +0.7 pp (-1.2 to +3.8) | 79.1% (67.7%–88.2%) | -4.9 pp (-9.6 to +0.9) |
| `p3` | 88.2% (79.5%–95.7%) | +2.0 pp (-2.8 to +6.4) | 97.2% (92.8%–100.0%) | -0.2 pp (-2.8 to +1.6) | 85.4% (76.9%–93.0%) | +1.4 pp (-3.1 to +5.4) |
| `p4` | 81.7% (70.8%–91.3%) | -4.6 pp (-10.4 to +1.1) | 98.2% (95.5%–100.0%) | +0.8 pp (-0.8 to +2.9) | 80.6% (70.1%–90.1%) | -3.4 pp (-9.6 to +2.7) |
| `p5` | 86.2% (76.5%–93.8%) | — | 97.4% (93.4%–99.7%) | — | 84.0% (74.0%–92.0%) | — |

## 9. Geocoding success

Each record's places, exploded and hinted as `fonte-polygons` does, resolved once per distinct place by the production geocoder, scored with production's confidence. Success is the resolver's, not a judged geometry.

| Prompt | Places / window | Δ Places / window | Records with ≥1 place | Δ Records with ≥1 place |
|---|---|---|---|---|
| `p1` | 2.56 (1.75–3.60) | +0.04 (-0.17 to +0.21) | 1.00 (1.00–1.00) | +0.00 (+0.00 to +0.00) |
| `p2` | 2.62 (1.66–4.11) | +0.11 (-0.16 to +0.46) | 1.00 (1.00–1.00) | +0.00 (+0.00 to +0.00) |
| `p3` | 1.84 (1.21–2.66) | -0.67 (-1.11 to -0.39) ◆ | 1.00 (1.00–1.00) | +0.00 (+0.00 to +0.00) |
| `p4` | 2.52 (1.66–3.81) | +0.00 (-0.19 to +0.17) | 1.00 (1.00–1.00) | +0.00 (+0.00 to +0.00) |
| `p5` | 2.52 (1.68–3.72) | — | 1.00 (1.00–1.00) | — |

| Prompt | Resolved | Δ Resolved | In band 0.70–0.98 | Δ In band 0.70–0.98 |
|---|---|---|---|---|
| `p1` | 86.1% (78.7%–92.1%) | +1.2 pp (-2.3 to +4.0) | 52.3% (41.0%–62.6%) | -0.5 pp (-4.0 to +3.2) |
| `p2` | 89.3% (84.4%–92.6%) | +4.4 pp (-0.5 to +9.6) | 55.0% (41.8%–65.0%) | +2.1 pp (-4.8 to +6.4) |
| `p3` | 86.4% (79.8%–91.6%) | +1.6 pp (-3.5 to +6.0) | 51.9% (41.2%–59.7%) | -1.0 pp (-5.6 to +4.4) |
| `p4` | 91.3% (86.7%–94.8%) | +6.5 pp (+1.6 to +12.9) ◆ | 54.8% (42.3%–64.9%) | +2.0 pp (-4.0 to +6.2) |
| `p5` | 84.9% (77.8%–90.3%) | — | 52.9% (41.2%–62.3%) | — |

| Prompt | Mean confidence (resolved) | Δ Mean confidence (resolved) | Mean confidence (in band) | Δ Mean confidence (in band) |
|---|---|---|---|---|
| `p1` | 0.769 (0.726–0.815) | +0.003 (-0.021 to +0.026) | 0.841 (0.810–0.879) | +0.008 (+0.002 to +0.015) ◆ |
| `p2` | 0.751 (0.713–0.789) | -0.015 (-0.046 to +0.010) | 0.831 (0.801–0.874) | -0.002 (-0.010 to +0.013) |
| `p3` | 0.767 (0.730–0.811) | +0.001 (-0.017 to +0.023) | 0.837 (0.810–0.875) | +0.005 (-0.008 to +0.014) |
| `p4` | 0.764 (0.727–0.806) | -0.001 (-0.027 to +0.020) | 0.831 (0.802–0.874) | -0.001 (-0.006 to +0.008) |
| `p5` | 0.766 (0.734–0.803) | — | 0.832 (0.805–0.873) | — |

## 10. Yield and validity (R2)

In-band event-locations per window is the statistic prompt 5 was selected on in June. Here each one is labelled by its record: **valid** if the record links to a gold event, **invalid** otherwise (an unmatched record, or any record on an event-absent window). Yield precision = valid / in band.

| Prompt | In band / window | Δ In band / window | Valid in band / window | Δ Valid in band / window | Invalid in band / window | Δ Invalid in band / window |
|---|---|---|---|---|---|---|
| `p1` | 1.34 (0.79–2.17) | +0.01 (-0.14 to +0.14) | 0.84 (0.54–1.18) | +0.03 (-0.07 to +0.12) | 0.50 (0.14–1.10) | -0.03 (-0.14 to +0.06) |
| `p2` | 1.44 (0.74–2.61) | +0.11 (-0.12 to +0.40) | 0.79 (0.49–1.13) | -0.02 (-0.18 to +0.13) | 0.66 (0.13–1.55) | +0.13 (-0.01 to +0.34) |
| `p3` | 0.96 (0.55–1.51) | -0.38 (-0.76 to -0.14) ◆ | 0.62 (0.38–0.89) | -0.18 (-0.29 to -0.09) ◆ | 0.33 (0.09–0.69) | -0.19 (-0.53 to +0.00) |
| `p4` | 1.38 (0.76–2.38) | +0.05 (-0.09 to +0.21) | 0.81 (0.53–1.11) | +0.00 (-0.12 to +0.11) | 0.57 (0.14–1.33) | +0.05 (-0.03 to +0.14) |
| `p5` | 1.33 (0.75–2.23) | — | 0.81 (0.53–1.11) | — | 0.53 (0.12–1.22) | — |

| Prompt | Yield precision | Δ Yield precision | Record yield precision | Δ Record yield precision | Windows with ≥1 in band | Δ Windows with ≥1 in band |
|---|---|---|---|---|---|---|
| `p1` | 62.6% (46.2%–84.9%) | +2.1 pp (-4.8 to +6.3) | 66.9% (51.0%–83.5%) | +0.7 pp (-5.1 to +6.9) | 43.1% (34.4%–51.9%) | +0.6 pp (-3.1 to +3.8) |
| `p2` | 54.5% (38.5%–83.7%) | -6.0 pp (-12.6 to +1.2) | 61.2% (45.6%–81.8%) | -5.0 pp (-12.2 to +2.9) | 40.6% (32.5%–48.8%) | -1.9 pp (-8.1 to +4.4) |
| `p3` | 65.4% (49.0%–86.5%) | +4.8 pp (-6.4 to +11.3) | 67.0% (50.0%–84.3%) | +0.8 pp (-6.5 to +7.8) | 36.2% (27.5%–45.0%) | -6.2 pp (-10.6 to -2.5) ◆ |
| `p4` | 58.4% (42.3%–83.7%) | -2.2 pp (-6.5 to +3.0) | 64.4% (49.7%–81.9%) | -1.8 pp (-6.7 to +4.6) | 42.5% (34.4%–50.6%) | +0.0 pp (-4.4 to +4.4) |
| `p5` | 60.6% (43.0%–85.7%) | — | 66.2% (50.0%–83.2%) | — | 42.5% (33.8%–51.2%) | — |

## 11. The June criterion, recomputed on these windows (descriptive)

June's rule (`scripts/compare_resolution_filtered_runs.py`): in-band rows per prompt, the p1–p4 union deduplicated on asset‖hazard‖location‖start‖end, and its exact-key overlap with p5. A key is valid if any record behind it links to a gold event (R2). June ran on 400 documents, single-event p1–p4 and Azure; these are 80 windows, multi-event p1–p4 and OpenRouter, so the two are not comparable figure for figure.

**Replicate r1**

| Prompt | In-band rows | Windows | Mean confidence | Valid share |
|---|---:|---:|---:|---|
| `p1` (prompt01) | 110 | 33 | 0.835 | 61.8% |
| `p2` (prompt02) | 113 | 33 | 0.830 | 54.0% |
| `p3` (prompt03) | 69 | 29 | 0.850 | 69.6% |
| `p4` (prompt04) | 103 | 35 | 0.836 | 57.3% |
| `p5` (prompt05) | 100 | 33 | 0.837 | 61.0% |

Union p1–p4: 231 keys over 39 windows, 55.8% valid; p5: 100 keys, 61.0% valid. Both 83, p5 only 17 (82.4% valid), union only 148 (55.4% valid); Jaccard 0.335.

**Replicate r2**

| Prompt | In-band rows | Windows | Mean confidence | Valid share |
|---|---:|---:|---:|---|
| `p1` (prompt01) | 104 | 36 | 0.846 | 63.5% |
| `p2` (prompt02) | 118 | 32 | 0.831 | 55.1% |
| `p3` (prompt03) | 84 | 29 | 0.826 | 61.9% |
| `p4` (prompt04) | 118 | 33 | 0.827 | 59.3% |
| `p5` (prompt05) | 113 | 35 | 0.828 | 60.2% |

Union p1–p4: 201 keys over 40 windows, 62.2% valid; p5: 113 keys, 60.2% valid. Both 93, p5 only 20 (85.0% valid), union only 108 (68.5% valid); Jaccard 0.421.

June, as recorded (`selection_summary.csv`, `retrieval_overlap_summary.csv`):

| June label | In-band rows | Documents | Mean confidence |
|---|---:|---:|---:|
| prompt01 | 58 | 33 | 0.813 |
| prompt02 | 67 | 51 | 0.834 |
| prompt03 | 64 | 40 | 0.839 |
| prompt04 | 61 | 37 | 0.833 |
| prompt05 | 134 | 56 | 0.853 |
| prompt01-04_union | 150 | 62 | 0.826 |

Union 150, p5 134, both 70, p5 only 64, union only 80; Jaccard 0.327.

## 12. Rankings, replicate noise and cross-session drift

| Rank by | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| In band / window (June's yield) | `p2` | `p4` | `p1` | `p5` | `p3` |
| Records / window | `p1` | `p4` | `p5` | `p2` | `p3` |
| Detection F1 | `p4` | `p1` | `p2` | `p5` | `p3` |
| Pooled attribute F1 | `p4` | `p1` | `p2` | `p5` | `p3` |
| Yield precision | `p3` | `p1` | `p5` | `p4` | `p2` |

Ranks are point estimates; whether two adjacent prompts differ is in §2–§10.

Replicate 2 − replicate 1 (R2, all windows):

| Prompt | Detection F1 | Pooled F1 | In band / window |
|---|---|---|---|
| `p1` | +1.1 pp (-3.2 to +6.3) | +0.3 pp (-2.9 to +3.6) | -0.07 (-0.51 to +0.25) |
| `p2` | +3.6 pp (-1.5 to +8.8) | +1.8 pp (-2.5 to +6.3) | +0.06 (-0.14 to +0.24) |
| `p3` | -1.5 pp (-6.9 to +3.2) | -0.5 pp (-4.7 to +3.1) | +0.19 (-0.16 to +0.76) |
| `p4` | +2.1 pp (-2.7 to +6.3) | -1.5 pp (-5.3 to +2.2) | +0.19 (-0.05 to +0.50) |
| `p5` | +2.4 pp (-1.2 to +6.7) | +3.2 pp (+0.2 to +7.0) ◆ | +0.16 (-0.12 to +0.60) |

Cross-session drift, p5 (this run) − Experiment B `full` (2026-11-01), both pooled over two replicates: detection F1 -1.3 pp (-4.4 to +1.5), pooled F1 -1.2 pp (-3.5 to +1.3), in band / window -0.07 (-0.26 to +0.10). Descriptive; `full` is never a contrast baseline.

## 13. Sensitivity

**S1 — without the 2 dev-pool windows** (R2)

| Prompt | Detection P | Δ Detection P | Detection R | Δ Detection R | Detection F1 | Δ Detection F1 | Pooled F1 | Δ Pooled F1 |
|---|---|---|---|---|---|---|---|---|
| `p1` | 59.7% (46.6%–74.2%) | +0.3 pp (-2.5 to +3.7) | 48.8% (38.8%–60.9%) | +2.1 pp (-1.2 to +5.8) | 53.7% (45.2%–63.7%) | +1.4 pp (-1.6 to +4.7) | 61.6% (55.2%–68.8%) | +1.2 pp (-1.6 to +3.6) |
| `p2` | 60.2% (46.6%–75.2%) | +0.8 pp (-4.9 to +7.9) | 47.0% (38.3%–57.2%) | +0.3 pp (-3.9 to +4.5) | 52.8% (45.2%–61.4%) | +0.5 pp (-3.3 to +4.7) | 60.7% (54.6%–67.2%) | +0.3 pp (-3.3 to +3.7) |
| `p3` | 62.6% (49.1%–76.4%) | +3.2 pp (-2.4 to +8.5) | 39.1% (32.2%–48.2%) | -7.6 pp (-14.0 to -3.2) ◆ | 48.1% (41.2%–55.9%) | -4.1 pp (-9.6 to +0.2) | 56.3% (50.9%–62.1%) | -4.1 pp (-8.9 to -0.3) ◆ |
| `p4` | 62.9% (50.9%–76.2%) | +3.5 pp (-1.6 to +9.5) | 50.3% (43.3%–59.7%) | +3.6 pp (-1.3 to +7.9) | 55.9% (49.6%–63.6%) | +3.6 pp (-0.6 to +8.1) | 63.1% (57.8%–68.7%) | +2.7 pp (-0.6 to +5.6) |
| `p5` | 59.4% (46.5%–73.4%) | — | 46.7% (37.4%–58.1%) | — | 52.3% (43.9%–61.9%) | — | 60.4% (54.1%–67.8%) | — |

**S2 — without the 5 `gold_validation` windows** (R2)

| Prompt | Detection P | Δ Detection P | Detection R | Δ Detection R | Detection F1 | Δ Detection F1 | Pooled F1 | Δ Pooled F1 |
|---|---|---|---|---|---|---|---|---|
| `p1` | 60.1% (47.6%–74.4%) | +0.9 pp (-1.6 to +4.3) | 49.7% (39.1%–62.7%) | +3.4 pp (+0.8 to +7.0) ◆ | 54.4% (45.4%–64.2%) | +2.5 pp (+0.0 to +5.6) ◆ | 62.6% (56.5%–69.7%) | +2.5 pp (+0.7 to +4.3) ◆ |
| `p2` | 60.2% (47.1%–75.8%) | +0.9 pp (-4.8 to +8.0) | 46.9% (37.8%–57.6%) | +0.6 pp (-3.6 to +4.7) | 52.7% (44.7%–61.3%) | +0.8 pp (-3.4 to +5.0) | 60.8% (54.9%–67.2%) | +0.7 pp (-3.0 to +4.0) |
| `p3` | 63.2% (50.2%–77.4%) | +4.0 pp (-1.7 to +9.9) | 39.8% (32.1%–49.2%) | -6.5 pp (-12.9 to -2.1) ◆ | 48.9% (41.4%–56.5%) | -3.1 pp (-8.5 to +1.2) | 57.2% (51.8%–63.1%) | -2.9 pp (-7.1 to +0.6) |
| `p4` | 63.5% (51.9%–76.8%) | +4.3 pp (-1.0 to +10.4) | 50.9% (43.4%–60.8%) | +4.6 pp (+0.0 to +9.0) | 56.5% (50.1%–64.2%) | +4.6 pp (+0.4 to +9.0) ◆ | 63.7% (58.6%–69.8%) | +3.6 pp (+0.7 to +6.3) ◆ |
| `p5` | 59.2% (46.4%–73.4%) | — | 46.3% (36.5%–58.3%) | — | 52.0% (43.1%–61.4%) | — | 60.1% (54.1%–67.2%) | — |

**S4 — R1, Experiment A's anchored matching** (all five emit evidence)

| Prompt | Detection P | Δ Detection P | Detection R | Δ Detection R | Detection F1 | Δ Detection F1 | CRC | Δ CRC |
|---|---|---|---|---|---|---|---|---|
| `p1` | 67.5% (54.4%–81.9%) | +0.2 pp (-2.3 to +2.5) | 54.4% (44.7%–66.7%) | +1.5 pp (-3.1 to +5.3) | 60.3% (52.2%–69.1%) | +1.0 pp (-2.6 to +3.9) | 51.3% (39.1%–64.4%) | +1.4 pp (-3.2 to +6.7) |
| `p2` | 68.7% (55.5%–83.2%) | +1.4 pp (-4.9 to +7.3) | 53.5% (43.2%–65.8%) | +0.6 pp (-4.4 to +5.9) | 60.2% (51.9%–68.8%) | +0.9 pp (-3.8 to +5.5) | 50.7% (37.9%–65.4%) | +0.9 pp (-4.7 to +7.5) |
| `p3` | 70.8% (58.0%–83.7%) | +3.5 pp (-1.1 to +8.2) | 44.1% (35.9%–54.9%) | -8.8 pp (-15.3 to -4.4) ◆ | 54.3% (47.0%–62.4%) | -4.9 pp (-10.1 to -0.7) ◆ | 51.4% (39.9%–64.1%) | +1.6 pp (-4.9 to +7.9) |
| `p4` | 70.3% (58.7%–82.8%) | +3.0 pp (-1.3 to +7.8) | 55.9% (48.2%–66.2%) | +2.9 pp (-2.2 to +6.8) | 62.3% (56.1%–69.0%) | +3.0 pp (-0.5 to +6.2) | 53.1% (40.9%–65.5%) | +3.3 pp (-2.6 to +9.7) |
| `p5` | 67.3% (54.7%–81.0%) | — | 52.9% (43.9%–64.9%) | — | 59.3% (51.8%–67.6%) | — | 49.8% (37.8%–62.7%) | — |

**S5 — other bands**

| Prompt | In [0.70, 1.0] / window | Δ In [0.70, 1.0] / window | Resolved / window | Δ Resolved / window |
|---|---|---|---|---|
| `p1` | 1.67 (1.08–2.52) | +0.05 (-0.11 to +0.19) | 2.20 (1.47–3.19) | +0.06 (-0.09 to +0.20) |
| `p2` | 1.74 (0.98–2.91) | +0.12 (-0.12 to +0.42) | 2.34 (1.46–3.74) | +0.21 (-0.05 to +0.57) |
| `p3` | 1.18 (0.75–1.73) | -0.44 (-0.83 to -0.19) ◆ | 1.59 (1.02–2.34) | -0.54 (-0.91 to -0.28) ◆ |
| `p4` | 1.74 (1.06–2.76) | +0.12 (-0.06 to +0.31) | 2.30 (1.49–3.51) | +0.16 (-0.01 to +0.35) |
| `p5` | 1.62 (1.00–2.54) | — | 2.14 (1.41–3.20) | — |

| Prompt | Yield precision [0.70, 1.0] | Δ Yield precision [0.70, 1.0] | Yield precision, any resolved | Δ Yield precision, any resolved |
|---|---|---|---|---|
| `p1` | 66.7% (50.9%–85.5%) | +2.6 pp (-3.1 to +6.5) | 63.1% (49.7%–78.9%) | +2.0 pp (-2.0 to +5.2) |
| `p2` | 59.7% (43.0%–85.4%) | -4.4 pp (-9.5 to +2.3) | 60.8% (47.9%–79.9%) | -0.3 pp (-4.5 to +5.4) |
| `p3` | 68.3% (53.4%–86.4%) | +4.2 pp (-5.2 to +10.1) | 66.3% (53.4%–80.7%) | +5.2 pp (-3.4 to +12.1) |
| `p4` | 63.4% (47.0%–84.5%) | -0.7 pp (-4.8 to +4.4) | 62.2% (49.3%–79.1%) | +1.1 pp (-1.8 to +4.9) |
| `p5` | 64.1% (47.0%–85.8%) | — | 61.1% (47.5%–78.1%) | — |

**S6 — stricter "valid"**

| Prompt | Complete-record in band / window | Δ Complete-record in band / window | Correct-place in band / window | Δ Correct-place in band / window |
|---|---|---|---|---|
| `p1` | 0.65 (0.41–0.94) | +0.13 (-0.03 to +0.36) | 0.65 (0.41–0.94) | +0.06 (-0.03 to +0.15) |
| `p2` | 0.55 (0.35–0.79) | +0.03 (-0.09 to +0.16) | 0.61 (0.38–0.86) | +0.02 (-0.10 to +0.14) |
| `p3` | 0.44 (0.26–0.65) | -0.08 (-0.18 to +0.02) | 0.48 (0.29–0.71) | -0.11 (-0.21 to +0.00) |
| `p4` | 0.58 (0.38–0.81) | +0.06 (-0.04 to +0.17) | 0.67 (0.44–0.93) | +0.08 (-0.03 to +0.19) |
| `p5` | 0.52 (0.33–0.74) | — | 0.59 (0.37–0.84) | — |

| Prompt | Yield precision, complete record | Δ Yield precision, complete record | Yield precision, correct places | Δ Yield precision, correct places |
|---|---|---|---|---|
| `p1` | 48.6% (28.1%–74.2%) | +9.6 pp (-2.3 to +23.5) | 48.6% (28.1%–74.2%) | +4.5 pp (-3.8 to +10.6) |
| `p2` | 38.1% (21.1%–66.9%) | -0.9 pp (-8.1 to +8.6) | 42.0% (22.4%–73.4%) | -2.1 pp (-8.2 to +6.1) |
| `p3` | 45.8% (28.3%–69.5%) | +6.8 pp (-6.0 to +14.8) | 50.3% (30.8%–76.8%) | +6.2 pp (-6.4 to +13.9) |
| `p4` | 42.1% (25.2%–67.7%) | +3.1 pp (-3.3 to +9.4) | 48.4% (28.7%–76.5%) | +4.3 pp (-2.0 to +11.7) |
| `p5` | 39.0% (21.0%–65.6%) | — | 44.1% (23.5%–73.0%) | — |

## 14. Hazard normalisation

| Prompt | Records relabelled | Records with an unmapped component | Top unmapped |
|---|---|---|---|
| `p1` | 0.0% | 0.0% | – |
| `p2` | 0.0% | 0.0% | – |
| `p3` | 0.0% | 0.0% | – |
| `p4` | 0.0% | 0.0% | – |
| `p5` | 0.0% | 0.0% | – |

## 15. Reference rows (not contrasted)

Experiment B's `full` replicates (prompt 5, same harness, 2026-11-01), the September OpenRouter GPT-5 prompt-5 run and the Azure production run, on the same windows. The Azure run is the one the windows were selected on.

| Run | Reading | Detection P | Detection R | Detection F1 | Pooled F1 | In band / window | Yield precision |
|---|---|---|---|---|---|---|---|
| Exp B full | R2 | 61.7% (48.5%–75.8%) | 49.1% (40.2%–60.9%) | 54.7% (46.6%–63.7%) | 62.2% (56.2%–68.9%) | 1.41 (0.76–2.43) | 55.6% (38.3%–84.2%) |
| Exp B full | R1 | 68.2% (54.7%–83.5%) | 54.4% (45.0%–66.9%) | 60.5% (52.7%–69.5%) | 62.2% (56.2%–68.9%) | 1.41 (0.76–2.43) | 59.1% (43.0%–86.9%) |
| GPT-5 Sept (OpenRouter) | R2 | 59.4% (46.6%–73.1%) | 49.4% (40.0%–60.7%) | 54.0% (45.2%–62.9%) | 63.7% (58.1%–69.7%) | 1.43 (0.75–2.55) | 55.3% (36.4%–84.5%) |
| GPT-5 Sept (OpenRouter) | R1 | 66.4% (53.6%–80.0%) | 55.3% (45.4%–67.8%) | 60.4% (52.8%–69.1%) | 63.7% (58.1%–69.7%) | 1.43 (0.75–2.55) | 57.9% (41.2%–84.4%) |
| prompt 5 (gpt-5, Azure) — production | R2 | 62.9% (51.1%–75.2%) | 48.2% (39.1%–59.9%) | 54.6% (46.6%–63.4%) | 63.5% (57.4%–70.3%) | 1.36 (0.77–2.34) | 58.7% (41.4%–83.2%) |
| prompt 5 (gpt-5, Azure) — production | R1 | 70.5% (58.5%–83.2%) | 54.1% (44.5%–67.0%) | 61.2% (53.7%–69.7%) | 63.5% (57.4%–70.3%) | 1.36 (0.77–2.34) | 60.6% (42.9%–86.2%) |

