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

.PHONY: help bootstrap-env install-dev smoke test shared-workloads-smoke shared-workloads-test lint format build bench paper offline-experiment experiment decision-study study-experiment shared-workloads-offline paper-experiment runtime-boundary-live live-benchmark shared-workloads-live optimization-live m1-online-rebuild m2-online-boundary m2-online-rebuild m2-candidate-pilot m2-candidate-pilot-rebuild pdf paper-pdf evidence clean

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
		--model '$(MODEL)'

m2-candidate-pilot-rebuild:
	PYTHONPATH=src $(PYTHON) $(BENCH_DIR)/aggregate_m2_candidate_pilot.py \
		--input-dir '$(M2_PILOT_SUITE_DIR)' \
		--output-dir '$(M2_PILOT_RESULTS_DIR)'

pdf: paper-pdf

paper-pdf:
	$(MAKE) -C $(PAPER_DIR) pdf TECTONIC='$(TECTONIC)' PYTHON='$(PYTHON)'

evidence:
	$(MAKE) -C $(PAPER_DIR) evidence

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
