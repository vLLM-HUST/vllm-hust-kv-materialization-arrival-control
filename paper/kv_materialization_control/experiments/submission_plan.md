# Submission Plan

## Positioning

Push this work as a short negative-result / systems-boundary paper. The paper's
claim is not that the controller accelerates serving. It is that, on the tested
local-prefix carrier, `always_full_reuse` leaves too little economic headroom
for arrival-time action selection, while requested, effective, and realized
partial reuse frequently diverge.

The current verdict remains `stop_mechanism_direction`. Do not add per-workload
tuning, post-hoc workload search, or another same-carrier hardware campaign to
manufacture a positive result.

## Submission Gates

P0 gates before external submission:

1. Keep all manuscript-consumed tables content-addressed in `PAPER_INPUTS.json`
   and verify that a fresh checkout has no missing `\input` files.
2. Select a short-paper / negative-results venue and apply its current template,
   page limit, anonymity, and artifact rules.
3. Complete author order, affiliations, acknowledgements, and an author claim
   review against `CLAIM_LEDGER.md`.
4. Build the PDF in a pinned TeX environment and archive the source/PDF pair.

P1, only if a selected venue requires broader external validity:

- add one independently preregistered carrier or remote-tier setting where full
  reuse has a non-trivial transfer cost; treat it as a new study, not a
  continuation of the closed controller search.

## Current Decision

- **GO:** internal paper convergence and venue selection as a bounded short paper.
- **NO-GO:** positive controller-speedup framing or full-paper submission on the
  current evidence alone.
- **No new experiments are authorized by this plan.**
