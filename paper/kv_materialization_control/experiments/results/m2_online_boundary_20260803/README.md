# M2 Online Benefit Boundary

This directory contains the completed preregistered M2 real-online suite.

- parent commit: `2e99ce1`
- runtime carrier commit: `475ea49`
- model: Qwen2.5-7B-Instruct
- runtime: graph mode, block size 128, segmented-tail seam
- matrix: 2 workloads × 3 policies × 3 independent lifecycle rounds
- completion: 18/18 bundles valid; 576/576 requests successful

The controller did not beat the best fixed policy. Against per-round best fixed
TTFT, it regressed by 9.24% on `shared_tool_scaffold_agent` and 6.60% on
`shared_scenario_multi_turn_knowledge_service`; `always_full_reuse` won all six
matched rounds. The cost model selected the same winner in all six rounds.
According to the preregistered stopping rule, the mechanism-direction verdict
is `stop_mechanism_direction`.

Rebuild all paper-facing artifacts with:

```bash
make m2-online-rebuild
```

The generated paper table has separate cost/performance and action/fallback
panels. Together they expose boundary alignment, lookup, commit, tail isolation,
matched TTFT/E2E/throughput deltas, peak cache usage, observed/effective/realized
action mixes, realignment, and both fallback directions.

The raw `runtime_observations.jsonl` records requested/effective actions; the
scheduler-owned `runtime_events.jsonl` and each `validation.json` establish
realized reuse, recomputed work, lookup/commit/tail-isolation costs, cache
usage, graph-mode evidence, and clean independent lifecycle boundaries.
