from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


EVENT = re.compile(
    r"WAVEMAT_EVENT event=(?P<event>\w+) gate=(?P<gate>-?\d+) "
    r"ts_ns=(?P<ts>\d+)(?: (?P<fields>.*))?$"
)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[round((len(values) - 1) * fraction)]


def parse(log: Path) -> dict[str, Any]:
    starts: dict[int, int] = {}
    submits: dict[tuple[int, int], list[int]] = defaultdict(list)
    records: list[dict[str, int]] = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = EVENT.search(line)
        if match is None:
            continue
        fields = {
            key: int(value)
            for key, value in re.findall(r"(\w+)=(-?\d+)", match.group("fields") or "")
        }
        event, gate, ts = match.group("event"), int(match.group("gate")), int(match.group("ts"))
        if event == "attention_start":
            starts[gate] = ts
        elif event == "transfer_submit" and "layer" in fields:
            submits[(gate, fields["layer"])].append(ts)
        elif event == "transfer_ready" and "layer" in fields:
            key = (gate, fields["layer"])
            if submits[key]:
                submit = submits[key].pop(0)
                records.append(
                    {
                        "gate": gate,
                        "layer": fields["layer"],
                        "attention_start_ns": starts.get(gate, -1),
                        "transfer_submit_ns": submit,
                        "transfer_ready_ns": ts,
                        "copy_duration_ns": fields.get("copy_duration_ns", ts - submit),
                    }
                )

    eligible = [record for record in records if record["gate"] >= 0]
    complete = [record for record in eligible if record["attention_start_ns"] >= 0]
    copy_ms = [record["copy_duration_ns"] / 1e6 for record in complete]
    gate_to_ready_ms = [
        (record["transfer_ready_ns"] - record["attention_start_ns"]) / 1e6
        for record in complete
    ]
    return {
        "metric": "gate_correlated_synchronous_dma_completion",
        "log": str(log),
        "transfer_records": len(records),
        "eligible_prefetch_records": len(eligible),
        "records_with_attention_gate": len(complete),
        "correlation_ratio": round(len(complete) / len(eligible), 6) if eligible else 0.0,
        "copy_duration_ms": {
            "mean": round(statistics.mean(copy_ms), 6) if copy_ms else None,
            "p50": round(percentile(copy_ms, 0.50), 6) if copy_ms else None,
            "p95": round(percentile(copy_ms, 0.95), 6) if copy_ms else None,
        },
        "gate_to_ready_ms": {
            "mean": round(statistics.mean(gate_to_ready_ms), 6) if gate_to_ready_ms else None,
            "p50": round(percentile(gate_to_ready_ms, 0.50), 6) if gate_to_ready_ms else None,
            "p95": round(percentile(gate_to_ready_ms, 0.95), 6) if gate_to_ready_ms else None,
        },
        "limitations": [
            "The completion boundary is the return from synchronous aclrtMemcpyBatch, immediately before layer-ready is set.",
            "This proves gate-to-DMA-completion ordering; device trace overlap remains the separate overlap metric.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize WaveMat M0 gate-correlated DMA trace.")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = parse(args.log)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
