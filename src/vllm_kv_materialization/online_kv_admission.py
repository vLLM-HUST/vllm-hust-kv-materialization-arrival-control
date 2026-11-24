"""Two-action admission policy for verified LMCache MP hits."""

import math
import time
from collections import deque

from lmcache.integration.vllm.lmcache_mp_connector import LMCacheMPConnector


class OnlineAdmissionMixin:
    """Choose external or resident-only reuse after the connector verifies a hit."""

    def __init__(self, vllm_config, role, kv_cache_config=None):
        super().__init__(vllm_config, role, kv_cache_config)
        config = vllm_config.kv_transfer_config.kv_connector_extra_config
        self.default_policy = config.get("admission_policy", "full")
        self.minimum_external = int(config.get("minimum_external_tokens", 2048))
        self.pending_reads = {}
        self.prefills = deque()
        self.ms_per_read_token = 0.010

    def update_state_after_alloc(self, request, blocks, num_external_tokens):
        super().update_state_after_alloc(request, blocks, num_external_tokens)
        if num_external_tokens:
            self.pending_reads[request.request_id] = (time.monotonic(), num_external_tokens)

    def update_connector_output(self, output):
        super().update_connector_output(output)
        for rid in output.finished_recving or ():
            sample = self.pending_reads.pop(rid, None)
            if sample:
                start, tokens = sample
                rate = (time.monotonic() - start) * 1000 / tokens
                self.ms_per_read_token = 0.75 * self.ms_per_read_token + 0.25 * rate

    def request_finished(self, request, block_ids):
        self.pending_reads.pop(request.request_id, None)
        return super().request_finished(request, block_ids)

    def build_connector_meta(self, output):
        now = time.monotonic()
        while self.prefills and now - self.prefills[0][0] > 0.45:
            self.prefills.popleft()
        for rid, n in output.num_scheduled_tokens.items():
            if n > 1:
                self.prefills.append((now, rid, n))
        return super().build_connector_meta(output)

    def _admission_options(self, request):
        return self.default_policy, self.minimum_external

    def _record_admission(self, **fields):
        pass

    def select_verified_hit(self, request, local, external, budget, maximum, running):
        policy, minimum = self._admission_options(request)
        if not local:
            return True
        pending = sum(tokens for _, tokens in self.pending_reads.values())
        ready = self.ms_per_read_token * (external + pending)
        residual = max(0, request.num_prompt_tokens - local - external)
        now = time.monotonic()
        active = {r.request_id for r in running}
        competing = min(maximum, sum(
            tokens for stamp, rid, tokens in self.prefills
            if rid in active and now - stamp <= 0.45
        ))
        next_budget = max(1, maximum - competing)

        def rounds(tokens, first_budget):
            # Account for one constrained batch then resume nominal capacity.
            return 1 + math.ceil(max(0, tokens - first_budget) / maximum)

        local_work = residual + external
        full_rounds = rounds(residual, maximum)
        local_rounds = rounds(local_work, maximum)
        full = ready + 0.05 * residual + 12 * full_rounds
        local_cost = 0.05 * local_work + 12 * local_rounds
        if policy == "online":
            if residual > next_budget:
                full += 0.05 * competing
            full += 12 * (rounds(residual, next_budget) - full_rounds)
            local_cost += 12 * (rounds(local_work, budget) - local_rounds)
        if policy in ("online", "readiness"):
            keep = full <= local_cost
        elif policy == "gate":
            keep = external >= minimum
        elif policy in ("full", "local"):
            keep = policy == "full"
        else:
            raise ValueError(f"Unknown admission policy {policy!r}")
        self._record_admission(
            request=request.request_id, policy=policy, local=local, verified=external,
            used=external if keep else 0, budget=budget, next_budget=next_budget,
            ready_ms=ready, full_cost_ms=full, local_cost_ms=local_cost,
        )
        return keep


class OnlineLMCacheConnector(OnlineAdmissionMixin, LMCacheMPConnector):
    """LMCache MP serving connector with optional two-action admission."""
