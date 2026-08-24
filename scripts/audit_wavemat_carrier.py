from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


def _git_rev(root: Path) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _check_file(
    root: Path,
    rel_path: str,
    needles: list[str],
) -> dict[str, Any]:
    path = root / rel_path
    if not path.is_file():
        return {
            "path": rel_path,
            "found": False,
            "detail": "missing file",
            "needles": needles,
            "matched": [],
        }

    text = path.read_text(encoding="utf-8")
    matched: list[dict[str, Any]] = []
    for needle in needles:
        lines = [i + 1 for i, line in enumerate(text.splitlines()) if needle in line]
        matched.append(
            {
                "needle": needle,
                "lines": lines,
                "found": bool(lines),
            }
        )
    return {
        "path": rel_path,
        "found": True,
        "detail": "present",
        "needles": needles,
        "matched": matched,
    }


def _carrier_checks(root: Path) -> list[dict[str, Any]]:
    specs = [
        (
            "kv_connector_v1_base",
            "vllm/distributed/kv_transfer/kv_connector/v1/base.py",
            [
                "class KVConnectorBase_V1(ABC):",
                "def wait_for_layer_load(self, layer_name: str) -> None:",
                "def save_kv_layer(",
                "def requires_piecewise_for_cudagraph(cls, extra_config: dict[str, Any]) -> bool:",
            ],
        ),
        (
            "attention_layerwise_decorator",
            "vllm/model_executor/layers/attention/kv_transfer_utils.py",
            ["def maybe_transfer_kv_layer(func: Callable) -> Callable:"],
        ),
        (
            "attention_consume_non_mla",
            "vllm/model_executor/layers/attention/attention.py",
            [
                "@eager_break_during_capture",
                "@maybe_transfer_kv_layer",
                "def unified_attention_with_output(",
            ],
        ),
        (
            "attention_consume_mla",
            "vllm/model_executor/layers/attention/mla_attention.py",
            [
                "@eager_break_during_capture",
                "@maybe_transfer_kv_layer",
                "def unified_mla_attention_with_output(",
            ],
        ),
        (
            "lmcache_layerwise_connector",
            "vllm/distributed/kv_transfer/kv_connector/v1/lmcache_connector.py",
            [
                "class LMCacheConnectorV1(KVConnectorBase_V1):",
                'return extra_config.get("use_layerwise", False)',
                "def wait_for_layer_load(self, layer_name: str) -> None:",
                "def save_kv_layer(",
            ],
        ),
        (
            "graph_mode_override",
            "vllm/config/vllm.py",
            [
                "KV connector %s requires PIECEWISE CUDA graph mode",
                "self.compilation_config.cudagraph_mode = CUDAGraphMode.PIECEWISE",
            ],
        ),
        (
            "breakable_graph_capture",
            "vllm/compilation/breakable_cudagraph.py",
            [
                "def eager_break_during_capture(fn: F) -> F:",
                "class BreakableCUDAGraphCapture:",
                "wait_for_layer_load",
            ],
        ),
        (
            "worker_connector_lifecycle",
            "vllm/v1/worker/kv_connector_model_runner_mixin.py",
            [
                "class KVConnectorModelRunnerMixin:",
                "kv_connector.start_load_kv(get_forward_context())",
                "kv_connector.wait_for_save()",
            ],
        ),
    ]

    results: list[dict[str, Any]] = []
    for name, rel_path, needles in specs:
        check = _check_file(root, rel_path, needles)
        results.append(
            {
                "case": name,
                "found": check["found"] and all(m["found"] for m in check["matched"]),
                "path": check["path"],
                "matched": check["matched"],
            }
        )
    return results


