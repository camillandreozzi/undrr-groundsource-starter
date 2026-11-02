# Experiment B — controlled ablation of prompt 5

> **Retrospective diagnostic ablation.** The windows were selected on production output (every Experiment A window because prompt 5 found an event in it) and the event-absent gold was annotated with production output visible. Differences below say which constraints matter on these windows; none is an estimate of generalisation performance.

- Protocol: `ablation/ABLATION_PROTOCOL.md` at commit `8b9e736`.
- Windows: `ablation/windows.csv` sha256 `384e684ce93ccbe0…` — all 80, event_present 44, single 10, multi 34, event_absent 36, random_negative 30, hard_negative 6, S1_no_dev_pool 78, S2_no_gold_validation 75.
- Gold: Experiment A `event_level_gold.csv` sha256 `5c66d9f9305e0be6…`, read in place; event-absent windows carry no gold events.
- Hazard normaliser `LEXICON_SHA256` `aec7441915b955d2…`, applied to every run.
- Model `openai/gpt-5`, reasoning effort medium, structured output json_schema; 2 replicates per configuration, pooled.
- Experiment A reproduction (September and Azure runs on its 45 windows, R1, every counter): **ok**.
- Runs scored: full r1, full r2, no_evidence r1, no_evidence r2, no_vocab r1, no_vocab r2, reduced_rules r1, reduced_rules r2, bare r1, bare r2. Windows in every contrast: 80.

_Intervals: 95% percentile window-cluster bootstrap, 2,000 resamples, one weight matrix per group shared by every configuration (paired). Δ = configuration − `full`. ◆ = interval excludes 0. Uncorrected for multiple comparisons. Judge every Δ against the replicate noise in §8._

## 1. Coverage and cost

| Run | Returned | Errored | Absent | Events | Failed calls | Cost | Providers |
|---|---:|---:|---:|---:|---:|---:|---|
| full r1 | 80 | 0 | 0 | 143 | 0 | $2.93 | OpenAI 80 |
| full r2 | 80 | 0 | 0 | 131 | 0 | $2.88 | OpenAI 80 |
| no_evidence r1 | 80 | 0 | 0 | 134 | 0 | $2.68 | OpenAI 80 |
| no_evidence r2 | 80 | 0 | 0 | 130 | 0 | $2.71 | OpenAI 80 |
| no_vocab r1 | 80 | 0 | 0 | 138 | 0 | $2.97 | OpenAI 80 |
| no_vocab r2 | 80 | 0 | 0 | 143 | 0 | $2.91 | OpenAI 80 |
| reduced_rules r1 | 80 | 0 | 0 | 255 | 0 | $3.30 | OpenAI 80 |
| reduced_rules r2 | 80 | 0 | 0 | 255 | 0 | $3.14 | OpenAI 80 |
| bare r1 | 80 | 0 | 0 | 265 | 0 | $3.03 | OpenAI 80 |
| bare r2 | 80 | 0 | 0 | 295 | 0 | $3.19 | OpenAI 80 |
| GPT-5 Sept (OpenRouter) | 80 | 0 | 0 | – | – | – | – |
| prompt 5 (gpt-5, Azure) — production | 80 | 0 | 0 | – | – | – | – |

## 2. Primary outcomes (R2, all windows)


| Config | Detection F1 | Δ Detection F1 | Pooled attribute F1 | Δ Pooled attribute F1 |
|---|---|---|---|---|
| `full` | 54.7% (46.6%–63.7%) | — | 62.2% (56.2%–68.9%) | — |
| `no_evidence` | 51.5% (43.3%–60.1%) | -3.2 pp (-6.9 to -0.0) ◆ | 60.0% (54.1%–66.5%) | -2.3 pp (-5.0 to +0.1) |
| `no_vocab` | 56.0% (48.2%–64.2%) | +1.3 pp (-1.6 to +4.7) | 63.7% (58.5%–69.7%) | +1.4 pp (-1.3 to +4.3) |
| `reduced_rules` | 68.6% (59.1%–76.7%) | +13.9 pp (+3.4 to +23.8) ◆ | 70.8% (63.6%–77.9%) | +8.6 pp (+3.1 to +14.1) ◆ |
| `bare` | 65.8% (55.3%–74.7%) | +11.1 pp (-0.4 to +21.6) | 68.2% (60.4%–75.3%) | +6.0 pp (-1.2 to +12.7) |

