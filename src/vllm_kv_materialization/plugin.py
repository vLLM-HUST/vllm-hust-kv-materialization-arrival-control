from __future__ import annotations

import logging
import os
from typing import Any

from vllm_kv_materialization.live_control import (
    RuntimeControlPlan,
    apply_runtime_control,
    bind_request_headers,
    compute_runtime_control,
    merge_runtime_control_extra_args,
    observe_request,
    reset_request_headers,
)

logger = logging.getLogger(__name__)

_PATCHED = False
_RUNTIME_PLANS_ATTR = "_kv_materialization_runtime_plans"
_RUNTIME_PLAN_CURSOR_ATTR = "_kv_materialization_runtime_plan_cursor"


def _store_runtime_plans(request: Any, plans: list[RuntimeControlPlan]) -> None:
    setattr(request, _RUNTIME_PLANS_ATTR, tuple(plans))
    setattr(request, _RUNTIME_PLAN_CURSOR_ATTR, 0)


def _consume_runtime_plan(request: Any) -> RuntimeControlPlan | None:
    plans = getattr(request, _RUNTIME_PLANS_ATTR, ())
    cursor = getattr(request, _RUNTIME_PLAN_CURSOR_ATTR, 0)
    if not isinstance(plans, tuple) or cursor >= len(plans):
        return None
    setattr(request, _RUNTIME_PLAN_CURSOR_ATTR, cursor + 1)
    return plans[cursor]


def _attach_runtime_plan_to_sampling_params(
    request: Any,
    original_to_sampling_params,
    max_tokens: int,
    default_sampling_params: dict,
):
    plan = _consume_runtime_plan(request)
    if plan is None:
        return original_to_sampling_params(request, max_tokens, default_sampling_params)

    previous_vllm_xargs = getattr(request, "vllm_xargs", None)
    try:
        request.vllm_xargs = merge_runtime_control_extra_args(
            previous_vllm_xargs,
            plan,
        )
        return original_to_sampling_params(request, max_tokens, default_sampling_params)
    finally:
        request.vllm_xargs = previous_vllm_xargs


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
        from vllm.entrypoints.openai.chat_completion.protocol import (
            ChatCompletionRequest,
        )
        from vllm.entrypoints.openai.chat_completion.serving import OpenAIServingChat
        from vllm.entrypoints.openai.completion.protocol import CompletionRequest
        from vllm.entrypoints.openai.completion.serving import OpenAIServingCompletion
        from vllm.entrypoints.openai.engine.serving import OpenAIServing
        from vllm.renderers.inputs.preprocess import extract_prompt_components
    except Exception:
        logger.exception("Failed to import vLLM during plugin registration.")
        return

    original_log_inputs = OpenAIServing._log_inputs
    original_chat_create = OpenAIServingChat.create_chat_completion
    original_completion_create = OpenAIServingCompletion.create_completion
    try:
        from vllm.entrypoints.serve.render.serving import OpenAIServingRender
    except ImportError:
        OpenAIServingRender = None

    if OpenAIServingRender is None:
        original_render_chat = OpenAIServingChat.render_chat_request
        original_render_completion = OpenAIServingCompletion.render_completion_request
    else:
        original_render_chat = OpenAIServingRender.render_chat
        original_render_completion = OpenAIServingRender.render_completion
    original_chat_to_sampling_params = ChatCompletionRequest.to_sampling_params
    original_completion_to_sampling_params = CompletionRequest.to_sampling_params

    def _prompt_token_count(model_config, prompt) -> int:
        try:
            components = extract_prompt_components(model_config, prompt)
            return len(components.token_ids or [])
        except Exception:
            logger.exception(
                "Failed to extract prompt components for KV materialization control."
            )
            return 0

    async def patched_render_chat(self, request):
        result = await original_render_chat(self, request)
        if not isinstance(result, tuple) or len(result) != 2:
            return result

        conversation, engine_prompts = result
        controlled_prompts = []
        runtime_plans = []
        for index, engine_prompt in enumerate(engine_prompts):
            prompt_tokens = _prompt_token_count(self.model_config, engine_prompt)
            output_tokens = int(
                getattr(request, "max_completion_tokens", None)
                or getattr(request, "max_tokens", 0)
                or 0
            )
            request_id = str(getattr(request, "request_id", None) or f"chat-{index}")
            _, plan = compute_runtime_control(request_id, prompt_tokens, output_tokens)
            runtime_plans.append(plan)
            controlled_prompts.append(apply_runtime_control(engine_prompt, plan))
        _store_runtime_plans(request, runtime_plans)
        return conversation, controlled_prompts

    async def patched_render_completion(self, request):
        result = await original_render_completion(self, request)
        if not isinstance(result, list):
            return result

        controlled_prompts = []
        runtime_plans = []
        for index, engine_prompt in enumerate(result):
            prompt_tokens = _prompt_token_count(self.model_config, engine_prompt)
            output_tokens = int(getattr(request, "max_tokens", 0) or 0)
            request_id = str(
                getattr(request, "request_id", None) or f"completion-{index}"
            )
            _, plan = compute_runtime_control(request_id, prompt_tokens, output_tokens)
            runtime_plans.append(plan)
            controlled_prompts.append(apply_runtime_control(engine_prompt, plan))
        _store_runtime_plans(request, runtime_plans)
        return controlled_prompts

    def patched_chat_to_sampling_params(self, max_tokens, default_sampling_params):
        return _attach_runtime_plan_to_sampling_params(
            self,
            original_chat_to_sampling_params,
            max_tokens,
            default_sampling_params,
        )

    def patched_completion_to_sampling_params(
        self, max_tokens, default_sampling_params
    ):
        return _attach_runtime_plan_to_sampling_params(
            self,
            original_completion_to_sampling_params,
            max_tokens,
            default_sampling_params,
        )

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
    if OpenAIServingRender is None:
        OpenAIServingChat.render_chat_request = patched_render_chat
        OpenAIServingCompletion.render_completion_request = patched_render_completion
    else:
        OpenAIServingRender.render_chat = patched_render_chat
        OpenAIServingRender.render_completion = patched_render_completion
    ChatCompletionRequest.to_sampling_params = patched_chat_to_sampling_params
    CompletionRequest.to_sampling_params = patched_completion_to_sampling_params

    vllm_envs.VLLM_KV_MATERIALIZATION_PLUGIN_LOADED = True
    vllm_envs.VLLM_KV_MATERIALIZATION_PLUGIN_MODE = os.getenv(
        "VLLM_KV_MATERIALIZATION_PLUGIN_MODE", "prefix_cache_runtime_control"
    )

    _PATCHED = True
    logger.info(
        "Registered vLLM KV materialization plugin with prefix-cache runtime control."
    )
    print(
        "KV_MATERIALIZATION_PLUGIN_REGISTERED mode=prefix_cache_runtime_control",
        flush=True,
    )
