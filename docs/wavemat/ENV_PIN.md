# WaveMat M0 environment pin

This file records the runtime pins used for the WaveMat M0 seam gate. It is
audit-only metadata, not an experimental result.

## Carrier (vLLM)

- path: `vendor/vllm`
- url: `https://github.com/vLLM-HUST/vllm-hust.git`
- branch: `feature/kv-materialization-runtime-integration`
- commit: `68b8be04493d39d5706f3d0d18f465f5eab947c4`
- base release: vllm-hust `0.23.1` (upstream `0.23.1rc0`)

## Default Ascend platform plugin

- path: `vendor/vllm-ascend-hust`
- url: `https://github.com/vLLM-HUST/vllm-ascend-hust.git`
- commit: `03a12f9bddd944952bd029c6b62e23d68fa3a28e`
- distribution name: `vllm-ascend-hust`
- entry point: `vllm.platform_plugins: ascend -> vllm_ascend:register`

The launcher prepends `vendor/vllm-ascend-hust` to `PYTHONPATH`, so the
`ascend` platform plugin resolves to this checkout instead of any globally
installed `vllm_ascend`. Build it once with:

```bash
bash scripts/setup_wavemat_plugin.sh
```

## Task model (lightweight DeepSeek)

- repo id: `deepseek-ai/DeepSeek-V2-Lite`
- local path: `/root/models/DeepSeek-V2-Lite`
- architecture: `deepseek_v2` (MLA), 27 layers, 16 attention heads,
  `kv_lora_rank=512`, 64 routed experts / 6 active, bf16

Note for M0: `DeepSeek-V2-Lite` has 16 attention heads. Ascend graph mode has
historically only been validated for query-head counts in `{32, 64, 128}`; the
16-head MLA case must be verified explicitly during the graph-mode seam gate,
and `enforce_eager=True` is the fallback for correctness-only runs.