## 3. Event-level detail (R2, all windows)


| Config | Detection P | Δ Detection P | Detection R | Δ Detection R | CRC | Δ CRC | CRR | Δ CRR |
|---|---|---|---|---|---|---|---|---|
| `full` | 61.7% (48.5%–75.8%) | — | 49.1% (40.2%–60.9%) | — | 54.4% (41.9%–67.9%) | — | 43.2% (34.7%–54.1%) | — |
| `no_evidence` | 59.1% (46.0%–73.2%) | -2.6 pp (-6.5 to +1.1) | 45.6% (36.8%–56.5%) | -3.5 pp (-7.9 to -0.3) ◆ | 50.8% (38.4%–64.2%) | -3.6 pp (-7.9 to +0.7) | 39.1% (31.3%–48.6%) | -4.1 pp (-8.9 to -0.3) ◆ |
| `no_vocab` | 62.3% (51.0%–74.5%) | +0.6 pp (-5.7 to +7.5) | 50.9% (41.4%–62.9%) | +1.8 pp (-0.3 to +4.2) | 53.0% (42.4%–64.5%) | -1.4 pp (-7.6 to +5.4) | 43.2% (34.7%–54.0%) | +0.0 pp (-3.1 to +3.2) |
| `reduced_rules` | 57.3% (45.6%–69.2%) | -4.4 pp (-13.2 to +3.4) | 85.6% (80.6%–91.1%) | +36.5 pp (+26.1 to +44.2) ◆ | 44.3% (31.9%–57.0%) | -10.1 pp (-20.1 to -1.7) ◆ | 66.5% (56.6%–74.2%) | +23.2 pp (+9.0 to +34.3) ◆ |
| `bare` | 52.9% (41.0%–64.9%) | -8.8 pp (-18.1 to -0.1) ◆ | 87.1% (81.6%–92.0%) | +37.9 pp (+26.6 to +46.5) ◆ | 39.6% (27.9%–51.8%) | -14.7 pp (-25.4 to -5.2) ◆ | 65.3% (55.2%–73.3%) | +22.1 pp (+5.6 to +35.4) ◆ |


| Config | Attribute F1 | Δ Attribute F1 | hazard | Δ hazard | year | Δ year | location | Δ location |
|---|---|---|---|---|---|---|---|---|
| `full` | 50.2% (42.6%–58.2%) | — | 53.5% (46.1%–61.9%) | — | 55.6% (46.9%–65.0%) | — | 44.3% (36.4%–53.7%) | — |
| `no_evidence` | 47.1% (39.6%–55.0%) | -3.1 pp (-6.7 to -0.4) ◆ | 50.2% (42.4%–58.3%) | -3.3 pp (-6.9 to -0.4) ◆ | 51.2% (42.9%–59.8%) | -4.4 pp (-8.9 to -0.9) ◆ | 42.2% (35.0%–50.3%) | -2.1 pp (-5.7 to +0.4) |
| `no_vocab` | 51.4% (44.3%–59.2%) | +1.2 pp (-1.5 to +4.3) | 55.3% (48.0%–63.0%) | +1.9 pp (-1.4 to +5.5) | 57.0% (48.5%–65.8%) | +1.4 pp (-1.4 to +4.6) | 45.2% (38.0%–54.0%) | +0.9 pp (-2.1 to +3.8) |
| `reduced_rules` | 62.7% (52.3%–72.0%) | +12.5 pp (+3.8 to +21.2) ◆ | 65.7% (55.7%–74.3%) | +12.2 pp (+2.0 to +21.6) ◆ | 70.2% (60.5%–78.6%) | +14.6 pp (+4.3 to +24.1) ◆ | 56.1% (45.0%–67.3%) | +11.8 pp (+3.6 to +20.0) ◆ |
| `bare` | 60.0% (49.8%–69.1%) | +9.8 pp (+0.0 to +19.0) ◆ | 61.7% (51.8%–70.8%) | +8.2 pp (-2.2 to +18.5) | 68.1% (57.4%–77.1%) | +12.5 pp (+1.2 to +23.2) ◆ | 54.0% (43.5%–64.0%) | +9.6 pp (+0.2 to +17.7) ◆ |


