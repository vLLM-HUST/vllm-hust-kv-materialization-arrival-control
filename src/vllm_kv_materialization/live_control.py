from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
from contextlib import suppress
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Mapping

from vllm_kv_materialization.policy import MaterializationPolicy
from vllm_kv_materialization.policy import MaterializationSignals

logger = logging.getLogger(__name__)

REQUEST_HEADERS: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "vllm_kv_materialization_request_headers",
    default={},
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


@dataclass(frozen=True, slots=True)
class RuntimeControlPlan:
    observed_decision: str
    effective_decision: str
    control_path: str
    cache_salt: str | None
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
    decision: str
    reused_tokens: int
    rationale: str
    runtime_effective_decision: str
    runtime_control_path: str
    runtime_cache_salt: str | None
    runtime_decision_supported: bool
    runtime_support_tier: str
    runtime_fallback_reason: str | None


def bind_request_headers(headers: Mapping[str, str] | None) -> contextvars.Token[dict[str, str]]:
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


def _default_reuse_confidence(anchor_seen_count: int, turn_index: int, reusable_prefix_tokens: int) -> float:
    if reusable_prefix_tokens <= 0:
        return 0.0
    if anchor_seen_count > 0:
        return 0.95
    if turn_index > 0:
        return 0.7
    return 0.35


def estimate_reusable_prefix_tokens(headers: Mapping[str, str], prompt_tokens: int) -> int:
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


def estimate_signals(headers: Mapping[str, str], prompt_tokens: int, output_tokens: int) -> tuple[MaterializationSignals, dict[str, Any]]:
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
        _default_reuse_confidence(anchor_seen_count, turn_index, reusable_prefix_tokens),
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
        transfer_time_ms = (remote_kv_bytes / (bandwidth_gbps * 1_000_000_000.0)) * 1000.0
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
        queue_pressure_discount_ms=_env_float("VLLM_KV_QUEUE_PRESSURE_DISCOUNT_MS", 0.5),
        ttft_bonus_ms=_env_float("VLLM_KV_TTFT_BONUS_MS", 1.5),
        low_confidence_cutoff=_env_float("VLLM_KV_LOW_CONFIDENCE_CUTOFF", 0.55),
        confidence_penalty_ms=_env_float("VLLM_KV_CONFIDENCE_PENALTY_MS", 4.0),
    )


def _make_anchor_scoped_salt(primary_anchor_id: str, workload_case: str) -> str | None:
    if primary_anchor_id:
        return f"kvmat:anchor:{primary_anchor_id}"
    if workload_case:
        return f"kvmat:case:{workload_case}"
    return None


def _make_request_scoped_salt(primary_anchor_id: str, workload_case: str, request_id: str) -> str:
    prefix = primary_anchor_id or workload_case or "request"
    return f"kvmat:recompute:{prefix}:{request_id}"


def compute_runtime_control(
    request_id: str,
    prompt_tokens: int,
    output_tokens: int,
) -> tuple[LiveObservation, RuntimeControlPlan]:
    headers = get_request_headers()
    signals, extras = estimate_signals(headers, prompt_tokens, output_tokens)
    outcome = _make_policy().decide(signals)

    primary_anchor_id = str(extras["primary_anchor_id"])
    workload_case = str(extras["workload_case"])

    if outcome.decision.value == "recompute":
        plan = RuntimeControlPlan(
            observed_decision=outcome.decision.value,
            effective_decision="recompute",
            control_path="request_scoped_prefix_cache_bypass",
            cache_salt=_make_request_scoped_salt(primary_anchor_id, workload_case, request_id),
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
            decision_supported=True,
            support_tier=RUNTIME_SUPPORT_NATIVE,
            fallback_reason=None,
        )
    else:
        plan = RuntimeControlPlan(
            observed_decision=outcome.decision.value,
            effective_decision="full_reuse",
            control_path="partial_reuse_fallback_to_anchor_scoped_full_reuse",
            cache_salt=_make_anchor_scoped_salt(primary_anchor_id, workload_case),
            decision_supported=False,
            support_tier=RUNTIME_SUPPORT_FALLBACK,
            fallback_reason=PARTIAL_REUSE_FALLBACK_REASON,
        )

    observation = LiveObservation(
        timestamp_s=time.time(),
        mode=os.getenv("VLLM_KV_MATERIALIZATION_PLUGIN_MODE", "prefix_cache_runtime_control"),
        request_id=headers.get(HEADER_REQUEST_ID, request_id) or request_id,
        workload_case=workload_case,
        workload_family=str(extras["workload_family"]),
        primary_anchor_id=primary_anchor_id,
        secondary_anchor_ids=tuple(str(value) for value in extras["secondary_anchor_ids"]),
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
        decision=outcome.decision.value,
        reused_tokens=outcome.reused_tokens,
        rationale=outcome.rationale,
        runtime_effective_decision=plan.effective_decision,
        runtime_control_path=plan.control_path,
        runtime_cache_salt=plan.cache_salt,
        runtime_decision_supported=plan.decision_supported,
        runtime_support_tier=plan.support_tier,
        runtime_fallback_reason=plan.fallback_reason,
    )
    return observation, plan


def apply_runtime_control(prompt: Any, plan: RuntimeControlPlan) -> Any:
    if plan.cache_salt is None:
        return prompt
    if not isinstance(prompt, dict):
        return prompt

    prompt_copy = dict(prompt)
    if prompt_copy.get("type") == "enc_dec" and isinstance(prompt_copy.get("decoder_prompt"), dict):
        decoder_prompt = dict(prompt_copy["decoder_prompt"])
        decoder_prompt["cache_salt"] = plan.cache_salt
        prompt_copy["decoder_prompt"] = decoder_prompt
        return prompt_copy

    prompt_copy["cache_salt"] = plan.cache_salt
    return prompt_copy


def observe_request(request_id: str, prompt_tokens: int, output_tokens: int) -> LiveObservation:
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
    with _LOG_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
