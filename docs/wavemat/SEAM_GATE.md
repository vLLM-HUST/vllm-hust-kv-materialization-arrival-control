# WaveMat M0 seam gate

Status: `M0 device sweep complete — no graph-only Go signal`. The active
experiment target is the locally present DeepSeek-V2-Lite, the supported small
MLA+MoE Layerwise KV Pool baseline. The TP=1 graph/eager sweep at static
prefetch 1/2/4 measured very low device-compute overlap (0–4.62%) in both
modes, with no repeatable graph-specific regression. This is a generic
upstream-baseline finding, not authorization for WaveMat M1. See
`M0_UPSTREAM_AUDIT.md`; this artifact does not enable WaveMat and is not an
end-to-end performance result.

## Scope

This file is the first reviewable artifact for the #12 M3 seam gate. It fixes
the carrier pointer at the current parent `vendor/vllm` gitlink, upgrades the
call-chain audit from provisional to static-verified, and adds a host-side
fail-closed generation/digest fixture. It does not implement the WaveMat
generation-tagged readiness runtime path.

## Carrier checkpoint

- parent commit: `375d3a8a10610e13d3ca1f46d0046f0a7282373e`
- `vendor/vllm` gitlink at parent HEAD:
  `68b8be04493d39d5706f3d0d18f465f5eab947c4`
- previously inconsistent docs:
  - `README.md`: `f8efeebe900e638f178e3b460f50cc750054fa17`
  - `HANDOFF.md` / M2 historical record: `475ea49`

The parent gitlink is now initialized and checked out at
`68b8be04493d39d5706f3d0d18f465f5eab947c4`. The M2 historical carrier
`475ea49` is preserved as historical evidence and is not rewritten.

## M2 historical carrier/plugin recheck

M2 result manifests (`m2_online_boundary_20260803` and
`m2_anchor_confirmation_20260803`) record:

- carrier: `vendor/vllm` commit
  `475ea49295b8c19907d2bd3c0af94beb9c99c441`
- model: `/root/models/Qwen2.5-7B-Instruct` (`Qwen2ForCausalLM`,
  `model_type=qwen2`, 28 hidden layers, 4 KV heads)
- paired plugin: `vllm-ascend-hust 0.19.1.post1.dev414+g03a12f9b`
- graph mode: `FULL_AND_PIECEWISE`, `enforce_eager=False`

The historical `vllm-hust` commit is a separate core checkout, while the
per-layer Ascend attention hook lives in the paired `vllm-ascend-hust` plugin.
Recheck of `vLLM-HUST/vllm-ascend-hust` at `03a12f9b` shows the layerwise
call sites only in `mla_v1.py` and `sfa_v1.py`:

- `wait_for_kv_layer_from_connector` / `maybe_save_kv_layer_to_connector`
  are imported and called in `mla_v1.py` and `sfa_v1.py`.
- `attention_v1.py` has only `is_kv_producer` / `kv_transfer_config` branches;
  it contains no `wait_for_kv_layer_from_connector`,
  `maybe_save_kv_layer_to_connector`, `wait_for_layer_load`, or
  `save_kv_layer`.

`Qwen2.5-7B-Instruct` is `qwen2` GQA, not an MLA/SFA/DSA model, so it follows
the generic `ASCEND` / `attention_v1.py` attention path. Therefore the M2 model
path did not have an Ascend per-layer load/save consume seam.

This is a first-fact negative, not M0 go/no-go by itself: if M0 stays on M2's
`Qwen2.5-7B-Instruct` and its paired plugin, the upstream layerwise KV baseline
is not active in `attention_v1`; the seam-gate result must be evaluated on that
observed absence rather than assuming the layerwise path was exercised.

This checkout confirms the pinned carrier contains the upstream
`KVConnectorBase_V1` layerwise interface and the LMCache layerwise
implementation. It does not vendor `vllm-ascend`; that code was audited from a
separate upstream checkout and is recorded below as an upstream path, not as
part of the pinned `vendor/vllm` tree.

## Verified static call chain

The following references are relative to the pinned carrier at
`vendor/vllm` commit `68b8be04493d39d5706f3d0d18f465f5eab947c4`. The Ascend
references are from the separate upstream `vllm-project/vllm-ascend` checkout
used for the audit, not from the vendored submodule.

