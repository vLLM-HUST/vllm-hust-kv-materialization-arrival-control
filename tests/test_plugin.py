from __future__ import annotations

import json
import os
import sys
from types import ModuleType, SimpleNamespace

import pytest

from vllm_kv_materialization import plugin
from vllm_kv_materialization.live_control import RUNTIME_KV_TRANSFER_CONTROL_KEY


def _install_fake_host(
    monkeypatch: pytest.MonkeyPatch,
    *,
    request_api_version: str = "1.0",
    kv_api_version: str = "1.0",
) -> tuple[list[tuple[str, object, tuple[str, ...]]], list[tuple[str, object]]]:
    request_registrations: list[tuple[str, object, tuple[str, ...]]] = []
    observer_registrations: list[tuple[str, object]] = []
    vllm = ModuleType("vllm")
    plugins = ModuleType("vllm.plugins")
    request_processing = ModuleType("vllm.plugins.request_processing")
    request_processing.REQUEST_PROCESSING_HOOK_API_VERSION = request_api_version

    def register_request_processor(
        name: str,
        processor: object,
        *,
        header_names: tuple[str, ...] = (),
    ) -> None:
        request_registrations.append((name, processor, tuple(header_names)))

    request_processing.register_request_processor = register_request_processor
    v1 = ModuleType("vllm.v1")
    core = ModuleType("vllm.v1.core")
    kv_materialization = ModuleType("vllm.v1.core.kv_materialization")
    kv_materialization.KV_MATERIALIZATION_RUNTIME_CONTROL_API_VERSION = kv_api_version
    kv_materialization.register_kv_materialization_runtime_observer = (
        lambda name, observer: observer_registrations.append((name, observer))
    )
    monkeypatch.setitem(sys.modules, "vllm", vllm)
    monkeypatch.setitem(sys.modules, "vllm.plugins", plugins)
    monkeypatch.setitem(
        sys.modules,
        "vllm.plugins.request_processing",
        request_processing,
    )
    monkeypatch.setitem(sys.modules, "vllm.v1", v1)
    monkeypatch.setitem(sys.modules, "vllm.v1.core", core)
    monkeypatch.setitem(
        sys.modules,
        "vllm.v1.core.kv_materialization",
        kv_materialization,
    )
    return request_registrations, observer_registrations


@pytest.fixture(autouse=True)
def reset_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plugin, "_REGISTERED", False)
    monkeypatch.delenv("VLLMHUST_EXT_ENABLED_BUNDLES", raising=False)
    monkeypatch.delenv("VLLM_PLUGINS", raising=False)
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_PLUGIN_LOADED", raising=False)
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_LOG_PATH", raising=False)
    monkeypatch.delenv("VLLM_KV_MATERIALIZATION_RUNTIME_EVENT_LOG_PATH", raising=False)


def test_process_request_returns_engine_control_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VLLM_KV_POLICY_MODE", "always_recompute")
    context = SimpleNamespace(
        request_id="request-1",
        prompt_tokens=128,
        max_tokens=16,
        headers={"x-kv-primary-anchor-id": "anchor-1"},
    )

    updates = plugin.process_request(context)

    assert updates[RUNTIME_KV_TRANSFER_CONTROL_KEY]["effective_decision"] == (
        "recompute"
    )


def test_process_request_records_client_correlated_observation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    log_path = tmp_path / "observations.jsonl"
    monkeypatch.setenv("VLLM_KV_MATERIALIZATION_LOG_PATH", str(log_path))
    context = SimpleNamespace(
        request_id="engine-request",
        prompt_tokens=128,
        max_tokens=16,
        headers={"x-request-id": "client-request"},
    )

    plugin.process_request(context)

    observation = json.loads(log_path.read_text(encoding="utf-8"))
    assert observation["request_id"] == "client-request"


def test_runtime_observer_persists_host_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    log_path = tmp_path / "runtime-events.jsonl"
    monkeypatch.setenv("VLLM_KV_MATERIALIZATION_RUNTIME_EVENT_LOG_PATH", str(log_path))

    plugin.observe_runtime_event({"event": "lookup", "request_id": "request-1"})

    event = json.loads(log_path.read_text(encoding="utf-8"))
    assert event["event"] == "lookup"
    assert event["request_id"] == "request-1"
    assert isinstance(event["timestamp_s"], float)


