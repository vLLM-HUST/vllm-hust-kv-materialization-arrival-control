from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

# A long shared prefix (roughly 250+ tokens) so prefix caching triggers a
# per-layer KV load on subsequent requests.
SHARED_PREFIX = (
    "The history of computing spans many centuries and reflects the human "
    "desire to automate calculation and process information more efficiently. "
    "Early mechanical devices such as the abacus and the Antikythera mechanism "
    "demonstrated that computation could be represented physically. During the "
    "nineteenth century, Charles Babbage designed the Analytical Engine and Ada "
    "Lovelace wrote what is often regarded as the first algorithm intended for "
    "a machine. The twentieth century brought electronic computers, beginning "
    "with large vacuum-tube machines and later transistorized systems. "
    "The invention of the integrated circuit enabled computers to become "
    "smaller, faster, and cheaper, leading to the personal computer revolution. "
    "Networking technologies then connected these machines into a global "
    "internet. Modern computing continues to evolve through parallel hardware, "
    "distributed systems, and machine learning, and it now influences nearly "
    "every aspect of science, industry, and daily life. "
)

SUFFIXES = [
    "Summarize the previous paragraph in one sentence.",
    "What was Ada Lovelace's contribution?",
    "Name two inventions that made computers smaller.",
    "What major change did networking bring?",
    "List one modern computing trend.",
    "What is the main topic of the paragraph?",
]


def run(
    model: str,
    use_layerwise: bool,
    prefetch_layers: int,
    max_tokens: int,
    gpu_memory_utilization: float,
    tensor_parallel_size: int,
    enforce_eager: bool,
    torch_profile_dir: Path | None,
) -> dict[str, Any]:
    from vllm import LLM, SamplingParams

    prompts = [SHARED_PREFIX + s for s in SUFFIXES]
    llm_kwargs: dict[str, Any] = {
        "model": model,
        "trust_remote_code": True,
        "enforce_eager": enforce_eager,
        "tensor_parallel_size": tensor_parallel_size,
        "max_model_len": 512,
        "max_num_seqs": 6,
        "gpu_memory_utilization": gpu_memory_utilization,
        # The cache under test is AscendStore.  Keeping vLLM's in-engine
        # prefix cache enabled makes the second request a local hit
        # (need_to_load=0), which bypasses layerwise materialization entirely.
        "enable_prefix_caching": False,
        "compilation_config": {"cudagraph_mode": "FULL_AND_PIECEWISE"},
        "kv_transfer_config": {
            "kv_connector": "AscendStoreConnector",
            "kv_role": "kv_both",
            "kv_connector_extra_config": {
                "backend": "memcache",
                "use_layerwise": use_layerwise,
                "layerwise_prefetch_layers": prefetch_layers,
            },
        },
    }
    if torch_profile_dir is not None:
        llm_kwargs["profiler_config"] = {
            "profiler": "torch",
            "torch_profiler_dir": str(torch_profile_dir),
            "torch_profiler_with_stack": False,
            "torch_profiler_with_memory": False,
        }
    llm = LLM(**llm_kwargs)

    params = SamplingParams(max_tokens=max_tokens, temperature=0)
    # Warmup: compute and store the shared prefix KV so the following requests
    # hit the prefix cache and exercise the per-layer LOAD path.
    llm.generate([SHARED_PREFIX], SamplingParams(max_tokens=1, temperature=0), use_tqdm=False)
    if torch_profile_dir is not None:
        # Do not collect model load or cache population: M0 needs only the
        # materialization/replay interval.  The profiler's device trace is the
        # source of truth for transfer--compute overlap; its wall time is not a
        # performance datapoint.
        torch_profile_dir.mkdir(parents=True, exist_ok=True)
        llm.start_profile(profile_prefix="wavemat_m0")
    try:
        started = time.time()
        outputs = llm.generate(prompts, params, use_tqdm=False)
        wall_s = time.time() - started
    finally:
        if torch_profile_dir is not None:
            llm.stop_profile()
    return {
        "model": model,
        "use_layerwise": use_layerwise,
        "layerwise_prefetch_layers": prefetch_layers,
        "max_tokens": max_tokens,
        "tensor_parallel_size": tensor_parallel_size,
        "enforce_eager": enforce_eager,
        "vllm_prefix_caching_enabled": False,
        "torch_profile_dir": str(torch_profile_dir) if torch_profile_dir else None,
        "wall_clock_s": round(wall_s, 3),
        "num_prompts": len(prompts),
        "first_output": outputs[0].outputs[0].text[:160],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="WaveMat M0 overlap (shared-prefix reuse).")
    parser.add_argument(
        "--model",
        default="/root/models/DeepSeek-V2-Lite",
        help=(
            "Supported small MLA+MoE layerwise baseline available on this host."
        ),
    )
    parser.add_argument("--enforce-eager", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--use-layerwise", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--prefetch-layers", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.22)
    parser.add_argument(
        "--tensor-parallel-size",
        type=int,
        default=8,
        choices=[1, 2, 4, 8],
        help="Use TP=1 for the single-NPU M0 seam gate; larger values are optional.",
    )
    parser.add_argument(
        "--torch-profile-dir",
        type=Path,
        help="Optional Ascend PyTorch Profiler output directory (measurement only).",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    assert "MMC_LOCAL_CONFIG_PATH" in os.environ, "MMC_LOCAL_CONFIG_PATH required"
    result = run(
        args.model,
        args.use_layerwise,
        args.prefetch_layers,
        args.max_tokens,
        args.gpu_memory_utilization,
        args.tensor_parallel_size,
        args.enforce_eager,
        args.torch_profile_dir,
    )
    result["artifact"] = "m0-wavemat-overlap"
    result["is_wavemat_mechanism_enabled"] = False
    result["generated_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "wall_clock_s": result["wall_clock_s"]}))


if __name__ == "__main__":
    main()
