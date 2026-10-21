# Canonical evidence custody

Current downloads use `vLLM-HUST/vllm-hust-benchmark`:

- [G0 formal stop](https://github.com/vLLM-HUST/vllm-hust-benchmark/releases/tag/g0-issue17-stop-20260901-v2)
- [WaveMat M0 raw traces](https://github.com/vLLM-HUST/vllm-hust-benchmark/releases/tag/wavemat-m0-raw-20260824-v1)
- [M2 closure](https://github.com/vLLM-HUST/vllm-hust-benchmark/releases/tag/m2-issue3-closure-evidence-20260811)

The historical custody documents retain original producer identities, hashes,
release IDs, failures and stop verdicts. They are not rewritten as new runs.
The source-to-target mapping is maintained in benchmark
`archive/mod-releases-20261021/kv-arrival.json`; new download consumers must use
the canonical locations while verifying the original SHA256 and byte length.

This migration does not certify KV performance, cross-run state isolation or
experiment validity. Remaining Git-embedded evidence is still migration debt
under benchmark issue #326; no history is rewritten.
