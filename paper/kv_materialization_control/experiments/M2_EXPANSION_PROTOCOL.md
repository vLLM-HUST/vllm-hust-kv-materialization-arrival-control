# M2 boundary expansion: preregistered candidate pilot

## Purpose

The original M2 matrix found no positive workload among its two preregistered
cases. This extension searches the existing workload catalog without changing
the controller or tuning it per workload. It is exploratory screening until a
candidate passes a fresh repeated confirmation matrix.

## Candidate selection fixed before online execution

The committed 28-case offline study was ranked by controller mean modeled TTFT
relative to the better of `always_recompute` and `always_full_reuse`.

- `shared_async_document_pipeline`: modeled controller delta -0.23%, with a
  64/15/1 full/partial/recompute mix over 80 requests;
- `shared_public_sharegpt_boundary`: modeled controller delta -0.19%, with a
  1/30/1 mix over 32 requests.

The synthetic shared-prefix case has the same current modeled metrics as the
ShareGPT boundary and is excluded as a redundant pilot. No case reaches the
original 5% meaningful-gain threshold offline; the pilot therefore tests
model/runtime disagreement rather than claiming prior positive evidence.

## Stage 1: fail-closed pilot

For each candidate, run `always_recompute`, `always_full_reuse`, and
`controller` once, each in an independently restarted graph-mode service. Use
the same model, carrier, block size, seed, concurrency, request rate, output
limit, segmented seam, and tuned controller knobs within a workload.

A workload is promoted only if controller mean TTFT is no worse than 2% above
the best fixed policy, while mean E2E and throughput are no worse than 5%.
This deliberately permissive gate avoids discarding a noisy candidate; pilot
runs are never included in the final positive claim.

## Stage 2: independent confirmation

For every promoted candidate, run three new temporally blocked matched rounds
with balanced policy order. A positive boundary requires controller mean TTFT
to improve by at least 5% relative to the per-round best fixed policy, with
mean E2E and throughput no worse than 5%. Requested actions cannot substitute
for scheduler-owned realized action accounting.

If neither pilot candidate passes the promotion gate, stop the expansion and
record that the current catalog/model screen produced no credible positive
candidate. Do not add candidates after observing pilot results under this
protocol.

