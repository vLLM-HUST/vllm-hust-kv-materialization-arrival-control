from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

EVIDENCE_LABEL = "real-online/m2-benefit-boundary"
POLICIES = ("always_recompute", "always_full_reuse", "controller")
ROUND_ORDERS = (
    POLICIES,
    ("controller", "always_recompute", "always_full_reuse"),
    ("always_full_reuse", "controller", "always_recompute"),
)
WORKLOADS = (
    ("shared_tool_scaffold_agent", 18.0, 128, "positive_candidate"),
    (
        "shared_scenario_multi_turn_knowledge_service",
        24.0,
        64,
        "fallback_or_no_gain_candidate",
    ),
)


@dataclass(frozen=True)
class RunSpec:
    workload: str
    policy_mode: str
    round_index: int
    order_index: int
    request_rate: float
    max_output_tokens: int
    boundary_role: str


def build_schedule() -> list[RunSpec]:
    schedule = []
    for workload, request_rate, max_output_tokens, boundary_role in WORKLOADS:
        for round_index, order in enumerate(ROUND_ORDERS, start=1):
            for order_index, policy_mode in enumerate(order, start=1):
                schedule.append(
                    RunSpec(
                        workload=workload,
                        policy_mode=policy_mode,
                        round_index=round_index,
                        order_index=order_index,
                        request_rate=request_rate,
                        max_output_tokens=max_output_tokens,
                        boundary_role=boundary_role,
                    )
                )
    return schedule


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the preregistered M2 three-policy online boundary matrix."
    )
    parser.add_argument("--suite-dir", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--carrier-root", default="vendor/vllm")
    parser.add_argument("--device", type=int, default=7)
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--block-size", type=int, default=128)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    suite_dir = Path(args.suite_dir).resolve()
    if suite_dir.is_relative_to(repo_root):
        raise SystemExit(
            "suite-dir must be outside the worktree; import the validated suite later"
        )
    if suite_dir.exists():
        raise SystemExit(f"refusing to overwrite suite directory: {suite_dir}")
    suite_dir.mkdir(parents=True)

    schedule = build_schedule()
    execution: dict[str, object] = {
        "schema_version": 2,
        "study": "M2 three-action online benefit boundary",
        "evidence_label": EVIDENCE_LABEL,
        "started_at_s": time.time(),
        "preregistration": {
            "unit": "independently restarted service lifecycle",
            "matched_block": "workload x round",
            "rounds": 3,
            "treatment": list(POLICIES),
            "seam": "segmented",
            "condition": "tuned",
            "positive_candidate": "shared_tool_scaffold_agent",
            "fallback_or_no_gain_candidate": (
                "shared_scenario_multi_turn_knowledge_service"
            ),
            "primary_metrics": [
                "mean_ttft_ms",
                "mean_latency_ms",
                "request_throughput_rps",
            ],
            "stopping_rule": (
                "Run exactly three temporally blocked rounds. Do not tune by "
                "workload. If controller does not beat the best fixed policy, "
                "record the negative result and stop."
            ),
        },
        "schedule": [asdict(spec) for spec in schedule],
        "runs": [],
    }
    manifest_path = suite_dir / "suite_manifest.json"
    write_json(manifest_path, execution)

    for sequence, spec in enumerate(schedule, start=1):
        run_dir = (
            suite_dir
            / spec.workload
            / spec.policy_mode
            / f"round_{spec.round_index:02d}_sequence_{sequence:02d}"
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
            validation_path = run_dir / "validation.json"
            validation = subprocess.run(
                [
                    sys.executable,
                    "paper/kv_materialization_control/experiments/validate_online_bundle.py",
                    str(run_dir),
                    "--output",
                    str(validation_path),
                    "--expected-evidence-label",
                    EVIDENCE_LABEL,
                ],
                cwd=repo_root,
                check=False,
            )
            record["validation_returncode"] = validation.returncode
            if validation.returncode != 0:
                result = validation
        execution["runs"].append(record)
        write_json(manifest_path, execution)
        if result.returncode == 3:
            execution["status"] = "blocked"
            break
        if result.returncode != 0:
            execution["status"] = "failed"
            break
    else:
        execution["status"] = "completed"

    execution["finished_at_s"] = time.time()
    write_json(manifest_path, execution)
    return 0 if execution["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
