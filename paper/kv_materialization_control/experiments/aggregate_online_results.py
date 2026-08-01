from __future__ import annotations

import argparse
import csv
import json
import math
import re
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
DECISION_METRICS = (
    "applied_recompute",
    "applied_partial_reuse",
    "applied_full_reuse",
    "realized_recompute",
    "realized_partial_reuse",
    "realized_full_reuse",
)
FACTORIAL_WORKLOADS = (
    "shared_scenario_multi_turn_knowledge_service",
    "shared_tool_scaffold_agent",
)
PRIMARY_METRICS = (
    "mean_ttft_ms",
    "mean_latency_ms",
    "request_throughput_rps",
)
# Two-sided 95% Student-t critical value for three matched lifecycle blocks (df=2).
T_CRITICAL_95_DF2 = 4.302652729911275


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def collect_runs(input_dir: Path) -> list[dict]:
    if (input_dir / "INVALIDATED.txt").exists():
        raise ValueError(
            f"suite is explicitly invalidated: {input_dir / 'INVALIDATED.txt'}"
        )
    execution_path = input_dir / "suite_manifest.json"
    if not execution_path.is_file():
        raise ValueError("suite_manifest.json is missing")
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
        applied_mix = validation.get("applied_decision_mix")
        realized_mix = validation.get("realized_decision_mix")
        if not isinstance(applied_mix, dict) or not isinstance(realized_mix, dict):
            raise TypeError(f"bundle lacks applied/realized decision mix: {bundle}")
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
            "applied_recompute": int(applied_mix.get("recompute", 0)),
            "applied_partial_reuse": int(applied_mix.get("partial_reuse", 0)),
            "applied_full_reuse": int(applied_mix.get("full_reuse", 0)),
            "realized_recompute": int(realized_mix.get("recompute", 0)),
            "realized_partial_reuse": int(realized_mix.get("partial_reuse", 0)),
            "realized_full_reuse": int(realized_mix.get("full_reuse", 0)),
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
        for metric in (*METRICS, *DECISION_METRICS):
            values = [float(row[metric]) for row in rows]
            q1 = percentile(values, 0.25)
            q3 = percentile(values, 0.75)
            aggregate[f"{metric}_median"] = round(statistics.median(values), 3)
            aggregate[f"{metric}_q1"] = round(q1, 3)
            aggregate[f"{metric}_q3"] = round(q3, 3)
            aggregate[f"{metric}_iqr"] = round(q3 - q1, 3)
        aggregates.append(aggregate)
    return aggregates


def _round_number(bundle: str) -> int:
    match = re.search(r"(?:^|/)round_(\d+)_sequence_\d+$", bundle)
    if match is None:
        raise ValueError(f"cannot recover matched round from bundle path: {bundle}")
    return int(match.group(1))


def _mean_ci(values: list[float]) -> tuple[float, float, float]:
    if len(values) != 3:
        raise ValueError(
            f"factorial analysis requires exactly 3 matched rounds, got {len(values)}"
        )
    mean = statistics.mean(values)
    half_width = T_CRITICAL_95_DF2 * statistics.stdev(values) / math.sqrt(len(values))
    return mean, mean - half_width, mean + half_width


def _relative_delta(numerator: float, denominator: float, label: str) -> float:
    if denominator == 0.0:
        raise ValueError(f"zero denominator for {label}")
    return 100.0 * (numerator / denominator - 1.0)


def _factorial_index(runs: list[dict]) -> dict[tuple[str, int, str, str], dict]:
    indexed: dict[tuple[str, int, str, str], dict] = {}
    for row in runs:
        if row["workload"] not in FACTORIAL_WORKLOADS:
            continue
        round_number = _round_number(row["bundle"])
        key = (row["workload"], round_number, row["seam"], row["condition"])
        if key in indexed:
            raise ValueError(f"duplicate factorial cell for matched round: {key}")
        indexed[key] = row

    expected = {
        (workload, round_number, seam, condition)
        for workload in FACTORIAL_WORKLOADS
        for round_number in (1, 2, 3)
        for seam in ("old", "segmented")
        for condition in ("baseline", "tuned")
    }
    actual = set(indexed)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"factorial matched rounds are incomplete or misaligned: "
            f"missing={missing}, extra={extra}"
        )
    return indexed


