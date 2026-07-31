from __future__ import annotations

import importlib
import os
import random
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


class WhitespaceTokenizer:
    def encode(self, text: str, add_special_tokens: bool = False) -> list[str]:
        del add_special_tokens
        return text.split()


@lru_cache(maxsize=4)
def _load_hf_tokenizer(model_name_or_path: str) -> Any:
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "transformers is required to build live workloads with a real model tokenizer."
        ) from exc
    return AutoTokenizer.from_pretrained(model_name_or_path, trust_remote_code=True)


def resolve_workload_tokenizer(tokenizer_name_or_path: str | None = None) -> Any:
    if not tokenizer_name_or_path:
        return WhitespaceTokenizer()
    return _load_hf_tokenizer(str(tokenizer_name_or_path))


@dataclass(frozen=True, slots=True)
class SharedLiveRequest:
    request_id: str
    prompt: str
    prompt_tokens: int
    output_tokens: int
    workload_case: str
    workload_family: str
    family_label: str
    primary_anchor_id: str
    secondary_anchor_ids: tuple[str, ...]
    shared_prefix_tokens: int
    reuse_confidence: float
    home_rank: int
    turn_index: int
    arrival_gap_s: float


@dataclass(frozen=True, slots=True)
class SharedLiveWorkload:
    case_id: str
    label: str
    dataset_name: str
    workload_family: str
    request_rate: float
    concurrency: int
    requests: tuple[SharedLiveRequest, ...]


def _candidate_workload_src_paths() -> tuple[Path, ...]:
    configured = os.environ.get("LLM_SERVING_WORKLOADS_SRC", "").strip()
    paths: list[Path] = []
    if configured:
        paths.append(Path(configured).expanduser())
    paths.append(REPO_ROOT.parent / "llm-serving-workloads" / "src")
    return tuple(paths)


def load_workloads_module() -> Any:
    for candidate in _candidate_workload_src_paths():
        if not candidate.is_dir():
            continue
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
        break
    try:
        return importlib.import_module("llm_serving_workloads")
    except ImportError as exc:
        raise RuntimeError(
            "llm-serving-workloads is required for workload-driven runs. "
            "Set LLM_SERVING_WORKLOADS_SRC=<repo>/src or install the package first."
        ) from exc


def default_shared_benchmark_case_ids() -> tuple[str, ...]:
    workloads = load_workloads_module()
    return tuple(
        str(case_id) for case_id in workloads.DEFAULT_SHARED_BENCHMARK_CASE_ORDER
    )


_EXPLICIT_DECISION_SURFACE_CASE_ROLES = {
    "shared_scenario_multi_turn_knowledge_service": "exact_continuation_baseline",
    "shared_scenario_rag_followup_long_context": "retrieval_followup_long_context_boundary",
    "shared_scenario_structured_agent_decode": "mixed_schema_and_transcript_overlap",
    "shared_prefix_multi_tenant_assistant": "prefix_rich_multi_tenant_surface",
    "session_continuation_with_maintenance": "long_context_continuation_surface",
    "dynamic_rag_corpus_update": "dynamic_retrieval_followup_surface",
    "memory_write_then_reuse": "write_then_retrieve_state_surface",
    "preemption_resume_long_decode": "checkpoint_resume_decode_surface",
    "shared_synthetic_shared_prefix_microbenchmark": "synthetic_shared_prefix_control",
    "shared_public_sharegpt_boundary": "public_boundary_control",
}


def _default_decision_surface_role(case_id: str) -> str:
    if case_id in _EXPLICIT_DECISION_SURFACE_CASE_ROLES:
        return _EXPLICIT_DECISION_SURFACE_CASE_ROLES[case_id]
    workloads = load_workloads_module()
    case = dict(workloads.SHARED_BENCHMARK_CASE_CATALOG[case_id])
    hints = dict(case.get("serving_hints", {}))
    continuity_focus = hints.get("continuity_focus")
    if continuity_focus:
        return f"catalog::{str(continuity_focus).replace('-', '_')}"
    dataset_name = str(case.get("dataset_name", "unknown"))
    return f"catalog_case::{dataset_name.replace('-', '_')}"


DECISION_SURFACE_CASE_IDS = default_shared_benchmark_case_ids()

DECISION_SURFACE_CASE_ROLES = {
    case_id: _default_decision_surface_role(case_id)
    for case_id in DECISION_SURFACE_CASE_IDS
}

RUNTIME_BOUNDARY_CASE_IDS = DECISION_SURFACE_CASE_IDS

EXPERIMENT_ARTICLE_CASE_IDS = DECISION_SURFACE_CASE_IDS