| Config | Pooled hazard | Δ Pooled hazard | Pooled year | Δ Pooled year | Pooled location | Δ Pooled location |
|---|---|---|---|---|---|---|
| `full` | 76.5% (70.9%–82.4%) | — | 73.6% (65.0%–82.6%) | — | 50.8% (44.0%–58.5%) | — |
| `no_evidence` | 75.7% (69.6%–81.6%) | -0.9 pp (-4.3 to +2.2) | 70.3% (61.8%–79.4%) | -3.3 pp (-8.2 to +1.0) | 48.6% (42.2%–55.9%) | -2.2 pp (-5.1 to +0.4) |
| `no_vocab` | 77.2% (71.7%–83.1%) | +0.7 pp (-2.7 to +3.7) | 76.3% (68.4%–84.3%) | +2.6 pp (-0.8 to +7.0) | 52.0% (45.9%–58.5%) | +1.2 pp (-1.8 to +4.0) |
| `reduced_rules` | 78.7% (72.0%–85.1%) | +2.2 pp (-3.1 to +7.4) | 80.2% (72.3%–87.5%) | +6.6 pp (-0.1 to +13.4) | 64.1% (54.8%–73.5%) | +13.3 pp (+5.2 to +22.0) ◆ |
| `bare` | 72.5% (64.4%–80.2%) | -4.0 pp (-11.2 to +3.1) | 78.4% (71.0%–85.4%) | +4.8 pp (-2.5 to +12.0) | 62.5% (52.6%–71.7%) | +11.7 pp (+2.2 to +20.4) ◆ |

## 4. By window group (R2)

**event_present**

| Config | Detection F1 | Δ Detection F1 | CRC | Δ CRC | Pooled F1 | Δ Pooled F1 |
|---|---|---|---|---|---|---|
| `full` | 59.0% (50.8%–68.1%) | — | 65.1% (53.2%–76.5%) | — | 66.4% (60.3%–73.2%) | — |
| `no_evidence` | 55.0% (46.8%–63.8%) | -4.0 pp (-7.8 to -0.8) ◆ | 59.6% (46.9%–73.0%) | -5.5 pp (-9.6 to -1.3) ◆ | 63.8% (57.9%–70.5%) | -2.6 pp (-5.4 to -0.3) ◆ |
| `no_vocab` | 59.5% (51.2%–68.7%) | +0.6 pp (-1.4 to +2.7) | 61.1% (49.6%–72.9%) | -4.0 pp (-7.5 to -0.6) ◆ | 67.6% (62.3%–73.7%) | +1.2 pp (-0.4 to +3.0) |
| `reduced_rules` | 76.2% (67.8%–82.9%) | +17.2 pp (+6.7 to +27.3) ◆ | 53.2% (39.9%–65.5%) | -11.9 pp (-21.0 to -2.6) ◆ | 78.4% (72.1%–84.2%) | +11.9 pp (+7.1 to +17.5) ◆ |
| `bare` | 75.3% (67.3%–82.4%) | +16.3 pp (+5.7 to +27.1) ◆ | 49.8% (37.4%–61.7%) | -15.3 pp (-25.3 to -5.6) ◆ | 77.9% (72.7%–82.9%) | +11.5 pp (+5.8 to +17.1) ◆ |

