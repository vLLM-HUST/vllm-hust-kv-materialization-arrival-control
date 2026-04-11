# Contributing

## Upstream Safety Rule

- Do not edit `/home/shuhao/reference-repos/vllm` for this repository.
- If the out-of-tree plugin boundary becomes insufficient, carry any unavoidable upstream-local work inside this repository under `vendor/` or `patches/`.

## Expected Workflow

1. Keep plugin logic under `src/vllm_kv_materialization/`.
2. Keep paper assets under `paper/` and experiment drivers under `paper/.../experiments/` or `scripts/`.
3. Update `README.md` and `CHANGELOG.md` for visible workflow changes.
4. Do not record this repository's changes in `/home/shuhao/sagellm/CHANGELOG.md`.

## Unified Local Commands

```bash
make install-dev
make smoke
make test
make offline-experiment
make experiment
make pdf
make build
```

## Testing

```bash
make test
```