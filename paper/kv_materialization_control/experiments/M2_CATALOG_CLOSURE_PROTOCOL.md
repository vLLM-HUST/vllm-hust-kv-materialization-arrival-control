# M2 existing-catalog closure protocol

## Scope and claim boundary

The targeted stateful secondary-anchor expansion promoted two workloads, but
neither produced a positive TTFT mean in independent five-round confirmation.
This final extension closes the remaining non-alias canonical cases in the
existing 28-ID catalog. It does not add a synthetic parameter sweep, change the
controller, or search request rates after observing results.

The conclusion is deliberately finite: if no case confirms, the study may state
that no meaningful significant positive workload was found in the existing
catalog under the matched Qwen2.5-7B/Ascend configuration. It must not claim
that a positive workload is mathematically impossible outside this catalog or
on other hardware/models.

## Fixed remaining cases

The following ten cases were not previously given a three-policy real-online
comparison and are not reduced aliases of an already selected canonical case:

- `shared_session_affine_multi_turn`;
- `shared_session_affine_bursty`;
- `shared_rag_followup`;
- `shared_long_context_doc_analysis`;
- `shared_repo_aware_coding_assistant`;
- `shared_experiment_planning_assistant`;
- `shared_simulation_analysis_verification`;
- `shared_realtime_voice_assistant`;
- `shared_dynamic_rag_corpus_update`;
- `shared_preemption_resume_long_decode`.

Rates and output caps are fixed from the workload catalog. The runtime remains
Qwen2.5-7B-Instruct, graph mode, block size 128, concurrency 4, seed 7, tuned
floor 128, confidence penalty 8 ms, and segmented-tail isolation.

## Gate, confirmation, and stop rule

Each case receives one independently restarted lifecycle under controller,
always full reuse, and always recompute. Promotion requires controller TTFT no
worse than 2% above the best fixed policy, E2E no worse than 5%, and throughput
no worse than 5%.

Any promoted case receives five fresh matched rounds under the significance
rule in `M2_SIGNIFICANCE_EXPANSION_PROTOCOL.md`: mean TTFT improvement at least
5%, one-sided lifecycle-level 95% upper bound below zero, and the E2E/throughput
guardrails. If no case confirms, stop workload search and record the finite
catalog result as negative. No post-hoc case, rate, or controller tuning is
allowed.

The pilot may be executed as five disjoint two-workload shards on NPU devices
3--7 to reduce wall-clock time. A workload and all three of its policies remain
bound to one device/port; shard membership is fixed by round-robin indexing of
the ordered list above. Confirmation remains workload-local and uses fresh
lifecycles.
