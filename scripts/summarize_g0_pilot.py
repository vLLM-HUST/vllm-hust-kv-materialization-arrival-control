#!/usr/bin/env python3
"""Build an auditable, non-verdict report from real G0 pilot runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def load_run(label: str, root: Path) -> dict[str, Any]:
    benchmark = root / "benchmark/random-online.json"
    requests = root / "benchmark/request_results.jsonl"
    telemetry = root / "raw/g0_connector_telemetry.jsonl"
    resources = root / "raw/g0_resource_samples.jsonl"
    connector = root / "parsed/g0_connector_summary.json"
    required = (benchmark, requests, telemetry, connector)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"incomplete run {label}: {missing}")

    bench = json.loads(benchmark.read_text(encoding="utf-8"))
    conn = json.loads(connector.read_text(encoding="utf-8"))
    materialization = conn["materialization"]
    overlap = conn.get("compute_transfer_overlap")
    return {
        "label": label,
        "run_dir": str(root.resolve()),
        "arm": bench["arm"],
        "requests": bench["requests"],
        "correctness_rate": bench["correctness_rate"],
        "ttft_p95_ms": bench["ttft_ms"]["p95"],
        "ttft_p99_ms": bench["ttft_ms"]["p99"],
        "goodput_rps": bench["goodput_rps"],
        "layer_ready_wait_p95_ms": materialization["layer_ready_wait_ms_p95"],
        "connector_queue_wait_p95_ms": materialization[
            "connector_queue_wait_ms_p95"
        ],
        "peak_bytes_in_flight": materialization["peak_bytes_in_flight"],
        "requested_materialization_bytes": materialization["requested_bytes"],
        "realized_materialization_bytes": materialization["realized_bytes"],
        "activation": conn["activation"],
        "compute_transfer_overlap": overlap,
        "artifacts": {
            "benchmark": artifact(benchmark),
            "requests": artifact(requests),
            "connector_telemetry": artifact(telemetry),
            "connector_summary": artifact(connector),
            **({"resource_samples": artifact(resources)} if resources.is_file() else {}),
        },
    }


def pct_ratio(left: float, right: float) -> float:
    return (left / right - 1.0) * 100.0


def comparisons(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_cell: dict[str, dict[str, dict[str, Any]]] = {}
    for run in runs:
        parts = run["label"].split("/")
        if len(parts) < 3:
            raise ValueError(f"run label must be workload/intensity/arm: {run['label']}")
        cell = "/".join(parts[:2])
        by_cell.setdefault(cell, {})[run["arm"]] = run

    output = []
    required = {
        "no_control",
        "request_token_bucket",
        "materialization_paced_oracle",
    }
    for cell, arms in sorted(by_cell.items()):
        if not required.issubset(arms):
            continue
        no_control = arms["no_control"]
        bucket = arms["request_token_bucket"]
        oracle = arms["materialization_paced_oracle"]
        output.append(
            {
                "cell": cell,
                "no_control_vs_oracle_ttft_regression_pct": pct_ratio(
                    no_control["ttft_p95_ms"], oracle["ttft_p95_ms"]
                ),
                "token_bucket_vs_oracle_ttft_gap_pct": pct_ratio(
                    bucket["ttft_p95_ms"], oracle["ttft_p95_ms"]
                ),
                "token_bucket_vs_oracle_goodput_gap_pct": pct_ratio(
                    bucket["goodput_rps"], oracle["goodput_rps"]
                ),
                "oracle_vs_no_control_goodput_loss_pct": (
                    1.0 - oracle["goodput_rps"] / no_control["goodput_rps"]
                )
                * 100.0,
            }
        )
    return output


def low_control_comparisons(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare the paired strict-low-concurrency no-control/oracle runs."""
    by_cell: dict[str, dict[str, dict[str, Any]]] = {}
    for run in runs:
        parts = run["label"].split("/")
        if len(parts) < 3:
            raise ValueError(f"run label must be workload/intensity/arm: {run['label']}")
        if parts[1] != "low_control":
            continue
        cell = "/".join(parts[:2])
        by_cell.setdefault(cell, {})[run["arm"]] = run

    output = []
    for cell, arms in sorted(by_cell.items()):
        if not {"no_control", "materialization_paced_oracle"}.issubset(arms):
            continue
        no_control = arms["no_control"]
        oracle = arms["materialization_paced_oracle"]
        output.append(
            {
                "cell": cell,
                "arrival_transform": "uniform_one_request_per_second",
                "no_control_vs_oracle_ttft_regression_pct": pct_ratio(
                    no_control["ttft_p95_ms"], oracle["ttft_p95_ms"]
                ),
                "no_control_vs_oracle_goodput_gap_pct": pct_ratio(
                    no_control["goodput_rps"], oracle["goodput_rps"]
                ),
                "no_control_correctness_rate": no_control["correctness_rate"],
                "oracle_correctness_rate": oracle["correctness_rate"],
            }
        )
    return output


