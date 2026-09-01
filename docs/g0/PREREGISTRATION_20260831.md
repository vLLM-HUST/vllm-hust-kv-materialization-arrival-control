# Issue #17 G0 preregistration and execution status

## Carrier and exact seam

- Parent repository: `77cd81d911127d0ebe838cacf8747a9e66a82129`.
- Vendored historical vLLM carrier: `68b8be04493d39d5706f3d0d18f465f5eab947c4`.
- Executed upstream vLLM: `/vllm-workspace/vllm` at
  `0fc695fc6d1d82e9a5ac6835ac8e4e1c83703665`.
- G0 vLLM-Ascend worktree: `/root/g0-vllm-ascend`, based on
  `f4a08bddd0cc65a0bd8c3d377b158ae5ca7527db`.
- Profiling carrier: `/root/vllm-hust-profiling`, based on
  `9be6a32b9e64e06c7a60def100452abf127850bb`.

The upstream seam is AscendStore's layerwise receive path:

- `config_data.py`: immutable enqueue clock and observed queue depth on
  `LayerLoadTask`;
- `pool_worker.py`: layer load enqueue and layer-ready wait activation with
  request IDs;
- `kv_transfer.py`: requested/realized bytes, global bytes in flight,
  transfer start/finish, result, and connector queue wait;
- `g0_telemetry.py`: opt-in JSONL sink with monotonic and wall clocks;
- msServiceProfiler `modelExec`: compute-envelope intervals joined to transfer
  intervals by the wall-clock bridge.

The default path contains observation only and does not change release order,
prefetch depth, retrieve/recompute choice, or graph/eager mode. Formal matched
baselines additionally use a default-off static `minimum_retrieve_tokens`
seam in this isolated worktree. It does not implement adaptive control.

## Trace and reuse overlay

- BurstGPT source commit:
  `d895a53bb7b8ec137d0d2fe203b335835a78c10a`; the pinned carrier is the
  densest positive-span 64-row window of `BurstGPT_1.csv`, source rows
  1,152,569 through 1,152,632.
- ServeGen source commit:
  `d70c8b2d5bc45f4b60a146fbc43dc5523f871c8b`; the pinned carrier calls the
  upstream Weibull sampler for language/m-small client 38, window 0, seed
  20260831.
- Only arrival shape comes from those sources. The auditable overlay cycles
  128/256/384 shared prefix tokens, adds 32 deterministic unique suffix
  tokens and requests 8 output tokens. It preserves request order.
- DeepSeek-V2-Lite MLA bf16 TP1 materialization cost is frozen as
  `27 × (512 + 64) × 2 = 31,104` bytes per reused token.
- `scripts/prepare_g0_traces.py` regenerates source carriers and emits their
  selection, size, and SHA-256 manifest. `scripts/g0_pathology.py init`
  generates source-shaped 8/32 req/s moderate/high overlays. The low control
  preserves content and order but uses strict one-request-per-second spacing;
  mean-rate scaling alone is rejected because it preserves simultaneous
  BurstGPT timestamps.
- The corrected low-control overlays are
  `0279fc2807a93a4cdefc2d48e92ddfe3be82d4a2607468159bff5420ab348b78`
  (BurstGPT) and
  `df360dd9e98c601aca46afbd79c8660b96e150637b2dcfea4fe8395bdeec0b2d`
  (ServeGen). Both contain arrivals 0 through 63 seconds with a 1-second
  minimum gap. A preliminary BurstGPT run made with the old mean-scaled
  overlay was interrupted, rejected before analysis, and is absent from raw
  custody.

## Matched protocol and statistics

The formal arms remain no-control/always-materialize, always recompute,
fixed concurrency, ordinary request token bucket, minimum-retrieve threshold,
fixed prefetch depth, and the offline materialization-byte oracle. The model,
request token IDs and order, warm prefix set, external-cache configuration,
eager mode, TP1, and NPU are fixed. Local vLLM prefix caching is disabled so
every reported reuse is activated through AscendStore.

Static baseline values are frozen at 512 tokens for always-recompute, 256
tokens for the LMCache-style minimum-retrieve threshold, and 4 layers for
fixed prefetch depth. Other materializing arms use threshold 0 and depth 1.
Raw `materialization_decision` and `connector_config` events must agree with
the benchmark controls or the run is rejected.

Each formal cell uses three fresh server lifecycles with rotated arm order.
Each run stores all request records. The within-run p50/p95/p99 uses the
nearest-rank empirical percentile; the report uses paired per-repeat deltas
and shows all three repeats as well as their median. The first Issue reply
promised a bootstrap 95% interval but did not freeze its implementation. The
2026-09-01 report-only completion uses a deterministic exact paired-lifecycle
bootstrap: it enumerates all `3^3 = 27` with-replacement resamples and reports
the median's 95% percentile interval. The lifecycle, not each request within a
lifecycle, is the independent sampling unit. This addition changes no run,
point estimate, threshold, arm, or Stop trigger.
Correctness requires
HTTP success, exactly 8 output tokens, a deterministic output hash, 100%
request completion, successful transfer results, realized bytes equal to
requested bytes, and nonzero activation counters.

The current 31,850,496-byte pilot oracle changes goodput too much to be a
formal Go comparison. The capacity frontier is therefore frozen before its
execution at 31,850,496 / 63,700,992 / 127,401,984 / 254,803,968 bytes,
corresponding to 4/8/16/32 times the 256-token request cost. Every point will
be reported; no workload-specific point may be substituted.

