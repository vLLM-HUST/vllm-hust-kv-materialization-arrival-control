# WaveMat M0 — upstream 0.23 layerwise audit + runtime status

Status: `static_audit` + `graph_mode_smoke_verified` + `layerwise_runtime_partially_measured`.
This artifact does not enable WaveMat and is not an end-to-end performance
result.

**Active overlap-test target:** `/root/models/DeepSeek-V2-Lite` (16B total,
2.4B active; MLA+MoE). It is already present locally and is the model used by
the official vLLM-Ascend Layerwise KV Pool example. This makes it the smallest
available DeepSeek model that exercises the relevant MLA layerwise path. Do not
substitute a smaller DeepSeek R1-distill checkpoint: those are Qwen/Llama dense
models and would not validate this MLA-specific seam.

## Environment (verified working)

- vLLM: `vllm-project/vllm` `0.23.0` (editable `/vllm-workspace/vllm`)
- vllm-ascend: `vllm-project/vllm-ascend` `0.23.0rc1`
  (editable `/vllm-workspace/vllm-ascend`, commit
  `f4a08bddd0cc65a0bd8c3d377b158ae5ca7527db`)
- model: `deepseek-ai/DeepSeek-V2-Lite`
  (`/root/models/DeepSeek-V2-Lite`, `deepseek_v2` MLA, 27 layers, 16 heads,
  `kv_lora_rank=512`, bf16)
- 8x Ascend 910B2, CANN 9.0.1, torch_npu 2.10.0.post2

## Graph-mode smoke (verified)

`DeepSeek-V2-Lite` with `enforce_eager=False` and
`cudagraph_mode=FULL_AND_PIECEWISE` captures both graphs on 8x 910B2:

```text
Capturing CUDA graphs (mixed prefill-decode, PIECEWISE): 100%| 2/2
Capturing CUDA graphs (decode, FULL): 100%| 2/2
Graph capturing finished in 5 secs, took 0.33 GiB
```

The earlier `{32, 64, 128}`-heads graph-mode concern does not reproduce: 16
attention heads capture fine.

## Upstream layerwise KV call chain (static)

References are relative to the installed upstream pair, not the vendored
`vendor/vllm` tree.

| Stage | File:line | Symbol | M0 relevance |
|---|---|---|---|
| graph-mode override | `vllm/config/vllm.py:1258-1266` | `VllmConfig` | layerwise connector forces `cudagraph_mode` to PIECEWISE |
| connector piecewise gate | `.../ascend_store/ascend_store_connector.py:75-80` | `AscendStoreConnector.requires_piecewise_for_cudagraph` | returns `use_layerwise` |
| connector layerwise flags | `ascend_store_connector.py:86-89` | `use_layerwise`, `use_gva_layerwise` | GVA layerwise only for `backend=memcache` |
| connector load/save | `ascend_store_connector.py:219,224` | `wait_for_layer_load`, `save_kv_layer` | delegates to `KVPoolWorker` |
| per-layer host events | `ascend_store/pool_worker.py:315-316` | `layer_load_finished_events`, `layer_save_finished_events` | one `threading.Event` per layer |
| per-layer device events | `pool_worker.py:320` | `sync_save_events` | one `torch.npu.Event` per layer |
| prefetch distance | `pool_worker.py:319` | `num_prefetch_layers` | from `layerwise_prefetch_layers` |
| prefetch window | `pool_worker.py:1309` | `submit_count = num_prefetch_layers if current_layer == 0 else 1` | layer-0 submits prefetch window, later layers submit 1 |
| load wait | `pool_worker.py:1317-1331` | `KVPoolWorker.wait_for_layer_load` | blocks on `layer_load_finished_events[current_layer]` |
| save event | `pool_worker.py:1339-1355` | `KVPoolWorker.save_kv_layer` | records `sync_save_events[current_layer]` |

## M0 gap candidates (code-level)

1. **FULL is not available for layerwise.** `requires_piecewise_for_cudagraph`
   returns `use_layerwise`, so any FULL mode is overridden to PIECEWISE. The
   issue's "FULL vs FULL_AND_PIECEWISE" comparison therefore collapses to
   PIECEWISE for the layerwise baseline.