**single**

| Config | Detection F1 | Δ Detection F1 | CRC | Δ CRC | Pooled F1 | Δ Pooled F1 |
|---|---|---|---|---|---|---|
| `full` | 58.0% (35.4%–89.8%) | — | 36.1% (16.9%–72.7%) | — | 65.3% (51.9%–82.2%) | — |
| `no_evidence` | 57.4% (35.3%–89.4%) | -0.6 pp (-5.9 to +7.5) | 36.8% (19.4%–70.8%) | +0.7 pp (-7.7 to +13.5) | 68.6% (54.9%–85.0%) | +3.3 pp (-0.5 to +8.7) |
| `no_vocab` | 54.3% (32.2%–86.5%) | -3.7 pp (-8.6 to +0.0) | 37.5% (20.0%–74.2%) | +1.4 pp (-6.7 to +13.3) | 64.7% (51.4%–81.9%) | -0.6 pp (-2.9 to +1.6) |
| `reduced_rules` | 54.4% (36.2%–83.0%) | -3.6 pp (-21.5 to +19.6) | 17.8% (5.7%–40.7%) | -18.3 pp (-36.1 to -9.2) ◆ | 68.5% (52.4%–87.1%) | +3.1 pp (-3.2 to +11.9) |
| `bare` | 51.4% (34.0%–81.8%) | -6.5 pp (-25.4 to +19.4) | 16.0% (5.2%–40.0%) | -20.1 pp (-42.9 to -2.6) ◆ | 65.0% (48.7%–84.7%) | -0.3 pp (-7.1 to +9.0) |

**multi**

| Config | Detection F1 | Δ Detection F1 | CRC | Δ CRC | Pooled F1 | Δ Pooled F1 |
|---|---|---|---|---|---|---|
| `full` | 59.3% (50.5%–68.5%) | — | 70.5% (59.8%–80.6%) | — | 66.6% (60.2%–73.8%) | — |
| `no_evidence` | 54.8% (46.2%–63.8%) | -4.4 pp (-8.9 to -0.8) ◆ | 64.2% (51.1%–77.4%) | -6.3 pp (-11.1 to -1.5) ◆ | 63.1% (56.8%–70.2%) | -3.5 pp (-6.7 to -1.1) ◆ |
| `no_vocab` | 60.3% (51.2%–69.9%) | +1.0 pp (-0.9 to +3.3) | 65.7% (54.3%–77.5%) | -4.8 pp (-8.5 to -1.1) ◆ | 68.1% (62.3%–74.7%) | +1.5 pp (-0.4 to +3.4) |
| `reduced_rules` | 78.3% (70.5%–85.0%) | +19.0 pp (+8.4 to +30.0) ◆ | 57.4% (44.1%–70.2%) | -13.1 pp (-22.9 to -3.4) ◆ | 79.6% (73.0%–85.7%) | +13.1 pp (+7.5 to +19.6) ◆ |
| `bare` | 77.7% (70.3%–84.2%) | +18.4 pp (+7.6 to +30.1) ◆ | 54.0% (42.2%–66.3%) | -16.4 pp (-26.8 to -5.8) ◆ | 79.7% (74.4%–84.8%) | +13.1 pp (+6.8 to +19.7) ◆ |

## 5. Event-absent windows

A record on an event-absent window has no gold event, so every one is a false positive. `S3` sets aside records whose places and year (and any evidence) are literally in the window — the Validation 2 "no" had no written guideline — as a bound on how much of the false-alarm rate could be gold error.

**event_absent**

