import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "canonical", ROOT / "scripts/canonical_evidence.py"
)
canonical = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canonical)


def test_all_wavemat_original_ids_resolve_without_rewriting_attestation():
    manifest = json.loads(
        (ROOT / "docs/wavemat/results/m0_raw_provenance_20260824_v1.json").read_text()
    )
    assets = [a["raw"] for a in manifest["arms"]] + manifest["gate_trace_analyzer"][
        "assets"
    ]
    for asset in assets:
        resolved = canonical.canonical_asset_url(asset["url"])
        assert "/vLLM-HUST/vllm-hust-benchmark/" in resolved
        registered = next(
            a
            for a in canonical.REGISTRY["assets"]
            if resolved.endswith(f"/{a['destination_id']}")
        )
        assert registered["digest"] == "sha256:" + asset["compressed_sha256"]
        assert registered["bytes"] == asset["compressed_bytes"]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/asset",
        "https://api.github.com/repos/unknown/releases/assets/1",
    ],
)
def test_unknown_origins_and_ids_rejected(url):
    with pytest.raises(ValueError):
        canonical.canonical_asset_url(url)