2. **Host-side per-layer wait.** `wait_for_layer_load` blocks on a Python
   `threading.Event` at each layer boundary, which is a graph-piece transition
   point in PIECEWISE mode. This host/device synchronization is the primary
   candidate for a graph-induced sync bubble.
3. **Static prefetch window.** `layerwise_prefetch_layers` fixes the transfer
   lookahead; bubbles form when transfer and compute rates diverge.

These are static-audit candidates, not measured overlap loss. Runtime proof is
still required for go/no-go.

## Runtime baseline (resolved and run)

The 8x 910B2 devices became free. The graph-mode AscendStore layerwise baseline
was then run with `use_layerwise=True` + `backend=memcache` +
`cudagraph_mode=FULL_AND_PIECEWISE`, `enforce_eager=False`, `tensor_parallel_size=8`,
`max_model_len=256`, one request, 32 output tokens:

| layerwise_prefetch_layers | generate_elapsed_s | generated_text (prefix) |
|---|---|---|
| 1 | 2.506 | `\n\n\nA: You can use the following code to get the current date...` |
| 2 | 2.511 | `\n\n\nA: You can use the following code to get the value...` |
| 4 | 2.529 | `\n\n\nA: You can use the following code to get the current date...` |

Raw results: `docs/wavemat/results/m0_layerwise_baseline_p{1,2,4}.json`.

Observations:

- Runtime confirms the static-audit finding: with `use_layerwise=True`, only
  PIECEWISE graphs are captured (`mixed prefill-decode, PIECEWISE`); no FULL
  decode graph is captured. The FULL mode is overridden to PIECEWISE.
- At this scale (one short request, 32 tokens), prefetch 1/2/4 produces
  essentially identical generation time (2.506 / 2.511 / 2.529 s), so no
  prefetch-induced bubble is yet measurable. This is a first-order signal, not
  a gap/no-gap conclusion; longer sequences and concurrent requests are needed
  to stress the transfer/compute overlap.
- Per-stage timing (transfer / layer-ready wait / attention compute /
  graph-piece transition) and TTFT p50/p95 are not yet instrumented; the next
  step is to enable KV events / iteration-stats tracing and a longer workload.

## Concurrent timing sweep (8 prompts x 64 tokens, max_num_seqs=4)

Measured wall-clock for 8 concurrent identical prompts (64 output tokens) with
`gpu_memory_utilization=0.22`:

| config | use_layerwise | prefetch | wall_clock_s |
|---|---|---|---|
| non-layerwise | False | 1 | 2.999 |
| layerwise | True | 1 | 8.649 / 8.658 |
| layerwise | True | 2 | 8.245 |
| layerwise | True | 4 | 8.192 / 8.118 |

Raw results: `docs/wavemat/results/m0_timing_*.json`.

Findings (first-order, reproducible at endpoints):

1. **Layerwise overhead**: the layerwise path is ~2.7-2.9x slower than
   non-layerwise (8.1-8.7 s vs 3.0 s). This is confounded: layerwise forces
   PIECEWISE (non-layerwise uses FULL+PIECEWISE) and does per-layer rather than
   whole-request transfer, so it is not yet attributable to graph-mode alone.
2. **Fixed-prefetch bubble is reproducible**: prefetch 1 -> 4 improves
   wall-clock by ~5.8% (8.65 s -> 8.16 s), monotonic through prefetch 2
   (8.245 s), with endpoint repeats agreeing within ~1%. This maps to the
   issue's gap candidate "固定 layerwise_prefetch_layers 形成 bubble" and to
   the code seam `pool_worker.py:1309`
   (`submit_count = num_prefetch_layers if current_layer == 0 else 1`).

Caveats: single/config (two repeats only at prefetch 1 and 4), short workload,
no per-stage transfer/wait/compute separation, and the layerwise-vs-non-layerwise
comparison is confounded. The next measurement should add an eager-mode layerwise
reference to isolate the graph-induced portion, and per-stage timing.

## Graph-induced gap: eager vs graph reference

