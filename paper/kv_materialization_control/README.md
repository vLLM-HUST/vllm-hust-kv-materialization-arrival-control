# KV Materialization Control Paper Workspace

This paper workspace is for a decision artifact, not a generic state-management
paper.

The paper's core question is:

- at request arrival, when reusable state already exists,
- should the system choose `full_reuse`, `partial_reuse`, or `recompute`?

The paper should stay focused on that three-action surface.

## Evidence Layers

This directory keeps three evidence layers separate.

- `decision-study`: workload-grounded offline analysis of the arrival-time
	decision surface
- `runtime-boundary-live`: live execution against a vLLM-compatible endpoint to
	document which actions the current runtime seam actually realizes
- `m2-online-boundary`: matched real-online comparison against
	`always_recompute` and `always_full_reuse`

The manuscript should not blur those layers into a single end-to-end claim.
The completed M2 result is negative. After the original matrix, the existing
catalog was closed with 14 additional canonical-workload pilots and four
five-round confirmations. None confirmed a meaningful significant gain, and
`always_full_reuse` won all 20 added confirmation rounds. The current mechanism
direction stops without per-workload retuning or post-hoc workload search; the
final verdict is fixed as `stop_mechanism_direction` in the issue closure
summary and this paper's boundary.

The 39 in-repo raw-bundle lifecycles are archived in release
`m2-issue3-closure-evidence-20260811`
(<https://github.com/intellistream/kv-materialization-arrival-control/releases/tag/m2-issue3-closure-evidence-20260811>,
asset `m2_raw_bundles_39_lifecycles.tar.gz`). The remaining 102 lifecycles are
aggregate-only supporting evidence, so the 39/102 reproducibility boundary is
retained until those raw bundles are archived to a persistent,
content-addressed location.

## Local Workflow

From the repository root:

```bash
make decision-study
make m2-online-rebuild
make pdf
```

The decision-study target refreshes `experiments/results/latest/` and emits the
JSON, Markdown, and LaTeX-friendly summaries consumed by the draft.

For live runtime-boundary runs, see `experiments/LIVE_EXPERIMENTS.md`.
