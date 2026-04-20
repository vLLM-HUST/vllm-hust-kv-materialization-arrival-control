# Changelog

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

### Changed

- Replaced template naming, package metadata, launcher names, and plugin entry points with repository-specific identifiers.
- Updated the top-level workflow so `make experiment` refreshes paper results and `make pdf` builds the paper from the latest generated summaries.
- Changed the paper-side default experiment from a checked-in toy trace to representative shared workload cases.
- Changed the live benchmark path from repo-local workload presets to named shared workload cases, with compatibility aliases retained only in the driver.
- Changed the recommended workspace entry so workload-driven tests start from `llm-serving-workloads` or repository targets explicitly wired to it.
- Changed the repo-local vLLM launcher so `MAX_MODEL_LEN` now defaults from `llm-serving-workloads` shared `serving_hints` via `WORKLOAD_CASE`, instead of hard-coding a separate repository-local context-window default.
- Changed the canonical experiment naming to `decision-study` and `runtime-boundary-live`, while retaining older names as compatibility aliases.
- Changed the README and paper framing to keep the repo scoped to arrival-time materialization decisions, explicitly excluding general admission and online memory evolution.