Same workload (8 prompts x 64 tokens, max_num_seqs=4, prefetch 1 and 4), with
`enforce_eager=True`:

| config | mode | wall_clock_s |
|---|---|---|
| layerwise prefetch 1 | eager | 16.828 |
| layerwise prefetch 4 | eager | 16.645 |
| layerwise prefetch 1 | graph (PIECEWISE) | 8.649 / 8.658 |
| layerwise prefetch 4 | graph (PIECEWISE) | 8.192 / 8.118 |

Raw results: `docs/wavemat/results/m0_timing_eager_p{1,4}.json`.

Conclusion for the graph-induced question: **no graph-induced overlap loss or
sync bubble is observed.** Graph mode (PIECEWISE) is ~2x faster than eager
(8.65 s vs 16.83 s at prefetch 1); the graph-piece boundary does not add
measurable host-wait. The reproducible prefetch 1->4 bubble (~5.8%) persists in
both eager (16.83->16.65 s) and graph (8.65->8.16 s) modes, so it is an
eager-agnostic fixed-prefetch scheduling bubble, not a graph-safety seam.

This is a candidate M0 no-graph-gap result, pending (a) runtime replay
correctness failure-injection (stale/ABA/duplicate/load-failure) and (b)
per-stage transfer/wait/compute timing on a longer workload.

## Correctness oracle (greedy output, 6 distinct prompts)

Six distinct prompts, `max_tokens=96`, `temperature=0`. Wall-clock and
exact-output comparison across three configs:

| config | wall_clock_s | greedy matches eager (of 6) |
|---|---|---|
| eager | 27.941 | 6/6 (reference) |
| non-layerwise graph (FULL+PIECEWISE) | 3.556 | 3/6 |
| layerwise graph prefetch 1 (PIECEWISE) | 11.696 | 3/6 |

Raw results: `docs/wavemat/results/m0_correctness_{eager,nonlayerwise,layerwise}.json`.

Observations:

- Graph mode (both non-layerwise and layerwise) diverges from eager on 3/6
  prompts. This is the dominant effect and is consistent with floating-point /
  MoE non-determinism between graph and eager kernel execution, not KV
  corruption.