| Config | False-alarm windows | Δ | Records / window | Δ | False-alarm S3 | Δ |
|---|---|---|---|---|---|---|
| `full` | 16.7% (5.6%–27.8%) | — | 0.62 (0.08–1.35) | — | 6.9% (0.0%–15.3%) | — |
| `no_evidence` | 16.7% (6.9%–27.8%) | +0.0 pp (-4.2 to +4.2) | 0.54 (0.10–1.13) | -0.08 | 5.6% (0.0%–12.5%) | -1.4 pp (-11.1 to +8.3) |
| `no_vocab` | 25.0% (11.1%–38.9%) | +8.3 pp (+0.0 to +19.4) | 0.51 (0.17–0.96) | -0.11 | 6.9% (1.4%–13.9%) | +0.0 pp (-4.2 to +4.2) |
| `reduced_rules` | 27.8% (13.9%–44.4%) | +11.1 pp (+2.8 to +22.2) ◆ | 1.18 (0.36–2.21) | +0.56 | 16.7% (6.9%–27.8%) | +9.7 pp (+1.4 to +19.4) ◆ |
| `bare` | 31.9% (18.1%–47.2%) | +15.3 pp (+4.2 to +27.8) ◆ | 1.58 (0.53–2.99) | +0.96 | 18.1% (6.9%–30.6%) | +11.1 pp (+0.0 to +22.2) |

**random_negative**

| Config | False-alarm windows | Δ | Records / window | Δ | False-alarm S3 | Δ |
|---|---|---|---|---|---|---|
| `full` | 3.3% (0.0%–10.0%) | — | 0.03 (0.00–0.10) | — | 0.0% (0.0%–0.0%) | — |
| `no_evidence` | 1.7% (0.0%–5.0%) | -1.7 pp (-5.0 to +0.0) | 0.02 (0.00–0.05) | -0.02 | 0.0% (0.0%–0.0%) | +0.0 pp (+0.0 to +0.0) |
| `no_vocab` | 10.0% (0.0%–20.0%) | +6.7 pp (+0.0 to +16.7) | 0.10 (0.00–0.20) | +0.07 | 0.0% (0.0%–0.0%) | +0.0 pp (+0.0 to +0.0) |
| `reduced_rules` | 13.3% (3.3%–26.7%) | +10.0 pp (+0.0 to +20.0) | 0.20 (0.03–0.43) | +0.17 | 5.0% (0.0%–13.3%) | +5.0 pp (+0.0 to +13.3) |
| `bare` | 18.3% (6.7%–33.3%) | +15.0 pp (+3.3 to +28.3) ◆ | 0.42 (0.07–0.83) | +0.38 | 8.3% (1.7%–16.7%) | +8.3 pp (+1.7 to +16.7) ◆ |

**hard_negative**

| Config | False-alarm windows | Δ | Records / window | Δ | False-alarm S3 | Δ |
|---|---|---|---|---|---|---|
| `full` | 83.3% (50.0%–100.0%) | — | 3.58 (0.83–6.75) | — | 41.7% (8.3%–75.0%) | — |
| `no_evidence` | 91.7% (75.0%–100.0%) | +8.3 pp (+0.0 to +25.0) | 3.17 (1.00–5.42) | -0.42 | 33.3% (8.3%–66.7%) | -8.3 pp (-58.3 to +50.0) |
| `no_vocab` | 100.0% (100.0%–100.0%) | +16.7 pp (+0.0 to +50.0) | 2.58 (1.33–4.42) | -1.00 | 41.7% (16.7%–66.7%) | +0.0 pp (-25.0 to +25.0) |
| `reduced_rules` | 100.0% (100.0%–100.0%) | +16.7 pp (+0.0 to +50.0) | 6.08 (2.42–9.92) | +2.50 | 75.0% (58.3%–91.7%) | +33.3 pp (-8.3 to +66.7) |
| `bare` | 100.0% (100.0%–100.0%) | +16.7 pp (+0.0 to +50.0) | 7.42 (2.66–13.75) | +3.83 | 66.7% (33.3%–100.0%) | +25.0 pp (-33.3 to +75.0) |

