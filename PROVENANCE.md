# Provenance

## Repository lineage

This project was developed as `intellistream/kv-materialization-arrival-control`
and transferred to
[`vLLM-HUST/vllm-hust-kv-materialization-arrival-control`](https://github.com/vLLM-HUST/vllm-hust-kv-materialization-arrival-control)
in pull request [#22](https://github.com/vLLM-HUST/vllm-hust-kv-materialization-arrival-control/pull/22).
The transfer retained the complete Git history. Authorship remains attributable
through the original commits; organization membership or package maintenance
does not replace commit authorship.

The current package maintainer is Wei He (`healer-positive`). The implementation
and evidence history also contains contributions from Shuhao Zhang and the
authors recorded in the repository's Git history and paper artifacts.

## Runtime carrier

`vendor/vllm` is a Git submodule sourced from
[`vLLM-HUST/vllm-hust`](https://github.com/vLLM-HUST/vllm-hust). The
materialization runtime contract is based on vLLM-HUST `main` at
`55d6c601da6ae2ed61ce9b7b3d5e3607a6402023` and reconciled with the versioned
plugin carrier at `4c1593c1bf9dfa3e7d4e11a29aec8d9f5a7dec3b` (PR #20). The
previous 0.23 carrier line ended at request-processing hook commit
`363794235231c032de407fbe759d693962ced81a` and is retained only as historical
evidence; it is not the supported plugin carrier.

The parent repository pins the exact carrier commit. Changes to the public
request-processing hook are developed in the carrier repository and must keep
their own author, review, and test history before the parent submodule pointer
is advanced.

## Third-party boundaries

- vLLM source and its notices remain under `vendor/vllm` and retain their
  upstream licensing and history.
- Workload definitions come from the separately versioned
  [`vLLM-HUST/llm-serving-workloads`](https://github.com/vLLM-HUST/llm-serving-workloads)
  package.
- Experiment outputs and paper artifacts do not change the ownership or
  license of their source software, datasets, or models.

No file should be copied from a legacy or sibling repository without adding
its source commit, author, and applicable license to this document.
