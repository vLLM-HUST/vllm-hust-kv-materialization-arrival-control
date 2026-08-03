from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

REQUIRED_OBSERVATION_FIELDS = {
    "request_id",
    "decision",
    "runtime_effective_decision",
    "runtime_target_reuse_tokens",
    "runtime_target_tail_tokens",
    "runtime_fallback_reason",
}
FORMAL_LABEL = "real-online/formal-matrix"
DRY_RUN_LABEL = "real-online/carrier-validation-dry-run"
M2_LABEL = "real-online/m2-benefit-boundary"
M2_PILOT_LABEL = "real-online/m2-candidate-pilot"
M2_ANCHOR_PILOT_LABEL = "real-online/m2-anchor-candidate-pilot"
M2_ANCHOR_CONFIRMATION_LABEL = "real-online/m2-anchor-confirmation"
RAW_RECOMPUTABLE_SUMMARY_FIELDS = (
    "requests",
    "completed",
    "failures",
    "mean_latency_ms",
    "p95_latency_ms",
    "mean_ttft_ms",
    "p95_ttft_ms",
)


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def normalize_engine_request_id(request_id: str, workload_request_ids: set[str]) -> str:
    normalized = request_id.removeprefix("chatcmpl-")
    matches = [
        candidate
        for candidate in workload_request_ids
        if normalized == candidate or normalized.startswith(f"{candidate}-")
    ]
    return max(matches, key=len) if matches else normalized


def request_percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((q / 100.0) * (len(ordered) - 1))))
    return ordered[index]


def recompute_request_summary(requests: list[dict]) -> dict[str, object]:
    successful = [row for row in requests if row.get("ok")]
    failures = [row for row in requests if not row.get("ok")]
    latencies_ms = [float(row["latency_s"]) * 1000.0 for row in successful]
    ttfts_ms = [
        float(row["ttft_s"]) * 1000.0
        for row in successful
        if row.get("ttft_s") is not None
    ]
    return {
        "requests": len(requests),
        "completed": len(successful),
        "failures": failures,
        "mean_latency_ms": round(mean(latencies_ms), 3) if latencies_ms else 0.0,
        "p95_latency_ms": (
            round(request_percentile(latencies_ms, 95), 3) if latencies_ms else 0.0
        ),
        "mean_ttft_ms": round(mean(ttfts_ms), 3) if ttfts_ms else 0.0,
        "p95_ttft_ms": (
            round(request_percentile(ttfts_ms, 95), 3) if ttfts_ms else 0.0
        ),
    }


def verify_request_summary(
    summary: dict, requests: list[dict]
) -> tuple[dict[str, object], list[str]]:
    recomputed = recompute_request_summary(requests)
    errors = []
    for field in RAW_RECOMPUTABLE_SUMMARY_FIELDS:
        if summary.get(field) != recomputed[field]:
            errors.append(
                f"summary {field}={summary.get(field)!r} does not match "
                f"raw request result {recomputed[field]!r}"
            )
    return recomputed, errors


