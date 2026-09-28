# NPU plugin live validation — 2026-09-10

## Verdict

PASS for the deployed vLLM 0.23 compatibility path. The current plugin package
was loaded from its declared `vllm.general_plugins` entry point, served a local
Qwen2.5-3B-Instruct model on an Ascend 910B2, completed two real
OpenAI-compatible requests, and produced controller plus engine-owned runtime
records.

The native vLLM-HUST hook API 1.0 path remains covered by repository and
carrier contract tests. It was not executed on this node because the checked-in
vLLM-HUST main carrier requires Torch 2.13 while the installed NPU runtime is
vLLM/vLLM-Ascend 0.23 with Torch-NPU 2.10.

## Runtime

- Device: Ascend 910B2, physical NPU 7
- Model: `/data/shared_datasets/models/Qwen2.5-3B-Instruct`
- Endpoint: `POST /v1/chat/completions`
- Host: vLLM 0.23 compatibility carrier based on `0fc695fc6`
- Plugin mode: `legacy-vllm-0.23-adapter`
- Prefix-cache block size: 128 tokens
- Policy: `always_full_reuse`
- Prompt: 3,102 tokens; output: 16 tokens

## Result

| Request | HTTP | Latency | Engine reused | Engine recomputed |
| --- | ---: | ---: | ---: | ---: |
| `npu-plugin-full-1` | 200 | 0.463 s | 0 | 3,102 |
| `npu-plugin-full-2` | 200 | 0.242 s | 3,072 | 30 |

The second request matched 24 physical hash blocks (`24 * 128 = 3,072`
tokens). Both lookup rows close exactly:
`engine_reused_tokens + engine_recomputed_tokens = engine_prompt_tokens`.
The server-reported aggregate prefix-cache hit rate was 49.5% after the pair.

Raw local evidence is under
`paper/kv_materialization_control/experiments/results/live/plugin_npu_validation_20260910/`.
The directory is intentionally ignored because it contains generated runtime
logs. It includes the successful `server.log`, `client.log`,
`runtime_observations.jsonl`, and `runtime_events.jsonl`, plus preserved logs
from the compatibility issues found and fixed during bring-up.

## Cleanup

The service was stopped after validation. Port 8011 was free and NPU 7 had no
running process after shutdown.
