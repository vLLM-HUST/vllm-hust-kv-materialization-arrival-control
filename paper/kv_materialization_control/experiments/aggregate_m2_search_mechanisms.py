from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ACTIONS = ("recompute", "partial_reuse", "full_reuse")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate raw M2 search/confirmation mechanism accounting."
    )
    parser.add_argument("--suite-dir", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    lifecycle_ids = set()
    for raw_suite_dir in args.suite_dir:
        suite_dir = Path(raw_suite_dir)
        suite = read_json(suite_dir / "suite_manifest.json")
        if suite.get("status") != "completed":
            raise ValueError(f"incomplete suite: {suite_dir}")
        stage = str(suite["evidence_label"])
        for validation_path in sorted(suite_dir.rglob("validation.json")):
            bundle = validation_path.parent
            validation = read_json(validation_path)
            manifest = read_json(bundle / "run_manifest.json")
            summary = read_json(bundle / "request_summary.json")
            observations = read_jsonl(bundle / "runtime_observations.jsonl")
            if not validation.get("valid"):
                raise ValueError(f"invalid bundle: {bundle}")
            lifecycle_id = str(manifest["service_lifecycle_id"])
            if lifecycle_id in lifecycle_ids:
                raise ValueError(f"repeated lifecycle ID: {lifecycle_id}")
            lifecycle_ids.add(lifecycle_id)
            observed = Counter(str(row["decision"]) for row in observations)
            effective = Counter(
                str(row["runtime_effective_decision"]) for row in observations
            )
            fallback = Counter(
                str(row["runtime_fallback_reason"])
                for row in observations
                if row.get("runtime_fallback_reason")
            )
            accounting = validation["engine_accounting"]
            realized = Counter(str(row["realized_decision"]) for row in accounting)
            groups[
                (str(manifest["workload_case"]), stage, str(manifest["policy_mode"]))
            ].append(
                {
                    "requests": int(summary["requests"]),
                    "mean_ttft_ms": float(summary["mean_ttft_ms"]),
                    "mean_latency_ms": float(summary["mean_latency_ms"]),
                    "request_throughput_rps": float(summary["request_throughput_rps"]),
                    "observed": observed,
                    "effective": effective,
                    "realized": realized,
                    "fallback": fallback,
                    "reused_tokens": sum(
                        int(row["reused_tokens"]) for row in accounting
                    ),
                    "recomputed_tokens": sum(
                        int(row["recomputed_tokens"]) for row in accounting
                    ),
                    "lookup_ms": sum(
                        float(row.get("lookup_latency_ms", 0.0)) for row in accounting
                    ),
                    "commit_ms": sum(
                        float(row.get("commit_latency_ms", 0.0)) for row in accounting
                    ),
                    "tail_isolation_ms": sum(
                        float(row.get("tail_isolation_latency_ms", 0.0))
                        for row in accounting
                    ),
                }
            )

    rows = []
    for (workload, stage, policy), runs in sorted(groups.items()):
        row: dict[str, object] = {
            "workload": workload,
            "stage": stage,
            "policy_mode": policy,
            "lifecycles": len(runs),
            "requests": sum(run["requests"] for run in runs),
            "mean_ttft_ms": round(
                statistics.mean(run["mean_ttft_ms"] for run in runs), 6
            ),
            "mean_latency_ms": round(
                statistics.mean(run["mean_latency_ms"] for run in runs), 6
            ),
            "mean_request_throughput_rps": round(
                statistics.mean(run["request_throughput_rps"] for run in runs), 6
            ),
            "reused_tokens": sum(run["reused_tokens"] for run in runs),
            "recomputed_tokens": sum(run["recomputed_tokens"] for run in runs),
            "lookup_ms": round(sum(run["lookup_ms"] for run in runs), 6),
            "commit_ms": round(sum(run["commit_ms"] for run in runs), 6),
            "tail_isolation_ms": round(
                sum(run["tail_isolation_ms"] for run in runs), 6
            ),
        }
        for action in ACTIONS:
            row[f"observed_{action}"] = sum(run["observed"][action] for run in runs)
            row[f"effective_{action}"] = sum(run["effective"][action] for run in runs)
            row[f"realized_{action}"] = sum(run["realized"][action] for run in runs)
        fallback = sum((run["fallback"] for run in runs), Counter())
        row["fallback_reasons"] = json.dumps(dict(sorted(fallback.items())))
        rows.append(row)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
