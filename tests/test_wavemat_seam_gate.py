from __future__ import annotations

import unittest
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT / "src" / "vllm_kv_materialization" / "wavemat_seam_gate.py"
)


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("wavemat_seam_gate", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


_gate = _load_gate_module()
VIOLATION_ABA = _gate.VIOLATION_ABA
VIOLATION_DIGEST_MISMATCH = _gate.VIOLATION_DIGEST_MISMATCH
VIOLATION_DUPLICATE = _gate.VIOLATION_DUPLICATE
VIOLATION_LOAD_FAILURE = _gate.VIOLATION_LOAD_FAILURE
VIOLATION_ORPHAN_AFTER_RECOVERY = _gate.VIOLATION_ORPHAN_AFTER_RECOVERY
VIOLATION_PARTIAL = _gate.VIOLATION_PARTIAL
VIOLATION_REUSE_BEFORE_ACK = _gate.VIOLATION_REUSE_BEFORE_ACK
VIOLATION_STALE = _gate.VIOLATION_STALE
LayerGroupRef = _gate.LayerGroupRef
SeamGateViolation = _gate.SeamGateViolation
WavematGateState = _gate.WavematGateState
run_failure_injection_matrix = _gate.run_failure_injection_matrix


def make_ref(generation: int = 1) -> LayerGroupRef:
    return LayerGroupRef(
        request_id="req-1",
        cache_id="cache-1",
        layer_start=0,
        layer_end=4,
        generation=generation,
    )


class WavematGateStateTests(unittest.TestCase):
    def test_partial_consume_is_rejected(self) -> None:
        state = WavematGateState()
        ref = make_ref()
        state.register(ref, "digest-a", "event-a")
        with self.assertRaises(SeamGateViolation) as ctx:
            state.consume(ref, "digest-a")
        self.assertEqual(ctx.exception.code, VIOLATION_PARTIAL)

    def test_stale_generation_is_rejected(self) -> None:
        state = WavematGateState()
        state.register(make_ref(generation=2), "digest-a", "event-a")
        with self.assertRaises(SeamGateViolation) as ctx:
            state.consume(make_ref(generation=1), "digest-a")
        self.assertEqual(ctx.exception.code, VIOLATION_STALE)

    def test_duplicate_consume_is_rejected(self) -> None:
        state = WavematGateState()
        ref = make_ref()
        state.register(ref, "digest-a", "event-a")
        state.mark_ready(ref, "digest-a", "event-a")
        state.consume(ref, "digest-a")
        with self.assertRaises(SeamGateViolation) as ctx:
            state.consume(ref, "digest-a")
        self.assertEqual(ctx.exception.code, VIOLATION_DUPLICATE)

    def test_aba_generation_reuse_is_rejected(self) -> None:
        state = WavematGateState()
        ref = make_ref(generation=1)
        state.register(ref, "digest-a", "event-a")
        state.mark_ready(ref, "digest-a", "event-a")
        state.consume(ref, "digest-a")
        state.ack(ref, "digest-a")
        with self.assertRaises(SeamGateViolation) as ctx:
            state.register(ref, "digest-a", "event-a")
        self.assertEqual(ctx.exception.code, VIOLATION_ABA)

    def test_load_failure_is_rejected(self) -> None:
        state = WavematGateState()
        ref = make_ref()
        state.register(ref, "digest-a", "event-a")
        state.mark_load_failure(ref)
        with self.assertRaises(SeamGateViolation) as ctx:
            state.consume(ref, "digest-a")
        self.assertEqual(ctx.exception.code, VIOLATION_LOAD_FAILURE)

    def test_digest_mismatch_is_rejected(self) -> None:
        state = WavematGateState()
        ref = make_ref()
        state.register(ref, "digest-a", "event-a")
        state.mark_ready(ref, "digest-a", "event-a")
        with self.assertRaises(SeamGateViolation) as ctx:
            state.consume(ref, "digest-b")
        self.assertEqual(ctx.exception.code, VIOLATION_DIGEST_MISMATCH)

    def test_reuse_before_ack_is_rejected(self) -> None:
        state = WavematGateState()
        ref = make_ref(generation=1)
        state.register(ref, "digest-a", "event-a")
        with self.assertRaises(SeamGateViolation) as ctx:
            state.register(make_ref(generation=2), "digest-a", "event-a")
        self.assertEqual(ctx.exception.code, VIOLATION_REUSE_BEFORE_ACK)

    def test_recovery_detects_orphans(self) -> None:
        state = WavematGateState()
        ref = make_ref()
        state.register(ref, "digest-a", "event-a")
        state.mark_ready(ref, "digest-a", "event-a")
        state.consume(ref, "digest-a")
        orphans = state.recover()
        self.assertEqual(len(orphans), 1)
        self.assertTrue(
            any(
                item["code"] == VIOLATION_ORPHAN_AFTER_RECOVERY
                for item in state.rejections
            )
        )


class WavematFailureMatrixTests(unittest.TestCase):
    def test_all_failure_injection_cases_pass(self) -> None:
        results = run_failure_injection_matrix()
        self.assertEqual(
            {item["case"] for item in results},
            {
                "partial",
                "stale",
                "duplicate",
                "aba",
                "load_failure",
                "digest_mismatch",
                "reuse_before_ack",
                "crash_recovery_orphan_detection",
            },
        )
        self.assertTrue(all(item["pass"] for item in results))


if __name__ == "__main__":
    unittest.main()