| Stage | Target path | Class / function | M0 gate question |
|---|---|---|---|
| repo plugin | `src/vllm_kv_materialization/plugin.py` | `register_plugin` | Prefix-cache seam only; no per-layer KV hook |
| worker connector lifecycle | `vendor/vllm/vllm/v1/worker/kv_connector_model_runner_mixin.py:34` | `KVConnectorModelRunnerMixin` | Binds metadata, starts load, waits for save |
| worker connector pre/post | `vendor/vllm/vllm/v1/worker/gpu/kv_connector.py:47` | `ActiveKVConnector` | `pre_forward`/`post_forward` boundary |
| KVConnector V1 base | `vendor/vllm/vllm/distributed/kv_transfer/kv_connector/v1/base.py:171` | `KVConnectorBase_V1` | Defines `start_load_kv`, `wait_for_layer_load`, `save_kv_layer`, `wait_for_save` |
| graph/eager break | `vendor/vllm/vllm/compilation/breakable_cudagraph.py:59` | `eager_break_during_capture` | Forces layerwise hooks into eager segment |
| attention consume | `vendor/vllm/vllm/model_executor/layers/attention/kv_transfer_utils.py:15` | `maybe_transfer_kv_layer` | Wraps attention; waits before, saves after |
| attention op | `vendor/vllm/vllm/model_executor/layers/attention/attention.py:761` | `unified_attention_with_output` | Consume seam for non-MLA |
| MLA attention op | `vendor/vllm/vllm/model_executor/layers/attention/mla_attention.py:1080` | `unified_mla_attention_with_output` | Consume seam for MLA |
| LMCache connector | `vendor/vllm/vllm/distributed/kv_transfer/kv_connector/v1/lmcache_connector.py:72` | `LMCacheConnectorV1` | `requires_piecewise_for_cudagraph` when layerwise |
| graph-mode override | `vendor/vllm/vllm/config/vllm.py:1295` | `VllmConfig` | Full graph modes forced to PIECEWISE for layerwise connectors |
| AscendStore connector | upstream `vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/ascend_store_connector.py:76` | `AscendStoreConnector` | Ascend KV Pool layerwise load/save |
| Ascend attention utils | upstream `vllm_ascend/attention/utils.py:431` | `wait_for_kv_layer_from_connector` / `maybe_save_kv_layer_to_connector` | Ascend consume seam |
| Ascend KV pool worker | upstream `vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/pool_worker.py:1701` | `KVPoolWorker.wait_for_layer_load` / `save_kv_layer` | Per-layer events, prefetch, thread wait |
| Ascend graph runtime | upstream `vllm_ascend/compilation/acl_graph.py:60` | `ACLGraphWrapper` | NPUGraph capture/replay |

The first fact is now settled at static-audit level: the pinned vLLM carrier
does expose a real per-layer `wait_for_layer_load`/`save_kv_layer` seam, and
the separate vLLM-Ascend tree has an AscendStore layerwise path. What is not
settled is the 910B2 runtime observation: whether that seam still has a
graph-induced gap.

## Gate checklist

- [x] Initialize `vendor/vllm` and record exact carrier commit + line numbers.
- [x] Confirm KVConnector V1 layerwise load/consume exists in the pinned carrier.
- [x] Confirm vLLM-Ascend Layerwise KV Pool and layerwise prefetch exist
      upstream; note it is not part of the vendored submodule.
- [x] Trace `wait_for_layer_load` / Ascend layer-ready path to attention
      consume at static-code level.
- [x] Trace `FULL` / `FULL_AND_PIECEWISE` config and graph/eager break path;
      layerwise connectors are forced to PIECEWISE.
- [x] Measure the real TP=1 910B2 consumer seam, paired graph/eager and
      prefetch 1/2/4 baselines. Device-timeline proxy shows no graph-only
      loss; see `M0_UPSTREAM_AUDIT.md`. A future Go claim would still require
      gate-correlated DMA completion, not wall-clock timing.
- [x] No layerwise-specific replay correctness signal was observed beyond the
      non-layerwise graph baseline; see `M0_UPSTREAM_AUDIT.md`.
- [ ] Keep `VLLM_WAVEMAT_ENABLE=0` and native path default until M0 go.
- [ ] Do not promote host fixture, simulation, dry-run, or projected numbers to
      end-to-end performance evidence.

## Runtime progress and current M0 reading

The pinned NPU environment can run vLLM-Ascend graph mode and AscendStore
memcache layerwise:

- Graph-mode readiness smoke passed on Qwen2.5-3B-Instruct with
  `FULL_AND_PIECEWISE`.
- AscendStore `kv_both` + `backend=memcache` + `use_layerwise=true` +
  `layerwise_prefetch_layers=1` passed on 8x 910B2 with
  `DeepSeek-V4-Flash-W8A8` in eager mode.

Both artifacts are recorded under `docs/wavemat/results/`. These are runtime
readiness/layerwise smokes, not M0 gap evidence.

The subsequent DeepSeek-V2-Lite TP=1 device sweep did exercise 54 real
`aclrtMemcpyBatch` loads per run, with vLLM prefix caching disabled. The
graph/eager overlap proxy is 0/0% at prefetch 1, 4.394/4.620% at prefetch 2,
and 4.305/4.040% at prefetch 4. It rules out a measurable graph-only overlap
penalty in this workload, while showing that larger static prefetch does not
make the synchronous baseline sufficiently overlap. That generic limitation is
outside WaveMat's graph-safe-materialization scope; do not start M1 unless
gate-correlated DMA tracing exposes a graph-only loss or correctness failure.

## Host-side failure injection

The first PR includes a deterministic, stdlib-only fixture:

- partial layer range
- stale generation
- duplicate consume
- ABA generation reuse
- load failure
- digest mismatch
- reuse before ACK
- crash/recovery orphan detection

All cases are expected to fail closed. Raw fixture results are generated by:

```bash
PYTHONPATH=src python3 scripts/run_wavemat_gate_selfcheck.py \
  --output docs/wavemat/results/m3_pr1_seam_gate_raw.json \
  --manifest-output docs/wavemat/M3_PR1_MANIFEST.json
```

The fixture result does not imply that a real Ascend per-layer consumer seam
exists or that WaveMat has any end-to-end performance benefit.
