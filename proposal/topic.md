# Topic Note

## Working Title

Adaptive KV Materialization Control for Multi-GPU LLM Serving

## Problem Statement

Modern LLM serving systems increasingly expose reusable KV or prefix state, but
the presence of reusable state does not by itself imply lower latency.
Realizing reuse can require inter-worker transfer, host-device movement,
partial reconstruction, and memory pressure that compete directly with prompt
recomputation cost. The systems question is therefore not simply whether reuse
exists, but whether that reuse should be fully realized, partially realized, or
discarded in favor of recomputation.

## Scope

This repository studies one narrow control hook: request-arrival KV
materialization. The decision surface is intentionally limited to three
actions:

- `full_reuse`
- `partial_reuse`
- `recompute`

This scope keeps the work orthogonal to decode-backend selection, worker
placement, and eviction timing. Those mechanisms may influence the cost model,
but they are not the primary subject of this artifact.

## Research Thesis

The central thesis is that reuse must be controlled, not merely detected. A
well-designed controller should compare the value of saved recomputation
against the cost of realizing reusable state, and should sometimes prefer
partial reuse or full recomputation even when a larger reusable prefix is
available.

## First-Phase Study Plan

- Compare always-recompute, always-full-reuse, thresholded partial reuse, and an adaptive heuristic over the same three-action space.
- Use shared workload cases from `llm-serving-workloads` so the study reflects scenario-grounded serving patterns rather than repo-local toy traces.
- Measure TTFT, p95 latency, recomputed prompt tokens, and KV bytes realized or transferred.
- Report an oracle selector only as an upper bound on policy headroom, not as a deployable result.

## Artifact Direction

The repository should produce two clearly separated evidence layers:

- offline workload-driven analysis that characterizes the materialization decision surface
- online plugin validation that tests whether the same control interface improves live serving behavior in vLLM
