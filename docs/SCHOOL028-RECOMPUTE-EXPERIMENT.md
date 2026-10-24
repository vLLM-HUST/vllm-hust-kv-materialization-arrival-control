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

## Measured MMLU-Pro screen

[Complete unchanged historical narrative](https://github.com/vLLM-HUST/vllm-hust-benchmark/blob/86d99669ef6e57c1144b2206d7ee9911e480a4e0/archive/mod-targeted-20261023/kv-school-document/snapshot/docs/SCHOOL028-RECOMPUTE-EXPERIMENT.md) preserves the source
identity, compatibility correction and observed request/salt counts.

- [Raw requests, policy/engine receipts and environment archive](https://raw.githubusercontent.com/vLLM-HUST/vllm-hust-benchmark/b354f203cabb4cfeba72a74e4eefb29dee85776b/reports/vllm-hust-midterm-20261019/b1-kvmat-screen-evidence.tar.gz)
- [Canonical screen summary JSON](https://raw.githubusercontent.com/vLLM-HUST/vllm-hust-benchmark/b354f203cabb4cfeba72a74e4eefb29dee85776b/reports/vllm-hust-midterm-20261019/b1-kvmat-screen.json)

This was a school-host recompute-only candidate screen, not the fixed
vLLM 0.18 / Ascend 0.18 B0. The canonical record is **not selected as B1** and
**quality was not rescored**. Request salt admission is not evidence of partial
reuse, avoided computation, task accuracy or statistical significance.
The native Manager manifest's compatibility restriction and bounded opt-in
adapter remain distinct. Do not rewrite historical labels or promote this screen
to a qualified current best configuration.

`BENCHMARK_DOCUMENTS.json` pins the original narrative and both existing raw
inputs by immutable commit, length and SHA256. CI downloads and verifies them;
it does not execute archived code or rerun inference. See [custody](../EVIDENCE.md).
