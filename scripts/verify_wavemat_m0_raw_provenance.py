#!/usr/bin/env python3
"""Validate WaveMat M0 raw custody and rebuild all committed summaries.

This is deliberately an offline provenance check after download: it never starts
vLLM, MMC, or an Ascend workload. GitHub access is only required when assets
are not supplied locally.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from summarize_wavemat_m0_device_trace import summarize as summarize_device
from summarize_wavemat_m0_gate_trace import parse as summarize_gate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/wavemat/results/m0_raw_provenance_20260824_v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decompressed_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(summary: dict[str, Any], local_field: str) -> dict[str, Any]:
    return {key: value for key, value in summary.items() if key != local_field}


def get_asset(url: str, destination: Path, local_asset_dir: Path | None) -> None:
    if local_asset_dir is not None:
        source = local_asset_dir / destination.name
        if not source.is_file():
            raise FileNotFoundError(f"missing local asset: {source}")
        shutil.copyfile(source, destination)
        return
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required unless --asset-dir is supplied")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def check_asset(item: dict[str, Any], kind: str, workdir: Path, asset_dir: Path | None) -> Path:
    raw = item.get("raw", item)
    asset = workdir / f"{item['id']}.gz"
    get_asset(raw["url"], asset, asset_dir)
    expected_size = raw["compressed_bytes"]
    if asset.stat().st_size != expected_size:
        raise ValueError(f"{item['id']}: compressed size mismatch")
    if sha256(asset) != raw["compressed_sha256"]:
        raise ValueError(f"{item['id']}: compressed SHA-256 mismatch")
    if decompressed_sha256(asset) != raw["uncompressed_sha256"]:
        raise ValueError(f"{item['id']}: uncompressed SHA-256 mismatch")
    print(f"verified {kind}:{item['id']}")
    return asset


def expected_summary(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--asset-dir", type=Path, help="Directory containing <arm-or-gate-id>.gz files")
    parser.add_argument("--output", type=Path, help="Write machine-readable result JSON")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    results: dict[str, Any] = {"assets": [], "device_summaries": [], "gate_summaries": []}
    with tempfile.TemporaryDirectory(prefix="wavemat-m0-provenance-") as directory:
        workdir = Path(directory)
        for arm in manifest["arms"]:
            asset = check_asset(arm, "trace", workdir, args.asset_dir)
            trace = workdir / f"{arm['id']}.json"
            with gzip.open(asset, "rb") as source, trace.open("wb") as output:
                shutil.copyfileobj(source, output)
            actual = canonical(summarize_device(trace), "trace")
            expected = canonical(expected_summary(arm["summary"]), "trace")
            if actual != expected:
                raise ValueError(f"{arm['id']}: rebuilt device summary differs")
            results["assets"].append(arm["id"])
            results["device_summaries"].append(arm["id"])
        for gate in manifest["gate_trace_analyzer"]["assets"]:
            asset = check_asset(gate, "gate", workdir, args.asset_dir)
            log = workdir / f"{gate['id']}.log"
            with gzip.open(asset, "rb") as source, log.open("wb") as output:
                shutil.copyfileobj(source, output)
            actual = canonical(summarize_gate(log), "log")
            stem = gate["id"].removesuffix("_gate")
            expected = canonical(expected_summary(f"docs/wavemat/results/m0_gate_{stem.removeprefix('tp1_')}_summary.json"), "log")
            if actual != expected:
                raise ValueError(f"{gate['id']}: rebuilt gate summary differs")
            results["assets"].append(gate["id"])
            results["gate_summaries"].append(gate["id"])
    results["result"] = "pass"
    text = json.dumps(results, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, RuntimeError, ValueError, OSError, urllib.error.URLError) as error:
        print(f"provenance verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
