from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

SHARED_PREFIX = (
    "The history of computing spans many centuries and reflects the human desire "
    "to automate calculation and process information. Early mechanical devices "
    "such as the abacus preceded modern electronic computers. "
)
SUFFIXES = [
    "Summarize this paragraph in one sentence.",
    "Name an early computing device.",
    "What is the main topic?",
    "State one consequence of electronic computers.",
]


def run(
    model: str,
    use_layerwise: bool,
    prefetch_layers: int,
    cudagraph_mode: str,
    max_tokens: int,
    enforce_eager: bool,
    gpu_memory_utilization: float,
    tensor_parallel_size: int,
) -> dict[str, Any]:
    from vllm import LLM, SamplingParams

    llm = LLM(
        model=model,
        trust_remote_code=True,
        enforce_eager=enforce_eager,
        tensor_parallel_size=tensor_parallel_size,
        max_model_len=512,
        max_num_seqs=4,
        gpu_memory_utilization=gpu_memory_utilization,
        # Ensure the second generation uses AscendStore materialization, not an
        # in-engine prefix-cache hit that would skip the layerwise path.
        enable_prefix_caching=False,
        compilation_config={"cudagraph_mode": cudagraph_mode},
        kv_transfer_config={
            "kv_connector": "AscendStoreConnector",
            "kv_role": "kv_both",
            "kv_connector_extra_config": {
                "backend": "memcache",
                "use_layerwise": use_layerwise,
                "layerwise_prefetch_layers": prefetch_layers,
            },
        },
    )

    params = SamplingParams(max_tokens=max_tokens, temperature=0)
    llm.generate([SHARED_PREFIX], SamplingParams(max_tokens=1, temperature=0), use_tqdm=False)
    prompts = [SHARED_PREFIX + suffix for suffix in SUFFIXES]
    started = time.time()
    outputs = llm.generate(prompts, params, use_tqdm=False)
    wall_s = time.time() - started

    results = [
        {
            "prompt": out.prompt,
            "text": out.outputs[0].text,
            "finish_reason": str(out.outputs[0].finish_reason),
        }
        for out in outputs
    ]
    return {
        "model": model,
        "use_layerwise": use_layerwise,
        "layerwise_prefetch_layers": prefetch_layers,
        "cudagraph_mode": cudagraph_mode,
        "enforce_eager": enforce_eager,
        "tensor_parallel_size": tensor_parallel_size,
        "vllm_prefix_caching_enabled": False,
        "max_tokens": max_tokens,
        "wall_clock_s": round(wall_s, 3),
        "outputs": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="WaveMat M0 correctness oracle.")
    parser.add_argument("--model", default="/root/models/DeepSeek-V2-Lite")
    parser.add_argument("--use-layerwise", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--prefetch-layers", type=int, default=1)
    parser.add_argument("--cudagraph-mode", default="FULL_AND_PIECEWISE")
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--enforce-eager", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.22)
    parser.add_argument("--tensor-parallel-size", type=int, choices=[1, 2, 4, 8], default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    assert "MMC_LOCAL_CONFIG_PATH" in os.environ, "MMC_LOCAL_CONFIG_PATH required"
    result = run(
        args.model,
        args.use_layerwise,
        args.prefetch_layers,
        args.cudagraph_mode,
        args.max_tokens,
        args.enforce_eager,
        args.gpu_memory_utilization,
        args.tensor_parallel_size,
    )
    result["artifact"] = "m0-wavemat-correctness"
    result["is_wavemat_mechanism_enabled"] = False
    result["generated_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "wall_clock_s": result["wall_clock_s"]}))


if __name__ == "__main__":
    main()
