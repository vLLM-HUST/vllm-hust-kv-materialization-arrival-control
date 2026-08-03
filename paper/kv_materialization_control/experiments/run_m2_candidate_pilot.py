from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

EVIDENCE_LABELS = {
    "offline-ranked": "real-online/m2-candidate-pilot",
    "anchor-topology": "real-online/m2-anchor-candidate-pilot",
    "stateful-secondary": "real-online/m2-stateful-secondary-pilot",
    "catalog-closure": "real-online/m2-catalog-closure-pilot",
}
POLICIES = ("always_recompute", "always_full_reuse", "controller")
OFFLINE_RANKED_CANDIDATES = (
    ("shared_async_document_pipeline", 18.0, 96),
    ("shared_public_sharegpt_boundary", 24.0, 64),
)
ANCHOR_TOPOLOGY_CANDIDATES = (
    ("shared_session_continuation_maintenance", 18.0, 112),
    ("shared_shared_prefix_multi_tenant_assistant", 18.0, 128),
)
STATEFUL_SECONDARY_CANDIDATES = (
    ("shared_code_eval_judge", 18.0, 96),
    ("shared_structured_json_generation", 18.0, 96),
    ("shared_multi_turn_support_chat", 20.0, 96),
    ("shared_memory_write_then_reuse", 16.0, 96),
)
CATALOG_CLOSURE_CANDIDATES = (
    ("shared_session_affine_multi_turn", 24.0, 96),
    ("shared_session_affine_bursty", 30.0, 128),
    ("shared_rag_followup", 18.0, 48),
    ("shared_long_context_doc_analysis", 12.0, 64),
    ("shared_repo_aware_coding_assistant", 20.0, 128),
    ("shared_experiment_planning_assistant", 16.0, 192),
    ("shared_simulation_analysis_verification", 14.0, 128),
    ("shared_realtime_voice_assistant", 36.0, 72),
    ("shared_dynamic_rag_corpus_update", 18.0, 72),
    ("shared_preemption_resume_long_decode", 10.0, 192),
)
CANDIDATES = OFFLINE_RANKED_CANDIDATES


@dataclass(frozen=True)
class RunSpec:
    workload: str
    policy_mode: str
    request_rate: float
    max_output_tokens: int


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def build_schedule(
    candidates: tuple[tuple[str, float, int], ...] = CANDIDATES,
) -> list[RunSpec]:
    orders = (
        ("controller", "always_full_reuse", "always_recompute"),
        ("always_recompute", "controller", "always_full_reuse"),
    )
    return [
        RunSpec(workload, policy, request_rate, max_output_tokens)
        for (workload, request_rate, max_output_tokens), order in zip(
            candidates, itertools.cycle(orders)
        )
        for policy in order
    ]


def select_shard(
    candidates: tuple[tuple[str, float, int], ...],
    *,
    shard_index: int,
    num_shards: int,
) -> tuple[tuple[str, float, int], ...]:
    if num_shards < 1 or not 0 <= shard_index < num_shards:
        raise ValueError("shard-index must be in [0, num-shards)")
    return candidates[shard_index::num_shards]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the preregistered M2 pilot.")
    parser.add_argument("--suite-dir", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--carrier-root", default="vendor/vllm")
    parser.add_argument("--device", type=int, default=7)
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--num-shards", type=int, default=1)
    parser.add_argument(
        "--candidate-set",
        choices=tuple(EVIDENCE_LABELS),
        default="offline-ranked",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    suite_dir = Path(args.suite_dir).resolve()
    if suite_dir.is_relative_to(repo_root):
        raise SystemExit("suite-dir must be outside the worktree")
    if suite_dir.exists():
        raise SystemExit(f"refusing to overwrite suite directory: {suite_dir}")
    suite_dir.mkdir(parents=True)

    all_candidates = {
        "offline-ranked": OFFLINE_RANKED_CANDIDATES,
        "anchor-topology": ANCHOR_TOPOLOGY_CANDIDATES,
        "stateful-secondary": STATEFUL_SECONDARY_CANDIDATES,
        "catalog-closure": CATALOG_CLOSURE_CANDIDATES,
    }[args.candidate_set]
    candidates = select_shard(
        all_candidates,
        shard_index=args.shard_index,
        num_shards=args.num_shards,
    )
    if not candidates:
        raise SystemExit("selected candidate shard is empty")
    evidence_label = EVIDENCE_LABELS[args.candidate_set]
    schedule = build_schedule(candidates)
    suite: dict[str, object] = {
        "schema_version": 1,
        "study": "M2 preregistered positive-candidate pilot",
        "evidence_label": evidence_label,
        "candidate_set": args.candidate_set,
        "shard_index": args.shard_index,
        "num_shards": args.num_shards,
        "started_at_s": time.time(),
        "promotion_gate": {
            "controller_vs_best_fixed_ttft_pct_max": 2.0,
            "controller_vs_best_fixed_e2e_pct_max": 5.0,
            "controller_vs_best_fixed_throughput_pct_min": -5.0,
        },
        "schedule": [asdict(spec) for spec in schedule],
        "runs": [],
    }
    manifest = suite_dir / "suite_manifest.json"
    write_json(manifest, suite)

    for sequence, spec in enumerate(schedule, start=1):
        run_dir = (
            suite_dir
            / spec.workload
            / spec.policy_mode
            / f"pilot_sequence_{sequence:02d}"
        )
        command = [
            sys.executable,
            "paper/kv_materialization_control/experiments/run_online_lifecycle.py",
            "--bundle-dir",
            str(run_dir),
            "--workload-case",
            spec.workload,
            "--condition",
            "tuned",
            "--policy-mode",
            spec.policy_mode,
            "--seam",
            "segmented",
            "--carrier-root",
            args.carrier_root,
            "--model",
            args.model,
            "--device",
            str(args.device),
            "--port",
            str(args.port),
            "--block-size",
            "128",
            "--max-model-len",
            "32768",
            "--request-rate",
            str(spec.request_rate),
            "--concurrency",
            "4",
            "--max-output-tokens",
            str(spec.max_output_tokens),
            "--seed",
            "7",
            "--evidence-label",
            evidence_label,
        ]
        result = subprocess.run(command, cwd=repo_root, check=False)
        record = {
            "sequence": sequence,
            "spec": asdict(spec),
            "bundle_dir": str(run_dir),
            "returncode": result.returncode,
        }
        if result.returncode == 0:
            validation = subprocess.run(
                [
                    sys.executable,
                    "paper/kv_materialization_control/experiments/validate_online_bundle.py",
                    str(run_dir),
                    "--output",
                    str(run_dir / "validation.json"),
                    "--expected-evidence-label",
                    evidence_label,
                ],
                cwd=repo_root,
                check=False,
            )
            record["validation_returncode"] = validation.returncode
            if validation.returncode != 0:
                result = validation
        suite["runs"].append(record)
        write_json(manifest, suite)
        if result.returncode != 0:
            suite["status"] = "blocked" if result.returncode == 3 else "failed"
            break
    else:
        suite["status"] = "completed"

    suite["finished_at_s"] = time.time()
    write_json(manifest, suite)
    return 0 if suite["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
