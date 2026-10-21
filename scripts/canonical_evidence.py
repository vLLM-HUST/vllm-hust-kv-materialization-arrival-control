"""Resolve historical asset identities without modifying archived attestations."""

import json
from pathlib import Path
from urllib.parse import urlparse

REGISTRY = json.loads(
    (Path(__file__).resolve().parents[1] / "EVIDENCE_SOURCES.json").read_text()
)


def canonical_asset_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com":
        raise ValueError("Unrecognized evidence API origin")
    for asset in REGISTRY["assets"]:
        if parsed.path in {
            f"/repos/intellistream/kv-materialization-arrival-control/releases/assets/{asset['source_id']}",
            f"/repos/vLLM-HUST/vllm-hust-kv-materialization-arrival-control/releases/assets/{asset['source_id']}",
            f"/repos/{REGISTRY['repository']}/releases/assets/{asset['destination_id']}",
        }:
            return f"https://api.github.com/repos/{REGISTRY['repository']}/releases/assets/{asset['destination_id']}"
    raise ValueError("Evidence asset is not in the verified custody registry")
