"""Experiment-only counters and policy overrides for the normal serving selector."""
from vllm_kv_materialization.online_kv_admission import OnlineAdmissionMixin
from kv41_boundary_connector import KV41LMCacheConnector as InstrumentedConnector, audit

class KV41LMCacheConnector(OnlineAdmissionMixin, InstrumentedConnector):
    def _admission_options(self, request):
        policy, minimum = super()._admission_options(request)
        options = request.kv_transfer_params or {}
        return (options.get("lmcache.kv41_policy", policy),
                options.get("lmcache.kv41_min_external", minimum))

    def _record_admission(self, **fields):
        audit("admission", **fields)
