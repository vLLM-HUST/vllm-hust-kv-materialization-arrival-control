CONDA ?= conda
CONDA_ENV ?= vllm-kv-materialization-exp
CONDA_RUN ?= $(CONDA) run --no-capture-output -n $(CONDA_ENV)
PYTHON ?= $(CONDA_RUN) python
PIP ?= $(CONDA_RUN) env -u LD_LIBRARY_PATH python -m pip
PYTEST ?= PYTHONPATH=src $(CONDA_RUN) python -m pytest -q
RUFF ?= $(CONDA_RUN) python -m ruff
BUILD ?= $(CONDA_RUN) python -m build
TECTONIC ?= tectonic
BOOTSTRAP_ENV ?= bash scripts/setup_repo_env.sh
SHARED_WORKLOAD_RESULTS_DIR ?= .benchmarks/results

PACKAGE_IMPORT := vllm_kv_materialization
BENCH_DIR := paper/kv_materialization_control/experiments
PAPER_DIR := paper/kv_materialization_control

.DEFAULT_GOAL := help

M2_SUITE_DIR ?= /tmp/kv_materialization_m2_online
M2_REBUILD_INPUT_DIR ?= $(BENCH_DIR)/results/m2_online_boundary_20260803
M2_RESULTS_DIR ?= $(M2_REBUILD_INPUT_DIR)/generated
M2_PILOT_SUITE_DIR ?= /tmp/kv_materialization_m2_candidate_pilot
M2_PILOT_RESULTS_DIR ?= $(M2_PILOT_SUITE_DIR)/generated
M2_ANCHOR_CONFIRMATION_DIR ?= /tmp/kv_materialization_m2_anchor_confirmation
M2_ANCHOR_CONFIRMATION_RESULTS_DIR ?= $(M2_ANCHOR_CONFIRMATION_DIR)/generated
M2_PILOT_CANDIDATE_SET ?= offline-ranked
M2_PILOT_SHARD_INDEX ?= 0
M2_PILOT_NUM_SHARDS ?= 1
M2_SIGNIFICANCE_CONFIRMATION_DIR ?= /tmp/kv_materialization_m2_significance_confirmation
M2_SIGNIFICANCE_CONFIRMATION_RESULTS_DIR ?= $(M2_SIGNIFICANCE_CONFIRMATION_DIR)/generated
G0_PILOT_DOCS_DIR ?= docs/g0

.PHONY: help bootstrap-env install-dev smoke test shared-workloads-smoke shared-workloads-test lint format build bench paper offline-experiment experiment decision-study study-experiment shared-workloads-offline paper-experiment runtime-boundary-live live-benchmark shared-workloads-live optimization-live m1-online-rebuild m2-online-boundary m2-online-rebuild m2-candidate-pilot m2-candidate-pilot-rebuild m2-anchor-confirmation m2-anchor-confirmation-rebuild m2-significance-confirmation m2-significance-confirmation-rebuild g0-init g0-rebuild g0-pilot-report pdf paper-pdf evidence clean

