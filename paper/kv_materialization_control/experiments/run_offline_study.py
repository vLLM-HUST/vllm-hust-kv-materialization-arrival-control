from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from dataclasses import replace
from pathlib import Path
from statistics import mean

from vllm_kv_materialization.policy import MaterializationDecision
from vllm_kv_materialization.policy import MaterializationPolicy
from vllm_kv_materialization.policy import MaterializationSignals
from vllm_kv_materialization.shared_workloads import DECISION_SURFACE_CASE_ROLES
from vllm_kv_materialization.shared_workloads import generate_case_requests
from vllm_kv_materialization.shared_workloads import load_workloads_module


WORKLOADS = load_workloads_module()


CORE_POLICIES = (
    "always_recompute",
    "always_full_reuse",
    "threshold_partial",
    "heuristic",
    "oracle_ttft",
)

SENSITIVITY_POLICIES = (
    "heuristic_transfer_underestimated",
    "heuristic_transfer_overestimated",
    "heuristic_recompute_underestimated",
    "heuristic_recompute_overestimated",
)
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the offline KV materialization study and emit paper-facing summaries."
    )
    parser.add_argument("--trace-jsonl")
    parser.add_argument(
        "--workload-case",
        action="append",
        default=[],
        help="Shared workload case id from llm-serving-workloads. Repeat to include multiple cases.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    if not args.trace_jsonl and not args.workload_case:
        parser.error("one of --trace-jsonl or --workload-case is required")
    return args


def load_traces(path: Path) -> list[dict]:
    traces = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        traces.append(json.loads(line))
    return traces


def workload_case_to_traces(case_id: str, *, seed: int) -> list[dict]:
    if case_id not in WORKLOADS.SHARED_BENCHMARK_CASE_CATALOG:
        raise ValueError(f"unknown workload case: {case_id}")

    requests = generate_case_requests(case_id, seed=seed)

    traces: list[dict] = []
    seen_primary: set[str] = set()
    seen_secondary: set[str] = set()
    rank_counts: dict[int, int] = {}

    for index, request in enumerate(requests):
        metadata = WORKLOADS.normalize_repo_local_metadata(request.repo_local_metadata)
        secondary_seen = len(set(metadata.secondary_anchor_ids) & seen_secondary)
        secondary_total = max(len(metadata.secondary_anchor_ids), 1)
        overlap_ratio = secondary_seen / secondary_total
        primary_seen = metadata.primary_anchor_id in seen_primary

        primary_ratio = 0.5 if primary_seen else 0.0
        overlap_bonus = 0.28 * overlap_ratio
        exact_turn_bonus = 0.06 if metadata.turn_index > 0 else 0.0
        reusable_ratio = min(0.88, primary_ratio + overlap_bonus + exact_turn_bonus)
        reusable_tokens = int(round(request.prompt_len * reusable_ratio))

        rank_count = rank_counts.get(metadata.home_rank, 0)
        queue_pressure = min(
            0.95,
            0.18 + (0.09 * rank_count) + (0.08 if primary_seen else 0.0) + (0.05 * secondary_seen),
        )

        ttft_sensitive = metadata.workload_family in {
            "session-affine-multi-turn",
            "session-affine-bursty",
            "rag-followup",
            "tool-scaffold-agent",
            "repo-aware-coding-assistant",
            "realtime-voice-assistant",
        }

        transfer_factor_ms = {
            "session-affine-multi-turn": 0.0048,
            "session-affine-bursty": 0.0046,
            "rag-followup": 0.0064,
            "long-context-doc-analysis": 0.0072,
            "tool-scaffold-agent": 0.0056,
            "repo-aware-coding-assistant": 0.0061,
        }.get(metadata.workload_family, 0.0055)
        recompute_factor_ms = {
            "session-affine-multi-turn": 0.0110,
            "session-affine-bursty": 0.0108,
            "rag-followup": 0.0118,
            "long-context-doc-analysis": 0.0132,
            "tool-scaffold-agent": 0.0114,
            "repo-aware-coding-assistant": 0.0121,
        }.get(metadata.workload_family, 0.0116)

        confidence_penalty = 1.0 + max(0.0, 0.6 - min(1.0, 0.2 + (0.45 if primary_seen else 0.0) + (0.3 * overlap_ratio))) * 2.8
        transfer_time_ms = 1.1 + (reusable_tokens * transfer_factor_ms * (1.0 + max(queue_pressure - 0.3, 0.0) * 0.75) * confidence_penalty)
        recompute_time_ms = (request.prompt_len * recompute_factor_ms) + (request.output_len * 0.01)
        recompute_time_ms *= 1.0 + (queue_pressure * 0.18)

        traces.append(
            {
                "trace_id": f"{case_id}-{index}",
                "workload_case": case_id,
                "workload_family": metadata.workload_family,
                "reusable_prefix_tokens": reusable_tokens,
                "remote_kv_bytes": reusable_tokens * 32768,
                "transfer_time_ms": round(transfer_time_ms, 3),
                "recompute_time_ms": round(recompute_time_ms, 3),
                "queue_pressure": round(queue_pressure, 3),
                "ttft_sensitive": ttft_sensitive,
                "reuse_confidence": round(min(0.98, 0.2 + (0.45 if primary_seen else 0.0) + (0.3 * overlap_ratio)), 3),
                "prompt_len": int(request.prompt_len),
                "output_len": int(request.output_len),
            }
        )

        seen_primary.add(metadata.primary_anchor_id)
        seen_secondary.update(metadata.secondary_anchor_ids)
        rank_counts[metadata.home_rank] = rank_count + 1

    return traces


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[index]


def build_signals(raw: dict) -> MaterializationSignals:
    return MaterializationSignals(
        reusable_prefix_tokens=int(raw["reusable_prefix_tokens"]),
        remote_kv_bytes=int(raw["remote_kv_bytes"]),
        transfer_time_ms=float(raw["transfer_time_ms"]),
        recompute_time_ms=float(raw["recompute_time_ms"]),
        queue_pressure=float(raw["queue_pressure"]),
        ttft_sensitive=bool(raw.get("ttft_sensitive", True)),
        reuse_confidence=float(raw.get("reuse_confidence", 0.0)),
    )


def decide_baseline(name: str, signals: MaterializationSignals) -> tuple[MaterializationDecision, int]:
    if name == "always_recompute":
        return MaterializationDecision.RECOMPUTE, 0
    if name == "always_full_reuse":
        if signals.reusable_prefix_tokens > 0:
            return MaterializationDecision.FULL_REUSE, signals.reusable_prefix_tokens
        return MaterializationDecision.RECOMPUTE, 0
    if name == "threshold_partial":
        if signals.reusable_prefix_tokens >= 512:
            return MaterializationDecision.PARTIAL_REUSE, max(256, signals.reusable_prefix_tokens // 2)
        return MaterializationDecision.RECOMPUTE, 0
    raise ValueError(f"unknown baseline: {name}")


def decide_oracle(signals: MaterializationSignals, *, partial_reuse_floor_tokens: int) -> tuple[MaterializationDecision, int]:
    candidates = [(MaterializationDecision.RECOMPUTE, 0)]
    if signals.reusable_prefix_tokens > 0:
        candidates.append((MaterializationDecision.FULL_REUSE, signals.reusable_prefix_tokens))
    if signals.reusable_prefix_tokens >= partial_reuse_floor_tokens:
        candidates.append(
            (
                MaterializationDecision.PARTIAL_REUSE,
                max(partial_reuse_floor_tokens, signals.reusable_prefix_tokens // 2),
            )
        )
    return min(candidates, key=lambda candidate: evaluate(signals, candidate[0], candidate[1])["ttft_ms"])


def perturb_signals(signals: MaterializationSignals, *, transfer_factor: float = 1.0, recompute_factor: float = 1.0) -> MaterializationSignals:
    return replace(
        signals,
        transfer_time_ms=signals.transfer_time_ms * transfer_factor,
        recompute_time_ms=signals.recompute_time_ms * recompute_factor,
    )


def evaluate(signals: MaterializationSignals, decision: MaterializationDecision, reused_tokens: int) -> dict:
    if decision is MaterializationDecision.FULL_REUSE:
        ttft_ms = signals.transfer_time_ms + 0.8
        recompute_tokens = 0
        transferred_bytes = signals.remote_kv_bytes
    elif decision is MaterializationDecision.PARTIAL_REUSE:
        reuse_ratio = reused_tokens / max(1, signals.reusable_prefix_tokens)
        ttft_ms = (signals.transfer_time_ms * reuse_ratio) + (signals.recompute_time_ms * (1.0 - reuse_ratio)) + 0.6
        recompute_tokens = max(0, signals.reusable_prefix_tokens - reused_tokens)
        transferred_bytes = int(signals.remote_kv_bytes * reuse_ratio)
    else:
        ttft_ms = signals.recompute_time_ms
        recompute_tokens = signals.reusable_prefix_tokens
        transferred_bytes = 0
    return {
        "decision": decision.value,
        "reused_tokens": reused_tokens,
        "ttft_ms": round(ttft_ms, 3),
        "recompute_tokens": recompute_tokens,
        "transferred_bytes": transferred_bytes,
    }


def summarize(records: list[dict]) -> dict:
    ttfts = sorted(record["ttft_ms"] for record in records)
    recompute_tokens = [record["recompute_tokens"] for record in records]
    transferred_bytes = [record["transferred_bytes"] for record in records]
    decisions: dict[str, int] = {}
    for record in records:
        decisions[record["decision"]] = decisions.get(record["decision"], 0) + 1
    return {
        "requests": len(records),
        "mean_ttft_ms": round(mean(ttfts), 3) if ttfts else 0.0,
        "p95_ttft_ms": round(percentile(ttfts, 0.95), 3),
        "mean_recompute_tokens": round(mean(recompute_tokens), 3) if recompute_tokens else 0.0,
        "mean_transferred_kib": round(mean(transferred_bytes) / 1024.0, 3) if transferred_bytes else 0.0,
        "decision_counts": decisions,
    }


def summarize_by_case(per_policy_records: dict[str, list[dict]], family_by_case: dict[str, str]) -> dict[str, dict]:
    summary: dict[str, dict] = {}
    case_ids = sorted({record["workload_case"] for rows in per_policy_records.values() for record in rows})
    for case_id in case_ids:
        policy_names = sorted({name for name, rows in per_policy_records.items() if any(record["workload_case"] == case_id for record in rows)})
        summary[case_id] = {
            "workload_family": family_by_case.get(case_id, "unknown"),
            "requests": len([record for record in per_policy_records.get("heuristic", []) if record["workload_case"] == case_id]),
            "policies": {name: summarize([record for record in per_policy_records[name] if record["workload_case"] == case_id]) for name in policy_names},
        }
    return summary


def render_markdown(summary: dict) -> str:
    lines = ["# Arrival-Time Decision Study Summary", ""]
    lines.append(f"- trace count: {summary['trace_count']}")
    lines.append(f"- trace source: {summary['trace_source']}")
    if summary.get("workload_cases"):
        lines.append(f"- workload cases: {', '.join(summary['workload_cases'])}")
    lines.append("- claim boundary: offline decision-surface evidence only; no live runtime-gain claim")
    lines.append("")
    lines.append("## Overall Policies")
    lines.append("")
    for policy_name in [*CORE_POLICIES, *SENSITIVITY_POLICIES]:
        if policy_name not in summary["policies"]:
            continue
        metrics = summary["policies"][policy_name]
        lines.append(f"## {policy_name}")
        lines.append("")
        lines.append(f"- requests: {metrics['requests']}")
        lines.append(f"- mean TTFT (ms): {metrics['mean_ttft_ms']}")
        lines.append(f"- p95 TTFT (ms): {metrics['p95_ttft_ms']}")
        lines.append(f"- mean recompute tokens: {metrics['mean_recompute_tokens']}")
        lines.append(f"- mean transferred KiB: {metrics['mean_transferred_kib']}")
        lines.append(f"- decisions: {metrics['decision_counts']}")
        lines.append("")
    if summary.get("case_summaries"):
        lines.append("## Per-Case Snapshot")
        lines.append("")
        for case_id, case_summary in summary["case_summaries"].items():
            lines.append(f"### {case_id}")
            lines.append("")
            lines.append(f"- family: {case_summary['workload_family']}")
            role = DECISION_SURFACE_CASE_ROLES.get(case_id)
            if role is not None:
                lines.append(f"- decision role: {role}")
            lines.append(f"- requests: {case_summary['requests']}")
            heuristic_metrics = case_summary["policies"].get("heuristic")
            oracle_metrics = case_summary["policies"].get("oracle_ttft")
            if heuristic_metrics is not None:
                lines.append(f"- heuristic p95 TTFT (ms): {heuristic_metrics['p95_ttft_ms']}")
            if oracle_metrics is not None:
                lines.append(f"- oracle p95 TTFT (ms): {oracle_metrics['p95_ttft_ms']}")
            lines.append("")
    return "\n".join(lines)


def render_table_tex(summary: dict) -> str:
    rows = []
    for policy_name in CORE_POLICIES:
        metrics = summary["policies"][policy_name]
        label = policy_name.replace("_", " ")
        rows.append(
            f"{label} & {metrics['mean_ttft_ms']} & {metrics['p95_ttft_ms']} & {metrics['mean_recompute_tokens']} & {metrics['mean_transferred_kib']} \\\\" 
        )
    body = "\n".join(rows)
    return (
        "\\begin{table}[t]\n"
        "\\centering\n"
        "\\setlength{\\tabcolsep}{3pt}\n"
        "\\footnotesize\n"
        "\\caption{Arrival-time decision-study snapshot on workload-driven traces derived from llm-serving-workloads.}\n"
        "\\begin{tabular}{@{}lrrrr@{}}\n"
        "\\toprule\n"
        "Policy & Mean & P95 & Recomp. & Xfer KiB \\\\ \n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )


def render_macros(summary: dict) -> str:
    metrics = summary["policies"]["heuristic"]
    oracle_metrics = summary["policies"]["oracle_ttft"]
    return "\n".join(
        [
            f"\\newcommand{{\\HeuristicMeanTTFT}}{{{metrics['mean_ttft_ms']}}}",
            f"\\newcommand{{\\HeuristicPNineFiveTTFT}}{{{metrics['p95_ttft_ms']}}}",
            f"\\newcommand{{\\OracleMeanTTFT}}{{{oracle_metrics['mean_ttft_ms']}}}",
            f"\\newcommand{{\\OraclePNineFiveTTFT}}{{{oracle_metrics['p95_ttft_ms']}}}",
        ]
    ) + "\n"


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    traces: list[dict] = []
    trace_source: str
    workload_cases = list(args.workload_case)
    if args.trace_jsonl:
        trace_path = Path(args.trace_jsonl)
        traces.extend(load_traces(trace_path))
        trace_source = f"jsonl:{trace_path.name}"
    else:
        trace_source = "llm-serving-workloads shared benchmark catalog"

    for case_id in workload_cases:
        traces.extend(workload_case_to_traces(case_id, seed=args.seed))

    policy = MaterializationPolicy(partial_reuse_floor_tokens=128)
    per_policy_records: dict[str, list[dict]] = {name: [] for name in [*CORE_POLICIES, *SENSITIVITY_POLICIES]}

    detailed_records = []
    family_by_case: dict[str, str] = {}
    for trace in traces:
        signals = build_signals(trace)
        heuristic_outcome = policy.decide(signals)
        heuristic_eval = evaluate(signals, heuristic_outcome.decision, heuristic_outcome.reused_tokens)
        heuristic_eval["trace_id"] = trace["trace_id"]
        heuristic_eval["policy_name"] = "heuristic"
        heuristic_eval["workload_case"] = trace.get("workload_case", "sample_trace")
        per_policy_records["heuristic"].append(heuristic_eval)
        case_id = trace.get("workload_case", "sample_trace")
        family_by_case[case_id] = str(trace.get("workload_family", family_by_case.get(case_id, "sample_trace")))
        detail_row = {
            "trace_id": trace["trace_id"],
            "signals": asdict(signals),
            "heuristic": heuristic_eval,
        }

        oracle_decision, oracle_reused_tokens = decide_oracle(
            signals,
            partial_reuse_floor_tokens=policy.partial_reuse_floor_tokens,
        )
        oracle_eval = evaluate(signals, oracle_decision, oracle_reused_tokens)
        oracle_eval["trace_id"] = trace["trace_id"]
        oracle_eval["policy_name"] = "oracle_ttft"
        oracle_eval["workload_case"] = case_id
        per_policy_records["oracle_ttft"].append(oracle_eval)
        detail_row["oracle_ttft"] = oracle_eval

        for policy_name in ("always_recompute", "always_full_reuse", "threshold_partial"):
            decision, reused_tokens = decide_baseline(policy_name, signals)
            evaluated = evaluate(signals, decision, reused_tokens)
            evaluated["trace_id"] = trace["trace_id"]
            evaluated["policy_name"] = policy_name
            evaluated["workload_case"] = case_id
            per_policy_records[policy_name].append(evaluated)
            detail_row[policy_name] = evaluated

        for policy_name, estimated_signals in (
            ("heuristic_transfer_underestimated", perturb_signals(signals, transfer_factor=0.75)),
            ("heuristic_transfer_overestimated", perturb_signals(signals, transfer_factor=1.25)),
            ("heuristic_recompute_underestimated", perturb_signals(signals, recompute_factor=0.75)),
            ("heuristic_recompute_overestimated", perturb_signals(signals, recompute_factor=1.25)),
        ):
            estimated_outcome = policy.decide(estimated_signals)
            evaluated = evaluate(signals, estimated_outcome.decision, estimated_outcome.reused_tokens)
            evaluated["trace_id"] = trace["trace_id"]
            evaluated["policy_name"] = policy_name
            evaluated["workload_case"] = case_id
            per_policy_records[policy_name].append(evaluated)
            detail_row[policy_name] = {
                "estimated_signals": asdict(estimated_signals),
                "actual_outcome": evaluated,
            }

        detailed_records.append(detail_row)

    summary = {
        "trace_count": len(traces),
        "trace_source": trace_source,
        "workload_cases": workload_cases,
        "policies": {name: summarize(records) for name, records in per_policy_records.items()},
        "case_summaries": summarize_by_case(per_policy_records, family_by_case),
    }

    (output_dir / "offline_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "offline_details.json").write_text(json.dumps(detailed_records, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "offline_summary.md").write_text(render_markdown(summary), encoding="utf-8")
    (output_dir / "offline_summary_table.tex").write_text(render_table_tex(summary), encoding="utf-8")
    (output_dir / "offline_summary_macros.tex").write_text(render_macros(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
