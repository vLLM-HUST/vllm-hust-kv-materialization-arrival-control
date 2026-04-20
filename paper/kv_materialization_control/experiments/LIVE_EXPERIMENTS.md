# Live Experiment Workflow

## Goal

Run a live runtime-boundary experiment against a vLLM OpenAI-compatible endpoint.

This path is not the same as the offline decision study. It is used to show
which arrival-time actions the current runtime seam realizes online.

## Default Model

Preferred local path in this workspace:

- `/home/shuhao/shared-models/Qwen2.5-7B-Instruct`

Compatibility-only paths on some hosts may include:

- `/shared-models/Qwen2.5-7B-Instruct`
- `/workspace/shared-models/Qwen2.5-7B-Instruct`

## Server Launch

Note: when `MAX_MODEL_LEN` is not set explicitly, the launch helper now reads
the recommended context window from `llm-serving-workloads`
`SHARED_BENCHMARK_CASE_CATALOG` using `WORKLOAD_CASE` and therefore defaults to
the shared workload hint (`32768` for the current Qwen2.5-7B-Instruct-centered
workspace). You can still override it manually for constrained local runs.

```bash
ENV_NAME=vllm-kv-materialization-exp \
MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
WORKLOAD_CASE=shared_prefix_multi_tenant_assistant \
bash paper/kv_materialization_control/experiments/launch_vllm_kv_materialization_server.sh
```

Enable the plugin loader explicitly:

```bash
ENV_NAME=vllm-kv-materialization-exp \
MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
ENABLE_PLUGIN=1 \
WORKLOAD_CASE=shared_prefix_multi_tenant_assistant \
bash paper/kv_materialization_control/experiments/launch_vllm_kv_materialization_server.sh
```

## Workload Driver

```bash
MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
BASE_URL=https://api.sage.org.ai/v1 \
OPENAI_API_KEY=<token> \
OPENAI_HTTP_USER_AGENT=python-httpx/0.28.1 \
WORKLOAD_CASE=shared_prefix_multi_tenant_assistant \
bash paper/kv_materialization_control/experiments/run_live_benchmark.sh
```

Preferred workspace entry from the shared workload repository:

```bash
cd /home/shuhao/llm-serving-workloads
make kv-materialization-live \
	BASE_URL=https://api.sage.org.ai/v1 \
	OPENAI_API_KEY=<token> \
	MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
	WORKLOAD_CASE=shared_prefix_multi_tenant_assistant
```

Recommended runtime-boundary cases:

- `shared_prefix_multi_tenant_assistant`
- `session_continuation_with_maintenance`
- `dynamic_rag_corpus_update`

These cover the artifact's most important online boundaries: prefix-rich reuse,
long-context continuation, and retrieval overlap under change.

## Runtime Taxonomy

Interpret live results with the runtime taxonomy fields emitted by the plugin.

- `runtime_support_tier=native_runtime_action`: the requested action is realized
  directly on the current runtime seam
- `runtime_support_tier=fallback_to_supported_runtime_action`: the requested
  action is not natively supported and has been degraded to a supported online
  action

For `partial_reuse`, the current expected fallback is:

- `runtime_fallback_reason=exact_partial_segment_materialization_unavailable_on_prefix_cache_path`
- `runtime_effective_decision=full_reuse`

## Output

The live harness writes a JSON summary with:

- completed requests
- mean latency
- p95 latency
- request throughput
- output-token throughput
- failure records, if any
