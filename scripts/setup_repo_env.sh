#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
BOOTSTRAP_SCRIPT="/root/llm-optimizations/scripts/bootstrap_shared_env.sh"
TARGET_ENV="${TARGET_ENV:-vllm-kv-materialization-exp}"
SOURCE_ENV="${SOURCE_ENV:-llm-optimizations}"

exec "$BOOTSTRAP_SCRIPT" \
  --profile generic \
  --source-env "$SOURCE_ENV" \
  --repo-root "$REPO_ROOT" \
  --env-name "$TARGET_ENV"