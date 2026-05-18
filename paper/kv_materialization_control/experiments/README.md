# Experiment Notes

This artifact has two experiment paths, and they mean different things.

## Decision Study

Canonical entry:

```bash
make decision-study
```

This path compares:

- `always_recompute`
- `always_full_reuse`
- `threshold_partial`
- `heuristic`
- `oracle_ttft`
- heuristic cost-misestimation sensitivity variants

Paper-facing artifacts emitted under `experiments/results/latest/` now include:

- `offline_summary_table.tex`
- `offline_summary_macros.tex`
- `offline_decision_mix_figure.tex`

The default shared-workload matrix comes directly from the current
`llm-serving-workloads` shared benchmark case order. This repository therefore
does not carry its own second default case list for the offline decision study;
it follows the sibling workload catalog unless you explicitly override
`--workload-case`.

Truthfulness boundary:

- safe claim: how the three-action arrival-time decision surface behaves under
	workload-grounded cost assumptions
- unsafe claim: live serving improvement or complete runtime realization of all
	three actions

## Runtime Boundary Live

Canonical entry:

```bash
make runtime-boundary-live MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
	WORKLOAD_CASE=shared_prefix_multi_tenant_assistant
```

This path uses the same shared workload catalog but answers a different
question: what can the current runtime seam realize online?

Current truthful live interpretation:

- `full_reuse`: supported
- `recompute`: supported
- `partial_reuse`: observed by the policy, but falls back to anchor-scoped
	`full_reuse` on the current prefix-cache path

## Primary Metrics

- TTFT
- prefill recompute tokens
- materialization latency
- KV bytes loaded or transferred
- p95 end-to-end latency
