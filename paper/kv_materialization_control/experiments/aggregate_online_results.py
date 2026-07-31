from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

FORMAL_LABEL = "real-online/formal-matrix"
REQUIRED_CELLS = {
    (workload, seam, condition): 3
    for workload in (
        "shared_scenario_multi_turn_knowledge_service",
        "shared_tool_scaffold_agent",
    )
    for seam in ("old", "segmented")
    for condition in ("baseline", "tuned")
}
REQUIRED_CELLS[("dynamic_rag_corpus_update", "segmented", "tuned")] = 3

METRICS = (
    "mean_ttft_ms",
    "p95_ttft_ms",
    "mean_latency_ms",
    "p95_latency_ms",
    "request_throughput_rps",
    "output_throughput_toks",
)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def collect_runs(input_dir: Path) -> list[dict]:
    if (input_dir / "INVALIDATED.txt").exists():
        raise ValueError(
            f"suite is explicitly invalidated: {input_dir / 'INVALIDATED.txt'}"
        )
    execution_path = input_dir / "suite_execution.json"
    if not execution_path.is_file():
        raise ValueError("suite_execution.json is missing")
    execution = json.loads(execution_path.read_text())
    if execution.get("status") != "completed":
        raise ValueError(f"suite execution status is {execution.get('status')!r}")
    runs: list[dict] = []
    for validation_path in sorted(input_dir.rglob("validation.json")):
        validation = json.loads(validation_path.read_text())
        if not validation.get("valid"):
            raise ValueError(f"invalid formal bundle: {validation_path.parent}")
        if not validation.get("engine_accounting"):
            raise ValueError(
                f"bundle lacks independent engine accounting: {validation_path.parent}"
            )
        bundle = validation_path.parent
        manifest = json.loads(bundle.joinpath("run_manifest.json").read_text())
        environment = json.loads(
            bundle.joinpath("environment_manifest.json").read_text()
        )
        cleanup = json.loads(bundle.joinpath("cleanup.json").read_text())
        if (
            manifest.get("evidence_label") != FORMAL_LABEL
            or environment.get("evidence_label") != FORMAL_LABEL
        ):
            raise ValueError(f"non-formal evidence label in {bundle}")
        if not cleanup.get("port_free_after") or not cleanup.get("device_idle_after"):
            raise ValueError(f"cleanup evidence failed in {bundle}")
        summary = json.loads(bundle.joinpath("request_summary.json").read_text())
        observations = read_jsonl(bundle / "runtime_observations.jsonl")
        decision_mix = Counter(
            row["runtime_effective_decision"] for row in observations
        )
        row = {
            "bundle": str(bundle.relative_to(input_dir)),
            "workload": manifest["workload_case"],
            "seam": manifest["seam"],
            "condition": manifest["condition"],
            "service_lifecycle_id": manifest.get("service_lifecycle_id"),
            "started_at_utc": manifest.get("started_at_utc"),
            "protocol_fingerprint": environment.get("protocol_fingerprint"),
            "completed": summary["completed"],
            "failed": len(summary["failures"]),
            "effective_recompute": decision_mix["recompute"],
            "effective_partial_reuse": decision_mix["partial_reuse"],
            "effective_full_reuse": decision_mix["full_reuse"],
        }
        row.update({metric: summary[metric] for metric in METRICS})
        runs.append(row)
    counts = Counter((row["workload"], row["seam"], row["condition"]) for row in runs)
    if counts != Counter(REQUIRED_CELLS):
        raise ValueError(
            f"formal matrix is incomplete or contains extra cells: {counts}"
        )
    lifecycle_ids = [row["service_lifecycle_id"] for row in runs]
    if None in lifecycle_ids or len(set(lifecycle_ids)) != len(lifecycle_ids):
        raise ValueError("service lifecycle IDs are missing or not independent")
    for workload in {row["workload"] for row in runs}:
        fingerprints = {
            row["protocol_fingerprint"] for row in runs if row["workload"] == workload
        }
        if None in fingerprints or len(fingerprints) != 1:
            raise ValueError(
                f"protocol drift detected for workload {workload}: {fingerprints}"
            )
    scheduled = execution.get("runs", [])
    if len(scheduled) != len(runs) or any(
        record.get("returncode") != 0 or record.get("validation_returncode") != 0
        for record in scheduled
    ):
        raise ValueError("suite execution records do not prove all lifecycles passed")
    return runs


def aggregate_runs(runs: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in runs:
        grouped[(row["workload"], row["seam"], row["condition"])].append(row)
    aggregates = []
    for (workload, seam, condition), rows in sorted(grouped.items()):
        aggregate: dict[str, object] = {
            "workload": workload,
            "seam": seam,
            "condition": condition,
            "runs": len(rows),
        }
        for metric in METRICS:
            values = [float(row[metric]) for row in rows]
            q1 = percentile(values, 0.25)
            q3 = percentile(values, 0.75)
            aggregate[f"{metric}_median"] = round(statistics.median(values), 3)
            aggregate[f"{metric}_q1"] = round(q1, 3)
            aggregate[f"{metric}_q3"] = round(q3, 3)
            aggregate[f"{metric}_iqr"] = round(q3 - q1, 3)
        aggregates.append(aggregate)
    return aggregates


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("no valid formal bundles found")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_tex(path: Path, aggregates: list[dict]) -> None:
    lines = [
        "% Generated from committed real-online bundles; do not edit.",
        "\\begin{tabular}{lllrrr}",
        "Workload & Seam & Knobs & Runs & Median TTFT (ms) & IQR TTFT (ms) \\\\",
        "\\hline",
    ]
    for row in aggregates:
        workload = str(row["workload"]).replace("_", "\\_")
        lines.append(
            f"{workload} & {row['seam']} & {row['condition']} & {row['runs']} & "
            f"{row['mean_ttft_ms_median']} & {row['mean_ttft_ms_iqr']} \\\\"
        )
    lines.extend(["\\end{tabular}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate valid M1 online bundles into per-run and median/IQR artifacts."
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runs = collect_runs(input_dir)
    aggregates = aggregate_runs(runs)
    write_csv(output_dir / "online_runs.csv", runs)
    write_csv(output_dir / "online_summary_median_iqr.csv", aggregates)
    write_tex(output_dir / "online_summary_table.tex", aggregates)


if __name__ == "__main__":
    main()
