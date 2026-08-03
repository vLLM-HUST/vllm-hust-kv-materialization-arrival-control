# M2 anchor-topology confirmation

This suite is the independent three-round confirmation for the workload
promoted by the anchor-topology pilot. Pilot data are excluded.

- workload: `shared_shared_prefix_multi_tenant_assistant`;
- matrix: 3 policies x 3 matched rounds;
- completion: 9/9 independent graph-mode bundles valid, 648/648 requests;
- fixed TTFT winner: `always_full_reuse` in 3/3 rounds.

Relative to the per-round best fixed policy, the controller's mean matched
deltas are:

- TTFT: -0.90% (improvement);
- end-to-end latency: -1.36% (improvement);
- request throughput: +1.35% (improvement).

All three primary metric signs are nominally favorable, but this is not a
positive conclusion under the preregistered 5% TTFT rule. Controller won TTFT
in rounds 1 and 2 but lost in round 3, so the result must not be reported as a
stable or significant gain.

Rebuild with:

```bash
make m2-anchor-confirmation-rebuild \
  M2_ANCHOR_CONFIRMATION_DIR=paper/kv_materialization_control/experiments/results/m2_anchor_confirmation_20260803 \
  M2_ANCHOR_CONFIRMATION_RESULTS_DIR=/tmp/m2-anchor-confirmation-rebuild
```
