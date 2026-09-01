#!/usr/bin/env python3
"""Rebuild the formal G0 gate directly from immutable real-runtime run trees."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import statistics
from collections import defaultdict
from itertools import product
from pathlib import Path
from typing import Any


MAIN_ARMS = {
    "no_control",
    "always_recompute",
    "concurrency_cap",
    "request_token_bucket",
    "minimum_retrieve_threshold",
    "fixed_prefetch_depth",
    "materialization_paced_oracle",
}
GENERIC_ARMS = ("concurrency_cap", "request_token_bucket")
ORACLE = "materialization_paced_oracle"
FRONTIER_BUDGETS = (63_700_992, 127_401_984, 254_803_968)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot take median of empty values")
    return statistics.median(values)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil((len(ordered) - 1) * q / 100)]


def paired_lifecycle_bootstrap_median(
    values: list[float], confidence: float = 95.0
) -> dict[str, Any]:
    """Exact bootstrap CI with server lifecycles as the sampling unit."""
    if not values:
        raise ValueError("cannot bootstrap empty lifecycle values")
    if len(values) > 8:
        raise ValueError("exact lifecycle bootstrap is limited to eight repeats")
    alpha = (100.0 - confidence) / 2.0
    samples = [
        median([values[index] for index in indices])
        for indices in product(range(len(values)), repeat=len(values))
    ]
    return {
        "confidence_pct": confidence,
        "lower_pct": percentile(samples, alpha),
        "upper_pct": percentile(samples, 100.0 - alpha),
        "replicates": len(samples),
        "sampling_unit": "paired_server_lifecycle",
        "statistic": "median",
        "method": "exact_n_to_n_resampling_with_replacement",
    }


def reuse_pressure_groups(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate request-attributable connector pressure by realized reuse."""
    reuse: dict[str, int] = {}
    requested: dict[str, int] = defaultdict(int)
    queue_wait: dict[str, list[float]] = defaultdict(list)
    layer_wait: dict[str, list[float]] = defaultdict(list)
    inflight: dict[str, list[int]] = defaultdict(list)
    for event in events:
        name = event.get("event")
        request_id = event.get("request_id")
        if name == "materialization_decision" and request_id and event.get("external_hit_tokens", 0) > 0:
            reuse[request_id] = int(event["external_hit_tokens"])
        request_ids = event.get("request_ids", [])
        if name == "transfer_started":
            byte_map = event.get("request_materialization_bytes", {})
            for rid in request_ids:
                requested[rid] += int(byte_map.get(rid, 0))
                queue_wait[rid].append(float(event.get("connector_queue_wait_ns", 0)) / 1e6)
                inflight[rid].append(int(event.get("bytes_in_flight", 0)))
        elif name == "layer_ready_wait_finished":
            for rid in request_ids:
                layer_wait[rid].append(float(event.get("layer_ready_wait_ns", 0)) / 1e6)

    grouped: dict[int, dict[str, list[float]]] = defaultdict(
        lambda: {"requested": [], "queue": [], "layer": [], "inflight": []}
    )
    for rid, tokens in reuse.items():
        grouped[tokens]["requested"].append(float(requested.get(rid, 0)))
        grouped[tokens]["queue"].extend(queue_wait.get(rid, []))
        grouped[tokens]["layer"].extend(layer_wait.get(rid, []))
        grouped[tokens]["inflight"].extend(float(value) for value in inflight.get(rid, []))
    return [
        {
            "reuse_tokens": tokens,
            "requests": sum(1 for value in reuse.values() if value == tokens),
            "requested_bytes_mean": statistics.mean(values["requested"]),
            "connector_queue_wait_ms_p95": percentile(values["queue"], 95),
            "layer_ready_wait_ms_p95": percentile(values["layer"], 95),
            "bytes_in_flight_p95": percentile(values["inflight"], 95),
        }
        for tokens, values in sorted(grouped.items())
    ]


def run_name(spec: dict[str, Any]) -> str:
    return (
        f"{spec['sequence']:03d}-{spec['workload']}-{spec['burst_intensity']}-"
        f"{spec['arm']}-r{spec['repeat']}"
    )


