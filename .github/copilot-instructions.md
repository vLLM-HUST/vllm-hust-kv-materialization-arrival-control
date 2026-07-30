# GitHub Copilot Instructions

## Repository Role

- Repository: `kv-materialization-arrival-control`
- Purpose: standalone vLLM adaptive KV materialization plugin and paper artifact

## Critical Boundary

- Do **not** modify `/home/shuhao/reference-repos/vllm` for this repository's work.
- Keep the reference vLLM checkout clean.
- If upstream-local experimentation becomes unavoidable, do it inside this repository instead under `vendor/` or `patches/`.

## Working Rules

- Keep plugin logic under `src/vllm_kv_materialization/`.
- Keep paper materials under `paper/`.
- Keep related-work PDFs under `paper/related_works/`.
- Keep experiment drivers under `scripts/` and `paper/.../experiments/`.
- Prefer the dedicated conda environment `vllm-kv-materialization-exp` for this repository.
- When this repository uses scenario-grounded workloads, consume them from the sibling `llm-serving-workloads` repository/package.
- Update this repository's `CHANGELOG.md` and `README.md` for user-visible behavior changes.
- Do not write `kv-materialization-arrival-control` changes into `/home/shuhao/sagellm/CHANGELOG.md`.
- Do not create `.venv` or `venv`.

## Research Scope

- Focus on request-arrival KV materialization decisions.
- The main action space is `full_reuse`, `partial_reuse`, or `recompute`.
- Do not reposition this repository as a decode-placement policy artifact or as another eviction-control line.

## Testing

```bash
PYTHONPATH=src pytest -q
```

## Conda Execution Rule

- Run repo-local experiments, benchmarks, paper artifact generation, smoke checks, and tests in the dedicated conda environment `vllm-kv-materialization-exp`.
- Prefer explicit `conda run -n vllm-kv-materialization-exp ...` over relying on shell activation or the ambient `python`.
- If a repo-local command omits `conda run`, treat it as shorthand for running inside `vllm-kv-materialization-exp`.
