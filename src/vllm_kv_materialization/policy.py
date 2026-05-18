from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
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


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))


def estimate_confident_reuse_tokens(
    signals: MaterializationSignals,
    *,
    partial_reuse_floor_tokens: int,
) -> int:
    total_tokens = max(signals.reusable_prefix_tokens, 0)
    if total_tokens <= 0:
        return 0
    if total_tokens <= partial_reuse_floor_tokens:
        return total_tokens

    floor_ratio = max(partial_reuse_floor_tokens / total_tokens, 0.18)
    confident_ratio = 0.18 + (0.72 * _clamp01(signals.reuse_confidence))
    if signals.ttft_sensitive:
        confident_ratio += 0.05
    confident_ratio -= 0.06 * max(signals.queue_pressure - 0.5, 0.0)
    confident_ratio = max(floor_ratio, min(confident_ratio, 0.92))
    return min(total_tokens, max(partial_reuse_floor_tokens, int(round(total_tokens * confident_ratio))))


def estimate_materialization_ttft_ms(
    signals: MaterializationSignals,
    decision: MaterializationDecision,
    reused_tokens: int,
    *,
    partial_reuse_floor_tokens: int,
) -> float:
    total_tokens = max(signals.reusable_prefix_tokens, 0)
    if decision is MaterializationDecision.RECOMPUTE or total_tokens <= 0:
        return round(signals.recompute_time_ms, 3)

    if decision is MaterializationDecision.FULL_REUSE:
        reused_tokens = total_tokens
    else:
        reused_tokens = min(max(reused_tokens, 0), total_tokens)
        if reused_tokens <= 0:
            return round(signals.recompute_time_ms, 3)

    confident_tokens = estimate_confident_reuse_tokens(
        signals,
        partial_reuse_floor_tokens=partial_reuse_floor_tokens,
    )
    confident_reused_tokens = min(reused_tokens, confident_tokens)
    uncertain_reused_tokens = max(0, reused_tokens - confident_tokens)
    uncertain_tail_discount = 0.5 + (0.4 * _clamp01(signals.reuse_confidence))
    effective_reused_tokens = confident_reused_tokens + (
        uncertain_reused_tokens * uncertain_tail_discount
    )

    transfer_ratio = reused_tokens / total_tokens
    effective_reuse_ratio = min(1.0, effective_reused_tokens / total_tokens)
    uncertain_ratio = uncertain_reused_tokens / total_tokens

    transfer_component_ms = signals.transfer_time_ms * transfer_ratio
    recompute_component_ms = signals.recompute_time_ms * (1.0 - effective_reuse_ratio)
    tail_penalty_ms = (
        (signals.recompute_time_ms * 0.25) + (signals.transfer_time_ms * 0.1)
    ) * uncertain_ratio * (1.0 - _clamp01(signals.reuse_confidence))

    if decision is MaterializationDecision.FULL_REUSE:
        control_overhead_ms = 0.8
    else:
        control_overhead_ms = 0.6 + (0.25 if signals.ttft_sensitive else 0.0) + (
            0.15 * signals.queue_pressure
        )

    return round(
        transfer_component_ms
        + recompute_component_ms
        + tail_penalty_ms
        + control_overhead_ms,
        3,
    )


def optimize_partial_reuse_tokens(
    signals: MaterializationSignals,
    *,
    partial_reuse_floor_tokens: int,
) -> int:
    total_tokens = max(signals.reusable_prefix_tokens, 0)
    if total_tokens < partial_reuse_floor_tokens:
        return 0

    confident_tokens = estimate_confident_reuse_tokens(
        signals,
        partial_reuse_floor_tokens=partial_reuse_floor_tokens,
    )
    step_tokens = max(64, partial_reuse_floor_tokens // 2)
    candidate_tokens = {
        partial_reuse_floor_tokens,
        max(partial_reuse_floor_tokens, total_tokens // 3),
        max(partial_reuse_floor_tokens, total_tokens // 2),
        max(partial_reuse_floor_tokens, (2 * total_tokens) // 3),
        max(partial_reuse_floor_tokens, confident_tokens - step_tokens),
        confident_tokens,
        min(total_tokens - 1, confident_tokens + step_tokens),
    }
    candidate_tokens = {
        min(total_tokens - 1, tokens)
        for tokens in candidate_tokens
        if partial_reuse_floor_tokens <= tokens < total_tokens
    }
    if not candidate_tokens:
        return 0

    return min(
        candidate_tokens,
        key=lambda tokens: estimate_materialization_ttft_ms(
            signals,
            MaterializationDecision.PARTIAL_REUSE,
            tokens,
            partial_reuse_floor_tokens=partial_reuse_floor_tokens,
        ),
    )


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

        adjusted_signals = replace(
            signals,
            transfer_time_ms=max(0.0, adjusted_transfer_ms),
        )
        full_reuse_signals = replace(
            adjusted_signals,
            transfer_time_ms=adjusted_signals.transfer_time_ms
            + ((1.0 - _clamp01(signals.reuse_confidence)) * self.confidence_penalty_ms),
        )

        candidate_outcomes: list[tuple[float, MaterializationOutcome]] = [
            (
                estimate_materialization_ttft_ms(
                    adjusted_signals,
                    MaterializationDecision.RECOMPUTE,
                    0,
                    partial_reuse_floor_tokens=self.partial_reuse_floor_tokens,
                ),
                MaterializationOutcome(
                    decision=MaterializationDecision.RECOMPUTE,
                    reused_tokens=0,
                    rationale="recompute_cheaper_for_small_reuse_window",
                ),
            ),
            (
                estimate_materialization_ttft_ms(
                    full_reuse_signals,
                    MaterializationDecision.FULL_REUSE,
                    signals.reusable_prefix_tokens,
                    partial_reuse_floor_tokens=self.partial_reuse_floor_tokens,
                ),
                MaterializationOutcome(
                    decision=MaterializationDecision.FULL_REUSE,
                    reused_tokens=signals.reusable_prefix_tokens,
                    rationale="full_reuse_transfer_cheaper_than_recompute",
                ),
            ),
        ]

        partial_tokens = optimize_partial_reuse_tokens(
            adjusted_signals,
            partial_reuse_floor_tokens=self.partial_reuse_floor_tokens,
        )
        if partial_tokens > 0:
            confident_tokens = estimate_confident_reuse_tokens(
                adjusted_signals,
                partial_reuse_floor_tokens=self.partial_reuse_floor_tokens,
            )
            partial_rationale = "partial_reuse_balances_transfer_and_recompute"
            if (
                adjusted_signals.reuse_confidence < self.low_confidence_cutoff
                and partial_tokens <= confident_tokens + max(64, self.partial_reuse_floor_tokens // 2)
            ):
                partial_rationale = "partial_reuse_trims_low_confidence_tail"
            candidate_outcomes.append(
                (
                    estimate_materialization_ttft_ms(
                        adjusted_signals,
                        MaterializationDecision.PARTIAL_REUSE,
                        partial_tokens,
                        partial_reuse_floor_tokens=self.partial_reuse_floor_tokens,
                    ),
                    MaterializationOutcome(
                        decision=MaterializationDecision.PARTIAL_REUSE,
                        reused_tokens=partial_tokens,
                        rationale=partial_rationale,
                    ),
                )
            )

        _, best_outcome = min(candidate_outcomes, key=lambda item: item[0])
        return best_outcome