def test_register_plugin_uses_public_host_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_registrations, observer_registrations = _install_fake_host(monkeypatch)
    monkeypatch.setenv("VLLMHUST_EXT_ENABLED_BUNDLES", plugin.EXTENSION_ID)

    plugin.register_plugin()

    assert request_registrations == [
        (plugin.PLUGIN_NAME, plugin.process_request, plugin._REQUEST_HEADERS)
    ]
    assert observer_registrations == [
        (plugin.PLUGIN_NAME, plugin.observe_runtime_event)
    ]
    assert plugin._REGISTERED is True


def test_installed_plugin_is_default_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_registrations, observer_registrations = _install_fake_host(monkeypatch)

    plugin.register_plugin()

    assert request_registrations == []
    assert observer_registrations == []
    assert plugin._REGISTERED is False


def test_manager_disabled_plugin_has_no_activation_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_registrations, observer_registrations = _install_fake_host(monkeypatch)
    monkeypatch.setenv(
        "VLLMHUST_EXT_ENABLED_BUNDLES",
        "org.vllm-hust.some-other-extension",
    )

    plugin.register_plugin()

    assert request_registrations == []
    assert observer_registrations == []
    assert plugin._REGISTERED is False


def test_direct_vllm_allowlist_explicitly_activates_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_registrations, _ = _install_fake_host(monkeypatch)
    monkeypatch.setenv("VLLM_PLUGINS", f"other,{plugin.PLUGIN_NAME}")

    plugin.register_plugin()

    assert request_registrations == [
        (plugin.PLUGIN_NAME, plugin.process_request, plugin._REQUEST_HEADERS)
    ]


def test_register_plugin_rejects_unsupported_host_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_host(monkeypatch, request_api_version="2.0")
    monkeypatch.setenv("VLLMHUST_EXT_ENABLED_BUNDLES", plugin.EXTENSION_ID)

    with pytest.raises(RuntimeError, match="Unsupported.*hook API"):
        plugin.register_plugin()


def test_register_plugin_rejects_unsupported_kv_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_host(monkeypatch, kv_api_version="2.0")
    monkeypatch.setenv("VLLMHUST_EXT_ENABLED_BUNDLES", plugin.EXTENSION_ID)

    with pytest.raises(RuntimeError, match="Unsupported.*KV materialization API"):
        plugin.register_plugin()


def test_register_plugin_rejects_host_without_public_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vllm = ModuleType("vllm")
    plugins = ModuleType("vllm.plugins")
    monkeypatch.setitem(sys.modules, "vllm", vllm)
    monkeypatch.setitem(sys.modules, "vllm.plugins", plugins)
    monkeypatch.delitem(sys.modules, "vllm.plugins.request_processing", raising=False)
    monkeypatch.setenv("VLLMHUST_EXT_ENABLED_BUNDLES", plugin.EXTENSION_ID)

    with pytest.raises(RuntimeError, match="installed host is unsupported"):
        plugin.register_plugin()


def test_register_plugin_uses_vllm_023_compatibility_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vllm = ModuleType("vllm")
    vllm.__version__ = "0.23.1.post1.dev572"
    plugins = ModuleType("vllm.plugins")
    registrations: list[str] = []
    legacy = ModuleType("vllm_kv_materialization.legacy_vllm_023")
    legacy.register_legacy_vllm_023_adapter = lambda: registrations.append("legacy")
    monkeypatch.setitem(sys.modules, "vllm", vllm)
    monkeypatch.setitem(sys.modules, "vllm.plugins", plugins)
    monkeypatch.delitem(sys.modules, "vllm.plugins.request_processing", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "vllm_kv_materialization.legacy_vllm_023",
        legacy,
    )
    monkeypatch.setenv("VLLM_PLUGINS", plugin.PLUGIN_NAME)

    plugin.register_plugin()

    assert registrations == ["legacy"]
    assert plugin._REGISTERED is True
    assert os.environ["VLLM_KV_MATERIALIZATION_PLUGIN_LOADED"] == "1"
