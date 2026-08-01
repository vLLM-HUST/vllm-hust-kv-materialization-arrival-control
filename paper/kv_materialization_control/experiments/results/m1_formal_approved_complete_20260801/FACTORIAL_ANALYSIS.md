# M1 non-randomized temporally blocked 2x2 descriptive analysis

This analysis uses the already committed M1 matrix. It does not treat the 864
requests as independent replicates and does not add a new NPU run.

## Analysis unit and estimands

For each workload, round 1, 2, and 3 are three matched temporal blocks of
independently restarted service lifecycles. Each block contains the four cells
`old/segmented` x `baseline/tuned`. All runs used the same NPU, block order was
fixed rather than randomized, and the three orderings are not completely
position-balanced. The script computes each contrast inside a block and then
reports the mean paired delta and a two-sided 95% Student-t interval over the
three blocks (df=2):

- seam main effect: mean(segmented cells) - mean(old cells);
- tuning main effect: mean(tuned cells) - mean(baseline cells);
- interaction: segmented relative tuning effect - old-seam relative tuning
  effect, reported in percentage points (pp);
- endpoint contrast: segmented+tuned - old+baseline.

Other relative effects are percentages computed inside each block. Negative
TTFT/E2E and positive throughput changes are favorable. These intervals are
descriptive and exploratory, are unadjusted for multiplicity, and summarize
only the observed temporal blocks. They are not causal or general-significance
intervals: the lifecycles are restarts, not randomized independent replicates.

## Prospective minimum effect and stopping rule

The matrix predates this document, so these thresholds are **not** represented
as preregistered for the completed M1 collection. They are registered here only
for deciding whether to spend more device time under the unchanged protocol:

- minimum meaningful mean TTFT reduction: 5%;
- minimum meaningful mean E2E reduction: 5%;
- minimum meaningful request-throughput increase: 5%;
- do not extend the unchanged protocol when the 95% CI excludes a 5% favorable
  effect for both primary system metrics (mean E2E and request throughput);
- TTFT alone is secondary and does not trigger more runs;
- any new mechanism-amplifying workload or protocol is a new study and must
  register its matrix and stopping rule before collection.

Under this rule the current unchanged protocol stops. For both knowledge and
tool workloads, the endpoint and seam-main 95% intervals exclude a 5% favorable
effect for both mean E2E and request throughput. TTFT remains too uncertain to
support a strong claim, but it does not override the stopping rule.

## Results

All values below are mean paired relative deltas with descriptive two-sided 95%
Student-t intervals. Interaction values are percentage-point differences (pp);
all other rows use percent (%).

| Workload | Effect | Mean TTFT | Mean E2E | Request throughput |
|---|---|---:|---:|---:|
| knowledge | seam main | +2.88% [-2.48, +8.25] | -0.01% [-2.85, +2.84] | -0.03% [-2.90, +2.84] |
| knowledge | tuning main | -4.80% [-8.78, -0.82] | -0.66% [-1.83, +0.50] | +0.69% [-0.40, +1.78] |
| knowledge | interaction | +7.07 pp [-0.05, +14.19] | +0.75 pp [+0.12, +1.38] | -0.69 pp [-1.56, +0.18] |
| knowledge | segmented+tuned vs old+baseline | -2.01% [-10.64, +6.63] | -0.67% [-4.37, +3.04] | +0.66% [-2.96, +4.29] |
| tool | seam main | +1.97% [-3.72, +7.67] | +0.76% [-1.05, +2.56] | -0.74% [-2.56, +1.08] |
| tool | tuning main | -0.91% [-7.75, +5.93] | +0.06% [-0.76, +0.88] | -0.02% [-0.82, +0.78] |
| tool | interaction | -1.31 pp [-6.74, +4.12] | +0.47 pp [-4.86, +5.80] | -0.45 pp [-5.64, +4.75] |
| tool | segmented+tuned vs old+baseline | +1.05% [-9.01, +11.10] | +0.81% [-1.42, +3.04] | -0.76% [-2.97, +1.45] |

The small endpoint median direction previously reported is not a stable main
effect. Knowledge tuning improves TTFT in this sample, but the interaction shows
that it is not evidence of a clean segmented-seam benefit. Tool remains a
negative boundary. The supported conclusion is: the mechanism and evidence
carrier are feasible, while performance benefit is workload-dependent and not
established as a strong general effect by three lifecycle blocks.

`dynamic_rag_corpus_update` has only segmented+tuned lifecycles. It remains a
tokenizer-faithful path check and is excluded from all factorial performance
contrasts.

## Rebuild

From the repository root:

```bash
make m1-online-rebuild
```

This first reruns every bundle validator, recomputes request counts, failures,
and mean/p95 TTFT/E2E from raw `request_results.jsonl`, rejects stale committed
validation, and checks a temporary rebuild byte-for-byte against the committed
generated files. It then regenerates the per-run and median/IQR artifacts plus:

- `generated/factorial_paired_round_deltas.csv`;
- `generated/factorial_effects_ci95.csv`;
- `generated/factorial_effects_ci95.tex`.

Historical throughput remains sourced from `request_summary.json`: these
bundles did not preserve an independent raw suite measurement duration, so the
raw-verification gate explicitly reports throughput as not raw-recomputable.
