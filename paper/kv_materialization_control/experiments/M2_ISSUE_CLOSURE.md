# M2 Issue #3 Closure: 三动作控制器在线收益边界

本文件是 issue #3 的最终闭合记录。它把预注册的 2-workload 收益边界矩阵与
后续扩展的 18 个 workload 筛选结果合并为一份可审计的总账，并给出继续/停止
判断。可复核性边界：141 个 lifecycle 中，39 个（主矩阵 18 + candidate/anchor
pilot 12 + anchor confirmation 9）在仓内保留 raw bundle，可从 `results/`
逐请求独立复核；其余 102 个（stateful/catalog pilot 42 + 五轮 significance
confirmation 60）仅保留逐 run 聚合与 verdict，标记为 aggregate-only
supporting evidence，不表述为 fresh clone 可逐请求复核。

## 最终摘要（Final Summary）

**verdict 固定：`stop_mechanism_direction`。** 本 issue 以负结果闭合，不再
继续调参或扩展搜索：

- 主矩阵 18/18 lifecycle、576/576 请求有效；controller 相对每轮最佳固定策略
  的 TTFT 在两个 workload 上分别回退 9.24% 与 6.60%，6/6 matched rounds 的
  最佳固定策略均为 `always_full_reuse`；
- 18 个扩展 workload 中，4 个晋级者的五轮确认全部为负（+0.87% ~ +3.70%，
  单侧 95% 上界均 >0），20/20 确认轮最佳固定策略均为 `always_full_reuse`；
- 该判定固定写入本最终摘要与论文边界（`kv_materialization_control.tex`），
  作为当前三动作控制器方向的收口记录，不因后续证据归档而改写。

## 研究问题

计入边界对齐、lookup、cache commit 和 recomputed tail 成本后，三动作控制器
是否能在正向 workload 上优于固定策略，并在负向 workload 上正确退回。

## 主矩阵（预注册 M2_PROTOCOL）

- runtime：graph mode、block size 128、segmented-tail seam，model
  Qwen2.5-7B-Instruct，与 M1 矩阵同 runtime 载体；
- 策略：`always_recompute`、`always_full_reuse`、`controller`；
- workload：`shared_tool_scaffold_agent`（positive candidate）、
  `shared_scenario_multi_turn_knowledge_service`（fallback candidate）；
- 每 workload 3 轮 × 3 策略，每 cell 独立服务生命周期，statistical unit 为
  lifecycle；
- 完成度：18/18 bundle valid、576/576 请求成功、18 个独立 lifecycle。

### 主矩阵结果

| workload | controller vs best-fixed TTFT | E2E Δ | RPS Δ | 分类 |
|---|---|---|---|---|
| shared_tool_scaffold_agent | +9.24% | +0.16% | -0.16% | fallback_or_no_gain |
| shared_scenario_multi_turn_knowledge_service | +6.60% | +0.66% | -0.68% | fallback_or_no_gain |

6/6 matched rounds 中最佳固定策略均为 `always_full_reuse`；cost model 的
winner 排序与在线结果 6/6 一致。按预注册 stopping rule，主矩阵以负结果闭合，
不追加同协议重复、不逐 workload 调参。

## 扩展 workload 筛选（不改变 controller 参数）

主矩阵之后按 issue 的收益边界目标，用同一 runtime 对现有 workload catalog
做了三轮扩展筛选：candidate/anchor/stateful 候选 pilot（宽松晋级门槛）→
晋级 workload 五轮 matched confirmation（预注册 5% 且有统计显著性的严格门槛）。
全 M2 共 20 个不同 workload（2 个主矩阵 + 18 个扩展）、141 个完成 lifecycle、
8208/8208 请求全部通过验证。其中 catalog-closure 阶段（14 个 canonical
workload：10 个 catalog pilot + 4 个 stateful pilot，42 个 pilot lifecycle；
4 个晋级 workload 的五轮确认，60 个 confirmation lifecycle）单独记录为
102/102 lifecycle、6192/6192 请求。

### 全部 workload 与结果（TTFT 相对每轮最佳固定策略，正值=回退）

| workload | 阶段 | TTFT Δ | 结果 |
|---|---|---|---|
| shared_tool_scaffold_agent | boundary | +9.24% | fallback_or_no_gain |
| shared_scenario_multi_turn_knowledge_service | boundary | +6.60% | fallback_or_no_gain |
| shared_async_document_pipeline | candidate pilot | +14.72% | 未晋级 |
| shared_public_sharegpt_boundary | candidate pilot | +130.90% | 未晋级 |
| shared_session_continuation_maintenance | anchor pilot | +69.57% | 未晋级 |
| shared_shared_prefix_multi_tenant_assistant | anchor pilot | -3.65% | 晋级 |
| shared_shared_prefix_multi_tenant_assistant | anchor confirmation | -0.90% | 名义为正，未达 5% 门槛 |
| shared_code_eval_judge | stateful pilot | -1.21% | 晋级 |
| shared_code_eval_judge | significance confirmation | +0.87% | 95% 上界 +2.13%，无显著正收益 |
| shared_structured_json_generation | stateful pilot | +0.91% | 晋级 |
| shared_structured_json_generation | significance confirmation | +0.87% | 95% 上界 +2.95%，无显著正收益 |
| shared_memory_write_then_reuse | stateful pilot | +3.83% | 未晋级 |
| shared_multi_turn_support_chat | stateful pilot | +110.73% | 未晋级 |
| shared_experiment_planning_assistant | catalog pilot | +4.81% | 未晋级 |
| shared_session_affine_multi_turn | catalog pilot | +12.44% | 未晋级 |
| shared_session_affine_bursty | catalog pilot | +1.15% | 晋级 |
| shared_session_affine_bursty | significance confirmation | +2.29% | 95% 上界 +3.89%，无显著正收益 |
| shared_simulation_analysis_verification | catalog pilot | +2.20% | 未晋级 |
| shared_rag_followup | catalog pilot | +39.90% | 未晋级 |
| shared_realtime_voice_assistant | catalog pilot | +23.31% | 未晋级 |
| shared_dynamic_rag_corpus_update | catalog pilot | +24.67% | 未晋级 |
| shared_long_context_doc_analysis | catalog pilot | -2.42% | 晋级 |
| shared_long_context_doc_analysis | significance confirmation | +3.70% | 95% 上界 +6.19%，无显著正收益 |
| shared_preemption_resume_long_decode | catalog pilot | +19.95% | 未晋级 |
| shared_repo_aware_coding_assistant | catalog pilot | +12.69% | 未晋级 |

