#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
vendor_root="${repo_root}/vendor/vllm"

if [[ -d "${vendor_root}/.git" ]]; then
    printf 'vendor/vllm already exists at %s\n' "${vendor_root}"
    exit 0
fi

git clone https://github.com/vllm-project/vllm.git "${vendor_root}"
