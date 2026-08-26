from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from vllm_kv_materialization.offline_traces import (
    build_signals,
    load_traces,
    workload_case_to_traces,
)
from vllm_kv_materialization.policy import MaterializationPolicy

SAMPLE_TRACES: list[dict[str, Any]] = [
    {
        "trace_id": "sample-0",
        "reusable_prefix_tokens": 2048,
        "remote_kv_bytes": 64 * 1024 * 1024,
        "transfer_time_ms": 8.5,
        "recompute_time_ms": 24.0,
        "queue_pressure": 0.8,
        "ttft_sensitive": True,
        "reuse_confidence": 0.9,
    },
    {
        "trace_id": "sample-1",
        "reusable_prefix_tokens": 512,
        "remote_kv_bytes": 24 * 1024 * 1024,
        "transfer_time_ms": 9.0,
        "recompute_time_ms": 11.0,
        "queue_pressure": 0.2,
        "ttft_sensitive": False,
        "reuse_confidence": 0.6,
    },
    {
        "trace_id": "sample-2",
        "reusable_prefix_tokens": 128,
        "remote_kv_bytes": 8 * 1024 * 1024,
        "transfer_time_ms": 5.0,
        "recompute_time_ms": 4.5,
        "queue_pressure": 0.1,
        "ttft_sensitive": True,
        "reuse_confidence": 0.3,
    },
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a tiny offline KV materialization experiment harness."
    )
    parser.add_argument("--policy", default="heuristic", choices=["heuristic"])
    parser.add_argument("--trace-jsonl")
    parser.add_argument("--workload-case")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--pretty", action="store_true")
    return parser


def resolve_trace_inputs(args: argparse.Namespace) -> tuple[str, list[dict[str, Any]]]:
    if args.trace_jsonl and args.workload_case:
        raise ValueError("choose at most one of --trace-jsonl or --workload-case")

    if args.trace_jsonl:
        traces = load_traces(Path(args.trace_jsonl))
        trace_source = str(Path(args.trace_jsonl))
    elif args.workload_case:
        traces = workload_case_to_traces(args.workload_case, seed=args.seed)
        trace_source = f"shared_workload:{args.workload_case}"
    else:
        traces = list(SAMPLE_TRACES)
        trace_source = "sample_traces"

    if args.limit is not None:
        traces = traces[: max(args.limit, 0)]

    return trace_source, traces


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    del args.policy

    policy = MaterializationPolicy()
    results = []
    trace_source, traces = resolve_trace_inputs(args)
    for index, raw_trace in enumerate(traces):
        signals = build_signals(raw_trace)
        outcome = policy.decide(signals)
        results.append(
            {
                "trace_id": str(raw_trace.get("trace_id", f"sample-{index}")),
                "trace_source": trace_source,
                "workload_case": raw_trace.get("workload_case"),
                "workload_family": raw_trace.get("workload_family"),
                "signals": asdict(signals),
                "outcome": asdict(outcome),
            }
        )

    if args.pretty:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        print(json.dumps(results, sort_keys=True))


if __name__ == "__main__":
    main()
