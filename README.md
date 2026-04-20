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
- `partial_reuse` is observed by the policy but currently falls back to
  anchor-scoped `full_reuse` on the unmodified prefix-cache path

## Partial Reuse Boundary

`partial_reuse` is the key action for this artifact, so its boundary stays
explicit.

Offline meaning:

- reuse only a profitable prefix segment
- recompute the remaining suffix
- compare that hybrid action against `full_reuse` and `recompute`

Current live-path taxonomy:

- observed decision: `partial_reuse`
- runtime support tier: `fallback_to_supported_runtime_action`
- fallback reason:
  `exact_partial_segment_materialization_unavailable_on_prefix_cache_path`
- effective live action: anchor-scoped `full_reuse`

That fallback is a real limitation of the current runtime path and should be
described as such, not widened into a generic “state-management” claim.

## Workload Source Of Truth

All workload-driven paths must enter through `llm-serving-workloads`. This
repository should not grow a second local workload catalog.

The default arrival-time decision matrix now covers six shared cases from the
sibling workload repository:

- `shared_scenario_multi_turn_knowledge_service`
- `shared_scenario_rag_followup_long_context`
- `shared_scenario_structured_agent_decode`
- `shared_prefix_multi_tenant_assistant`
- `session_continuation_with_maintenance`
- `dynamic_rag_corpus_update`

Those cases deliberately cover:

- prefix-rich multi-tenant overlap
- long-context continuation under maintenance-style continuity
- dynamic retrieval follow-up under evolving corpus state

## Canonical Paths

Preferred bootstrap:

```bash
make bootstrap-env
```

Canonical repository-local entrypoints:

```bash
make decision-study
make runtime-boundary-live MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
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
cd /home/shuhao/llm-serving-workloads
make kv-materialization-study
make kv-materialization-live \
  BASE_URL=https://api.sage.org.ai/v1 \
  OPENAI_API_KEY=<token> \
  MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct \
  WORKLOAD_CASE=shared_prefix_multi_tenant_assistant
```

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
make runtime-boundary-live MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct
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

Keep `/home/shuhao/reference-repos/vllm` untouched. If an upstream-local delta
becomes unavoidable, carry it inside this repository under `vendor/` or
`patches/`.

This repository exists because vLLM supports out-of-tree plugins through
`vllm.general_plugins`. That seam is the right place to study arrival-time
materialization decisions without turning this repo into an upstream fork.