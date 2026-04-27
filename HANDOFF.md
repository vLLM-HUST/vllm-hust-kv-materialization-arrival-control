# 项目交接说明

## 当前定位

这个仓库已经完成独立化和 transfer 准备，但从研究视角看，仍然属于 advanced incubation 阶段。

它已经不是一个空模板，也不是单纯的工程脚手架。当前更准确的状态是：

1. 核心问题已经收紧到 request arrival 时刻的 KV materialization decision。
2. 三种动作 `full_reuse`、`partial_reuse`、`recompute` 的离线决策面已经建立。
3. shared workload 入口、offline study、live boundary 路径和 paper 骨架都已存在。
4. 但真正的论文级主线仍然没有完全闭环，尤其是 `partial_reuse` 的 runtime realization 还没有打通。

因此，接手人不应把这个仓库当成“已经做完的插件”，而应把它当成“问题定义和证据边界都已经比较清楚，但还需要继续做强的系统研究项目”。

## 当前已经有的基础

在开始继续推进前，应把以下内容视为已知基线：

1. 这个仓库研究的是 arrival-time KV materialization 决策，而不是 general admission control，也不是 online memory evolution。
2. 当前动作空间已经固定为 `full_reuse`、`partial_reuse`、`recompute`。
3. offline study 已经能对三动作决策面做 workload-grounded 分析。
4. live path 当前只能 truthfully 实现：
	- `full_reuse`
	- `recompute`
	- `partial_reuse` 目前仍会退化到 anchor-scoped `full_reuse`
5. shared workload 入口已经统一到 `llm-serving-workloads`，不应在本仓库复制 workload family。

## 这个项目离一篇系统论文还差什么

### 1. 还差把 `partial_reuse` 从“被观察到的动作”推进到“被真正实现的动作”

当前最关键的缺口不是有没有 paper，也不是有没有 benchmark，而是主角动作 `partial_reuse` 还没有形成真正的 runtime path。

如果后续论文仍然停留在：

1. offline 决策面里 `partial_reuse` 很重要
2. live runtime 里 `partial_reuse` 只是 fallback 到 `full_reuse`

那么论文很容易停在一个“研究问题很好，但系统实现没有真正闭环”的状态。

所以接手后的首要任务，应围绕下面的问题推进：

1. `partial_reuse` 需要什么 runtime seam 才能真正 materialize 一个 profitable prefix segment？
2. 当前 prefix-cache path 为什么只能表达 anchor-scoped exact reuse，而不能表达 segment-level materialization？
3. 是继续在 out-of-tree plugin boundary 内试探，还是需要一个最小 upstream/runtime hook proposal？

### 2. 还差更强的机制层内容

当前 offline 控制面已经有了，但如果要做成系统论文，还需要一个更强的 mechanism story，而不只是“有三个动作，然后离线比较一下”。

至少要进一步明确：

1. 三动作的判定信号是什么
	- prefix overlap geometry
	- recompute cost
	- materialization cost
	- startup latency pressure
2. 决策器的误差来源是什么
	- cost estimation drift
	- overlap boundary estimation drift
	- runtime fallback distortion
3. 如果 runtime 只能部分实现动作空间，控制器如何 truthfully 退化而不污染结论

也就是说，后续主线不应只停留在“离线算哪个动作更好”，而要写成“如何在不完整 runtime seam 下设计一个 truthful arrival-time materialization controller”。

### 3. 还差更完整的实验闭环

当前实验已经有一定基础，但离系统论文仍差几层。

至少还要补：

1. `partial_reuse` 的机制性实验
	- 哪些 workload case 最依赖 segment-level materialization
	- 如果只能 fallback 到 `full_reuse`，误差有多大
2. offline 与 live 的一致性分析
	- offline 决策面和 live realizable surface 的偏差到底有多大
	- 哪些 workload 上偏差最大，为什么
3. sensitivity 分析
	- 成本估计误差
	- overlap 估计误差
	- prompt/decode 长度变化
	- workload overlap pattern 变化
