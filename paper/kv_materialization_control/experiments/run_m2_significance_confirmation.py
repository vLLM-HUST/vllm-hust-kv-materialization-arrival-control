from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

EVIDENCE_LABEL = "real-online/m2-significance-confirmation"
POLICIES = ("always_recompute", "always_full_reuse", "controller")
ROUND_ORDERS = (
    POLICIES,
    ("controller", "always_recompute", "always_full_reuse"),
    ("always_full_reuse", "controller", "always_recompute"),
    ("always_recompute", "controller", "always_full_reuse"),
    ("always_full_reuse", "always_recompute", "controller"),
)


@dataclass(frozen=True)
class RunSpec:
    round_index: int
    policy_mode: str


def build_schedule() -> list[RunSpec]:
    return [
        RunSpec(round_index, policy)
        for round_index, order in enumerate(ROUND_ORDERS, start=1)
        for policy in order
    ]


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a five-round significance confirmation for one promoted M2 workload."
    )
    parser.add_argument("--suite-dir", required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--request-rate", type=float, required=True)
    parser.add_argument("--max-output-tokens", type=int, required=True)
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
        "study": "M2 promoted-workload five-round significance confirmation",
        "evidence_label": EVIDENCE_LABEL,
        "workload": args.workload,
        "started_at_s": time.time(),
        "positive_rule": {
            "controller_vs_best_fixed_ttft_pct_mean_max": -5.0,
            "paired_ttft_delta_one_sided_95pct_upper_max": 0.0,
            "controller_vs_best_fixed_e2e_pct_mean_max": 5.0,
            "controller_vs_best_fixed_throughput_pct_mean_min": -5.0,
        },
        "schedule": [asdict(spec) for spec in schedule],
        "runs": [],
    }
    manifest = suite_dir / "suite_manifest.json"
    write_json(manifest, suite)

    for sequence, spec in enumerate(schedule, start=1):
        run_dir = (
            suite_dir
            / args.workload
            / spec.policy_mode
            / f"round_{spec.round_index:02d}_sequence_{sequence:02d}"
        )
        command = [
            sys.executable,
            "paper/kv_materialization_control/experiments/run_online_lifecycle.py",
            "--bundle-dir",
            str(run_dir),
            "--workload-case",
            args.workload,
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
            str(args.request_rate),
            "--concurrency",
            "4",
            "--max-output-tokens",
            str(args.max_output_tokens),
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