def _ascend_checks(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        return [
            {
                "case": "ascend_source_available",
                "found": False,
                "path": str(root),
                "detail": "vllm-ascend root not present; ascend checks skipped",
            }
        ]

    specs = [
        (
            "ascend_store_connector",
            "vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/ascend_store_connector.py",
            [
                "class AscendStoreConnector(KVConnectorBase_V1, SupportsHMA):",
                "def requires_piecewise_for_cudagraph(cls, extra_config: dict[str, Any]) -> bool:",
                'return extra_config.get("use_layerwise", False)',
                "def wait_for_layer_load(self, layer_name: str) -> None:",
                "def save_kv_layer(",
            ],
        ),
        (
            "ascend_attention_consume",
            "vllm_ascend/attention/utils.py",
            [
                "def wait_for_kv_layer_from_connector(layer_name: str):",
                "def maybe_save_kv_layer_to_connector(",
                "connector.wait_for_layer_load(layer_name)",
                "connector.save_kv_layer(layer_name, kv_cache_layer, attn_metadata)",
            ],
        ),
        (
            "ascend_pool_worker_prefetch",
            "vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/pool_worker.py",
            [
                'self.num_prefetch_layers = int(self._extra_config.get("layerwise_prefetch_layers", 1))',
                "def wait_for_layer_load(self) -> None:",
                "def save_kv_layer(self, connector_metadata: AscendConnectorMetadata) -> None:",
                "layer_load_finished_events",
                "layer_save_finished_events",
            ],
        ),
        (
            "ascend_acl_graph",
            "vllm_ascend/compilation/acl_graph.py",
            [
                "class ACLGraphWrapper:",
                "torch.npu.NPUGraph()",
                "def __call__(self, *args, **kwargs):",
                "entry.aclgraph.replay()",
            ],
        ),
    ]

    results: list[dict[str, Any]] = []
    for name, rel_path, needles in specs:
        check = _check_file(root, rel_path, needles)
        results.append(
            {
                "case": name,
                "found": check["found"] and all(m["found"] for m in check["matched"]),
                "path": check["path"],
                "matched": check["matched"],
            }
        )
    return results


def build_manifest(
    carrier_root: Path,
    ascend_root: Path,
    carrier_checks: list[dict[str, Any]],
    ascend_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    carrier_rev = _git_rev(carrier_root)
    ascend_rev = _git_rev(ascend_root) if ascend_root.is_dir() else None
    all_checks = carrier_checks + ascend_checks
    passed = all(item["found"] for item in all_checks)
    return {
        "artifact": "m3-wavemat-seam-gate-carrier-audit",
        "evidence_class": "carrier_audit_static",
        "is_end_to_end_performance_evidence": False,
        "is_wavemat_mechanism_enabled": False,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "carrier_vendor_vllm_commit": carrier_rev,
        "carrier_expected_commit": "68b8be04493d39d5706f3d0d18f465f5eab947c4",
        "vllm_ascend_commit": ascend_rev,
        "vllm_ascend_is_vendored": False,
        "carrier_checks": carrier_checks,
        "ascend_checks": ascend_checks,
        "all_static_checks_pass": passed,
        "claim": (
            "Static source audit confirms the pinned vendor/vllm carrier exposes "
            "KVConnector V1 layerwise load/consume seams and forces layerwise "
            "connectors to PIECEWISE graph mode; upstream vllm-ascend exposes "
            "AscendStoreConnector layerwise wait/save/prefetch and ACLGraph. "
            "This is not a 910B2 runtime trace and does not establish a graph "
            "induced gap or its absence."
        ),
    }


def write_outputs(
    carrier_root: Path,
    ascend_root: Path,
    output_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    carrier_checks = _carrier_checks(carrier_root)
    ascend_checks = _ascend_checks(ascend_root)
    manifest = build_manifest(carrier_root, ascend_root, carrier_checks, ascend_checks)
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
        description="Static WaveMat M0 carrier/seam audit."
    )
    parser.add_argument(
        "--carrier-root",
        type=Path,
        default=Path("vendor/vllm"),
        help="Pinned vendor/vllm checkout.",
    )
    parser.add_argument(
        "--ascend-root",
        type=Path,
        default=Path("/tmp/wavemat-vllm-ascend"),
        help="Optional vllm-ascend checkout for upstream path audit.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/wavemat/results/m3_carrier_audit_raw.json"),
        help="Raw audit output path.",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=Path("docs/wavemat/M3_CARRIER_AUDIT_MANIFEST.json"),
        help="Machine-readable manifest path.",
    )
    args = parser.parse_args()

    manifest = write_outputs(
        args.carrier_root,
        args.ascend_root,
        args.output,
        args.manifest_output,
    )
    print(f"wrote {args.output}")
    print(f"wrote {args.manifest_output}")
    print(f"all_static_checks_pass={manifest['all_static_checks_pass']}")


if __name__ == "__main__":
    main()
