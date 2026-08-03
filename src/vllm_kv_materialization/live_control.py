from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from vllm_kv_materialization.policy import (
    MaterializationDecision,
    MaterializationOutcome,
    MaterializationPolicy,
    MaterializationSignals,
    estimate_materialization_ttft_ms,
)

logger = logging.getLogger(__name__)

REQUEST_HEADERS: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "vllm_kv_materialization_request_headers",
    default={},  # noqa: B039 - callers receive a defensive copy from get_request_headers
)

_ANCHOR_SEEN_COUNTS: dict[str, int] = {}
_ANCHOR_LOCK = threading.Lock()
_LOG_LOCK = threading.Lock()

HEADER_REQUEST_ID = "x-request-id"
HEADER_PRIMARY_ANCHOR = "x-kv-primary-anchor-id"
HEADER_SECONDARY_ANCHORS = "x-kv-secondary-anchor-ids"
HEADER_SHARED_PREFIX_TOKENS = "x-kv-shared-prefix-tokens"
HEADER_REUSE_CONFIDENCE = "x-kv-reuse-confidence"
HEADER_QUEUE_PRESSURE = "x-kv-queue-pressure"
HEADER_WORKLOAD_CASE = "x-kv-workload-case"
HEADER_WORKLOAD_FAMILY = "x-kv-workload-family"
HEADER_TURN_INDEX = "x-kv-turn-index"
HEADER_HOME_RANK = "x-kv-home-rank"

DEFAULT_BYTES_PER_TOKEN = 16 * 1024
DEFAULT_TRANSFER_BANDWIDTH_GBPS = 25.0
DEFAULT_PREFILL_MS_PER_1K = 14.0
DEFAULT_QUEUE_PRESSURE = 0.0

RUNTIME_SUPPORT_NATIVE = "native_runtime_action"
RUNTIME_SUPPORT_FALLBACK = "fallback_to_supported_runtime_action"
PARTIAL_REUSE_FALLBACK_REASON = (
    "exact_partial_segment_materialization_unavailable_on_prefix_cache_path"
)
PARTIAL_REUSE_ALIGNMENT_FALLBACK_REASON = (
    "partial_reuse_cut_point_realigned_to_runtime_hash_blocks"
)
PARTIAL_REUSE_RUNTIME_REALIGN_TO_RECOMPUTE = (
    "block_aligned_partial_reuse_collapses_to_recompute"
)
PARTIAL_REUSE_RUNTIME_REALIGN_TO_FULL_REUSE = (
    "block_aligned_partial_reuse_dominated_by_full_reuse"
)
RUNTIME_KV_TRANSFER_CONTROL_KEY = "kv_materialization_runtime_control"
RUNTIME_KV_TRANSFER_CONTROL_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class RuntimeControlPlan:
    observed_decision: str
    effective_decision: str
    control_path: str
    cache_salt: str | None
    segmented_tail_cache_salt: str | None
    target_reuse_tokens: int
    target_tail_tokens: int
    decision_supported: bool
    support_tier: str
    fallback_reason: str | None


@dataclass(frozen=True, slots=True)
class LiveObservation:
    timestamp_s: float
    mode: str
    request_id: str
    workload_case: str
    workload_family: str
    primary_anchor_id: str
    secondary_anchor_ids: tuple[str, ...]
    home_rank: int
    turn_index: int
    prompt_tokens: int
    output_tokens: int
    reusable_prefix_tokens: int
    remote_kv_bytes: int
    transfer_time_ms: float
    recompute_time_ms: float
    reuse_confidence: float
    queue_pressure: float
    policy_mode: str
    decision: str
    reused_tokens: int
    rationale: str
    runtime_effective_decision: str
    runtime_control_path: str
    runtime_cache_salt: str | None
    runtime_target_reuse_tokens: int
    runtime_target_tail_tokens: int
    runtime_decision_supported: bool
    runtime_support_tier: str
    runtime_fallback_reason: str | None
    decision_latency_ms: float
    boundary_alignment_latency_ms: float
    controller_latency_ms: float


def bind_request_headers(
    headers: Mapping[str, str] | None,
) -> contextvars.Token[dict[str, str]]:
    normalized: dict[str, str] = {}
    if headers is not None:
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    return REQUEST_HEADERS.set(normalized)


def reset_request_headers(token: contextvars.Token[dict[str, str]]) -> None:
    REQUEST_HEADERS.reset(token)


