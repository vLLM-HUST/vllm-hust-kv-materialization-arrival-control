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
- `partial_reuse`: supported only at block-aligned granularity on the current
	prefix-cache path, with aligned lookup capping, aligned shared-cache commit
	capping, and request-scoped segmented tail hashing

The current paper-facing live matrix is:

- old seam + baseline knobs (`floor=256`, `confidence_penalty=4.0`)
- old seam + tuned knobs (`floor=128`, `confidence_penalty=8.0`)
- new segmented seam + baseline knobs (`floor=256`, `confidence_penalty=4.0`)
- new segmented seam + tuned knobs (`floor=128`, `confidence_penalty=8.0`)

Representative live results:

- `shared_scenario_multi_turn_knowledge_service`
	old baseline: mean `3289.302 ms`, p95 `3641.928 ms`, throughput `1.209 rps`
	old tuned: mean `3860.692 ms`, p95 `4170.369 ms`, throughput `1.031 rps`
	new segmented baseline: mean `3054.712 ms`, p95 `3383.972 ms`, throughput `1.303 rps`
	new segmented tuned: mean `2980.648 ms`, p95 `3214.822 ms`, throughput `1.335 rps`
- `shared_tool_scaffold_agent`
	old baseline: mean `8856.437 ms`, p95 `10627.872 ms`, throughput `0.896 rps`
	old tuned: mean `11068.224 ms`, p95 `12187.492 ms`, throughput `0.717 rps`
	new segmented baseline: mean `9362.399 ms`, p95 `10302.383 ms`, throughput `0.848 rps`
	new segmented tuned: mean `9186.471 ms`, p95 `10182.569 ms`, throughput `0.865 rps`
- `dynamic_rag_corpus_update` on tokenizer-faithful live generation
	new segmented tuned: mean `2634.091 ms`, p95 `3073.478 ms`, throughput `1.510 rps`

Current truthful interpretation:

- the stronger segmented seam is enough to recover the tuned `partial_reuse`
	path from the earlier negative online point into a competitive one
- the segmented seam alone is not a universal gain under conservative baseline
	knobs, so the claim must stay workload-dependent rather than global
- the new segmented-baseline decision mix is already workload-sensitive:
	knowledge-service realized `8` effective `recompute` requests plus `24`
	effective `partial_reuse` requests, while tool-scaffold realized `48`
	effective `partial_reuse` requests plus `16` effective `full_reuse`
- workload construction fidelity matters for truthful online claims: the
	corrected `dynamic_rag_corpus_update` rerun showed that the earlier 32K live
	overflow was caused by whitespace-tokenized workload generation, not by the
	case itself or by a policy defect; with the real Qwen tokenizer, the case ran
	cleanly and realized `8` effective `partial_reuse` requests plus `24`
	effective `full_reuse` requests
	requests after runtime re-ranking

## Primary Metrics

- TTFT
- prefill recompute tokens
- materialization latency
- KV bytes loaded or transferred
- p95 end-to-end latency
