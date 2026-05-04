# Top-Tier Push Plan

Primary thesis: Arrival-time state handling should choose among full reuse, partial reuse, and recompute rather than collapse everything into a binary cache hit or miss.
Honest fallback: `partial_reuse` is still observed offline but falls back to `full_reuse` on the current live prefix-cache path.
Next gate: Expand the decision-study matrix and keep the runtime-boundary report explicit about which actions are currently realizable online.
Missing evidence: Quantitative evidence that partial reuse is structurally profitable on representative overlap geometries and can be realized in the runtime path.

Immediate actions:
1. Refresh heatmaps for the full decision-study workload set.
2. Keep live-path wording explicit about fallback-to-full-reuse behavior.
3. Treat the repository as a boundary paper unless true partial materialization lands.