from __future__ import annotations

import pytest
from vllm.plugins import request_processing
from vllm.plugins.request_processing import (
    RequestProcessingContext,
    apply_request_processors,
)
from vllm.v1.core import kv_materialization

from vllm_kv_materialization import plugin
from vllm_kv_materialization.live_control import RUNTIME_KV_TRANSFER_CONTROL_KEY


def test_plugin_uses_pinned_host_request_processing_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(request_processing, "_request_processors", {})
    monkeypatch.setattr(kv_materialization, "_runtime_observers", {})
    monkeypatch.setattr(plugin, "_REGISTERED", False)
    monkeypatch.setenv("VLLMHUST_EXT_ENABLED_BUNDLES", plugin.EXTENSION_ID)
    monkeypatch.setenv("VLLM_KV_POLICY_MODE", "always_recompute")
    plugin.register_plugin()

    extra_args = apply_request_processors(
        RequestProcessingContext(
            endpoint="chat",
            request_id="contract-request-1",
            prompt_tokens=128,
            max_tokens=16,
            headers={"x-kv-primary-anchor-id": "contract-anchor-1"},
        ),
        {"caller-owned": True},
    )

    assert extra_args is not None
    assert extra_args["caller-owned"] is True
    assert extra_args[RUNTIME_KV_TRANSFER_CONTROL_KEY]["effective_decision"] == (
        "recompute"
    )
