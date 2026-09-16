from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "DECISION_SURFACE_CASE_IDS",
    "DECISION_SURFACE_CASE_ROLES",
    "EXPERIMENT_ARTICLE_CASE_IDS",
    "RUNTIME_BOUNDARY_CASE_IDS",
    "MaterializationDecision",
    "MaterializationPolicy",
    "MaterializationSignals",
    "build_live_workload",
    "recommended_context_window",
    "register_plugin",
]

if TYPE_CHECKING:
    from vllm_kv_materialization.plugin import register_plugin
    from vllm_kv_materialization.policy import (
        MaterializationDecision,
        MaterializationPolicy,
        MaterializationSignals,
    )
    from vllm_kv_materialization.shared_workloads import (
        DECISION_SURFACE_CASE_IDS,
        DECISION_SURFACE_CASE_ROLES,
        EXPERIMENT_ARTICLE_CASE_IDS,
        RUNTIME_BOUNDARY_CASE_IDS,
        build_live_workload,
        recommended_context_window,
    )


def __getattr__(name: str) -> Any:
    """Keep plugin import lightweight while preserving the public API."""

    if name == "register_plugin":
        from vllm_kv_materialization.plugin import register_plugin

        return register_plugin
    if name in {
        "MaterializationDecision",
        "MaterializationPolicy",
        "MaterializationSignals",
    }:
        from vllm_kv_materialization import policy

        return getattr(policy, name)
    if name in {
        "DECISION_SURFACE_CASE_IDS",
        "DECISION_SURFACE_CASE_ROLES",
        "EXPERIMENT_ARTICLE_CASE_IDS",
        "RUNTIME_BOUNDARY_CASE_IDS",
        "build_live_workload",
        "recommended_context_window",
    }:
        from vllm_kv_materialization import shared_workloads

        return getattr(shared_workloads, name)
    raise AttributeError(name)
