# M2 existing-catalog positive-boundary closure

This bundle records the finite existing-catalog closure requested after the
earlier -0.90% multi-tenant result was judged non-significant. It is not a new
controller tuning sweep.

## Online coverage

- 14 previously unconfirmed canonical workloads received a three-policy pilot;
- four permissively promoted workloads received five fresh matched rounds;
- 102/102 independent graph-mode lifecycles validated;
- 6,192/6,192 requests completed;
- all lifecycle IDs are unique;
- requested, effective, and engine-realized actions remain separately recorded.

The ten remaining canonical cases are stored as five disjoint pilot shards in
this directory. The earlier four-case stateful-secondary pilot and all four
confirmation suites are stored in sibling result directories.

## Pilot screen

| Workload | Controller TTFT vs best fixed | Promoted |
|---|---:|---:|
| `shared_code_eval_judge` | -1.21% | yes |
| `shared_structured_json_generation` | +0.91% | yes |
| `shared_multi_turn_support_chat` | +110.73% | no |
| `shared_memory_write_then_reuse` | +3.83% | no |
| `shared_session_affine_multi_turn` | +12.44% | no |
| `shared_session_affine_bursty` | +1.15% | yes |
| `shared_rag_followup` | +39.90% | no |
| `shared_long_context_doc_analysis` | -2.42% | yes |
| `shared_repo_aware_coding_assistant` | +12.69% | no |
| `shared_experiment_planning_assistant` | +4.81% | no |
| `shared_simulation_analysis_verification` | +2.20% | no |
| `shared_realtime_voice_assistant` | +23.31% | no |
| `shared_dynamic_rag_corpus_update` | +24.67% | no |
| `shared_preemption_resume_long_decode` | +19.95% | no |

The promotion threshold was deliberately permissive (TTFT at most +2%, E2E at
most +5%, throughput at least -5%). Pilot results are not positive claims.

## Independent five-round confirmation

| Workload | TTFT mean vs per-round best fixed | One-sided 95% upper | E2E | Throughput | Significant >=5% positive |
|---|---:|---:|---:|---:|---:|
| `shared_code_eval_judge` | +0.87% | +2.13% | +0.23% | -0.19% | no |
| `shared_structured_json_generation` | +0.87% | +2.95% | -0.58% | +0.50% | no |
| `shared_long_context_doc_analysis` | +3.70% | +6.19% | +0.96% | -0.89% | no |
| `shared_session_affine_bursty` | +2.29% | +3.89% | +0.45% | -0.39% | no |

`always_full_reuse` was the best fixed TTFT policy in all 20/20 confirmation
rounds. None of the four controller means was positive, let alone at least 5%,
and every one-sided confidence upper bound was above zero.

## Conclusion and boundary

No meaningful significant positive workload was found among the non-redundant
representatives of the existing 28-ID catalog under the matched
Qwen2.5-7B-Instruct/Ascend configuration. The workload search stops here; the
mechanism direction should not support a positive online-performance claim.

This is a finite catalog result, not a proof that no positive workload can exist
for another model, hardware platform, carrier implementation, or workload
outside the catalog. Eight case IDs were not rerun because they are aliases or
reduced redundant variants; the public generated-prefix boundary covers the
offline-identical synthetic generated-prefix control.

## Rebuild

Rebuild each pilot shard with `aggregate_m2_candidate_pilot.py`, each promoted
suite with `aggregate_m2_significance_confirmation.py`, and the raw mechanism
table with `aggregate_m2_search_mechanisms.py`. The checked-in
`mechanism_breakdown.csv` contains performance, observed/effective/realized
action counts, engine token accounting, lookup/commit/tail costs, and fallback
reasons for all 54 workload/stage/policy groups.
