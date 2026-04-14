from __future__ import annotations

import logging
import os

from vllm_kv_materialization.live_control import apply_runtime_control
from vllm_kv_materialization.live_control import bind_request_headers
from vllm_kv_materialization.live_control import compute_runtime_control
from vllm_kv_materialization.live_control import observe_request
from vllm_kv_materialization.live_control import reset_request_headers

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
        from vllm.entrypoints.openai.chat_completion.serving import OpenAIServingChat
        from vllm.entrypoints.openai.completion.serving import OpenAIServingCompletion
        from vllm.entrypoints.openai.engine.serving import OpenAIServing
        from vllm.entrypoints.serve.render.serving import OpenAIServingRender
        from vllm.renderers.inputs.preprocess import extract_prompt_components
    except Exception:
        logger.exception("Failed to import vLLM during plugin registration.")
        return

    original_log_inputs = OpenAIServing._log_inputs
    original_chat_create = OpenAIServingChat.create_chat_completion
    original_completion_create = OpenAIServingCompletion.create_completion
    original_render_chat = OpenAIServingRender.render_chat
    original_render_completion = OpenAIServingRender.render_completion

    def _prompt_token_count(model_config, prompt) -> int:
        try:
            components = extract_prompt_components(model_config, prompt)
            return len(components.token_ids or [])
        except Exception:
            logger.exception("Failed to extract prompt components for KV materialization control.")
            return 0

    async def patched_render_chat(self, request):
        result = await original_render_chat(self, request)
        if not isinstance(result, tuple) or len(result) != 2:
            return result

        conversation, engine_prompts = result
        controlled_prompts = []
        for index, engine_prompt in enumerate(engine_prompts):
            prompt_tokens = _prompt_token_count(self.model_config, engine_prompt)
            output_tokens = int(
                getattr(request, "max_completion_tokens", None)
                or getattr(request, "max_tokens", 0)
                or 0
            )
            request_id = str(getattr(request, "request_id", None) or f"chat-{index}")
            _, plan = compute_runtime_control(request_id, prompt_tokens, output_tokens)
            controlled_prompts.append(apply_runtime_control(engine_prompt, plan))
        return conversation, controlled_prompts

    async def patched_render_completion(self, request):
        result = await original_render_completion(self, request)
        if not isinstance(result, list):
            return result

        controlled_prompts = []
        for index, engine_prompt in enumerate(result):
            prompt_tokens = _prompt_token_count(self.model_config, engine_prompt)
            output_tokens = int(getattr(request, "max_tokens", 0) or 0)
            request_id = str(getattr(request, "request_id", None) or f"completion-{index}")
            _, plan = compute_runtime_control(request_id, prompt_tokens, output_tokens)
            controlled_prompts.append(apply_runtime_control(engine_prompt, plan))
        return controlled_prompts

    def patched_log_inputs(self, request_id, inputs, params, lora_request) -> None:
        original_log_inputs(self, request_id, inputs, params, lora_request)
        try:
            prompt_components = self._extract_prompt_components(inputs)
            prompt_tokens = len(prompt_components.token_ids or [])
            output_tokens = int(getattr(params, "max_tokens", 0) or 0)
            observe_request(request_id, prompt_tokens, output_tokens)
        except Exception:
            logger.exception("Failed to record KV materialization observation.")

    async def patched_chat_create(self, request, raw_request=None):
        token = bind_request_headers(getattr(raw_request, "headers", None))
        try:
            return await original_chat_create(self, request, raw_request)
        finally:
            reset_request_headers(token)

    async def patched_completion_create(self, request, raw_request=None):
        token = bind_request_headers(getattr(raw_request, "headers", None))
        try:
            return await original_completion_create(self, request, raw_request)
        finally:
            reset_request_headers(token)

    OpenAIServing._log_inputs = patched_log_inputs
    OpenAIServingChat.create_chat_completion = patched_chat_create
    OpenAIServingCompletion.create_completion = patched_completion_create
    OpenAIServingRender.render_chat = patched_render_chat
    OpenAIServingRender.render_completion = patched_render_completion

    setattr(vllm_envs, "VLLM_KV_MATERIALIZATION_PLUGIN_LOADED", True)
    setattr(
        vllm_envs,
        "VLLM_KV_MATERIALIZATION_PLUGIN_MODE",
        os.getenv("VLLM_KV_MATERIALIZATION_PLUGIN_MODE", "prefix_cache_runtime_control"),
    )

    _PATCHED = True
    logger.info("Registered vLLM KV materialization plugin with prefix-cache runtime control.")