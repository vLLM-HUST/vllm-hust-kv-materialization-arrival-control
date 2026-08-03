# M2 anchor-topology candidate pilot

This exploratory real-online suite tests whether a shared secondary scaffold
anchor creates a positive controller region that fixed primary-anchor full
reuse cannot reach.

- matrix: 2 workloads x 3 policies x 1 independent pilot lifecycle;
- completion: 6/6 bundles valid, 456/456 requests completed;
- promoted: `shared_shared_prefix_multi_tenant_assistant`;
- not promoted: `shared_session_continuation_maintenance`.

For the promoted workload, controller mean TTFT was 145.910 ms versus 151.443
ms for `always_full_reuse` and 274.357 ms for `always_recompute`: a 3.65%
pilot improvement over the best fixed policy. E2E changed by +0.31% and
throughput by -0.25%. This is screening evidence only and is excluded from the
three-round confirmation estimate.

