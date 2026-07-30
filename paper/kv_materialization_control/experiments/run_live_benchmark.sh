#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8011}"
MODEL="${MODEL:-}"
WORKLOAD_CASE="${WORKLOAD_CASE:-shared_scenario_multi_turn_knowledge_service}"
OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)/results/live}"
LABEL="${LABEL:-${WORKLOAD_CASE}}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
OPENAI_HTTP_USER_AGENT="${OPENAI_HTTP_USER_AGENT:-python-httpx/0.28.1}"

mkdir -p "$OUTPUT_DIR"
if [[ -z "$MODEL" ]]; then
  echo "MODEL is required" >&2
  exit 2
fi
"$PYTHON_BIN" "$(dirname "$0")/run_openai_workloads.py" \
  --base-url "$BASE_URL" \
  --model "$MODEL" \
  --workload-case "$WORKLOAD_CASE" \
  --api-key "$OPENAI_API_KEY" \
  --user-agent "$OPENAI_HTTP_USER_AGENT" \
  --output "$OUTPUT_DIR/${LABEL}.json"

echo "$OUTPUT_DIR/${LABEL}.json"
