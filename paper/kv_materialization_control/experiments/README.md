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

The default shared-workload matrix comes from `llm-serving-workloads` and now
includes:

- `shared_scenario_multi_turn_knowledge_service`
- `shared_scenario_rag_followup_long_context`
- `shared_scenario_structured_agent_decode`
- `shared_prefix_multi_tenant_assistant`
- `session_continuation_with_maintenance`
- `dynamic_rag_corpus_update`

Those cases give one matrix with exact continuation, long-context retrieval,
schema-heavy structured decode, prefix-rich multi-tenancy, long-context
continuation, and dynamic retrieval follow-up.

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
