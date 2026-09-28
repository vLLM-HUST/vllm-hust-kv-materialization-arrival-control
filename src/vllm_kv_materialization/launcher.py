from __future__ import annotations

import os

from vllm_kv_materialization.plugin import EXTENSION_ID, PLUGIN_NAME


def _merge_plugins(existing: str | None, plugin_name: str) -> str:
    if not existing:
        return plugin_name
    parts = [part.strip() for part in existing.split(",") if part.strip()]
    if plugin_name not in parts:
        parts.append(plugin_name)
    return ",".join(parts)


def main() -> None:
    os.environ["VLLM_PLUGINS"] = _merge_plugins(
        os.getenv("VLLM_PLUGINS"),
        PLUGIN_NAME,
    )
    os.environ["VLLMHUST_EXT_ENABLED_BUNDLES"] = _merge_plugins(
        os.getenv("VLLMHUST_EXT_ENABLED_BUNDLES"),
        EXTENSION_ID,
    )

    from vllm.entrypoints.cli.main import main as vllm_main

    vllm_main()


if __name__ == "__main__":
    main()
