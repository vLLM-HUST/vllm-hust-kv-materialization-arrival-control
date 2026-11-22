# Paper Readiness

## Decision

**GO for paper convergence around a load-dependent positive observation and a
separate fixed-policy boundary.**

The Qwen3.5 series reports a +7.13% five-point geometric-mean throughput change,
with +9.22%, +11.90%, and +15.16% at concurrency 4/8/16. This is a positive
real-online observation, but not yet a matched-repetition causal claim. The
separate Qwen2.5 M2 controller loses to `always_full_reuse`; the two protocols
must not be pooled or used to overwrite each other.

## Contribution That Survives Review

1. Requested, effective, and engine-realized KV actions are distinct measurable
   quantities; reporting only the policy output can overstate partial reuse.
2. A block-aligned segmented-tail carrier exposes the lookup, alignment, commit,
   isolation, and recomputed-tail costs needed for a physical break-even test.
3. The controller-enabled Qwen3.5 runtime shows a negative-to-positive transition
   as concurrency increases, while telemetry proves that reuse and recompute
   paths were exercised.
4. When local full reuse is already cheap, the M2 action selector has no measured
   economic headroom: full reuse wins 6/6 main rounds and 20/20 added rounds.
5. The paper states its reproducibility boundary explicitly: 39 lifecycles have
   retained raw bundles and 102 are aggregate-only supporting evidence.

## Remaining Submission Work

- select a venue and apply its current formatting and anonymity rules;
- run an independently ordered matched replication of the Qwen3.5 C1--C16 series;
- obtain author approval of claims, order, and affiliations;
- build and archive the PDF in a pinned TeX environment.

No M2 controller retuning or additional post-hoc workload search is required.
