# Experiment Notes

Planned comparison surface:

- baseline: always recompute
- baseline: always full reuse
- baseline: fixed-threshold partial reuse
- candidate: adaptive heuristic policy
- baseline: oracle upper bound over the same three-action space
- sensitivity: transfer and recompute cost misestimation around the heuristic

Default offline pipeline:

- uses shared workload cases from `llm-serving-workloads`
- current representative cases:
	- `shared_scenario_multi_turn_knowledge_service`
	- `shared_scenario_rag_followup_long_context`
	- `shared_scenario_structured_agent_decode`

Default live pipeline:

- uses the same shared benchmark case catalog from `llm-serving-workloads`
- defaults to `shared_scenario_multi_turn_knowledge_service`
- can be launched either from this repository or from `llm-serving-workloads`
  via `make kv-materialization-live`

Primary metrics:

- TTFT
- prefill recompute tokens
- materialization latency
- KV bytes loaded or transferred
- p95 end-to-end latency