help:
	@printf '%s\n' \
		'Common targets:' \
		'  make bootstrap-env Clone the shared baseline env into the repo-owned conda env and install this repo' \
		'  make install-dev  Install the package in editable mode with dev extras' \
		'  make smoke        Import-check the top-level package' \
		'  make test         Run the unit test suite' \
		'  make shared-workloads-smoke Emit a generic shared workload compatibility report under .benchmarks/results' \
		'  make shared-workloads-test  Run unit tests plus the shared workload compatibility report' \
		'  make offline-experiment  Run the tiny policy harness' \
		'  make decision-study [WORKLOAD_CASES="..."]  Run the workload-driven arrival-time decision study' \
		'  make study-experiment  Compatibility alias of make decision-study' \
		'  make experiment   Compatibility alias of make decision-study' \
		'  make shared-workloads-offline [WORKLOAD_CASES="..."]  Compatibility alias of make decision-study' \
		'  make runtime-boundary-live MODEL=<model> [WORKLOAD_CASE=<case>]  Run the live runtime-boundary benchmark' \
		'  make m1-online-rebuild  Rebuild M1 online CSV/TeX from committed raw bundles' \
		'  make m2-online-boundary MODEL=<model> [M2_SUITE_DIR=/outside/worktree]  Run the preregistered M2 matrix' \
		'  make m2-online-rebuild M2_SUITE_DIR=<validated-suite> [M2_RESULTS_DIR=<dir>]  Rebuild M2 artifacts' \
		'  make m2-candidate-pilot MODEL=<model> [M2_PILOT_SUITE_DIR=/outside/worktree]  Run preregistered candidate pilot' \
		'  make m2-candidate-pilot-rebuild M2_PILOT_SUITE_DIR=<suite>  Rebuild pilot verdict' \
		'  make m2-anchor-confirmation MODEL=<model>  Run promoted-workload confirmation' \
		'  make m2-anchor-confirmation-rebuild M2_ANCHOR_CONFIRMATION_DIR=<suite>  Rebuild confirmation verdict' \
		'  make m2-significance-confirmation MODEL=<model> WORKLOAD_CASE=<promoted> REQUEST_RATE=<rate>  Run five-round significance confirmation' \
		'  make g0-init G0_SUITE_DIR=/outside/suite BURSTGPT_TRACE=<trace> SERVEGEN_TRACE=<trace>  Initialize G0 pathology gate' \
		'  make g0-rebuild G0_SUITE_DIR=/outside/suite  Rebuild fail-closed G0 verdict from raw bundles' \
		'  make g0-pilot-report  Rebuild the explicitly non-verdict real-runtime pilot report' \
		'  make shared-workloads-live MODEL=<model> [WORKLOAD_CASE=<case>]  Compatibility alias of make runtime-boundary-live' \
		'  make optimization-live MODEL=<model> [WORKLOAD_CASE=<case>]  Compatibility alias of make runtime-boundary-live' \
		'  make pdf          Build the paper PDF after refreshing latest offline-study results' \
		'  make evidence     Print the latest study summary paths' \
		'  make lint         Run ruff checks' \
		'  make format       Run ruff formatting' \
		'  make build        Build sdist and wheel artifacts' \
		'  make bench        Show the benchmark workspace for this repo' \
		'  make paper        Show the paper workspace for this repo' \
		'  make clean        Remove common local build caches' \
		'' \
		'Default environment:' \
		'  CONDA_ENV=$(CONDA_ENV)'

bootstrap-env:
	$(BOOTSTRAP_ENV)

install-dev:
	$(PIP) install -e ".[dev]"

smoke:
	PYTHONPATH=src $(PYTHON) -c "import importlib; importlib.import_module('$(PACKAGE_IMPORT)')"

test:
	$(PYTEST)

shared-workloads-smoke:
	@mkdir -p '$(SHARED_WORKLOAD_RESULTS_DIR)'
	$(CONDA_RUN) env PYTHONPATH='src' python -m llm_serving_workloads.shared_workload_smoke \
		--output-json '$(SHARED_WORKLOAD_RESULTS_DIR)/shared_workloads_smoke.json' \
		--output-markdown '$(SHARED_WORKLOAD_RESULTS_DIR)/shared_workloads_smoke.md'

shared-workloads-test: test shared-workloads-smoke

offline-experiment:
	PYTHONPATH=src $(PYTHON) -m vllm_kv_materialization.offline_experiment --policy heuristic --pretty

decision-study:
	$(MAKE) -C $(PAPER_DIR) decision-study PYTHON='$(PYTHON)' WORKLOAD_CASES='$(WORKLOAD_CASES)'

study-experiment: decision-study

experiment: decision-study

shared-workloads-offline: decision-study

paper-experiment:
	$(MAKE) -C $(PAPER_DIR) decision-study PYTHON='$(PYTHON)'

runtime-boundary-live:
	$(MAKE) -C $(PAPER_DIR) runtime-boundary-live PYTHON='$(PYTHON)' MODEL='$(MODEL)' WORKLOAD_CASE='$(WORKLOAD_CASE)' BASE_URL='$(BASE_URL)' REQUEST_RATE='$(REQUEST_RATE)' CONCURRENCY='$(CONCURRENCY)' SEED='$(SEED)' LABEL='$(LABEL)'

live-benchmark: runtime-boundary-live

shared-workloads-live: runtime-boundary-live

optimization-live: runtime-boundary-live

m1-online-rebuild:
	PYTHONPATH=src $(PYTHON) $(BENCH_DIR)/verify_m1_online_rebuild.py \
		--input-dir $(BENCH_DIR)/results/m1_formal_approved_complete_20260801 \
		--generated-dir $(BENCH_DIR)/results/m1_formal_approved_complete_20260801/generated
	PYTHONPATH=src $(PYTHON) $(BENCH_DIR)/aggregate_online_results.py \
		--input-dir $(BENCH_DIR)/results/m1_formal_approved_complete_20260801 \
		--output-dir $(BENCH_DIR)/results/m1_formal_approved_complete_20260801/generated

m2-online-boundary:
	PYTHONPATH=src $(PYTHON) $(BENCH_DIR)/run_m2_online_boundary.py \
		--suite-dir '$(M2_SUITE_DIR)' \
		--model '$(MODEL)'

