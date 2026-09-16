from __future__ import annotations

from vllm_kv_materialization.launcher import _merge_plugins
from vllm_kv_materialization.plugin import EXTENSION_ID, PLUGIN_NAME


def test_merge_plugins_when_empty() -> None:
    assert _merge_plugins(None, "kv_materialization") == "kv_materialization"


def test_merge_plugins_appends_once() -> None:
    merged = _merge_plugins("foo,bar", "kv_materialization")
    assert merged == "foo,bar,kv_materialization"
    assert _merge_plugins(merged, "kv_materialization") == merged


def test_merge_plugins_handles_existing_whitespace() -> None:
    merged = _merge_plugins(" foo , kv_materialization ", "kv_materialization")
    assert merged == "foo,kv_materialization"


def test_plugin_and_extension_identifiers_are_stable() -> None:
    assert PLUGIN_NAME == "kv_materialization"
    assert EXTENSION_ID == "org.vllm-hust.kv-materialization-arrival-control"