def factorial_effects(runs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Compute 2x2 contrasts with lifecycle round as the matched unit.

    Relative effects are calculated within each round before their mean and
    Descriptive Student-t intervals are computed. Negative latency effects and
    positive throughput effects are favorable. Relative interaction is the
    percentage-point difference between segmented and old-seam tuning effects.
    """
    indexed = _factorial_index(runs)
    round_rows: list[dict] = []
    summaries: list[dict] = []
    for workload in FACTORIAL_WORKLOADS:
        for metric in PRIMARY_METRICS:
            values_by_effect: dict[str, list[tuple[float, float]]] = defaultdict(list)
            for round_number in (1, 2, 3):
                cell = {
                    (seam, condition): float(
                        indexed[(workload, round_number, seam, condition)][metric]
                    )
                    for seam in ("old", "segmented")
                    for condition in ("baseline", "tuned")
                }
                old_mean = statistics.mean(
                    cell[("old", condition)] for condition in ("baseline", "tuned")
                )
                segmented_mean = statistics.mean(
                    cell[("segmented", condition)]
                    for condition in ("baseline", "tuned")
                )
                baseline_mean = statistics.mean(
                    cell[(seam, "baseline")] for seam in ("old", "segmented")
                )
                tuned_mean = statistics.mean(
                    cell[(seam, "tuned")] for seam in ("old", "segmented")
                )
                segmented_tuning_pct = _relative_delta(
                    cell[("segmented", "tuned")],
                    cell[("segmented", "baseline")],
                    "segmented tuning effect",
                )
                old_tuning_pct = _relative_delta(
                    cell[("old", "tuned")],
                    cell[("old", "baseline")],
                    "old-seam tuning effect",
                )
                contrasts = {
                    "seam_main": (
                        segmented_mean - old_mean,
                        _relative_delta(segmented_mean, old_mean, "seam main effect"),
                        "percent",
                    ),
                    "tuning_main": (
                        tuned_mean - baseline_mean,
                        _relative_delta(
                            tuned_mean, baseline_mean, "tuning main effect"
                        ),
                        "percent",
                    ),
                    "interaction": (
                        (cell[("segmented", "tuned")] - cell[("segmented", "baseline")])
                        - (cell[("old", "tuned")] - cell[("old", "baseline")]),
                        segmented_tuning_pct - old_tuning_pct,
                        "percentage_points",
                    ),
                    "segmented_tuned_vs_old_baseline": (
                        cell[("segmented", "tuned")] - cell[("old", "baseline")],
                        _relative_delta(
                            cell[("segmented", "tuned")],
                            cell[("old", "baseline")],
                            "endpoint contrast",
                        ),
                        "percent",
                    ),
                }
                for effect, (absolute, relative, unit) in contrasts.items():
                    values_by_effect[effect].append((absolute, relative))
                    round_rows.append(
                        {
                            "workload": workload,
                            "metric": metric,
                            "effect": effect,
                            "round": round_number,
                            "absolute_delta": round(absolute, 6),
                            "relative_delta": round(relative, 6),
                            "relative_delta_unit": unit,
                        }
                    )
            for effect, values in values_by_effect.items():
                absolute_mean, absolute_low, absolute_high = _mean_ci(
                    [value[0] for value in values]
                )
                relative_mean, relative_low, relative_high = _mean_ci(
                    [value[1] for value in values]
                )
                summaries.append(
                    {
                        "workload": workload,
                        "metric": metric,
                        "effect": effect,
                        "matched_rounds": 3,
                        "absolute_delta_mean": round(absolute_mean, 6),
                        "absolute_delta_ci95_low": round(absolute_low, 6),
                        "absolute_delta_ci95_high": round(absolute_high, 6),
                        "relative_delta_mean": round(relative_mean, 6),
                        "relative_delta_ci95_low": round(relative_low, 6),
                        "relative_delta_ci95_high": round(relative_high, 6),
                        "relative_delta_unit": (
                            "percentage_points"
                            if effect == "interaction"
                            else "percent"
                        ),
                        "interval_interpretation": "descriptive_exploratory",
                    }
                )
    return round_rows, summaries


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("no valid formal bundles found")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_tex(path: Path, aggregates: list[dict]) -> None:
    row_end = " " + "\\" * 2

    def count_text(value: object) -> str:
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)

    lines = [
        "% Generated from committed real-online bundles; do not edit.",
        "\\begin{tabular}{lllrrr}",
        ("Workload & Seam & Knobs & Runs & Median TTFT (ms) & IQR TTFT (ms)" + row_end),
        "\\hline",
    ]
    for row in aggregates:
        workload = str(row["workload"]).replace("_", "\\_")
        lines.append(
            f"{workload} & {row['seam']} & {row['condition']} & {row['runs']} & "
            f"{row['mean_ttft_ms_median']} & {row['mean_ttft_ms_iqr']}{row_end}"
        )
    lines.extend(
        [
            "\\end{tabular}",
            "",
            "% R/P/F means recompute/partial-reuse/full-reuse request counts.",
            "\\begin{tabular}{lllll}",
            "Workload & Seam & Knobs & Applied R/P/F & Realized R/P/F" + row_end,
            "\\hline",
        ]
    )
    for row in aggregates:
        workload = str(row["workload"]).replace("_", "\\_")
        applied = "/".join(
            count_text(row[f"applied_{decision}_median"])
            for decision in ("recompute", "partial_reuse", "full_reuse")
        )
        realized = "/".join(
            count_text(row[f"realized_{decision}_median"])
            for decision in ("recompute", "partial_reuse", "full_reuse")
        )
        lines.append(
            f"{workload} & {row['seam']} & {row['condition']} & "
            f"{applied} & {realized}{row_end}"
        )
    lines.extend(["\\end{tabular}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_factorial_tex(path: Path, summaries: list[dict]) -> None:
    row_end = " " + "\\" * 2
    labels = {
        "mean_ttft_ms": "Mean TTFT",
        "mean_latency_ms": "Mean E2E",
        "request_throughput_rps": "Request throughput",
    }
    lines = [
        "% Descriptive, non-randomized temporally blocked 2x2 analysis; do not edit.",
        "\\begin{tabular}{llllrrr}",
        "Workload & Metric & Effect & Unit & Mean & Descriptive 95\\% low & "
        "Descriptive 95\\% high" + row_end,
        "\\hline",
    ]
    for row in summaries:
        workload = str(row["workload"]).replace("_", "\\_")
        unit = "pp" if row["relative_delta_unit"] == "percentage_points" else "\\%"
        lines.append(
            f"{workload} & {labels[str(row['metric'])]} & {row['effect']} & {unit} & "
            f"{row['relative_delta_mean']:.3f} & "
            f"{row['relative_delta_ci95_low']:.3f} & "
            f"{row['relative_delta_ci95_high']:.3f}{row_end}"
        )
    lines.extend(["\\end{tabular}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def build_artifacts(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    runs = collect_runs(input_dir)
    aggregates = aggregate_runs(runs)
    factorial_rounds, factorial_summaries = factorial_effects(runs)
    write_csv(output_dir / "online_runs.csv", runs)
    write_csv(output_dir / "online_summary_median_iqr.csv", aggregates)
    write_csv(output_dir / "factorial_paired_round_deltas.csv", factorial_rounds)
    write_csv(output_dir / "factorial_effects_ci95.csv", factorial_summaries)
    write_tex(output_dir / "online_summary_table.tex", aggregates)
    write_factorial_tex(output_dir / "factorial_effects_ci95.tex", factorial_summaries)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate valid M1 online bundles into per-run and median/IQR artifacts."
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    build_artifacts(Path(args.input_dir).resolve(), Path(args.output_dir).resolve())


if __name__ == "__main__":
    main()
