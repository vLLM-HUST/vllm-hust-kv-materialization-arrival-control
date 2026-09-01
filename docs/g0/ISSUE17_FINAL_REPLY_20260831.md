# G0 formal result: Stop, with disclosed carrier correction

@ShuhaoZhangTony G0 的性能运行已按第一个 Stop 条件停止；未实现自适应 release 机制，也未继续挑 workload。关闭 Issue 前，请同时确认下面的 carrier 治理纠正。

## Carrier 治理纠正

首次获批回复把 `vendor/vllm@68b8be04493d39d5706f3d0d18f465f5eab947c4` 写成唯一 runtime carrier。calibration 后发现物化专属 activation/cost 信号位于 AscendStore layerwise 路径，正式序列 1–63 实际执行的是：

- vLLM `0fc695fc6d1d82e9a5ac6835ac8e4e1c83703665`；
- vLLM-Ascend base `f4a08bddd0cc65a0bd8c3d377b158ae5ca7527db` 加只读 G0 源码快照；
- profiling base `9be6a32b9e64e06c7a60def100452abf127850bb` 加只读 G0 源码快照；
- DeepSeek-V2-Lite bf16、TP1、eager、physical NPU 2。

单个 run 内没有混用两套 runtime，也没有复用 WaveMat graph 结论，但“未先更新获批 Issue 回复就替换 carrier”属于治理偏差。原始 run 不做改写；机器可读的 `posthoc_correction=true` sidecar 已纳入新 custody。以下 Stop 结论只适用于实际执行的 AscendStore carrier，不外推到未执行的 vendored carrier。请 Owner 明确确认是否接受该纠正作为本 Issue 的最终 carrier identity。

## Formal verdict

`Stop`，报告状态 `complete_early_stop`。连续 canonical 序列 1–63 共 63 个有效 run、4,032 个成功请求；每个有效 run 都是 64/64 HTTP 200、固定 8 output tokens、correctness 100%，跨 arm/重复的逐请求输出 SHA-256 一致。两个 HTTP 失败尝试单独保存在 rejected custody 中，不参与统计。

| Cell | no-control 相对 oracle 的 p95 TTFT 回退（三次） | 中位数及 paired-lifecycle bootstrap 95% CI | materialization counter gate | 普通限流等价 |
|---|---:|---:|---:|---:|
| BurstGPT / moderate | 14.95%, 24.05%, 23.90% | 23.90% [14.95%, 24.05%] | pass | no |
| BurstGPT / high | 20.49%, 39.58%, 25.36% | 25.36% [20.49%, 39.58%] | pass | no |
| ServeGen / moderate | 8.47%, 17.84%, 2.18% | 8.47% [2.18%, 17.84%] | pass | **yes** |

bootstrap 以独立 server lifecycle 为重采样单位，穷举 `3^3=27` 个有放回样本；没有把同一 lifecycle 内 64 个请求当成独立重复。它是 2026-09-01 对首次回复中 CI 承诺的报告层补全，不改变任何 run、point estimate、阈值或 Stop trigger。

ServeGen/moderate 只有 1/3 重复达到 10%，命中“病理不能跨重复稳定复现”。同一 cell 中，普通 request token bucket 的中位 p95 改善为 7.18%，paced oracle 为 7.81%；token bucket goodput 损失为 22.67%，oracle 为 23.41%。按报告冻结的 1 个百分点等价容差，普通限流达到同等效果，形成第二个 Stop trigger。即使不采用该等价容差，第一个 repeatability Stop 也独立成立。

物化计数本身有效且方向一致。例如 ServeGen/moderate 三次 no-control peak bytes-in-flight 为 7.52–7.67 MB，oracle 为 0.885 MB；no-control layer-ready wait p95 为 2.18–2.24 ms，oracle 为 0.96–0.98 ms。byte pacing 的确削平物化波峰，但没有形成稳定的 >=10% TTFT 尾延迟收益，也没有优于通用 token bucket。

因此序列 64–96 和 capacity-frontier 序列 97–132 均按 fail-fast Stop 不再执行。正式低并发 control 和第四个主 cell 是 Go 所需证据；任一 Stop 已成立后继续运行只会形成事后 workload 选择。

## 可重建交付

- 正式 JSON/Markdown、pathology CSV/SVG 由 `make g0-formal-rebuild` 从真实 run tree 重建；
- raw manifest 覆盖 frozen suite、63 个 canonical runs、2 个 rejected attempts 和报告；
- 主仓证据 Draft PR：<https://github.com/intellistream/kv-materialization-arrival-control/pull/21>；
- profiling runner Draft PR：<https://github.com/vLLM-HUST/vllm-hust-profiling/pull/3>；
- AscendStore telemetry Draft PR：<https://github.com/vllm-project/vllm-ascend/pull/15468>；
- GitHub Release：<https://github.com/intellistream/kv-materialization-arrival-control/releases/tag/g0-issue17-stop-20260901-v2>；
- raw archive asset ID `539131048`，size `16,033,682` bytes，SHA-256 `6474d718f65aeee3824e25897934922672c2a51e92f6c218be6f5b16a7f0ad4a`；
- raw manifest SHA-256 `7847e2cbfd12858e09bc0ade41e55dc31219110f33f223e156428ee17781a2a4`，覆盖 8 个 suite 文件、1,260 个 canonical-run 文件、28 个 rejected 文件和 4 个报告文件；
- custody、manifest、正式报告和 pathology CSV/SVG 均作为独立 Release assets 上传，GitHub 返回的 asset digest 与本地 SHA-256 一致；
- G0 定向测试当前为 15 passed。

请求 Owner 确认两点：

1. 接受上述实际执行 carrier 的治理纠正；
2. 接受 `Stop`，关闭本方向，不另开 wave-shaping 机制 Issue，不扩展动作空间，并把结果归入通用 scheduling/admission-control 边界。