m2-online-rebuild:
	PYTHONPATH=src $(PYTHON) $(BENCH_DIR)/aggregate_m2_boundary.py \
		--input-dir '$(M2_REBUILD_INPUT_DIR)' \
		--output-dir '$(M2_RESULTS_DIR)'

m2-candidate-pilot:
	PYTHONPATH=src $(PYTHON) $(BENCH_DIR)/run_m2_candidate_pilot.py \
		--suite-dir '$(M2_PILOT_SUITE_DIR)' \
		--model '$(MODEL)' \
		--candidate-set '$(M2_PILOT_CANDIDATE_SET)' \
		--shard-index '$(M2_PILOT_SHARD_INDEX)' \
		--num-shards '$(M2_PILOT_NUM_SHARDS)'

m2-candidate-pilot-rebuild:
	PYTHONPATH=src $(PYTHON) $(BENCH_DIR)/aggregate_m2_candidate_pilot.py \
		--input-dir '$(M2_PILOT_SUITE_DIR)' \
		--output-dir '$(M2_PILOT_RESULTS_DIR)'

m2-anchor-confirmation:
	PYTHONPATH=src $(PYTHON) $(BENCH_DIR)/run_m2_anchor_confirmation.py \
		--suite-dir '$(M2_ANCHOR_CONFIRMATION_DIR)' \
		--model '$(MODEL)'

m2-anchor-confirmation-rebuild:
	PYTHONPATH=src $(PYTHON) $(BENCH_DIR)/aggregate_m2_anchor_confirmation.py \
		--input-dir '$(M2_ANCHOR_CONFIRMATION_DIR)' \
		--output-dir '$(M2_ANCHOR_CONFIRMATION_RESULTS_DIR)'

m2-significance-confirmation:
	PYTHONPATH=src $(PYTHON) $(BENCH_DIR)/run_m2_significance_confirmation.py \
		--suite-dir '$(M2_SIGNIFICANCE_CONFIRMATION_DIR)' \
		--model '$(MODEL)' \
		--workload '$(WORKLOAD_CASE)' \
		--request-rate '$(REQUEST_RATE)' \
		--max-output-tokens '$(MAX_OUTPUT_TOKENS)'

m2-significance-confirmation-rebuild:
	PYTHONPATH=src $(PYTHON) $(BENCH_DIR)/aggregate_m2_significance_confirmation.py \
		--input-dir '$(M2_SIGNIFICANCE_CONFIRMATION_DIR)' \
		--output-dir '$(M2_SIGNIFICANCE_CONFIRMATION_RESULTS_DIR)'

g0-init:
	PYTHONPATH=src $(PYTHON) scripts/g0_pathology.py init --suite-dir '$(G0_SUITE_DIR)' --burstgpt-trace '$(BURSTGPT_TRACE)' --servegen-trace '$(SERVEGEN_TRACE)'

g0-rebuild:
	PYTHONPATH=src $(PYTHON) scripts/g0_pathology.py rebuild --suite-dir '$(G0_SUITE_DIR)'

g0-formal-rebuild:
	python3 scripts/rebuild_g0_formal.py \
		--suite-dir '$(G0_SUITE_DIR)' \
		--run-root '$(G0_RUN_ROOT)' \
		--output-json '$(G0_FORMAL_JSON)' \
		--output-markdown '$(G0_FORMAL_MARKDOWN)' \
		--output-pathology-csv '$(G0_PATHOLOGY_CSV)' \
		--output-pathology-svg '$(G0_PATHOLOGY_SVG)'

g0-formal-manifest:
	python3 scripts/build_g0_raw_manifest.py build \
		--suite-dir '$(G0_SUITE_DIR)' \
		--run-root '$(G0_RUN_ROOT)' \
		--rejected-root '$(G0_REJECTED_ROOT)' \
		--report-root '$(G0_REPORT_ROOT)' \
		--output '$(G0_RAW_MANIFEST)'

g0-formal-manifest-verify:
	python3 scripts/build_g0_raw_manifest.py verify --manifest '$(G0_RAW_MANIFEST)'

