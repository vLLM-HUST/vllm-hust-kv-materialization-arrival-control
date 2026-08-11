# M2 Raw Bundle Archive Manifest — 39 lifecycles

This manifest describes the raw-bundle release artifact for M2 issue #3
closure. The final verdict is fixed as `stop_mechanism_direction`, and the
evidence boundary is kept at 39/102: 39 lifecycles are reviewable
request-by-request from the raw bundles in this archive, while the remaining
102 M2 lifecycles remain aggregate-only supporting evidence.

- Release tag: `m2-issue3-closure-evidence-20260811`
- Release URL:
  <https://github.com/intellistream/kv-materialization-arrival-control/releases/tag/m2-issue3-closure-evidence-20260811>
- Archive date: 2026-08-11
- Source repository: `intellistream/kv-materialization-arrival-control`

## Contents

The archive contains the same raw-bundle directories that are checked into the
repository under `paper/kv_materialization_control/experiments/results/`:

| Directory | Lifecycles | Contents |
|---|---|---|
| `results/m2_online_boundary_20260803/` | 18 | preregistered main matrix (2 workloads × 3 policies × 3 rounds) |
| `results/m2_candidate_pilot_20260803/` | 6 | offline-ranked candidate pilot (`failed_label_attempt` excluded) |
| `results/m2_anchor_pilot_20260803/` | 6 | anchor-topology candidate pilot |
| `results/m2_anchor_confirmation_20260803/` | 9 | independent three-round anchor confirmation |

Each lifecycle bundle retains the raw SSE request records, runtime
observations, scheduler-owned events, validation JSON, environment manifest,
and cleanup evidence, so per-request review can be reproduced from this
archive alone.

## Evidence boundary (kept at 39/102)

The other 102 M2 lifecycles (stateful/catalog pilots plus the four five-round
significance confirmations) are aggregate-only supporting evidence: their raw
bundles originally lived in `/tmp` on the execution machine and are no longer
retrievable. This archive does not include them, and this release does not
restore the 141-lifecycle per-request-review claim. Per-request raw review
covers 39 lifecycles; the remaining 102 remain aggregate-only until their raw
bundles are archived to a persistent, content-addressed location.

## Verification

Unpack the archive and validate any lifecycle with:

```bash
tar -xzf <archive>
python paper/kv_materialization_control/experiments/validate_online_bundle.py \
  --bundle-dir <unpacked-lifecycle-dir>
```

The full main-matrix rebuild entry point remains:

```bash
make m2-online-rebuild \
  M2_REBUILD_INPUT_DIR=paper/kv_materialization_control/experiments/results/m2_online_boundary_20260803
```
