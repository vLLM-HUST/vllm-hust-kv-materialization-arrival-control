CONDA ?= conda
CONDA_ENV ?= vllm-kv-materialization-exp
CONDA_RUN ?= $(CONDA) run --no-capture-output -n $(CONDA_ENV)
PYTHON ?= $(CONDA_RUN) python
PIP ?= $(CONDA_RUN) python -m pip
PYTEST ?= PYTHONPATH=src $(CONDA_RUN) python -m pytest -q
RUFF ?= $(CONDA_RUN) python -m ruff
BUILD ?= $(CONDA_RUN) python -m build
TECTONIC ?= tectonic
SHARED_ENV_SCRIPT ?= /home/shuhao/llm-optimizations/scripts/bootstrap_shared_env.sh
SHARED_SOURCE_ENV ?= llm-optimizations
SHARED_ENV_NAME ?= $(CONDA_ENV)
BOOTSTRAP_ENV ?= bash scripts/setup_repo_env.sh
WORKLOAD_REPO ?= $(abspath $(CURDIR)/../llm-serving-workloads)
SHARED_WORKLOAD_RESULTS_DIR ?= .benchmarks/results

PACKAGE_IMPORT := vllm_kv_materialization
BENCH_DIR := paper/kv_materialization_control/experiments
PAPER_DIR := paper/kv_materialization_control

.DEFAULT_GOAL := help

.PHONY: help bootstrap-env bootstrap-shared-env install-dev smoke test shared-workloads-smoke shared-workloads-test lint format build bench paper offline-experiment experiment study-experiment shared-workloads-offline paper-experiment live-benchmark shared-workloads-live optimization-live pdf paper-pdf evidence clean

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
		'  make study-experiment  Run the workload-driven experimental-paper pipeline' \
		'  make experiment   Alias of make study-experiment' \
		'  make shared-workloads-offline [WORKLOAD_CASES="..."]  Run shared workload cases through the offline study pipeline' \
		'  make shared-workloads-live MODEL=<model> [WORKLOAD_CASE=<case>]  Run a shared-workload live benchmark' \
		'  make optimization-live MODEL=<model> [WORKLOAD_CASE=<case>]  Alias of make shared-workloads-live' \
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

bootstrap-shared-env:
	$(SHARED_ENV_SCRIPT) --profile generic --source-env '$(SHARED_SOURCE_ENV)' --repo-root "$$PWD" --env-name '$(SHARED_ENV_NAME)'

install-dev:
	@if [ -f '$(WORKLOAD_REPO)/pyproject.toml' ]; then \
		$(PIP) install -e '$(WORKLOAD_REPO)'; \
	else \
		printf 'Skipping sibling llm-serving-workloads install: %s\n' '$(WORKLOAD_REPO)'; \
	fi
	$(PIP) install -e ".[dev]"

smoke:
	PYTHONPATH=src $(PYTHON) -c "import importlib; importlib.import_module('$(PACKAGE_IMPORT)')"

test:
	$(PYTEST)

shared-workloads-smoke:
	@mkdir -p '$(SHARED_WORKLOAD_RESULTS_DIR)'
	PYTHONPATH='$(WORKLOAD_REPO)/src:src' $(PYTHON) -m llm_serving_workloads.shared_workload_smoke \
		--output-json '$(SHARED_WORKLOAD_RESULTS_DIR)/shared_workloads_smoke.json' \
		--output-markdown '$(SHARED_WORKLOAD_RESULTS_DIR)/shared_workloads_smoke.md'

shared-workloads-test: test shared-workloads-smoke

offline-experiment:
	PYTHONPATH=src $(PYTHON) -m vllm_kv_materialization.offline_experiment --policy heuristic --pretty

study-experiment: shared-workloads-offline

experiment: study-experiment

shared-workloads-offline:
	$(MAKE) -C $(PAPER_DIR) experiment PYTHON='$(PYTHON)' WORKLOAD_CASES='$(WORKLOAD_CASES)'

paper-experiment:
	$(MAKE) -C $(PAPER_DIR) experiment PYTHON='$(PYTHON)'

live-benchmark:
	$(MAKE) -C $(PAPER_DIR) live-benchmark PYTHON='$(PYTHON)' MODEL='$(MODEL)' WORKLOAD_CASE='$(WORKLOAD_CASE)' BASE_URL='$(BASE_URL)' REQUEST_RATE='$(REQUEST_RATE)' CONCURRENCY='$(CONCURRENCY)' SEED='$(SEED)' LABEL='$(LABEL)'

shared-workloads-live: live-benchmark

optimization-live: shared-workloads-live

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