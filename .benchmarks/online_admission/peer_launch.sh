#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")"
work=${KV41_WORK:-/tmp/kv-arrival-c1-c16.raYwEN}
core=${KV41_CORE:?Set KV41_CORE to the patched vLLM package root}
repo=$(cd ../.. && pwd)
v="$work/venv/bin/python"
out="$PWD/${1:?new output directory required}"
mkdir "$out"
export KV41_CONTENTION_DIR="$out" VLLM_SERVER_DEV_MODE=1
sha256sum "$repo/src/vllm_kv_materialization/online_kv_admission.py" kv41_online_probe.py peer_replay.py "$core/vllm/v1/core/sched/scheduler.py" > "$out/build.sha256"
unset LD_PRELOAD HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy OPENAI_API_KEY
ulimit -c 0
source /usr/local/Ascend/cann/set_env.sh >/dev/null
source /usr/local/Ascend/nnal/atb/set_env.sh --cxx_abi=1 >/dev/null
export DO_NOT_TRACK=1 VLLM_NO_USAGE_STATS=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1
export XDG_CACHE_HOME="$work/cache" VLLM_CACHE_ROOT="$work/cache/vllm"
export ASCEND_CACHE_PATH="$work/cache/ascend" TMPDIR="$work/tmp"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=4 TASK_QUEUE_ENABLE=0 HCCL_OP_EXPANSION_MODE=AIV
export VLLM_WORKER_MULTIPROC_METHOD=spawn VLLM_USE_RUST_FRONTEND=0
export VLLM_PLUGINS=ascend,ascend_model,ascend_model_loader,ascend_kv_connector
export PYTHONPATH="$core:$repo/src:$PWD:$PWD/runtime:$PWD/runtime-deps:${PYTHONPATH:-}"
npu-smi info > "$out/npu-before.txt"
grep -q 'No running processes found in NPU 1' "$out/npu-before.txt"
grep -q 'No running processes found in NPU 6' "$out/npu-before.txt"

cache_pid=
engine_pid=
cleanup() {
    for pid in "$engine_pid" "$cache_pid"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill -TERM -- "-$pid" 2>/dev/null || true
            for ((attempt=0; attempt<18; ++attempt)); do
                if ! kill -0 "$pid" 2>/dev/null; then break; fi
                sleep 1
            done
            kill -KILL -- "-$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done
    npu-smi info > "$out/npu-after.txt"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

setsid "$v" -c 'from lmcache.cli.main import main; main()' server \
    --host 127.0.0.1 --port 35555 --http-host 127.0.0.1 --http-port 35762 \
    --chunk-size 128 --supported-transfer-mode engine_driven --l1-size-gb 0.234375 \
    --shm-name "lmcache-kv41-$$" --no-l1-use-lazy --eviction-policy LRU --eviction-trigger-watermark 0.98 \
    > "$out/cache.log" 2>&1 &
cache_pid=$!
deadline=$((SECONDS + 90))
until grep -q '35555' "$out/cache.log" && curl -sf --noproxy '*' http://127.0.0.1:35762/healthcheck >/dev/null; do
    if ! kill -0 "$cache_pid" 2>/dev/null || ((SECONDS > deadline)); then exit 2; fi
    sleep 2
done

args=(
    serve /models/Qwen2.5-7B-Instruct --host 127.0.0.1 --port 34762
    --served-model-name Qwen2.5-7B-Instruct --tensor-parallel-size 2
    --pipeline-parallel-size 1 --dtype bfloat16 --safetensors-load-strategy lazy
    --max-model-len 16384 --max-num-seqs 8 --max-num-batched-tokens 4096
    --enable-prefix-caching --async-scheduling --block-size 128
    --compilation-config '{"cudagraph_mode":"FULL_AND_PIECEWISE"}'
    --kv-cache-memory-bytes 2147483648
    --kv-transfer-config '{"kv_connector":"KV41LMCacheConnector","kv_connector_module_path":"kv41_online_probe","kv_role":"kv_both","kv_connector_extra_config":{"admission_policy":"peer","reference_peer_tpot_ms":68.2235341410463,"lmcache.mp.host":"tcp://127.0.0.1","lmcache.mp.port":35555,"lmcache.mp.mp_transfer_mode":"engine_driven"}}'
)
printf '%s\n' "${args[@]}" > "$out/args.txt"
setsid "$v" -m vllm.entrypoints.cli.main "${args[@]}" > "$out/engine.log" 2>&1 &
engine_pid=$!
deadline=$((SECONDS + 390))
until curl -sf --noproxy '*' http://127.0.0.1:34762/health >/dev/null; do
    if ! kill -0 "$engine_pid" 2>/dev/null || ((SECONDS > deadline)); then exit 3; fi
    if grep -Eq 'EngineCore failed to start|Error in model runner' "$out/engine.log"; then exit 3; fi
    sleep 3
done
"$v" peer_replay.py "$out" "${2:?paired lifecycle index}" 2>&1 | tee "$out/driver.log"
