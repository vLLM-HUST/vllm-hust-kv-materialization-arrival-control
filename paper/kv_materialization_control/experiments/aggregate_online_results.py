from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

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
    runs: list[dict] = []
    for validation_path in sorted(input_dir.rglob("validation.json")):
        validation = json.loads(validation_path.read_text())
        if not validation.get("valid"):
            continue
        bundle = validation_path.parent
        manifest = json.loads(bundle.joinpath("run_manifest.json").read_text())
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
            "completed": summary["completed"],
            "failed": len(summary["failures"]),
            "effective_recompute": decision_mix["recompute"],
            "effective_partial_reuse": decision_mix["partial_reuse"],
            "effective_full_reuse": decision_mix["full_reuse"],
        }
        row.update({metric: summary[metric] for metric in METRICS})
        runs.append(row)
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