def expected_controls(arm: str) -> tuple[int, int]:
    threshold = 512 if arm == "always_recompute" else 256 if arm == "minimum_retrieve_threshold" else 0
    depth = 4 if arm == "fixed_prefetch_depth" else 1
    return threshold, depth


def load_run(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    paths = {
        "benchmark": root / "benchmark/random-online.json",
        "requests": root / "benchmark/request_results.jsonl",
        "telemetry": root / "raw/g0_connector_telemetry.jsonl",
        "resources": root / "raw/g0_resource_samples.jsonl",
        "connector": root / "parsed/g0_connector_summary.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise ValueError(f"missing artifacts: {missing}")

    bench = read_json(paths["benchmark"])
    requests = read_jsonl(paths["requests"])
    telemetry_events = read_jsonl(paths["telemetry"])
    conn = read_json(paths["connector"])
    arm = spec["arm"]
    if bench.get("arm") != arm:
        raise ValueError(f"arm mismatch: expected {arm}, got {bench.get('arm')}")
    if bench.get("requests") != len(requests) or not requests:
        raise ValueError("benchmark/request record count mismatch")
    if len(requests) != 64:
        raise ValueError(f"expected 64 workload requests, got {len(requests)}")
    if bench.get("correctness_rate") != 1.0:
        raise ValueError("correctness is not 100%")
    ids = [row.get("request_id") for row in requests]
    if None in ids or len(ids) != len(set(ids)):
        raise ValueError("request IDs are missing or duplicated")
    if any(
        not row.get("ok")
        or row.get("http_status") != 200
        or not row.get("output_sha256")
        or row.get("output_tokens") != 8
        for row in requests
    ):
        raise ValueError("request correctness/hash activation failure")

    activation = conn.get("activation", {})
    decisions = activation.get("decision_counts", {})
    request_count = len(requests)
    if activation.get("connector_config_events") != 1:
        raise ValueError("connector configuration was not activated exactly once")
    if activation.get("decision_request_ids") != request_count:
        raise ValueError("materialization decision coverage mismatch")
    if sum(decisions.values()) != request_count:
        raise ValueError("materialization decision count mismatch")
    if not activation.get("all_transfer_results_ok"):
        raise ValueError("connector transfer failure observed")

    materialize = decisions.get("materialize", 0)
    recompute = decisions.get("recompute_threshold", 0)
    transfers = activation.get("transfer_starts", 0)
    if arm == "always_recompute" and (recompute != request_count or materialize or transfers):
        raise ValueError("always-recompute arm did not exclusively recompute")
    if arm == "minimum_retrieve_threshold" and not (materialize and recompute and transfers):
        raise ValueError("minimum-retrieve arm did not activate both decisions")
    if arm not in {"always_recompute", "minimum_retrieve_threshold"} and materialize != request_count:
        raise ValueError("materializing arm did not materialize every request")

    threshold, depth = expected_controls(arm)
    controls = bench.get("controls", {})
    if controls.get("minimum_retrieve_tokens") != threshold:
        raise ValueError("minimum-retrieve runtime control mismatch")
    if controls.get("fixed_prefetch_depth") != depth:
        raise ValueError("prefetch-depth runtime control mismatch")

    mat = conn.get("materialization", {})
    if mat.get("requested_bytes") != mat.get("realized_bytes"):
        raise ValueError("requested and realized materialization bytes differ")
    resources = conn.get("resources", {})
    return {
        "sequence": spec["sequence"],
        "workload": spec["workload"],
        "burst_intensity": spec["burst_intensity"],
        "repeat": spec["repeat"],
        "arm": arm,
        "run_dir": str(root.resolve()),
        "requests": request_count,
        "correctness_rate": bench["correctness_rate"],
        "ttft_ms": bench["ttft_ms"],
        "e2e_ms": bench["e2e_ms"],
        "tpot_ms": bench["tpot_ms"],
        "throughput_rps": bench["throughput_rps"],
        "goodput_rps": bench["goodput_rps"],
        "controls": controls,
        "activation": activation,
        "materialization": mat,
        "resources": resources,
        "compute_transfer_overlap": conn.get("compute_transfer_overlap"),
        "reuse_pressure": reuse_pressure_groups(telemetry_events),
        "outputs": {
            row["request_id"]: {
                "sha256": row["output_sha256"],
                "tokens": row["output_tokens"],
                "http_status": row["http_status"],
            }
            for row in requests
        },
        "artifacts": {key: artifact(path) for key, path in paths.items()},
    }


def pct_regression(slower: float, faster: float) -> float:
    return (slower / faster - 1.0) * 100.0


def pct_improvement(baseline: float, candidate: float) -> float:
    return (1.0 - candidate / baseline) * 100.0


def pressure_explained(no_control: dict[str, Any], oracle: dict[str, Any]) -> bool:
    no_mat = no_control["materialization"]
    oracle_mat = oracle["materialization"]
    pairs = (
        (no_mat.get("peak_bytes_in_flight"), oracle_mat.get("peak_bytes_in_flight")),
        (no_mat.get("connector_queue_wait_ms_p95"), oracle_mat.get("connector_queue_wait_ms_p95")),
        (no_mat.get("layer_ready_wait_ms_p95"), oracle_mat.get("layer_ready_wait_ms_p95")),
    )
    return any(
        left is not None and right is not None and float(left) > max(float(right) * 1.1, float(right) + 0.05)
        for left, right in pairs
    )


def cell_evidence(rounds: list[dict[str, dict[str, Any]]]) -> dict[str, Any]:
    regressions = []
    oracle_improvements = []
    goodput_losses = []
    pressure = []
    generic: dict[str, dict[str, list[float]]] = {
        arm: {"tail": [], "goodput_loss": []} for arm in GENERIC_ARMS
    }
    for arms in rounds:
        no_control, oracle = arms["no_control"], arms[ORACLE]
        regressions.append(
            pct_regression(no_control["ttft_ms"]["p95"], oracle["ttft_ms"]["p95"])
        )
        oracle_improvements.append(
            pct_improvement(no_control["ttft_ms"]["p95"], oracle["ttft_ms"]["p95"])
        )
        goodput_losses.append(
            pct_improvement(no_control["goodput_rps"], oracle["goodput_rps"])
        )
        pressure.append(pressure_explained(no_control, oracle))
        for arm in GENERIC_ARMS:
            candidate = arms[arm]
            generic[arm]["tail"].append(
                pct_improvement(no_control["ttft_ms"]["p95"], candidate["ttft_ms"]["p95"])
            )
            generic[arm]["goodput_loss"].append(
                pct_improvement(no_control["goodput_rps"], candidate["goodput_rps"])
            )

    oracle_tail = median(regressions)
    oracle_improvement = median(oracle_improvements)
    oracle_loss = median(goodput_losses)
    generic_summary = {}
    generic_equivalent = False
    for arm, values in generic.items():
        tail = median(values["tail"])
        loss = median(values["goodput_loss"])
        equivalent = tail >= oracle_improvement - 1.0 and loss <= oracle_loss + 1.0
        generic_summary[arm] = {
            "median_p95_improvement_pct": tail,
            "median_p95_improvement_bootstrap_ci": paired_lifecycle_bootstrap_median(
                values["tail"]
            ),
            "median_goodput_loss_pct": loss,
            "median_goodput_loss_bootstrap_ci": paired_lifecycle_bootstrap_median(
                values["goodput_loss"]
            ),
            "equivalent_or_better_than_oracle": equivalent,
        }
        generic_equivalent |= equivalent
    return {
        "repeat_p95_regression_pct": regressions,
        "median_p95_regression_pct": oracle_tail,
        "median_p95_regression_bootstrap_ci": paired_lifecycle_bootstrap_median(
            regressions
        ),
        "median_p95_improvement_pct": oracle_improvement,
        "median_p95_improvement_bootstrap_ci": paired_lifecycle_bootstrap_median(
            oracle_improvements
        ),
        "repeat_goodput_loss_pct": goodput_losses,
        "median_goodput_loss_pct": oracle_loss,
        "median_goodput_loss_bootstrap_ci": paired_lifecycle_bootstrap_median(
            goodput_losses
        ),
        "repeat_materialization_pressure_explained": pressure,
        "repeats_meeting_tail_gate": sum(value >= 10.0 for value in regressions),
        "reproducible_tail_gate": oracle_tail >= 10.0,
        "materialization_counter_gate": sum(pressure) >= 2,
        "capacity_preserving_gate": abs(oracle_loss) <= 5.0,
        "generic_baselines": generic_summary,
        "generic_equivalent_stop": generic_equivalent,
    }


def preregistered_stop_triggers(cells: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    triggers = []
    for name, row in sorted(cells.items()):
        if not row["reproducible_tail_gate"]:
            triggers.append({"cell": name, "trigger": "tail_pathology_not_reproducible"})
        if not row["materialization_counter_gate"]:
            triggers.append({"cell": name, "trigger": "materialization_counter_gate_failed"})
        if row["generic_equivalent_stop"]:
            triggers.append({"cell": name, "trigger": "generic_baseline_equivalent"})
    return triggers


def frontier_specs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the frozen three additional byte budgets in runner order."""
    sequence = len(manifest["schedule"]) + 1
    specs = []
    workloads = sorted({spec["workload"] for spec in manifest["schedule"]})
    # The runner's order is part of custody and intentionally explicit here.
    workloads = [name for name in ("burstgpt", "servegen") if name in workloads]
    intensities = ["moderate", "high"]
    for workload in workloads:
        for intensity in intensities:
            for repeat in range(1, int(manifest["repeats"]) + 1):
                for budget in FRONTIER_BUDGETS:
                    specs.append(
                        {
                            "sequence": sequence,
                            "workload": workload,
                            "burst_intensity": intensity,
                            "repeat": repeat,
                            "arm": ORACLE,
                            "budget": budget,
                        }
                    )
                    sequence += 1
    return specs


def frontier_run_name(spec: dict[str, Any]) -> str:
    return f"{run_name(spec)}-budget{spec['budget']}"


def summarize_frontier(
    manifest: dict[str, Any],
    run_root: Path,
    by_round: dict[tuple[str, str, int], dict[str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[str], bool]:
    rows = []
    errors = []
    for spec in frontier_specs(manifest):
        root = run_root / frontier_run_name(spec)
        if not root.exists():
            continue
        try:
            run = load_run(root, spec)
            actual_budget = run["controls"].get("oracle_byte_budget")
            if actual_budget != spec["budget"]:
                raise ValueError(
                    f"oracle budget mismatch: expected {spec['budget']}, got {actual_budget}"
                )
            baseline = by_round[(spec["workload"], spec["burst_intensity"], spec["repeat"])].get(
                "no_control"
            )
            if baseline is None:
                raise ValueError("frontier point has no matched no-control run")
            if run["outputs"] != baseline["outputs"]:
                raise ValueError("frontier output hashes differ from no-control")
            rows.append(
                {
                    **{key: value for key, value in run.items() if key != "outputs"},
                    "oracle_byte_budget": spec["budget"],
                    "p95_improvement_vs_no_control_pct": pct_improvement(
                        baseline["ttft_ms"]["p95"], run["ttft_ms"]["p95"]
                    ),
                    "goodput_loss_vs_no_control_pct": pct_improvement(
                        baseline["goodput_rps"], run["goodput_rps"]
                    ),
                }
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"frontier sequence {spec['sequence']}: {exc}")
    complete = len(rows) == len(frontier_specs(manifest)) and not errors
    return rows, errors, complete


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# G0 formal pathology gate",
        "",
        f"**Status: {report['status']}; verdict: {report['verdict']}.**",
        "",
        f"Validated runs: {len(report['runs'])}/{report['expected_runs']}.",
    ]
    if report.get("planned_but_not_executed_sequences"):
        missing = report["planned_but_not_executed_sequences"]
        lines.append(
            f" Planned-but-not-executed sequence range: {missing[0]}–{missing[-1]}."
        )
    if report.get("execution_identity_correction"):
        record = report["execution_identity_correction"]["record"]
        lines.extend(
            [
                "",
                "Execution identity has a disclosed post-hoc carrier correction; "
                f"owner acknowledgement required: {str(record['owner_acknowledgement_required']).lower()}.",
            ]
        )
    if report["errors"]:
        lines.extend(["", "## Incomplete or invalid inputs", ""])
        lines.extend(f"- {error}" for error in report["errors"])
    if report["cells"]:
        lines.extend(
            [
                "",
                "## Pathology cells",
                "",
                "| Cell | Repeat p95 regression | Median (bootstrap 95% CI) | Median oracle goodput loss | Materialization counters | Generic equivalent |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for name, row in sorted(report["cells"].items()):
            repeat_text = ", ".join(f"{value:.2f}%" for value in row["repeat_p95_regression_pct"])
            ci = row["median_p95_regression_bootstrap_ci"]
            lines.append(
                f"| {name} | {repeat_text} | {row['median_p95_regression_pct']:.2f}% "
                f"([{ci['lower_pct']:.2f}%, {ci['upper_pct']:.2f}%]) | "
                f"{row['median_goodput_loss_pct']:.2f}% | "
                f"{str(row['materialization_counter_gate']).lower()} | "
                f"{str(row['generic_equivalent_stop']).lower()} |"
            )
    if report["low_controls"]:
        lines.extend(["", "## Low-concurrency controls", ""])
        for name, row in sorted(report["low_controls"].items()):
            values = ", ".join(f"{value:.2f}%" for value in row["repeat_p95_regression_pct"])
            lines.append(f"- {name}: {values}; passes absence gate: {row['passes_absence_gate']}.")
    if report.get("stop_triggers"):
        lines.extend(["", "## Preregistered Stop triggers", ""])
        lines.extend(
            f"- {row['cell']}: `{row['trigger']}`."
            for row in report["stop_triggers"]
        )
    lines.extend(["", f"Reason: {report['reason']}", ""])
    return "\n".join(lines)


def pathology_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for run in report["runs"]:
        if run["burst_intensity"] == "low_control" or run["arm"] not in {
            "no_control",
            ORACLE,
        }:
            continue
        for row in run["reuse_pressure"]:
            grouped[
                (
                    run["workload"],
                    run["burst_intensity"],
                    run["arm"],
                    int(row["reuse_tokens"]),
                )
            ].append(row)

    output = []
    metrics = (
        "requested_bytes_mean",
        "connector_queue_wait_ms_p95",
        "layer_ready_wait_ms_p95",
        "bytes_in_flight_p95",
    )
    for (workload, intensity, arm, reuse_tokens), rows in sorted(grouped.items()):
        summary = {
            "workload": workload,
            "burst_intensity": intensity,
            "arm": arm,
            "reuse_tokens": reuse_tokens,
            "repeats": len(rows),
            "requests_per_repeat": median([float(row["requests"]) for row in rows]),
        }
        for metric in metrics:
            values = [float(row[metric]) for row in rows if row[metric] is not None]
            summary[metric] = median(values) if values else None
        output.append(summary)
    return output


def write_pathology_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "workload",
        "burst_intensity",
        "arm",
        "reuse_tokens",
        "repeats",
        "requests_per_repeat",
        "requested_bytes_mean",
        "connector_queue_wait_ms_p95",
        "layer_ready_wait_ms_p95",
        "bytes_in_flight_p95",
    ]
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_pathology_svg(rows: list[dict[str, Any]], path: Path) -> None:
    """Write a dependency-free grouped-bar view of layer-ready pressure."""
    selected = [row for row in rows if row["layer_ready_wait_ms_p95"] is not None]
    categories = sorted(
        {(row["workload"], row["burst_intensity"], row["reuse_tokens"]) for row in selected}
    )
    lookup = {
        (row["workload"], row["burst_intensity"], row["reuse_tokens"], row["arm"]): float(
            row["layer_ready_wait_ms_p95"]
        )
        for row in selected
    }
    width, height = 1200, 620
    left, right, top, bottom = 85, 30, 70, 165
    plot_w, plot_h = width - left - right, height - top - bottom
    maximum = max(lookup.values(), default=1.0) * 1.1 or 1.0
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="600" y="32" text-anchor="middle" font-family="sans-serif" font-size="20">G0 materialization pressure by burst intensity and KV reuse</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#333"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#333"/>',
    ]
    for tick in range(6):
        value = maximum * tick / 5
        y = top + plot_h - plot_h * tick / 5
        svg.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#ddd"/>')
        svg.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11">{value:.2f}</text>'
        )
    group_w = plot_w / max(1, len(categories))
    colors = {"no_control": "#3569b0", ORACLE: "#e68632"}
    for index, (workload, intensity, reuse_tokens) in enumerate(categories):
        center = left + group_w * (index + 0.5)
        for offset, arm in ((-0.18, "no_control"), (0.18, ORACLE)):
            value = lookup.get((workload, intensity, reuse_tokens, arm))
            if value is None:
                continue
            bar_w = max(4.0, group_w * 0.28)
            bar_h = plot_h * value / maximum
            x = center + group_w * offset - bar_w / 2
            y = top + plot_h - bar_h
            svg.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{colors[arm]}"/>'
            )
        label = html.escape(f"{workload}/{intensity}/{reuse_tokens}")
        svg.append(
            f'<text x="{center:.1f}" y="{top + plot_h + 14}" transform="rotate(55 {center:.1f} {top + plot_h + 14})" text-anchor="start" font-family="sans-serif" font-size="10">{label}</text>'
        )
    svg.extend(
        [
            f'<text x="18" y="{top + plot_h / 2:.1f}" transform="rotate(-90 18 {top + plot_h / 2:.1f})" text-anchor="middle" font-family="sans-serif" font-size="13">Layer-ready wait p95 (ms)</text>',
            '<rect x="930" y="48" width="12" height="12" fill="#3569b0"/><text x="948" y="59" font-family="sans-serif" font-size="12">no control</text>',
            '<rect x="1030" y="48" width="12" height="12" fill="#e68632"/><text x="1048" y="59" font-family="sans-serif" font-size="12">paced oracle</text>',
            "</svg>",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(svg) + "\n", encoding="utf-8")


def rebuild(suite: Path, run_root: Path) -> dict[str, Any]:
    manifest = read_json(suite / "suite_manifest.json")
    identity_path = suite / "execution_identity_posthoc_correction.json"
    identity_correction = None
    if identity_path.is_file():
        identity_correction = read_json(identity_path)
        if not identity_correction.get("posthoc_correction"):
            raise ValueError("execution identity sidecar is not marked as a post-hoc correction")
        identity_correction = {
            "artifact": artifact(identity_path),
            "record": identity_correction,
        }
    runs = []
    errors = []
    missing_sequences = []
    for spec in manifest["schedule"]:
        root = run_root / run_name(spec)
        if not root.exists():
            missing_sequences.append(spec["sequence"])
            continue
        try:
            runs.append(load_run(root, spec))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"sequence {spec['sequence']}: {exc}")

    by_round: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for run in runs:
        key = (run["workload"], run["burst_intensity"], run["repeat"])
        by_round[key][run["arm"]] = run

    for key, arms in sorted(by_round.items()):
        if len(arms) < 2:
            continue
        reference = next(iter(arms.values()))["outputs"]
        for arm, run in arms.items():
            if run["outputs"] != reference:
                errors.append(f"output hash mismatch in {key}: {arm}")

    by_cell_outputs: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        by_cell_outputs[(run["workload"], run["burst_intensity"])].append(run)
    for key, cell_runs in sorted(by_cell_outputs.items()):
        reference = cell_runs[0]["outputs"]
        for run in cell_runs[1:]:
            if run["outputs"] != reference:
                errors.append(
                    f"cross-repeat output hash mismatch in {key}: "
                    f"repeat {run['repeat']} arm {run['arm']}"
                )

    cells = {}
    low_controls = {}
    workloads = sorted({spec["workload"] for spec in manifest["schedule"]})
    intensities = sorted(
        {spec["burst_intensity"] for spec in manifest["schedule"] if not spec["low_concurrency_control"]}
    )
    repeats = int(manifest["repeats"])
    if not errors:
        for workload in workloads:
            for intensity in intensities:
                rounds = [by_round[(workload, intensity, repeat)] for repeat in range(1, repeats + 1)]
                # A complete three-repeat cell is sufficient to trigger a
                # preregistered Stop. Deliberately unexecuted later cells are
                # not evidence errors after that trigger.
                if all(set(arms) == MAIN_ARMS for arms in rounds):
                    cells[f"{workload}/{intensity}"] = cell_evidence(rounds)
            rounds = [by_round[(workload, "low_control", repeat)] for repeat in range(1, repeats + 1)]
            if all(set(arms) == {"no_control", ORACLE} for arms in rounds):
                values = [
                    pct_regression(arms["no_control"]["ttft_ms"]["p95"], arms[ORACLE]["ttft_ms"]["p95"])
                    for arms in rounds
                ]
                low_controls[workload] = {
                    "repeat_p95_regression_pct": values,
                    "median_p95_regression_pct": median(values),
                    "passes_absence_gate": median(values) < 10.0,
                }

    frontier, frontier_errors, frontier_complete = summarize_frontier(
        manifest, run_root, by_round
    )
    errors.extend(frontier_errors)

    executed_sequences = sorted(run["sequence"] for run in runs)
    execution_prefix_complete = executed_sequences == list(
        range(1, max(executed_sequences, default=0) + 1)
    )
    stop_triggers = preregistered_stop_triggers(cells)

    verdict = "none"
    status = "incomplete_no_verdict"
    reason = "formal matrix is incomplete or contains invalid artifacts"
    early_stop = bool(stop_triggers) and execution_prefix_complete and not errors
    if early_stop:
        verdict = "stop"
        status = "complete_early_stop"
        reason = (
            "a complete frozen three-repeat cell triggered a preregistered Stop; "
            "later matrix entries were intentionally not executed"
        )
    elif not errors and not missing_sequences:
        status = "complete"
        generic_stop = any(row["generic_equivalent_stop"] for row in cells.values())
        pathology_ok = len(cells) >= 4 and all(
            row["reproducible_tail_gate"] and row["materialization_counter_gate"]
            for row in cells.values()
        )
        low_ok = len(low_controls) >= 2 and all(
            row["passes_absence_gate"] for row in low_controls.values()
        )
        capacity_ok = all(row["capacity_preserving_gate"] for row in cells.values())
        if generic_stop:
            verdict = "stop"
            reason = "a generic concurrency or request-rate baseline is equivalent to the oracle"
        elif not pathology_ok:
            verdict = "stop"
            reason = "the >=10% repeatable materialization-specific tail pathology gate failed"
        elif not low_ok:
            verdict = "stop"
            reason = "the low-concurrency control shows the same >=10% gap"
        elif capacity_ok:
            verdict = "go"
            reason = "all preregistered pathology, capacity, specificity, and correctness gates pass"
        elif frontier_complete:
            verdict = "go"
            reason = "pathology gates pass and the frozen frontier reports the capacity-tail boundary"
        else:
            status = "needs_capacity_frontier"
            reason = "tail pathology is present but oracle goodput differs by >5%; rebuild after the frozen capacity frontier"

    public_runs = [{key: value for key, value in run.items() if key != "outputs"} for run in runs]
    return {
        "schema_version": 1,
        "artifact": "g0-formal-pathology-gate",
        "status": status,
        "verdict": verdict,
        "reason": reason,
        "suite": artifact(suite / "suite_manifest.json"),
        "execution_identity_correction": identity_correction,
        "run_root": str(run_root.resolve()),
        "expected_runs": len(manifest["schedule"]),
        "expected_frontier_runs": len(frontier_specs(manifest)),
        "runs": public_runs,
        "executed_sequences": executed_sequences,
        "execution_prefix_complete": execution_prefix_complete,
        "planned_but_not_executed_sequences": missing_sequences,
        "stop_triggers": stop_triggers,
        "capacity_frontier": frontier,
        "capacity_frontier_complete": frontier_complete,
        "errors": errors,
        "cells": cells,
        "low_controls": low_controls,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite-dir", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    parser.add_argument("--output-pathology-csv")
    parser.add_argument("--output-pathology-svg")
    args = parser.parse_args()
    report = rebuild(Path(args.suite_dir).resolve(), Path(args.run_root).resolve())
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_markdown.write_text(markdown(report), encoding="utf-8")
    rows = pathology_rows(report)
    if args.output_pathology_csv:
        write_pathology_csv(rows, Path(args.output_pathology_csv))
    if args.output_pathology_svg:
        write_pathology_svg(rows, Path(args.output_pathology_svg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
