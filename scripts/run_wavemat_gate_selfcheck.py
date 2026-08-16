from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT / "src" / "vllm_kv_materialization" / "wavemat_seam_gate.py"
)


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("wavemat_seam_gate", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate WaveMat M0 host-side seam-gate raw results."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/wavemat/results/m3_pr1_seam_gate_raw.json"),
        help="Output JSON path for raw fixture results.",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=Path("docs/wavemat/M3_PR1_MANIFEST.json"),
        help="Output JSON path for the machine-readable PR manifest.",
    )
    parser.add_argument(
        "--parent-commit",
        default="375d3a8a10610e13d3ca1f46d0046f0a7282373e",
        help="Parent repository commit recorded in the manifest.",
    )
    parser.add_argument(
        "--carrier-gitlink",
        default="68b8be04493d39d5706f3d0d18f465f5eab947c4",
        help="vendor/vllm gitlink recorded at parent HEAD.",
    )
    args = parser.parse_args()

    gate_module = _load_gate_module()
    write_raw_results = gate_module.write_raw_results
    manifest = write_raw_results(
        args.output,
        args.parent_commit,
        args.carrier_gitlink,
    )
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output}")
    print(f"wrote {args.manifest_output}")
    print(
        "failure_injection_cases_pass="
        f"{manifest['all_failure_injection_cases_pass']}"
    )


if __name__ == "__main__":
    main()
