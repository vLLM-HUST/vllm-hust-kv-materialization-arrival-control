from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any


def _first_token_ms(output: Any) -> float | None:
    """Best-effort TTFT from vLLM v1 RequestOutput.metrics."""
    metrics = getattr(output, "metrics", None)
    if metrics is None:
        return None
    for attr in ("first_token_time", "time_to_first_token"):
        value = getattr(metrics, attr, None)
        if value is not None:
            return float(value) * 1000.0
    return None


def run_baseline(
    model: str,
    prefetch_layers: int,
    cudagraph_mode: str,
    max_tokens: int,
    gpu_memory_utilization: float,
) -> dict[str, Any]:
    from vllm import LLM, SamplingParams

    assert "MMC_LOCAL_CONFIG_PATH" in os.environ, (
        "MMC_LOCAL_CONFIG_PATH must point at the MMC local config; the "
        "AscendStore memcache backend requires a running MMC meta service."
    )

    llm = LLM(
        model=model,
        trust_remote_code=True,
        enforce_eager=False,
        tensor_parallel_size=8,
        max_model_len=256,
        max_num_seqs=2,
        gpu_memory_utilization=gpu_memory_utilization,
        disable_log_stats=True,
        compilation_config={"cudagraph_mode": cudagraph_mode},
        kv_transfer_config={
            "kv_connector": "AscendStoreConnector",
            "kv_role": "kv_both",
            "kv_connector_extra_config": {
                "backend": "memcache",
                "use_layerwise": True,
                "layerwise_prefetch_layers": prefetch_layers,
            },
        },
    )

    started = time.time()
    output = llm.generate(
        ["Hello, world!"],
        SamplingParams(max_tokens=max_tokens, temperature=0),
    )[0]
    elapsed_s = time.time() - started

    return {
        "model": model,
        "cudagraph_mode": cudagraph_mode,
        "layerwise_prefetch_layers": prefetch_layers,
        "max_tokens": max_tokens,
        "prompt": output.prompt,
        "generated_text": output.outputs[0].text,
        "ttft_ms": _first_token_ms(output),
        "generate_elapsed_s": round(elapsed_s, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="WaveMat M0 layerwise baseline.")
    parser.add_argument(
        "--model",
        default="/root/models/DeepSeek-V2-Lite",
    )
    parser.add_argument("--prefetch-layers", type=int, default=1)
    parser.add_argument(
        "--cudagraph-mode",
        default="FULL_AND_PIECEWISE",
        choices=["FULL", "FULL_AND_PIECEWISE", "PIECEWISE", "NONE"],
    )
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.6)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/wavemat/results/m0_layerwise_baseline_raw.json"),
    )
    args = parser.parse_args()

    evidence = run_baseline(
        args.model,
        args.prefetch_layers,
        args.cudagraph_mode,
        args.max_tokens,
        args.gpu_memory_utilization,
    )
    evidence["generated_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    evidence["artifact"] = "m0-wavemat-layerwise-baseline"
    evidence["is_end_to_end_performance_evidence"] = False
    evidence["is_wavemat_mechanism_enabled"] = False

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output}")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
