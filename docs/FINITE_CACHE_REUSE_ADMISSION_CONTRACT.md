# Finite-Cache Reuse Admission Research Contract

Status: preregister-before-execution reframe contract, 2026-08-28.

This contract replaces continued tuning of the request-local three-action
controller. It does not replace or weaken the M2 and WaveMat negative results.
It authorizes no adaptive treatment until the D0 fixed-policy crossover gate
passes on native runtime receipts.

## 1. What is the research question?

When reuse-bearing sessions overlap under a fixed paged-KV block budget, can
accepting every available full-prefix reuse be locally optimal for the arriving
request but globally harmful because retained blocks evict more valuable state
or delay uncached, deadline-critical requests?

The decision object is now a cross-request reuse-admission or retention action:
`admit`, `bypass-and-recompute`, or `defer`. It is not another threshold sweep
over `full_reuse`, `partial_reuse`, and `recompute` for an isolated request.

The connector branch is conditional. It exists only if a separate receipt
proves nonzero requested and realized transfer bytes, queue wait, completion
identity, and both required endpoints on an exact pinned carrier. Local
prefix-cache reuse must never be relabeled as connector or DMA materialization.

## 2. Why is it important, and what is the architecture causal chain?

The causal chain must be reported in this order:

1. **Architecture fact.** The graph-mode carrier exposes block-aligned local
   prefix reuse. Finite paged-KV blocks are shared across requests, while
   request-local metadata does not instantiate a `KVConnector`.
2. **Invalidated assumption.** The old work assumed request-local selection
   could beat a fixed reuse policy on the service objective.
3. **Real counterexample.** `always_full_reuse` won all six matched M2 rounds;
   controller TTFT regressed 9.24% and 6.60% on the two workloads. WaveMat also
   found no independent graph-only overlap gap on its tested path.
4. **Native mechanism.** Only after D0, use cache-manager block identity and
   occupancy/victim receipts to compare marginal saved prefill work with the
   eviction, residence, and deadline externality imposed on concurrent work.
5. **Predictive boundary.** Burst intensity, finite block occupancy, reuse
   horizon, victim value, and uncached-request slack must predict a fixed-policy
   winner switch before an adaptive action is admitted.
6. **Generalization class.** Paged-KV runtimes with shared finite cache and
   native block identity; platform specificity alone is not a contribution.

## 3. What are the strongest baselines and oracle?

Every arm uses the same model, request order, arrival times, cache budget,
graph mode, seed, runtime commits, sampling, initial cache state, and cache
salt.

| ID | Arm | Role |
|---|---|---|
| B0 | `always_full_reuse` | Mandatory strongest baseline that defeated the old controller. |
| B1 | `always_recompute` / reuse bypass | Opposite fixed action and externality probe. |
| B2 | old three-action controller | Historical ablation only; never retuned. |
| B3 | fixed request/concurrency cap | Tests whether a generic scheduler primitive is sufficient. |
| B4 | fixed KV-block/reuse-byte budget | Tests whether a static resource cap is sufficient. |
| B5 | unmodified native cache policy | Deployable runtime baseline. |
| O | offline future-aware oracle | Upper bound only; never an online treatment or baseline. |

For a connector study, also include a normal request/token bucket and fixed
prefetch-depth or transfer-concurrency baselines. If a generic fixed control
matches the proposed mechanism, the materialization-specific novelty stops.

## 4. What did the negative result close, and what remains unknown?

Closed:

- the current request-local three-action controller and cost model;
- per-workload retuning or post-hoc workload search to beat B0;
- treating requested partial reuse as realized engine work;
- a broad graph-only overlap claim on the audited WaveMat path.

Still unknown, not established:

- whether finite capacity makes full-reuse occupancy evict higher-value state;
- whether roomy and constrained cells have different best fixed arms;
- whether decision-time victim cost, horizon, slack, and residence predict that
  crossover;
- whether any real connector carrier has a materialization-specific burst
  queue.

Simulation, a synthetic reuse overlay, or a renamed local-cache action cannot
establish these unknowns. Synthetic input may appear only as a labeled stress
control, never as the primary effect evidence.

## 5. What is the new hypothesis and mechanism?

