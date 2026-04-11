#!/usr/bin/env bash
set -euo pipefail

CONDA_SH="/root/miniconda3/etc/profile.d/conda.sh"
ENV_NAME="${ENV_NAME:-vllm-kv-materialization-exp}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8011}"
MODEL="${MODEL:-/home/shuhao/shared-models/Qwen2.5-7B-Instruct}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.85}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
BLOCK_SIZE="${BLOCK_SIZE:-16}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-$(basename "$MODEL") }"
ENABLE_PLUGIN="${ENABLE_PLUGIN:-0}"

source "$CONDA_SH"
conda activate "$ENV_NAME"
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"
unset PYTHONPATH
if [[ "$ENABLE_PLUGIN" == "1" ]]; then
  export VLLM_PLUGINS="kv_materialization"
else
  export VLLM_PLUGINS=""
fi

exec vllm serve "$MODEL" \
  --host "$HOST" \
  --port "$PORT" \
  --served-model-name "$SERVED_MODEL_NAME" \
  --max-model-len "$MAX_MODEL_LEN" \
  --block-size "$BLOCK_SIZE" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --enable-prefix-caching \
  "$@"
