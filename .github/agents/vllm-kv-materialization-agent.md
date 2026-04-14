# Agent Notes

## Repository Role

- This repository is the standalone home for request-arrival KV materialization control in vLLM.
- Keep plugin code, workload-driven experiments, and paper assets here.
- Treat the sibling `llm-serving-workloads` repository as the workload source of truth.

## Canonical Workflow

- Prefer the dedicated conda environment `vllm-kv-materialization-exp`.
- Prefer `make bootstrap-env` or `bash scripts/setup_repo_env.sh` for environment setup.
- Prefer the repository root `Makefile` for smoke tests, unit tests, offline study entrypoints, live benchmarks, and paper builds.
- Keep `/home/shuhao/reference-repos/vllm` untouched; if a runtime-local delta becomes unavoidable, carry it inside this repository under `vendor/` or `patches/`.

## Scope Guardrail

- This repository is for request-arrival materialization decisions only.
- The action space is `full_reuse`, `partial_reuse`, or `recompute`.
- Do not reposition this repository as a decode-backend selector, placement policy, eviction controller, or KV-transfer mechanism artifact.
- Treat placement, migration, and eviction as background conditions unless measured evidence in this repository proves they must become first-class variables.

## Evidence Rules

- Keep offline decision-study evidence and live plugin evidence explicitly separated.
- Do not write study-side oracle results as if they were deployed serving gains.
- Do not claim that reusable state is always beneficial; the central thesis is that realizing reuse has a cost and therefore requires control.
- When summarizing results, state whether the evidence is workload-driven offline analysis or online endpoint measurement.

## Design Memory

- Frame the paper as a systems problem about balancing prefill recomputation against KV realization cost, not as a generic caching story.
- Center the artifact narrative on one narrow control hook with a measurable three-action decision surface.
- Use `/home/shuhao/sglang-dp-locality-plugin` as the design reference for repository-level workflow discipline, but keep this repository's technical framing specific to KV materialization.