Detection with the S3 bound, all windows:

| Config | Detection P (S3) | Δ Detection P (S3) | Detection F1 (S3) | Δ Detection F1 (S3) |
|---|---|---|---|---|
| `full` | 70.4% (59.3%–81.6%) | — | 57.9% (49.8%–66.9%) | — |
| `no_evidence` | 67.8% (55.5%–80.1%) | -2.6 pp (-7.7 to +4.1) | 54.5% (46.4%–63.4%) | -3.3 pp (-7.4 to +0.2) |
| `no_vocab` | 69.2% (58.4%–80.7%) | -1.2 pp (-5.1 to +3.4) | 58.6% (50.5%–67.3%) | +0.8 pp (-1.5 to +3.1) |
| `reduced_rules` | 64.7% (54.0%–75.6%) | -5.7 pp (-14.0 to +2.3) | 73.7% (65.4%–80.8%) | +15.9 pp (+5.5 to +25.5) ◆ |
| `bare` | 62.1% (52.0%–72.4%) | -8.4 pp (-17.9 to +0.6) | 72.5% (64.2%–79.3%) | +14.6 pp (+3.7 to +25.0) ◆ |

## 6. Traceability

Snippet grades are `citation_quality.classify` against the window; held-out grades are out of the denominator. `no_evidence` and `bare` emit no evidence by design: snippet traceability is **unavailable** for them, not zero. Attribute traceability — every place word-bounded in the window, and a year that appears in it — applies to all five.

| Config | Snippets / record | Quotable | Grounded | Unsupported | Records with a quotable snippet | Places literal | Year literal | Both |
|---|---:|---|---|---|---|---|---|---|
| `full` | 1.88 | 65.5% (57.0%–73.4%) | 95.3% (90.1%–99.0%) | 1.2% (0.0%–3.4%) | 78.8% (70.1%–86.5%) | 88.0% (78.3%–95.2%) | 96.4% (92.8%–99.0%) | 84.7% (75.3%–92.3%) |
| `no_evidence` | — | unavailable | unavailable | unavailable | unavailable | 84.8% (74.3%–93.2%) | 97.3% (93.0%–100.0%) | 82.6% (72.0%–91.1%) |
| `no_vocab` | 1.87 | 70.0% (62.5%–76.8%) | 96.2% (93.8%–98.2%) | 0.0% (0.0%–0.0%) | 86.1% (80.6%–90.9%) | 85.4% (75.8%–93.2%) | 97.2% (93.1%–99.7%) | 82.9% (73.3%–91.1%) |
| `reduced_rules` | 1.65 | 66.1% (57.6%–74.1%) | 95.7% (92.2%–98.2%) | 0.0% (0.0%–0.0%) | 78.4% (70.5%–85.3%) | 85.5% (77.0%–92.9%) | 94.1% (89.8%–97.1%) | 79.8% (71.1%–87.6%) |
| `bare` | — | unavailable | unavailable | unavailable | unavailable | 84.1% (77.2%–90.1%) | 93.0% (87.4%–96.7%) | 78.6% (70.7%–85.2%) |

Δ attribute traceability:

| Config | Places and year literal | Δ Places and year literal |
|---|---|---|
| `full` | 84.7% (75.3%–92.3%) | — |
| `no_evidence` | 82.6% (72.0%–91.1%) | -2.1 pp (-7.3 to +3.7) |
| `no_vocab` | 82.9% (73.3%–91.1%) | -1.8 pp (-4.9 to +1.8) |
| `reduced_rules` | 79.8% (71.1%–87.6%) | -4.9 pp (-10.6 to +0.6) |
| `bare` | 78.6% (70.7%–85.2%) | -6.1 pp (-12.8 to +0.0) |

## 7. Schema compliance (raw JSON before the post-filter)

