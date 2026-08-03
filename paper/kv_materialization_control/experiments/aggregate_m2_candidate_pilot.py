from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

POLICIES = ("always_recompute", "always_full_reuse", "controller")
EVIDENCE_LABEL = "real-online/m2-candidate-pilot"
ANCHOR_EVIDENCE_LABEL = "real-online/m2-anchor-candidate-pilot"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_delta(value: float, baseline: float) -> float:
    if baseline == 0:
        raise ValueError("zero baseline")
    return 100.0 * (value / baseline - 1.0)


def passes_promotion_gate(
    ttft_delta: float, e2e_delta: float, throughput_delta: float
) -> bool:
    return ttft_delta <= 2.0 and e2e_delta <= 5.0 and throughput_delta >= -5.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate the M2 pilot.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--expected-evidence-label",
        choices=(EVIDENCE_LABEL, ANCHOR_EVIDENCE_LABEL),
        default=EVIDENCE_LABEL,
    )
    args = parser.parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    suite = read_json(input_dir / "suite_manifest.json")
    if suite.get("status") != "completed":
        raise ValueError(f"pilot suite is not completed: {suite.get('status')}")
    if suite.get("evidence_label") != args.expected_evidence_label:
        raise ValueError("wrong pilot evidence label")

    runs = []
    for validation_path in sorted(input_dir.rglob("validation.json")):
        bundle = validation_path.parent
        validation = read_json(validation_path)
        manifest = read_json(bundle / "run_manifest.json")
        summary = read_json(bundle / "request_summary.json")
        environment = read_json(bundle / "environment_manifest.json")
        if not validation.get("valid"):
            raise ValueError(f"invalid bundle: {bundle}")
        accounting = validation.get("engine_accounting")
        if not isinstance(accounting, list) or not accounting:
            raise ValueError(f"missing engine accounting: {bundle}")
        runs.append(
            {
                "bundle": str(bundle.relative_to(input_dir)),
                "workload": manifest["workload_case"],
                "policy_mode": manifest["policy_mode"],
                "service_lifecycle_id": manifest["service_lifecycle_id"],
                "protocol_fingerprint": environment["protocol_fingerprint"],
                "requests": summary["requests"],
                "completed": summary["completed"],
                "mean_ttft_ms": summary["mean_ttft_ms"],
                "mean_latency_ms": summary["mean_latency_ms"],
                "request_throughput_rps": summary["request_throughput_rps"],
                "reused_tokens": sum(int(row["reused_tokens"]) for row in accounting),
                "recomputed_tokens": sum(
                    int(row["recomputed_tokens"]) for row in accounting
                ),
            }
        )

    workloads = sorted({row["workload"] for row in runs})
    expected = {(w, p) for w in workloads for p in POLICIES}
    actual = {(row["workload"], row["policy_mode"]) for row in runs}
    if len(workloads) != 2 or actual != expected or len(runs) != 6:
        raise ValueError("pilot matrix is incomplete")
    ids = [row["service_lifecycle_id"] for row in runs]
    if len(ids) != len(set(ids)):
        raise ValueError("pilot lifecycle IDs are not independent")
    for workload in workloads:
        fingerprints = {
            row["protocol_fingerprint"] for row in runs if row["workload"] == workload
        }
        if len(fingerprints) != 1:
            raise ValueError(f"protocol drift for {workload}")

    index = {(row["workload"], row["policy_mode"]): row for row in runs}
    verdicts = []
    for workload in workloads:
        controller = index[(workload, "controller")]
        fixed = [index[(workload, policy)] for policy in POLICIES[:2]]
        best_ttft = min(fixed, key=lambda row: float(row["mean_ttft_ms"]))
        best_e2e = min(fixed, key=lambda row: float(row["mean_latency_ms"]))
        best_rps = max(fixed, key=lambda row: float(row["request_throughput_rps"]))
        ttft_delta = relative_delta(
            float(controller["mean_ttft_ms"]), float(best_ttft["mean_ttft_ms"])
        )
        e2e_delta = relative_delta(
            float(controller["mean_latency_ms"]), float(best_e2e["mean_latency_ms"])
        )
        rps_delta = relative_delta(
            float(controller["request_throughput_rps"]),
            float(best_rps["request_throughput_rps"]),
        )
        promote = passes_promotion_gate(ttft_delta, e2e_delta, rps_delta)
        verdicts.append(
            {
                "workload": workload,
                "best_fixed_ttft_policy": best_ttft["policy_mode"],
                "controller_vs_best_fixed_ttft_pct": round(ttft_delta, 6),
                "controller_vs_best_fixed_e2e_pct": round(e2e_delta, 6),
                "controller_vs_best_fixed_throughput_pct": round(rps_delta, 6),
                "promotion": promote,
            }
        )

    for name, rows in (("pilot_runs.csv", runs), ("pilot_verdicts.csv", verdicts)):
        with (output_dir / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (output_dir / "pilot_verdict.json").write_text(
        json.dumps(
            {
                "promoted_workloads": [
                    row["workload"] for row in verdicts if row["promotion"]
                ],
                "workloads": verdicts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
