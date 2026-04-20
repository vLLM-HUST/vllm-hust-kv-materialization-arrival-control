# Arrival-Time Decision Study Summary

- trace count: 208
- trace source: llm-serving-workloads shared benchmark catalog
- workload cases: shared_scenario_multi_turn_knowledge_service, shared_scenario_rag_followup_long_context, shared_scenario_structured_agent_decode, shared_prefix_multi_tenant_assistant, session_continuation_with_maintenance, dynamic_rag_corpus_update
- claim boundary: offline decision-surface evidence only; no live runtime-gain claim

## Overall Policies

## always_recompute

- requests: 208
- mean TTFT (ms): 18.769
- p95 TTFT (ms): 39.909
- mean recompute tokens: 918.37
- mean transferred KiB: 0.0
- decisions: {'recompute': 208}

## always_full_reuse

- requests: 208
- mean TTFT (ms): 9.912
- p95 TTFT (ms): 21.1
- mean recompute tokens: 0
- mean transferred KiB: 29387.846
- decisions: {'recompute': 18, 'full_reuse': 190}

## threshold_partial

- requests: 208
- mean TTFT (ms): 15.449
- p95 TTFT (ms): 30.99
- mean recompute tokens: 504.154
- mean transferred KiB: 13254.923
- decisions: {'recompute': 78, 'partial_reuse': 130}

## heuristic

- requests: 208
- mean TTFT (ms): 10.782
- p95 TTFT (ms): 22.161
- mean recompute tokens: 18.644
- mean transferred KiB: 28791.231
- decisions: {'recompute': 18, 'full_reuse': 168, 'partial_reuse': 22}

## oracle_ttft

- requests: 208
- mean TTFT (ms): 9.912
- p95 TTFT (ms): 21.1
- mean recompute tokens: 0
- mean transferred KiB: 29387.846
- decisions: {'recompute': 18, 'full_reuse': 190}

## heuristic_transfer_underestimated

- requests: 208
- mean TTFT (ms): 10.782
- p95 TTFT (ms): 22.161
- mean recompute tokens: 18.644
- mean transferred KiB: 28791.231
- decisions: {'recompute': 18, 'full_reuse': 168, 'partial_reuse': 22}

## heuristic_transfer_overestimated

- requests: 208
- mean TTFT (ms): 10.782
- p95 TTFT (ms): 22.161
- mean recompute tokens: 18.644
- mean transferred KiB: 28791.231
- decisions: {'recompute': 18, 'full_reuse': 168, 'partial_reuse': 22}

## heuristic_recompute_underestimated

- requests: 208
- mean TTFT (ms): 10.782
- p95 TTFT (ms): 22.161
- mean recompute tokens: 18.644
- mean transferred KiB: 28791.231
- decisions: {'recompute': 18, 'full_reuse': 168, 'partial_reuse': 22}

## heuristic_recompute_overestimated

- requests: 208
- mean TTFT (ms): 10.782
- p95 TTFT (ms): 22.161
- mean recompute tokens: 18.644
- mean transferred KiB: 28791.231
- decisions: {'recompute': 18, 'full_reuse': 168, 'partial_reuse': 22}

## Per-Case Snapshot

### dynamic_rag_corpus_update

- family: dynamic-rag-corpus-update
- decision role: dynamic_retrieval_followup_surface
- requests: 32
- heuristic p95 TTFT (ms): 27.734
- oracle p95 TTFT (ms): 21.1

### session_continuation_with_maintenance

- family: session-continuation-maintenance
- decision role: long_context_continuation_surface
- requests: 40
- heuristic p95 TTFT (ms): 8.455
- oracle p95 TTFT (ms): 7.702

### shared_prefix_multi_tenant_assistant

- family: shared-prefix-multi-tenant-assistant
- decision role: prefix_rich_multi_tenant_surface
- requests: 40
- heuristic p95 TTFT (ms): 20.265
- oracle p95 TTFT (ms): 20.265

### shared_scenario_multi_turn_knowledge_service

- family: session-affine-multi-turn
- decision role: exact_continuation_baseline
- requests: 32
- heuristic p95 TTFT (ms): 5.656
- oracle p95 TTFT (ms): 5.656

### shared_scenario_rag_followup_long_context

- family: rag-followup
- decision role: retrieval_followup_long_context_boundary
- requests: 32
- heuristic p95 TTFT (ms): 22.161
- oracle p95 TTFT (ms): 22.161

### shared_scenario_structured_agent_decode

- family: tool-scaffold-agent
- decision role: mixed_schema_and_transcript_overlap
- requests: 32
- heuristic p95 TTFT (ms): 5.264
- oracle p95 TTFT (ms): 5.264
