# 容量规划

## 容量模型

容量模型建议记录：work units/sec per instance、CPU/work unit、memory baseline + per in-flight、DB work、network bytes、queue service rate。

示例（容量模型表）：

```text
component    workUnit   capacityPerInstance   limitingResource   safeUtilization
parser       pages/s    120                   CPU                70%
vlm-worker   images/s   8                     GPU                80%
```

- `capacityPerInstance`：单实例稳定容量（来自 Load Test）；
- `safeUtilization`：正常状态允许达到的上限（保留余量）；
- 超过 safeUtilization 前应触发扩容。

## Capacity Plan 必须考虑

- traffic growth（增长趋势）；
- launch spike（发布峰值）；
- instance/AZ failure（故障余量）；
- maintenance（维护窗口）；
- dependency slowdown（依赖变慢）；
- autoscale lag（扩容延迟）。

## Headroom

Headroom 是有意保留的。需要承受一个 AZ 故障的系统不能在正常状态把所有 AZ 都跑满。

- 正常状态利用率 ≤ safeUtilization（如 70%）；
- 单 AZ 故障后仍能满足关键流量（利用率跳到 ~140% 也不崩溃）；
- Headroom = (1 - safeUtilization)，是故障缓冲，不是浪费。

## Forecast

Forecast 关注：

- current peak（当前峰值）；
- 7/30/90 day trend（趋势）；
- seasonality（季节性）；
- planned launch（计划发布）；
- data growth（数据增长）；
- performance regression（性能回归，会改变容量结论）。

方法：按增长率和 Lead Time 推算"何时到达安全上限"，而不是等快耗尽才发现。

## 扩缩触发点

扩容触发点应是"预测会在 provisioning lead time 之前达到安全上限"，而不是已经耗尽再扩。

```text
触发扩容时间 = 预计到达 safeUtilization 的时间 - provisioning lead time
```

- 指标用与真正瓶颈相关的（CPU/concurrency/queue age/custom work units）；
- 不用与瓶颈无关的指标（如 QPS 但瓶颈在 DB）。

## Autoscaling

Autoscaling 要考虑：

- 冷启动时间；
- 扩容延迟（provisioning 到可用）；
- 指标滞后（采集+决策+执行延迟）；
- 下游瓶颈（扩了但下游跟不上）；
- 缩容策略（避免抖动，稳定后再缩）。

## 定期重新 Load Test

代码、数据、依赖和硬件都会让旧容量结论失效。定期重测并更新容量模型，不沿用旧数据。
