from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def run_layerwise_smoke(
    model: str,
    tensor_parallel_size: int,
    max_model_len: int,
    gpu_memory_utilization: float,
    prefetch_layers: int,
    enforce_eager: bool,
) -> dict[str, Any]:
    from vllm import LLM, SamplingParams

    started = time.time()
    llm = LLM(
        model=model,
        trust_remote_code=True,
        enforce_eager=enforce_eager,
        max_model_len=max_model_len,
        max_num_seqs=1,
        gpu_memory_utilization=gpu_memory_utilization,
        tensor_parallel_size=tensor_parallel_size,
        quantization="ascend",
        disable_log_stats=True,
        kv_transfer_config={
            "kv_connector": "AscendStoreConnector",
            "kv_role": "kv_both",
            "kv_connector_extra_config": {
                "backend": "memcache",
                "mooncake_rpc_port": "0",
                "use_layerwise": True,
                "layerwise_prefetch_layers": prefetch_layers,
            },
        },
    )
    output = llm.generate(
        ["Hello, world!"],
        SamplingParams(max_tokens=4, temperature=0),
    )[0]
    elapsed_s = time.time() - started
    return {
        "model": model,
        "tensor_parallel_size": tensor_parallel_size,
        "max_model_len": max_model_len,
        "gpu_memory_utilization": gpu_memory_utilization,
        "enforce_eager": enforce_eager,
        "layerwise_prefetch_layers": prefetch_layers,
        "prompt": output.prompt,
        "generated_text": output.outputs[0].text,
        "elapsed_s": round(elapsed_s, 3),
    }


def build_manifest(evidence: dict[str, Any]) -> dict[str, Any]:
    generated = bool(evidence.get("generated_text"))
    return {
        "artifact": "m3-wavemat-ascend-store-layerwise-smoke",
        "evidence_class": "ascend_store_layerwise_smoke",
        "is_end_to_end_performance_evidence": False,
        "is_wavemat_mechanism_enabled": False,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "layerwise_evidence": evidence,
        "all_smoke_checks_pass": generated,
        "claim": (
            "AscendStoreConnector was configured with backend=memcache and "
            "use_layerwise=true for a real NPU run. This is a layerwise runtime "
            "smoke, not an M0 overlap/gap result."
        ),
    }


def write_outputs(
    evidence: dict[str, Any],
    output_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    manifest = build_manifest(evidence)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an AscendStore layerwise NPU smoke."
    )
    parser.add_argument(
        "--model",
        default="/data/shared_datasets/models/DeepSeek-V4-Flash-W8A8",
        help="MLA/SFA/DSA model path.",
    )
    parser.add_argument("--tensor-parallel-size", type=int, default=8)
    parser.add_argument("--max-model-len", type=int, default=128)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.65)
    parser.add_argument("--prefetch-layers", type=int, default=1)
    parser.add_argument(
        "--enforce-eager",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Start in eager mode; use --no-enforce-eager for graph mode.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/wavemat/results/m3_ascend_store_layerwise_smoke_raw.json"),
        help="Raw layerwise smoke output path.",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=Path("docs/wavemat/M3_ASCEND_STORE_LAYERWISE_SMOKE_MANIFEST.json"),
        help="Machine-readable manifest path.",
    )
    args = parser.parse_args()

    evidence = run_layerwise_smoke(
        args.model,
        args.tensor_parallel_size,
        args.max_model_len,
        args.gpu_memory_utilization,
        args.prefetch_layers,
        args.enforce_eager,
    )
    manifest = write_outputs(evidence, args.output, args.manifest_output)
    print(f"wrote {args.output}")
    print(f"wrote {args.manifest_output}")
    print(f"all_smoke_checks_pass={manifest['all_smoke_checks_pass']}")


if __name__ == "__main__":
    main()
