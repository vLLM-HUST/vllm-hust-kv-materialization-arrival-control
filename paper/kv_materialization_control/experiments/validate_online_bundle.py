from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PREFIX_EVENT_RE = re.compile(r"Prefix cache trace (lookup|commit) request_id=([^ ]+)")
REQUIRED_OBSERVATION_FIELDS = {
    "request_id",
    "decision",
    "reused_tokens",
    "runtime_effective_decision",
    "runtime_target_reuse_tokens",
    "runtime_target_tail_tokens",
    "runtime_reused_tokens",
    "runtime_recomputed_tokens",
    "runtime_fallback_reason",
}


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def normalize_engine_request_id(request_id: str) -> str:
    normalized = request_id
    normalized = normalized.removeprefix("chatcmpl-")
    return (
        normalized.rsplit("-", 1)[0] if re.search(r"-\d+$", normalized) else normalized
    )


def validate_bundle(bundle_dir: Path) -> dict[str, object]:
    errors: list[str] = []
    required_files = [
        "environment_manifest.json",
        "run_manifest.json",
        "request_summary.json",
        "request_results.jsonl",
        "runtime_observations.jsonl",
        "server.log",
        "client.log",
        "cleanup.json",
    ]
    for name in required_files:
        if not bundle_dir.joinpath(name).is_file():
            errors.append(f"missing required file: {name}")
    if errors:
        return {"valid": False, "errors": errors}

    environment = json.loads(
        bundle_dir.joinpath("environment_manifest.json").read_text()
    )
    run_manifest = json.loads(bundle_dir.joinpath("run_manifest.json").read_text())
    summary = json.loads(bundle_dir.joinpath("request_summary.json").read_text())
    cleanup = json.loads(bundle_dir.joinpath("cleanup.json").read_text())
    requests = read_jsonl(bundle_dir / "request_results.jsonl")
    observations = read_jsonl(bundle_dir / "runtime_observations.jsonl")
    server_log = bundle_dir.joinpath("server.log").read_text(
        encoding="utf-8", errors="replace"
    )

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
            f"request/observation ID mismatch: missing={sorted(request_ids - observation_ids)} extra={sorted(observation_ids - request_ids)}"
        )
    for index, observation in enumerate(observations):
        missing = REQUIRED_OBSERVATION_FIELDS - observation.keys()
        if missing:
            errors.append(f"observation {index} missing fields: {sorted(missing)}")
    for index, request in enumerate(requests):
        if request.get("ok") and request.get("ttft_s") is None:
            errors.append(f"successful request {index} missing TTFT")
        if request.get("ok") and not request.get("raw_events"):
            errors.append(f"successful request {index} missing raw SSE events")

    runtime_events: dict[str, set[str]] = {}
    for event, raw_request_id in PREFIX_EVENT_RE.findall(server_log):
        request_id = normalize_engine_request_id(raw_request_id)
        runtime_events.setdefault(request_id, set()).add(event)
    missing_runtime_events = sorted(
        request_id
        for request_id in request_ids
        if runtime_events.get(str(request_id)) != {"lookup", "commit"}
    )
    if missing_runtime_events:
        errors.append(
            f"requests missing runtime lookup/commit events: {missing_runtime_events}"
        )
    if environment.get("parent", {}).get("dirty") or environment.get("carrier", {}).get(
        "dirty"
    ):
        errors.append("parent or carrier was dirty at run start")
    if run_manifest.get("status") != "completed":
        errors.append(f"run status is not completed: {run_manifest.get('status')}")
    if not cleanup.get("port_free_after") or not cleanup.get("device_idle_after"):
        errors.append("cleanup did not prove both port and device idle")

    return {
        "valid": not errors,
        "errors": errors,
        "request_count": len(requests),
        "completed": sum(bool(row.get("ok")) for row in requests),
        "failed": sum(not bool(row.get("ok")) for row in requests),
        "observation_count": len(observations),
        "runtime_event_request_count": len(runtime_events),
        "decision_mix": {
            decision: sum(
                row.get("runtime_effective_decision") == decision
                for row in observations
            )
            for decision in ("recompute", "partial_reuse", "full_reuse")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one auditable real-online bundle."
    )
    parser.add_argument("bundle_dir")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = validate_bundle(Path(args.bundle_dir).resolve())
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
