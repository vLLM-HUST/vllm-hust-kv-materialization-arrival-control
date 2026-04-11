# Agent Notes

## Repository Role

- Repository: `vllm-kv-materialization-plugin`
- Purpose: standalone vLLM plugin and research artifact for adaptive KV materialization
- Scope: out-of-tree plugin logic, trace-driven experiments, paper draft, and related-work archive

## Working Rule

- Keep the core plugin under `src/vllm_kv_materialization/`.
- Keep experiment scripts under `scripts/` and `paper/.../experiments/`.
- Keep paper material under `paper/`.
- Keep related-work PDFs inside `paper/related_works/`.

## Research Boundary

- Focus on request-arrival materialization decisions: full reuse, partial reuse, or recompute.
- Do not reframe this repository as another decode-placement or eviction-policy project.
- Treat worker placement and eviction timing as background conditions unless a later result proves they must become first-class variables.

## Canonical Workflow

- Prefer the dedicated conda environment `vllm-kv-materialization-exp` for this repository.
- Prefer `make bootstrap-env` or `bash scripts/setup_repo_env.sh` for environment setup.
- Prefer the repository root `Makefile` for smoke tests, unit tests, offline experiments, live benchmarks, and packaging.
