from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

EVIDENCE_LABEL = "real-online/m2-candidate-pilot"
POLICIES = ("always_recompute", "always_full_reuse", "controller")
CANDIDATES = (
    ("shared_async_document_pipeline", 18.0, 96),
    ("shared_public_sharegpt_boundary", 24.0, 64),
)


@dataclass(frozen=True)
class RunSpec:
    workload: str
    policy_mode: str
    request_rate: float
    max_output_tokens: int


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def build_schedule() -> list[RunSpec]:
    orders = (
        ("controller", "always_full_reuse", "always_recompute"),
        ("always_recompute", "controller", "always_full_reuse"),
    )
    return [
        RunSpec(workload, policy, request_rate, max_output_tokens)
        for (workload, request_rate, max_output_tokens), order in zip(
            CANDIDATES, orders, strict=True
        )
        for policy in order
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the preregistered M2 pilot.")
    parser.add_argument("--suite-dir", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--carrier-root", default="vendor/vllm")
    parser.add_argument("--device", type=int, default=7)
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    suite_dir = Path(args.suite_dir).resolve()
    if suite_dir.is_relative_to(repo_root):
        raise SystemExit("suite-dir must be outside the worktree")
    if suite_dir.exists():
        raise SystemExit(f"refusing to overwrite suite directory: {suite_dir}")
    suite_dir.mkdir(parents=True)

    schedule = build_schedule()
    suite: dict[str, object] = {
        "schema_version": 1,
        "study": "M2 preregistered positive-candidate pilot",
        "evidence_label": EVIDENCE_LABEL,
        "started_at_s": time.time(),
        "promotion_gate": {
            "controller_vs_best_fixed_ttft_pct_max": 2.0,
            "controller_vs_best_fixed_e2e_pct_max": 5.0,
            "controller_vs_best_fixed_throughput_pct_min": -5.0,
        },
        "schedule": [asdict(spec) for spec in schedule],
        "runs": [],
    }
    manifest = suite_dir / "suite_manifest.json"
    write_json(manifest, suite)

    for sequence, spec in enumerate(schedule, start=1):
        run_dir = (
            suite_dir
            / spec.workload
            / spec.policy_mode
            / f"pilot_sequence_{sequence:02d}"
        )
        command = [
            sys.executable,
            "paper/kv_materialization_control/experiments/run_online_lifecycle.py",
            "--bundle-dir",
            str(run_dir),
            "--workload-case",
            spec.workload,
            "--condition",
            "tuned",
            "--policy-mode",
            spec.policy_mode,
            "--seam",
            "segmented",
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
            str(spec.request_rate),
            "--concurrency",
            "4",
            "--max-output-tokens",
            str(spec.max_output_tokens),
            "--seed",
            "7",
            "--evidence-label",
            EVIDENCE_LABEL,
        ]
        result = subprocess.run(command, cwd=repo_root, check=False)
        record = {
            "sequence": sequence,
            "spec": asdict(spec),
            "bundle_dir": str(run_dir),
            "returncode": result.returncode,
        }
        if result.returncode == 0:
            validation = subprocess.run(
                [
                    sys.executable,
                    "paper/kv_materialization_control/experiments/validate_online_bundle.py",
                    str(run_dir),
                    "--output",
                    str(run_dir / "validation.json"),
                    "--expected-evidence-label",
                    EVIDENCE_LABEL,
                ],
                cwd=repo_root,
                check=False,
            )
            record["validation_returncode"] = validation.returncode
            if validation.returncode != 0:
                result = validation
        suite["runs"].append(record)
        write_json(manifest, suite)
        if result.returncode != 0:
            suite["status"] = "blocked" if result.returncode == 3 else "failed"
            break
    else:
        suite["status"] = "completed"

    suite["finished_at_s"] = time.time()
    write_json(manifest, suite)
    return 0 if suite["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
