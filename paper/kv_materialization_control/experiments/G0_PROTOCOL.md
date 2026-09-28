# G0: burst-aware KV materialization pathology gate

This is a preregistered pathology gate, not an online mechanism evaluation.
Do not add an adaptive release policy to this suite. Its sole question is
whether a burst of otherwise matched KV retrievals produces a
materialization-specific tail-latency pathology that generic request shaping
cannot match.

Execution identity, trace selection, hardware, custody, and the explicitly
incomplete real-runtime pilot are recorded in
`docs/g0/PREREGISTRATION_20260831.md`. Pilot values must not be treated as the
formal verdict or used to pick a workload-specific threshold.

## Frozen matrix

The input traces are one immutable BurstGPT replay and one immutable ServeGen
replay. Each has `moderate` and `high` burst intensity. A low-concurrency
control uses the same canonical request sequence and overlay but replaces the
source burst timestamps with strict one-request-per-second spacing. Merely
scaling the mean rate is invalid because simultaneous source timestamps would
remain a burst. Every main cell has three independently restarted
lifecycles and the following arms: `no_control`, `always_recompute`,
`concurrency_cap`, `request_token_bucket`, `minimum_retrieve_threshold`,
`fixed_prefetch_depth` (when the connector has that seam), and
`materialization_paced_oracle`. The oracle is an offline upper bound only.
Paired per-lifecycle deltas are reported with all three values and their
median. To complete the bootstrap interval promised in the first Issue reply,
the 2026-09-01 report-only amendment adds an exact 27-resample
paired-lifecycle bootstrap 95% interval. Requests within one lifecycle are not
treated as independent bootstrap units. This reporting amendment changes no
gate or executed input.

The matched static baselines are frozen as follows before formal repeats:
`always_recompute` uses AscendStore `minimum_retrieve_tokens=512`, which is
above every 128/256/384-token reuse carrier; `minimum_retrieve_threshold`
uses 256 tokens; `fixed_prefetch_depth` uses the existing
`layerwise_prefetch_layers=4` seam. All other materializing arms use threshold
0 and prefetch depth 1. These are fixed baselines, not adaptive policies, and
must emit one decision per request plus the effective connector configuration.

The real-runtime runner writes `benchmark/random-online.json`,
`benchmark/request_results.jsonl`, `raw/g0_connector_telemetry.jsonl`,
`raw/g0_resource_samples.jsonl`, and
`parsed/g0_connector_summary.json` for every arm, together with the raw and
parsed msServiceProfiler data. A record is rejected unless it contains
realized/requested bytes, bytes in flight, connector queue wait, layer-ready
wait, transfer busy, compute overlap, HBM/DRAM pressure, reuse/recompute
decisions, and correctness/activation counters. This makes the gate fail
closed if the connector cannot expose the signals.

## Overlay and custody

`scripts/g0_pathology.py overlay` converts an immutable trace to a canonical
reuse carrier. It assigns only deterministic prefix/session keys and target KV
bytes; it never reorders requests or changes their content. The output records
SHA-256 identities of both the input trace and output overlay.

Raw suites must be created outside the worktree. Archive a completed suite as
a compressed GitHub Release asset, then record asset ID, sizes, and compressed
and uncompressed SHA-256 in the custody manifest.

## Go / Stop rule

`scripts/rebuild_g0_formal.py` recomputes summaries directly from the real run
tree. Go requires all four main cells to have a median >=10% no-control versus
oracle p95 TTFT regression across the three frozen repeats (equivalently, at
least two of three repeats reach the threshold), with 100% correctness. The oracle must either stay
within 5% goodput or the complete frozen capacity–tail frontier below must be
reported. Go also requires higher materialization-specific pressure in
no-control, no equivalent benefit from generic caps, and no equal
low-concurrency effect. Missing data normally remains `incomplete_no_verdict`.
The sole exception is preregistered fail-fast Stop: once an execution-prefix
complete, frozen three-repeat cell fails repeatability, lacks the required
materialization counters, or shows an equivalent generic cap, later schedule
entries must not be run merely to search for a favorable workload. The report
then records `complete_early_stop`, the unexecuted sequence range, and the
machine-readable Stop trigger. Invalid or partial existing runs can never use
this exception.

The capacity–tail boundary is the frozen, fully reported byte-budget grid
`[31,850,496; 63,700,992; 127,401,984; 254,803,968]`. These are 4/8/16/32
times the 256-token V2-Lite MLA request cost; they were frozen before the
frontier runs. It is not permissible to retain only the best oracle budget
or to change the grid after inspecting a formal cell.

The executable matrix has 96 rotated base runs plus 36 b8/b16/b32 frontier
runs (132 total). `run_g0_matrix.sh` skips only runs that already pass the
64-request correctness and telemetry gates; it stops on a partial directory
and never overwrites a run.

```bash
python3 scripts/g0_pathology.py init --suite-dir /outside/g0-suite \
  --burstgpt-trace /data/BurstGPT.jsonl --servegen-trace /data/ServeGen.jsonl
python3 scripts/rebuild_g0_formal.py \
  --suite-dir /outside/g0-suite --run-root /outside/g0-formal-runs \
  --output-json /outside/g0-formal.json \
  --output-markdown /outside/g0-formal.md \
  --output-pathology-csv /outside/g0-pathology.csv \
  --output-pathology-svg /outside/g0-pathology.svg
```