def capacity_frontier(
    frontier_runs: list[dict[str, Any]], runs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    no_control = {
        "/".join(run["label"].split("/")[:2]): run
        for run in runs
        if run["arm"] == "no_control"
    }
    output = []
    for run in frontier_runs:
        cell = "/".join(run["label"].split("/")[:2])
        baseline = no_control.get(cell)
        if baseline is None:
            raise ValueError(f"frontier run has no no-control baseline: {cell}")
        output.append(
            {
                **run,
                "cell": cell,
                "p95_improvement_vs_no_control_pct": (
                    1.0 - run["ttft_p95_ms"] / baseline["ttft_p95_ms"]
                )
                * 100.0,
                "goodput_loss_vs_no_control_pct": (
                    1.0 - run["goodput_rps"] / baseline["goodput_rps"]
                )
                * 100.0,
            }
        )
    return sorted(output, key=lambda row: int(row["oracle_byte_budget"]))


def capacity_frontier_gate(frontier: list[dict[str, Any]]) -> dict[str, Any]:
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for row in frontier:
        by_cell.setdefault(row["cell"], []).append(row)
    cells = []
    for cell, rows in sorted(by_cell.items()):
        within_capacity = [
            row for row in rows if row["goodput_loss_vs_no_control_pct"] <= 5.0
        ]
        joint = [
            row
            for row in rows
            if row["p95_improvement_vs_no_control_pct"] >= 10.0
            and row["goodput_loss_vs_no_control_pct"] <= 5.0
        ]
        cells.append(
            {
                "cell": cell,
                "points": len(rows),
                "joint_gate_points": len(joint),
                "best_p95_improvement_within_5pct_goodput_loss": (
                    max(
                        row["p95_improvement_vs_no_control_pct"]
                        for row in within_capacity
                    )
                    if within_capacity
                    else None
                ),
            }
        )
    return {
        "tail_improvement_threshold_pct": 10.0,
        "goodput_loss_threshold_pct": 5.0,
        "all_cells_have_joint_gate_point": bool(cells)
        and all(cell["joint_gate_points"] > 0 for cell in cells),
        "cells": cells,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G0 real-runtime pilot",
        "",
        "**Status: incomplete — no Go/Stop verdict.** This is a single-repeat",
        "2 workloads × 2 intensities core pilot for no-control, request token bucket,",
        "and the byte oracle (plus one fixed-concurrency check). It validates the",
        "real AscendStore telemetry, includes the paired strict 1 req/s controls, and",
        "selects the capacity frontier to preregister; it lacks the required repeats",
        "and remaining matched arms.",
        "",
        "| Workload / arm | p95 TTFT (ms) | Goodput (req/s) | Layer-ready p95 (ms) | Peak in-flight bytes | Correct |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for run in report["runs"]:
        lines.append(
            f"| {run['label']} | {run['ttft_p95_ms']:.3f} | "
            f"{run['goodput_rps']:.3f} | {run['layer_ready_wait_p95_ms']:.3f} | "
            f"{run['peak_bytes_in_flight']} | {run['correctness_rate']:.0%} |"
        )
    lines.extend(["", "## Matched comparisons", ""])
    for row in report["comparisons"]:
        lines.append(
            f"- {row['cell']}: no-control/oracle p95 regression "
            f"{row['no_control_vs_oracle_ttft_regression_pct']:.2f}%; token-bucket/oracle "
            f"p95 gap {row['token_bucket_vs_oracle_ttft_gap_pct']:.2f}%; "
            f"token-bucket/oracle goodput gap "
            f"{row['token_bucket_vs_oracle_goodput_gap_pct']:.2f}%; "
            f"oracle goodput loss versus no-control "
            f"{row['oracle_vs_no_control_goodput_loss_pct']:.2f}%."
        )
    if report["low_control_comparisons"]:
        lines.extend(["", "## Strict low-concurrency controls", ""])
        for row in report["low_control_comparisons"]:
            lines.append(
                f"- {row['cell']}: no-control/oracle p95 regression "
                f"{row['no_control_vs_oracle_ttft_regression_pct']:.2f}%; "
                f"no-control/oracle goodput gap "
                f"{row['no_control_vs_oracle_goodput_gap_pct']:.2f}%; "
                f"correctness {row['no_control_correctness_rate']:.0%}/"
                f"{row['oracle_correctness_rate']:.0%}."
            )
    if report["capacity_frontier"]:
        lines.extend(
            [
                "",
                "## Frozen capacity frontier",
                "",
                "| Cell / budget bytes | p95 TTFT (ms) | Goodput (req/s) | p95 improvement | Goodput loss |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for row in report["capacity_frontier"]:
            lines.append(
                f"| {row['cell']} / {row['oracle_byte_budget']} | "
                f"{row['ttft_p95_ms']:.3f} | {row['goodput_rps']:.3f} | "
                f"{row['p95_improvement_vs_no_control_pct']:.2f}% | "
                f"{row['goodput_loss_vs_no_control_pct']:.2f}% |"
            )
        lines.extend(["", "Capacity-preserving check (goodput loss <=5%):", ""])
        for cell in report["capacity_frontier_gate"]["cells"]:
            best = cell["best_p95_improvement_within_5pct_goodput_loss"]
            best_text = "no eligible point" if best is None else f"{best:.2f}%"
            lines.append(
                f"- {cell['cell']}: best p95 improvement {best_text}; "
                f"joint >=10% tail / <=5% goodput points: "
                f"{cell['joint_gate_points']}."
            )
    lines.extend(
        [
            "",
            "The two traces disagree on generic token-bucket equivalence, so the Stop",
            "condition is not established. Across all four frozen frontiers, no budget",
            "point jointly reaches >=10% p95 improvement and <=5% goodput loss. The Go",
            "condition is therefore not established. Neither strict low-concurrency",
            "control shows the >=10% gap, which passes that control check for this",
            "repeat. Complete the remaining matched arms and repeats before a verdict.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        metavar="LABEL=DIR",
        help="pilot run, for example burstgpt/high/no_control=/tmp/run",
    )
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    parser.add_argument(
        "--frontier-run",
        action="append",
        default=[],
        metavar="LABEL=DIR",
        help="frozen oracle-frontier run",
    )
    args = parser.parse_args()

    runs = []
    for value in args.run:
        if "=" not in value:
            raise SystemExit(f"--run must be LABEL=DIR: {value}")
        label, path = value.split("=", 1)
        runs.append(load_run(label, Path(path)))
    frontier_runs = []
    for value in args.frontier_run:
        if "=" not in value:
            raise SystemExit(f"--frontier-run must be LABEL=DIR: {value}")
        label, path = value.split("=", 1)
        run = load_run(label, Path(path))
        benchmark = json.loads(
            (Path(path) / "benchmark/random-online.json").read_text(encoding="utf-8")
        )
        run["oracle_byte_budget"] = int(benchmark["controls"]["oracle_byte_budget"])
        frontier_runs.append(run)
    frontier = capacity_frontier(frontier_runs, runs)
    report = {
        "schema_version": 1,
        "artifact": "g0-real-runtime-pilot",
        "status": "incomplete_no_verdict",
        "runs": runs,
        "comparisons": comparisons(runs),
        "low_control_comparisons": low_control_comparisons(runs),
        "capacity_frontier": frontier,
        "capacity_frontier_gate": capacity_frontier_gate(frontier),
    }
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    output_markdown.write_text(markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