def get_request_headers() -> dict[str, str]:
    return dict(REQUEST_HEADERS.get())


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    with suppress(ValueError):
        return float(raw)
    logger.warning("Invalid float for %s=%r; using default %s", name, raw, default)
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    with suppress(ValueError):
        return int(raw)
    logger.warning("Invalid int for %s=%r; using default %s", name, raw, default)
    return default


def _header_float(headers: Mapping[str, str], name: str, default: float) -> float:
    raw = headers.get(name, "").strip()
    if not raw:
        return default
    with suppress(ValueError):
        return float(raw)
    return default


def _header_int(headers: Mapping[str, str], name: str, default: int) -> int:
    raw = headers.get(name, "").strip()
    if not raw:
        return default
    with suppress(ValueError):
        return int(raw)
    return default


def _split_secondary_anchor_ids(raw: str) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _default_reuse_confidence(
    anchor_seen_count: int, turn_index: int, reusable_prefix_tokens: int
) -> float:
    if reusable_prefix_tokens <= 0:
        return 0.0
    if anchor_seen_count > 0:
        return 0.95
    if turn_index > 0:
        return 0.7
    return 0.35


def estimate_reusable_prefix_tokens(
    headers: Mapping[str, str], prompt_tokens: int
) -> int:
    explicit = _header_int(headers, HEADER_SHARED_PREFIX_TOKENS, -1)
    if explicit >= 0:
        return min(explicit, max(prompt_tokens, 0))

    primary_anchor_id = headers.get(HEADER_PRIMARY_ANCHOR, "").strip()
    if not primary_anchor_id or prompt_tokens <= 0:
        return 0

    turn_index = _header_int(headers, HEADER_TURN_INDEX, 0)
    if turn_index > 0:
        return max(0, int(prompt_tokens * 0.6))
    return max(0, int(prompt_tokens * 0.35))


def estimate_signals(
    headers: Mapping[str, str], prompt_tokens: int, output_tokens: int
) -> tuple[MaterializationSignals, dict[str, Any]]:
    del output_tokens

    primary_anchor_id = headers.get(HEADER_PRIMARY_ANCHOR, "").strip()
    reusable_prefix_tokens = estimate_reusable_prefix_tokens(headers, prompt_tokens)
    turn_index = _header_int(headers, HEADER_TURN_INDEX, 0)

    anchor_seen_count = 0
    if primary_anchor_id:
        with _ANCHOR_LOCK:
            anchor_seen_count = _ANCHOR_SEEN_COUNTS.get(primary_anchor_id, 0)
            _ANCHOR_SEEN_COUNTS[primary_anchor_id] = anchor_seen_count + 1

    reuse_confidence = _header_float(
        headers,
        HEADER_REUSE_CONFIDENCE,
        _default_reuse_confidence(
            anchor_seen_count, turn_index, reusable_prefix_tokens
        ),
    )
    queue_pressure = _header_float(
        headers,
        HEADER_QUEUE_PRESSURE,
        _env_float("VLLM_KV_QUEUE_PRESSURE", DEFAULT_QUEUE_PRESSURE),
    )

    bytes_per_token = _env_int("VLLM_KV_BYTES_PER_TOKEN", DEFAULT_BYTES_PER_TOKEN)
    bandwidth_gbps = _env_float(
        "VLLM_KV_TRANSFER_BANDWIDTH_GBPS",
        DEFAULT_TRANSFER_BANDWIDTH_GBPS,
    )
    prefill_ms_per_1k = _env_float(
        "VLLM_KV_PREFILL_MS_PER_1K",
        DEFAULT_PREFILL_MS_PER_1K,
    )

    remote_kv_bytes = max(reusable_prefix_tokens, 0) * max(bytes_per_token, 0)
    transfer_time_ms = 0.0
    if bandwidth_gbps > 0.0:
        transfer_time_ms = (
            remote_kv_bytes / (bandwidth_gbps * 1_000_000_000.0)
        ) * 1000.0
    recompute_time_ms = (max(reusable_prefix_tokens, 0) / 1000.0) * prefill_ms_per_1k

    signals = MaterializationSignals(
        reusable_prefix_tokens=max(reusable_prefix_tokens, 0),
        remote_kv_bytes=max(remote_kv_bytes, 0),
        transfer_time_ms=max(transfer_time_ms, 0.0),
        recompute_time_ms=max(recompute_time_ms, 0.0),
        queue_pressure=max(queue_pressure, 0.0),
        ttft_sensitive=True,
        reuse_confidence=max(0.0, min(reuse_confidence, 1.0)),
    )
    extras = {
        "primary_anchor_id": primary_anchor_id,
        "secondary_anchor_ids": _split_secondary_anchor_ids(
            headers.get(HEADER_SECONDARY_ANCHORS, "")
        ),
        "workload_case": headers.get(HEADER_WORKLOAD_CASE, ""),
        "workload_family": headers.get(HEADER_WORKLOAD_FAMILY, ""),
        "home_rank": _header_int(headers, HEADER_HOME_RANK, 0),
        "turn_index": turn_index,
    }
    return signals, extras


