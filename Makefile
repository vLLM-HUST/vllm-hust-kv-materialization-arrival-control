PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
PYTEST ?= PYTHONPATH=src $(PYTHON) -m pytest -q
RUFF ?= $(PYTHON) -m ruff
BUILD ?= $(PYTHON) -m build
SHARED_ENV_SCRIPT ?= /home/shuhao/llm-optimizations/scripts/bootstrap_shared_env.sh
SHARED_PROFILE ?= vllm-research
SHARED_ENV_NAME ?= vllm-exp

PACKAGE_IMPORT := vllm_general_plugin_template
BENCH_DIR := tests
PAPER_DIR :=

.DEFAULT_GOAL := help

.PHONY: help bootstrap-shared-env install-dev smoke test lint format build bench paper clean

help:
	@printf '%s\n' \
		'Common targets:' \
		'  make install-dev  Install the package in editable mode with dev extras' \
		'  make smoke        Import-check the top-level package' \
		'  make test         Run the unit test suite' \
		'  make lint         Run ruff checks' \
		'  make format       Run ruff formatting' \
		'  make build        Build sdist and wheel artifacts' \
		'  make bench        Show the benchmark workspace for this repo' \
		'  make paper        Show the paper workspace for this repo' \
		'  make clean        Remove common local build caches'

bootstrap-shared-env:
	$(SHARED_ENV_SCRIPT) --profile $(SHARED_PROFILE) --repo-root "$$PWD" --env-name '$(SHARED_ENV_NAME)'

install-dev:
	$(PIP) install -e ".[dev]"

smoke:
	PYTHONPATH=src $(PYTHON) -c "import importlib; importlib.import_module('$(PACKAGE_IMPORT)')"

test:
	$(PYTEST)

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