from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from dataclasses import replace
from pathlib import Path
from statistics import mean

from vllm_kv_materialization.offline_traces import build_signals
from vllm_kv_materialization.offline_traces import load_traces
from vllm_kv_materialization.offline_traces import workload_case_to_traces
from vllm_kv_materialization.policy import MaterializationDecision
from vllm_kv_materialization.policy import estimate_materialization_ttft_ms
from vllm_kv_materialization.policy import MaterializationPolicy
from vllm_kv_materialization.policy import MaterializationSignals
from vllm_kv_materialization.policy import optimize_partial_reuse_tokens
from vllm_kv_materialization.shared_workloads import DECISION_SURFACE_CASE_IDS
from vllm_kv_materialization.shared_workloads import DECISION_SURFACE_CASE_ROLES


CORE_POLICIES = (
    "always_recompute",
    "always_full_reuse",
    "threshold_partial",
    "heuristic",
    "oracle_ttft",
)

FIGURE_POLICIES = (
    "threshold_partial",
    "heuristic",
    "oracle_ttft",
)

POLICY_TITLES = {
    "threshold_partial": "Threshold partial",
    "heuristic": "Adaptive heuristic",
    "oracle_ttft": "Oracle TTFT",
}

POLICY_LABELS = {
    "always_recompute": "Always recompute",
    "always_full_reuse": "Always full reuse",
    "threshold_partial": "Static threshold",
    "heuristic": "Adaptive heuristic",
    "oracle_ttft": "Oracle",
}