| Config | Raw events / window | Dropped | not verifiable | low confidence | missing field | duplicate | Admin-level mismatch | Invalid admin tag | Exact-vocabulary hazard | ISO date |
|---|---:|---|---|---|---|---|---|---|---|---|
| `full` | 1.71 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 80.8% |
| `no_evidence` | 1.65 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 79.6% |
| `no_vocab` | 1.76 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 43.1% | 78.3% |
| `reduced_rules` | 3.41 | 6.6% | 1.6% | 0.2% | 3.8% | 0.9% | 0.0% | 0.0% | 100.0% | 84.5% |
| `bare` | 3.84 | 8.9% | 2.6% | 0.5% | 5.2% | 0.7% | 0.0% | 0.0% | 20.2% | 78.9% |

Error rows and failed calls are in §1. `no_vocab` and `bare` are not asked for exact labels; their exact-vocabulary rate is descriptive.

## 8. Replicate noise (replicate 2 − replicate 1, R2, all windows)

| Config | Detection F1 | Pooled F1 | CRC | False-alarm windows |
|---|---|---|---|---|
| `full` | +0.2 pp (-3.8 to +4.2) | -0.8 pp (-3.7 to +2.0) | +2.6 pp (-3.6 to +7.9) | +0.0 pp (+0.0 to +0.0) |
| `no_evidence` | +9.6 pp (+4.0 to +16.2) ◆ | +5.1 pp (+0.7 to +10.3) ◆ | +9.1 pp (+0.5 to +17.0) ◆ | +5.6 pp (+0.0 to +13.9) |
| `no_vocab` | +1.0 pp (-2.5 to +4.3) | -0.1 pp (-2.9 to +2.3) | -2.6 pp (-7.2 to +2.5) | +0.0 pp (+0.0 to +0.0) |
| `reduced_rules` | -2.1 pp (-6.1 to +2.1) | -0.9 pp (-3.5 to +2.2) | -1.6 pp (-6.5 to +3.9) | +0.0 pp (+0.0 to +0.0) |
| `bare` | -1.7 pp (-7.5 to +4.6) | -0.8 pp (-4.0 to +2.0) | +0.0 pp (-5.6 to +6.3) | +2.8 pp (+0.0 to +8.3) |

## 9. Sensitivity

**S1 — without the 2 dev-pool windows** (R2)

| Config | Detection F1 | Δ Detection F1 | Pooled F1 | Δ Pooled F1 |
|---|---|---|---|---|
| `full` | 54.1% (45.8%–63.6%) | — | 62.0% (55.5%–69.7%) | — |
| `no_evidence` | 50.8% (42.7%–60.4%) | -3.3 pp (-7.4 to -0.2) ◆ | 59.6% (53.6%–66.6%) | -2.3 pp (-5.2 to +0.0) |
| `no_vocab` | 55.0% (47.2%–63.8%) | +0.9 pp (-2.1 to +4.3) | 63.1% (57.7%–69.3%) | +1.1 pp (-1.6 to +4.1) |
| `reduced_rules` | 68.2% (58.0%–77.1%) | +14.0 pp (+3.6 to +24.5) ◆ | 70.5% (63.0%–78.0%) | +8.6 pp (+2.9 to +14.4) ◆ |
| `bare` | 65.1% (54.4%–74.5%) | +10.9 pp (-0.7 to +22.3) | 67.8% (59.7%–75.0%) | +5.9 pp (-1.5 to +12.7) |

**S2 — without the 5 `gold_validation` windows** (R2)

