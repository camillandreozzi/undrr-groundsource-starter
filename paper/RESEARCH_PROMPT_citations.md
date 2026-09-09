# Deep-research prompt — citation sweep for the EACL 2027 Industry Track paper

Paste everything below the line into a deep-research tool. Written 2026-09-02.

---

You are a research librarian specialising in computational linguistics. Your job is to
assemble the citation base for a short paper being submitted to the **EACL 2027 Industry
Track** (6 content pages, references excluded, deadline 11 September 2026). I need
citations for three sections only: **Introduction**, **Related Work**, and **Method /
Validation Design**. Do not write prose for me — find, verify and organise sources.

## The paper you are supporting

**Working title:** *Auditable LLM Extraction of Geo-referenced Hazard Events from the
Disaster-Risk-Reduction Corpus.*

**What we built and deployed.** A production pipeline at the UN Office for Disaster Risk
Reduction (UNDRR) that reads the organisation's internal document lake — PreventionWeb
disaster-risk-reduction (DRR) grey literature: national reports, guidance notes,
post-disaster assessments, workshop and evaluation material submitted by member states
and NGOs — and turns it into structured, geo-referenced hazard-event records. Each record
carries a hazard type from a controlled vocabulary, an event date or date range, one or
more location strings, a stated confidence level, and an evidence snippet quoted from the
source. A second stage resolves each location string to an actual geometry (polygon /
multipolygon, EPSG:4326) via an OpenStreetMap/Nominatim geocoder behind a swappable
interface, with a possessive/facility-noun rewrite ladder and a country-level last-resort
fallback.

**Scale and design choices that need literature support.**
- Documents are read from a SQL warehouse; each is truncated to a 12,000-character window
  before extraction.
- Extraction is a single LLM call per document with a Pydantic/JSON schema constraining
  the output structure (a commercial instruction-tuned model via Azure OpenAI); no
  fine-tuning, no supervised training data.
- Prompt selection was empirical: five candidate prompts compared on a small
  hand-labelled development set, then one frozen for the production run.
- Production run: 10,000 documents, 11,659 rows, 3,572 verifiable events, 19.1% of
  documents yield at least one event, 81.2% of location mentions resolve to a geometry.
- Evaluation is **human judgement over stratified random samples**, because the corpus has
  no event annotations and no comparable annotated resource exists for it. Three arms:
  (1) 175 sampled events judged correct/partial/wrong; (2) 60 geocoded locations judged
  separately for location correctness, geometry correctness and admin-level granularity;
  (3) a **non-LLM baseline** — spaCy `en_core_web_lg` NER plus a hazard lexicon derived
  from the controlled vocabulary, with a ±1-sentence window around hazard mentions — run
  over the *same* documents, emitted into the *identical* schema, and judged under the
  *same* rubric, scored as a paired comparison (McNemar) plus a recall-oriented
  NER-only arm.
- Sampling is seeded and regenerable; the paper also reports a label-free "risk score"
  covariate (stated confidence, multi-event documents, vague dates, country-level admin
  tags, thin evidence) and asks whether the system's own difficulty signals predict human
  verdicts.
- Single human judge; inter-annotator agreement was **not** collected and is declared as a
  limitation.
- Deployment lessons we report honestly: token-level log-probabilities were silently never
  captured for the whole production run because of a configuration either/or with the
  model's reasoning-effort setting, so calibration analysis is impossible post hoc; and
  the model never emits its lowest confidence label, making stated confidence effectively
  a two-level signal.
- Cost and latency reporting: per-document seconds are recoverable from run logs;
  per-document dollars were not instrumented.

**Positioning.** The three closest systems are Google Research's **Groundsource** (news
articles only, floods only, ~2.6M records, proprietary location mapping), the European
Commission **JRC**'s AI narrative summarisation over EM-DAT (summarises existing events,
extracts no new ones), and **LLM-GeoDis** (maps EM-DAT free-text location fields to
shapes). Our distinctness claims are: (a) grey literature rather than news, (b) full
hazard taxonomy rather than one hazard, (c) an open, auditable, regenerable validation
design rather than a proprietary one, (d) end-to-end text-to-geometry inside one pipeline.

## What I need from you

For each of the clusters below, return **verified real publications**, weighted heavily
towards computational linguistics and NLP venues. Within CL, prefer in this order: TACL
and *Computational Linguistics* journal; ACL, EMNLP, NAACL, EACL, COLING, LREC/LREC-COLING
main conferences; ACL Anthology workshops (especially crisis/humanitarian NLP, NLP for
positive impact, geo-NLP, event extraction workshops); then arXiv preprints that are
widely cited but unpublished. Non-CL work (GIScience, *Natural Hazards*, *Scientific Data*,
disaster-risk literature) is allowed **only** where CL has no equivalent — mark those
clearly as out-of-field and keep them few.

