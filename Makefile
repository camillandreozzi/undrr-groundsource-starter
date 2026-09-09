.PHONY: setup test extract db-check polygons visualisation visualization qa review docker-build prefill recommend polygon-score \
	gold-extract gold-polygons gold-prefill-validation gold-validate gold-validation-score upload \
	prod-prefill-validation prod-validate prod-validation-score \
	prod-polygon-sample prod-polygon-prefill prod-polygon-validate prod-polygon-score \
	ner-setup ner-fetch ner-extract ner-preflight ner-polygons ner-compare \
	ner-prefill-validation ner-validate ner-validate-only ner-score \
	annotate annotate-prefetch annotate-score \
	or-check-models or-build-docs or-dry-run or-smoke or-run or-agreement or-score

PYTHON ?= python3
VENV ?= .venv
VENV_BIN := $(VENV)/bin
VENV_PYTHON := $(VENV_BIN)/python

# Default output directory for extraction (can be overridden from environment)
EXTRACT_OUTPUT_DIR=outputs/event_extractions

# Default Nominatim user agent required by the Nominatim API policy.
# Customize this with a real contact if you prefer.
NOMINATIM_USER_AGENT ?= undrr-fonte/0.1 (camilla.andreozzi@un.org)

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip setuptools wheel
	$(VENV_PYTHON) -m pip install -r requirements-dev.txt -c constraints.txt

test:
	$(VENV_PYTHON) -m unittest discover -s tests -p "test_*.py"

db-check:
	$(VENV_BIN)/fonte-extract --db-only --limit 3

# Writes to $EXTRACT_OUTPUT_DIR (see .env).
extract:
	$(VENV_BIN)/fonte-extract \
		--limit 10000 \
		--resume \
		--output-dir $(EXTRACT_OUTPUT_DIR)

polygons:
	$(VENV_BIN)/fonte-polygons \
		--input $(EXTRACT_OUTPUT_DIR)/event_extractions.jsonl \
		--output $(EXTRACT_OUTPUT_DIR)/event_geometries.parquet \
		--coastline data/ne_50m_coastline.zip \
		--user-agent "$(NOMINATIM_USER_AGENT)"

visualisation:
	$(VENV_PYTHON) scripts/visualize_event_extractions.py \
		--map-only \
		--output-dir $(EXTRACT_OUTPUT_DIR)/visualisation_checks \
		--geometries $(EXTRACT_OUTPUT_DIR)/event_geometries.parquet \
		--map-output $(EXTRACT_OUTPUT_DIR)/polygon_map.html \
		--require-geometries

visualization: visualisation

# QA counts, flags and static plots. Separate from `visualisation`, which is
# --map-only and skips the QA pass entirely — that is how the report went stale.
qa:
	$(VENV_PYTHON) scripts/visualize_event_extractions.py \
		--skip-map \
		--input $(EXTRACT_OUTPUT_DIR)/event_extractions.csv \
		--output-dir $(EXTRACT_OUTPUT_DIR)/visualisation_checks

review:
	$(VENV_PYTHON) -m streamlit run eval/gold_review_app.py

# Auto pre-fill gold labels (consensus) and polygon review queue (risk-ranked).
prefill:
	$(VENV_PYTHON) eval/prefill_gold.py
	$(VENV_PYTHON) eval/prefill_polygon_review.py

# After gold.csv is verified: score the 8 runs and emit the recommendation.
recommend:
	$(VENV_PYTHON) eval/score_against_gold.py
	$(VENV_PYTHON) eval/recommend.py

# After the polygon queue is judged: accuracy overall + by stratum.
polygon-score:
	$(VENV_PYTHON) eval/score_polygon_validation.py

# ---- Gold run (prompt 5, 2000 docs) + easier validation ----------------------

# 1. Extract the gold dataset with the production prompt.
# Tunable from the command line, e.g.  make gold-extract WORKERS=2 MODEL=gpt-5
GOLD_MODEL ?= gpt-5
GOLD_WORKERS ?= 4
GOLD_REASONING ?= low
GOLD_LIMIT ?= 2000
gold-extract:
	$(VENV_BIN)/fonte-extract \
		--prompt 5 \
		--limit $(GOLD_LIMIT) \
		--workers $(GOLD_WORKERS) \
		--model $(GOLD_MODEL) \
		--reasoning-effort $(GOLD_REASONING) \
		--output-dir outputs/gold \
		--resume

# 1b. Resolve polygons (geometries) for the gold extraction.
gold-polygons:
	$(VENV_BIN)/fonte-polygons \
		--input outputs/gold/event_extractions.jsonl \
		--output outputs/gold/event_geometries.parquet \
		--coastline data/ne_50m_coastline.zip \
		--cache outputs/gold/.nominatim_cache.json \
		--user-agent "$$NOMINATIM_USER_AGENT"

# 2. Build the ~100-event stratified, risk-ranked validation queue.
gold-prefill-validation:
	$(VENV_PYTHON) eval/prefill_gold_validation.py

