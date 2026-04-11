from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from vllm_kv_materialization.policy import MaterializationPolicy
from vllm_kv_materialization.policy import MaterializationSignals


SAMPLE_TRACES = [
    MaterializationSignals(
        reusable_prefix_tokens=2048,
        remote_kv_bytes=64 * 1024 * 1024,
        transfer_time_ms=8.5,
        recompute_time_ms=24.0,
        queue_pressure=0.8,
        ttft_sensitive=True,
        reuse_confidence=0.9,
    ),
    MaterializationSignals(
        reusable_prefix_tokens=512,
        remote_kv_bytes=24 * 1024 * 1024,
        transfer_time_ms=9.0,
        recompute_time_ms=11.0,
        queue_pressure=0.2,
        ttft_sensitive=False,
        reuse_confidence=0.6,
    ),
    MaterializationSignals(
        reusable_prefix_tokens=128,
        remote_kv_bytes=8 * 1024 * 1024,
        transfer_time_ms=5.0,
        recompute_time_ms=4.5,
        queue_pressure=0.1,
        ttft_sensitive=True,
        reuse_confidence=0.3,
    ),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a tiny offline KV materialization experiment harness."
    )
    parser.add_argument("--policy", default="heuristic", choices=["heuristic"])
    parser.add_argument("--pretty", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    del args.policy

    policy = MaterializationPolicy()
    results = []
    for index, signals in enumerate(SAMPLE_TRACES):
        outcome = policy.decide(signals)
        results.append(
            {
                "trace_id": f"sample-{index}",
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
