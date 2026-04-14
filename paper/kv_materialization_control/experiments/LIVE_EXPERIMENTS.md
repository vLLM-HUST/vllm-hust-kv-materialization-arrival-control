# Live Experiment Workflow

## Goal

Run a real-model benchmark against a vLLM OpenAI-compatible endpoint rather than relying only on synthetic offline traces.

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
WORKLOAD_CASE=shared_scenario_multi_turn_knowledge_service \
bash paper/kv_materialization_control/experiments/launch_vllm_kv_materialization_server.sh
```

Enable the plugin loader explicitly:

```bash
ENV_NAME=vllm-kv-materialization-exp \
MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
ENABLE_PLUGIN=1 \
WORKLOAD_CASE=shared_scenario_multi_turn_knowledge_service \
bash paper/kv_materialization_control/experiments/launch_vllm_kv_materialization_server.sh
```

## Workload Driver

```bash
MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
BASE_URL=https://api.sage.org.ai/v1 \
OPENAI_API_KEY=<token> \
OPENAI_HTTP_USER_AGENT=python-httpx/0.28.1 \
WORKLOAD_CASE=shared_scenario_multi_turn_knowledge_service \
bash paper/kv_materialization_control/experiments/run_live_benchmark.sh
```

Preferred workspace entry from the shared workload repository:

```bash
cd /home/shuhao/llm-serving-workloads
make kv-materialization-live \
	BASE_URL=https://api.sage.org.ai/v1 \
	OPENAI_API_KEY=<token> \
	MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
	WORKLOAD_CASE=shared_scenario_multi_turn_knowledge_service
```

## Output

The live harness writes a JSON summary with:

- completed requests
- mean latency
- p95 latency
- request throughput
- output-token throughput
- failure records, if any
