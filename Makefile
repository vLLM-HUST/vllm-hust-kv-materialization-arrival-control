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

PACKAGE_IMPORT := vllm_kv_materialization
BENCH_DIR := paper/kv_materialization_control/experiments
PAPER_DIR := paper/kv_materialization_control

.DEFAULT_GOAL := help

.PHONY: help bootstrap-env bootstrap-shared-env install-dev smoke test lint format build bench paper offline-experiment experiment paper-experiment live-benchmark pdf paper-pdf evidence clean

help:
	@printf '%s\n' \
		'Common targets:' \
		'  make bootstrap-env Clone the shared baseline env into the repo-owned conda env and install this repo' \
		'  make install-dev  Install the package in editable mode with dev extras' \
		'  make smoke        Import-check the top-level package' \
		'  make test         Run the unit test suite' \
		'  make offline-experiment  Run the offline materialization policy harness' \
		'  make experiment   Run the paper offline study pipeline and refresh latest results' \
		'  make live-benchmark MODEL=<model> [WORKLOAD=short_low]  Run a real-model endpoint benchmark' \
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
	$(PIP) install -e ".[dev]"

smoke:
	PYTHONPATH=src $(PYTHON) -c "import importlib; importlib.import_module('$(PACKAGE_IMPORT)')"

test:
	$(PYTEST)

offline-experiment:
	PYTHONPATH=src $(PYTHON) -m vllm_kv_materialization.offline_experiment --policy heuristic --pretty

experiment: paper-experiment

paper-experiment:
	$(MAKE) -C $(PAPER_DIR) experiment PYTHON='$(PYTHON)'

live-benchmark:
	$(MAKE) -C $(PAPER_DIR) live-benchmark PYTHON='$(PYTHON)' MODEL='$(MODEL)' WORKLOAD='$(WORKLOAD)'

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