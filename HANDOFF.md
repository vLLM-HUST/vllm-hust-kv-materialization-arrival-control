# 项目交接说明

## Runtime carrier checkpoint

唯一 runtime carrier 是 `vendor/vllm` submodule，分支为
`feature/kv-materialization-runtime-integration`，基于 vLLM-HUST `main`
commit `e4ce33646f2ef1781289e6dc651fad0d00177c55`，当前 pinned carrier commit
为 `68b8be04493d39d5706f3d0d18f465f5eab947c4`。fresh checkout 的最小 CPU 验收命令为：

```bash
git submodule update --init --recursive
bash scripts/setup_repo_env.sh
make test
```

环境脚本只创建或复用 `vllm-kv-materialization-exp`；如果它尚不存在，
脚本会从 `vllm-hust-dev` 克隆，但不会向后者安装项目依赖。

## M2 closure checkpoint（2026-08-03）

M0、M1 和 M2 已闭合。M2 在 parent `2e99ce1`、carrier `475ea49` 上完成
2 workloads × 3 policies × 3 independent lifecycles，18/18 bundle validation
通过，576/576 请求成功。controller 相对每轮最佳固定策略的 matched mean TTFT
分别回退 9.24% 和 6.60%；`always_full_reuse` 赢得 6/6 matched rounds，cost model
排序也 6/6 一致。

因此当前明确判断是 `stop_mechanism_direction`：不再按 workload 调参，不追加同协议
重复，也不把 M1 的 seam/runtime-realization 结果写成固定策略收益。原始 bundle、机制
表和机器可读 claim ledger 位于
`paper/kv_materialization_control/experiments/results/m2_online_boundary_20260803/`。
该 verdict 已固定写入最终摘要与论文边界；39 个仓内 raw-bundle lifecycle 同时归档于
release `m2-issue3-closure-evidence-20260811`
（asset `m2_raw_bundles_39_lifecycles.tar.gz`），其余 102 个 lifecycle 保持
aggregate-only 口径（39/102），不恢复 141 个 lifecycle 的逐请求复核声明。

后文只把 M2 之前的路线列为已关闭历史；“继续做强 partial reuse / deeper seam”不再是
当前执行计划，也不能在同一协议下重新开启。

## 负结果后的新研究合同（2026-08-28）

当前只允许推进一个不同的、带前置门的研究问题：有限 paged-KV 容量下，局部最优的
`always_full_reuse` 是否会因为占用、逐出 victim 或阻塞无缓存关键请求而产生跨请求外部性。
这不是旧三动作控制器的改名或调参延续。

执行必须以 `docs/FINITE_CACHE_REUSE_ADMISSION_CONTRACT.md` 为准。先做不包含新 treatment
的 D0 固定策略 crossover 矩阵；`always_full_reuse` 仍是不可删除的强基线，offline future-aware
oracle 只能作为上界。只有 D0 同时通过固定策略 winner switch、原生 block/victim/wait receipt、
正确性和 cleanup 门，才允许另立 M1 方案。没有 crossover、静态容量/并发门已足够、receipt
无法归因、或任何 ownership/stale/cleanup 错误都立即停止。

证据标签必须保持 `real-online`、`replay`、`host-fixture`、`smoke`、`simulation`、
`projected`、`derived-artifact` 分离；旧 M2 和 WaveMat 负结果继续成立。两周交付止于
一次有原始记录和 Go/Stop verdict 的 D0，不以实现新策略为交付目标。

## 当前定位与唯一进行中主线

该课题由学生 owner 负责实施与实验；本文件只给出导师侧研究故事线和验收合同。
旧 request-local 三动作 controller 已由 M2 负结果关闭：它在两个 workload、六个
matched round 中均输给 `always_full_reuse`。旧阈值、`partial_reuse` guardrail、deeper
seam 和 connector continuation 只作为已完成历史方法与边界证据保留，不再是进行中机制，
也不得通过调参或挑 workload 重开。

唯一进行中的研究问题是：在固定 paged-KV 容量下，局部最优的 full reuse 是否会通过
block residency、victim displacement、queue wait 或 deadline pressure 对并发请求产生可测
外部性。该现象尚未被观察到，当前没有新 treatment。

## D0 两周交付（学生 owner 执行）

学生 owner 应严格按 `docs/FINITE_CACHE_REUSE_ADMISSION_CONTRACT.md` 完成一次
treatment-free、matched fixed-policy crossover：

1. 冻结 `always_full_reuse`、`always_recompute`、旧 controller、固定并发/容量门和原生
   cache policy；不得删除最强固定基线。
2. 在低/高 overlap 与 roomy/constrained capacity 的预注册 cell 中运行完全相同的请求、
   顺序、模型、runtime 和资源边界。
3. 保存原生 block、victim、residency、wait、action、completion identity 与 cleanup receipt；
   正确性和 ownership/cleanup 必须 100% 通过。
4. future-aware oracle 仅作离线上界，不是 online policy，也不允许据此实现自适应 treatment。
5. 交付原始记录、哈希、聚合表和一个明确的 Go/Stop verdict；导师不代做实现、环境、实验、
   结果生成或性能调优。

## 可证伪条件与停止门

D0 只有在 `always_full_reuse` 保留至少一个低压力 winner，同时另一可部署固定策略在至少
两个预注册 constrained-overlap cell 获胜，且 full reuse 的 p95 TTFT 至少差 10% 或 SLO
goodput 至少低 5%，并由原生 receipt 因果解释时才通过。没有 crossover、静态容量/并发门
已足够、receipt 无法归因、或出现任何正确性/cleanup 错误，都立即停止有限缓存新假设。
只有 D0 通过后，学生 owner 才可另立 M1 treatment；M1 仍须满足相对最强固定基线至少 5%
SLO-goodput 增益、总体 p95 回退不超过 5%、零正确性与清理错误。

## 已关闭的历史路线

三动作 controller、offline decision surface、block-aligned `partial_reuse` seam、参数敏感性和
connector-backed continuation 均属于旧路线的历史方法或诊断材料。它们可以用于解释负结果
如何产生，但不得再写成下一阶段任务、当前贡献或待实现机制。

## 不该做的事情

1. 不要把这个仓库重新写成 generic state-management 或 generic memory-evolution 项目。
2. 不要把 `partial_reuse` 的 fallback 当成已经实现了真实 partial reuse。
3. 不要在本仓库复制 `llm-serving-workloads` 的 workload family。
4. 不要为了实验方便直接改共享 upstream `vllm`。
5. 不要把 offline overlap 或 offline action choice 直接写成 runtime gain。

## 最低投稿门槛

在宣称新主线 ready for submission 之前，必须先有通过上述门槛的 D0 fixed-policy
crossover；否则论文只能报告旧 controller 的负结果与新假设尚未观察，不能声称有限缓存
外部性存在，更不能声称新策略有效。

## 开始前先读

1. `README.md`
2. `CHANGELOG.md`
3. `paper/kv_materialization_control/kv_materialization_control.tex`
4. `src/vllm_kv_materialization/policy.py`
5. `src/vllm_kv_materialization/live_control.py`
6. `src/vllm_kv_materialization/offline_experiment.py`
7. `paper/kv_materialization_control/experiments/run_offline_study.py`
8. `paper/kv_materialization_control/experiments/run_openai_workloads.py`
