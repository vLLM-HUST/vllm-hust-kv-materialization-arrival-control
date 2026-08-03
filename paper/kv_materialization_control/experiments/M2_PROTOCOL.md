# M2：三动作控制器在线收益边界

## 研究问题

M2 只回答 arrival-time KV materialization control 的收益边界：在同一 runtime、
模型、请求序列和独立服务生命周期下，当前三动作控制器能否在候选正向 workload
上优于 `always_recompute` 与 `always_full_reuse`，并在候选负向 workload 上退回或
如实记录无收益。它不扩展到 chunk index、semantic candidate 或验证协议。

## 预注册矩阵

- runtime seam：segmented-tail isolation；不在主比较中混入旧 seam；
- controller knobs：沿用 M1 的 `tuned` 条件（floor 128 tokens、confidence penalty
  8 ms），M2 不按 workload 调参；
- 策略：`always_recompute`、`always_full_reuse`、`controller`；
- workload：`shared_tool_scaffold_agent` 是 positive candidate，
  `shared_scenario_multi_turn_knowledge_service` 是 fallback/no-gain candidate；
- 每个 workload 三轮，每轮三个策略，策略首位在三轮中平衡；
- 每个 cell 独立启动和关闭服务；统计单位是 lifecycle，不是 request；
- 固定 request rate、concurrency、seed、block size、model length 和输出长度；
- 恰好三轮后停止。如果 controller 没有优于最佳固定策略，记录负结果，不追加
  同协议重复或逐 workload 调参。

主指标是 mean TTFT、mean end-to-end latency 和 request throughput。正收益的保守
判据是 controller 相对每轮最佳固定策略的平均 TTFT 至少改善 5%，且平均 E2E 与
throughput 均不劣化超过 5%。否则归类为 `fallback_or_no_gain`。

## 原始证据与机制分解

每个 bundle 必须包含并通过验证：

- 原始 SSE request records 与可重算的延迟、TTFT 和吞吐；
- planner observation 中的 policy mode、observed/effective action、decision 和
  boundary-alignment 计时；
- scheduler-owned lookup/commit event 中的 realized action、reused/recomputed token、
  lookup/commit/tail-isolation 计时、cached blocks 与 cache usage；
- fallback reason，包括 block realign、退回 full reuse 和退回 recompute；
- parent/carrier commit、环境、模型配置、protocol fingerprint、graph-mode 和清理证据。

`requested partial_reuse` 永远不替代 engine 计数。论文表中的 avoided prefill work
来自 `engine_reused_tokens`；recomputed tail 来自 realized partial request 的
`engine_recomputed_tokens`。

## 执行与重建

在 clean parent/carrier worktree 和空闲 NPU 上执行：

```bash
make m2-online-boundary \
  MODEL=/root/models/Qwen2.5-7B-Instruct \
  M2_SUITE_DIR=/tmp/kv_materialization_m2_online
```

验证全部 lifecycle 后重建：

```bash
make m2-online-rebuild \
  M2_SUITE_DIR=/tmp/kv_materialization_m2_online \
  M2_RESULTS_DIR=paper/kv_materialization_control/experiments/results/m2_online_boundary
```

聚合器只接受状态为 `completed`、18 个 cell 完整、protocol matched、lifecycle ID
独立且逐 bundle validation 通过的 suite。它生成 per-run CSV、机制分解 CSV、收益
边界 CSV、cost-model/online 排序检查、论文 TeX 表、claim ledger 和继续/停止判断。

## 当前证据状态

协议、runtime counters、runner、validator 和 deterministic aggregator 已实现；在真实
NPU suite 完整导入前，M2 的 real-online 收益与投稿判断均保持 pending，不能从 M1
controller-only 数据推断固定策略边界。
