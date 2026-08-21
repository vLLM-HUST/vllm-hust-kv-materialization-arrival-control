# WaveMat M0 — upstream 0.23 layerwise audit + runtime status

Status: `static_audit` + `graph_mode_smoke_verified` + `layerwise_runtime_blocked`.
This artifact does not enable WaveMat and is not an end-to-end performance
result.

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

## Runtime blocker (as of 2026-08-21 ~06:30 UTC)

The 8x 910B2 devices are occupied by processes in another namespace: `npu-smi`
reports one process per device at ~59-62 GB, and `torch.npu.mem_get_info`
reports ~2.3 GB free per device (NPU0 ~23 MB). This is below the ~4 GB/device
weight footprint of `DeepSeek-V2-Lite`, so the graph-mode AscendStore layerwise
baseline (prefetch 1/2/4) cannot run until a free device is available.

Per the issue, this maps to the stop condition "M0 没有空闲 910B2 graph-mode
环境" unless a free device becomes available.

## Environment notes

- `OMP_NUM_THREADS=1` is required with `tensor_parallel_size=8` (torch
  `Invalid thread pool!` otherwise).
- Keep the CANN `PYTHONPATH` entry so the `acl` module is importable in worker
  processes.
- `HCCL_NPU_SOCKET_PORT_RANGE` may be needed to avoid port 16666 bind conflicts
  between consecutive runs.
