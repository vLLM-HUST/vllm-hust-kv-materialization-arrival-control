import json
from pathlib import Path

from vllm_kv_materialization import plugin


def test_school_bundle_requires_explicit_flag(monkeypatch):
    monkeypatch.setenv("VLLMHUST_EXT_ENABLED_BUNDLES", plugin.SCHOOL_EXTENSION_ID)
    monkeypatch.delenv("VLLM_KV_ENABLE_SCHOOL_028", raising=False)
    assert not plugin._activation_requested()
    monkeypatch.setenv("VLLM_KV_ENABLE_SCHOOL_028", "1")
    assert plugin._activation_requested()


def test_unrelated_manager_bundle_cannot_activate_school(monkeypatch):
    monkeypatch.setenv("VLLMHUST_EXT_ENABLED_BUNDLES", "org.example.other")
    monkeypatch.setenv("VLLM_KV_ENABLE_SCHOOL_028", "1")
    monkeypatch.setenv("VLLM_PLUGINS", "kv_materialization")
    assert not plugin._activation_requested()


def test_school_bundle_does_not_broaden_native_manifest():
    root = Path(plugin.__file__).parent
    native = json.loads((root / "vllm-hust-extension-v0.3.json").read_text())
    school = json.loads((root / "school_bundle/vllm-hust-extension-v0.3.json").read_text())
    assert native["host"]["version_range"] == ">=0.31,<0.32"
    assert school["host"]["version_range"] == "==0.28.1.post1.dev143"
    assert school["extension_id"] == plugin.SCHOOL_EXTENSION_ID
    assert school["activation"]["environment"]["VLLM_KV_ENABLE_SCHOOL_028"] == "1"