g0-pilot-report:
	python3 scripts/summarize_g0_pilot.py \
		--run burstgpt/high/no_control=/tmp/g0-formal-pilot-burstgpt-high-nocontrol-r1 \
		--run burstgpt/high/concurrency_cap=/tmp/g0-formal-pilot-burstgpt-high-concurrency4-r1 \
		--run burstgpt/high/request_token_bucket=/tmp/g0-formal-pilot-burstgpt-high-tokenbucket8c4-r1 \
		--run burstgpt/high/materialization_paced_oracle=/tmp/g0-formal-pilot-burstgpt-high-oracle-r1 \
		--run burstgpt/moderate/no_control=/tmp/g0-formal-pilot-burstgpt-moderate-nocontrol-r1 \
		--run burstgpt/moderate/request_token_bucket=/tmp/g0-formal-pilot-burstgpt-moderate-tokenbucket8c4-r1 \
		--run burstgpt/moderate/materialization_paced_oracle=/tmp/g0-formal-pilot-burstgpt-moderate-oracle-r1 \
		--run burstgpt/low_control/no_control=/tmp/g0-low-control-v2-burstgpt-nocontrol-r1 \
		--run burstgpt/low_control/materialization_paced_oracle=/tmp/g0-low-control-v2-burstgpt-oracle-r1 \
		--run servegen/high/no_control=/tmp/g0-formal-pilot-servegen-high-nocontrol-r1 \
		--run servegen/high/request_token_bucket=/tmp/g0-formal-pilot-servegen-high-tokenbucket8c4-r1 \
		--run servegen/high/materialization_paced_oracle=/tmp/g0-formal-pilot-servegen-high-oracle-r1 \
		--run servegen/moderate/no_control=/tmp/g0-formal-pilot-servegen-moderate-nocontrol-r1 \
		--run servegen/moderate/request_token_bucket=/tmp/g0-formal-pilot-servegen-moderate-tokenbucket8c4-r1 \
		--run servegen/moderate/materialization_paced_oracle=/tmp/g0-formal-pilot-servegen-moderate-oracle-r1 \
		--run servegen/low_control/no_control=/tmp/g0-low-control-v2-servegen-nocontrol-r1 \
		--run servegen/low_control/materialization_paced_oracle=/tmp/g0-low-control-v2-servegen-oracle-r1 \
		--frontier-run burstgpt/high/oracle_b4=/tmp/g0-formal-pilot-burstgpt-high-oracle-r1 \
		--frontier-run burstgpt/high/oracle_b8=/tmp/g0-frontier-burstgpt-high-oracle-b8-r1 \
		--frontier-run burstgpt/high/oracle_b16=/tmp/g0-frontier-burstgpt-high-oracle-b16-r1 \
		--frontier-run burstgpt/high/oracle_b32=/tmp/g0-frontier-burstgpt-high-oracle-b32-r1 \
		--frontier-run burstgpt/moderate/oracle_b4=/tmp/g0-formal-pilot-burstgpt-moderate-oracle-r1 \
		--frontier-run burstgpt/moderate/oracle_b8=/tmp/g0-frontier-v3-burstgpt-moderate-oracle-b8-r1 \
		--frontier-run burstgpt/moderate/oracle_b16=/tmp/g0-frontier-v3-burstgpt-moderate-oracle-b16-r1 \
		--frontier-run burstgpt/moderate/oracle_b32=/tmp/g0-frontier-v3-burstgpt-moderate-oracle-b32-r1 \
		--frontier-run servegen/high/oracle_b4=/tmp/g0-formal-pilot-servegen-high-oracle-r1 \
		--frontier-run servegen/high/oracle_b8=/tmp/g0-frontier-v3-servegen-high-oracle-b8-r1 \
		--frontier-run servegen/high/oracle_b16=/tmp/g0-frontier-v3-servegen-high-oracle-b16-r1 \
		--frontier-run servegen/high/oracle_b32=/tmp/g0-frontier-v3-servegen-high-oracle-b32-r1 \
		--frontier-run servegen/moderate/oracle_b4=/tmp/g0-formal-pilot-servegen-moderate-oracle-r1 \
		--frontier-run servegen/moderate/oracle_b8=/tmp/g0-frontier-v3-servegen-moderate-oracle-b8-r1 \
		--frontier-run servegen/moderate/oracle_b16=/tmp/g0-frontier-v3-servegen-moderate-oracle-b16-r1 \
		--frontier-run servegen/moderate/oracle_b32=/tmp/g0-frontier-v3-servegen-moderate-oracle-b32-r1 \
		--output-json '$(G0_PILOT_DOCS_DIR)/pilot_20260831.json' \
		--output-markdown '$(G0_PILOT_DOCS_DIR)/pilot_20260831.md'

pdf: paper-pdf

paper-pdf:
	$(MAKE) -C $(PAPER_DIR) pdf TECTONIC='$(TECTONIC)' PYTHON='$(PYTHON)'

evidence:
	$(MAKE) -C $(PAPER_DIR) evidence-bundle

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

build:
	$(BUILD)

bench:
	@printf 'Benchmark assets: %s\n' '$(BENCH_DIR)'

paper:
	@printf 'Paper assets: %s\n' '$(PAPER_DIR)'

clean:
	rm -rf build dist .pytest_cache .ruff_cache .mypy_cache .coverage
