from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import replace
from typing import Any

from vllm_kv_materialization.live_control import (
    HEADER_REQUEST_ID,
    LiveObservation,
    RuntimeControlPlan,
    apply_runtime_control,
    bind_request_headers,
    compute_runtime_control,
    get_request_headers,
    merge_runtime_control_extra_args,
    record_observation,
    reset_request_headers,
)

logger = logging.getLogger(__name__)

_RUNTIME_PLANS_ATTR = "_kv_materialization_runtime_plans"
_RUNTIME_PLAN_CURSOR_ATTR = "_kv_materialization_runtime_plan_cursor"
_RUNTIME_OBSERVATIONS: ContextVar[tuple[LiveObservation, ...]] = ContextVar(
    "vllm_kv_materialization_legacy_observations",
    default=(),
)
_RUNTIME_OBSERVATION_CURSOR: ContextVar[int] = ContextVar(
    "vllm_kv_materialization_legacy_observation_cursor",
    default=0,
)


def _store_runtime_plans(
    request: Any,
    plans: list[RuntimeControlPlan],
    observations: list[LiveObservation],
) -> None:
    setattr(request, _RUNTIME_PLANS_ATTR, tuple(plans))
    setattr(request, _RUNTIME_PLAN_CURSOR_ATTR, 0)
    _RUNTIME_OBSERVATIONS.set(tuple(observations))
    _RUNTIME_OBSERVATION_CURSOR.set(0)


def _consume_runtime_plan(request: Any) -> RuntimeControlPlan | None:
    plans = getattr(request, _RUNTIME_PLANS_ATTR, ())
    cursor = getattr(request, _RUNTIME_PLAN_CURSOR_ATTR, 0)
    if not isinstance(plans, tuple) or cursor >= len(plans):
        return None
    setattr(request, _RUNTIME_PLAN_CURSOR_ATTR, cursor + 1)
    return plans[cursor]


def _consume_runtime_observation() -> LiveObservation | None:
    observations = _RUNTIME_OBSERVATIONS.get()
    cursor = _RUNTIME_OBSERVATION_CURSOR.get()
    if cursor >= len(observations):
        return None
    _RUNTIME_OBSERVATION_CURSOR.set(cursor + 1)
    return observations[cursor]


def _attach_runtime_plan_to_sampling_params(
    request: Any,
    original_to_sampling_params: Any,
    max_tokens: int,
    default_sampling_params: dict,
) -> Any:
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