**H0, fixed-policy crossover.** B0 remains best under low pressure, but a
different fixed deployable arm wins in preregistered high-overlap,
capacity-constrained cells because retained reuse imposes a measurable
occupancy, victim, or SLO externality. H0 is tested before any treatment exists.

**H1, marginal-externality admission.** Only after H0 passes, a deterministic
policy may estimate:

```text
local saved prefill cost
- expected victim recompute cost
- block-bytes * expected residence shadow price
- deadline/critical-request interference cost
```

Inputs must exist before the decision: exact reusable block bytes, current
free/evictable blocks, independently calibrated reuse horizon, known deadline
or slack, and native cache-manager receipts. Future labels belong only to O.
Calibration uses a disjoint trace and is frozen before held-out evaluation.

## 6. What is the minimum viable real experiment?

### D0: pathology and action-space gate

- Use a licensed, privacy-safe real or publicly citable multi-session trace
  with genuine prefix/session reuse.
- Run low/high overlap by roomy/constrained KV budget, at least three
  independent service starts per fixed arm, counterordered.
- Freeze cells and capacities from source/runtime limits before observing
  results.
- Record TTFT p50/p95/p99, TPOT, E2E, throughput, SLO goodput, prefix-hit and
  recompute tokens, free/used/evicted blocks, victim identity, block residence,
  waiting reason, queue time, and cleanup.

Correctness/provenance oracle:

- 100% request/response identity plus exact output token IDs or a justified
  deterministic digest;
- requested, effective, and engine-realized actions recorded separately;
- consistent block identity, generation, cache salt, owner, reference count,
  and cleanup;
- zero stale, duplicate, partial, ABA, orphan, cross-request reuse, or silent
  fallback events;
- parent/runtime/workload/model/image/config hashes, raw-file hashes, lifecycle,
  allocation, and post-run cleanup receipt for every run.

D0 is Go only if all of the following hold without post-result cell selection:

1. B0 wins at least one low-pressure cell;
2. another fixed deployable arm wins at least two preregistered constrained
   overlap cells across independent starts;
3. B0 has at least 10% worse p95 TTFT or at least 5% lower SLO goodput there;
4. native occupancy/eviction/wait receipts explain the change, rather than
   order drift, generic saturation, output differences, or eager fallback;
5. correctness and cleanup are 100%.

If D0 fails, stop before H1. If D0 passes, M1 compares H1 with the strongest
deployable B0--B5 arm in each frozen held-out cell. M1 requires at least 5% SLO
goodput improvement, no more than 5% aggregate p95 TTFT regression, zero
correctness/cleanup errors, and preservation of B0 behavior at low pressure.

Evidence is labeled without promotion: `real-online`, `replay`,
`host-fixture`, `smoke`, `simulation`, `projected`, or `derived-artifact`.
Only matched `real-online` evidence may support the treatment effect.

## 7. What is the contribution, limit, and stop rule?

If D0 and M1 pass, the contribution is a measured cross-request occupancy
externality and a receipt-backed reuse-admission rule. It is not a revived
partial-reuse controller. The portable claim is that full-prefix reuse remains
locally dominant until retained KV blocks acquire a measurable opportunity
cost.

Stop on any of the following: no fixed-policy crossover; B0 remains dominant;
native receipts cannot identify victim/action realization; B3/B4 matches the
oracle or treatment; only synthetic or post-hoc cells are positive; connector
bytes/queue receipts are absent; M1 misses either performance gate; or any
correctness, ownership, stale-state, or cleanup error occurs. A stop closes
this reframe without spawning another controller variant.

## First two-week delivery

Week 1: audit the cache-manager/action seam and any connector seam separately;
freeze trace license/hash and the D0 manifest; add host/unit tests for action
receipts, block/generation identity, stale/ABA/orphan rejection, and deterministic
replay. Do not implement H1.

Week 2: execute one bounded, counterordered D0 matrix; retain raw JSONL,
manifest, per-run/aggregate tables, hashes, cleanup receipts, and an explicit
Go/Stop verdict. On Stop, close the reframe. On Go, submit a separate M1 design
with frozen state, action, baselines, calibration split, and held-out gates.
