# M1 old/segmented paired carrier validation

This non-performance dry pair addresses the reviewer gate after the in-worktree
runner self-contamination was identified. It was executed from a repository-
external scratch root and imported without rewriting its manifests.

- Parent commit: `f2ddea6c1d076abe94d9de068af5cf9f83eff29f`
- Carrier commit: `68b8be04493d39d5706f3d0d18f465f5eab947c4`
- Workload: `shared_scenario_multi_turn_knowledge_service`
- Knobs: baseline for both seams
- Device/model/block: NPU 7, Qwen2.5-7B-Instruct, 128 tokens
- Protocol fingerprint for both runs:
  `e05dc1bf54e11cfdec742df4693d7ee35aaf6c4ee4757bd90a49db888d0e81cf`
- Independent lifecycle IDs: 2/2
- Request completion: 32/32 for each run
- Strict validation: PASS for both runs
- Applied mix for each run: 8 recompute, 0 partial, 24 full
- Realized mix for each run: 16 recompute, 16 partial, 0 full
- Cleanup: port and NPU idle after both runs

Reviewer-facing files:

- `paired_suite_manifest.json`: suite command, exact lifecycle/validation
  commands, fingerprint and lifecycle IDs.
- `01_old_baseline/{validation.json,environment_manifest.json}`.
- `02_segmented_baseline/{validation.json,environment_manifest.json}`.

This pair validates the carrier and protocol only. It is not included in the
formal performance aggregation.
