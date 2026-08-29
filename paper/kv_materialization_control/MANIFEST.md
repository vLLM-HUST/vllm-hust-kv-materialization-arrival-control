# Advisor paper artifact manifest

- Repository: `intellistream/kv-materialization-arrival-control`
- Draft PR: `#19`
- Artifact commit: `3805fd3d57702f4ad67642310610c5ad27e2bb90`
- Entry point: `paper/kv_materialization_control/kv_materialization_control.tex`
- Bibliography: `paper/kv_materialization_control/kv_materialization_control.bib`
- PDF: `paper/kv_materialization_control/kv_materialization_control.pdf` (7 pages)
- Full Tectonic log: `paper/kv_materialization_control/kv_materialization_control.log`
- Build transcript: `paper/kv_materialization_control/BUILD_TRANSCRIPT.txt`
- Build command: `tectonic --keep-intermediates --keep-logs kv_materialization_control.tex`
- Build exit code: `0`

## Artifact hashes

| Asset | SHA256 |
|---|---|
| `kv_materialization_control.tex` | `ae427f30a0331f0580641ea8c01a2b59dfc086d24d4985528d72b56148419f7e` |
| `kv_materialization_control.bib` | `c85aee0168d90ac3e0f13c5b451f70f0753a5403d4b51a76b594ea2fddc76d0e` |
| `kv_materialization_control.pdf` | `78322a956e3bff824c5c48d37af10d1aa5533cd7fd157f8142449992d70cfc22` |
| `kv_materialization_control.log` | `1e5fc18f2d590c4f8526412e1ccd3d81c9d02bdcaca7d9acdcdd54384b807291` |
| `BUILD_TRANSCRIPT.txt` | `6e794b9e742f8956dba228c63dd280b56b91a255f16045688a39d81b05b478e5` |
| `experiments/results/latest/offline_summary_macros.tex` | `74f3421ceb4f46cc9bb7f99d976837df3dac86a56129dce04eb25da8ad382b72` |
| `experiments/results/latest/offline_decision_mix_figure.tex` | `1450d883bc86ee5b6594890bd45aca79d023af3eed0c8cc0cef3652f50cb096b` |

The artifact commit binds the exact TeX, bibliography, historical generated inputs,
PDF, log, and transcript. The following metadata-only commit binds this manifest
to that immutable artifact commit; the Draft PR body records the final PR head.

## Verification and evidence boundary

- Tectonic completed successfully without undefined references or fatal errors.
- Allowlisted non-fatal diagnostics: underfull boxes at TeX lines 322 (badness
  1515) and 635 (badness 6412), plus IEEEtran/XeTeX font-substitution warnings.
- All seven rendered pages were inspected. No clipping, unintended overlap,
  unreadable figure, or cross-column overflow was observed. The final-page blank
  right column is the natural end of the manuscript.
- Host tests with the repository's exact `llm-serving-workloads` dependency pin
  (`ceef92d52e0c49f26ba1efc6706edd1f6df5d913`) yielded `65 passed, 3 failed`.
  The three failures are environment compatibility failures: vendored vLLM
  v0.24 imports reject the available Transformers v4 environment. They are not
  caused by this paper-only change. An initial run without the dependency pin
  stopped during collection with four missing-package errors.
- `git diff --check` passed for the paper changes.
- Highest cited evidence level: historical `real-online` runtime-boundary
  receipts already committed by the student project. The offline decision figure
  and summary are historical derived artifacts recovered byte-for-byte from
  commit `32f42772e861e3ca7a08a91328bcb285f9a1b7a0`; no experiment was rerun.
- The negative M2 result closes the old request-local three-action controller
  direction on the tested carrier. The finite-cache externality mechanism and
  its preregistered matched evaluation remain a hypothesis awaiting student-owned
  implementation and experiments.
- No NPU workload, serving experiment, mechanism implementation, environment
  installation, or new result generation was performed for this artifact.