4. negative result / boundary case
	- 哪些场景下 `partial_reuse` 即使真正实现也未必值得
	- 哪些场景下 `full_reuse` 与 `recompute` 已经足够
5. runtime hook value 分析
	- 如果增加一个最小 runtime seam，预期能恢复多少离线决策价值

### 4. 还差必要的调研

要把这条线做成论文，必须把相关工作定位补扎实。

建议重点调研：

1. prefix reuse / KV reuse / segment reuse 相关系统工作
2. serving-time memory-for-compute tradeoff 相关工作
3. long-context serving 中的 state materialization / state transfer / partial recompute 相关工作
4. runtime hook / plugin boundary / serving controller 相关系统论文

调研目标是回答：

1. 我们的贡献到底是一个决策问题、一个 runtime mechanism，还是一个 boundary paper？
2. `partial_reuse` 与 exact reuse、full recompute、segment reuse 的关系是什么？
3. 这个工作和 admission、memory evolution、scheduler line 的边界要如何清楚切开？

### 5. 还差更硬的论文主线

如果要投系统论文，后续文章主线建议围绕下面四层组织：

1. 问题：arrival-time KV materialization 是什么，为什么它和 admission / eviction / scheduler 不一样。
2. 方法：三动作控制器如何建模，为什么 `partial_reuse` 是关键动作。
3. 边界：当前 runtime seam 能做什么，不能做什么，truthfulness 如何保证。
4. 价值：最小 runtime hook 为什么值得，恢复了什么原本丢掉的决策价值。

如果论文最后只剩“offline 很好看，live 还没做出来”，说服力会明显不足。

## 建议的推进顺序

### 第一阶段：冻结问题与边界

1. 读完 `README.md`、`CHANGELOG.md`、`paper/kv_materialization_control/kv_materialization_control.tex`。
2. 明确这篇论文的最终问题定义。
3. 明确动作空间、信号、runtime boundary 和 fallback taxonomy。

### 第二阶段：做强 `partial_reuse`

1. 先系统梳理 `partial_reuse` 当前为什么无法在 live runtime 真正落地。
2. 判断是否能在现有 plugin seam 内实现最小 segment-level materialization。
3. 如果不能，就明确提出一个最小 runtime hook proposal。

### 第三阶段：补实验闭环

1. 做 offline vs live 偏差分析。
2. 做 sensitivity 和 negative result。
3. 做 runtime hook value / realizable surface analysis。

### 第四阶段：重写论文

1. 用真实机制、真实偏差分析和真实 runtime boundary 替换现有骨架中的泛化表述。
2. 明确哪些结论是 decision-surface 层，哪些是 runtime-realization 层。
3. 把 truthfulness boundary 写成论文贡献的一部分，而不是免责声明。

## 不该做的事情

1. 不要把这个仓库重新写成 generic state-management 或 generic memory-evolution 项目。
2. 不要把 `partial_reuse` 的 fallback 当成已经实现了真实 partial reuse。
3. 不要在本仓库复制 `llm-serving-workloads` 的 workload family。
4. 不要为了实验方便直接改共享 upstream `vllm`。
5. 不要把 offline overlap 或 offline action choice 直接写成 runtime gain。

## 最低投稿门槛

在宣称这个项目 ready for submission 之前，至少要满足：

1. `partial_reuse` 的 runtime-boundary 问题被系统讲清楚
2. 有一套完整的 offline vs live 边界分析
3. 有一组能说明最小 runtime hook 价值的实验或机制论证
4. 有清晰的 negative-result narrative
5. 论文草稿已经从“artifact 说明”提升成“问题 + 方法 + 边界 + 价值”的系统论文结构

## 开始前先读

1. `README.md`
2. `CHANGELOG.md`
3. `paper/kv_materialization_control/kv_materialization_control.tex`
4. `src/vllm_kv_materialization/policy.py`
5. `src/vllm_kv_materialization/live_control.py`
6. `src/vllm_kv_materialization/offline_experiment.py`
7. `paper/kv_materialization_control/experiments/run_offline_study.py`
8. `paper/kv_materialization_control/experiments/run_openai_workloads.py`
