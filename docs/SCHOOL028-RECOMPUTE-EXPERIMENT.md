# School 0.28 bounded recompute experiment

This opt-in adapter is an experimental compatibility path, not support for the
segmented materialization host API. It requires the school build
`0.28.1.post1.dev143+gf18cf803c` and exact SHA256 pins for the chat serving and
engine request modules. Other source revisions fail before hooks are installed.
Default plugin registration and the supported native host remain unchanged.

Enable `kv_materialization` in `VLLM_PLUGINS` and set
`VLLM_KV_ENABLE_SCHOOL_028=1` explicitly. Install the committed plugin with
`--no-deps` into an isolated target; do not replace the serving runtime. Record
the plugin commit, actual import path, host versions, source hashes, policy log
and runtime event log with each experiment.

Only text token prompts and effective `recompute` decisions are accepted. The
existing controller supplies a request-scoped cache salt. Token IDs, decoding
parameters and model weights are unchanged. Non-recompute decisions and
multimodal prompts fail closed. Requests without reuse anchors are not given
synthetic anchors or shared-prefix hints to improve benchmark results.

The `school028_request_salt_admitted` event proves the salt reached the engine
request. It does not prove cache reuse, avoided computation or performance
improvement. This experiment does not exercise partial reuse or transfer.
Same-workload measurements and correctness checks are required before selecting
any result as B1. The adapter alone is not qualification evidence.
