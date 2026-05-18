# vLLM KV Materialization Plugin

This repository studies one narrow control point in vLLM serving: arrival-time
KV materialization decisions.

For an incoming request with reusable prefix or KV state already available, the
controller chooses exactly one action:

- `full_reuse`
- `partial_reuse`
- `recompute`

Everything in this repository should stay subordinate to that question. This is
not a general admission-control repository, not an online memory-evolution
repository, and not a generic state-management repository.

## Reference Paper

- Short label: `LEAP / SIGMOD 2024`
- Full paper: `Predictive and Near-Optimal Sampling for View Materialization in Video Databases`

Chinese guidance for student follow-up:

- 学这篇的地方：把 materialization 写成一个有成本约束的 selective decision problem，强调“现在值不值得物化”而不是泛化成所有状态管理都归这个仓库。
- 不要直接照搬的地方：LEAP 面向视频数据库 view materialization；当前仓库面向 arrival-time KV materialization，动作集合是 `full_reuse / partial_reuse / recompute`。
- 写作时更适合继承的是：选择性物化的决策逻辑、收益与代价的平衡表达、以及“部分物化当前为什么还只停在 boundary”这种边界诚实写法。

## Scope

This artifact studies:

- whether reusable state should be fully materialized, partially materialized,
  or ignored at request arrival
- how that three-action decision surface behaves across shared workload
  families with different overlap geometry and startup-latency pressure
- how much of that decision surface is currently realizable through the current
  out-of-tree vLLM runtime seam

This artifact does not study:

- general admission or queue-gating policy
- online memory evolution, writeback, or long-horizon state lifecycle control
- a broad scheduler or placement redesign

## Truthfulness Boundary

This repository keeps two evidence layers separate.

- `decision-study`: offline, workload-grounded analysis of the three-action
  arrival-time decision surface
- `runtime-boundary-live`: live execution against a vLLM-compatible endpoint to
  show what the current runtime seam can and cannot realize online

The offline study supports claims about decision structure, sensitivity, and
workload coverage. It does not imply deployed runtime gains.

The live path is truthfulness-safe only when described as a runtime realization
boundary:

- `full_reuse` is realized through anchor-scoped prefix-cache reuse
- `recompute` is realized through request-scoped prefix-cache bypass
- `partial_reuse` is realized only at hash-block granularity on the current
  prefix-cache path; exact token-level segmented materialization is still not
  available

## Partial Reuse Boundary

`partial_reuse` is the key action for this artifact, so its boundary stays
explicit.

Offline meaning:

- choose a profitable cut point, reuse the high-confidence prefix segment, and
  recompute the remaining suffix
- recompute the remaining suffix
- compare that hybrid action against `full_reuse` and `recompute`

Current offline evaluator semantics:

- `partial_reuse` is no longer modeled as a fixed half-prefix proxy
- the evaluator estimates a confidence-aware reuse frontier and discounts the
  value of low-confidence tail tokens
- the policy and oracle both optimize the partial cut point against that same
  cost model, so `partial_reuse` now means "reuse up to the best boundary" and
  not simply "reuse some arbitrary fraction"

Current live-path taxonomy:

- observed decision: `partial_reuse`
- runtime support tier:
  `native_runtime_action` for block-aligned partial reuse, otherwise
  `fallback_to_supported_runtime_action`
- fallback reason taxonomy:
  `partial_reuse_cut_point_realigned_to_runtime_hash_blocks` when the offline
  cut point is rounded down to a realizable full-block boundary,
  `block_aligned_partial_reuse_dominated_by_full_reuse` when that realizable
  boundary is no longer better than `full_reuse`, and
  `block_aligned_partial_reuse_collapses_to_recompute` when it is no longer
  better than `recompute`
- effective live action: block-aligned `partial_reuse`, anchor-scoped
  `full_reuse`, or request-scoped `recompute`, depending on the best
  realizable runtime action after block alignment
- the live control seam preserves the offline cut point inside a dedicated
  materialization-control `extra_args` payload, then aligns it to the runtime
  hash-block boundary before the carrier runtime applies the corresponding
  prefix-cache policy
- on the current carrier seam, effective `partial_reuse` now caps both
  prefix-cache lookup and shared-cache commit at the aligned reuse boundary,
  so the recomputed tail is executed for the current request but is not
  materialized back into the shared prefix-cache namespace
- a true connector-backed KV transfer/materialization path still requires an
  explicit global `kv_transfer_config`; request-local control metadata alone
  does not create a `KVConnector`
