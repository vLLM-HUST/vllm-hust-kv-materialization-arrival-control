from paper.kv_materialization_control.experiments.aggregate_m2_candidate_pilot import (
    passes_promotion_gate,
)
from paper.kv_materialization_control.experiments.aggregate_m2_significance_confirmation import (
    one_sided_upper_95,
)
from paper.kv_materialization_control.experiments.run_m2_anchor_confirmation import (
    build_schedule as build_confirmation_schedule,
)
from paper.kv_materialization_control.experiments.run_m2_candidate_pilot import (
    ANCHOR_TOPOLOGY_CANDIDATES,
    CANDIDATES,
    POLICIES,
    STATEFUL_SECONDARY_CANDIDATES,
    build_schedule,
)
from paper.kv_materialization_control.experiments.run_m2_significance_confirmation import (
    build_schedule as build_significance_schedule,
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

    anchor_schedule = build_schedule(ANCHOR_TOPOLOGY_CANDIDATES)
    assert {(spec.workload, spec.policy_mode) for spec in anchor_schedule} == {
        (candidate[0], policy)
        for candidate in ANCHOR_TOPOLOGY_CANDIDATES
        for policy in POLICIES
    }

    stateful_schedule = build_schedule(STATEFUL_SECONDARY_CANDIDATES)
    assert {(spec.workload, spec.policy_mode) for spec in stateful_schedule} == {
        (candidate[0], policy)
        for candidate in STATEFUL_SECONDARY_CANDIDATES
        for policy in POLICIES
    }


def test_candidate_pilot_promotion_gate_is_fail_closed() -> None:
    assert passes_promotion_gate(2.0, 5.0, -5.0)
    assert not passes_promotion_gate(2.01, 0.0, 0.0)
    assert not passes_promotion_gate(0.0, 5.01, 0.0)
    assert not passes_promotion_gate(0.0, 0.0, -5.01)


def test_anchor_confirmation_schedule_has_three_balanced_rounds() -> None:
    schedule = build_confirmation_schedule()
    assert len(schedule) == 9
    assert {(spec.round_index, spec.policy_mode) for spec in schedule} == {
        (round_index, policy) for round_index in (1, 2, 3) for policy in POLICIES
    }


def test_significance_confirmation_has_five_complete_rounds() -> None:
    schedule = build_significance_schedule()
    assert len(schedule) == 15
    assert {(spec.round_index, spec.policy_mode) for spec in schedule} == {
        (round_index, policy) for round_index in range(1, 6) for policy in POLICIES
    }


def test_significance_bound_uses_lifecycle_level_variation() -> None:
    assert one_sided_upper_95([-8.0, -7.0, -6.0, -7.0, -8.0]) < 0.0
    assert one_sided_upper_95([-8.0, -7.0, -6.0, -7.0, 8.0]) > 0.0