四个晋级 workload 的五轮确认全部为负：controller TTFT 均值均为正回退
（+0.87% ~ +3.70%），且所有单侧 95% 上界都大于 0；20/20 确认轮最佳固定
策略均为 `always_full_reuse`。

## 机制分解与物理成本

每个 bundle 记录并验证：

- avoided prefill token 与 recomputed tail token 来自 engine 计数
  （`engine_reused_tokens` / `engine_recomputed_tokens`），不把 requested
  partial_reuse 当作 realized reuse；
- lookup、boundary alignment、cache commit、tail isolation、decision 与
  controller 延迟；
- observed / effective / realized action 三套计数及差异；
- realign、退回 full reuse、退回 recompute 的次数与 fallback reason；
- TTFT、E2E 延迟、吞吐和 peak cache usage。

主矩阵逐 bundle 明细见 `results/m2_online_boundary_20260803/`；扩展
workload 的 54 组 workload/stage/policy 汇总（含 action 计数与 fallback
reasons）见 `results/m2_catalog_closure_20260803/mechanism_breakdown.csv`。

## 验收条件对照

- matched 配置与重复服务生命周期：全 M2 141 个完成 lifecycle
  （18 主矩阵 + 123 扩展）全部独立、validated，8208/8208 请求成功；
- 核心结论可从原始 action counters 与性能记录复核：仓内 39 个 lifecycle
  （主矩阵 18 + candidate/anchor pilot 12 + anchor confirmation 9）保留
  raw bundle，可逐请求独立复核；其余 102 个 lifecycle 仅保留逐 run 聚合
  CSV + verdict，为 aggregate-only supporting evidence（raw bundle 原存
  执行机 /tmp，现已不可取回，见"数据保留程度"）；
- requested partial_reuse 不计为 realized reuse：所有机制分解均以 engine
  计数为准；
- 论文机制分解表与重建脚本：`m2_mechanism_table.tex` /
  `m2_action_table.tex`（已 `\input` 进论文），`make m2-online-rebuild`
  与 `make m2-significance-confirmation-rebuild`；
- claim ledger：real-online / simulation-model / derived-artifact 三类均已
  标记（`CLAIM_LEDGER.md` + 各 `claim_ledger.json`）。

## 最终判断

**verdict：`stop_mechanism_direction`。** 在现有 workload catalog、matched
Qwen2.5-7B-Instruct/Ascend 配置下，未发现 controller 相对最佳固定策略
`always_full_reuse` 的有意义且统计显著的正收益 workload；最佳结果
（multi-tenant assistant）在独立确认中只有 -0.90% TTFT，低于 5% 门槛。
结果按负结果记录，不继续 post-hoc workload 搜索或逐 workload 调参。
该 verdict 固定写入最终摘要与论文边界，作为本方向的标准闭合表述。

这是有限 catalog 结论，不是"任何配置下都不存在正收益"的普适定理；chunk
index、semantic candidate 与验证协议仍属于 vLLM-HUST #198 的范围。

## 数据保留程度与 Release 归档

- 仓库内保留 raw bundle（validation.json、runtime observations）：
  `m2_online_boundary_20260803`（18 lifecycle）、`m2_candidate_pilot`（6）、
  `m2_anchor_pilot`（6）、`m2_anchor_confirmation`（9），共 39 个 lifecycle；
- 已创建公开可引用的 raw-bundle release 归档（对应上述 39 个 lifecycle）：
  release tag `m2-issue3-closure-evidence-20260811`，
  <https://github.com/intellistream/kv-materialization-arrival-control/releases/tag/m2-issue3-closure-evidence-20260811>，
  asset `m2_raw_bundles_39_lifecycles.tar.gz`（SHA-256
  `56803f152b19e7f30aba6195bacba25eb2adb1de9db9e42369752ccb9fae37c4`）；
- 仓库内保留逐 run 聚合与 verdict（无 raw bundle）：
  `m2_stateful_secondary_pilot`、`m2_catalog_closure_20260803`（5 shards）、
  4 个 `m2_significance_*` 确认目录，共 102 个 lifecycle；
- 执行机 `/tmp` 中的原始 suite 已被清理，102 个 lifecycle 的 raw bundle
  无法再取回；这些结果一律作为 aggregate-only supporting evidence，不参与
  "fresh clone 可逐请求独立复核" 的声明；
- 上述 release 只归档 39 个 lifecycle 的 raw bundle，不包含 102 个
  aggregate-only lifecycle，也不恢复 141 个 lifecycle 的强声明；在 102 个
  raw bundle 被归档到持久、内容寻址的位置之前，论文与 issue 保持 39/102
  口径；
- 若后续把 102 个 lifecycle 的 raw bundle 归档到持久、内容寻址的 artifact
  （release asset 或对象存储），可再把复核范围扩回 141 个 lifecycle；归档
  完成前，论文与 issue 中的可复现性表述以上述 39/102 边界为准。
