# M2 significance expansion: stateful secondary-anchor surfaces

## Claim rule

The earlier multi-tenant result is not a positive conclusion: its mean TTFT
delta was only -0.90%, below the preregistered 5% meaningful boundary, and its
round direction was inconsistent. This extension requires both effect size and
uncertainty evidence. A confirmed positive workload must satisfy all of:

- controller mean TTFT at least 5% below the per-round better fixed policy;
- the one-sided 95% Student-t upper confidence bound of the five matched
  lifecycle-level TTFT deltas is below zero;
- mean E2E regression no greater than 5%;
- mean throughput regression no greater than 5%.

Pilot observations are excluded from confirmation. Requested partial reuse is
never accepted as realized reuse; every bundle must pass scheduler-owned engine
accounting validation.

## Candidate set fixed before execution

The existing catalog was audited for untested, non-alias workload families with
a high controller partial-reuse fraction and secondary anchors shared across
primary state scopes. The following four cases are fixed before online runs:

| Workload | Offline controller action mix (recompute/full/partial) | Mechanism surface |
|---|---:|---|
| `shared_code_eval_judge` | 1/3/60 | judge/schema anchors shared across submissions |
| `shared_structured_json_generation` | 1/0/63 | schemas shared across independent JSON tasks |
| `shared_multi_turn_support_chat` | 1/2/61 | issue scaffold plus per-session history |
| `shared_memory_write_then_reuse` | 1/11/52 | namespace write followed by delayed reuse |

The controller, block size, floor, confidence penalty, model, seed, concurrency,
and segmented-tail seam are unchanged. Request rates use catalog recommendations;
the output cap is 96 tokens for all four cases.

## Sequential gate and stop rule

Each workload first receives one independently restarted lifecycle for each of
`always_recompute`, `always_full_reuse`, and `controller`. The permissive pilot
gate remains TTFT no worse than 2%, E2E no worse than 5%, and throughput no worse
than 5% relative to the appropriate best fixed policy.

Every promoted workload receives five fresh temporally blocked matched rounds
(15 independent service lifecycles) with balanced policy order. No controller
parameter is changed after observing results. If none passes the confirmation
rule, this hypothesis is negative. Further catalog closure, if needed, must be
registered as a separate exhaustive study rather than appended post hoc.
