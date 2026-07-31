from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunSpec:
    workload: str
    seam: str
    condition: str
    round_index: int
    order_index: int
    request_rate: float
    max_output_tokens: int


ROUND_ORDERS = (
    (
        ("old", "baseline"),
        ("segmented", "baseline"),
        ("old", "tuned"),
        ("segmented", "tuned"),
    ),
    (
        ("segmented", "tuned"),
        ("old", "tuned"),
        ("segmented", "baseline"),
        ("old", "baseline"),
    ),
    (
        ("old", "tuned"),
        ("old", "baseline"),
        ("segmented", "tuned"),
        ("segmented", "baseline"),
    ),
)
WORKLOADS = (
    ("shared_scenario_multi_turn_knowledge_service", 24.0, 64),
    ("shared_tool_scaffold_agent", 18.0, 128),
)


def build_schedule() -> list[RunSpec]:
    schedule: list[RunSpec] = []
    for workload, request_rate, max_output_tokens in WORKLOADS:
        for round_index, order in enumerate(ROUND_ORDERS, start=1):
            for order_index, (seam, condition) in enumerate(order, start=1):
                schedule.append(
                    RunSpec(
                        workload,
                        seam,
                        condition,
                        round_index,
                        order_index,
                        request_rate,
                        max_output_tokens,
                    )
                )
    for round_index in range(1, 4):
        schedule.append(
            RunSpec(
                "dynamic_rag_corpus_update",
                "segmented",
                "tuned",
                round_index,
                1,
                18.0,
                72,
            )
        )
    return schedule


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute the fixed M1 online matrix with independent services."
    )
    parser.add_argument("--suite-dir", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--old-carrier-root", required=True)
    parser.add_argument("--segmented-carrier-root", default="vendor/vllm")
    parser.add_argument("--device", type=int, default=7)
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--block-size", type=int, default=128)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    suite_dir = Path(args.suite_dir).resolve()
    if suite_dir.exists():
        raise SystemExit(f"refusing to overwrite suite directory: {suite_dir}")
    suite_dir.mkdir(parents=True)
    schedule = build_schedule()
    execution: dict[str, object] = {
        "schema_version": 1,
        "started_at_s": time.time(),
        "schedule": [spec.__dict__ for spec in schedule],
        "runs": [],
    }
    execution_path = suite_dir / "suite_execution.json"

    for sequence, spec in enumerate(schedule, start=1):
        condition_label = f"{spec.seam}_{spec.condition}"
        run_dir = (
            suite_dir
            / spec.workload
            / condition_label
            / f"round_{spec.round_index:02d}_sequence_{sequence:02d}"
        )
        carrier_root = (
            args.old_carrier_root if spec.seam == "old" else args.segmented_carrier_root
        )
        command = [
            sys.executable,
            "paper/kv_materialization_control/experiments/run_online_lifecycle.py",
            "--bundle-dir",
            str(run_dir),
            "--workload-case",
            spec.workload,
            "--condition",
            spec.condition,
            "--seam",
            spec.seam,
            "--carrier-root",
            carrier_root,
            "--model",
            args.model,
            "--device",
            str(args.device),
            "--port",
            str(args.port),
            "--block-size",
            str(args.block_size),
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
            "real-online/formal-matrix",
        ]
        result = subprocess.run(command, cwd=repo_root, check=False)
        run_record = {
            "sequence": sequence,
            "spec": spec.__dict__,
            "bundle_dir": str(run_dir),
            "returncode": result.returncode,
        }
        if result.returncode == 0:
            validation_path = run_dir / "validation.json"
            validation = subprocess.run(
                [
                    sys.executable,
                    "paper/kv_materialization_control/experiments/validate_online_bundle.py",
                    str(run_dir),
                    "--output",
                    str(validation_path),
                    "--expected-evidence-label",
                    "real-online/formal-matrix",
                ],
                cwd=repo_root,
                check=False,
            )
            run_record["validation_returncode"] = validation.returncode
            if validation.returncode != 0:
                (run_dir / "FAILED.txt").write_text(
                    "Bundle validation failed after lifecycle completion. See validation.json.\n",
                    encoding="utf-8",
                )
                result = validation
        execution["runs"].append(run_record)
        execution_path.write_text(
            json.dumps(execution, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if result.returncode == 3:
            execution["status"] = "blocked"
            break
        if result.returncode != 0:
            execution["status"] = "failed"
            break
    else:
        execution["status"] = "completed"

    execution["finished_at_s"] = time.time()
    execution_path.write_text(
        json.dumps(execution, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if execution["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