# 3. Judge the queue (Correct / Partial / Wrong) in the easier review app.
gold-validate:
	$(VENV_PYTHON) -m streamlit run eval/gold_validation_app.py

# 4. Score accuracy overall + by hazard stratum.
gold-validation-score:
	$(VENV_PYTHON) eval/score_gold_validation.py

# ---- Validation of the production run ($(EXTRACT_OUTPUT_DIR)) ---------------
# Same two-track gold review as the `gold-*` targets above, pointed at the
# production extraction instead of outputs/gold, and writing to its own files
# so the older gold-run queue and its verdicts stay intact.

PROD_VALIDATION_CSV ?= eval/production_validation.csv
PROD_VALIDATION_TARGET ?= 175
PROD_POLYGON_DIR ?= outputs/event_extractions_polygon_validation
PROD_POLYGON_CSV := $(PROD_POLYGON_DIR)/polygon_validation_sample.csv

# 1. Build the stratified, risk-ranked event queue.
prod-prefill-validation:
	$(VENV_PYTHON) eval/prefill_gold_validation.py \
		--source $(EXTRACT_OUTPUT_DIR)/event_extractions.jsonl \
		--out $(PROD_VALIDATION_CSV) \
		--target $(PROD_VALIDATION_TARGET)

# 2. Judge the queue (Correct / Partial / Wrong).
prod-validate:
	GOLD_VALIDATION_CSV=$(PROD_VALIDATION_CSV) \
		$(VENV_PYTHON) -m streamlit run eval/gold_validation_app.py

# 3. Score accuracy overall, by hazard family, and by raw hazard stratum.
prod-validation-score:
	$(VENV_PYTHON) eval/score_gold_validation.py --in $(PROD_VALIDATION_CSV)

# 1b. Build the polygon sample from this run's geometries.
prod-polygon-sample:
	$(VENV_PYTHON) scripts/make_polygon_validation_sample.py \
		--extractions $(EXTRACT_OUTPUT_DIR)/event_extractions.jsonl \
		--geometries $(EXTRACT_OUTPUT_DIR)/event_geometries.parquet \
		--output-dir $(PROD_POLYGON_DIR) \
		--high-conf-n 150 --low-conf-n 150 --unresolved-n 100 --seed 42

# 2b. Risk-rank and queue 20 rows per stratum.
prod-polygon-prefill:
	$(VENV_PYTHON) eval/prefill_polygon_review.py --file $(PROD_POLYGON_CSV)

# 3b. Judge the polygon queue.
prod-polygon-validate:
	POLYGON_VALIDATION_CSV=$(PROD_POLYGON_CSV) \
		$(VENV_PYTHON) -m streamlit run eval/polygon_validation_review_app.py

# 4b. Score location / geometry / date accuracy.
prod-polygon-score:
	$(VENV_PYTHON) eval/score_polygon_validation.py \
		--file $(PROD_POLYGON_CSV) \
		--out eval/PRODUCTION_POLYGON_VALIDATION.md

# ---- NER benchmark baseline (benchmark_ner/) --------------------------------
# A classical NER + gazetteer pipeline over the same corpus as
# $(EXTRACT_OUTPUT_DIR), geocoded by the same resolver and judged by the same
# review app, so the LLM run can be measured against a baseline. See
# benchmark_ner/README.md for what each number means.

NER_DIR ?= benchmark_ner/outputs
NER_PROCESSES ?= 4
NER_LIMIT ?=

# 0. One-off: the spaCy runtime and model (not part of the main install).
ner-setup:
	$(VENV_PYTHON) -m pip install -e ".[ner]" -c constraints.txt
	$(VENV_PYTHON) -m spacy download en_core_web_lg

# 1. Same Databricks query as `extract`, same 12k-char window.
ner-fetch:
	$(VENV_PYTHON) -m benchmark_ner.fetch_documents

# 2. Run the baseline. NER_LIMIT=200 for a smoke run first.
ner-extract:
	$(VENV_PYTHON) -m benchmark_ner.ner_extract \
		--n-process $(NER_PROCESSES) \
		$(if $(NER_LIMIT),--limit $(NER_LIMIT),)

# 3. How many Nominatim lookups are NOT already cached? Read this before
#    starting ner-polygons — it is the long pole of the whole benchmark.
ner-preflight:
	$(VENV_PYTHON) -m benchmark_ner.geocode_preflight

# 4. Identical resolver, ladder and coastal clipping as `make polygons`,
#    sharing the same cache so overlapping locations cost nothing.
ner-polygons:
	$(VENV_BIN)/fonte-polygons \
		--input $(NER_DIR)/ner_extractions.jsonl \
		--output $(NER_DIR)/event_geometries.parquet \
		--coastline data/ne_50m_coastline.zip \
		--cache .nominatim_cache.json \
		--user-agent "$(NOMINATIM_USER_AGENT)"