| Config | Detection F1 | Δ Detection F1 | Pooled F1 | Δ Pooled F1 |
|---|---|---|---|---|
| `full` | 54.1% (45.2%–63.8%) | — | 61.9% (55.8%–69.3%) | — |
| `no_evidence` | 50.8% (42.0%–60.2%) | -3.4 pp (-7.2 to -0.1) ◆ | 59.6% (53.7%–66.5%) | -2.3 pp (-5.1 to +0.0) |
| `no_vocab` | 55.0% (46.4%–64.0%) | +0.9 pp (-2.1 to +4.2) | 63.1% (57.9%–69.2%) | +1.2 pp (-1.6 to +4.2) |
| `reduced_rules` | 68.5% (58.5%–77.4%) | +14.3 pp (+3.8 to +25.1) ◆ | 70.6% (63.3%–78.2%) | +8.7 pp (+2.9 to +14.7) ◆ |
| `bare` | 65.3% (54.9%–74.8%) | +11.1 pp (-0.8 to +23.0) | 67.8% (60.2%–75.1%) | +5.8 pp (-1.7 to +12.9) |

**S4 — R1, Experiment A's anchored matching** (configurations that emit evidence)

| Config | Detection F1 | Δ Detection F1 | CRC | Δ CRC | Attribute F1 | Δ Attribute F1 |
|---|---|---|---|---|---|---|
| `full` | 60.5% (52.7%–69.5%) | — | 51.8% (39.9%–65.3%) | — | 52.1% (44.9%–60.1%) | — |
| `no_vocab` | 62.1% (54.8%–70.2%) | +1.6 pp (-1.4 to +5.1) | 50.9% (40.4%–62.4%) | -0.9 pp (-7.0 to +5.7) | 53.2% (46.0%–61.4%) | +1.0 pp (-1.7 to +4.5) |
| `reduced_rules` | 74.3% (64.9%–82.0%) | +13.8 pp (+3.2 to +22.9) ◆ | 42.5% (30.7%–54.9%) | -9.3 pp (-19.7 to -0.2) ◆ | 63.4% (53.0%–73.0%) | +11.3 pp (+2.6 to +19.9) ◆ |

## 10. Hazard normalisation

| Config | Records relabelled | Records with an unmapped component | Top unmapped |
|---|---|---|---|
| `full` | 0.0% | 0.0% | – |
| `no_evidence` | 0.0% | 0.0% | – |
| `no_vocab` | 49.5% | 7.5% | Meteotsunami (10), Derecho (severe windstorm) (2), Meteotsunami (atmospheric inertia–gravity wave-induced) (1), Supercyclone (1), Rising sea temperatures causing coral bleaching (marine heat) (1), Civil crisis (conflict) (1) |
| `reduced_rules` | 0.0% | 0.0% | – |
| `bare` | 76.6% | 11.2% | meteotsunami (5), Meteotsunami (5), Dry conditions and erratic rainfall (4), torrential rains (4), Previous dry conditions (4), Severe weather (2) |

Unmapped components pass through to `hazard_key`, whose family regex still rolls some up (a bare "storm" lands in the cyclone family).

## 11. Reference rows (not contrasted)

The September OpenRouter GPT-5 prompt-5 run and the Azure production run on the same windows. The Azure run is the one the windows were selected on.

| Run | Reading | Detection F1 | Pooled F1 | CRC | False-alarm windows |
|---|---|---|---|---|---|
| GPT-5 Sept (OpenRouter) | R2 | 54.0% (45.2%–62.9%) | 63.7% (58.1%–69.7%) | 49.0% (36.8%–62.5%) | 19.4% (8.3%–33.3%) |
| GPT-5 Sept (OpenRouter) | R1 | 60.4% (52.8%–69.1%) | 63.7% (58.1%–69.7%) | 46.2% (34.1%–59.6%) | 19.4% (8.3%–33.3%) |
| prompt 5 (gpt-5, Azure) — production | R2 | 54.6% (46.6%–63.4%) | 63.5% (57.4%–70.3%) | 53.8% (42.3%–65.6%) | 16.7% (5.6%–30.6%) |
| prompt 5 (gpt-5, Azure) — production | R1 | 61.2% (53.7%–69.7%) | 63.5% (57.4%–70.3%) | 51.5% (40.6%–63.2%) | 16.7% (5.6%–30.6%) |