DEFAULT_LIVE_WORKLOAD_CASE = EXPERIMENT_ARTICLE_CASE_IDS[0]

WORKLOAD_CASE_ALIASES = {
    # Paper-facing name retained by the M1 matrix; the shared catalog renamed
    # this same tool-scaffold family to the scenario-oriented identifier.
    "shared_tool_scaffold_agent": "shared_scenario_structured_agent_decode",
}


def resolve_case_spec(case_id: str) -> dict[str, Any]:
    workloads = load_workloads_module()
    catalog = workloads.SHARED_BENCHMARK_CASE_CATALOG
    canonical_case_id = WORKLOAD_CASE_ALIASES.get(case_id, case_id)
    if canonical_case_id not in catalog:
        raise ValueError(f"unknown workload case: {case_id}")
    case = dict(catalog[canonical_case_id])
    case["requested_case_id"] = case_id
    case["canonical_case_id"] = canonical_case_id
    return case


def recommended_context_window(
    case_id: str, *, fallback: int | None = None
) -> int | None:
    case = resolve_case_spec(case_id)
    hints = dict(case.get("serving_hints", {}))
    value = hints.get("recommended_context_window")
    if value is None:
        return fallback
    return int(value)


def _make_prompt(
    shared_prefix_tokens: int,
    unique_tokens: int,
    *,
    shared_token: str,
    unique_token: str,
) -> str:
    parts = [shared_token] * max(shared_prefix_tokens, 1)
    parts.extend([unique_token] * max(unique_tokens, 1))
    return " ".join(parts)


