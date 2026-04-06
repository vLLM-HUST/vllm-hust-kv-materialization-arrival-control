# GitHub Copilot Instructions

## Repository Role

- Repository: `vllm-general-plugin-template`
- Purpose: reusable standalone template for out-of-tree vLLM plugins

## Critical Boundary

- Do **not** modify `/home/shuhao/reference-repos/vllm` when using this template.
- If a future plugin built from this template truly requires upstream-local changes, clone or vendor vLLM inside the derived repository and patch there.
- The template should teach clean plugin boundaries, not direct edits to the reference checkout.

## Working Rules

- Keep the template minimal and reusable.
- Keep example plugin logic under `src/`.
- When derived plugins need reusable scenario benchmark workloads, point them
	at the sibling `llm-serving-workloads` repository/package as the workload
	source of truth instead of teaching repo-local workload copies.
- Record template changes in this repository's `CHANGELOG.md` only.
- Do not write template-repo changes into `/home/shuhao/sagellm/CHANGELOG.md`.
- Update `README.md` if the recommended plugin boundary changes.
- Do not create `.venv` or `venv`.

## Research Ideation Reference

- When designing new plugin ideas from this template, you may consult
	`/home/shuhao/private-materials` as private reference material.
- Prioritize Shuhao's prior research results and technical summaries,
	especially under `汇报材料/26年学术委员会演讲/`, `项目文档/内部项目/`,
	`项目文档/纵向项目/`, `项目文档/横向项目/`, and `申报材料/`.
- Use those materials to inspire reusable optimization patterns, evaluation
	checklists, and problem framing for derived repositories.
- Do **not** copy private material verbatim into this template, do **not** move
	files out of `private-materials`, and do **not** present proposal content as
	validated implementation results.
- Translate any borrowed idea into clean, reusable plugin seams instead of
	embedding repository-specific private context into the template itself.

## Testing

```bash
PYTHONPATH=src pytest -q
```