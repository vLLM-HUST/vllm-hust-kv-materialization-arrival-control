# M1 Matched Graph-Mode Online Suite

This directory contains 27 independently started real-online service
lifecycles. No README/TeX-only historical number is included in aggregation.

- model: `/root/models/Qwen2.5-7B-Instruct`
- device: Ascend 910B2 NPU 7, checked idle before every lifecycle
- graph configuration: `enforce_eager=False`, Ascend `FULL_AND_PIECEWISE`
  cudagraph capture
- effective block size: 128
- segmented carrier: `f8efeebe900e638f178e3b460f50cc750054fa17`
- old carrier: `e4ce33646f2ef1781289e6dc651fad0d00177c55`
- seed: 7; temperature: 0.0; concurrency: 4
- workload source: `llm-serving-workloads`
  `ceef92d52e0c49f26ba1efc6706edd1f6df5d913`

`shared_tool_scaffold_agent` is the issue/paper-facing compatibility name for
the pinned shared-catalog case `shared_scenario_structured_agent_decode`; each
bundle records the requested name and workload source commit.

Rebuild all generated CSV and TeX artifacts from the raw bundles:

```bash
make m1-online-rebuild
```

The tool workload remains a negative end-to-end boundary. Its
segmented-tuned median latency is 2162.147 ms versus 2158.511 ms for old
baseline, and median request throughput is 1.824 rps versus 1.827 rps. Its
median TTFT is slightly lower, so the result is metric-dependent rather than a
universal regression; it does not support a positive end-to-end claim.

The knowledge-service positive signal is small: segmented-tuned median latency
is 1159.468 ms versus 1165.272 ms for old baseline, with 3.407 versus 3.393
rps. The committed median/IQR table, rather than the discarded historical
single-run summary, is the auditable result.