- Layerwise graph diverges from non-layerwise graph on 2/6 prompts. This is a
  separate, smaller signal that the per-layer save/load or eager-break path
  changes numerics slightly. It warrants a block/layer digest-level check (the
  issue's `block/layer digest` oracle) rather than a token-level conclusion.
- On the 3 divergent prompts the outputs differ by a few tokens (lengths differ
  by ~1), not by gross corruption.

Open correctness items: (a) replay determinism of the same layerwise config
across two runs, and (b) a block/layer digest comparison between layerwise
load and recompute, both of which need digest instrumentation.

## Replay determinism (resolves the correctness question)

Same config run twice (6 distinct prompts, max_tokens=96, temperature=0):

| config | run1 wall_s | run2 wall_s | exact greedy match across runs |
|---|---|---|---|
| non-layerwise graph | 3.556 | 3.473 | 3/6 |
| layerwise graph prefetch 1 | 11.696 | 11.618 | 2/6 |

Result: **both the layerwise and non-layerwise graph paths are non-deterministic
across replays** (3/6 and 2/6 exact match). The greedy-output non-determinism is
therefore NOT layerwise-specific; it is a property of the DeepSeek-V2-Lite MoE
model + graph execution (kernel fusion / MoE routing numerics). The layerwise KV
materialization introduces no additional correctness gap beyond the baseline.

Implication for the correctness oracle: for this MoE model, "greedy token
sequence identical" cannot be satisfied even by the non-layerwise baseline, so
the oracle should be a block/layer digest comparison (load vs recompute), not a
token-level equality.

## Provisional M0 reading (not a no-gap conclusion)

- Graph-induced overlap loss / sync bubble: **not established either way**.
  Graph is 2-8x faster than eager at end-to-end wall-clock, but this does not
  measure whether the per-layer ready event falls on a graph-piece critical
  path.
- Layerwise-specific replay/correctness gap: **not observed** (layerwise is no
  more non-deterministic than the non-layerwise baseline).
- Only reproducible signal is the fixed-prefetch bubble (~5.8%), which is
  eager-agnostic and matches the issue's "固定 prefetch" exclusion.

The prior no-graph-gap/Stop wording was too strong.  The required remaining M0
experiment is a shared-prefix *load* workload (not only a save or no-hit run),
with 1/2/4 static prefetch, paired eager and PIECEWISE runs, and per-layer
records at the actual `KVPoolWorker.wait_for_layer_load` seam.  Summarize those
records with `scripts/summarize_wavemat_m0_overlap.py`.  It fail-closes:
missing records or wall-clock-only results cannot be used to claim that
upstream sufficiently overlaps transfer and compute.  A device-event timeline
for transfer submit/ready and attention start/end is still required to report
an overlap ratio.

### Reproducible layer-ready wait run

Run the following paired sweep only when all eight devices are idle; do not
evict another user's NPU job.  The disposable upstream Ascend checkout must
emit `WAVEMAT_TIMING layer=<id> load_wait_s=<seconds>` immediately around the
existing `layer_load_finished_events[current_layer].wait()` in
`KVPoolWorker.wait_for_layer_load`.  This is observability only, not a WaveMat
mechanism change.

```bash
export MMC_LOCAL_CONFIG_PATH="$PWD/docs/wavemat/configs/mmc-local.conf"
export OMP_NUM_THREADS=1
for mode in graph eager; do
  for prefetch in 1 2 4; do
    args=(--model /root/models/DeepSeek-V2-Lite \
      --prefetch-layers "$prefetch" --max-tokens 64)
    if [ "$mode" = eager ]; then args+=(--enforce-eager); fi
    python3 scripts/run_wavemat_m0_overlap.py "${args[@]}" \
      --output "docs/wavemat/results/m0_overlap_${mode}_p${prefetch}.json" \
      2>&1 | tee "docs/wavemat/results/m0_overlap_${mode}_p${prefetch}.log"
  done
done
python3 scripts/summarize_wavemat_m0_overlap.py \
  --graph-log docs/wavemat/results/m0_overlap_graph_p1.log \
  --eager-log docs/wavemat/results/m0_overlap_eager_p1.log \
  --output docs/wavemat/results/m0_overlap_wait_p1_summary.json
```

The current workload first saves a long shared prefix, then requests suffixes
under that prefix, so the second generation is a cache-load path. vLLM's own
prefix cache is disabled in the driver: otherwise it bypasses AscendStore with
`need_to_load=0`, and no layerwise materialization takes place. Record both
requested and effective graph mode: current upstream forces layerwise
connectors to PIECEWISE, so requested `FULL` / `FULL_AND_PIECEWISE` is not a
valid independent full-graph baseline. Repeat the paired sweep at least twice;
do not declare Stop until the device-event timeline also supplies transfer
submit/ready and attention start/end to calculate overlap ratio.

### TP=1 real-load trace (2026-08-24)

This run used NPU 2, DeepSeek-V2-Lite, `backend=memcache`,
`use_layerwise=true`, and vLLM prefix caching disabled.  The latter is
important: every measured consumer had `vllm_cached=0`, `kvpool_cached=128`,
and `need_to_allocate=128`, so it was an actual AscendStore load rather than an
in-engine prefix-cache hit.

| mode | prefetch | wall-clock s | layer-ready wait samples | mean wait ms |
|---|---:|---:|---:|---:|
| PIECEWISE graph | 1 | 9.376 | 54 | 0.515 |
| eager | 1 | 8.173 | 54 | 0.510 |
| PIECEWISE graph | 2 | 9.540 | 2 | n/a (prefetched layers did not block at the consumer) |
| PIECEWISE graph | 4 | 9.069 | 2 | n/a (prefetched layers did not block at the consumer) |

Raw JSON: `results/m0_overlap_tp1_{graph_p1,graph_p2,graph_p4,eager_p1}.json`;
the paired wait summary is `results/m0_overlap_tp1_wait_p1_summary.json`.

Interpretation: the graph-minus-eager mean ready-wait delta is **+0.005ms**,
which is below this host-clock trace's useful resolution and does not support a
graph-induced host synchronization bubble.  This is a real-load result, but is
only TP=1 and one paired run. It does **not** establish a transfer/compute
overlap ratio or a final M0 Stop conclusion: that still requires device-event
timestamps for transfer submit/ready and attention start/end.

### What counts as “sufficient overlap”

The next trace must emit one correlated record per `(request epoch,
transfer_layer, gate_attention_layer)`.  A prefetch task for layer `L` carries
the attention-start gate of the earlier layer whose compute it is intended to
overlap; record that gate layer explicitly rather than inferring it from log
order.

| Timestamp | Real upstream seam | Meaning |
|---|---|---|
| `transfer_submit_ns` | immediately before `KVCacheStoreLayerRecvingThread._batch_copy_with_limits` | copy is submitted after its attention-start gate opens |
| `transfer_ready_ns` | immediately before `layer_load_finished_events[layer].set()` | data is declared safe for the consumer |
| `attention_start_ns` | the existing `record_attention_compute_start()` event | compute stream reaches the attention op |
| `attention_end_ns` | an NPU event recorded immediately after the attention op | attention work has completed on the compute stream |

Use NPU events to establish stream ordering and a trace worker to serialize
them to host timestamps; do not call `synchronize()` on the model thread.
For each correlated pair calculate:

```text
overlap_ns = max(0, min(transfer_ready_ns, attention_end_ns)
                    - max(transfer_submit_ns, attention_start_ns))
transfer_overlap_ratio = overlap_ns / (transfer_ready_ns - transfer_submit_ns)
exposed_bubble_ns = max(0, transfer_ready_ns - attention_end_ns)
```

The final M0 Stop condition is met only if, in matched TP=1 graph/eager runs
at prefetch 1/2/4, (1) at least 95% of eligible prefetched loads have complete
correlated records, (2) graph has no material increase in `exposed_bubble_ns`
or decrease in `transfer_overlap_ratio` relative to eager, and (3) no
layerwise-specific correctness failure appears. Missing events are a trace
failure, not zero-overlap evidence. The existing p2/p4 observation (only two
consumer waits) is a lead to validate with this timeline, not this condition.

### Single-NPU trace when the TP=8 group is occupied

V2-Lite supports TP=1. A one-NPU trace on an otherwise idle device is valid
for the M0 graph-safety and layer-ready-wait questions, but must be labelled
TP=1 and must not be compared directly with TP=8 latency or throughput.

MMC's local meta service is process-global: start the TP=1 service before any
TP=8 MMC service, or stop only a service known to be dedicated to this
experiment. A TP=1 client cannot safely reuse an occupied TP=8 local-service
configuration. Do not restart a shared service merely to run this trace.

```bash
export ASCEND_RT_VISIBLE_DEVICES=2
export MMC_LOCAL_CONFIG_PATH="$PWD/docs/wavemat/configs/mmc-local-tp1.conf"
export OMP_NUM_THREADS=1
setsid python3 scripts/start_mmc_meta_service.py > /tmp/wavemat-mmc-tp1.log 2>&1 &
python3 scripts/run_wavemat_m0_overlap.py \
  --tensor-parallel-size 1 --prefetch-layers 1 --max-tokens 64 \
  --output docs/wavemat/results/m0_overlap_tp1_graph_p1.json
```

## AscendStore memcache backend prerequisites

- A standalone MMC meta service must be listening on `127.0.0.1:5000` (meta),
  `127.0.0.1:6000` (config store), `127.0.0.1:8000` (HTTP):
  `setsid python3 scripts/start_mmc_meta_service.py`.
- `MMC_LOCAL_CONFIG_PATH` must point at
  `docs/wavemat/configs/mmc-local.conf`.

## Environment notes

- `OMP_NUM_THREADS=1` is required with `tensor_parallel_size=8` (torch
  `Invalid thread pool!` otherwise).
- Keep the CANN `PYTHONPATH` entry so the `acl` module is importable in worker
  processes.
- `HCCL_NPU_SOCKET_PORT_RANGE` may be needed to avoid port 16666 bind conflicts
  between consecutive runs.
