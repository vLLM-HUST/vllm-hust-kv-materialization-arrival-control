# Claim Ledger

| Claim | Evidence class | Status | Rebuild source |
|---|---|---|---|
| M1 的三轮独立重启矩阵支持 non-randomized、temporally blocked 的描述性 seam 分析 | real-online | supported；不支持稳定的一般 seam 性能收益 | `experiments/results/m1_formal_approved_complete_20260801/` |
| M2 三动作控制器相对最佳固定策略的在线收益边界 | real-online | negative：两个 workload 的 controller TTFT 分别比最佳固定策略回退 9.24% 和 6.60% | `experiments/results/m2_online_boundary_20260803/generated/m2_benefit_boundary.csv` |
| observed/effective/realized action、fallback 原因和物理开销分解 | real-online | supported：18 个独立 lifecycle、576/576 请求完成，全部 raw validation 通过 | raw observations/events → `m2_online_runs.csv` |
| 当前 cost model 的策略排序与在线排序一致 | simulation/model | supported：6/6 matched rounds 的 winner 均为 `always_full_reuse` | `m2_cost_model_agreement.csv` |
| 论文机制表与继续投稿/停止判断 | derived-artifact | supported：成本/性能和 action/fallback 两个 panel 均由 raw bundle 重建；`stop_mechanism_direction`，不继续逐 workload 调参 | `m2_mechanism_table.tex`, `m2_action_table.tex`, `m2_verdict.json` |
| M2 offline-ranked positive-candidate pilot | real-online | negative/exploratory：两个新增候选均未通过 promotion gate；不作为重复确认或论文正收益证据 | `experiments/results/m2_candidate_pilot_20260803/` |
| M2 anchor-topology positive-candidate pilot | real-online | exploratory：multi-tenant candidate 以 TTFT -3.65% 通过 promotion gate；必须由排除 pilot 的三轮 matched confirmation 复验 | `experiments/results/m2_anchor_pilot_20260803/` |
| M2 anchor-topology independent confirmation | real-online | not positive：TTFT -0.90%、E2E -1.36%、throughput +1.35%，但不满足预注册 5% TTFT boundary，且轮级方向为 2 胜 1 负 | `experiments/results/m2_anchor_confirmation_20260803/` |
| M2 stateful-secondary 四 workload pilot | real-online | exploratory：4 个新 workload、12/12 lifecycle；2 个通过宽松晋级门槛，pilot 不作为正收益证据 | `experiments/results/m2_stateful_secondary_pilot_20260803/` |
| M2 stateful-secondary 五轮确认 | real-online | negative：code-eval 与 structured-JSON 的 controller TTFT 均为 +0.87%，单侧 95% 上界分别 +2.13%/+2.95% | `experiments/results/m2_significance_code_eval_20260803/`, `experiments/results/m2_significance_structured_json_20260803/` |
| M2 剩余 canonical catalog closure pilot | real-online | exploratory/negative：10 个 workload、30/30 lifecycle；2 个通过宽松晋级门槛，其余回退 +2.20% 至 +39.90% | `experiments/results/m2_catalog_closure_20260803/` |
| M2 catalog closure 五轮确认 | real-online | negative：long-context TTFT +3.70%（95% 上界 +6.19%），bursty +2.29%（上界 +3.89%）；20/20 轮最佳固定策略均为 full reuse | `experiments/results/m2_significance_long_context_20260803/`, `experiments/results/m2_significance_bursty_20260803/` |
| M2 扩展 workload 的 cost-model 排序 | simulation/model | supported at confirmation boundary：离线模型未预测任何 >=5% 收益，且 4 个晋级 workload 的五轮在线最佳固定策略均为 full reuse；不进行逐 workload 参数校准 | offline study → four confirmation verdicts |
| M2 现有 catalog 显著正收益结论 | derived-artifact | negative/stop：14 个新 canonical workload 完成 pilot，4 个晋级者全部完成五轮确认；102/102 lifecycle、6192/6192 请求有效，未发现 >=5% 且单侧 95% 上界低于 0 的 workload；停止 post-hoc 搜索和调参。证据边界：该 102/102 lifecycle 为 aggregate-only supporting evidence（逐 run 聚合 + verdict，raw bundle 原存执行机 /tmp、现已不可取回），不参与 fresh-clone 逐请求复核声明 | `experiments/results/m2_catalog_closure_20260803/README.md`, `mechanism_breakdown.csv` |
| M2 issue #3 完整闭合：20 个 workload 的收益边界总账与继续/停止判断 | derived-artifact | negative/stop（verdict 固定为 `stop_mechanism_direction`）：2 个主矩阵 workload 均 fallback_or_no_gain；18 个扩展 workload 中晋级者五轮确认全部为负；141/141 lifecycle、8208/8208 请求。证据边界：39/141 lifecycle 仓内 raw 可逐请求复核（并归档于 release `m2-issue3-closure-evidence-20260811`），102/141 为 aggregate-only supporting evidence，39/102 口径在 102 个 raw bundle 归档前保持不变 | `experiments/M2_ISSUE_CLOSURE.md` + 各 `results/m2_*/` 生成物 + `experiments/RELEASE_MANIFEST.md` |

生成的 `claim_ledger.json` 是该轮结果的机器可读 ledger。requested action 仍不得写成
realized reuse；例如 tool controller 的 lifecycle 中位 applied mix 是 8/8/16
（recompute/partial/full），而 engine-realized mix 是 16/16/0。
