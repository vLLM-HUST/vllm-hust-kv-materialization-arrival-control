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

```bash
ENV_NAME=vllm-kv-materialization-exp \
MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
bash paper/kv_materialization_control/experiments/launch_vllm_kv_materialization_server.sh
```

Enable the plugin loader explicitly:

```bash
ENV_NAME=vllm-kv-materialization-exp \
MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
ENABLE_PLUGIN=1 \
bash paper/kv_materialization_control/experiments/launch_vllm_kv_materialization_server.sh
```

## Workload Driver

```bash
MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
BASE_URL=http://127.0.0.1:8011 \
WORKLOAD=short_low \
bash paper/kv_materialization_control/experiments/run_live_benchmark.sh
```

## Output

The live harness writes a JSON summary with:

- completed requests
- mean latency
- p95 latency
- request throughput
- output-token throughput
- failure records, if any
