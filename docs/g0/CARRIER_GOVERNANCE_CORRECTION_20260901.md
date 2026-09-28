# Issue #17 carrier governance correction

The approved first reply named `vendor/vllm@68b8be04493d39d5706f3d0d18f465f5eab947c4`
as G0's unique in-repository runtime carrier. That identity was not the runtime
used by formal sequences 1–63.

The calibration gate found that the required materialization-specific
activation and cost signals are available in the AscendStore layerwise path.
The formal runs therefore executed one internally consistent, isolated carrier:

- vLLM `0fc695fc6d1d82e9a5ac6835ac8e4e1c83703665`;
- vLLM-Ascend base `f4a08bddd0cc65a0bd8c3d377b158ae5ca7527db`
  plus the read-only G0 source snapshot
  `af62e947cbdd53eb5f278c7bf83e7f56db7ec0529195011864dba5e75df35182`;
  reconstruction commit `643b36992`; the unnecessary upstream Draft PR
  <https://github.com/vllm-project/vllm-ascend/pull/15468> was closed unmerged;
- profiling base `9be6a32b9e64e06c7a60def100452abf127850bb`
  plus source snapshot
  `4c9a4f956e1e2e25f28bcb7c93f0c096cd5d5582abdba67da0b27ff02b76867a`;
  reconstruction commit `3d2ef06`; the profiling Draft PR
  <https://github.com/vLLM-HUST/vllm-hust-profiling/pull/3> was closed unmerged;
- DeepSeek-V2-Lite bf16, TP1, eager mode, physical NPU 2.

No run mixed the vendored and Ascend carriers, and no WaveMat graph result was
reused as G0 evidence. Nevertheless, substituting the executed carrier without
first updating the approved Issue reply is a governance deviation. The raw run
tree is not rewritten. A machine-readable post-hoc correction is stored beside
the frozen suite as `execution_identity_posthoc_correction.json` and is covered
by the new custody manifest.

The negative conclusion is deliberately narrow: Stop applies to the executed
AscendStore carrier. It is not evidence about the unexecuted vendored carrier.
Because the executed cell independently shows non-repeatability and generic
token-bucket equivalence, the correction does not justify additional
performance runs or a mechanism issue. Owner acknowledgement of this carrier
correction is still required before closing Issue #17 as governance-complete.
