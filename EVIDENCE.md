# Canonical historical data

This migration batch is stored only in [vllm-hust-benchmark](https://github.com/vLLM-HUST/vllm-hust-benchmark/tree/2144d58de108cddaff3800fdcbf12dc9d3ab1d18/archive/mod-consumers-20261023/kv-arrival).
`BENCHMARK_EVIDENCE.json` pins the manifest and its SHA256. The manifest preserves original
repository/commit/path identities, failures and every file hash. This is custody, not a new result.

```bash
python scripts/fetch_mod_consumer_evidence.py --destination /absolute/new/external/evidence
export BENCHMARK_EVIDENCE_ROOT=/absolute/new/external/evidence
```

The destination must be new and outside this checkout. The downloader verifies the archive and
every member before writing, rejects links/unsafe paths, and never falls back to local copies.
Use `$BENCHMARK_EVIDENCE_ROOT/paper/kv_materialization_control/experiments/results/live/` for this batch's original data.
Existing generation commands may still write new local outputs; do not commit them here.

Other historical directories are not declared migrated by this batch. Original failures and
diagnostic/NO_GO scopes remain unchanged. No hardware experiment is required to read this archive.


## Additional historical directories

[Canonical history manifest](https://github.com/vLLM-HUST/vllm-hust-benchmark/blob/afd47a8e9964b71844dec75a8e908f279ae98202/archive/mod-history-20261023/kv-arrival/manifest.json) lists original paths, sizes and SHA256.
This is a separate capsule from BENCHMARK_EVIDENCE.json; do not reuse its destination.
No hardware experiment or new performance acceptance is implied.

```sh
python scripts/fetch_mod_consumer_evidence.py --config BENCHMARK_HISTORY.json \
  --destination /absolute/new/external/history
```

The restored root preserves these original paths:

- `.benchmarks/results/`
- `docs/NPU_LIVE_VALIDATION_20260910.md`

Frozen reports retain original labels and local paths; these do not assert that omitted captures were recovered.


## Remaining collections (formal / handoff / TP4-TP8 / profiler)

[Member manifest](https://github.com/vLLM-HUST/vllm-hust-benchmark/blob/812ef01ae992475d4ce6a3bb6a6ce4bda43b5f12/archive/mod-collections-20261023/kv-arrival/manifest.json) preserves the source commit and every original hash.

```sh
python scripts/fetch_mod_consumer_evidence.py --config BENCHMARK_COLLECTION.json \
  --destination /absolute/new/external/collection
export BENCHMARK_COLLECTION_ROOT=/absolute/new/external/collection
```

This root is separate from BENCHMARK_EVIDENCE_ROOT and BENCHMARK_HISTORY_ROOT.
Do not execute archived scripts; use the maintained repository validators.
All paths below are archive-relative; generation commands may still produce ignored local outputs.

- `paper/kv_materialization_control/experiments/results/`
- `docs/g0/`
- `docs/wavemat/`

Current forwarding documents, configuration and imported code remain; exact retained paths are tested in tests/test_collection_evidence_boundary.py.

## School recompute mixed document

[Original manifest](https://github.com/vLLM-HUST/vllm-hust-benchmark/blob/d8a370e9135ee5231707d8f1e3afa723851f1966/archive/mod-targeted-20261023/kv-school-document/manifest.json) preserves the complete adapter/screen
narrative. The maintained document keeps implementation guidance and directly
links the existing benchmark raw screen archive and summary. This is custody,
not a new experiment or B1 qualification. Ignored live-log gaps in other batches
remain unresolved.

```sh
python scripts/fetch_mod_consumer_evidence.py --config BENCHMARK_DOCUMENTS.json \
  --destination /absolute/new/external/school-document
```

The screen raw inputs are separately length/SHA checked in consumer CI. Installation
source pins are unchanged; historical Release pages are not current package sources.
