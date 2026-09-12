# G0 raw-signal gate

**Current status: technical early-Stop evidence complete; Issue owner decision
pending.** No additional performance matrix or wave-shaping mechanism work is
warranted on the executed AscendStore carrier. The Issue is not governance-
complete until the owner accepts the post-hoc carrier correction and the
truth-oracle boundary in `REVIEW_CORRECTIONS_20260901.md`. The original static audit
correctly found that the unmodified AscendStore connector did not export the
required counters. An isolated G0 worktree at `/root/g0-vllm-ascend` now
exports requested/realized bytes, bytes in flight, connector enqueue/wait,
layer-ready wait, request IDs, decisions, configuration, and activation
results. It also contains the default-off static threshold required only for
the matched recompute/minimum-retrieve baselines. The old
`telemetry_seam_audit_20260831.json` remains as the immutable before-state; its
`telemetry_unavailable_stop` result is superseded for this instrumented G0
carrier and is not the current study verdict.

Formal execution validated the contiguous canonical run prefix 1–63 and then
stopped at the repeatability condition. ServeGen/moderate did not reproduce
the >=10% p95 TTFT pathology in two of three repeats. Ordinary request-token-
bucket equivalence is supporting evidence only because its exact one-point
tolerance was not stated in the approved Issue reply. The report is
`/root/g0-formal/issue17/reports/formal_v1_20260831/g0_formal_report.json`;
the read-only archive and custody record are under
`/root/g0-artifacts/issue17/formal_20260831`.
The published custody release is
<https://github.com/intellistream/kv-materialization-arrival-control/releases/tag/g0-issue17-stop-20260901-v2>;
its raw archive asset ID is `539131048`, with SHA-256
`6474d718f65aeee3824e25897934922672c2a51e92f6c218be6f5b16a7f0ad4a`.

`pilot_20260831.md` and `pilot_20260831.json` are a real-runtime, single-repeat
2 workload × 2 intensity core pilot plus paired strict 1 req/s controls. They
validate the seam and expose the next required check; they do not replace the
preregistered three repeats or full matched baselines. The frozen four-point
capacity frontier is now complete for all four burst cells at repeat 1.

Rebuild it with:

```bash
python3 scripts/audit_g0_telemetry_seam.py \
  --connector /vllm-workspace/vllm-ascend/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/ascend_store_connector.py \
  --pool-worker /vllm-workspace/vllm-ascend/vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/pool_worker.py \
  --repo-root "$PWD" \
  --output docs/g0/telemetry_seam_audit_20260831.json
```

Rebuild the pilot report from the custody paths recorded in its JSON with
`scripts/summarize_g0_pilot.py`. Raw archives and SHA-256 identities are
recorded separately in `pilot_custody_20260831.json`.

Rebuild the formal real-runtime evidence directly from its run tree with
`scripts/rebuild_g0_formal.py`. It reports `incomplete_no_verdict` for missing
or invalid evidence, except when a complete three-repeat cell in a contiguous
execution prefix has already triggered preregistered fail-fast Stop:

```bash
make g0-formal-rebuild \
  G0_SUITE_DIR=/root/g0-formal/issue17/suite/formal_v1_20260831 \
  G0_RUN_ROOT=/root/g0-formal/issue17/formal_v1_20260831 \
  G0_FORMAL_JSON=/tmp/g0-formal.json \
  G0_FORMAL_MARKDOWN=/tmp/g0-formal.md \
  G0_PATHOLOGY_CSV=/tmp/g0-pathology.csv \
  G0_PATHOLOGY_SVG=/tmp/g0-pathology.svg
```

For a location-independent rebuild starting from the immutable GitHub Release,
including relocated manifest verification, use:

```bash
make g0-release-rebuild
```
