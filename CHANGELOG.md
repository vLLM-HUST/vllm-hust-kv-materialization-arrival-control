# Changelog

## Unreleased

- Fixed the M2 issue #3 closure wording per the final review: the verdict
  `stop_mechanism_direction` is now the fixed final-summary and paper-boundary
  statement, and the 39 in-repo raw-bundle lifecycles are archived in release
  `m2-issue3-closure-evidence-20260811` (asset
  `m2_raw_bundles_39_lifecycles.tar.gz`). The 39/102 evidence boundary is
  retained: the 102 aggregate-only lifecycles remain outside the
  per-request-review claim until their raw bundles are archived to a
  persistent, content-addressed location.
- Added the preregistered M2 matched online boundary study comparing
  `always_recompute`, `always_full_reuse`, and the three-action controller over
  independent service lifecycles.
- Added explicit fixed-policy runtime modes and scheduler-owned timing for
  lookup, cache commit, block-boundary alignment, and segmented-tail isolation;
  recompute now bypasses cache lookup and commit as a native action.
- Added fail-closed M2 bundle validation, action/fallback/work decomposition,
  cost-model ordering checks, a paper-facing TeX table, a typed claim ledger,
  and a deterministic continue/stop verdict.
- Completed the 18-lifecycle M2 matrix (576/576 requests): the controller
  regressed TTFT versus the best fixed policy by 9.24% and 6.60% on the two
  preregistered workloads, so the mechanism direction stops as a negative
  result rather than receiving workload-specific retuning.
- Closed M2 issue #3 with a consolidated 20-workload benefit-boundary ledger
  (`paper/kv_materialization_control/experiments/M2_ISSUE_CLOSURE.md`):
  18 extension workloads were screened without retuning, all four promoted
  workloads failed five-round confirmations (+0.87% to +3.70% TTFT, all
  one-sided 95% upper bounds above zero), and the final verdict is
  `stop_mechanism_direction` across 141 validated lifecycles and 8208/8208
  requests. Evidence boundary: raw bundles for only 39 of the 141 lifecycles
  are in the repository (per-request review); the remaining 102 lifecycles are
  aggregate-only supporting evidence whose raw bundles lived in `/tmp` on the
  execution machine and are no longer retrievable.

## [Unreleased]

### Added

- Created the standalone `vllm-kv-materialization-plugin` repository scaffold.
- Added a runnable offline policy model for `full_reuse`, `partial_reuse`, and `recompute` decisions.
- Added a paper workspace with an offline-study pipeline, experiment result emitters, and a compileable LaTeX draft.
- Added a related-work archive with the most relevant distributed inference PDFs for the materialization line.
- Added a repo-local environment bootstrap helper and a dedicated conda environment workflow centered on `vllm-kv-materialization-exp`.
- Added workload-driven offline study inputs sourced from the sibling `llm-serving-workloads` repository.
- Added oracle and cost-misestimation sensitivity baselines to the offline study outputs.
- Added a shared-workload adapter so both offline and live materialization evaluations consume the same `llm-serving-workloads` case catalog.
- Added explicit dual-mode workflows for experimental-paper reruns and optimization-paper live benchmarks.
- Added OpenAI-compatible live endpoint support for `OPENAI_API_KEY`, custom `User-Agent`, and endpoint roots that already include `/v1`.
- Added standard `shared-workloads-smoke` and `shared-workloads-test` root targets, plus a `.benchmarks/` placeholder workspace for standardized shared workload smoke artifacts.
- Added explicit decision-surface workload coverage for prefix-rich multi-tenant, long-context continuation, and dynamic retrieval follow-up shared cases from `llm-serving-workloads`.
- Added explicit live runtime fallback taxonomy fields so `partial_reuse` degradations are logged as unsupported exact segment materialization rather than implied as native runtime support.
- Added a detailed Chinese `HANDOFF.md` so the repository can be handed to a student with a clear paper-oriented plan, especially around the unresolved `partial_reuse` runtime boundary.
- Added an isolated `carrier/vllm-hust/` runtime copy for carrier-side experiments so segmented materialization hooks can be developed without modifying the shared workspace checkout.

### Changed

- Changed the live runtime seam so per-request materialization plans now carry exact reuse and tail token targets through a dedicated materialization-control `extra_args` payload instead of reusing `kv_transfer_params`, avoiding false `KVConnector` expectations while exact token-level `partial_reuse` remains unavailable.
- Changed live `partial_reuse` handling from a pure `full_reuse` fallback to a block-aligned realizable action: the runtime now rounds the offline cut point down to the configured hash-block size, executes block-aligned partial reuse when it remains best, and otherwise re-ranks to `full_reuse` or `recompute`.
- Changed the carrier-side prefix-cache hook to honor `effective_decision`, so only realized `partial_reuse` plans cap prefix-cache lookup while `full_reuse` and `recompute` fallbacks execute their intended runtime actions.
- Changed the carrier-side cache commit path so effective `partial_reuse` no longer materializes recomputed tail blocks into the shared prefix cache; shared cache writes now stop at the aligned reuse boundary.
- Changed the paper-side live launcher to auto-detect a usable conda bootstrap and environment, run against the repo-local `carrier/vllm-hust` copy by default, and place live-run caches under writable temporary roots unless explicitly overridden.
- Replaced template naming, package metadata, launcher names, and plugin entry points with repository-specific identifiers.
- Updated the top-level workflow so `make experiment` refreshes paper results and `make pdf` builds the paper from the latest generated summaries.
- Changed the paper-side default experiment from a checked-in toy trace to representative shared workload cases.
- Changed the live benchmark path from repo-local workload presets to named shared workload cases, with compatibility aliases retained only in the driver.
- Changed the recommended workspace entry so workload-driven tests start from `llm-serving-workloads` or repository targets explicitly wired to it.
- Changed the repo-local vLLM launcher so `MAX_MODEL_LEN` now defaults from `llm-serving-workloads` shared `serving_hints` via `WORKLOAD_CASE`, instead of hard-coding a separate repository-local context-window default.
- Changed the canonical experiment naming to `decision-study` and `runtime-boundary-live`, while retaining older names as compatibility aliases.
- Changed the README and paper framing to keep the repo scoped to arrival-time materialization decisions, explicitly excluding general admission and online memory evolution.
- Changed package metadata and repository URLs for transfer readiness to the `intellistream` organization.
- Changed docs to remove user-specific absolute path examples and source-organization-specific live endpoint examples.
- Added explicit ownership and transfer targets in `README.md` for `caozhe` and `xuheng li`.
- Changed the ownership marker to record `cao zhe` as the current student owner and `intellistream` as the target repository organization.
- Changed repository ownership markers from transfer planning state to completed handoff state after moving the repository into the `intellistream` organization.
- Changed the offline `partial_reuse` semantics from a fixed fraction proxy to a confidence-aware cut-point optimizer shared by the policy, threshold baseline, and oracle evaluator.
