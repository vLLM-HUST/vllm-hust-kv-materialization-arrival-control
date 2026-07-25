# KV Materialization Editorial and Submission Audit — 2026-07-25

## Disposition

**Clean research draft; not a submission candidate.**

The paper is now readable and reproducible at its bounded offline scope, but
the current online claim cannot be independently audited from the files in the
workspace. No new hardware run was performed in this pass.

## Seven-question review

1. **Question.** At request arrival, should a server fully reuse available KV
   state, reuse only a block-aligned prefix, or recompute?
2. **Importance.** Reuse can reduce prefill work, but transfer, adaptation, and
   memory pressure can erase that benefit.
3. **Gap.** Existing prefix-cache and remote-KV work motivates realization
   cost, but this draft does not yet position itself adequately against recent
   KV blending, cache stitching, and remote-KV systems.
4. **Idea.** Compare estimated saved prefill work with realization cost, select
   one of three actions, and record both the requested and executed action.
5. **Feasibility.** The repository contains a block-aligned segmented vLLM
   path and a deterministic offline cost-model study.
6. **Evaluation.** The offline result covers 1,296 requests from 25 workload
   cases at `llm-serving-workloads@3afdd1aca8a4255a50bb523254037cdca0a7adc4`.
   Full reuse is the best mean-TTFT policy in 18 cases; the oracle selects
   partial reuse for 71 requests. The online tables are descriptive single
   runs and are not statistically powered.
7. **Takeaway.** Partial reuse is a narrow workload-specific option, not a
   broad win. The mechanism is a plausible research seed, but a submission
   claim requires retained raw online results and stronger novelty coverage.

## Editorial changes

- Replaced `Anonymous Artifact Draft` with `Anonymous Authors`.
- Rewrote the title, abstract, introduction, contribution statement,
  limitations, conclusion, and AI disclosure in normal paper language.
- Removed the 25-row workload-code table.
- Replaced the three-panel, 25-workload stacked chart with one readable chart
  showing only the eight workloads where the oracle selects partial reuse.
- Added a compact aggregate offline result table and labeled its numbers as
  cost-model estimates.
- Labeled every online table cell as a descriptive single run without a
  confidence interval.
- Removed repeated artifact/evidence-boundary sections and internal workload
  identifiers from reader-facing prose.
- Added finite hyphenation penalties and `microtype`; the final log has no
  overfull or underfull boxes.

## Evidence and reproducibility

- Offline manifest:
  `experiments/results/offline_evidence_manifest.json`
- Pinned workload commit:
  `3afdd1aca8a4255a50bb523254037cdca0a7adc4`
- Offline summary SHA-256:
  `7572d84f9cca17f2460d79c38beadb143685378ca4817ee4a453ca8b46dd320c`
- The present `llm-serving-workloads` main branch contains 28 cases and
  deterministically yields 1,488 requests. The paper does not silently replace
  the pinned 25-case evidence with that newer catalog.
- The four-cell online matrix is present only as manuscript/README aggregates.
  The corresponding raw result bundle was not found in the workspace. These
  numbers therefore remain descriptive and cannot support a submission claim.

## Validation

- Deterministic Tectonic build twice with
  `SOURCE_DATE_EPOCH=1784985600`: byte-identical.
- PDF: 5 US-Letter pages; all fonts embedded.
- TeX log: no overfull box, underfull box, undefined reference, or undefined
  citation.
- Visual inspection: all five pages rendered at 160 dpi and inspected; no
  clipping, overlap, unreadable table, or abnormal one-column gap.
- Ruff: pass.
- CPU tests not importing the carrier runtime: 35 passed, 3 deselected.
- The three carrier-integration tests require a functioning vLLM/torch/NPU
  environment. The documented `vllm-kv-materialization-exp` environment is
  absent; `vllm-hust-dev` fails while loading the Ascend runtime
  (`libhccl.so`/runtime-root failure). Two stale unit assertions were repaired
  to match the current full-reuse realignment and dataclass schema.

## Remaining submission blockers

1. Recover the exact raw online result bundles for the reported matrix, or run
   a newly frozen, repeated, matched graph-mode protocol and retain every raw
   result. Do not treat the current single-run aggregates as a speedup result.
2. Establish novelty against recent KV blending, stitching, and remote-KV
   systems with a materially complete related-work comparison.
3. Restore a reproducible project runtime environment and pass the three
   carrier-integration tests without changing the scientific path.
4. Select a venue and bind its page limit, template, anonymity, and AI
   disclosure rules.

No author confirmation is requested because these are scientific and
reproducibility blockers, not final-byte approval.