### Cluster 1 — Event extraction as a CL task (Related Work, Method)
Task definitions, benchmarks, and the document-level turn: ACE/ERE and TAC-KBP lineage,
MAVEN, RAMS, WikiEvents, DocEE, MEE and any multilingual/document-level successors
published since. I especially want work that frames **document-level** event extraction
with arguments spread across a long document, and work on **event schemas / ontologies**
and controlled hazard or disaster vocabularies. Also: cross-document event coreference and
event deduplication (ECB+ and successors), since duplicate events across documents about
the same disaster are an acknowledged downstream problem for us.

### Cluster 2 — LLMs for information extraction (Introduction, Related Work, Method)
Zero-shot and few-shot IE with instruction-tuned LLMs; guideline-following IE (e.g. the
GoLLIE line); unified IE instruction tuning; LLM-based NER; and — critically — the
**sceptical** evaluations showing LLMs underperform supervised systems on event extraction
and NER benchmarks. I need both the enabling papers and the papers that would let a
reviewer say "this is a solved/overclaimed problem", so I can pre-empt them.

### Cluster 3 — Constrained / schema-guided generation (Method)
Producing valid structured output from an LLM: JSON-schema and grammar-constrained
decoding, code-as-structure prompting, function/tool calling as an IE interface, and
studies of how schema constraints affect extraction quality. This is what justifies our
Pydantic-schema design choice in one sentence.

### Cluster 4 — Toponym resolution, geoparsing and geo-NLP (Related Work, Method)
The core CL geoparsing line: toponym resolution corpora (LGL, GeoVirus, WikToR, TR-News),
SemEval-2019 Task 12, Gritta et al.'s critique of geoparsing evaluation and the pragmatic
evaluation guide, EUPEG-style benchmark platforms, neural geoparsers, and the recent
LLM-for-geoparsing / geospatial-LM work. Two specific things I need:
1. Evidence on **metonymy and same-name ambiguity across countries** (our dominant failure
   mode: Ipswich UK vs Ipswich AU) and on the use of **country hints** in disambiguation.
2. Established practice on **evaluating geocoding at polygon/areal granularity** rather than
   point-distance error (accuracy@161km and friends) — and any prior work that judges
   *admin-level granularity* as a separate axis, as we do.
Also find **Mordecai** and the political-event geolocation line, which is the closest
methodological neighbour to what we do.

### Cluster 5 — Crisis, humanitarian and disaster NLP (Introduction, Related Work)
CrisisNLP / CrisisLex / CrisisBench / TREC-IS; HumSet and the DEEP/humanitarian-analysis
line; surveys of NLP for humanitarian response and social good. I need this cluster to
support two Introduction claims: that disaster NLP is overwhelmingly **social media and
news** rather than institutional grey literature, and that structured, geo-referenced
disaster records have downstream value. If there is any prior CL work on **DRR policy
documents, national disaster reports, or Sendai Framework reporting**, that is the single
most valuable thing you can find — search hard for it and tell me plainly if it does not
exist, because "no prior CL work on this document type" is a claim I want to make.

### Cluster 6 — Event databases built from text (Related Work)
GDELT, ICEWS, POLECAT, PETRARCH and the automated political-event-data tradition; LLM-era
successors; and the critical literature on **validating machine-coded event data** against
human coding. Also EM-DAT, DesInventar and the disaster-database side, plus any published
critique of their coverage or geolocation quality — this supports why a new extraction
pipeline is worth building.

### Cluster 7 — Human evaluation, annotation and sampling methodology (Method / Validation)
This is where I most need defensible citations, because our evaluation is human judgement
over samples with a single judge:
- Best-practice guidance and critiques of **human evaluation in NLP** (Belz and colleagues'
  work on reproducibility of human evaluation; evaluation-design checklists).
- **Annotation guidelines, rubric design, and inter-annotator agreement** — Krippendorff /
  Cohen / Artstein & Poesio-style methodological references, plus any CL work arguing when
  a **single annotator is acceptable** or how to report it responsibly. If the honest answer
  is that CL norms require multiple annotators, say so directly — I need to know how
  exposed this limitation leaves us.
- **Stratified and risk-ranked sampling** for evaluating extraction systems; estimating
  population accuracy from a sample; reporting confidence intervals on small strata.
