#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
CONDA_SH="${CONDA_SH:-}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8011}"
MODEL="${MODEL:-}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.85}"
WORKLOAD_CASE="${WORKLOAD_CASE:-shared_scenario_multi_turn_knowledge_service}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-}"
BLOCK_SIZE="${BLOCK_SIZE:-16}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-$(basename "$MODEL")}"
ENABLE_PLUGIN="${ENABLE_PLUGIN:-1}"
CARRIER_VLLM_HUST_ROOT="${CARRIER_VLLM_HUST_ROOT:-$REPO_ROOT/vendor/vllm}"
VLLM_ASCEND_HUST_ROOT="${VLLM_ASCEND_HUST_ROOT:-$REPO_ROOT/vendor/vllm-ascend-hust}"
XDG_CACHE_HOME="${VLLM_KV_MATERIALIZATION_XDG_CACHE_HOME:-$REPO_ROOT/.cache/vllm}"
HF_HOME="${VLLM_KV_MATERIALIZATION_HF_HOME:-$REPO_ROOT/.cache/huggingface}"
VLLM_CACHE_ROOT="${VLLM_CACHE_ROOT:-$XDG_CACHE_HOME/vllm}"

if [[ -z "$CONDA_SH" ]]; then
  conda_candidates=()
  if command -v conda >/dev/null 2>&1; then
    conda_base="$(conda info --base 2>/dev/null || true)"
    if [[ -n "$conda_base" ]]; then
      conda_candidates+=("$conda_base/etc/profile.d/conda.sh")
    fi
  fi
  for candidate in "${conda_candidates[@]}"; do
    if [[ -f "$candidate" ]]; then
      CONDA_SH="$candidate"
      break
    fi
  done
fi

if [[ -z "$CONDA_SH" || ! -f "$CONDA_SH" ]]; then
  echo "unable to locate conda.sh; set CONDA_SH explicitly" >&2
  exit 1
fi

source "$CONDA_SH"
ENV_NAME="${ENV_NAME:-vllm-kv-materialization-exp}"
if [[ -z "$MODEL" ]]; then
  echo "MODEL is required" >&2
  exit 2
fi
if [[ ! -f "$CARRIER_VLLM_HUST_ROOT/vllm/__init__.py" ]]; then
  echo "missing runtime carrier; run: git submodule update --init" >&2
  exit 2
fi
if [[ ! -f "$VLLM_ASCEND_HUST_ROOT/vllm_ascend/__init__.py" ]]; then
  echo "missing vllm-ascend-hust plugin; run: git submodule update --init" >&2
  exit 2
fi
conda activate "$ENV_NAME"
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"
export XDG_CACHE_HOME
export HF_HOME
export VLLM_CACHE_ROOT
export PYTHONNOUSERSITE="${PYTHONNOUSERSITE:-1}"
export PYTHONPATH="$VLLM_ASCEND_HUST_ROOT:$CARRIER_VLLM_HUST_ROOT:$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export VLLM_KV_RUNTIME_BLOCK_SIZE="${VLLM_KV_RUNTIME_BLOCK_SIZE:-$BLOCK_SIZE}"
mkdir -p "$XDG_CACHE_HOME" "$HF_HOME" "$VLLM_CACHE_ROOT"
if [[ -z "$MAX_MODEL_LEN" ]]; then
  MAX_MODEL_LEN="$({
    python - "$WORKLOAD_CASE" <<'PY'
import sys

from vllm_kv_materialization.shared_workloads import recommended_context_window

print(recommended_context_window(sys.argv[1], fallback=32768))
PY
  } )"
fi
if [[ "$ENABLE_PLUGIN" == "1" ]]; then
  export VLLM_PLUGINS="ascend,kv_materialization"
else
  export VLLM_PLUGINS="ascend"
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
