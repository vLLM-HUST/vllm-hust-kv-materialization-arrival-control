# M2 anchor-topology candidate pilot

## Separate hypothesis

The offline-ranked pilot closed without a promoted workload. This second pilot
does not append cases to that protocol. It tests a distinct runtime mechanism:
partial reuse may select a shared secondary `scaffold::` anchor while fixed
full reuse remains scoped to a per-session or per-tenant primary anchor.

Before online execution, the catalog was scanned for workloads containing a
`scaffold::` secondary anchor shared across multiple primary anchors. Four case
IDs matched. The two larger canonical cases are fixed as the pilot candidates:

- `shared_session_continuation_maintenance`: 80 requests, 16 primary anchors,
  four shared scaffold anchors;
- `shared_shared_prefix_multi_tenant_assistant`: 72 requests, 18 primary
  anchors, four shared scaffold anchors.

The smaller aliases are excluded as redundant variants. Controller code,
floor, confidence penalty, model, block size, seed, and segmented seam remain
unchanged.

## Gate and confirmation

Each candidate receives one independently restarted lifecycle for controller,
always full reuse, and always recompute. Promotion uses the same permissive
pilot gate as the offline-ranked pilot: TTFT no worse than 2% above the best
fixed policy, E2E no worse than 5%, and throughput no worse than 5%.

A promoted workload must then pass three new matched rounds, excluding pilot
data, under the original meaningful-gain rule: at least 5% mean TTFT improvement
over the per-round best fixed policy without more than 5% E2E or throughput
regression. If neither candidate is promoted, this anchor-topology hypothesis
is recorded as negative and no further catalog cases are added post hoc.

