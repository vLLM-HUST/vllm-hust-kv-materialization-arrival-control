import json
import subprocess
import sys
from pathlib import Path

import pytest


def write_run(root: Path, arm: str, ttft: float, goodput: float) -> None:
    (root / "benchmark").mkdir(parents=True)
    (root / "raw").mkdir()
    (root / "parsed").mkdir()
    (root / "benchmark/random-online.json").write_text(
        json.dumps(
            {
                "arm": arm,
                "requests": 1,
                "correctness_rate": 1.0,
                "ttft_ms": {"p95": ttft, "p99": ttft},
                "goodput_rps": goodput,
                "controls": {"oracle_byte_budget": 1024},
            }
        )
    )
    (root / "benchmark/request_results.jsonl").write_text("{}\n")
    (root / "raw/g0_connector_telemetry.jsonl").write_text("{}\n")
    (root / "parsed/g0_connector_summary.json").write_text(
        json.dumps(
            {
                "activation": {"request_ids": 1},
                "materialization": {
                    "layer_ready_wait_ms_p95": 1.0,
                    "connector_queue_wait_ms_p95": 0.1,
                    "peak_bytes_in_flight": 1024,
                    "requested_bytes": 1024,
                    "realized_bytes": 1024,
                },
            }
        )
    )


def test_builds_matched_comparison(tmp_path: Path) -> None:
    arms = {
        "no_control": (120.0, 10.0),
        "request_token_bucket": (101.0, 8.1),
        "materialization_paced_oracle": (100.0, 8.0),
    }
    run_args = []
    for arm, (ttft, goodput) in arms.items():
        root = tmp_path / arm
        write_run(root, arm, ttft, goodput)
        run_args.extend(["--run", f"burstgpt/high/{arm}={root}"])
    output = tmp_path / "report.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/summarize_g0_pilot.py",
            *run_args,
            "--output-json",
            str(output),
            "--output-markdown",
            str(tmp_path / "report.md"),
            "--frontier-run",
            f"burstgpt/high/oracle_b4={tmp_path / 'materialization_paced_oracle'}",
        ],
        check=True,
    )
    comparison = json.loads(output.read_text())["comparisons"][0]
    assert comparison["no_control_vs_oracle_ttft_regression_pct"] == pytest.approx(20.0)
    assert comparison["token_bucket_vs_oracle_ttft_gap_pct"] == pytest.approx(1.0)
    frontier = json.loads(output.read_text())["capacity_frontier"][0]
    assert frontier["oracle_byte_budget"] == 1024
    assert frontier["p95_improvement_vs_no_control_pct"] == pytest.approx(100 / 6)
    gate = json.loads(output.read_text())["capacity_frontier_gate"]
    assert gate["all_cells_have_joint_gate_point"] is False
    assert gate["cells"][0]["joint_gate_points"] == 0


def test_builds_strict_low_control_comparison(tmp_path: Path) -> None:
    no_control = tmp_path / "no_control"
    oracle = tmp_path / "oracle"
    write_run(no_control, "no_control", 103.0, 1.0)
    write_run(oracle, "materialization_paced_oracle", 100.0, 1.0)
    output = tmp_path / "report.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/summarize_g0_pilot.py",
            "--run",
            f"burstgpt/low_control/no_control={no_control}",
            "--run",
            f"burstgpt/low_control/materialization_paced_oracle={oracle}",
            "--output-json",
            str(output),
            "--output-markdown",
            str(tmp_path / "report.md"),
        ],
        check=True,
    )
    report = json.loads(output.read_text())
    assert report["comparisons"] == []
    comparison = report["low_control_comparisons"][0]
    assert comparison["arrival_transform"] == "uniform_one_request_per_second"
    assert comparison["no_control_vs_oracle_ttft_regression_pct"] == pytest.approx(3.0)
    assert comparison["no_control_vs_oracle_goodput_gap_pct"] == pytest.approx(0.0)
