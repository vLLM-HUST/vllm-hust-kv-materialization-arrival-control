from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from vllm_kv_materialization.policy import (
    MaterializationDecision,
    MaterializationSignals,
    estimate_materialization_ttft_ms,
)

EVIDENCE_LABEL = "real-online/m2-benefit-boundary"
POLICIES = ("always_recompute", "always_full_reuse", "controller")
WORKLOADS = (
    "shared_tool_scaffold_agent",
    "shared_scenario_multi_turn_knowledge_service",
)
METRICS = (
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_latency_ms",
    "p95_latency_ms",
    "request_throughput_rps",
    "output_throughput_toks",
)
MEANINGFUL_GAIN_PCT = 5.0


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def round_index(bundle: Path) -> int:
    match = re.search(r"round_(\d+)_sequence_\d+$", bundle.name)
    if match is None:
        raise ValueError(f"cannot recover matched round from {bundle}")
    return int(match.group(1))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty artifact: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def collect_runs(input_dir: Path) -> list[dict]:
    suite = read_json(input_dir / "suite_manifest.json")
    if suite.get("status") != "completed":
        raise ValueError(f"M2 suite status is {suite.get('status')!r}, not completed")
    if suite.get("evidence_label") != EVIDENCE_LABEL:
        raise ValueError("M2 suite evidence label is missing or incorrect")

    runs = []
    for validation_path in sorted(input_dir.rglob("validation.json")):
        bundle = validation_path.parent
        validation = read_json(validation_path)
        manifest = read_json(bundle / "run_manifest.json")
        environment = read_json(bundle / "environment_manifest.json")
        summary = read_json(bundle / "request_summary.json")
        observations = read_jsonl(bundle / "runtime_observations.jsonl")
        if not validation.get("valid"):
            raise ValueError(f"invalid M2 bundle: {bundle}")
        if manifest.get("evidence_label") != EVIDENCE_LABEL:
            raise ValueError(f"wrong evidence label: {bundle}")
        policy = manifest.get("policy_mode")
        if policy not in POLICIES:
            raise ValueError(f"invalid policy mode {policy!r}: {bundle}")
        accounting = validation.get("engine_accounting")
        if not isinstance(accounting, list) or not accounting:
            raise ValueError(f"missing engine accounting: {bundle}")

        observed = Counter(str(row["decision"]) for row in observations)
        effective = Counter(
            str(row["runtime_effective_decision"]) for row in observations
        )
        realized = Counter(str(row["realized_decision"]) for row in accounting)
        reasons = Counter(
            str(row["runtime_fallback_reason"])
            for row in observations
            if row.get("runtime_fallback_reason")
        )
        cache_usages = [
            float(row["peak_cache_usage"])
            for row in accounting
            if isinstance(row.get("peak_cache_usage"), (int, float))
        ]
        row = {
            "bundle": str(bundle.relative_to(input_dir)),
            "workload": manifest["workload_case"],
            "policy_mode": policy,
            "round": round_index(bundle),
            "service_lifecycle_id": manifest.get("service_lifecycle_id"),
            "protocol_fingerprint": environment.get("protocol_fingerprint"),
            "requests": summary["requests"],
            "completed": summary["completed"],
            **{metric: summary[metric] for metric in METRICS},
            "prompt_tokens": sum(int(item["prompt_tokens"]) for item in accounting),
            "avoided_prefill_tokens": sum(
                int(item["reused_tokens"]) for item in accounting
            ),
            "recomputed_tail_tokens": sum(
                int(item["recomputed_tokens"])
                for item in accounting
                if item["realized_decision"] == "partial_reuse"
            ),
            "lookup_latency_ms": round(
                sum(float(item["lookup_latency_ms"]) for item in accounting), 6
            ),
            "commit_latency_ms": round(
                sum(float(item["commit_latency_ms"]) for item in accounting), 6
            ),
            "tail_isolation_latency_ms": round(
                sum(float(item["tail_isolation_latency_ms"]) for item in accounting),
                6,
            ),
            "decision_latency_ms": round(
                sum(float(item["decision_latency_ms"]) for item in observations),
                6,
            ),
            "boundary_alignment_latency_ms": round(
                sum(
                    float(item["boundary_alignment_latency_ms"])
                    for item in observations
                ),
                6,
            ),
            "controller_latency_ms": round(
                sum(float(item["controller_latency_ms"]) for item in observations),
                6,
            ),
            "cached_blocks": sum(int(item["cached_blocks"]) for item in accounting),
            "peak_cache_usage": max(cache_usages, default=0.0),
            "observed_recompute": observed["recompute"],
            "observed_partial_reuse": observed["partial_reuse"],
            "observed_full_reuse": observed["full_reuse"],
            "effective_recompute": effective["recompute"],
            "effective_partial_reuse": effective["partial_reuse"],
            "effective_full_reuse": effective["full_reuse"],
            "realized_recompute": realized["recompute"],
            "realized_partial_reuse": realized["partial_reuse"],
            "realized_full_reuse": realized["full_reuse"],
            "realign_count": reasons[
                "partial_reuse_cut_point_realigned_to_runtime_hash_blocks"
            ],
            "fallback_full_reuse_count": reasons[
                "block_aligned_partial_reuse_dominated_by_full_reuse"
            ],
            "fallback_recompute_count": reasons[
                "block_aligned_partial_reuse_collapses_to_recompute"
            ],
            "fallback_reasons_json": json.dumps(dict(sorted(reasons.items()))),
            "_observations": observations,
        }
        runs.append(row)

    expected = {
        (workload, policy, matched_round)
        for workload in WORKLOADS
        for policy in POLICIES
        for matched_round in (1, 2, 3)
    }
    actual = {(row["workload"], row["policy_mode"], row["round"]) for row in runs}
    if actual != expected:
        raise ValueError(
            f"M2 matrix mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    lifecycle_ids = [row["service_lifecycle_id"] for row in runs]
    if None in lifecycle_ids or len(lifecycle_ids) != len(set(lifecycle_ids)):
        raise ValueError("M2 lifecycle IDs are missing or not independent")
    for workload in WORKLOADS:
        fingerprints = {
            row["protocol_fingerprint"] for row in runs if row["workload"] == workload
        }
        if None in fingerprints or len(fingerprints) != 1:
            raise ValueError(f"matched protocol drift for {workload}: {fingerprints}")
    scheduled = suite.get("runs", [])
    if len(scheduled) != len(runs) or any(
        record.get("returncode") != 0 or record.get("validation_returncode") != 0
        for record in scheduled
    ):
        raise ValueError("suite records do not close all M2 lifecycle validations")
    return runs


def public_runs(runs: list[dict]) -> list[dict]:
    return [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in runs
    ]


def mechanism_summary(runs: list[dict]) -> list[dict]:
    fields = (
        "avoided_prefill_tokens",
        "recomputed_tail_tokens",
        "lookup_latency_ms",
        "commit_latency_ms",
        "tail_isolation_latency_ms",
        "decision_latency_ms",
        "boundary_alignment_latency_ms",
        "controller_latency_ms",
        "cached_blocks",
        "peak_cache_usage",
        "observed_recompute",
        "observed_partial_reuse",
        "observed_full_reuse",
        "effective_recompute",
        "effective_partial_reuse",
        "effective_full_reuse",
        "realized_recompute",
        "realized_partial_reuse",
        "realized_full_reuse",
        "realign_count",
        "fallback_full_reuse_count",
        "fallback_recompute_count",
    )
    output = []
    for workload in WORKLOADS:
        for policy in POLICIES:
            group = [
                row
                for row in runs
                if row["workload"] == workload and row["policy_mode"] == policy
            ]
            output.append(
                {
                    "workload": workload,
                    "policy_mode": policy,
                    "lifecycles": len(group),
                    **{
                        f"{field}_median": round(
                            statistics.median(float(row[field]) for row in group), 6
                        )
                        for field in fields
                    },
                }
            )
    return output


def relative_delta(controller: float, baseline: float) -> float:
    if baseline == 0:
        raise ValueError("zero fixed-policy denominator")
    return 100.0 * (controller / baseline - 1.0)


def boundary_summary(runs: list[dict]) -> list[dict]:
    index = {(row["workload"], row["round"], row["policy_mode"]): row for row in runs}
    output = []
    for workload in WORKLOADS:
        deltas: dict[str, list[float]] = defaultdict(list)
        fixed_winners = Counter()
        for matched_round in (1, 2, 3):
            controller = index[(workload, matched_round, "controller")]
            fixed = [
                index[(workload, matched_round, policy)] for policy in POLICIES[:2]
            ]
            for metric in ("mean_ttft_ms", "mean_latency_ms"):
                best = min(fixed, key=lambda row: float(row[metric]))
                deltas[metric].append(
                    relative_delta(float(controller[metric]), float(best[metric]))
                )
                if metric == "mean_ttft_ms":
                    fixed_winners[str(best["policy_mode"])] += 1
            best_throughput = max(
                fixed, key=lambda row: float(row["request_throughput_rps"])
            )
            deltas["request_throughput_rps"].append(
                relative_delta(
                    float(controller["request_throughput_rps"]),
                    float(best_throughput["request_throughput_rps"]),
                )
            )
        mean_ttft_delta = statistics.mean(deltas["mean_ttft_ms"])
        mean_e2e_delta = statistics.mean(deltas["mean_latency_ms"])
        mean_throughput_delta = statistics.mean(deltas["request_throughput_rps"])
        positive = (
            mean_ttft_delta <= -MEANINGFUL_GAIN_PCT
            and mean_e2e_delta <= MEANINGFUL_GAIN_PCT
            and mean_throughput_delta >= -MEANINGFUL_GAIN_PCT
        )
        output.append(
            {
                "workload": workload,
                "matched_rounds": 3,
                "controller_vs_best_fixed_ttft_pct_mean": round(mean_ttft_delta, 6),
                "controller_vs_best_fixed_e2e_pct_mean": round(mean_e2e_delta, 6),
                "controller_vs_best_fixed_throughput_pct_mean": round(
                    mean_throughput_delta, 6
                ),
                "best_fixed_ttft_wins_json": json.dumps(dict(fixed_winners)),
                "meaningful_gain_threshold_pct": MEANINGFUL_GAIN_PCT,
                "classification": "positive" if positive else "fallback_or_no_gain",
            }
        )
    return output


def modeled_cost(observation: dict, action: str, reused_tokens: int) -> float:
    signals = MaterializationSignals(
        reusable_prefix_tokens=int(observation["reusable_prefix_tokens"]),
        remote_kv_bytes=int(observation["remote_kv_bytes"]),
        transfer_time_ms=float(observation["transfer_time_ms"]),
        recompute_time_ms=float(observation["recompute_time_ms"]),
        queue_pressure=float(observation["queue_pressure"]),
        ttft_sensitive=True,
        reuse_confidence=float(observation["reuse_confidence"]),
    )
    return estimate_materialization_ttft_ms(
        signals,
        MaterializationDecision(action),
        reused_tokens,
        partial_reuse_floor_tokens=128,
    )


def cost_model_agreement(runs: list[dict]) -> list[dict]:
    index = {(row["workload"], row["round"], row["policy_mode"]): row for row in runs}
    rows = []
    for workload in WORKLOADS:
        for matched_round in (1, 2, 3):
            controller = index[(workload, matched_round, "controller")]
            observations = controller["_observations"]
            predicted = {
                "always_recompute": statistics.mean(
                    modeled_cost(obs, "recompute", 0) for obs in observations
                ),
                "always_full_reuse": statistics.mean(
                    modeled_cost(obs, "full_reuse", int(obs["reusable_prefix_tokens"]))
                    for obs in observations
                ),
                "controller": statistics.mean(
                    modeled_cost(
                        obs,
                        str(obs["runtime_effective_decision"]),
                        int(obs["runtime_target_reuse_tokens"]),
                    )
                    for obs in observations
                ),
            }
            actual = {
                policy: float(index[(workload, matched_round, policy)]["mean_ttft_ms"])
                for policy in POLICIES
            }
            predicted_winner = min(predicted, key=predicted.get)
            actual_winner = min(actual, key=actual.get)
            rows.append(
                {
                    "workload": workload,
                    "round": matched_round,
                    **{
                        f"modeled_{policy}_ttft_ms": round(value, 6)
                        for policy, value in predicted.items()
                    },
                    **{
                        f"online_{policy}_ttft_ms": round(value, 6)
                        for policy, value in actual.items()
                    },
                    "modeled_winner": predicted_winner,
                    "online_winner": actual_winner,
                    "winner_agreement": predicted_winner == actual_winner,
                }
            )
    return rows


def write_tex(path: Path, mechanisms: list[dict], boundaries: list[dict]) -> None:
    boundary_index = {row["workload"]: row for row in boundaries}
    lines = [
        "% Generated only from validated M2 real-online bundles; do not edit.",
        "\\begin{tabular}{llrrrrrrl}",
        (
            "Workload & Policy & Avoided tokens & Tail tokens & Lookup ms & "
            "Commit ms & Tail isolation ms & TTFT vs best fixed (\\%) & "
            "Boundary \\\\"
        ),
        "\\hline",
    ]
    for row in mechanisms:
        if row["policy_mode"] != "controller":
            continue
        boundary = boundary_index[row["workload"]]
        workload = str(row["workload"]).replace("_", "\\_")
        classification = str(boundary["classification"]).replace("_", "\\_")
        lines.append(
            f"{workload} & controller & "
            f"{row['avoided_prefill_tokens_median']:.0f} & "
            f"{row['recomputed_tail_tokens_median']:.0f} & "
            f"{row['lookup_latency_ms_median']:.3f} & "
            f"{row['commit_latency_ms_median']:.3f} & "
            f"{row['tail_isolation_latency_ms_median']:.3f} & "
            f"{boundary['controller_vs_best_fixed_ttft_pct_mean']:.2f} & "
            f"{classification} \\\\"
        )
    lines.extend(["\\end{tabular}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def build_artifacts(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    runs = collect_runs(input_dir)
    mechanisms = mechanism_summary(runs)
    boundaries = boundary_summary(runs)
    agreement = cost_model_agreement(runs)
    classifications = {row["classification"] for row in boundaries}
    verdict = (
        "continue_submission"
        if {"positive", "fallback_or_no_gain"}.issubset(classifications)
        else "stop_mechanism_direction"
    )
    write_csv(output_dir / "m2_online_runs.csv", public_runs(runs))
    write_csv(output_dir / "m2_mechanism_breakdown.csv", mechanisms)
    write_csv(output_dir / "m2_benefit_boundary.csv", boundaries)
    write_csv(output_dir / "m2_cost_model_agreement.csv", agreement)
    write_tex(output_dir / "m2_mechanism_table.tex", mechanisms, boundaries)
    write_json(
        output_dir / "m2_verdict.json",
        {
            "verdict": verdict,
            "reason": (
                "continue only when the preregistered matrix contains both a "
                "meaningful positive boundary and a fallback/no-gain boundary"
            ),
            "workloads": boundaries,
            "cost_model_winner_agreement_rounds": sum(
                bool(row["winner_agreement"]) for row in agreement
            ),
            "cost_model_rounds": len(agreement),
        },
    )
    write_json(
        output_dir / "claim_ledger.json",
        {
            "schema_version": 1,
            "claims": [
                {
                    "claim": "three-policy online benefit boundary",
                    "evidence_class": "real-online",
                    "status": "supported"
                    if "positive" in classifications
                    else "negative",
                    "artifact": "m2_benefit_boundary.csv",
                },
                {
                    "claim": "requested, effective, and realized actions plus physical costs",
                    "evidence_class": "real-online",
                    "status": "supported",
                    "artifact": "m2_online_runs.csv",
                },
                {
                    "claim": "cost-model ordering agrees with online ordering",
                    "evidence_class": "simulation/model",
                    "status": "supported"
                    if all(bool(row["winner_agreement"]) for row in agreement)
                    else "mixed_or_negative",
                    "artifact": "m2_cost_model_agreement.csv",
                },
                {
                    "claim": "paper-facing mechanism decomposition and direction verdict",
                    "evidence_class": "derived-artifact",
                    "status": "supported",
                    "artifact": "m2_mechanism_table.tex,m2_verdict.json",
                },
            ],
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild the M2 benefit boundary from validated raw bundles."
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    build_artifacts(Path(args.input_dir).resolve(), Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
