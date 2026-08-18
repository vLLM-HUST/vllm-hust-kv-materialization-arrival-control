from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def _module_version(module: Any) -> str:
    return str(getattr(module, "__version__", "unknown"))


def collect_device_evidence() -> dict[str, Any]:
    import torch
    import torch_npu

    return {
        "torch_version": _module_version(torch),
        "torch_npu_version": _module_version(torch_npu),
        "npu_available": torch.npu.is_available(),
        "npu_device_count": torch.npu.device_count() if torch.npu.is_available() else 0,
    }


def run_generation(model: str) -> dict[str, Any]:
    from vllm import LLM, SamplingParams

    started = time.time()
    llm = LLM(
        model=model,
        trust_remote_code=True,
        enforce_eager=False,
        max_model_len=256,
        max_num_seqs=2,
        gpu_memory_utilization=0.45,
        disable_log_stats=True,
        compilation_config={"cudagraph_mode": "FULL_AND_PIECEWISE"},
    )
    output = llm.generate(
        ["Hello, world!"],
        SamplingParams(max_tokens=8, temperature=0),
    )[0]
    elapsed_s = time.time() - started
    return {
        "model": model,
        "prompt": output.prompt,
        "generated_text": output.outputs[0].text,
        "elapsed_s": round(elapsed_s, 3),
        "graph_mode": "FULL_AND_PIECEWISE",
    }


def build_manifest(
    device_evidence: dict[str, Any],
    generation_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    generation_passed = generation_evidence is not None and bool(
        generation_evidence.get("generated_text")
    )
    return {
        "artifact": "m3-wavemat-npu-graph-smoke",
        "evidence_class": "npu_graph_smoke",
        "is_end_to_end_performance_evidence": False,
        "is_wavemat_mechanism_enabled": False,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device_evidence": device_evidence,
        "generation_evidence": generation_evidence,
        "all_smoke_checks_pass": device_evidence["npu_available"]
        and device_evidence["npu_device_count"] > 0
        and generation_passed,
        "claim": (
            "Ascend NPU is available and vLLM Ascend completed one graph-mode "
            "(FULL_AND_PIECEWISE) offline generation. This is an environment "
            "readiness smoke, not an M0 overlap/gap result."
        ),
    }


def write_outputs(
    output_path: Path,
    manifest_path: Path,
    device_evidence: dict[str, Any],
    generation_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    manifest = build_manifest(device_evidence, generation_evidence)
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
        description="WaveMat M0 NPU graph-mode readiness smoke."
    )
    parser.add_argument(
        "--model",
        default="/data/shared_datasets/models/Qwen2.5-3B-Instruct",
        help="Model path for the graph-mode generation smoke.",
    )
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Only collect NPU device evidence, skip vLLM generation.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/wavemat/results/m3_npu_graph_smoke_raw.json"),
        help="Raw smoke output path.",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=Path("docs/wavemat/M3_NPU_GRAPH_SMOKE_MANIFEST.json"),
        help="Machine-readable manifest path.",
    )
    args = parser.parse_args()

    device_evidence = collect_device_evidence()
    generation_evidence = None if args.skip_generation else run_generation(args.model)
    manifest = write_outputs(
        args.output,
        args.manifest_output,
        device_evidence,
        generation_evidence,
    )
    print(f"wrote {args.output}")
    print(f"wrote {args.manifest_output}")
    print(f"all_smoke_checks_pass={manifest['all_smoke_checks_pass']}")


if __name__ == "__main__":
    main()
