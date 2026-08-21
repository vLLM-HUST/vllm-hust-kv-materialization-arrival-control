#!/usr/bin/env bash

set -euo pipefail

# Pin and build the default Ascend platform plugin for the WaveMat M0 seam gate.
#
# The task's default Ascend plugin is vllm-ascend-hust pinned to commit
# 03a12f9bddd944952bd029c6b62e23d68fa3a28e. This script:
#   1. initializes the plugin submodule and its nested catlass dependency,
#   2. builds it in-place as an editable install,
#   3. verifies that `vllm_ascend` resolves to this checkout.
#
# Usage:
#   bash scripts/setup_wavemat_plugin.sh
#
# Environment:
#   PYTHON_BIN       Python interpreter to use (default: python3 on PATH)
#   COMPILE_CUSTOM_KERNELS  Build Ascend custom kernels (default: 1)

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
PLUGIN_ROOT="${REPO_ROOT}/vendor/vllm-ascend-hust"
PLUGIN_COMMIT="03a12f9bddd944952bd029c6b62e23d68fa3a28e"
PYTHON_BIN="${PYTHON_BIN:-python3}"
COMPILE_CUSTOM_KERNELS="${COMPILE_CUSTOM_KERNELS:-1}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[ERROR] python interpreter not found: ${PYTHON_BIN}" >&2
  exit 1
fi

echo "[INFO] Syncing plugin submodule (${PLUGIN_COMMIT})"
git -C "${REPO_ROOT}" submodule update --init -- vendor/vllm-ascend-hust
git -C "${PLUGIN_ROOT}" checkout "${PLUGIN_COMMIT}"
git -C "${PLUGIN_ROOT}" submodule update --init --recursive

actual_commit="$(git -C "${PLUGIN_ROOT}" rev-parse HEAD)"
if [[ "${actual_commit}" != "${PLUGIN_COMMIT}"* ]]; then
  echo "[ERROR] plugin checkout mismatch: got ${actual_commit}, want ${PLUGIN_COMMIT}" >&2
  exit 1
fi

echo "[INFO] Building vllm-ascend-hust (COMPILE_CUSTOM_KERNELS=${COMPILE_CUSTOM_KERNELS})"
COMPILE_CUSTOM_KERNELS="${COMPILE_CUSTOM_KERNELS}" \
  "${PYTHON_BIN}" -m pip install -e "${PLUGIN_ROOT}" --no-build-isolation --no-deps

echo "[INFO] Verifying vllm_ascend resolves to the pinned checkout"
PYTHONPATH="${PLUGIN_ROOT}" VLLM_ASCEND_EXPECTED_ROOT="${PLUGIN_ROOT}" "${PYTHON_BIN}" - <<'PY'
from pathlib import Path
import os
import vllm_ascend

module_path = Path(vllm_ascend.__file__).resolve()
expected = Path(os.environ["VLLM_ASCEND_EXPECTED_ROOT"]).resolve()
print(f"[INFO] vllm_ascend module path: {module_path}")
if expected not in module_path.parents:
    raise SystemExit(f"[ERROR] vllm_ascend resolved to {module_path}, expected under {expected}")
print("[OK] vllm-ascend-hust is the default Ascend platform plugin.")
print(f"[OK] register() -> {vllm_ascend.register()}")
PY

echo "[OK] WaveMat default plugin setup complete."
