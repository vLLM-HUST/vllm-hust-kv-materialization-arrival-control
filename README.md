# KV Materialization Arrival Control

This repository studies the request-arrival decision among full reuse,
block-aligned partial reuse, and recomputation. It is distinct from
`intellistream/kv-materialization-scheduling`, which studies cross-request
resource coordination and scheduling.

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
  prefix-cache path; the current carrier seam now isolates the recomputed tail
  in a request-scoped segmented hash namespace, but exact token-level
  materialization is still not available

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
- carrier-side segmented hashing now also resets the tail hash chain at the
  aligned reuse boundary under a request-scoped `segmented_tail_cache_salt`,
  so the recomputed suffix no longer inherits the shared prefix hash chain
- a true connector-backed KV transfer/materialization path still requires an
  explicit global `kv_transfer_config`; request-local control metadata alone
  does not create a `KVConnector`
- carrier-side runtime changes must live under
  [carrier/vllm-hust](/workspace/kv-materialization-arrival-control/carrier/vllm-hust)
  rather than the shared workspace checkout; the current carrier copy already
  contains the current segmented runtime seam: aligned prefix-cache lookup,
  aligned cache-write capping, and request-scoped tail hash isolation derived
  from `target_reuse_tokens`

The live paper matrix now has four cells for the two representative workloads:
old seam + baseline knobs, old seam + tuned knobs, new segmented seam +
baseline knobs, and new segmented seam + tuned knobs.

- `shared_scenario_multi_turn_knowledge_service`
  old baseline: mean `3289.302 ms`, p95 `3641.928 ms`, throughput `1.209 rps`
  old tuned: mean `3860.692 ms`, p95 `4170.369 ms`, throughput `1.031 rps`
  new segmented baseline: mean `3054.712 ms`, p95 `3383.972 ms`, throughput `1.303 rps`
  new segmented tuned: mean `2980.648 ms`, p95 `3214.822 ms`, throughput `1.335 rps`
- `shared_tool_scaffold_agent`
  old baseline: mean `8856.437 ms`, p95 `10627.872 ms`, throughput `0.896 rps`
  old tuned: mean `11068.224 ms`, p95 `12187.492 ms`, throughput `0.717 rps`
  new segmented baseline: mean `9362.399 ms`, p95 `10302.383 ms`, throughput `0.848 rps`
  new segmented tuned: mean `9186.471 ms`, p95 `10182.569 ms`, throughput `0.865 rps`

This matrix supports a narrower and more honest paper claim:

- the stronger segmented carrier seam is what makes the tuned `partial_reuse`
  path competitive again on both workloads
- the segmented seam alone is not a universal win under conservative baseline
  knobs: knowledge-service improves over the old baseline, but tool-scaffold is
  still mixed and does not beat the old-baseline mean/throughput point
- runtime realization and guardrails interact: under the new segmented baseline
  run, knowledge-service split into `8` effective `recompute` requests and `24`
  effective `partial_reuse` requests, while tool-scaffold observed
  `partial_reuse` on all `64` requests but realized `48` effective
  `partial_reuse` requests and `16` effective `full_reuse` requests after
  block-aligned re-ranking

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

- current student owner: `cao zhe`
- current organization: `intellistream`
- status: handed off to `cao zhe` and transferred to `intellistream`
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
[carrier/vllm-hust](/workspace/kv-materialization-arrival-control/carrier/vllm-hust)
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

## Generic dev-hub Validation

Use this pattern to validate this plugin through the host-managed vLLM-HUST dev-hub launcher. Keep dev-hub generic: do not hardcode this repository name, plugin name, port, NPU IDs, or experiment container in dev-hub itself.

Before launch:

- confirm this repository is visible inside the container, usually under `/workspace/<repo-name>`;
- check NPU occupancy with `npu-smi info`;
- choose a unique experiment container name, systemd unit name, and free port;
- use a real API key already configured for the manager, but never print or record it;
- do not share the active twin container.

Generic launch template:

```bash
export DEV_HUB_ROOT=${DEV_HUB_ROOT:-/home/shuhao/vllm-hust-dev-hub}

export VLLM_ENGINE_CONTAINER=<unique-experiment-container>
export VLLM_ENGINE_IMAGE=<known-good-vllm-ascend-image>
export VLLM_ENGINE_AUTO_CREATE_CONTAINER=true
export VLLM_ENGINE_MODEL_PATH=<model-path>
export VLLM_ENGINE_SERVED_MODEL_NAME=<served-model-name>
export VLLM_ENGINE_CONDA_ENV=<conda-env>
export VLLM_ENGINE_PORT=<free-port>
export VLLM_ENGINE_TP_SIZE=<tp-size>
export VLLM_ENGINE_NPU_DEVICES=<dedicated-npu-ids>
export VLLM_ENGINE_SYSTEMD_UNIT=<unique-unit-name>.service
export VLLM_ENGINE_COMPILATION_CONFIG='<optional-json-compilation-config>'

export VLLM_PLUGINS=<plugin-name-or-comma-list>
export VLLM_ENGINE_PYTHONPATH=/workspace/<repo-name>/src:/workspace/<repo-name>:/workspace/vllm-hust:/workspace/vllm-ascend-hust

"$DEV_HUB_ROOT/manage.sh" restart
"$DEV_HUB_ROOT/manage.sh" status --json
```

Run A/B with only plugin-owned environment variables changed between baseline and experiment. Record command shape, devices, model, graph config, prompt, max tokens, output length, TTFT, TPOT, throughput, result paths, confirmed facts, hypotheses, rejected directions, and the next experiment. If startup fails, stop through the same manager and record the failure; do not switch to manual Docker startup.
