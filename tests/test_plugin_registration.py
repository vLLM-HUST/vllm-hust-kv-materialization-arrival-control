from __future__ import annotations


def test_register_plugin_supports_current_serving_layout() -> None:
    from vllm_kv_materialization import plugin

    plugin._PATCHED = False
    plugin.register_plugin()

    assert plugin._PATCHED is True
