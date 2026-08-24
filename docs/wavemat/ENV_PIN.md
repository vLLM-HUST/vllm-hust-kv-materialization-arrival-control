# WaveMat M0 environment pin

This file records the runtime pins used for the WaveMat M0 seam gate. It is
audit-only metadata, not an experimental result.

# WaveMat M0 environment pin

This file records the runtime pins used for the WaveMat M0 seam gate. It is
audit-only metadata, not an experimental result.

## M0 runtime (upstream 0.23 pair)

The active overlap experiment uses the locally available DeepSeek V4 Lite test
target: `/data/shared_datasets/models/DeepSeek-V4-Flash-W8A8`. “V4 Lite” is
the experiment label; the upstream local directory is named V4 Flash W8A8.
The DeepSeek-V2-Lite pin recorded later in this document is historical M0
baseline evidence, not the active overlap-test target.

M0 uses the installed upstream pair, with no `PYTHONPATH` override:

- vLLM: `vllm-project/vllm` `0.23.0` (editable at `/vllm-workspace/vllm`,
  commit `0fc695fc6d1d82e9a5ac6835ac8e4e1c83703665`)
- vllm-ascend: `vllm-project/vllm-ascend` `0.23.0rc1` (editable at
  `/vllm-workspace/vllm-ascend`, commit `f4a08bddd0cc65a0bd8c3d377b158ae5ca7527db`)
- entry point: `vllm.platform_plugins: ascend -> vllm_ascend:register`

This is the current upstream layerwise KV pipeline (Layerwise KV Pool /
layerwise prefetch / event callbacks), which is the correct M0 baseline per the
issue.

## Why not the vllm-hust forks

The available vllm-hust artifacts do not form a runnable pair for DeepSeek MLA:

- `vendor/vllm` (vllm-hust `0.23.1`) + upstream vllm-ascend `0.23.0rc1`
  fails at plugin patch time:
  `AttributeError: Glm47MoeModelToolParser has no attribute
  '_extract_tool_call_regions'`.
- `vendor/vllm` + vllm-ascend-hust `03a12f9b` (based on vllm-ascend `0.19.1rc1`)
  fails at model load:
  `TypeError: _deepseek_v2_mla_attention_init() got an unexpected keyword
  argument 'reduce_results'`.

The HUST fork's layerwise changes on top of `0.19.1` are minimal (3 non-merge
commits; zero changes to the attention backends), so it adds no baseline
mechanism over upstream. It remains only as the historical M2 reference (paired
with the now-unavailable carrier `475ea49`).

## Task model

- repo id: `deepseek-ai/DeepSeek-V2-Lite`
- local path: `/root/models/DeepSeek-V2-Lite`
- architecture: `deepseek_v2` (MLA), 27 layers, 16 attention heads,
  `kv_lora_rank=512`, 64 routed experts / 6 active, bf16

Graph mode has been verified on 8x 910B2 with `enforce_eager=False` and
`cudagraph_mode=FULL_AND_PIECEWISE`: both PIECEWISE and FULL graphs capture
successfully. The earlier `{32, 64, 128}`-heads concern is not supported by the
code and does not reproduce.

## Environment notes

- `OMP_NUM_THREADS=1` is required with `tensor_parallel_size=8`; otherwise the
  forked workers crash with torch `Invalid thread pool!`.
- Keep the CANN `PYTHONPATH` entry
  (`/usr/local/Ascend/cann-9.0.1/python/site-packages`) so the `acl` module is
  importable in worker processes.