DECISION_STYLES = (
    ("full_reuse", "full reuse", "teal!70!black"),
    ("partial_reuse", "partial reuse", "orange!85!black"),
    ("recompute", "recompute", "gray!70"),
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
        args.workload_case = list(DECISION_SURFACE_CASE_IDS)
    return args


def percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[index]
def decide_baseline(name: str, signals: MaterializationSignals) -> tuple[MaterializationDecision, int]:
    if name == "always_recompute":
        return MaterializationDecision.RECOMPUTE, 0
    if name == "always_full_reuse":
        if signals.reusable_prefix_tokens > 0:
            return MaterializationDecision.FULL_REUSE, signals.reusable_prefix_tokens
        return MaterializationDecision.RECOMPUTE, 0
    if name == "threshold_partial":
        if signals.reusable_prefix_tokens >= 512:
            partial_tokens = optimize_partial_reuse_tokens(
                signals,
                partial_reuse_floor_tokens=256,
            )
            if partial_tokens > 0:
                return MaterializationDecision.PARTIAL_REUSE, partial_tokens
        return MaterializationDecision.RECOMPUTE, 0
    raise ValueError(f"unknown baseline: {name}")


def decide_oracle(signals: MaterializationSignals, *, partial_reuse_floor_tokens: int) -> tuple[MaterializationDecision, int]:
    candidates = [(MaterializationDecision.RECOMPUTE, 0)]
    if signals.reusable_prefix_tokens > 0:
        candidates.append((MaterializationDecision.FULL_REUSE, signals.reusable_prefix_tokens))
    if signals.reusable_prefix_tokens >= partial_reuse_floor_tokens:
        partial_tokens = optimize_partial_reuse_tokens(
            signals,
            partial_reuse_floor_tokens=partial_reuse_floor_tokens,
        )
        if partial_tokens > 0:
            candidates.append((MaterializationDecision.PARTIAL_REUSE, partial_tokens))
    return min(candidates, key=lambda candidate: evaluate(signals, candidate[0], candidate[1])["ttft_ms"])


def perturb_signals(signals: MaterializationSignals, *, transfer_factor: float = 1.0, recompute_factor: float = 1.0) -> MaterializationSignals:
    return replace(
        signals,
        transfer_time_ms=signals.transfer_time_ms * transfer_factor,
        recompute_time_ms=signals.recompute_time_ms * recompute_factor,
    )


def evaluate(signals: MaterializationSignals, decision: MaterializationDecision, reused_tokens: int) -> dict:
    ttft_ms = estimate_materialization_ttft_ms(
        signals,
        decision,
        reused_tokens,
        partial_reuse_floor_tokens=256,
    )
    if decision is MaterializationDecision.FULL_REUSE:
        recompute_tokens = 0
        transferred_bytes = signals.remote_kv_bytes
        reused_tokens = signals.reusable_prefix_tokens
    elif decision is MaterializationDecision.PARTIAL_REUSE:
        reuse_ratio = reused_tokens / max(1, signals.reusable_prefix_tokens)
        recompute_tokens = max(0, signals.reusable_prefix_tokens - reused_tokens)
        transferred_bytes = int(signals.remote_kv_bytes * reuse_ratio)
    else:
        reused_tokens = 0
        recompute_tokens = signals.reusable_prefix_tokens
        transferred_bytes = 0
    return {
        "decision": decision.value,
        "reused_tokens": reused_tokens,
        "ttft_ms": ttft_ms,
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
        label = POLICY_LABELS[policy_name]
        rows.append(
            f"{label} & {metrics['mean_ttft_ms']:.2f} & {metrics['p95_ttft_ms']:.2f} & "
            f"{metrics['mean_recompute_tokens']:.1f} & {metrics['mean_transferred_kib'] / 1024.0:.1f} \\\\"
        )
    body = "\n".join(rows)
    return (
        "\\begin{table}[t]\n"
        "\\centering\n"
        "\\setlength{\\tabcolsep}{3pt}\n"
        "\\footnotesize\n"
        "\\caption{Offline cost-model results across 1,296 requests from 25 workload cases. "
        "Latency values are model estimates, not online measurements.}\n"
        "\\label{tab:offline-summary}\n"
        "\\begin{tabular}{@{}lrrrr@{}}\n"
        "\\toprule\n"
        "Policy & Mean & P95 & Recomp. & Xfer MiB \\\\\n"
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


def latex_escape(value: str) -> str:
    replacements = {
        "\\": "\\textbackslash{}",
        "_": "\\_",
        "&": "\\&",
        "%": "\\%",
        "#": "\\#",
    }
    return "".join(replacements.get(char, char) for char in value)


def humanize_case_id(case_id: str) -> str:
    return case_id.replace("_", " ")


def build_workload_codebook(summary: dict) -> list[dict[str, str]]:
    case_ids = [
        case_id
        for case_id in summary.get("workload_cases", [])
        if case_id in summary.get("case_summaries", {})
    ]
    if not case_ids:
        case_ids = sorted(summary.get("case_summaries", {}).keys())

    codebook = []
    for index, case_id in enumerate(case_ids, start=1):
        case_summary = summary["case_summaries"].get(case_id, {})
        codebook.append(
            {
                "code": f"Q{index}",
                "case_id": case_id,
                "workload_family": case_summary.get("workload_family", "unknown"),
                "decision_role": DECISION_SURFACE_CASE_ROLES.get(case_id, "unassigned"),
            }
        )
    return codebook


def render_workload_key_table_tex(summary: dict) -> str:
    codebook = summary.get("workload_codebook") or build_workload_codebook(summary)
    rows = []
    for entry in codebook:
        rows.append(
            " & ".join(
                [
                    entry["code"],
                    latex_escape(humanize_case_id(entry["case_id"])),
                    latex_escape(entry["workload_family"]),
                ]
            )
            + r" \\")

    body = "\n".join(rows)
    return (
        "\\begin{table*}[t]\n"
        "\\centering\n"
        "\\scriptsize\n"
        "\\setlength{\\tabcolsep}{4pt}\n"
        "\\caption{Workload shorthand used in Figure~\\ref{fig:offline-decision-mix}. The default workload matrix still comes directly from \\texttt{llm-serving-workloads}; the paper uses compact Q-codes only to keep the figure legible.}\n"
        "\\label{tab:offline-workload-key}\n"
        "\\begin{tabular}{@{}lp{0.45\\textwidth}p{0.3\\textwidth}@{}}\n"
        "\\toprule\n"
        "ID & Workload case & Family \\\\ \n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
        "\\end{table*}\n"
    )


def render_decision_mix_figure_tex(summary: dict) -> str:
    labels = {
        "memory_write_then_reuse": "Memory write",
        "shared_async_document_pipeline": "Async document",
        "shared_memory_write_then_reuse": "Shared memory write",
        "shared_prefix_multi_tenant_assistant": "Multi-tenant prefix",
        "shared_public_sharegpt_boundary": "ShareGPT control",
        "shared_session_continuation_maintenance": "Session maintenance",
        "shared_shared_prefix_multi_tenant_assistant": "Shared multi-tenant",
        "shared_synthetic_shared_prefix_microbenchmark": "Synthetic prefix",
    }
    case_ids = [
        case_id
        for case_id, case_summary in summary["case_summaries"].items()
        if case_summary["policies"]["oracle_ttft"]["decision_counts"].get("partial_reuse", 0) > 0
    ]
    case_ids.sort(key=lambda case_id: labels[case_id])
    ycoords = ",".join("{" + labels[case_id] + "}" for case_id in reversed(case_ids))

    lines = [
        "\\begin{figure}[t]",
        "\\centering",
        "\\footnotesize",
        "\\begin{tikzpicture}",
        "\\begin{axis}[",
        "xbar,",
        "bar width=5pt,",
        "width=0.80\\columnwidth,",
        "height=0.23\\textheight,",
        "xmin=0, xmax=100,",
        "xlabel={Requests selecting partial reuse (\\%)},",
        f"symbolic y coords={{{ycoords}}},",
        "ytick=data,",
        "yticklabel style={font=\\tiny},",
        "xtick={0,25,50,75,100},",
        "xmajorgrids=true,",
        "grid style={draw=gray!20},",
        "legend columns=2,",
        "legend style={at={(0.5,1.03)}, anchor=south, draw=none, font=\\scriptsize},",
        "]",
    ]

    for policy_name, color in (("heuristic", "teal!70!black"), ("oracle_ttft", "orange!85!black")):
        coords = []
        for case_id in case_ids:
            metrics = summary["case_summaries"][case_id]["policies"][policy_name]
            requests = max(1, metrics["requests"])
            partial = metrics["decision_counts"].get("partial_reuse", 0)
            coords.append(f"({round(partial * 100.0 / requests, 1)},{{{labels[case_id]}}})")
        lines.append(f"\\addplot+[draw=none, fill={color}] coordinates {{{' '.join(coords)}}};")
    lines.append("\\legend{Adaptive heuristic,Oracle}")

    lines.extend(
        [
            "\\end{axis}",
            "\\end{tikzpicture}",
            "\\caption{The eight workload cases in which the offline oracle selects partial reuse at least once. "
            "Partial reuse is concentrated rather than universal; the heuristic also over-selects it in several cases.}",
            "\\label{fig:offline-decision-mix}",
            "\\end{figure}",
            "",
        ]
    )
    return "\n".join(lines)


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
    summary["workload_codebook"] = build_workload_codebook(summary)

    (output_dir / "offline_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "offline_details.json").write_text(json.dumps(detailed_records, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "offline_summary.md").write_text(render_markdown(summary), encoding="utf-8")
    (output_dir / "offline_summary_table.tex").write_text(render_table_tex(summary), encoding="utf-8")
    (output_dir / "offline_summary_macros.tex").write_text(render_macros(summary), encoding="utf-8")
    (output_dir / "offline_workload_key_table.tex").write_text(render_workload_key_table_tex(summary), encoding="utf-8")
    (output_dir / "offline_decision_mix_figure.tex").write_text(render_decision_mix_figure_tex(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
