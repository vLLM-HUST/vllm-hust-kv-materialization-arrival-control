#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
TARGET_ENV="${TARGET_ENV:-vllm-kv-materialization-exp}"
SOURCE_ENV="${SOURCE_ENV:-vllm-hust-dev}"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda is required to create ${TARGET_ENV}" >&2
  exit 1
fi

if ! conda env list | awk '{print $1}' | grep -Fxq "$TARGET_ENV"; then
  conda create -y --name "$TARGET_ENV" --clone "$SOURCE_ENV"
fi

exec conda run --no-capture-output -n "$TARGET_ENV" \
  env -u LD_LIBRARY_PATH python -m pip install -e "$REPO_ROOT[dev]"
