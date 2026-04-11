#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8011}"
MODEL="${MODEL:-/home/shuhao/shared-models/Qwen2.5-7B-Instruct}"
WORKLOAD="${WORKLOAD:-short_low}"
OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)/results/live}"
LABEL="${LABEL:-${WORKLOAD}}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$OUTPUT_DIR"
"$PYTHON_BIN" "$(dirname "$0")/run_openai_workloads.py" \
  --base-url "$BASE_URL" \
  --model "$MODEL" \
  --workload "$WORKLOAD" \
  --output "$OUTPUT_DIR/${LABEL}.json"

echo "$OUTPUT_DIR/${LABEL}.json"
