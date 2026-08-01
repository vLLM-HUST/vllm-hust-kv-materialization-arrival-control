from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a protocol-identical old/segmented carrier-validation pair."
    )
    parser.add_argument("--suite-dir", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--carrier-root", default="vendor/vllm")
    parser.add_argument("--device", type=int, default=7)
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    suite_dir = Path(args.suite_dir).resolve()
    if suite_dir.is_relative_to(repo_root):
        raise SystemExit("paired suite-dir must be outside the parent worktree")
    if suite_dir.exists():
        raise SystemExit(f"refusing to overwrite paired suite: {suite_dir}")
    suite_dir.mkdir(parents=True)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "status": "running",
        "started_at_s": time.time(),
        "suite_command": [sys.executable, *sys.argv],
        "workload": "shared_scenario_multi_turn_knowledge_service",
        "condition": "baseline",
        "runs": [],
    }
    manifest_path = suite_dir / "paired_suite_manifest.json"
    write_json(manifest_path, manifest)

    for sequence, seam in enumerate(("old", "segmented"), start=1):
        run_dir = suite_dir / f"{sequence:02d}_{seam}_baseline"
        lifecycle_command = [
            sys.executable,
            "paper/kv_materialization_control/experiments/run_online_lifecycle.py",
            "--bundle-dir",
            str(run_dir),
            "--workload-case",
            "shared_scenario_multi_turn_knowledge_service",
            "--condition",
            "baseline",
            "--seam",
            seam,
            "--carrier-root",
            args.carrier_root,
            "--model",
            args.model,
            "--device",
            str(args.device),
            "--port",
            str(args.port),
            "--block-size",
            "128",
            "--max-model-len",
            "32768",
            "--request-rate",
            "24",
            "--concurrency",
            "4",
            "--max-output-tokens",
            "64",
            "--seed",
            "7",
            "--evidence-label",
            "real-online/carrier-validation-dry-run",
        ]
        lifecycle = subprocess.run(lifecycle_command, cwd=repo_root, check=False)
        record: dict[str, object] = {
            "sequence": sequence,
            "seam": seam,
            "bundle_dir": str(run_dir),
            "lifecycle_command": lifecycle_command,
            "lifecycle_returncode": lifecycle.returncode,
        }
        if lifecycle.returncode == 0:
            validation_path = run_dir / "validation.json"
            validation_command = [
                sys.executable,
                "paper/kv_materialization_control/experiments/validate_online_bundle.py",
                str(run_dir),
                "--output",
                str(validation_path),
                "--expected-evidence-label",
                "real-online/carrier-validation-dry-run",
                "--require-realized-partial",
            ]
            validation = subprocess.run(validation_command, cwd=repo_root, check=False)
            record["validation_command"] = validation_command
            record["validation_returncode"] = validation.returncode
        runs = manifest["runs"]
        assert isinstance(runs, list)
        runs.append(record)
        write_json(manifest_path, manifest)
        if lifecycle.returncode != 0 or record.get("validation_returncode") != 0:
            manifest["status"] = "blocked" if lifecycle.returncode == 3 else "failed"
            manifest["finished_at_s"] = time.time()
            write_json(manifest_path, manifest)
            return 1

    environments = [
        json.loads(
            (
                suite_dir / f"{index:02d}_{seam}_baseline/environment_manifest.json"
            ).read_text()
        )
        for index, seam in enumerate(("old", "segmented"), start=1)
    ]
    run_manifests = [
        json.loads(
            (suite_dir / f"{index:02d}_{seam}_baseline/run_manifest.json").read_text()
        )
        for index, seam in enumerate(("old", "segmented"), start=1)
    ]
    fingerprints = {row.get("protocol_fingerprint") for row in environments}
    lifecycle_ids = {row.get("service_lifecycle_id") for row in run_manifests}
    errors = []
    if len(fingerprints) != 1 or None in fingerprints:
        errors.append(f"protocol fingerprints differ: {sorted(map(str, fingerprints))}")
    if len(lifecycle_ids) != 2 or None in lifecycle_ids:
        errors.append("paired runs do not have two independent lifecycle IDs")
    manifest["protocol_fingerprint"] = next(iter(fingerprints), None)
    manifest["service_lifecycle_ids"] = sorted(map(str, lifecycle_ids))
    manifest["errors"] = errors
    manifest["status"] = "failed" if errors else "completed"
    manifest["finished_at_s"] = time.time()
    write_json(manifest_path, manifest)
    if errors:
        (suite_dir / "FAILED.txt").write_text("\n".join(errors) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
