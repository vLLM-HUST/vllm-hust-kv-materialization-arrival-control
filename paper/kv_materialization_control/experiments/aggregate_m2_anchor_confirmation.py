from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import Counter
from pathlib import Path

from run_m2_anchor_confirmation import EVIDENCE_LABEL, POLICIES, WORKLOAD


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def relative_delta(value: float, baseline: float) -> float:
    if baseline == 0:
        raise ValueError("zero baseline")
    return 100.0 * (value / baseline - 1.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate anchor confirmation.")
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
        raise ValueError("confirmation suite is not completed or has the wrong label")

    runs = []
    for validation_path in sorted(input_dir.rglob("validation.json")):
        bundle = validation_path.parent
        validation = read_json(validation_path)
        manifest = read_json(bundle / "run_manifest.json")
        summary = read_json(bundle / "request_summary.json")
        environment = read_json(bundle / "environment_manifest.json")
        observations = read_jsonl(bundle / "runtime_observations.jsonl")
        match = re.search(r"round_(\d+)_", bundle.name)
        if not validation.get("valid") or match is None:
            raise ValueError(f"invalid confirmation bundle: {bundle}")
        accounting = validation["engine_accounting"]
        observed = Counter(row["decision"] for row in observations)
        effective = Counter(row["runtime_effective_decision"] for row in observations)
        realized = Counter(row["realized_decision"] for row in accounting)
        runs.append(
            {
                "bundle": str(bundle.relative_to(input_dir)),
                "round": int(match.group(1)),
                "policy_mode": manifest["policy_mode"],
                "service_lifecycle_id": manifest["service_lifecycle_id"],
                "protocol_fingerprint": environment["protocol_fingerprint"],
                "requests": summary["requests"],
                "completed": summary["completed"],
                "mean_ttft_ms": summary["mean_ttft_ms"],
                "mean_latency_ms": summary["mean_latency_ms"],
                "request_throughput_rps": summary["request_throughput_rps"],
                **{
                    f"observed_{a}": observed[a]
                    for a in ("recompute", "partial_reuse", "full_reuse")
                },
                **{
                    f"effective_{a}": effective[a]
                    for a in ("recompute", "partial_reuse", "full_reuse")
                },
                **{
                    f"realized_{a}": realized[a]
                    for a in ("recompute", "partial_reuse", "full_reuse")
                },
                "reused_tokens": sum(int(row["reused_tokens"]) for row in accounting),
                "recomputed_tokens": sum(
                    int(row["recomputed_tokens"]) for row in accounting
                ),
            }
        )

    expected = {
        (round_index, policy) for round_index in (1, 2, 3) for policy in POLICIES
    }
    actual = {(row["round"], row["policy_mode"]) for row in runs}
    ids = [row["service_lifecycle_id"] for row in runs]
    if actual != expected or len(runs) != 9 or len(ids) != len(set(ids)):
        raise ValueError("confirmation matrix is incomplete or lifecycle IDs repeat")
    if len({row["protocol_fingerprint"] for row in runs}) != 1:
        raise ValueError("confirmation protocol drift")

    index = {(row["round"], row["policy_mode"]): row for row in runs}
    deltas = {"ttft": [], "e2e": [], "rps": []}
    winners = Counter()
    for round_index in (1, 2, 3):
        controller = index[(round_index, "controller")]
        fixed = [index[(round_index, policy)] for policy in POLICIES[:2]]
        best_ttft = min(fixed, key=lambda row: float(row["mean_ttft_ms"]))
        best_e2e = min(fixed, key=lambda row: float(row["mean_latency_ms"]))
        best_rps = max(fixed, key=lambda row: float(row["request_throughput_rps"]))
        winners[best_ttft["policy_mode"]] += 1
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

    mean_deltas = {name: statistics.mean(values) for name, values in deltas.items()}
    positive = (
        mean_deltas["ttft"] <= -5.0
        and mean_deltas["e2e"] <= 5.0
        and mean_deltas["rps"] >= -5.0
    )
    nominal_positive = (
        mean_deltas["ttft"] < 0.0
        and mean_deltas["e2e"] <= 0.0
        and mean_deltas["rps"] >= 0.0
    )
    verdict = {
        "workload": WORKLOAD,
        "controller_vs_best_fixed_ttft_pct_mean": round(mean_deltas["ttft"], 6),
        "controller_vs_best_fixed_e2e_pct_mean": round(mean_deltas["e2e"], 6),
        "controller_vs_best_fixed_throughput_pct_mean": round(mean_deltas["rps"], 6),
        "best_fixed_ttft_wins": dict(winners),
        "nominal_positive": nominal_positive,
        "meaningful_positive_5pct": positive,
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
