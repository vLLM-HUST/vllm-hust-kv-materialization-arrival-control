# Agent Notes

## Repository Role

- This repository is the canonical starting point for new standalone optimization repositories in the vLLM line.
- Keep it minimal, reusable, and template-oriented.

## New Repository Rule

- When a new optimization idea does not belong to an existing repository, start here.
- Copy this repository into a new child repository, rename the package and plugin identifiers, then add the new repo-specific scope, experiments, and paper assets there.
- Do not start a new optimization line by cloning another research repository unless the user explicitly requests that exception.

## Canonical Workflow

- Prefer `make bootstrap-shared-env` for environment setup.
- Prefer the repository root `Makefile` for smoke tests, unit tests, linting, packaging, and future template validation.

## Design Memory

- Use `/home/shuhao/sglang-dp-locality-plugin` as the repository-design reference when expanding this template's root layout, README structure, benchmark and paper navigation, or top-level conventions.
- This template should absorb the reusable repository-design lessons from the most complete research repositories in the workspace, while staying generic enough for future plugin ideas.
