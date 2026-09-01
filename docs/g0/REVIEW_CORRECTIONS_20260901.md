# G0 review corrections before Issue #17 owner decision

This note records review findings without rewriting the immutable v2 raw
custody. Merging the evidence PR does not close Issue #17; the Issue owner
must make the carrier and Stop decisions in the Issue itself.

## Decision scope

The evidence supports stopping further performance runs and mechanism work on
the executed AscendStore carrier. The primary trigger is repeatability:
ServeGen/moderate exceeded the 10% p95 TTFT regression threshold in only one
of three independent server lifecycles (8.47%, 17.84%, and 2.18%; median
8.47%). This conclusion does not require the report's generic-baseline
equivalence tolerance.

The request-token-bucket comparison remains a supporting observation only.
The report implementation uses a one-percentage-point tolerance for both tail
improvement and goodput loss. That exact tolerance was not stated in the
approved Issue reply or frozen suite manifest, so it must not be represented
as an independently preregistered Stop trigger.

## Truth-oracle boundary

The immutable runs close the following observations on the executed path:

| Signal | Raw evidence | Rebuild validation |
|---|---|---|
| connector activation/config | explicit `connector_config` and decision events | fail-closed |
| requested/realized bytes | per-transfer and per-request byte records | equality required |
| bytes in flight | transfer start/finish records | summarized |
| connector queue depth/wait | enqueue and transfer records | summarized |
| layer-ready wait | completion records with request IDs | summarized |
| materialize/recompute choice | explicit decision taxonomy | fail-closed per arm |
| transfer result | explicit result code | all results must succeed |

The runs do **not** contain explicit fields named `cache_epoch`,
`fallback_reason`, or `waiting_reason`. Cache state is indirectly constrained
by fixed overlays, warm-prefix setup, realized reuse/bytes, output hashes, and
fresh server lifecycles, but that is not an exported cache-epoch oracle.
Similarly, decision labels distinguish materialization, threshold recompute,
and cache miss, but they are not a separate fallback-reason field. The run
directories also do not contain the preregistration's promised standalone
`run_manifest.json` or environment/config file; relevant controls and runtime
identity are distributed across benchmark JSON, connector events, logs, the
suite manifest, and the post-hoc identity sidecar.

These omissions cannot be repaired by adding fields to historical raw data.
The owner must either accept this disclosed evidence boundary for the narrow
negative conclusion, or treat the incomplete truth-oracle contract itself as
a Stop condition. They must not be described as fully closed telemetry gates.

## Carrier governance

Formal sequences 1–63 did not execute the vendored vLLM carrier named in the
approved first reply. They executed the single AscendStore carrier recorded in
`CARRIER_GOVERNANCE_CORRECTION_20260901.md`. The Stop result therefore applies
only to that executed DeepSeek-V2-Lite TP1 eager AscendStore configuration.
Owner acknowledgement is required before the Issue is governance-complete.

## Portable custody rebuild

The published manifest retains absolute producer roots as provenance. Its
relative file entries can now be verified after extraction elsewhere, using
root overrides in `build_g0_raw_manifest.py`. The complete portable workflow
is:

```bash
make g0-release-rebuild
```

It downloads the immutable v2 archive, checks the archive SHA-256, rejects
unsafe archive members, verifies all relocated suite/run/rejected/report
files, rebuilds the verdict and pathology artifacts, checks the published
Markdown/CSV/SVG hashes, and compares JSON after removing only host-specific
path fields. For a private repository it reuses an authenticated `gh` session,
or `GH_TOKEN` / `GITHUB_TOKEN`; `G0_RELEASE_ARCHIVE=/path/to/archive` provides
an offline path. The published JSON remains immutable and retains producer
paths.
