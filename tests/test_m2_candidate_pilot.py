from paper.kv_materialization_control.experiments.aggregate_m2_candidate_pilot import (
    passes_promotion_gate,
)
from paper.kv_materialization_control.experiments.run_m2_candidate_pilot import (
    CANDIDATES,
    POLICIES,
    build_schedule,
)
from paper.kv_materialization_control.experiments.validate_online_bundle import (
    M2_PILOT_LABEL,
)


def test_candidate_pilot_schedule_is_complete_and_independent() -> None:
    schedule = build_schedule()

    assert len(schedule) == len(CANDIDATES) * len(POLICIES)
    assert {(spec.workload, spec.policy_mode) for spec in schedule} == {
        (candidate[0], policy) for candidate in CANDIDATES for policy in POLICIES
    }
    assert M2_PILOT_LABEL == "real-online/m2-candidate-pilot"


def test_candidate_pilot_promotion_gate_is_fail_closed() -> None:
    assert passes_promotion_gate(2.0, 5.0, -5.0)
    assert not passes_promotion_gate(2.01, 0.0, 0.0)
    assert not passes_promotion_gate(0.0, 5.01, 0.0)
    assert not passes_promotion_gate(0.0, 0.0, -5.01)
