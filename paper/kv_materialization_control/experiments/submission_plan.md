# Submission Plan

## Current Repository Scope

- policy surface: request-arrival KV materialization
- action space: `full_reuse`, `partial_reuse`, `recompute`
- current evidence: offline trace-driven study with paper-facing summaries

## Next Study Steps

1. Replace the checked-in synthetic trace with workload-carrier traces derived from `llm-serving-workloads`.
2. Add oracle and cost-misestimation sensitivity baselines.
3. Wire the same policy interface into a vLLM plugin hook and validate online TTFT behavior.
4. Expand the paper from skeleton form into a full systems draft with workload, methodology, and ablation sections.
