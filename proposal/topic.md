# Topic Note

## Working Title

Adaptive KV Materialization for Multi-GPU vLLM Serving

## Core Question

When a new request arrives and reusable KV or prefix state exists, should the
system fully reuse that state, partially materialize it, or recompute the
prefix from scratch?

## Why This Repository Exists

- It is orthogonal to decode-placement policies.
- It is orthogonal to KV eviction timing work.
- It keeps a single-hook policy surface that can be implemented as an out-of-tree vLLM plugin.

## First-Phase Experimental Study

- Compare full reuse, fixed-threshold partial reuse, recompute, and a simple adaptive heuristic.
- Use workload families with strong state reuse: multi-turn chat, shared-prefix coding, RAG follow-up, and long-context document analysis.
- Measure TTFT, recompute tokens, KV bytes loaded, transfer latency, and tail latency.
