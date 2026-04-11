# Offline Study Summary

- trace count: 96
- trace source: llm-serving-workloads
- workload cases: shared_scenario_multi_turn_knowledge_service, shared_scenario_rag_followup_long_context, shared_scenario_structured_agent_decode

## Overall Policies

## always_recompute

- requests: 96
- mean TTFT (ms): 12.847
- p95 TTFT (ms): 24.286
- mean recompute tokens: 620.76
- mean transferred KiB: 0.0
- decisions: {'recompute': 96}

## always_full_reuse

- requests: 96
- mean TTFT (ms): 8.384
- p95 TTFT (ms): 22.161
- mean recompute tokens: 0
- mean transferred KiB: 19864.333
- decisions: {'recompute': 13, 'full_reuse': 83}

## threshold_partial

- requests: 96
- mean TTFT (ms): 11.371
- p95 TTFT (ms): 22.161
- mean recompute tokens: 384.344
- mean transferred KiB: 7565.333
- decisions: {'recompute': 56, 'partial_reuse': 40}

## heuristic

- requests: 96
- mean TTFT (ms): 8.411
- p95 TTFT (ms): 22.161
- mean recompute tokens: 1.083
- mean transferred KiB: 19829.667
- decisions: {'recompute': 13, 'full_reuse': 79, 'partial_reuse': 4}

## oracle_ttft

- requests: 96
- mean TTFT (ms): 8.384
- p95 TTFT (ms): 22.161
- mean recompute tokens: 0
- mean transferred KiB: 19864.333
- decisions: {'recompute': 13, 'full_reuse': 83}

## heuristic_transfer_underestimated

- requests: 96
- mean TTFT (ms): 8.411
- p95 TTFT (ms): 22.161
- mean recompute tokens: 1.083
- mean transferred KiB: 19829.667
- decisions: {'recompute': 13, 'full_reuse': 79, 'partial_reuse': 4}

## heuristic_transfer_overestimated

- requests: 96
- mean TTFT (ms): 8.411
- p95 TTFT (ms): 22.161
- mean recompute tokens: 1.083
- mean transferred KiB: 19829.667
- decisions: {'recompute': 13, 'full_reuse': 79, 'partial_reuse': 4}

## heuristic_recompute_underestimated

- requests: 96
- mean TTFT (ms): 8.411
- p95 TTFT (ms): 22.161
- mean recompute tokens: 1.083
- mean transferred KiB: 19829.667
- decisions: {'recompute': 13, 'full_reuse': 79, 'partial_reuse': 4}

## heuristic_recompute_overestimated

- requests: 96
- mean TTFT (ms): 8.411
- p95 TTFT (ms): 22.161
- mean recompute tokens: 1.083
- mean transferred KiB: 19829.667
- decisions: {'recompute': 13, 'full_reuse': 79, 'partial_reuse': 4}

## Per-Case Snapshot

### shared_scenario_multi_turn_knowledge_service

- family: session-affine-multi-turn
- requests: 32
- heuristic p95 TTFT (ms): 5.656
- oracle p95 TTFT (ms): 5.656

### shared_scenario_rag_followup_long_context

- family: rag-followup
- requests: 32
- heuristic p95 TTFT (ms): 22.161
- oracle p95 TTFT (ms): 22.161

### shared_scenario_structured_agent_decode

- family: tool-scaffold-agent
- requests: 32
- heuristic p95 TTFT (ms): 5.264
- oracle p95 TTFT (ms): 5.264
