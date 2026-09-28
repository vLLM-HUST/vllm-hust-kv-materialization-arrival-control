from __future__ import annotations

from vllm.plugins import request_processing
from vllm.v1.core import kv_materialization

from vllm_kv_materialization import plugin


def test_register_plugin_supports_current_native_host_contract(monkeypatch) -> None:
    monkeypatch.setattr(request_processing, "_request_processors", {})
    monkeypatch.setattr(kv_materialization, "_runtime_observers", {})
    monkeypatch.setattr(plugin, "_REGISTERED", False)
    monkeypatch.setenv("VLLMHUST_EXT_ENABLED_BUNDLES", plugin.EXTENSION_ID)

    plugin.register_plugin()

    assert plugin._REGISTERED is True
    assert plugin.PLUGIN_NAME in request_processing._request_processors
    assert plugin.PLUGIN_NAME in kv_materialization._runtime_observers
