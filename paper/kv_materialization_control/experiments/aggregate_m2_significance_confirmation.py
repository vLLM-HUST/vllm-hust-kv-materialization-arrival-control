from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from pathlib import Path

from paper.kv_materialization_control.experiments.run_m2_significance_confirmation import (
    EVIDENCE_LABEL,
    POLICIES,
)

ONE_SIDED_T_CRITICAL_95_DF4 = 2.131847


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_delta(value: float, baseline: float) -> float:
    if baseline == 0:
        raise ValueError("zero baseline")
    return 100.0 * (value / baseline - 1.0)


def one_sided_upper_95(values: list[float]) -> float:
    if len(values) != 5:
        raise ValueError("the preregistered confidence bound requires five rounds")
    return statistics.mean(values) + ONE_SIDED_T_CRITICAL_95_DF4 * (
        statistics.stdev(values) / math.sqrt(len(values))
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate M2 significance confirmation."
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    suite = read_json(input_dir / "suite_manifest.json")
    if (
        suite.get("status") != "completed"
        or suite.get("evidence_label") != EVIDENCE_LABEL
    ):
        raise ValueError("significance suite is not completed or has the wrong label")
    workload = str(suite["workload"])

    runs = []
    for validation_path in sorted(input_dir.rglob("validation.json")):
        bundle = validation_path.parent
        validation = read_json(validation_path)
        manifest = read_json(bundle / "run_manifest.json")
        summary = read_json(bundle / "request_summary.json")
        environment = read_json(bundle / "environment_manifest.json")
        match = re.search(r"round_(\d+)_", bundle.name)
        if not validation.get("valid") or match is None:
            raise ValueError(f"invalid confirmation bundle: {bundle}")
        runs.append(
            {
                "bundle": str(bundle.relative_to(input_dir)),
                "workload": manifest["workload_case"],
                "round": int(match.group(1)),
                "policy_mode": manifest["policy_mode"],
                "service_lifecycle_id": manifest["service_lifecycle_id"],
                "protocol_fingerprint": environment["protocol_fingerprint"],
                "requests": summary["requests"],
                "completed": summary["completed"],
                "mean_ttft_ms": summary["mean_ttft_ms"],
                "mean_latency_ms": summary["mean_latency_ms"],
                "request_throughput_rps": summary["request_throughput_rps"],
            }
        )

    expected = {
        (round_index, policy) for round_index in range(1, 6) for policy in POLICIES
    }
    actual = {(row["round"], row["policy_mode"]) for row in runs}
    ids = [row["service_lifecycle_id"] for row in runs]
    if actual != expected or len(runs) != 15 or len(ids) != len(set(ids)):
        raise ValueError("confirmation matrix is incomplete or lifecycle IDs repeat")
    if {row["workload"] for row in runs} != {workload}:
        raise ValueError("confirmation workload drift")
    if len({row["protocol_fingerprint"] for row in runs}) != 1:
        raise ValueError("confirmation protocol drift")

    index = {(row["round"], row["policy_mode"]): row for row in runs}
    deltas = {"ttft": [], "e2e": [], "rps": []}
    best_fixed = []
    for round_index in range(1, 6):
        controller = index[(round_index, "controller")]
        fixed = [index[(round_index, policy)] for policy in POLICIES[:2]]
        best_ttft = min(fixed, key=lambda row: float(row["mean_ttft_ms"]))
        best_e2e = min(fixed, key=lambda row: float(row["mean_latency_ms"]))
        best_rps = max(fixed, key=lambda row: float(row["request_throughput_rps"]))
        best_fixed.append(best_ttft["policy_mode"])
        deltas["ttft"].append(
            relative_delta(
                float(controller["mean_ttft_ms"]), float(best_ttft["mean_ttft_ms"])
            )
        )
        deltas["e2e"].append(
            relative_delta(
                float(controller["mean_latency_ms"]), float(best_e2e["mean_latency_ms"])
            )
        )
        deltas["rps"].append(
            relative_delta(
                float(controller["request_throughput_rps"]),
                float(best_rps["request_throughput_rps"]),
            )
        )

    means = {name: statistics.mean(values) for name, values in deltas.items()}
    upper = one_sided_upper_95(deltas["ttft"])
    significant_positive = (
        means["ttft"] <= -5.0
        and upper < 0.0
        and means["e2e"] <= 5.0
        and means["rps"] >= -5.0
    )
    verdict = {
        "workload": workload,
        "controller_vs_best_fixed_ttft_pct_by_round": [
            round(value, 6) for value in deltas["ttft"]
        ],
        "controller_vs_best_fixed_ttft_pct_mean": round(means["ttft"], 6),
        "controller_vs_best_fixed_ttft_pct_one_sided_95_upper": round(upper, 6),
        "controller_vs_best_fixed_e2e_pct_mean": round(means["e2e"], 6),
        "controller_vs_best_fixed_throughput_pct_mean": round(means["rps"], 6),
        "best_fixed_ttft_policy_by_round": best_fixed,
        "significant_meaningful_positive": significant_positive,
    }
    with (output_dir / "confirmation_runs.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(runs[0]))
        writer.writeheader()
        writer.writerows(runs)
    (output_dir / "confirmation_verdict.json").write_text(
        json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
