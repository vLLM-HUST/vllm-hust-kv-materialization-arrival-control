# Top-Tier Push Plan

Primary thesis: full-prefix reuse is locally dominant until finite retained KV
blocks acquire a measurable cross-request opportunity cost. The old
request-local three-action controller is closed, not awaiting more tuning.

Evidence boundary: M2 is `real-online` negative evidence for the old controller;
WaveMat closes its tested graph-only overlap direction. Neither establishes a
finite-cache eviction pathology or connector queue. Only matched `real-online`
evidence with native action, block, victim, wait, and cleanup receipts may
support the reframe.

Next gate: execute D0 from
`docs/FINITE_CACHE_REUSE_ADMISSION_CONTRACT.md` without an adaptive treatment.
Keep `always_full_reuse`, `always_recompute`, the native cache policy, static
concurrency/capacity controls, the frozen old controller, and an offline oracle.

Performance gate: require a repeatable fixed-policy winner switch in at least
two preregistered constrained/overlap cells, where `always_full_reuse` is at
least 10% worse in p95 TTFT or 5% lower in SLO goodput, with 100% correctness
and cleanup. M1 is allowed only after D0 passes; it then requires at least 5%
SLO-goodput gain, no more than 5% aggregate p95 regression, and zero errors.

Immediate two-week delivery:

1. Week 1: freeze trace license/hash, cache-manager seam audit, D0 manifest,
   baselines, oracle, receipts, statistics, and stop rules; add receipt and
   identity tests. Do not implement the treatment.
2. Week 2: run one bounded counterordered D0 matrix and retain raw data, hashes,
   cleanup receipts, and an explicit Go/Stop verdict.
3. Stop if no crossover exists, generic static controls suffice, native
   causality is unobservable, or correctness/cleanup fails. Do not spawn another
   controller variant.
