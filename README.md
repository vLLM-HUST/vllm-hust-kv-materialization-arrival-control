# vLLM General Plugin Template

## Bootstrap

Preferred bootstrap:

```bash
make bootstrap-shared-env
```

That clones the shared `vllm-research` baseline and installs the template repository as the repo overlay.

This repository is a minimal standalone template for building an independently
publishable vLLM optimization plugin.

It is intended for the exact workflow you asked about:

- keep the optimization in its own repository,
- publish it as a normal Python package,
- install it into a target vLLM environment, and
- inject it into vLLM through the official plugin mechanism instead of carrying
  a long-lived fork.

## Upstream Safety Workflow

- Keep `/home/shuhao/reference-repos/vllm` clean.
- Use this template to build out-of-tree plugins, not to justify patching the reference checkout.
- If a derived plugin truly needs upstream-local code, vendor or clone vLLM inside that derived repository.

## Why This Works

vLLM already supports general plugins through Python entry points under the
group `vllm.general_plugins`, filtered by the `VLLM_PLUGINS` environment
variable and loaded through `vllm.plugins.load_general_plugins()`.

That means an optimization plugin can be distributed out of tree as long as it:

1. registers a callable entry point,
2. keeps the registration logic re-entrant, and
3. patches or extends a stable-enough runtime boundary in the target vLLM
   version.

## Repository Layout

```text
vllm-general-plugin-template/
├── CHANGELOG.md
├── CONTRIBUTING.md
├── Makefile
├── README.md
├── pyproject.toml
├── src/
│   └── vllm_general_plugin_template/
│       ├── __init__.py
│       ├── launcher.py
│       └── plugin.py
└── tests/
    └── test_launcher.py
```

## Installation

```bash
make install-dev
```

## Common Local Commands

```bash
make help
make smoke
make test
make lint
make format
make build
```

## Usage

With explicit plugin loading:

```bash
VLLM_PLUGINS=general_plugin_template \
vllm serve --model <model>
```

Or through the wrapper launcher:

```bash
vllm-template-serve serve --model <model>
```

## What To Change For A Real Optimization

- Rename the package and plugin name in `pyproject.toml`.
- Replace the sample patch in `plugin.py` with your real optimization hook.
- Keep the patch idempotent because vLLM may load plugins in multiple
  processes.
- Prefer narrow monkey-patch boundaries such as one scheduler method, one
  attention-layer path, or one model registration hook.

## Good Fit For This Pattern

- decode backend selection
- scheduler admission control
- KV pressure control
- out-of-tree model registration
- instrumentation and observability hooks
- targeted runtime fast paths

## Weak Fit For This Pattern

- changes that require deep custom kernels inside vLLM C++ or Triton internals
- changes that need broad cross-module refactors in upstream runtime logic
- features that depend on undocumented internals with high churn risk

## Publishing Flow

```bash
python -m build --sdist --wheel
pip install dist/vllm_general_plugin_template-*.whl
```

Then load it in the target vLLM environment:

```bash
VLLM_PLUGINS=general_plugin_template vllm serve --model <model>
```