def _make_policy() -> MaterializationPolicy:
    return MaterializationPolicy(
        partial_reuse_floor_tokens=_env_int("VLLM_KV_PARTIAL_REUSE_FLOOR_TOKENS", 256),
        queue_pressure_discount_ms=_env_float(
            "VLLM_KV_QUEUE_PRESSURE_DISCOUNT_MS", 0.5
        ),
        ttft_bonus_ms=_env_float("VLLM_KV_TTFT_BONUS_MS", 1.5),
        low_confidence_cutoff=_env_float("VLLM_KV_LOW_CONFIDENCE_CUTOFF", 0.55),
        confidence_penalty_ms=_env_float("VLLM_KV_CONFIDENCE_PENALTY_MS", 4.0),
    )


def _select_policy_outcome(
    signals: MaterializationSignals,
    policy: MaterializationPolicy,
) -> tuple[str, MaterializationOutcome]:
    policy_mode = os.getenv("VLLM_KV_POLICY_MODE", "controller").strip().lower()
    if policy_mode == "controller":
        return policy_mode, policy.decide(signals)
    if policy_mode == "always_recompute":
        return policy_mode, MaterializationOutcome(
            decision=MaterializationDecision.RECOMPUTE,
            reused_tokens=0,
            rationale="fixed_policy_always_recompute",
        )
    if policy_mode == "always_full_reuse":
        return policy_mode, MaterializationOutcome(
            decision=MaterializationDecision.FULL_REUSE,
            reused_tokens=max(signals.reusable_prefix_tokens, 0),
            rationale="fixed_policy_always_full_reuse",
        )
    raise ValueError(
        "VLLM_KV_POLICY_MODE must be controller, always_recompute, or "
        f"always_full_reuse; got {policy_mode!r}"
    )


def _make_anchor_scoped_salt(primary_anchor_id: str, workload_case: str) -> str | None:
    if primary_anchor_id:
        return f"kvmat:anchor:{primary_anchor_id}"
    if workload_case:
        return f"kvmat:case:{workload_case}"
    return None


def _pick_partial_fallback_anchor(
    primary_anchor_id: str,
    secondary_anchor_ids: tuple[str, ...],
) -> str:
    for anchor_id in secondary_anchor_ids:
        if "scaffold::" in anchor_id:
            return anchor_id
    return primary_anchor_id


def _make_partial_fallback_salt(
    primary_anchor_id: str,
    secondary_anchor_ids: tuple[str, ...],
    workload_case: str,
) -> str | None:
    selected_anchor_id = _pick_partial_fallback_anchor(
        primary_anchor_id,
        secondary_anchor_ids,
    )
    if selected_anchor_id:
        return f"kvmat:anchor:{selected_anchor_id}"
    if workload_case:
        return f"kvmat:case:{workload_case}"
    return None


def _make_request_scoped_salt(
    primary_anchor_id: str, workload_case: str, request_id: str
) -> str:
    prefix = primary_anchor_id or workload_case or "request"
    return f"kvmat:recompute:{prefix}:{request_id}"


def _get_runtime_hash_block_size() -> int:
    for env_name in (
        "VLLM_KV_RUNTIME_HASH_BLOCK_SIZE",
        "VLLM_KV_RUNTIME_BLOCK_SIZE",
    ):
        block_size = _env_int(env_name, 0)
        if block_size > 0:
            return block_size
    return 0


