# M1 reviewer-approved matched graph-mode suite

This is the canonical M1 performance suite executed after the paired carrier
dry-run was reviewed and formally released. Dry-run and earlier suites are not
included in these statistics.

- Parent: `2d2b1af992439a391195f132d3bbe84475bde9d4`
- Runtime carrier: `68b8be04493d39d5706f3d0d18f465f5eab947c4`
- Workload source: `ceef92d52e0c49f26ba1efc6706edd1f6df5d913`
- Device/model: NPU 7, Qwen2.5-7B-Instruct
- Mode/block size: graph, 128 tokens
- Suite status: completed
- Valid independently restarted service lifecycles: 27/27
- Request completion: 864/864, 0 failed
- Cleanup: 27/27 port and device checks passed

The knowledge and tool workloads contain all four preregistered cells with
three independently restarted service lifecycles per cell. Dynamic RAG has
three independently restarted segmented+tuned tokenizer-faithful checks.
Execution order is retained in
`suite_manifest.json`.

Both per-run and aggregate artifacts distinguish applied policy actions from
realized engine cache outcomes. Rebuild all CSV/TeX outputs from the committed
raw bundles with:

```bash
make m1-online-rebuild
```

The non-randomized temporally blocked 2x2 descriptive analysis, exploratory
intervals, prospective minimum meaningful effects, and stopping rule are documented in
`FACTORIAL_ANALYSIS.md`. Generated factorial artifacts are stored alongside the
existing per-run and median/IQR outputs in `generated/`.

## Direction check

Comparing `old + baseline` with `segmented + tuned` medians:

- Knowledge: TTFT -1.88%, end-to-end latency -1.01%, request throughput
  +1.00%. The positive signal remains small.
- Tool: TTFT +1.20%, end-to-end latency +0.59%, request throughput -0.55%.
  The negative boundary remains and is retained.

This suite supplies M1 evidence only and does not rewrite paper conclusions.
The factorial closure supports the narrower statement that the mechanism is
feasible but the performance benefit is workload-dependent; it does not support
a strong general seam-benefit claim. Dynamic RAG remains a path check without a
matched performance control.
