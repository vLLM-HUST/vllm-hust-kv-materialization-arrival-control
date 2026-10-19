"""Opt-in, source-pinned text/recompute experiment on the school 0.28 host.

This is not the segmented materialization API. Non-recompute decisions fail
closed; no partial-reuse or transfer support is implied by this adapter.
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import uuid
from pathlib import Path

from .live_control import (
    apply_runtime_control,
    bind_request_headers,
    compute_runtime_control,
    record_observation,
    reset_request_headers,
)

HOST_PINS = {
    "chat": "ea1f76074a9587c8054f54d30a6ba748b6a5fc4d90dd82c801504505c1da1f92",
    "request": "da610d5203e72d2d524adc5fb39df11502a23520f2f31d9a44cf13d343f9c25d",
}


def controlled_prompt(prompt, request_id, max_tokens):
    if not isinstance(prompt, dict) or not isinstance(
        prompt.get("prompt_token_ids"), list
    ):
        raise TypeError("School 0.28 adapter requires a text token prompt")
    if prompt.get("multi_modal_data") or prompt.get("multi_modal_inputs"):
        raise ValueError("School 0.28 adapter does not qualify multimodal requests")
    observation, plan = compute_runtime_control(
        request_id, len(prompt["prompt_token_ids"]), max_tokens
    )
    if plan.effective_decision != "recompute":
        raise ValueError("School 0.28 adapter only qualifies request-scoped recompute")
    controlled = apply_runtime_control(prompt, plan)
    if controlled.get("cache_salt") != plan.cache_salt or not plan.cache_salt:
        raise ValueError("Request-scoped cache salt was not applied")
    record_observation(observation)
    return controlled


def register_school_vllm_028_adapter():
    from vllm.entrypoints.openai.chat_completion.serving import OpenAIServingChat
    from vllm.v1.request import Request

    from .plugin import observe_runtime_event

    for name, cls in (("chat", OpenAIServingChat), ("request", Request)):
        digest = hashlib.sha256(Path(inspect.getfile(cls)).read_bytes()).hexdigest()
        if digest != HOST_PINS[name]:
            raise RuntimeError(
                f"School 0.28 {name} source does not match qualified pin"
            )
    if getattr(OpenAIServingChat, "_kvmat_school028", False):
        return
    original_render = OpenAIServingChat.render_chat_request
    original_create = OpenAIServingChat.create_chat_completion
    original_init = Request.__init__

    @functools.wraps(original_render)
    async def render(self, request):
        result = await original_render(self, request)
        if not isinstance(result, tuple) or len(result) != 2:
            return result
        conversation, prompts = result
        max_tokens = request.max_completion_tokens or request.max_tokens or 0
        controlled = [
            controlled_prompt(prompt, f"school028-{uuid.uuid4().hex}", max_tokens)
            for prompt in prompts
        ]
        return conversation, controlled

    @functools.wraps(original_create)
    async def create(self, request, raw_request=None):
        token = bind_request_headers(getattr(raw_request, "headers", None))
        try:
            return await original_create(self, request, raw_request)
        finally:
            reset_request_headers(token)

    @functools.wraps(original_init)
    def initialize(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        salt = self.cache_salt
        if isinstance(salt, str) and salt.startswith("kvmat:recompute:"):
            observe_runtime_event(
                {
                    "event": "school028_request_salt_admitted",
                    "request_id": self.request_id,
                    "cache_salt_sha256": hashlib.sha256(salt.encode()).hexdigest(),
                    "prompt_tokens": len(self.prompt_token_ids or []),
                    "scope": (
                        "salt admission, not cache-hit or avoided-compute measurement"
                    ),
                }
            )

    OpenAIServingChat.render_chat_request = render
    OpenAIServingChat.create_chat_completion = create
    OpenAIServingChat._kvmat_school028 = True
    Request.__init__ = initialize