## Device, duration, and minimum resource request

- One Ascend 910B2, physical NPU 2; TP1; DeepSeek-V2-Lite bf16; eager mode;
  max model length 512, max sequences 64, max batched tokens 8192.
- One CPU-side MMC meta/config service and 1 GiB local DRAM store.
- Minimum request: exclusive use of one otherwise-idle 910B2 for 4–6 hours,
  plus approximately 10 GiB host scratch. The executable plan contains 96
  rotated base runs and 36 additional frozen-frontier runs (132 total), plus
  restarts, parsing, and fail-closed reruns.

## Raw custody

Raw pilot archives are read-only under
`/root/g0-artifacts/issue17/pilot_20260831`. Each archive includes request
JSONL, connector JSONL, resource samples, profiler DB/CSV/Chrome trace, runtime
configuration, and logs. `pilot_custody_20260831.json` records size, SHA-256,
mode, custodian, and recovery procedure. The corrected low-control suite
manifest and overlays are archived alongside the four valid low-control runs.
`scripts/summarize_g0_pilot.py` rebuilds the committed pilot table from raw
run directories.

The first attempted BurstGPT-moderate b8 frontier startup used an absent MMC
service path and never reached `/health` or workload replay. Its partial
directory is rejected and absent from custody. The valid `frontier-v3` runs
were started only after ports 5000/6000/18080 were verified and use fresh,
non-overwriting directories.

For formal data, create a new outside-worktree directory, never overwrite a
run sequence, archive it as a release asset, and record both archive and
uncompressed manifest SHA-256 before computing a verdict.
`scripts/rebuild_g0_formal.py` reads the real profiler run tree, verifies
cross-arm request output hashes and baseline activation, and rebuilds the
formal JSON/Markdown report plus the intensity × reuse pressure CSV/SVG.

## Distinguishing materialization congestion from ordinary queueing

Materialization evidence is the co-movement of TTFT tail with requested and
realized KV bytes, peak bytes in flight, connector wait, layer-ready wait,
transfer busy and its overlap with `modelExec`, while request order, reuse
tokens, output, and mode stay fixed. HBM peak/bandwidth, AI-core busy,
process-tree PSS, batch profiler spans, TPOT, and decode throughput are the
controls for general memory/compute/decode saturation. Low-concurrency replay
is the control for ordinary queueing.

The single-repeat 2×2 core pilot is not a verdict. All four burst cells show at
least 10% no-control/oracle p95 TTFT regression and increased materialization
pressure. The ordinary token-bucket/oracle p95 gap ranges from 0.94% to
14.38%, so generic equivalence is not stable across cells. The oracle loses
23.79%–62.91% goodput against no-control. In the strict 1 req/s control,
BurstGPT's no-control/oracle p95 regression is 3.08% and ServeGen's is -3.92%,
with less than 0.1% goodput gap and 100% correctness in both arms; neither
control reproduces the >=10% burst difference. The frozen four-point byte
frontier is complete for all four burst cells at repeat 1. No point jointly
achieves >=10% p95 TTFT improvement and <=5% goodput loss; the best p95
improvements among points within the 5% capacity bound are 6.96% (BurstGPT
moderate), -1.21% (BurstGPT high), -0.04% (ServeGen moderate), and -2.92%
(ServeGen high). Therefore neither Go nor Stop is established; remaining
matched baselines and repeat evidence are still required.

The three previously missing baselines passed pre-formal BurstGPT-moderate
smoke activation: always-recompute produced 64 recompute decisions and zero
materialization bytes; threshold 256 produced 42 materialize and 22 recompute
decisions; prefetch depth 4 produced 64 materialize decisions. All three had
100% correctness, and their raw connector configuration matched the recorded
controls. Smoke results select no thresholds and are excluded from the formal
verdict.

## Formal fail-fast outcome

Formal execution stopped after the contiguous canonical prefix 1–63, when
ServeGen/moderate completed all seven arms and all three frozen repeats. Its
no-control/oracle p95 TTFT regressions were 8.47%, 17.84%, and 2.18%; the
median was 8.47%, with only one repeat reaching the preregistered 10% gate.
All three pairs had higher no-control materialization pressure and identical
request output hashes, so the result is not caused by missing activation or
correctness drift. In the same cell, ordinary request token bucket achieved a
7.18% median p95 improvement versus the oracle's 7.81%, with a slightly lower
goodput loss; under the frozen one-percentage-point equivalence tolerance this
is also a generic-baseline Stop trigger.

Sequences 64–96 and the capacity frontier were intentionally not executed.
Continuing after either Stop trigger would violate the issue instruction not
to tune or select workloads after inspection. Two failed HTTP attempts are
preserved separately under the rejected custody tree and are excluded from
the 63 canonical valid runs; their correctness failure and request IDs remain
machine-readable.

The final v2 custody is published at
<https://github.com/intellistream/kv-materialization-arrival-control/releases/tag/g0-issue17-stop-20260901-v2>.
Raw archive asset ID `539131048` has size 16,033,682 bytes and SHA-256
`6474d718f65aeee3824e25897934922672c2a51e92f6c218be6f5b16a7f0ad4a`.
The independently downloadable v2 manifest has SHA-256
`7847e2cbfd12858e09bc0ade41e55dc31219110f33f223e156428ee17781a2a4`.
