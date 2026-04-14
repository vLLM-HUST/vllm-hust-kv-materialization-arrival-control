# KV Materialization Control Paper Workspace

This directory contains the paper skeleton and experiment notes for the vLLM KV
materialization project.

The workspace now supports two evidence modes from the same paper tree:

- experimental mode: offline shared-workload study
- optimization mode: live shared-workload benchmark over the out-of-tree plugin

Primary claim direction:

- reusable state is not free to realize
- the right policy is not always full reuse
- partial reuse can outperform both full reuse and recompute in mixed workloads

## Local Workflow

From the repository root:

```bash
make study-experiment
make pdf
```

The experiment target refreshes `experiments/results/latest/` and emits both
JSON and LaTeX-friendly summaries consumed by the draft.

For real-model serving experiments, see:

- `experiments/LIVE_EXPERIMENTS.md`