def _generate_public_case_requests(
    workloads: Any, case_id: str, case: dict[str, Any], *, seed: int
) -> list[Any]:
    dataset_name = str(case["dataset_name"])
    num_prompts = int(
        case.get(
            "num_prompts", int(case["num_groups"]) * int(case["prompts_per_group"])
        )
    )
    num_groups = max(1, int(case.get("num_groups", 1)))
    prompts_per_group = max(1, int(case.get("prompts_per_group", 1)))
    system_prompt_len = int(case.get("system_prompt_len", 256))
    question_len = int(case.get("question_len", 64))
    output_len = int(case.get("output_len", 64))
    rng = random.Random(seed)
    rows: list[Any] = []

    if dataset_name == "generated-shared-prefix":
        family_label = "Synthetic shared-prefix micro-benchmark"
        workload_family = "synthetic-shared-prefix"
        anchor_strategy = "synthetic-prefix-hash"
    elif dataset_name == "sharegpt":
        family_label = "ShareGPT public boundary"
        workload_family = "sharegpt-public-boundary"
        anchor_strategy = "conversation-prefix-hash"
    else:
        raise ValueError(f"unsupported public workload dataset: {dataset_name}")

    for index in range(num_prompts):
        group_index = min(index // prompts_per_group, num_groups - 1)
        turn_index = index % prompts_per_group
        shared_prefix_tokens = system_prompt_len + rng.randint(
            0, max(question_len // 3, 1)
        )
        unique_tokens = max(question_len + rng.randint(-8, 8), 8)
        shared_token = f"{dataset_name.replace('-', '_')}_g{group_index}_shared"
        unique_token = f"req{index}_turn{turn_index}"
        prompt = _make_prompt(
            shared_prefix_tokens,
            unique_tokens,
            shared_token=shared_token,
            unique_token=unique_token,
        )
        metadata = {
            "workload_family": workload_family,
            "family_label": family_label,
            "deployment_story": str(case.get("label", case_id)),
            "anchor_strategy": anchor_strategy,
            "locality_activation_rationale": "public workload boundary carried through shared benchmark case catalog",
            "primary_anchor_id": f"{case_id}:group:{group_index}",
            "secondary_anchor_ids": [
                f"{case_id}:turn:{turn_index}",
                f"{case_id}:band:{group_index % 2}",
            ],
            "primary_anchor_kind": "shared_prefix"
            if dataset_name == "generated-shared-prefix"
            else "conversation_cluster",
            "secondary_anchor_kind": "request_turn",
            "home_rank": group_index % max(1, int(case.get("dp_size", 8))),
            "anchor_index": group_index,
            "turn_index": turn_index,
            "shared_prefix_tokens": shared_prefix_tokens,
        }
        rows.append(
            workloads.RepoLocalDatasetRow(
                prompt=prompt,
                prompt_len=len(prompt.split()),
                output_len=output_len,
                repo_local_metadata=metadata,
            )
        )

    return rows


def generate_case_requests(
    case_id: str, *, seed: int, tokenizer: Any | None = None
) -> list[Any]:
    workloads = load_workloads_module()
    case = resolve_case_spec(case_id)
    dataset_name = str(case["dataset_name"])
    effective_tokenizer = tokenizer if tokenizer is not None else WhitespaceTokenizer()
    if dataset_name in getattr(workloads, "PUBLIC_WORKLOAD_DATASET_NAMES", ()):
        return _generate_public_case_requests(workloads, case_id, case, seed=seed)
    if not workloads.is_repo_local_workload_dataset(dataset_name):
        raise ValueError(
            f"workload case {case_id} uses unsupported dataset {dataset_name}"
        )
    return workloads.generate_repo_local_workload_requests(
        dataset_name=dataset_name,
        tokenizer=effective_tokenizer,
        dp_size=int(case.get("dp_size", 8)),
        num_prompts=int(
            case.get(
                "num_prompts", int(case["num_groups"]) * int(case["prompts_per_group"])
            )
        ),
        num_groups=int(case["num_groups"]),
        system_prompt_len=int(case["system_prompt_len"]),
        question_len=int(case["question_len"]),
        output_len=int(case["output_len"]),
        seed=seed,
        **dict(case.get("benchmark_kwargs", {})),
    )


def build_live_workload(
    case_id: str,
    *,
    seed: int = 7,
    request_rate: float | None = None,
    concurrency: int | None = None,
    max_output_tokens: int | None = None,
    tokenizer_name_or_path: str | None = None,
) -> SharedLiveWorkload:
    workloads = load_workloads_module()
    case = resolve_case_spec(case_id)
    rows = generate_case_requests(
        case_id,
        seed=seed,
        tokenizer=resolve_workload_tokenizer(tokenizer_name_or_path),
    )
    preset = workloads.WORKLOAD_PRESET_CATALOG.get(str(case["dataset_name"]), {})
    effective_request_rate = float(
        request_rate
        if request_rate is not None
        else preset.get("recommended_request_rate", 16)
    )
    default_concurrency = max(1, min(8, max(1, int(case.get("num_groups", 1)) // 2)))
    effective_concurrency = int(
        concurrency if concurrency is not None else default_concurrency
    )
    arrival_gap_s = 1.0 / max(effective_request_rate, 1.0)
    requests: list[SharedLiveRequest] = []
    workload_family = str(case["dataset_name"])

    for index, row in enumerate(rows):
        metadata = workloads.normalize_repo_local_metadata(row.repo_local_metadata)
        workload_family = metadata.workload_family or workload_family
        shared_prefix_tokens = int(metadata.extras.get("shared_prefix_tokens", 0))
        if shared_prefix_tokens <= 0:
            shared_prefix_tokens = max(
                0, int(row.prompt_len * (0.6 if metadata.turn_index > 0 else 0.35))
            )
        reuse_confidence = 0.95 if metadata.turn_index > 0 else 0.45
        output_tokens = int(row.output_len)
        if max_output_tokens is not None:
            output_tokens = max(1, min(output_tokens, int(max_output_tokens)))
        requests.append(
            SharedLiveRequest(
                request_id=f"{case_id}-{index}",
                prompt=row.prompt,
                prompt_tokens=int(row.prompt_len),
                output_tokens=output_tokens,
                workload_case=case_id,
                workload_family=metadata.workload_family,
                family_label=metadata.family_label,
                primary_anchor_id=metadata.primary_anchor_id,
                secondary_anchor_ids=tuple(metadata.secondary_anchor_ids),
                shared_prefix_tokens=shared_prefix_tokens,
                reuse_confidence=reuse_confidence,
                home_rank=int(metadata.home_rank),
                turn_index=int(metadata.turn_index),
                arrival_gap_s=0.0 if index == 0 else arrival_gap_s,
            )
        )

    return SharedLiveWorkload(
        case_id=case_id,
        label=str(case.get("label", case_id)),
        dataset_name=str(case["dataset_name"]),
        workload_family=workload_family,
        request_rate=effective_request_rate,
        concurrency=effective_concurrency,
        requests=tuple(requests),
    )


__all__ = [
    "DECISION_SURFACE_CASE_IDS",
    "DECISION_SURFACE_CASE_ROLES",
    "DEFAULT_LIVE_WORKLOAD_CASE",
    "EXPERIMENT_ARTICLE_CASE_IDS",
    "RUNTIME_BOUNDARY_CASE_IDS",
    "SharedLiveRequest",
    "SharedLiveWorkload",
    "WhitespaceTokenizer",
    "build_live_workload",
    "generate_case_requests",
    "load_workloads_module",
    "recommended_context_window",
    "resolve_case_spec",
    "resolve_workload_tokenizer",
]
