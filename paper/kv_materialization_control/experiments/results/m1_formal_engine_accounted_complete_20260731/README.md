# M1 matched graph-mode real-online suite

This is the post-fix, independently engine-accounted M1 suite. The earlier
`m1_formal` directory is preserved but explicitly invalidated and must not be
mixed into these statistics.

- Parent at execution start: `18a878e`
- Runtime carrier: `68b8be0`
- Device: NPU 7
- Model: `/root/models/Qwen2.5-7B-Instruct`
- Mode: graph (`enforce_eager=False`, graph capture evidence retained per run)
- Block/hash block size: 128 tokens
- Valid lifecycles: 27/27; no failed requests
- Required four-grid cells: 3 independent service starts per cell
- Dynamic RAG check: 3 independent service starts

Every bundle retains request results and raw SSE events, planner observations,
engine-owned lookup/commit JSONL, token-accounting closure, environment and
commands, validation, and cleanup evidence. `suite_manifest.json` preserves the
balanced execution order.

The generated per-run CSV and TeX now report both the applied policy-action mix
and the realized engine lookup mix. The post-review protocol-identical old/
segmented carrier-validation pair is retained separately under
`../m1_paired_dry_20260801T021223Z_f2ddea6` and is not mixed into these formal
statistics.

Rebuild the committed CSV and TeX artifacts from raw bundles with:

```bash
make m1-online-rebuild
```

## Direction check

Comparing the preregistered `old + baseline` reference with `segmented + tuned`
using medians:

- Knowledge workload: median end-to-end latency changes from 1176.164 ms to
  1165.671 ms (-0.89%), and request throughput from 3.361 to 3.389 req/s
  (+0.83%). The positive signal remains small.
- Tool workload: median end-to-end latency changes from 2173.180 ms to
  2181.972 ms (+0.40%), and request throughput from 1.815 to 1.808 req/s
  (-0.39%). TTFT improves, but the end-to-end/throughput boundary remains
  negative; it is retained and reported.

These results rebuild evidence for M1 only and do not rewrite the paper's
conclusions.
