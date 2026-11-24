"""Benchmark adapter for exact LMCache cutoffs and measured concurrent H2D traffic."""

import json
import os
from pathlib import Path
import threading
import time

from lmcache.integration.vllm.lmcache_mp_connector import LMCacheMPConnector
from vllm.distributed.kv_transfer.kv_connector.v1.base import KVConnectorRole

import torch


WORK = Path(os.environ["KV41_CONTENTION_DIR"])
BLOCK = 128
ELIGIBLE = 4096
COPY_SIZE = 4 * 1024 * 1024
COPY_BATCH = 8


def audit(event, **fields):
    with (WORK / f"connector-{os.getpid()}.jsonl").open("a") as f:
        f.write(json.dumps({"event": event, "timestamp_ns": time.time_ns(), **fields}) + "\n")


def copy_traffic(device):
    try:
        torch.npu.set_device(device)
        host = torch.zeros(COPY_SIZE, dtype=torch.int8, device="cpu", pin_memory=True)
        dst = torch.empty_like(host, device=device)
        stream = torch.npu.Stream(device=device)
        control = WORK / "traffic"
        previous = ("", "")
        audit("copy_ready", device=str(device), buffer_bytes=COPY_SIZE)
        while True:
            operation = (control.read_text().strip().split() if control.exists() else ["none", "idle"])
            tag, mode = operation
            if (tag, mode) != previous:
                audit("copy_ack", device=str(device), tag=tag, mode=mode)
                previous = (tag, mode)
            if mode in ("medium", "high"):
                begin_ns = time.time_ns()
                with torch.npu.stream(stream):
                    for _ in range(COPY_BATCH):
                        dst.copy_(host, non_blocking=True)
                stream.synchronize()
                audit("copy_batch", device=str(device), tag=tag, begin_ns=begin_ns,
                      end_ns=time.time_ns(), bytes=COPY_BATCH*COPY_SIZE)
                if mode == "medium":
                    time.sleep(0.003)
            else:
                time.sleep(0.003)
    except Exception as error:
        audit("copy_error", device=str(device), error=repr(error))
        raise


class KV41LMCacheConnector(LMCacheMPConnector):
    def __init__(self, vllm_config, role, kv_cache_config=None):
        super().__init__(vllm_config, role, kv_cache_config)
        if role == KVConnectorRole.SCHEDULER:
            submit = self.scheduler_adapter.maybe_submit_lookup_request

            def capped_submit(request_id, token_ids, cache_salt="", request_configs=None,
                              reserve_last_token=False):
                config = dict(request_configs or {})
                cap = config.pop("lmcache.kv41_lookup_cap", None)
                if cap is not None:
                    assert 0 <= cap <= ELIGIBLE and cap % BLOCK == 0
                    if cap == 0:
                        config["lmcache.skip_load"] = True
                    else:
                        token_ids = token_ids[:cap + int(reserve_last_token)]
                return submit(request_id, token_ids, cache_salt=cache_salt,
                              request_configs=config, reserve_last_token=reserve_last_token)

            self.scheduler_adapter.maybe_submit_lookup_request = capped_submit

    def get_num_new_matched_tokens(self, request, num_computed_tokens):
        params = request.kv_transfer_params or {}
        arm = params.get("lmcache.kv41_arm")
        if arm is not None:
            tracker = self._get_or_create_request_tracker(request)
            config = tracker.request_configs
            if arm == "threshold":
                extra = max(0, ELIGIBLE - num_computed_tokens)
                cap = ELIGIBLE if extra >= config["lmcache.kv41_min_external"] else 0
            else:
                cap = int(arm)
                if cap <= num_computed_tokens:
                    cap = 0
            if cap == 0:
                # Preserve the actual APC match already computed by vLLM. This
                # benchmark gate declines only additional external retrieval.
                align = self._hit_alignment_tokens
                tracker.num_vllm_hit_tokens = num_computed_tokens // align * align
                audit("decision", request=request.request_id, arm=arm,
                      local=num_computed_tokens, external=0, cutoff=0)
                return 0, False
            config["lmcache.kv41_lookup_cap"] = cap
        result = super().get_num_new_matched_tokens(request, num_computed_tokens)
        if arm is not None and result[0] is not None:
            audit("decision", request=request.request_id, arm=arm, local=num_computed_tokens,
                  external=result[0], cutoff=cap)
        return result

    def build_connector_meta(self, output):
        new = {r.req_id: r.num_computed_tokens for r in output.scheduled_new_reqs}
        cached = output.scheduled_cached_reqs
        starts = new | dict(zip(cached.req_ids, cached.num_computed_tokens, strict=True))
        # The connector sees the scheduler output before _update_after_schedule.
        # Count only positions within the prompt, including the final prefill
        # invocation that produces logits. Async loads have no forward tokens.
        batch = []
        for req_id, tokens in output.num_scheduled_tokens.items():
            if not req_id.startswith(("cmpl-kv41-target-", "cmpl-kv41-back-")):
                continue
            tracker = self.request_trackers[req_id]
            start = starts[req_id]
            prefill = min(tokens, max(0, tracker.num_prompt_tokens - start))
            batch.append({"request":req_id,"start":start,"scheduled":tokens,"prefill":prefill})
        if batch:
            audit("forward_batch", total=output.total_num_scheduled_tokens, requests=batch,
                  preempted=list(output.preempted_req_ids or ()))
        return super().build_connector_meta(output)

    def register_kv_caches(self, kv_caches):
        super().register_kv_caches(kv_caches)
        value = next(iter(kv_caches.values()))
        tensor = value if isinstance(value, torch.Tensor) else value[0]
        self._kv41_copy_thread = threading.Thread(target=copy_traffic,
                                                 args=(tensor.device,), daemon=True)
        self._kv41_copy_thread.start()
