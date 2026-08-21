from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    return round(statistics.quantiles(values, n=100, method="inclusive")[min(99, int(p * 100) - 1)], 4)


def _extract_stats(outputs: list[Any]) -> dict[str, Any]:
    ttft: list[float] = []
    decode: list[float] = []
    e2e: list[float] = []
    tpot: list[float] = []

    for out in outputs:
        metrics = getattr(out, "metrics", None)
        if metrics is None:
            continue
        # RequestOutput.metrics is a RequestStateStats in vLLM v1.
        ttft_s = getattr(metrics, "first_token_latency", None)
        first_ts = getattr(metrics, "first_token_ts", 0.0)
        last_ts = getattr(metrics, "last_token_ts", 0.0)
        n_gen = int(getattr(metrics, "num_generation_tokens", 0) or 0)
        if ttft_s is None:
            continue
        decode_s = float(last_ts - first_ts)
        ttft.append(float(ttft_s))
        decode.append(decode_s)
        e2e.append(float(ttft_s) + decode_s)
        if n_gen > 1:
            tpot.append(decode_s / (n_gen - 1))

    return {
        "num_finished": len(ttft),
        "ttft_s_p50": _pct(ttft, 0.5),
        "ttft_s_p95": _pct(ttft, 0.95),
        "tpot_s_p50": _pct(tpot, 0.5),
        "tpot_s_p95": _pct(tpot, 0.95),
        "e2e_s_p50": _pct(e2e, 0.5),
        "e2e_s_p95": _pct(e2e, 0.95),
        "decode_s_mean": round(statistics.fmean(decode), 4) if decode else None,
    }


def run(
    model: str,
    use_layerwise: bool,
    prefetch_layers: int,
    cudagraph_mode: str,
    num_prompts: int,
    max_num_seqs: int,
    max_tokens: int,
    gpu_memory_utilization: float,
) -> dict[str, Any]:
    from vllm import LLM, SamplingParams

    llm = LLM(
        model=model,
        trust_remote_code=True,
        enforce_eager=False,
        tensor_parallel_size=8,
        max_model_len=256,
        max_num_seqs=max_num_seqs,
        gpu_memory_utilization=gpu_memory_utilization,
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

    prompts = ["Write a function that returns the sum of two integers."] * num_prompts
    params = SamplingParams(max_tokens=max_tokens, temperature=0)
    started = time.time()
    outputs = llm.generate(prompts, params, use_tqdm=False)
    wall_s = time.time() - started

    stats = _extract_stats(outputs)
    stats.update(
        {
            "model": model,
            "use_layerwise": use_layerwise,
            "layerwise_prefetch_layers": prefetch_layers,
            "cudagraph_mode": cudagraph_mode,
            "num_prompts": num_prompts,
            "max_num_seqs": max_num_seqs,
            "max_tokens": max_tokens,
            "wall_clock_s": round(wall_s, 3),
            "first_output_text": outputs[0].outputs[0].text[:120],
        }
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="WaveMat M0 layerwise timing.")
    parser.add_argument("--model", default="/root/models/DeepSeek-V2-Lite")
    parser.add_argument("--use-layerwise", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--prefetch-layers", type=int, default=1)
    parser.add_argument("--cudagraph-mode", default="FULL_AND_PIECEWISE")
    parser.add_argument("--num-prompts", type=int, default=8)
    parser.add_argument("--max-num-seqs", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.6)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    assert "MMC_LOCAL_CONFIG_PATH" in os.environ, "MMC_LOCAL_CONFIG_PATH required"
    result = run(
        args.model,
        args.use_layerwise,
        args.prefetch_layers,
        args.cudagraph_mode,
        args.num_prompts,
        args.max_num_seqs,
        args.max_tokens,
        args.gpu_memory_utilization,
    )
    result["artifact"] = "m0-wavemat-layerwise-timing"
    result["is_end_to_end_performance_evidence"] = False
    result["is_wavemat_mechanism_enabled"] = False
    result["generated_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
