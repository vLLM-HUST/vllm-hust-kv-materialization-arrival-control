# vLLM KV Materialization Plugin

This repository is a standalone research plugin for vLLM focused on adaptive
KV materialization at request arrival.

The target question is deliberately narrow:

- when reusable KV or prefix state exists,
- should vLLM fully reuse it,
- partially materialize it,
- or recompute from scratch?

The repository is structured to support two phases of work in one place:

- an experimental study on reuse-benefit versus materialization-overhead
- a future out-of-tree vLLM plugin that installs through
  `vllm.general_plugins`

## Upstream Safety Workflow

- Keep `/home/shuhao/reference-repos/vllm` untouched.
- Use the dedicated repo clone and environment for this project.
- If an upstream-local delta becomes unavoidable, carry it inside this
  repository under `vendor/` or `patches/` instead of modifying the shared
  reference checkout.

## Bootstrap

Preferred bootstrap:

```bash
make bootstrap-env
```

Default assumptions for this repository:

- shared clone source env: `llm-optimizations`
- dedicated environment name: `vllm-kv-materialization-exp`
- local model examples should prefer `/home/shuhao/shared-models/<model>`

This repository now assumes day-to-day commands run inside the dedicated conda
environment `vllm-kv-materialization-exp`, either explicitly or through the
top-level `Makefile` targets, which default to `conda run -n vllm-kv-materialization-exp ...`.

## Current Scope

The first iteration is intentionally experimental-study-first.

The codebase includes:

- a small installable plugin registration surface
- a lightweight offline policy model for KV materialization decisions
- experiment scripts for trace-driven comparison
- experiment scripts for real-model OpenAI-compatible endpoint benchmarking
- a paper-side offline study pipeline that writes paper-ready summaries
- a paper skeleton and related-work archive

The current action space is:

- `full_reuse`
- `partial_reuse`
- `recompute`

## Repository Layout

```text
vllm-kv-materialization-plugin/
├── CHANGELOG.md
├── CONTRIBUTING.md
├── Makefile
├── README.md
├── agent.md
├── proposal/
├── pyproject.toml
├── scripts/
├── src/
│   └── vllm_kv_materialization/
├── paper/
│   ├── kv_materialization_control/
│   └── related_works/
├── tests/
└── vendor/
```

## Why This Can Be A Separate Repository

vLLM supports out-of-tree plugins through the `vllm.general_plugins` entry-point
group and the `VLLM_PLUGINS` environment variable.

This repository uses that plugin boundary so the policy logic, experiments, and
paper can evolve independently from upstream vLLM.

## Common Commands

```bash
make help
make bootstrap-env
make install-dev
make smoke
make test
make offline-experiment
make experiment
make live-benchmark MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct
make pdf
make paper
make build
```

## Usage

Run vLLM with the plugin enabled through the wrapper launcher:

```bash
vllm-kv-materialization-serve serve --model <model>
```

Run the offline experiment harness:

```bash
vllm-kv-materialization-offline --policy heuristic
```

The canonical repo-local bootstrap helper is:

```bash
bash scripts/setup_repo_env.sh
```

Run the paper-side study pipeline and build the PDF:

```bash
make experiment
make pdf
```

Run a real-model benchmark once a vLLM environment and model path are available:

```bash
make live-benchmark MODEL=/home/shuhao/shared-models/Qwen2.5-7B-Instruct WORKLOAD=short_low
```

## Paper And Experiments

The paper workspace lives under:

- `paper/kv_materialization_control/`
- `paper/kv_materialization_control/experiments/`
- `paper/related_works/`

The experiment pipeline currently emits:

- `paper/kv_materialization_control/experiments/results/latest/offline_summary.json`
- `paper/kv_materialization_control/experiments/results/latest/offline_summary.md`
- `paper/kv_materialization_control/experiments/results/latest/offline_summary_table.tex`

The default offline study now derives representative workload cases from the
sibling `llm-serving-workloads` repository instead of relying only on the
checked-in sample JSONL, and it reports an oracle upper bound plus heuristic
cost-misestimation sensitivity results alongside the main baselines.

The live benchmark path writes endpoint results under:

- `paper/kv_materialization_control/experiments/results/live/`

The current proposal materials live under:

- `proposal/topic.md`

## Research Framing

This repository is intentionally not a placement-policy clone of DP-locality
work and not an eviction-policy clone of prior KV-retention work.

Its question is orthogonal:

- given reusable state,
- how much of that state should be materialized,
- and when is reuse not worth its realization overhead?

That gives a single-hook policy problem with a moderate action space and a
clean path from study to plugin.