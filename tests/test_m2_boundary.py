from __future__ import annotations

import json
from pathlib import Path

from paper.kv_materialization_control.experiments.aggregate_m2_boundary import (
    boundary_summary,
    build_artifacts,
)
from paper.kv_materialization_control.experiments.run_m2_online_boundary import (
    POLICIES,
    WORKLOADS,
    build_schedule,
)


def test_m2_schedule_is_complete_and_temporally_blocked() -> None:
    schedule = build_schedule()

    assert len(schedule) == len(WORKLOADS) * len(POLICIES) * 3
    assert {
        (spec.workload, spec.policy_mode, spec.round_index) for spec in schedule
    } == {
        (workload, policy, matched_round)
        for workload, _, _, _ in WORKLOADS
        for policy in POLICIES
        for matched_round in (1, 2, 3)
    }
    for workload, _, _, _ in WORKLOADS:
        first_policies = [
            spec.policy_mode
            for spec in schedule
            if spec.workload == workload and spec.order_index == 1
        ]
        assert set(first_policies) == set(POLICIES)


def _boundary_rows() -> list[dict]:
    rows = []
    for workload, positive in (
        ("shared_tool_scaffold_agent", True),
        ("shared_scenario_multi_turn_knowledge_service", False),
    ):
        for matched_round in (1, 2, 3):
            values = {
                "always_recompute": (100.0, 200.0, 10.0),
                "always_full_reuse": (90.0, 190.0, 11.0),
                "controller": (
                    (80.0, 185.0, 10.8) if positive else (92.0, 192.0, 10.7)
                ),
            }
            for policy, (ttft, latency, throughput) in values.items():
                rows.append(
                    {
                        "workload": workload,
                        "round": matched_round,
                        "policy_mode": policy,
                        "mean_ttft_ms": ttft,
                        "mean_latency_ms": latency,
                        "request_throughput_rps": throughput,
                    }
                )
    return rows


def test_m2_boundary_requires_meaningful_gain_and_no_large_regression() -> None:
    summary = {row["workload"]: row for row in boundary_summary(_boundary_rows())}

    assert summary["shared_tool_scaffold_agent"]["classification"] == "positive"
    assert (
        summary["shared_scenario_multi_turn_knowledge_service"]["classification"]
        == "fallback_or_no_gain"
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_synthetic_suite(root: Path) -> None:
    suite_runs = []
    sequence = 0
    metric_rows = _boundary_rows()
    metric_index = {
        (row["workload"], row["round"], row["policy_mode"]): row for row in metric_rows
    }
    for workload, _, _, _ in WORKLOADS:
        for matched_round in (1, 2, 3):
            for policy in POLICIES:
                sequence += 1
                bundle = (
                    root
                    / workload
                    / policy
                    / f"round_{matched_round:02d}_sequence_{sequence:02d}"
                )
                bundle.mkdir(parents=True)
                metrics = metric_index[(workload, matched_round, policy)]
                effective = (
                    "partial_reuse"
                    if policy == "controller"
                    else ("recompute" if policy == "always_recompute" else "full_reuse")
                )
                reused = (
                    128
                    if effective == "partial_reuse"
                    else (0 if effective == "recompute" else 256)
                )
                recomputed = 384 - reused
                _write_json(
                    bundle / "run_manifest.json",
                    {
                        "evidence_label": "real-online/m2-benefit-boundary",
                        "workload_case": workload,
                        "policy_mode": policy,
                        "service_lifecycle_id": f"lifecycle-{sequence}",
                    },
                )
                _write_json(
                    bundle / "environment_manifest.json",
                    {"protocol_fingerprint": f"fingerprint-{workload}"},
                )
                _write_json(
                    bundle / "request_summary.json",
                    {
                        "requests": 1,
                        "completed": 1,
                        "mean_ttft_ms": metrics["mean_ttft_ms"],
                        "p95_ttft_ms": metrics["mean_ttft_ms"],
                        "mean_latency_ms": metrics["mean_latency_ms"],
                        "p95_latency_ms": metrics["mean_latency_ms"],
                        "request_throughput_rps": metrics["request_throughput_rps"],
                        "output_throughput_toks": 64.0,
                    },
                )
                observation = {
                    "decision": effective,
                    "runtime_effective_decision": effective,
                    "runtime_fallback_reason": None,
                    "runtime_target_reuse_tokens": reused,
                    "reusable_prefix_tokens": 256,
                    "remote_kv_bytes": 4096,
                    "transfer_time_ms": 1.0,
                    "recompute_time_ms": 4.0,
                    "queue_pressure": 0.0,
                    "reuse_confidence": 0.8,
                    "decision_latency_ms": 0.01,
                    "boundary_alignment_latency_ms": 0.02,
                    "controller_latency_ms": 0.04,
                }
                (bundle / "runtime_observations.jsonl").write_text(
                    json.dumps(observation) + "\n", encoding="utf-8"
                )
                _write_json(
                    bundle / "validation.json",
                    {
                        "valid": True,
                        "engine_accounting": [
                            {
                                "prompt_tokens": 384,
                                "reused_tokens": reused,
                                "recomputed_tokens": recomputed,
                                "realized_decision": effective,
                                "lookup_latency_ms": 0.1,
                                "commit_latency_ms": 0.2,
                                "tail_isolation_latency_ms": 0.03,
                                "cached_blocks": 2,
                                "peak_cache_usage": 0.25,
                            }
                        ],
                    },
                )
                suite_runs.append(
                    {
                        "returncode": 0,
                        "validation_returncode": 0,
                    }
                )
    _write_json(
        root / "suite_manifest.json",
        {
            "status": "completed",
            "evidence_label": "real-online/m2-benefit-boundary",
            "runs": suite_runs,
        },
    )


def test_m2_artifacts_rebuild_byte_identically(tmp_path: Path) -> None:
    suite = tmp_path / "suite"
    first = tmp_path / "first"
    second = tmp_path / "second"
    suite.mkdir()
    _write_synthetic_suite(suite)

    build_artifacts(suite, first)
    build_artifacts(suite, second)

    assert {path.name for path in first.iterdir()} == {
        path.name for path in second.iterdir()
    }
    for first_path in first.iterdir():
        assert first_path.read_bytes() == second.joinpath(first_path.name).read_bytes()
    verdict = json.loads(first.joinpath("m2_verdict.json").read_text())
    assert verdict["verdict"] == "continue_submission"
