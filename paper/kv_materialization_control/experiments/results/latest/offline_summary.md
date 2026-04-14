# Offline Study Summary

- trace count: 800
- trace source: llm-serving-workloads
- workload cases: shared_session_affine_multi_turn, shared_session_affine_bursty, shared_rag_followup, shared_long_context_doc_analysis, shared_tool_scaffold_agent, shared_repo_aware_coding_assistant, shared_experiment_planning_assistant, shared_simulation_analysis_verification, shared_async_document_pipeline, shared_realtime_voice_assistant, shared_synthetic_shared_prefix_microbenchmark, shared_scenario_multi_turn_knowledge_service, shared_scenario_rag_followup_long_context, shared_scenario_structured_agent_decode, shared_public_sharegpt_boundary

## Overall Policies

## always_recompute

- requests: 800
- mean TTFT (ms): 18.982
- p95 TTFT (ms): 61.033
- mean recompute tokens: 893.827
- mean transferred KiB: 0.0
- decisions: {'recompute': 800}

## always_full_reuse

- requests: 800
- mean TTFT (ms): 10.532
- p95 TTFT (ms): 32.45
- mean recompute tokens: 0
- mean transferred KiB: 28602.48
- decisions: {'recompute': 50, 'full_reuse': 750}

## threshold_partial

- requests: 800
- mean TTFT (ms): 15.871
- p95 TTFT (ms): 37.431
- mean recompute tokens: 488.98
- mean transferred KiB: 12955.12
- decisions: {'recompute': 272, 'partial_reuse': 528}

## heuristic

- requests: 800
- mean TTFT (ms): 11.525
- p95 TTFT (ms): 34.532
- mean recompute tokens: 20.723
- mean transferred KiB: 27939.36
- decisions: {'recompute': 50, 'full_reuse': 635, 'partial_reuse': 115}

## oracle_ttft

- requests: 800
- mean TTFT (ms): 10.532
- p95 TTFT (ms): 32.45
- mean recompute tokens: 0
- mean transferred KiB: 28602.48
- decisions: {'recompute': 50, 'full_reuse': 750}

## heuristic_transfer_underestimated

- requests: 800
- mean TTFT (ms): 11.525
- p95 TTFT (ms): 34.532
- mean recompute tokens: 20.723
- mean transferred KiB: 27939.36
- decisions: {'recompute': 50, 'full_reuse': 635, 'partial_reuse': 115}

## heuristic_transfer_overestimated

- requests: 800
- mean TTFT (ms): 11.538
- p95 TTFT (ms): 34.532
- mean recompute tokens: 20.927
- mean transferred KiB: 27932.8
- decisions: {'recompute': 52, 'full_reuse': 633, 'partial_reuse': 115}

## heuristic_recompute_underestimated

- requests: 800
- mean TTFT (ms): 11.886
- p95 TTFT (ms): 34.532
- mean recompute tokens: 62.315
- mean transferred KiB: 26608.4
- decisions: {'recompute': 52, 'full_reuse': 599, 'partial_reuse': 149}

## heuristic_recompute_overestimated

- requests: 800
- mean TTFT (ms): 11.525
- p95 TTFT (ms): 34.532
- mean recompute tokens: 20.723
- mean transferred KiB: 27939.36
- decisions: {'recompute': 50, 'full_reuse': 635, 'partial_reuse': 115}

## Per-Case Snapshot

### shared_async_document_pipeline

- family: async-document-pipeline
- requests: 80
- heuristic p95 TTFT (ms): 8.936
- oracle p95 TTFT (ms): 8.936

### shared_experiment_planning_assistant

- family: experiment-planning-assistant
- requests: 64
- heuristic p95 TTFT (ms): 14.964
- oracle p95 TTFT (ms): 14.964

### shared_long_context_doc_analysis

- family: long-context-doc-analysis
- requests: 48
- heuristic p95 TTFT (ms): 59.478
- oracle p95 TTFT (ms): 59.478

### shared_public_sharegpt_boundary

- family: sharegpt-public-boundary
- requests: 32
- heuristic p95 TTFT (ms): 5.966
- oracle p95 TTFT (ms): 5.966

### shared_rag_followup

- family: rag-followup
- requests: 64
- heuristic p95 TTFT (ms): 32.45
- oracle p95 TTFT (ms): 32.45

### shared_realtime_voice_assistant

- family: realtime-voice-assistant
- requests: 64
- heuristic p95 TTFT (ms): 10.147
- oracle p95 TTFT (ms): 10.147

### shared_repo_aware_coding_assistant

- family: repo-aware-coding-assistant
- requests: 64
- heuristic p95 TTFT (ms): 15.512
- oracle p95 TTFT (ms): 15.512

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

### shared_session_affine_bursty

- family: session-affine-bursty
- requests: 64
- heuristic p95 TTFT (ms): 10.621
- oracle p95 TTFT (ms): 10.621

### shared_session_affine_multi_turn

- family: session-affine-multi-turn
- requests: 64
- heuristic p95 TTFT (ms): 7.655
- oracle p95 TTFT (ms): 7.655

### shared_simulation_analysis_verification

- family: simulation-analysis-verification
- requests: 64
- heuristic p95 TTFT (ms): 10.384
- oracle p95 TTFT (ms): 10.384

### shared_synthetic_shared_prefix_microbenchmark

- family: synthetic-shared-prefix
- requests: 32
- heuristic p95 TTFT (ms): 5.966
- oracle p95 TTFT (ms): 5.966

### shared_tool_scaffold_agent

- family: tool-scaffold-agent
- requests: 64
- heuristic p95 TTFT (ms): 11.632
- oracle p95 TTFT (ms): 11.632