def _align_runtime_reuse_tokens(reuse_tokens: int, block_size: int) -> int:
    if block_size <= 1:
        return max(reuse_tokens, 0)
    return (max(reuse_tokens, 0) // block_size) * block_size


def _adjust_signals_for_runtime(
    signals: MaterializationSignals,
    policy: MaterializationPolicy,
) -> tuple[MaterializationSignals, MaterializationSignals]:
    adjusted_transfer_ms = signals.transfer_time_ms - (
        signals.queue_pressure * policy.queue_pressure_discount_ms
    )
    if signals.ttft_sensitive:
        adjusted_transfer_ms -= policy.ttft_bonus_ms

    adjusted_signals = replace(
        signals,
        transfer_time_ms=max(0.0, adjusted_transfer_ms),
    )
    full_reuse_signals = replace(
        adjusted_signals,
        transfer_time_ms=adjusted_signals.transfer_time_ms
        + (
            (1.0 - max(0.0, min(signals.reuse_confidence, 1.0)))
            * policy.confidence_penalty_ms
        ),
    )
    return adjusted_signals, full_reuse_signals


def _pick_realizable_runtime_action(
    signals: MaterializationSignals,
    policy: MaterializationPolicy,
    partial_reuse_tokens: int,
) -> str:
    adjusted_signals, full_reuse_signals = _adjust_signals_for_runtime(
        signals,
        policy,
    )
    candidates: list[tuple[float, str]] = [
        (
            estimate_materialization_ttft_ms(
                adjusted_signals,
                MaterializationDecision.RECOMPUTE,
                0,
                partial_reuse_floor_tokens=policy.partial_reuse_floor_tokens,
            ),
            "recompute",
        ),
        (
            estimate_materialization_ttft_ms(
                full_reuse_signals,
                MaterializationDecision.FULL_REUSE,
                signals.reusable_prefix_tokens,
                partial_reuse_floor_tokens=policy.partial_reuse_floor_tokens,
            ),
            "full_reuse",
        ),
    ]

    if 0 < partial_reuse_tokens < signals.reusable_prefix_tokens:
        candidates.append(
            (
                estimate_materialization_ttft_ms(
                    adjusted_signals,
                    MaterializationDecision.PARTIAL_REUSE,
                    partial_reuse_tokens,
                    partial_reuse_floor_tokens=policy.partial_reuse_floor_tokens,
                ),
                "partial_reuse",
            )
        )

    _, best_action = min(candidates, key=lambda item: item[0])
    return best_action


def build_runtime_control_extra_args(plan: RuntimeControlPlan) -> dict[str, Any]:
    return {
        RUNTIME_KV_TRANSFER_CONTROL_KEY: {
            "schema_version": RUNTIME_KV_TRANSFER_CONTROL_SCHEMA_VERSION,
            "observed_decision": plan.observed_decision,
            "effective_decision": plan.effective_decision,
            "control_path": plan.control_path,
            "decision_supported": plan.decision_supported,
            "support_tier": plan.support_tier,
            "fallback_reason": plan.fallback_reason,
            "target_reuse_tokens": plan.target_reuse_tokens,
            "target_tail_tokens": plan.target_tail_tokens,
            "segmented_tail_cache_salt": plan.segmented_tail_cache_salt,
            "requires_segmented_materialization": (
                plan.observed_decision == "partial_reuse"
            ),
        }
    }


def merge_runtime_control_extra_args(
    extra_args: Mapping[str, Any] | None,
    plan: RuntimeControlPlan,
) -> dict[str, Any]:
    merged = dict(extra_args or {})
    merged.update(build_runtime_control_extra_args(plan))
    return merged


def build_runtime_kv_transfer_params(plan: RuntimeControlPlan) -> dict[str, Any]:
    return build_runtime_control_extra_args(plan)


def merge_runtime_kv_transfer_params(
    kv_transfer_params: Mapping[str, Any] | None,
    plan: RuntimeControlPlan,
) -> dict[str, Any]:
    return merge_runtime_control_extra_args(kv_transfer_params, plan)


def compute_runtime_control(
    request_id: str,
    prompt_tokens: int,
    output_tokens: int,
) -> tuple[LiveObservation, RuntimeControlPlan]:
    controller_started_ns = time.perf_counter_ns()
    headers = get_request_headers()
    signals, extras = estimate_signals(headers, prompt_tokens, output_tokens)
    policy = _make_policy()
    decision_started_ns = time.perf_counter_ns()
    policy_mode, outcome = _select_policy_outcome(signals, policy)
    decision_latency_ms = (time.perf_counter_ns() - decision_started_ns) / 1_000_000
    boundary_alignment_latency_ms = 0.0

    primary_anchor_id = str(extras["primary_anchor_id"])
    secondary_anchor_ids = tuple(str(value) for value in extras["secondary_anchor_ids"])
    workload_case = str(extras["workload_case"])
    target_reuse_tokens = max(min(outcome.reused_tokens, max(prompt_tokens, 0)), 0)
    target_tail_tokens = max(max(prompt_tokens, 0) - target_reuse_tokens, 0)

    if outcome.decision.value == "recompute":
        plan = RuntimeControlPlan(
            observed_decision=outcome.decision.value,
            effective_decision="recompute",
            control_path="request_scoped_prefix_cache_bypass",
            cache_salt=_make_request_scoped_salt(
                primary_anchor_id, workload_case, request_id
            ),
            segmented_tail_cache_salt=None,
            target_reuse_tokens=target_reuse_tokens,
            target_tail_tokens=target_tail_tokens,
            decision_supported=True,
            support_tier=RUNTIME_SUPPORT_NATIVE,
            fallback_reason=None,
        )
    elif outcome.decision.value == "full_reuse":
        plan = RuntimeControlPlan(
            observed_decision=outcome.decision.value,
            effective_decision="full_reuse",
            control_path="anchor_scoped_prefix_cache",
            cache_salt=_make_anchor_scoped_salt(primary_anchor_id, workload_case),
            segmented_tail_cache_salt=None,
            target_reuse_tokens=target_reuse_tokens,
            target_tail_tokens=target_tail_tokens,
            decision_supported=True,
            support_tier=RUNTIME_SUPPORT_NATIVE,
            fallback_reason=None,
        )
    else:
        boundary_alignment_started_ns = time.perf_counter_ns()
        runtime_hash_block_size = _get_runtime_hash_block_size()
        aligned_reuse_tokens = min(
            _align_runtime_reuse_tokens(target_reuse_tokens, runtime_hash_block_size),
            max(signals.reusable_prefix_tokens, 0),
            max(prompt_tokens, 0),
        )
        aligned_tail_tokens = max(max(prompt_tokens, 0) - aligned_reuse_tokens, 0)

        runtime_seam = os.getenv("VLLM_KV_RUNTIME_SEAM", "segmented").strip().lower()
        if runtime_seam == "old":
            realizable_action = "full_reuse"
        elif runtime_hash_block_size > 0:
            realizable_action = _pick_realizable_runtime_action(
                signals,
                policy,
                aligned_reuse_tokens,
            )
        else:
            realizable_action = "full_reuse"

        if realizable_action == "partial_reuse" and aligned_reuse_tokens > 0:
            plan = RuntimeControlPlan(
                observed_decision=outcome.decision.value,
                effective_decision="partial_reuse",
                control_path="block_aligned_partial_prefix_cache",
                cache_salt=_make_partial_fallback_salt(
                    primary_anchor_id,
                    secondary_anchor_ids,
                    workload_case,
                ),
                segmented_tail_cache_salt=_make_request_scoped_salt(
                    primary_anchor_id,
                    workload_case,
                    request_id,
                ),
                target_reuse_tokens=aligned_reuse_tokens,
                target_tail_tokens=aligned_tail_tokens,
                decision_supported=True,
                support_tier=RUNTIME_SUPPORT_NATIVE,
                fallback_reason=(
                    PARTIAL_REUSE_ALIGNMENT_FALLBACK_REASON
                    if aligned_reuse_tokens != target_reuse_tokens
                    else None
                ),
            )
        elif realizable_action == "recompute":
            plan = RuntimeControlPlan(
                observed_decision=outcome.decision.value,
                effective_decision="recompute",
                control_path="partial_reuse_realigned_to_request_scoped_recompute",
                cache_salt=_make_request_scoped_salt(
                    primary_anchor_id,
                    workload_case,
                    request_id,
                ),
                segmented_tail_cache_salt=None,
                target_reuse_tokens=0,
                target_tail_tokens=max(prompt_tokens, 0),
                decision_supported=False,
                support_tier=RUNTIME_SUPPORT_FALLBACK,
                fallback_reason=PARTIAL_REUSE_RUNTIME_REALIGN_TO_RECOMPUTE,
            )
        else:
            plan = RuntimeControlPlan(
                observed_decision=outcome.decision.value,
                effective_decision="full_reuse",
                control_path="partial_reuse_fallback_to_anchor_scoped_full_reuse",
                cache_salt=_make_partial_fallback_salt(
                    primary_anchor_id,
                    secondary_anchor_ids,
                    workload_case,
                ),
                segmented_tail_cache_salt=None,
                target_reuse_tokens=max(signals.reusable_prefix_tokens, 0),
                target_tail_tokens=max(
                    max(prompt_tokens, 0) - max(signals.reusable_prefix_tokens, 0), 0
                ),
                decision_supported=False,
                support_tier=RUNTIME_SUPPORT_FALLBACK,
                fallback_reason=(
                    PARTIAL_REUSE_FALLBACK_REASON
                    if runtime_seam == "old"
                    else (
                        PARTIAL_REUSE_RUNTIME_REALIGN_TO_FULL_REUSE
                        if runtime_hash_block_size > 0
                        else PARTIAL_REUSE_FALLBACK_REASON
                    )
                ),
            )
        boundary_alignment_latency_ms = (
            time.perf_counter_ns() - boundary_alignment_started_ns
        ) / 1_000_000

    controller_latency_ms = (time.perf_counter_ns() - controller_started_ns) / 1_000_000

    observation = LiveObservation(
        timestamp_s=time.time(),
        mode=os.getenv(
            "VLLM_KV_MATERIALIZATION_PLUGIN_MODE", "prefix_cache_runtime_control"
        ),
        request_id=headers.get(HEADER_REQUEST_ID, request_id) or request_id,
        workload_case=workload_case,
        workload_family=str(extras["workload_family"]),
        primary_anchor_id=primary_anchor_id,
        secondary_anchor_ids=secondary_anchor_ids,
        home_rank=int(extras["home_rank"]),
        turn_index=int(extras["turn_index"]),
        prompt_tokens=max(prompt_tokens, 0),
        output_tokens=max(output_tokens, 0),
        reusable_prefix_tokens=signals.reusable_prefix_tokens,
        remote_kv_bytes=signals.remote_kv_bytes,
        transfer_time_ms=round(signals.transfer_time_ms, 6),
        recompute_time_ms=round(signals.recompute_time_ms, 6),
        reuse_confidence=round(signals.reuse_confidence, 6),
        queue_pressure=round(signals.queue_pressure, 6),
        policy_mode=policy_mode,
        decision=outcome.decision.value,
        reused_tokens=outcome.reused_tokens,
        rationale=outcome.rationale,
        runtime_effective_decision=plan.effective_decision,
        runtime_control_path=plan.control_path,
        runtime_cache_salt=plan.cache_salt,
        runtime_target_reuse_tokens=plan.target_reuse_tokens,
        runtime_target_tail_tokens=plan.target_tail_tokens,
        runtime_decision_supported=plan.decision_supported,
        runtime_support_tier=plan.support_tier,
        runtime_fallback_reason=plan.fallback_reason,
        decision_latency_ms=round(decision_latency_ms, 6),
        boundary_alignment_latency_ms=round(boundary_alignment_latency_ms, 6),
        controller_latency_ms=round(controller_latency_ms, 6),
    )
    return observation, plan


def apply_runtime_control(prompt: Any, plan: RuntimeControlPlan) -> Any:
    if plan.cache_salt is None:
        return prompt
    if not isinstance(prompt, dict):
        return prompt

    prompt_copy = dict(prompt)
    if prompt_copy.get("type") == "enc_dec" and isinstance(
        prompt_copy.get("decoder_prompt"), dict
    ):
        decoder_prompt = dict(prompt_copy["decoder_prompt"])
        decoder_prompt["cache_salt"] = plan.cache_salt
        prompt_copy["decoder_prompt"] = decoder_prompt
        return prompt_copy

    prompt_copy["cache_salt"] = plan.cache_salt
    return prompt_copy


def observe_request(
    request_id: str, prompt_tokens: int, output_tokens: int
) -> LiveObservation:
    observation, _ = compute_runtime_control(request_id, prompt_tokens, output_tokens)
    if observation.primary_anchor_id:
        with _ANCHOR_LOCK:
            _ANCHOR_SEEN_COUNTS[observation.primary_anchor_id] = (
                _ANCHOR_SEEN_COUNTS.get(observation.primary_anchor_id, 0) + 1
            )
    _append_observation(observation)
    return observation


def _append_observation(observation: LiveObservation) -> None:
    log_path = os.getenv("VLLM_KV_MATERIALIZATION_LOG_PATH", "").strip()
    if not log_path:
        return
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(observation), sort_keys=True)
    with _LOG_LOCK, path.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.write("\n")
