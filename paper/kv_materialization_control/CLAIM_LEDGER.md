# Claim Ledger

| Claim | Evidence class | Status | Rebuild source |
|---|---|---|---|
| M1 的三轮独立重启矩阵支持 non-randomized、temporally blocked 的描述性 seam 分析 | real-online | supported；不支持稳定的一般 seam 性能收益 | `experiments/results/m1_formal_approved_complete_20260801/` |
| M2 三动作控制器相对最佳固定策略的在线收益边界 | real-online | pending，必须由完整的 18-cell M2 suite 决定 | `aggregate_m2_boundary.py` → `m2_benefit_boundary.csv` |
| observed/effective/realized action、fallback 原因和物理开销分解 | real-online | instrumentation ready；online values pending | raw observations/events → `m2_online_runs.csv` |
| 当前 cost model 的策略排序与在线排序一致 | simulation/model | pending；不得用模型输出替代在线结果 | `aggregate_m2_boundary.py` → `m2_cost_model_agreement.csv` |
| 论文机制表与继续投稿/停止判断 | derived-artifact | pending；仅从 validated real-online bundle 重建 | `m2_mechanism_table.tex`, `m2_verdict.json` |

M2 聚合完成后，生成的 `claim_ledger.json` 是该轮结果的机器可读 ledger。未完成真实
online suite 时，不得手工把 pending 改成 supported，也不得把 requested
`partial_reuse` 数量写成 realized reuse。
