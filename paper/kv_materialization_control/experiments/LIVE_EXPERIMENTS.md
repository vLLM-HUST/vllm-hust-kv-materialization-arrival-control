# Live Experiment Workflow

## Goal

Run a live runtime-boundary experiment against a vLLM OpenAI-compatible endpoint.

This path is not the same as the offline decision study. It is used to show
which arrival-time actions the current runtime seam realizes online.

## Model

Set `MODEL` to a locally available model or model identifier. The scripts do
not assume a host-specific model directory.

## Server Launch

Note: when `MAX_MODEL_LEN` is not set explicitly, the launch helper now reads
the recommended context window from `llm-serving-workloads`
`SHARED_BENCHMARK_CASE_CATALOG` using `WORKLOAD_CASE` and therefore defaults to
the shared workload hint (`32768` for the current Qwen2.5-7B-Instruct-centered
workspace). You can still override it manually for constrained local runs.

```bash
ENV_NAME=vllm-kv-materialization-exp \
MODEL=/path/to/model \
WORKLOAD_CASE=shared_prefix_multi_tenant_assistant \
bash paper/kv_materialization_control/experiments/launch_vllm_kv_materialization_server.sh
```

Enable the plugin loader explicitly:

```bash
ENV_NAME=vllm-kv-materialization-exp \
MODEL=/path/to/model \
ENABLE_PLUGIN=1 \
WORKLOAD_CASE=shared_prefix_multi_tenant_assistant \
bash paper/kv_materialization_control/experiments/launch_vllm_kv_materialization_server.sh
```

## Workload Driver

```bash
MODEL=/path/to/model \
BASE_URL=https://api.sage.org.ai/v1 \
OPENAI_API_KEY=<token> \
OPENAI_HTTP_USER_AGENT=python-httpx/0.28.1 \
WORKLOAD_CASE=shared_prefix_multi_tenant_assistant \
bash paper/kv_materialization_control/experiments/run_live_benchmark.sh
```

When the workload comes from the repo-local shared catalog, prefer passing the
real model tokenizer into the live runner so shared-workload token budgets are
constructed against the same tokenizer that the endpoint will actually use:

```bash
conda run -n vllm-kv-materialization-exp python \
	paper/kv_materialization_control/experiments/run_openai_workloads.py \
	--base-url http://127.0.0.1:8011 \
	--model Qwen2.5-7B-Instruct \
	--tokenizer /path/to/model \
	--workload-case dynamic_rag_corpus_update \
	--output paper/kv_materialization_control/experiments/results/live/dynamic_rag_live.json
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

For `partial_reuse`, the current runtime may realize one of two truthful paths:

- `runtime_effective_decision=partial_reuse` with
	`runtime_control_path=block_aligned_partial_prefix_cache` when the aligned
	cut point remains profitable on the current prefix-cache path
- `runtime_effective_decision=full_reuse` when the aligned partial segment is
	dominated by anchor-scoped reuse or cannot survive runtime realignment

## Output

The live harness writes a JSON summary with:

- completed requests
- mean latency
- p95 latency
- request throughput
- output-token throughput
- failure records, if any

Recent runtime-boundary note:

- `dynamic_rag_corpus_update` can run successfully on the Qwen2.5-7B live path,
  but only when the workload itself is generated with the real Qwen tokenizer.
  The earlier 32K-overflow failure was caused by building the workload with a
  whitespace tokenizer, which inflated the effective prompt budget seen by the
  runtime.
