from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VIOLATION_PARTIAL = "partial_layer_range"
VIOLATION_STALE = "stale_generation"
VIOLATION_DUPLICATE = "duplicate_consume"
VIOLATION_ABA = "aba_generation_reuse"
VIOLATION_LOAD_FAILURE = "load_failure"
VIOLATION_ACK_BEFORE_CONSUME = "ack_without_consume"
VIOLATION_REUSE_BEFORE_ACK = "reuse_before_ack"
VIOLATION_ORPHAN_AFTER_RECOVERY = "orphan_after_recovery"
VIOLATION_DIGEST_MISMATCH = "digest_mismatch"


class SeamGateViolation(Exception):
    """Fail-closed rejection raised by the seam-gate host fixture."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class LayerGroupRef:
    request_id: str
    cache_id: str
    layer_start: int
    layer_end: int
    generation: int

    @property
    def identity(self) -> tuple[str, str, int, int]:
        return (self.request_id, self.cache_id, self.layer_start, self.layer_end)


@dataclass(frozen=True, slots=True)
class LayerGroupReadiness:
    ref: LayerGroupRef
    ready_event: str
    digest: str


@dataclass(frozen=True, slots=True)
class ConsumerAck:
    ref: LayerGroupRef
    digest: str


@dataclass(frozen=True, slots=True)
class _Slot:
    ref: LayerGroupRef
    digest: str
    ready_event: str
    status: str


_STATUS_REGISTERED = "registered"
_STATUS_READY = "ready"
_STATUS_CONSUMED = "consumed"
_STATUS_ACKED = "acked"
_STATUS_LOAD_FAILED = "load_failed"


class WavematGateState:
    """Host-side fail-closed state fixture for WaveMat M0 seam-gate tests.

    This is intentionally not a vLLM runtime hook. It only encodes the ownership
    and generation contract that must later be checked against the actual
    Ascend layer-ready/consume path.
    """

    def __init__(self) -> None:
        self._slots: dict[tuple[str, str, int, int], _Slot] = {}
        self._last_generation: dict[tuple[str, str, int, int], int] = {}
        self.rejections: list[dict[str, Any]] = []

    def _violation(self, code: str, message: str) -> SeamGateViolation:
        self.rejections.append({"code": code, "message": message})
        return SeamGateViolation(code, message)

    def register(
        self,
        ref: LayerGroupRef,
        digest: str,
        ready_event: str,
    ) -> None:
        key = ref.identity
        previous = self._slots.get(key)
        last_generation = self._last_generation.get(key)

        if previous is not None and previous.status not in {
            _STATUS_ACKED,
        }:
            raise self._violation(
                VIOLATION_REUSE_BEFORE_ACK,
                f"slot {key!r} generation {previous.ref.generation} "
                f"not acked before reuse",
            )

        if last_generation is not None and ref.generation <= last_generation:
            raise self._violation(
                VIOLATION_ABA if ref.generation == last_generation else VIOLATION_STALE,
                f"generation {ref.generation} cannot reuse identity {key!r} "
                f"after generation {last_generation}",
            )

        self._slots[key] = _Slot(
            ref=ref,
            digest=digest,
            ready_event=ready_event,
            status=_STATUS_REGISTERED,
        )
        self._last_generation[key] = ref.generation

    def mark_load_failure(self, ref: LayerGroupRef) -> None:
        key = ref.identity
        slot = self._slots.get(key)
        if slot is None or slot.ref.generation != ref.generation:
            raise self._violation(
                VIOLATION_STALE,
                f"cannot fail unknown/stale generation {ref.generation} for {key!r}",
            )
        self._slots[key] = _Slot(
            ref=slot.ref,
            digest=slot.digest,
            ready_event=slot.ready_event,
            status=_STATUS_LOAD_FAILED,
        )

    def mark_ready(
        self,
        ref: LayerGroupRef,
        digest: str,
        ready_event: str,
    ) -> None:
        key = ref.identity
        slot = self._slots.get(key)
        if slot is None:
            raise self._violation(
                VIOLATION_STALE,
                f"unknown layer group {key!r}",
            )
        if slot.ref.generation != ref.generation:
            raise self._violation(
                VIOLATION_STALE,
                f"ready for generation {ref.generation} while registered "
                f"generation is {slot.ref.generation}",
            )
        if slot.status == _STATUS_LOAD_FAILED:
            raise self._violation(
                VIOLATION_LOAD_FAILURE,
                f"layer group {key!r} already marked load-failed",
            )
        if slot.digest != digest:
            raise self._violation(
                VIOLATION_DIGEST_MISMATCH,
                f"ready digest mismatch for {key!r}",
            )

        self._slots[key] = _Slot(
            ref=slot.ref,
            digest=slot.digest,
            ready_event=ready_event,
            status=_STATUS_READY,
        )

    def consume(self, ref: LayerGroupRef, digest: str) -> None:
        key = ref.identity
        slot = self._slots.get(key)
        if slot is None:
            raise self._violation(
                VIOLATION_STALE,
                f"unknown layer group {key!r}",
            )
        if slot.ref.generation != ref.generation:
            raise self._violation(
                VIOLATION_STALE,
                f"consume generation {ref.generation} while registered "
                f"generation is {slot.ref.generation}",
            )
        if slot.status == _STATUS_LOAD_FAILED:
            raise self._violation(
                VIOLATION_LOAD_FAILURE,
                f"cannot consume load-failed layer group {key!r}",
            )
        if slot.status == _STATUS_REGISTERED:
            raise self._violation(
                VIOLATION_PARTIAL,
                f"cannot consume partial layer group {key!r} before ready",
            )
        if slot.status == _STATUS_CONSUMED:
            raise self._violation(
                VIOLATION_DUPLICATE,
                f"duplicate consume for layer group {key!r}",
            )
        if slot.status == _STATUS_ACKED:
            raise self._violation(
                VIOLATION_ABA,
                f"consume after ack for layer group {key!r}",
            )
        if slot.digest != digest:
            raise self._violation(
                VIOLATION_DIGEST_MISMATCH,
                f"consume digest mismatch for {key!r}",
            )

        self._slots[key] = _Slot(
            ref=slot.ref,
            digest=slot.digest,
            ready_event=slot.ready_event,
            status=_STATUS_CONSUMED,
        )

    def ack(self, ref: LayerGroupRef, digest: str) -> None:
        key = ref.identity
        slot = self._slots.get(key)
        if slot is None:
            raise self._violation(
                VIOLATION_STALE,
                f"unknown layer group {key!r}",
            )
        if slot.ref.generation != ref.generation:
            raise self._violation(
                VIOLATION_STALE,
                f"ack generation {ref.generation} while registered "
                f"generation is {slot.ref.generation}",
            )
        if slot.status != _STATUS_CONSUMED:
            raise self._violation(
                VIOLATION_ACK_BEFORE_CONSUME,
                f"ack for layer group {key!r} before consume",
            )
        if slot.digest != digest:
            raise self._violation(
                VIOLATION_DIGEST_MISMATCH,
                f"ack digest mismatch for {key!r}",
            )

        self._slots[key] = _Slot(
            ref=slot.ref,
            digest=slot.digest,
            ready_event=slot.ready_event,
            status=_STATUS_ACKED,
        )

    def recover(self) -> list[LayerGroupRef]:
        """Return non-acked slots; non-empty means an orphan-buffer violation."""
        orphans = [
            slot.ref
            for slot in self._slots.values()
            if slot.status in {_STATUS_REGISTERED, _STATUS_READY, _STATUS_CONSUMED}
        ]
        if orphans:
            self.rejections.append(
                {
                    "code": VIOLATION_ORPHAN_AFTER_RECOVERY,
                    "message": f"{len(orphans)} orphan slot(s) after recovery",
                }
            )
        return orphans


def _ref(
    request_id: str = "req-1",
    cache_id: str = "cache-1",
    layer_start: int = 0,
    layer_end: int = 4,
    generation: int = 1,
) -> LayerGroupRef:
    return LayerGroupRef(
        request_id=request_id,
        cache_id=cache_id,
        layer_start=layer_start,
        layer_end=layer_end,
        generation=generation,
    )


def _expect_violation(
    operation: Any,
    expected_code: str,
) -> dict[str, Any]:
    try:
        operation()
    except SeamGateViolation as exc:
        return {
            "pass": exc.code == expected_code,
            "expected": expected_code,
            "observed": exc.code,
            "detail": str(exc),
        }
    return {
        "pass": False,
        "expected": expected_code,
        "observed": None,
        "detail": "operation unexpectedly succeeded",
    }


def _expect_recovery_violation(
    operation: Any,
) -> dict[str, Any]:
    try:
        state = operation()
    except SeamGateViolation as exc:
        return {
            "pass": exc.code == VIOLATION_ORPHAN_AFTER_RECOVERY,
            "expected": VIOLATION_ORPHAN_AFTER_RECOVERY,
            "observed": exc.code,
            "detail": str(exc),
        }

    observed = [
        item["code"]
        for item in state.rejections
        if item["code"] == VIOLATION_ORPHAN_AFTER_RECOVERY
    ]
    return {
        "pass": bool(observed),
        "expected": VIOLATION_ORPHAN_AFTER_RECOVERY,
        "observed": observed[0] if observed else None,
        "detail": (
            "orphan slot(s) detected"
            if observed
            else "operation unexpectedly succeeded without orphan detection"
        ),
    }


def run_failure_injection_matrix() -> list[dict[str, Any]]:
    """Run a deterministic host-side failure matrix.

    This output is a correctness fixture result, not an end-to-end performance
    result and not evidence that a real per-layer Ascend seam exists.
    """

    results: list[dict[str, Any]] = []

    def partial_case() -> None:
        state = WavematGateState()
        ref = _ref(generation=1)
        state.register(ref, "digest-a", "event-a")
        state.consume(ref, "digest-a")

    results.append(
        {
            "case": "partial",
            **_expect_violation(partial_case, VIOLATION_PARTIAL),
        }
    )

    def stale_case() -> None:
        state = WavematGateState()
        state.register(_ref(generation=2), "digest-a", "event-a")
        state.consume(_ref(generation=1), "digest-a")

    results.append(
        {
            "case": "stale",
            **_expect_violation(stale_case, VIOLATION_STALE),
        }
    )

    def duplicate_case() -> None:
        state = WavematGateState()
        ref = _ref(generation=1)
        state.register(ref, "digest-a", "event-a")
        state.mark_ready(ref, "digest-a", "event-a")
        state.consume(ref, "digest-a")
        state.consume(ref, "digest-a")

    results.append(
        {
            "case": "duplicate",
            **_expect_violation(duplicate_case, VIOLATION_DUPLICATE),
        }
    )

    def aba_case() -> None:
        state = WavematGateState()
        ref = _ref(generation=1)
        state.register(ref, "digest-a", "event-a")
        state.mark_ready(ref, "digest-a", "event-a")
        state.consume(ref, "digest-a")
        state.ack(ref, "digest-a")
        state.register(ref, "digest-a", "event-a")

    results.append(
        {
            "case": "aba",
            **_expect_violation(aba_case, VIOLATION_ABA),
        }
    )

    def load_failure_case() -> None:
        state = WavematGateState()
        ref = _ref(generation=1)
        state.register(ref, "digest-a", "event-a")
        state.mark_load_failure(ref)
        state.consume(ref, "digest-a")

    results.append(
        {
            "case": "load_failure",
            **_expect_violation(load_failure_case, VIOLATION_LOAD_FAILURE),
        }
    )

    def digest_mismatch_case() -> None:
        state = WavematGateState()
        ref = _ref(generation=1)
        state.register(ref, "digest-a", "event-a")
        state.mark_ready(ref, "digest-a", "event-a")
        state.consume(ref, "digest-b")

    results.append(
        {
            "case": "digest_mismatch",
            **_expect_violation(digest_mismatch_case, VIOLATION_DIGEST_MISMATCH),
        }
    )

    def reuse_before_ack_case() -> None:
        state = WavematGateState()
        ref = _ref(generation=1)
        state.register(ref, "digest-a", "event-a")
        state.register(_ref(generation=2), "digest-a", "event-a")

    results.append(
        {
            "case": "reuse_before_ack",
            **_expect_violation(reuse_before_ack_case, VIOLATION_REUSE_BEFORE_ACK),
        }
    )

    def crash_recovery_case() -> WavematGateState:
        state = WavematGateState()
        ref = _ref(generation=1)
        state.register(ref, "digest-a", "event-a")
        state.mark_ready(ref, "digest-a", "event-a")
        state.consume(ref, "digest-a")
        state.recover()
        return state

    results.append(
        {
            "case": "crash_recovery_orphan_detection",
            **_expect_recovery_violation(crash_recovery_case),
        }
    )

    return results


def build_gate_manifest(
    parent_commit: str,
    carrier_gitlink: str,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    passed = all(bool(item["pass"]) for item in results)
    return {
        "artifact": "m3-wavemat-seam-gate-pr1",
        "evidence_class": "host_fixture_correctness",
        "is_end_to_end_performance_evidence": False,
        "is_wavemat_mechanism_enabled": False,
        "parent_commit": parent_commit,
        "vendor_vllm_gitlink_at_parent_head": carrier_gitlink,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "failure_injection_cases": results,
        "all_failure_injection_cases_pass": passed,
        "claim": (
            "Host-side fail-closed generation/digest contract fixture passes "
            "for partial/stale/duplicate/ABA/load-failure/digest-mismatch/"
            "reuse-before-ack and detects orphan slots after crash recovery. "
            "This does not prove a real Ascend per-layer consumer seam."
        ),
    }


def write_raw_results(
    output_path: Path,
    parent_commit: str,
    carrier_gitlink: str,
) -> dict[str, Any]:
    results = run_failure_injection_matrix()
    manifest = build_gate_manifest(parent_commit, carrier_gitlink, results)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


__all__ = [
    "ConsumerAck",
    "LayerGroupReadiness",
    "LayerGroupRef",
    "SeamGateViolation",
    "WavematGateState",
    "run_failure_injection_matrix",
    "write_raw_results",
]
