from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_pinned_host_contract(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    relative_path: str,
) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "vendor" / "vllm" / relative_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


from vllm_kv_materialization import plugin
from vllm_kv_materialization.live_control import RUNTIME_KV_TRANSFER_CONTROL_KEY


@pytest.fixture
def pinned_host_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModuleType, ModuleType]:
    for package_name in ("vllm", "vllm.plugins", "vllm.v1", "vllm.v1.core"):
        package = ModuleType(package_name)
        package.__path__ = []
        monkeypatch.setitem(sys.modules, package_name, package)

    host_logger = ModuleType("vllm.logger")
    host_logger.init_logger = logging.getLogger
    monkeypatch.setitem(sys.modules, "vllm.logger", host_logger)

    request_processing = _load_pinned_host_contract(
        monkeypatch,
        "vllm.plugins.request_processing",
        "vllm/plugins/request_processing.py",
    )
    kv_materialization = _load_pinned_host_contract(
        monkeypatch,
        "vllm.v1.core.kv_materialization",
        "vllm/v1/core/kv_materialization.py",
    )
    return request_processing, kv_materialization


def test_plugin_uses_pinned_host_request_processing_contract(
    monkeypatch: pytest.MonkeyPatch,
    pinned_host_contract: tuple[ModuleType, ModuleType],
) -> None:
    request_processing, kv_materialization = pinned_host_contract
    monkeypatch.setattr(request_processing, "_request_processors", {})
    monkeypatch.setattr(kv_materialization, "_runtime_observers", {})
    monkeypatch.setattr(plugin, "_REGISTERED", False)
    monkeypatch.setenv("VLLMHUST_EXT_ENABLED_BUNDLES", plugin.EXTENSION_ID)
    monkeypatch.setenv("VLLM_KV_POLICY_MODE", "always_recompute")
    plugin.register_plugin()

    extra_args = request_processing.apply_request_processors(
        request_processing.RequestProcessingContext(
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