def validate_bundle(
    bundle_dir: Path,
    *,
    expected_evidence_label: str | None = None,
    require_realized_partial: bool = False,
) -> dict[str, object]:
    errors: list[str] = []
    required_files = [
        "environment_manifest.json",
        "run_manifest.json",
        "request_summary.json",
        "request_results.jsonl",
        "runtime_observations.jsonl",
        "runtime_events.jsonl",
        "server.log",
        "client.log",
        "cleanup.json",
    ]
    for name in required_files:
        if not bundle_dir.joinpath(name).is_file():
            errors.append(f"missing required file: {name}")
    if errors:
        return {"valid": False, "errors": errors}

    environment = json.loads((bundle_dir / "environment_manifest.json").read_text())
    manifest = json.loads((bundle_dir / "run_manifest.json").read_text())
    summary = json.loads((bundle_dir / "request_summary.json").read_text())
    cleanup = json.loads((bundle_dir / "cleanup.json").read_text())
    requests = read_jsonl(bundle_dir / "request_results.jsonl")
    observations = read_jsonl(bundle_dir / "runtime_observations.jsonl")
    engine_events = read_jsonl(bundle_dir / "runtime_events.jsonl")
    is_m2 = expected_evidence_label == M2_LABEL or (
        environment.get("evidence_label") == M2_LABEL
        and manifest.get("evidence_label") == M2_LABEL
    )

    recomputed_summary, summary_errors = verify_request_summary(summary, requests)
    errors.extend(summary_errors)

    request_ids = {row.get("request_id") for row in requests}
    observation_ids = {row.get("request_id") for row in observations}
    if len(requests) != int(summary.get("requests", -1)):
        errors.append(
            f"per-request count {len(requests)} != summary requests {summary.get('requests')}"
        )
    if len(request_ids) != len(requests) or None in request_ids:
        errors.append("per-request IDs are missing or duplicated")
    if request_ids != observation_ids:
        errors.append(
            "request/observation ID mismatch: "
            f"missing={sorted(request_ids - observation_ids)} "
            f"extra={sorted(observation_ids - request_ids)}"
        )
    observations_by_id = {row.get("request_id"): row for row in observations}
    for index, observation in enumerate(observations):
        missing = REQUIRED_OBSERVATION_FIELDS - observation.keys()
        if missing:
            errors.append(f"observation {index} missing fields: {sorted(missing)}")
        if (
            "runtime_reused_tokens" in observation
            or "runtime_recomputed_tokens" in observation
        ):
            errors.append(
                f"observation {index} contains deprecated planner-derived runtime counters"
            )
        if is_m2:
            for field in (
                "policy_mode",
                "decision_latency_ms",
                "boundary_alignment_latency_ms",
                "controller_latency_ms",
            ):
                if field not in observation:
                    errors.append(f"M2 observation {index} missing field: {field}")
    for index, request in enumerate(requests):
        if request.get("ok") and request.get("ttft_s") is None:
            errors.append(f"successful request {index} missing TTFT")
        if request.get("ok") and not request.get("raw_events"):
            errors.append(f"successful request {index} missing raw SSE events")

    events_by_id: dict[str, list[dict]] = defaultdict(list)
    for index, event in enumerate(engine_events):
        raw_id = event.get("request_id")
        if not isinstance(raw_id, str):
            errors.append(f"engine event {index} missing request_id")
            continue
        normalized = normalize_engine_request_id(raw_id, request_ids)
        if normalized not in request_ids:
            errors.append(f"engine event {index} has unknown request_id: {raw_id}")
            continue
        events_by_id[normalized].append(event)

    realized_mix: Counter[str] = Counter()
    accounting_rows: list[dict] = []
    for request_id in sorted(str(value) for value in request_ids):
        events = events_by_id.get(request_id, [])
        lookups = [row for row in events if row.get("event") == "lookup"]
        commits = [row for row in events if row.get("event") == "commit"]
        if len(lookups) != 1:
            errors.append(
                f"request {request_id} has {len(lookups)} engine lookup events"
            )
            continue
        if not commits:
            errors.append(f"request {request_id} has no engine commit event")
        lookup = lookups[0]
        observation = observations_by_id.get(request_id, {})
        prompt = lookup.get("engine_prompt_tokens")
        reused = lookup.get("engine_reused_tokens")
        recomputed = lookup.get("engine_recomputed_tokens")
        if not all(isinstance(value, int) for value in (prompt, reused, recomputed)):
            errors.append(f"request {request_id} engine counters are not integers")
            continue
        if prompt != observation.get("prompt_tokens"):
            errors.append(
                f"request {request_id} prompt mismatch engine={prompt} "
                f"planner={observation.get('prompt_tokens')}"
            )
        if reused < 0 or recomputed < 0 or reused + recomputed != prompt:
            errors.append(
                f"request {request_id} token accounting does not close: "
                f"reused={reused} recomputed={recomputed} prompt={prompt}"
            )
        if lookup.get("applied_decision") != observation.get(
            "runtime_effective_decision"
        ):
            errors.append(f"request {request_id} applied/effective decision mismatch")
        if lookup.get("observed_decision") != observation.get("decision"):
            errors.append(f"request {request_id} observed decision mismatch")
        if lookup.get("fallback_reason") != observation.get("runtime_fallback_reason"):
            errors.append(f"request {request_id} fallback reason mismatch")
        if lookup.get("target_reuse_tokens") != observation.get(
            "runtime_target_reuse_tokens"
        ):
            errors.append(f"request {request_id} target reuse mismatch")
        block_size = lookup.get("hash_block_size")
        if reused and (not isinstance(block_size, int) or reused % block_size):
            errors.append(f"request {request_id} reused boundary is not block aligned")
        realized = lookup.get("realized_decision")
        expected_realized = (
            "recompute"
            if reused == 0
            else "full_reuse"
            if recomputed == 0
            else "partial_reuse"
        )
        if realized != expected_realized:
            errors.append(f"request {request_id} realized decision is inconsistent")
        if is_m2:
            for field in (
                "lookup_latency_ms",
                "tail_isolation_latency_ms",
                "cache_usage",
            ):
                if not isinstance(lookup.get(field), (int, float)):
                    errors.append(
                        f"request {request_id} lookup missing numeric {field}"
                    )
            for commit in commits:
                for field in ("commit_latency_ms", "cache_usage"):
                    if not isinstance(commit.get(field), (int, float)):
                        errors.append(
                            f"request {request_id} commit missing numeric {field}"
                        )
        realized_mix[str(realized)] += 1
        accounting_row = {
            "request_id": request_id,
            "prompt_tokens": prompt,
            "reused_tokens": reused,
            "recomputed_tokens": recomputed,
            "realized_decision": realized,
        }
        if is_m2:
            commit_latency_ms = sum(
                float(row.get("commit_latency_ms", 0.0)) for row in commits
            )
            cached_blocks = sum(int(row.get("cached_blocks", 0)) for row in commits)
            cache_usages = [
                float(row["cache_usage"])
                for row in (lookup, *commits)
                if isinstance(row.get("cache_usage"), (int, float))
            ]
            accounting_row.update(
                {
                    "lookup_latency_ms": lookup.get("lookup_latency_ms"),
                    "commit_latency_ms": round(commit_latency_ms, 9),
                    "tail_isolation_latency_ms": lookup.get(
                        "tail_isolation_latency_ms"
                    ),
                    "cached_blocks": cached_blocks,
                    "peak_cache_usage": max(cache_usages, default=None),
                }
            )
        accounting_rows.append(accounting_row)

    labels = {environment.get("evidence_label"), manifest.get("evidence_label")}
    expected_label = expected_evidence_label
    if len(labels) != 1 or None in labels:
        errors.append(
            f"environment/run evidence labels disagree: {sorted(map(str, labels))}"
        )
    elif expected_label and labels != {expected_label}:
        errors.append(f"evidence label {next(iter(labels))!r} != {expected_label!r}")
    if not environment.get("protocol_fingerprint"):
        errors.append("environment manifest missing protocol fingerprint")
    if environment.get("parent", {}).get("dirty") or environment.get("carrier", {}).get(
        "dirty"
    ):
        errors.append("parent or carrier was dirty at run start")
    if manifest.get("status") != "completed":
        errors.append(f"run status is not completed: {manifest.get('status')}")
    if not cleanup.get("port_free_after") or not cleanup.get("device_idle_after"):
        errors.append("cleanup did not prove both port and device idle")
    graph_evidence = environment.get("execution_mode_evidence", [])
    if not graph_evidence or not any(
        "enforce_eager=False" in line for line in graph_evidence
    ):
        errors.append("server log did not prove graph-mode configuration")
    if require_realized_partial and realized_mix["partial_reuse"] == 0:
        errors.append("dry run did not produce a nonzero realized partial reuse")
    if is_m2:
        policy_mode = manifest.get("policy_mode")
        observation_modes = {row.get("policy_mode") for row in observations}
        if policy_mode not in {
            "controller",
            "always_recompute",
            "always_full_reuse",
        }:
            errors.append(f"invalid or missing M2 policy mode: {policy_mode!r}")
        if observation_modes != {policy_mode}:
            errors.append(
                "M2 policy mode mismatch between run and observations: "
                f"{policy_mode!r} vs {sorted(map(str, observation_modes))}"
            )
        duration_s = summary.get("measurement_duration_s")
        output_tokens = summary.get("completed_output_tokens")
        if not isinstance(duration_s, (int, float)) or duration_s <= 0:
            errors.append("M2 summary missing positive measurement_duration_s")
        elif summary.get("request_throughput_rps") != round(
            int(summary.get("completed", 0)) / duration_s, 3
        ):
            errors.append("M2 request throughput does not close from raw duration")
        if not isinstance(output_tokens, int) or output_tokens < 0:
            errors.append("M2 summary missing nonnegative completed_output_tokens")
        elif (
            isinstance(duration_s, (int, float))
            and duration_s > 0
            and summary.get("output_throughput_toks")
            != round(output_tokens / duration_s, 3)
        ):
            errors.append("M2 output throughput does not close from raw duration")

    throughput_verification = {
        "status": "not_raw_recomputable",
        "reason": (
            "the historical bundle does not contain an independent raw suite "
            "measurement duration; throughput remains sourced from "
            "request_summary.json"
        ),
    }
    if is_m2:
        throughput_verification = {
            "status": "raw_recomputed",
            "measurement_duration_s": summary.get("measurement_duration_s"),
            "completed_output_tokens": summary.get("completed_output_tokens"),
            "request_throughput_rps": summary.get("request_throughput_rps"),
            "output_throughput_toks": summary.get("output_throughput_toks"),
        }

    return {
        "valid": not errors,
        "errors": errors,
        "request_count": len(requests),
        "completed": sum(bool(row.get("ok")) for row in requests),
        "failed": sum(not bool(row.get("ok")) for row in requests),
        "raw_summary_verification": {
            "valid": not summary_errors,
            "recomputed": recomputed_summary,
            "throughput": throughput_verification,
        },
        "observation_count": len(observations),
        "engine_event_count": len(engine_events),
        "engine_accounting": accounting_rows,
        "applied_decision_mix": {
            decision: sum(
                row.get("runtime_effective_decision") == decision
                for row in observations
            )
            for decision in ("recompute", "partial_reuse", "full_reuse")
        },
        "realized_decision_mix": dict(sorted(realized_mix.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one auditable real-online bundle."
    )
    parser.add_argument("bundle_dir")
    parser.add_argument("--output")
    parser.add_argument(
        "--expected-evidence-label",
        choices=(
            FORMAL_LABEL,
            DRY_RUN_LABEL,
            M2_LABEL,
            M2_PILOT_LABEL,
            M2_ANCHOR_PILOT_LABEL,
            M2_ANCHOR_CONFIRMATION_LABEL,
        ),
    )
    parser.add_argument("--require-realized-partial", action="store_true")
    args = parser.parse_args()
    result = validate_bundle(
        Path(args.bundle_dir).resolve(),
        expected_evidence_label=args.expected_evidence_label,
        require_realized_partial=args.require_realized_partial,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