- **LLM-as-judge** literature, so I can cite why we did *not* use it (or the conditions
  under which it would have been acceptable).
- **Paired significance testing** in NLP — McNemar's test and the broader significance-
  testing guidance for NLP comparisons (Dror et al. and similar).

### Cluster 8 — Baselines, and the ethics of comparing to one (Method)
Work arguing for **simple/lexical baselines** against neural or LLM systems; papers where a
spaCy-or-similar off-the-shelf NER pipeline is used as the reference point; and any
methodological writing on making a baseline comparison *fair* (same inputs, same schema,
same rubric) rather than a straw man. Reviewers will attack our baseline as weak — find me
the literature that both defends and attacks that choice.

### Cluster 9 — Confidence, calibration and self-reported uncertainty (Method, Deployment lessons)
Verbalised/stated confidence from LLMs and how well it calibrates; log-probability-based
confidence and its limitations; calibration of instruction-tuned and reasoning models;
selective prediction / abstention in IE. Our finding is that the model's stated confidence
collapses to two levels and never uses its lowest label — find prior work reporting the
same degeneracy so this reads as a confirmed phenomenon rather than an anecdote.

### Cluster 10 — Prompt selection, sensitivity and reproducibility (Method)
Prompt-format sensitivity and variance across semantically equivalent prompts; prompt
selection as an empirical procedure; the reproducibility problem with closed commercial
API models (version drift, undisclosed changes) — we need one or two citations to justify
freezing a prompt and to caveat reproducibility.

### Cluster 11 — Deployment reality: cost, latency, long documents (Industry-track framing)
Efficient/cost-aware NLP and inference-cost reporting norms; papers reporting real
deployment economics of LLM pipelines; long-document handling and the effect of
**truncation windows** on extraction recall (justifying or problematising our
12,000-character cut); and any "lessons learned from deploying NLP in an organisation"
papers, especially from ACL/EMNLP/NAACL/EACL **industry tracks** — I would like two or
three exemplars of what a strong industry-track paper cites and how it frames deployment
lessons.

### Cluster 12 — Documentation, data release and ethics (Introduction, Ethics/Limitations)
Data statements, datasheets, and model/system documentation norms; NLP work on **corpora
that cannot be redistributed** for rights reasons and what is releasable instead (we can
likely release only short quoted evidence snippets, not the corpus); and anything on
auditability/traceability of automatically extracted records feeding policy decisions.

## Output format

Return a single document with one subsection per cluster. Within each cluster, list
sources in **priority order** and for each give exactly:

1. **Full citation** — authors, year, title, venue (spelled out), and pages/volume if a journal.
2. **Link** — ACL Anthology URL where one exists, otherwise DOI, otherwise arXiv ID.
3. **BibTeX key suggestion** in the `surnameYearKeyword` style, plus the complete BibTeX
   entry, copied from the ACL Anthology or DBLP rather than reconstructed from memory.
4. **Why it matters here** — two or three sentences, concrete about *our* system, not a
   generic abstract summary.
5. **Where it goes** — Introduction, Related Work, or Method — and, where you can, the
   specific claim it supports, phrased as the sentence it would sit at the end of.
6. **Strength** — `must-cite`, `strong`, or `optional`.

Then close with four short lists:

- **The 25-reference core.** If I could only cite 25 things in a 6-page paper, which, and why.
- **Threats.** Any paper that undercuts, scoops or contradicts our contribution claims —
  particularly anything already doing LLM event extraction on institutional or grey
  literature, anything doing text-to-polygon disaster geolocation, and anything that has
  already published the "stated confidence is degenerate" finding. Be adversarial here; I
  would rather find these now than in a review.
- **Unsupportable claims.** Claims in the description above that you could find **no**
  literature for. Say so explicitly rather than substituting a loose neighbour — I will
  rewrite the claim or drop it.
- **Search notes.** Which queries and venues you swept, so the gaps are interpretable.

## Hard rules

- **Never invent a citation.** Every entry must be one you actually located. If you are
  unsure a paper exists, leave it out and note it under search notes.
- Verify title, author list, year and venue against the ACL Anthology, DBLP or the
  publisher — not from memory. Flag anything you could not verify.
- Prefer the **published** version over the arXiv preprint where both exist, and use the
  Anthology citation for anything in it.
- Recency matters but is not everything: for benchmarks and methodology, the canonical
  older reference beats a recent survey. For LLM-based IE, prioritise 2023 onwards.
- Aim for roughly 60–90 verified sources total across all clusters — enough to select 40–55
  for a 6-page paper, and no padding.
