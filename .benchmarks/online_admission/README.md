# Two-action admission for verified LMCache hits

Apply `vendor/patches/verified-external-admission.patch` to the pinned vLLM 0.25.1 core. The hook runs after a positive async LMCache lookup and before destination block allocation. The vLLM-HUST project package supplies the serving connector. Set `kv_connector_module_path` to `vllm_kv_materialization.online_kv_admission`, `kv_connector` to `OnlineLMCacheConnector`, and `kv_connector_extra_config.admission_policy` to `online` in the engine's KV transfer config. The same connector supports `readiness`, `gate` with a `minimum_external_tokens` setting, and the default `full`. Ordinary clients require no request fields. This pilot exercises LMCache MP asynchronous loads with a resident APC prefix.

The replay uses the same selection code through an instrumented connector. The probe adds request IDs, forced baseline overrides, and forward-batch counters. Its two cache-isolated NPU copy threads stay idle in this comparison. The configured online target carries no policy override. Each trial recreates the 2,048-token local prefix against the 4,096-token checkpoint and compares 32 emitted token IDs to cold recomputation on the same service. The two phases change a target's position relative to a four-request background wave. A full comparison uses six counterbalanced epochs in one service lifecycle. Issue #41 records the individual qualification failures and which lifecycle results can be compared.

The Ascend TP2 harness requires the Qwen2.5-7B-Instruct weights, the paper's frozen discovery fixtures, the existing LMCache MP engine-driven runtime, and two available devices configured as on the experimental host. Set `KV41_CORE` to the directory containing the patched vLLM package. Set `KV41_WORK` to the prepared environment containing the Python venv and writable caches. From this directory run `bash launch.sh RUN_DIRECTORY` under the host's device and service locks. Use `KV41_PROMPT_TOKENS=4891 KV41_LEAD_MS=420` for the alternate discovery fixture or `KV41_PROMPT_TOKENS=7742 KV41_LEAD_MS=1800` for the quiescent leading phase. Restart the engine and LMCache between fixtures. The launcher retains the experimental host's model and device paths.

## Peer decode cost, frozen discovery confirmation

Follow-up to the 7,742-token normal-admission pilot. In all six within-wave
resident-only timing targets the first background request shared target
prefill for two successive decode positions (absolute KV positions 4099
and 4100). Full reuse exposed the same request to one target-prefill batch,
later in its decode. All these peer steps were scheduled. Host dispatch
intervals describe service overlap and cannot identify skipped tokens or
device-kernel duration.

The peer-aware rule starts with the original target-only decision. When
resident-only adds a prefill round, charge each currently decoding peer
0.05 ms times the additional computed tokens plus 12 ms per extra round.
Divide by the peer's declared output-token budget minus one. Keep full
reuse if the largest estimated increase exceeds 5% of the prior calibrated
gate's 68.223534 ms co-batched p95 TPOT. This uses a fixed-length decoding
workload. No peer, no extra round, or an estimate below budget leaves the
original decision in place. The model considers current incumbents; future
arrivals are unavailable. Report the predicted cost and actual choice.
The previous gate calibration (493.10 ms mean full, 533.73 ms local)
fixes the external threshold at 2048 for confirmation.

Run four independent cold-start service/cache lifecycles. Each is a
paired block containing all four policies. Freeze the original controller,
the calibrated gate, readiness-only and the peer-aware default. Use two
phases of the same four-background open-loop wave, unchanged offsets
(+1800 or -20 ms for the first arrival, then every 250 ms), prompt,
2048 local plus 2048 verified external tokens, 4096-token scheduler
budget, 240 MiB LMCache and idle transfer lanes. Reset and re-prime
before each target. Rotate a balanced Williams order for eight epochs,
with both phases every epoch; vary first phase and policy across blocks.
One additional epoch qualifies all policies before timing. Each block
therefore has sixteen timing targets per arm. Assert all 32 target IDs
and all four peers' 16 IDs against contemporaneous separate cold
references. Assert local and external counts, receipts, and prefill.

Use linear p95 within each block, pairing arms by lifecycle. Same-batch
peer TPOT uses each peer's whole-stream average gap and only peers
sharing at least one actual forward step with the target. Also report
the all-peer result. Primary baseline is the frozen load-calibrated gate.
Summarize paired log ratios with a geometric mean and a two-sided 95%
Student interval across the four independent blocks (df=3). Report
point and interval outcomes for -5% TTFT and +5% peer TPOT. Any stronger
claim requires both bounds to clear their respective margins. A failed
exactness/realization check disqualifies the entire corresponding block;
record all failures, and do not tune the rule or use reserved prompts.

For this protocol run `bash peer_launch.sh RUN_DIR BLOCK_INDEX` in a fresh service for each index from 1 to 4 under the same host locks.
