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
materialization runtime contract is based on current vLLM-HUST `main` at
`d14cd5cc6ff205652429dc93feeb9700c6623108` and implemented by carrier commit
`8c018264e994e8147d7f2dc5aafc613fa0218aec`. The previous 0.23 carrier line
ended at request-processing hook commit
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
