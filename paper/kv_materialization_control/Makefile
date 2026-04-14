PYTHON ?= python3
TECTONIC ?= tectonic
ROOT_DIR := $(abspath ../..)
EXPERIMENT_DIR := $(CURDIR)/experiments
RESULT_DIR := $(EXPERIMENT_DIR)/results/latest
PAPER_TEX := kv_materialization_control.tex
PAPER_PDF := kv_materialization_control.pdf
DEFAULT_WORKLOAD_CASES := shared_scenario_multi_turn_knowledge_service shared_scenario_rag_followup_long_context shared_scenario_structured_agent_decode
DEFAULT_LIVE_WORKLOAD_CASE := shared_scenario_multi_turn_knowledge_service

.DEFAULT_GOAL := help

.PHONY: help experiment live-benchmark optimization-live pdf clean evidence-bundle submission-plan

help:
	@printf '%s\n' \
		'Paper targets:' \
		'  make experiment      Run the workload-driven offline study and refresh latest paper-facing artifacts' \
		'  make live-benchmark  Run a shared-workload live benchmark against a vLLM endpoint' \
		'  make optimization-live Alias of make live-benchmark' \
		'  make pdf             Build the paper PDF with tectonic' \
		'  make evidence-bundle Show the latest generated evidence files' \
		'  make submission-plan Print the paper submission plan note'

experiment:
	PYTHONPATH=$(ROOT_DIR)/src $(PYTHON) $(EXPERIMENT_DIR)/run_offline_study.py \
		$(foreach case,$(if $(WORKLOAD_CASES),$(WORKLOAD_CASES),$(DEFAULT_WORKLOAD_CASES)),--workload-case $(case)) \
		--output-dir $(RESULT_DIR)

live-benchmark:
	@test -n "$(MODEL)" || { echo 'MODEL is required. Usage: make live-benchmark MODEL=/path/to/model [WORKLOAD_CASE=shared_scenario_multi_turn_knowledge_service]' >&2; exit 2; }
	PYTHONPATH=$(ROOT_DIR)/src $(PYTHON) $(EXPERIMENT_DIR)/run_openai_workloads.py \
		--base-url "$${BASE_URL:-http://127.0.0.1:8011}" \
		--model "$(MODEL)" \
		--workload-case "$${WORKLOAD_CASE:-$(DEFAULT_LIVE_WORKLOAD_CASE)}" \
		--api-key "$${OPENAI_API_KEY:-}" \
		--user-agent "$${OPENAI_HTTP_USER_AGENT:-python-httpx/0.28.1}" \
		$(if $(REQUEST_RATE),--request-rate $(REQUEST_RATE),) \
		$(if $(CONCURRENCY),--concurrency $(CONCURRENCY),) \
		$(if $(SEED),--seed $(SEED),) \
		--output $(EXPERIMENT_DIR)/results/live/$${LABEL:-$${WORKLOAD_CASE:-$(DEFAULT_LIVE_WORKLOAD_CASE)}}.json

optimization-live: live-benchmark

pdf: experiment
	cd $(CURDIR) && $(TECTONIC) --keep-logs $(PAPER_TEX)

submission-plan:
	@cat $(EXPERIMENT_DIR)/submission_plan.md

evidence-bundle:
	@printf 'Latest results in %s\n' '$(RESULT_DIR)'
	@find $(RESULT_DIR) -maxdepth 1 -type f | sort

clean:
	rm -f $(CURDIR)/*.aux $(CURDIR)/*.log $(CURDIR)/*.out $(CURDIR)/*.toc $(CURDIR)/$(PAPER_PDF)
