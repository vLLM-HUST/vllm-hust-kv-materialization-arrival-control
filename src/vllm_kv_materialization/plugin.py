from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PATCHED = False


def register_plugin() -> None:
    """Register the plugin.

    The current patch surface is intentionally minimal. It only marks plugin
    availability so offline and future in-process experiments can verify that
    the plugin was loaded correctly.
    """

    global _PATCHED
    if _PATCHED:
        return

    try:
        from vllm import envs as vllm_envs
    except Exception:
        logger.exception("Failed to import vLLM during plugin registration.")
        return

    setattr(vllm_envs, "VLLM_KV_MATERIALIZATION_PLUGIN_LOADED", True)

    _PATCHED = True
    logger.info("Registered vLLM KV materialization plugin.")