# 5. Automatic agreement between the two runs (not accuracy).
ner-compare:
	$(VENV_PYTHON) -m benchmark_ner.compare

# 6. Build the NER queue paired to the judged LLM queue, plus the NER-only arm.
ner-prefill-validation:
	$(VENV_PYTHON) -m benchmark_ner.prefill_paired_validation \
		--llm-queue $(PROD_VALIDATION_CSV)

# 7. Judge the paired queue in the existing review app.
ner-validate:
	GOLD_VALIDATION_CSV=benchmark_ner/ner_paired_validation.csv \
		$(VENV_PYTHON) -m streamlit run eval/gold_validation_app.py

# 7b. Judge the events only the baseline found (the extra-recall arm).
ner-validate-only:
	GOLD_VALIDATION_CSV=benchmark_ner/ner_only_validation.csv \
		$(VENV_PYTHON) -m streamlit run eval/gold_validation_app.py

# 8. Accuracy on the same events, with the paired significance test.
ner-score:
	$(VENV_PYTHON) -m benchmark_ner.score_paired \
		--llm-queue $(PROD_VALIDATION_CSV)

# --------------------------------------------------------------------------
# Human annotation — model-independent ground truth over the queue's documents.
# Annotate once here, then score any number of runs without re-judging.
# --------------------------------------------------------------------------
HUMAN_ANNOTATIONS ?= eval/human_annotations.csv
LLM_RUN ?= outputs/event_extractions/event_extractions.jsonl
NER_RUN ?= benchmark_ner/outputs/ner_extractions.jsonl

# Pull just the queue's documents out of the 57 MB parquet into a ~2 MB store
# the app loads in milliseconds. The app builds this itself on first run, so
# this target is for doing it ahead of time (or in CI).
annotate-prefetch:
	$(VENV_PYTHON) eval/prefetch_annotation_documents.py

# Annotate the 167 documents behind the 175-event queue. Builds
# $(HUMAN_ANNOTATIONS) on first run; resumes where you left off after that.
annotate:
	$(VENV_PYTHON) -m streamlit run eval/human_annotation_app.py

# Score runs against those annotations -> eval/HUMAN_ANNOTATION_SCORES.md.
# Add another model with:  make annotate-score EXTRA_RUN="gpt-x=path/to/run.jsonl"
annotate-score:
	$(VENV_PYTHON) eval/score_against_human.py \
		--annotations $(HUMAN_ANNOTATIONS) \
		--run "prompt 5=$(LLM_RUN)" \
		--run "NER baseline=$(NER_RUN)" \
		$(if $(EXTRA_RUN),--run "$(EXTRA_RUN)",)

# --------------------------------------------------------------------------
# Multi-model benchmark — prompt 5 held fixed, the model varied via OpenRouter,
# over the same 167 documents the annotation queue covers.
# Needs OPENROUTER_API_KEY in .env. Run the targets in this order.
# --------------------------------------------------------------------------
OR_WORKERS ?= 4

# 1. Validate every roster model id against OpenRouter. No inference, no spend.
or-check-models:
	$(VENV_PYTHON) -m benchmark_openrouter.run_openrouter --check-models

# 2. Freeze the 167 documents (text + full metadata) into a tracked snapshot.
#    Needs Databricks; add --from-parquet if you only have the NER bulk file.
or-build-docs:
	$(VENV_PYTHON) -m benchmark_openrouter.build_documents

# 3. Estimate what a full roster run costs, from live pricing. No spend.
or-dry-run:
	$(VENV_PYTHON) -m benchmark_openrouter.run_openrouter --all --dry-run

# 4. Smoke-test the cheapest model on 3 documents before committing to a run.
or-smoke:
	$(VENV_PYTHON) -m benchmark_openrouter.run_openrouter \
		--model meta-llama/llama-4-maverick --limit 3 --save-raw

# 5. The run itself. Add --tier frontier / --model X to narrow it.
#    Always safe to re-run: --resume skips finished documents, retries errors.
or-run:
	$(VENV_PYTHON) -m benchmark_openrouter.run_openrouter \
		--all --workers $(OR_WORKERS) --resume

# 6. Cross-model agreement -> benchmark_openrouter/MODEL_AGREEMENT.md.
#    Needs no human annotation: run it as soon as the models finish.
or-agreement:
	$(VENV_PYTHON) -m benchmark_openrouter.agreement

# 7. Accuracy against the human annotations -> MODEL_SCORES.md. Refuses until
#    all 167 documents are annotated; add --allow-partial to preview.
or-score:
	$(VENV_PYTHON) -m benchmark_openrouter.score_all

docker-build:
	docker build -t undrr-fonte .

# Upload local $EXTRACT_OUTPUT_DIR files to Azure Blob Storage (independent of extract/polygons).
upload:
	$(VENV_BIN)/fonte-upload --source $(EXTRACT_OUTPUT_DIR)
