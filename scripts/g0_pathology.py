#!/usr/bin/env python3
"""Fail-closed artifacts for the G0 KV-materialization congestion gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

WORKLOADS = ("burstgpt", "servegen")
INTENSITIES = ("moderate", "high")
INTENSITY_RPS = {"low_control": 1.0, "moderate": 8.0, "high": 32.0}
ARMS = ("no_control", "always_recompute", "concurrency_cap", "request_token_bucket", "minimum_retrieve_threshold", "fixed_prefetch_depth", "materialization_paced_oracle")
REPEATS = 3
REQUIRED_TELEMETRY = {"request_id", "requested_materialization_bytes", "realized_materialization_bytes", "bytes_in_flight", "connector_queue_depth", "connector_queue_wait_ms", "layer_ready_wait_ms", "transfer_busy_ms", "compute_busy_ms", "hbm_peak_bytes", "dram_peak_bytes", "realized_reuse_tokens", "fallback_reason", "waiting_reason", "activation_counter"}
REQUIRED_REQUEST = {"request_id", "ok", "ttft_ms", "e2e_ms", "tpot_ms", "output_tokens"}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("cannot calculate percentile of no values")
    values = sorted(values)
    return values[math.ceil((len(values) - 1) * q / 100)]


def git_commit(path: Path) -> str:
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], text=True, capture_output=True, check=True).stdout.strip()


def canonical_trace_rows(path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    if not rows:
        raise ValueError(f"empty trace: {path}")
    normalized = []
    for index, row in enumerate(rows):
        request_id = str(row.get("request_id", row.get("id", index)))
        arrival_s = row.get("arrival_s", row.get("timestamp_s", row.get("timestamp")))
        content = row.get("content", row.get("prompt", row.get("text")))
        prompt_token_ids = row.get("prompt_token_ids")
        if not isinstance(arrival_s, (int, float)):
            raise ValueError(f"trace row {index} needs arrival_s/timestamp")
        if not isinstance(content, str) and not (
            isinstance(prompt_token_ids, list)
            and prompt_token_ids
            and all(isinstance(token, int) for token in prompt_token_ids)
        ):
            raise ValueError(
                f"trace row {index} needs content/prompt/text or prompt_token_ids"
            )
        normalized.append({**row, "request_id": request_id, "arrival_s": float(arrival_s)})
    if len({row["request_id"] for row in normalized}) != len(normalized):
        raise ValueError("trace request IDs must be unique")
    return normalized


def write_overlay(trace: Path, output: Path, workload: str, burst_intensity: str) -> dict[str, Any]:
    rows = canonical_trace_rows(trace)
    source_start = rows[0]["arrival_s"]
    source_span = rows[-1]["arrival_s"] - source_start
    if source_span <= 0:
        raise ValueError(f"trace needs positive arrival span: {trace}")
    target_span = (len(rows) - 1) / INTENSITY_RPS[burst_intensity]
    scale = target_span / source_span
    overlay = []
    for index, row in enumerate(rows):
        identity = row.get("prompt_token_ids", row.get("content"))
        content_digest = hashlib.sha256(
            json.dumps(identity, separators=(",", ":")).encode()
        ).hexdigest()
        prefix_tokens = int(row.get("reuse_prefix_tokens", 0))
        # A low-concurrency control must remove instantaneous source bursts,
        # not merely lower their mean rate. Keep content and order identical
        # while assigning deterministic one-request-per-second arrivals.
        arrival_s = (
            index / INTENSITY_RPS[burst_intensity]
            if burst_intensity == "low_control"
            else (row["arrival_s"] - source_start) * scale
        )
        overlay.append({
            **row,
            "arrival_s": arrival_s,
            "sequence_index": index,
            "prefix_key": f"{workload}:prefix:{prefix_tokens}",
            "session_key": f"{workload}:session:{index // 4:06d}",
            "content_sha256": content_digest,
            "target_materialization_bytes": int(row.get("target_materialization_bytes", max(4096, prefix_tokens * 31104))),
            "burst_intensity": burst_intensity,
        })
    with output.open("w", encoding="utf-8") as destination:
        for row in overlay:
            destination.write(json.dumps(row, sort_keys=True) + "\n")
    return {"trace": str(trace.resolve()), "trace_sha256": sha256(trace), "overlay": str(output.resolve()), "overlay_sha256": sha256(output), "requests": len(overlay), "workload": workload, "burst_intensity": burst_intensity, "arrival_transform": "uniform_low_concurrency" if burst_intensity == "low_control" else "source_shape_scaled"}


def init_suite(args: argparse.Namespace) -> int:
    suite, root = Path(args.suite_dir).resolve(), Path(__file__).resolve().parents[1]
    if suite.exists():
        raise SystemExit(f"refusing to overwrite suite directory: {suite}")
    suite.mkdir(parents=True)
    custody = []
    for workload, trace_arg in (("burstgpt", args.burstgpt_trace), ("servegen", args.servegen_trace)):
        trace = Path(trace_arg)
        if not trace.is_file():
            raise SystemExit(f"missing immutable trace for {workload}: {trace}")
        for intensity in (*INTENSITIES, "low_control"):
            custody.append(write_overlay(trace, suite / f"{workload}_{intensity}_overlay.jsonl", workload, intensity))
    schedule, sequence = [], 0
    for workload in WORKLOADS:
        for intensity in INTENSITIES:
            for repeat in range(1, REPEATS + 1):
                order = ARMS[repeat - 1:] + ARMS[:repeat - 1]
                for order_index, arm in enumerate(order, 1):
                    sequence += 1
                    schedule.append({"sequence": sequence, "workload": workload, "burst_intensity": intensity, "repeat": repeat, "order_index": order_index, "arm": arm, "low_concurrency_control": False})
    for workload in WORKLOADS:
        for repeat in range(1, REPEATS + 1):
            for arm in ("no_control", "materialization_paced_oracle"):
                sequence += 1
                schedule.append({"sequence": sequence, "workload": workload, "burst_intensity": "low_control", "repeat": repeat, "order_index": 1, "arm": arm, "low_concurrency_control": True})
    write_json(suite / "suite_manifest.json", {"schema_version": 1, "study": "G0 burst-aware KV materialization pathology gate", "status": "initialized", "parent_commit": git_commit(root), "carrier_gitlink": git_commit(root / "vendor/vllm"), "repeats": REPEATS, "arms": ARMS, "required_telemetry": sorted(REQUIRED_TELEMETRY), "trace_overlay_custody": custody, "schedule": schedule})
    return 0


def load_bundle(bundle: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    paths = (bundle / "run_manifest.json", bundle / "request_results.jsonl", bundle / "materialization_telemetry.jsonl")
    if not all(path.is_file() for path in paths):
        raise ValueError(f"incomplete raw bundle: {bundle}")
    manifest, requests, telemetry = json.loads(paths[0].read_text()), read_jsonl(paths[1]), read_jsonl(paths[2])
    if not requests or len(requests) != len(telemetry):
        raise ValueError(f"request/telemetry count mismatch: {bundle}")
    request_ids = {row.get("request_id") for row in requests}
    if request_ids != {row.get("request_id") for row in telemetry} or None in request_ids:
        raise ValueError(f"request/telemetry ID mismatch: {bundle}")
    for row in requests:
        missing = REQUIRED_REQUEST - row.keys()
        if missing or not row["ok"]:
            raise ValueError(f"request correctness failure in {bundle}: missing={sorted(missing)}")
    for row in telemetry:
        missing = REQUIRED_TELEMETRY - row.keys()
        if missing or not row["activation_counter"]:
            raise ValueError(f"telemetry activation failure in {bundle}: missing={sorted(missing)}")
    return manifest, requests, telemetry


def summarize_bundle(bundle: Path) -> dict[str, Any]:
    manifest, requests, telemetry = load_bundle(bundle)
    duration_s = max(float(row["e2e_ms"]) for row in requests) / 1000
    return {"bundle": str(bundle), **{key: manifest[key] for key in ("workload", "burst_intensity", "repeat", "arm")}, "requests": len(requests), "p95_ttft_ms": percentile([float(row["ttft_ms"]) for row in requests], 95), "mean_e2e_ms": statistics.mean(float(row["e2e_ms"]) for row in requests), "mean_tpot_ms": statistics.mean(float(row["tpot_ms"]) for row in requests), "goodput_rps": len(requests) / duration_s if duration_s else 0.0, "materialization_pressure": statistics.mean(float(row["connector_queue_wait_ms"]) + float(row["layer_ready_wait_ms"]) + float(row["bytes_in_flight"]) / max(1, float(row["requested_materialization_bytes"])) for row in telemetry)}


def rebuild(args: argparse.Namespace) -> int:
    suite = Path(args.suite_dir).resolve()
    meta = json.loads((suite / "suite_manifest.json").read_text())
    by_cell: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    summaries, errors = [], []
    for spec in meta["schedule"]:
        bundle = suite / "runs" / f"{spec['sequence']:03d}_{spec['arm']}"
        try:
            summary = summarize_bundle(bundle)
            if any(summary[key] != spec[key] for key in ("workload", "burst_intensity", "repeat", "arm")):
                raise ValueError("bundle manifest does not match preregistered schedule")
            summaries.append(summary); by_cell[(spec["workload"], spec["burst_intensity"], spec["repeat"])][spec["arm"]] = summary
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"sequence {spec['sequence']}: {exc}")
    evidence, verdict = [], "stop"
    if not errors:
        for workload in WORKLOADS:
            for intensity in INTENSITIES:
                rounds = [by_cell[(workload, intensity, repeat)] for repeat in range(1, REPEATS + 1)]
                if any(set(item) != set(ARMS) for item in rounds):
                    errors.append(f"incomplete arm matrix: {workload}/{intensity}"); continue
                regression = statistics.median((r["no_control"]["p95_ttft_ms"] / r["materialization_paced_oracle"]["p95_ttft_ms"] - 1) * 100 for r in rounds)
                generic = min(statistics.median((r["no_control"]["p95_ttft_ms"] / r[arm]["p95_ttft_ms"] - 1) * 100 for r in rounds) for arm in ("concurrency_cap", "request_token_bucket"))
                pressure = statistics.median(r["no_control"]["materialization_pressure"] - r["materialization_paced_oracle"]["materialization_pressure"] for r in rounds)
                goodput = max(abs(r["no_control"]["goodput_rps"] / r["materialization_paced_oracle"]["goodput_rps"] - 1) * 100 for r in rounds)
                evidence.append({"workload": workload, "burst_intensity": intensity, "p95_regression_pct": regression, "generic_cap_effect_pct": generic, "pressure_gap": pressure, "max_goodput_gap_pct": goodput})
        low_equal = False
        for workload in WORKLOADS:
            rounds = [by_cell[(workload, "low_control", repeat)] for repeat in range(1, REPEATS + 1)]
            if any(set(item) != {"no_control", "materialization_paced_oracle"} for item in rounds):
                errors.append(f"incomplete low control: {workload}"); continue
            low_equal |= statistics.median((r["no_control"]["p95_ttft_ms"] / r["materialization_paced_oracle"]["p95_ttft_ms"] - 1) * 100 for r in rounds) >= 10
        if not errors and not low_equal and all(row["p95_regression_pct"] >= 10 and row["pressure_gap"] > 0 and row["generic_cap_effect_pct"] < row["p95_regression_pct"] - 1 and row["max_goodput_gap_pct"] <= 5 for row in evidence):
            verdict = "go"
    output = suite / "generated"; output.mkdir(exist_ok=True)
    write_json(output / "g0_runs.json", summaries)
    write_json(output / "g0_verdict.json", {"verdict": verdict, "errors": errors, "evidence": evidence, "reason": "G0 Go requires all preregistered materialization-specific gates"})
    return 0 if verdict == "go" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init"); init.add_argument("--suite-dir", required=True); init.add_argument("--burstgpt-trace", required=True); init.add_argument("--servegen-trace", required=True); init.set_defaults(func=init_suite)
    rebuild_cmd = sub.add_parser("rebuild"); rebuild_cmd.add_argument("--suite-dir", required=True); rebuild_cmd.set_defaults(func=rebuild)
    args = parser.parse_args(); return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
