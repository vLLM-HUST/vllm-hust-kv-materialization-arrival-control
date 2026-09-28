#!/usr/bin/env python3
"""Audit whether a KV connector exposes the raw signals required by G0.

This is deliberately a static gate.  It never infers queue or transfer values
from wall-clock logs: a missing native export is a G0 Stop condition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit(path: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connector", required=True, type=Path)
    parser.add_argument("--pool-worker", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    connector = args.connector.resolve()
    worker = args.pool_worker.resolve()
    repo_root = args.repo_root.resolve()
    if not connector.is_file() or not worker.is_file():
        raise SystemExit("connector and pool-worker paths must be readable files")
    connector_text, worker_text = connector.read_text(), worker.read_text()
    checks = {
        "connector_stats_export": "def get_kv_connector_stats" in connector_text,
        "load_hook": "def start_load_kv" in connector_text,
        "layer_ready_hook": "def wait_for_layer_load" in connector_text,
        "queue_exists": "request_queue" in worker_text,
        "queue_depth_export": ".qsize()" in worker_text,
        "in_flight_bytes_export": "bytes_in_flight" in connector_text + worker_text,
        "per_request_transfer_export": "request_id" in connector_text + worker_text,
    }
    required_exports = ("connector_stats_export", "queue_depth_export", "in_flight_bytes_export", "per_request_transfer_export")
    missing = [name for name in required_exports if not checks[name]]
    payload = {
        "schema_version": 1,
        "artifact": "g0-materialization-telemetry-seam-audit",
        "repository": {
            "parent_commit": git_commit(repo_root),
            "vendor_vllm_gitlink": git_commit(repo_root / "vendor" / "vllm"),
        },
        "connector": {"path": str(connector), "sha256": sha256(connector), "git_commit": git_commit(connector.parent)},
        "pool_worker": {"path": str(worker), "sha256": sha256(worker), "git_commit": git_commit(worker.parent)},
        "checks": checks,
        "required_exports": list(required_exports),
        "missing_required_exports": missing,
        "verdict": "telemetry_unavailable_stop" if missing else "telemetry_contract_present",
        "interpretation": (
            "The connector has internal execution hooks but does not export the raw "
            "materialization counters needed to separate congestion from generic queueing."
            if missing
            else "Static API presence only; runtime activation still must be verified."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