- carrier-side runtime changes must live under
  [carrier/vllm-hust](/workspace/vllm-kv-materialization-plugin/carrier/vllm-hust)
  rather than the shared workspace checkout; the current carrier copy already
  contains a segmented-prefix hook that caps prefix-cache lookup at the allowed
  full-block prefix derived from `target_reuse_tokens`

That fallback is a real limitation of the current runtime path and should be
described as such, not widened into a generic “state-management” claim.

## Workload Source Of Truth

All workload-driven paths must enter through `llm-serving-workloads`. This
repository should not grow a second local workload catalog or a repo-local
default case subset.

The default arrival-time decision matrix now follows the shared benchmark case
order exported by the sibling workload repository. In other words, this
repository's default decision-study workload set is whatever
`llm-serving-workloads` currently exposes as its default shared benchmark case
catalog, rather than a second hardcoded list carried locally.

## Canonical Paths

Preferred bootstrap:

```bash
make bootstrap-env
```

Canonical repository-local entrypoints:

```bash
make decision-study
make runtime-boundary-live MODEL=/path/to/shared-models/Qwen2.5-7B-Instruct \
  WORKLOAD_CASE=shared_prefix_multi_tenant_assistant
make pdf
```

Compatibility aliases remain available:

- `make study-experiment`
- `make experiment`
- `make shared-workloads-offline`
- `make live-benchmark`
- `make shared-workloads-live`
- `make optimization-live`

Preferred workload-entry wrapper from `llm-serving-workloads`:

```bash
cd /path/to/llm-serving-workloads
make kv-materialization-study
make kv-materialization-live \
  BASE_URL=https://<openai-compatible-endpoint>/v1 \
  OPENAI_API_KEY=<token> \
  MODEL=/path/to/shared-models/Qwen2.5-7B-Instruct \
  WORKLOAD_CASE=shared_prefix_multi_tenant_assistant
```

## Ownership And Transfer

- target owners: `caozhe`, `xuheng li`
- target organization: `Qixin-Gaoke`
- transfer readiness: keep repository docs and scripts free of user-specific
  absolute paths and source-organization hardcoding

For graduate-student takeover and paper-oriented follow-up, start from
`HANDOFF.md`.

## Common Commands

```bash
make help
make install-dev
make smoke
make test
make shared-workloads-smoke
make shared-workloads-test
make offline-experiment
make decision-study
make runtime-boundary-live MODEL=/path/to/shared-models/Qwen2.5-7B-Instruct
make pdf
make build
```

`shared-workloads-smoke` writes the standardized compatibility report under
`.benchmarks/results`.

## Usage

Run vLLM with the plugin enabled through the wrapper launcher:

```bash
vllm-kv-materialization-serve serve --model <model>
```

Run the toy policy harness:

```bash
vllm-kv-materialization-offline --policy heuristic
```

When launching a local vLLM server through
`paper/kv_materialization_control/experiments/launch_vllm_kv_materialization_server.sh`,
leave `MAX_MODEL_LEN` unset if you want the launcher to derive the serving
window from `llm-serving-workloads` via `WORKLOAD_CASE`.

That launcher now defaults to the repo-local
[carrier/vllm-hust](/workspace/vllm-kv-materialization-plugin/carrier/vllm-hust)
runtime path, auto-detects a usable conda bootstrap and environment, and uses
writable temporary cache roots for live runs. Override `CONDA_SH`, `ENV_NAME`,
`VLLM_KV_MATERIALIZATION_XDG_CACHE_HOME`, or
`VLLM_KV_MATERIALIZATION_HF_HOME` when you need a different local setup.

For OpenAI-compatible endpoints, `BASE_URL` may be either the server root or a
path that already ends with `/v1`. The live driver normalizes both forms and
forwards `OPENAI_API_KEY` plus `OPENAI_HTTP_USER_AGENT` when present.

## Paper And Experiments

Paper assets live under:

- `paper/kv_materialization_control/`
- `paper/kv_materialization_control/experiments/`
- `paper/related_works/`

The decision-study pipeline emits paper-facing summaries under
`paper/kv_materialization_control/experiments/results/latest/`.

The runtime-boundary live path writes endpoint summaries under
`paper/kv_materialization_control/experiments/results/live/`.

## Repository Boundary

Keep the shared external `reference-repos/vllm` checkout untouched. If an upstream-local delta
becomes unavoidable, carry it inside this repository under `vendor/` or
`patches/`.

This repository exists because vLLM supports out-of-tree plugins through
`vllm.general_plugins`. That seam is the right place to study arrival-time
materialization decisions without turning this repo into an upstream fork.