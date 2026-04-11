from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MaterializationDecision(str, Enum):
    FULL_REUSE = "full_reuse"
    PARTIAL_REUSE = "partial_reuse"
    RECOMPUTE = "recompute"


@dataclass(slots=True)
class MaterializationSignals:
    reusable_prefix_tokens: int
    remote_kv_bytes: int
    transfer_time_ms: float
    recompute_time_ms: float
    queue_pressure: float
    ttft_sensitive: bool = True
    reuse_confidence: float = 0.0


@dataclass(slots=True)
class MaterializationOutcome:
    decision: MaterializationDecision
    reused_tokens: int
    rationale: str


class MaterializationPolicy:
    """Small interpretable policy model for trace-driven experiments."""

    def __init__(
        self,
        *,
        partial_reuse_floor_tokens: int = 256,
        queue_pressure_discount_ms: float = 0.5,
        ttft_bonus_ms: float = 1.5,
        low_confidence_cutoff: float = 0.55,
        confidence_penalty_ms: float = 4.0,
    ) -> None:
        self.partial_reuse_floor_tokens = partial_reuse_floor_tokens
        self.queue_pressure_discount_ms = queue_pressure_discount_ms
        self.ttft_bonus_ms = ttft_bonus_ms
        self.low_confidence_cutoff = low_confidence_cutoff
        self.confidence_penalty_ms = confidence_penalty_ms

    def decide(self, signals: MaterializationSignals) -> MaterializationOutcome:
        if signals.reusable_prefix_tokens <= 0:
            return MaterializationOutcome(
                decision=MaterializationDecision.RECOMPUTE,
                reused_tokens=0,
                rationale="no_reusable_prefix",
            )

        adjusted_transfer_ms = signals.transfer_time_ms - (
            signals.queue_pressure * self.queue_pressure_discount_ms
        )
        if signals.ttft_sensitive:
            adjusted_transfer_ms -= self.ttft_bonus_ms

        adjusted_transfer_ms += (1.0 - max(0.0, min(signals.reuse_confidence, 1.0))) * self.confidence_penalty_ms

        full_reuse_threshold = signals.recompute_time_ms * (0.5 + (0.25 * max(signals.reuse_confidence, 0.0)))

        if (
            signals.reusable_prefix_tokens >= self.partial_reuse_floor_tokens
            and signals.reuse_confidence < self.low_confidence_cutoff
        ):
            return MaterializationOutcome(
                decision=MaterializationDecision.PARTIAL_REUSE,
                reused_tokens=max(self.partial_reuse_floor_tokens, signals.reusable_prefix_tokens // 3),
                rationale="partial_reuse_for_low_confidence_prefix",
            )

        if adjusted_transfer_ms <= full_reuse_threshold:
            return MaterializationOutcome(
                decision=MaterializationDecision.FULL_REUSE,
                reused_tokens=signals.reusable_prefix_tokens,
                rationale="full_reuse_transfer_cheaper_than_recompute",
            )

        if signals.reusable_prefix_tokens >= self.partial_reuse_floor_tokens:
            reused_tokens = max(
                self.partial_reuse_floor_tokens,
                signals.reusable_prefix_tokens // 2,
            )
            if signals.reuse_confidence < self.low_confidence_cutoff:
                reused_tokens = max(self.partial_reuse_floor_tokens, signals.reusable_prefix_tokens // 3)
            return MaterializationOutcome(
                decision=MaterializationDecision.PARTIAL_REUSE,
                reused_tokens=reused_tokens,
                rationale="partial_reuse_balances_transfer_and_recompute",
            )

        return MaterializationOutcome(
            decision=MaterializationDecision.RECOMPUTE,
            reused_tokens=0,
            rationale="recompute_cheaper_for_small_reuse_window",
        )
