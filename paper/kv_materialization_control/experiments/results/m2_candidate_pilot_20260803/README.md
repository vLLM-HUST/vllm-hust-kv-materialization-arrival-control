# M2 offline-ranked candidate pilot

This directory preserves the first preregistered expansion of the M2 boundary.
It screened the two catalog workloads with the best modeled controller delta.

- matrix: 2 workloads x 3 policies x 1 independent pilot lifecycle;
- completion: 6/6 bundles valid, 464/464 requests completed;
- promotion result: no workload passed the preregistered pilot gate;
- confirmation result: no repeated confirmation matrix was started.

`shared_async_document_pipeline` controller TTFT was 14.72% worse than the
best fixed policy. `shared_public_sharegpt_boundary` was 130.90% worse. In both
cases `always_full_reuse` was the best fixed policy.

The `failed_label_attempt/` directory retains the initial non-performance
failure caused by the validator not yet accepting the new evidence label. It
completed 80/80 requests but was not admitted to the matrix and was rerun from
scratch after the label-only fix.

Rebuild the pilot verdict with:

```bash
make m2-candidate-pilot-rebuild \
  M2_PILOT_SUITE_DIR=paper/kv_materialization_control/experiments/results/m2_candidate_pilot_20260803 \
  M2_PILOT_RESULTS_DIR=/tmp/m2-candidate-pilot-rebuild
```