def register_legacy_vllm_023_adapter() -> None:
    """Install the compatibility adapter for the deployed vLLM 0.23 API.

    vLLM-HUST hosts with the public, versioned hook never enter this path. The
    adapter retains support for the Ascend 0.23 runtime used by existing NPU
    deployments while still loading through ``vllm.general_plugins``.
    """

    from vllm import envs as vllm_envs
    from vllm.entrypoints.openai.chat_completion.protocol import (
        ChatCompletionRequest,
    )
    from vllm.entrypoints.openai.chat_completion.serving import OpenAIServingChat
    from vllm.entrypoints.openai.completion.protocol import CompletionRequest
    from vllm.entrypoints.openai.completion.serving import OpenAIServingCompletion
    from vllm.entrypoints.openai.engine.serving import OpenAIServing
    from vllm.renderers.inputs.preprocess import extract_prompt_components

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

    def _prompt_token_count(model_config: Any, prompt: Any) -> int:
        try:
            components = extract_prompt_components(model_config, prompt)
            return len(components.token_ids or [])
        except Exception:
            logger.exception(
                "Failed to extract prompt components for KV materialization control."
            )
            return 0

    async def patched_render_chat(self: Any, request: Any) -> Any:
        result = await original_render_chat(self, request)
        if not isinstance(result, tuple) or len(result) != 2:
            return result

        conversation, engine_prompts = result
        controlled_prompts = []
        runtime_plans = []
        observations = []
        for index, engine_prompt in enumerate(engine_prompts):
            prompt_tokens = _prompt_token_count(self.model_config, engine_prompt)
            output_tokens = int(
                getattr(request, "max_completion_tokens", None)
                or getattr(request, "max_tokens", 0)
                or 0
            )
            request_id = str(
                getattr(request, "request_id", None) or f"chat-{id(request)}-{index}"
            )
            observation, plan = compute_runtime_control(
                request_id, prompt_tokens, output_tokens
            )
            observations.append(observation)
            runtime_plans.append(plan)
            controlled_prompts.append(apply_runtime_control(engine_prompt, plan))
        _store_runtime_plans(request, runtime_plans, observations)
        return conversation, controlled_prompts

    async def patched_render_completion(self: Any, request: Any) -> Any:
        result = await original_render_completion(self, request)
        if not isinstance(result, list):
            return result

        controlled_prompts = []
        runtime_plans = []
        observations = []
        for index, engine_prompt in enumerate(result):
            prompt_tokens = _prompt_token_count(self.model_config, engine_prompt)
            output_tokens = int(getattr(request, "max_tokens", 0) or 0)
            request_id = str(
                getattr(request, "request_id", None)
                or f"completion-{id(request)}-{index}"
            )
            observation, plan = compute_runtime_control(
                request_id, prompt_tokens, output_tokens
            )
            observations.append(observation)
            runtime_plans.append(plan)
            controlled_prompts.append(apply_runtime_control(engine_prompt, plan))
        _store_runtime_plans(request, runtime_plans, observations)
        return controlled_prompts

    def patched_chat_to_sampling_params(
        self: Any, max_tokens: int, default_sampling_params: dict
    ) -> Any:
        return _attach_runtime_plan_to_sampling_params(
            self,
            original_chat_to_sampling_params,
            max_tokens,
            default_sampling_params,
        )

    def patched_completion_to_sampling_params(
        self: Any, max_tokens: int, default_sampling_params: dict
    ) -> Any:
        return _attach_runtime_plan_to_sampling_params(
            self,
            original_completion_to_sampling_params,
            max_tokens,
            default_sampling_params,
        )

    def patched_log_inputs(
        self: Any,
        request_id: str,
        inputs: Any,
        params: Any,
        lora_request: Any,
    ) -> None:
        original_log_inputs(self, request_id, inputs, params, lora_request)
        try:
            observation = _consume_runtime_observation()
            if observation is None:
                return
            if not get_request_headers().get(HEADER_REQUEST_ID):
                observation = replace(observation, request_id=request_id)
            record_observation(observation)
        except Exception:
            logger.exception("Failed to record KV materialization observation.")

    async def patched_chat_create(
        self: Any, request: Any, raw_request: Any = None
    ) -> Any:
        token = bind_request_headers(getattr(raw_request, "headers", None))
        observations_token = _RUNTIME_OBSERVATIONS.set(())
        cursor_token = _RUNTIME_OBSERVATION_CURSOR.set(0)
        try:
            return await original_chat_create(self, request, raw_request)
        finally:
            _RUNTIME_OBSERVATION_CURSOR.reset(cursor_token)
            _RUNTIME_OBSERVATIONS.reset(observations_token)
            reset_request_headers(token)

    async def patched_completion_create(
        self: Any, request: Any, raw_request: Any = None
    ) -> Any:
        token = bind_request_headers(getattr(raw_request, "headers", None))
        observations_token = _RUNTIME_OBSERVATIONS.set(())
        cursor_token = _RUNTIME_OBSERVATION_CURSOR.set(0)
        try:
            return await original_completion_create(self, request, raw_request)
        finally:
            _RUNTIME_OBSERVATION_CURSOR.reset(cursor_token)
            _RUNTIME_OBSERVATIONS.reset(observations_token)
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
    vllm_envs.VLLM_KV_MATERIALIZATION_PLUGIN_MODE = "prefix_cache_runtime_control"
