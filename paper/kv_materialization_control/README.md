# KV Materialization Control Paper Workspace

This paper workspace is for a decision artifact, not a generic state-management
paper.

The paper's core question is:

- at request arrival, when reusable state already exists,
- should the system choose `full_reuse`, `partial_reuse`, or `recompute`?

The paper should stay focused on that three-action surface.

## Evidence Layers

This directory keeps two evidence layers separate.

- `decision-study`: workload-grounded offline analysis of the arrival-time
	decision surface
- `runtime-boundary-live`: live execution against a vLLM-compatible endpoint to
	document which actions the current runtime seam actually realizes

The manuscript should not blur those layers into a single end-to-end claim.

## Local Workflow

From the repository root:

```bash
make decision-study
make pdf
```

The decision-study target refreshes `experiments/results/latest/` and emits the
JSON, Markdown, and LaTeX-friendly summaries consumed by the draft.

For live runtime-boundary runs, see `experiments/LIVE_EXPERIMENTS.md`.
