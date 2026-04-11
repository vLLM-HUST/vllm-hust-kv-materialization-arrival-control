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

### Changed

- Replaced template naming, package metadata, launcher names, and plugin entry points with repository-specific identifiers.
- Updated the top-level workflow so `make experiment` refreshes paper results and `make pdf` builds the paper from the latest generated summaries.
- Changed the paper-side default experiment from a checked-in toy trace to representative shared workload cases.