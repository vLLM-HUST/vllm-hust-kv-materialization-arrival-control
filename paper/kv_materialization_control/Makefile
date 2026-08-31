PYTHON ?= python3
TECTONIC ?= tectonic
PDFLATEX ?= pdflatex
BIBTEX ?= bibtex
ROOT_DIR := $(abspath ../..)
LLM_OPTIMIZATIONS_ROOT ?= $(abspath $(ROOT_DIR)/../llm-optimizations)
LLM_OPTIMIZATIONS_PDF_DIR ?= $(LLM_OPTIMIZATIONS_ROOT)/docs/papers
LLM_OPTIMIZATIONS_PDF_NAME ?= kv-materialization__kv_materialization_control.pdf
EXPERIMENT_DIR := $(CURDIR)/experiments
RESULT_DIR := $(EXPERIMENT_DIR)/results/latest
PAPER_TEX := kv_materialization_control.tex
PAPER_PDF := kv_materialization_control.pdf

.DEFAULT_GOAL := help

.PHONY: help experiment decision-study live-benchmark runtime-boundary-live optimization-live pdf clean evidence-bundle submission-plan

help:
	@printf '%s\n' \
		'Paper targets:' \
		'  make decision-study      Run the workload-driven arrival-time decision study and refresh paper artifacts' \
		'  make experiment          Compatibility alias of make decision-study' \
		'  make runtime-boundary-live Run a shared-workload live runtime-boundary benchmark against a vLLM endpoint' \
		'  make live-benchmark      Compatibility alias of make runtime-boundary-live' \
		'  make optimization-live   Compatibility alias of make runtime-boundary-live' \
		'  make pdf             Build the paper PDF with tectonic or pdflatex' \
		'  make evidence-bundle Show the latest generated evidence files' \
		'  make submission-plan Print the paper submission plan note'

decision-study:
	PYTHONPATH=$(ROOT_DIR)/src $(PYTHON) $(EXPERIMENT_DIR)/run_offline_study.py \
		$(foreach case,$(WORKLOAD_CASES),--workload-case $(case)) \
		--output-dir $(RESULT_DIR)

experiment: decision-study

runtime-boundary-live:
	@test -n "$(MODEL)" || { echo 'MODEL is required. Usage: make live-benchmark MODEL=/path/to/model [WORKLOAD_CASE=<shared-case-id>]' >&2; exit 2; }
	PYTHONPATH=$(ROOT_DIR)/src $(PYTHON) $(EXPERIMENT_DIR)/run_openai_workloads.py \
		--base-url "$${BASE_URL:-http://127.0.0.1:8011}" \
		--model "$(MODEL)" \
		$(if $(WORKLOAD_CASE),--workload-case "$(WORKLOAD_CASE)",) \
		--api-key "$${OPENAI_API_KEY:-}" \
		--user-agent "$${OPENAI_HTTP_USER_AGENT:-python-httpx/0.28.1}" \
		$(if $(REQUEST_RATE),--request-rate $(REQUEST_RATE),) \
		$(if $(CONCURRENCY),--concurrency $(CONCURRENCY),) \
		$(if $(SEED),--seed $(SEED),) \
		--output $(EXPERIMENT_DIR)/results/live/$${LABEL:-$${WORKLOAD_CASE:-default_live_case}}.json

live-benchmark: runtime-boundary-live

optimization-live: runtime-boundary-live

pdf:
	@if command -v '$(TECTONIC)' >/dev/null 2>&1; then \
		cd '$(CURDIR)' && '$(TECTONIC)' --keep-logs '$(PAPER_TEX)'; \
	elif command -v '$(PDFLATEX)' >/dev/null 2>&1 && command -v '$(BIBTEX)' >/dev/null 2>&1; then \
		cd '$(CURDIR)' && '$(PDFLATEX)' -interaction=nonstopmode -halt-on-error '$(PAPER_TEX)' && \
		'$(BIBTEX)' '$(basename $(PAPER_TEX))' && \
		'$(PDFLATEX)' -interaction=nonstopmode -halt-on-error '$(PAPER_TEX)' && \
		'$(PDFLATEX)' -interaction=nonstopmode -halt-on-error '$(PAPER_TEX)'; \
	else \
		echo 'Install tectonic, or install both pdflatex and bibtex.' >&2; \
		exit 2; \
	fi
	@if [ -d "$(LLM_OPTIMIZATIONS_ROOT)" ] && [ -f "$(PAPER_PDF)" ]; then \
		python3 "$(LLM_OPTIMIZATIONS_ROOT)/scripts/export_paper_pdf.py" \
			--workspace-file "$(LLM_OPTIMIZATIONS_ROOT)/llm-optimizations.code-workspace" \
			--repo-root "$(ROOT_DIR)" \
			--source-pdf "$(PAPER_PDF)" \
			--output-name "$(LLM_OPTIMIZATIONS_PDF_NAME)" \
			--destination-dir "$(LLM_OPTIMIZATIONS_PDF_DIR)"; \
	fi

submission-plan:
	@cat $(EXPERIMENT_DIR)/submission_plan.md

evidence-bundle:
	@printf 'Latest results in %s\n' '$(RESULT_DIR)'
	@find $(RESULT_DIR) -maxdepth 1 -type f | sort

clean:
	rm -f $(CURDIR)/*.aux $(CURDIR)/*.log $(CURDIR)/*.out $(CURDIR)/*.toc $(CURDIR)/$(PAPER_PDF)
