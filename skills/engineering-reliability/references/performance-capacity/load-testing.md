# 负载测试

## 测试类型

### Load

验证目标负载下 latency、error、resource、queue、throughput。回答"目标负载下系统表现如何"。

### Stress

持续加压找到 saturation、首个 bottleneck、degradation point、failure mode 和 recovery。回答"系统何时崩溃、如何崩溃、能否恢复"。

### Spike

短时间突增验证 autoscaling、queue、cold start 和 load shedding。回答"瞬时峰值是否触发正确保护"。

### Soak

长时间运行发现 memory/file/connection leak、fragmentation、GC drift、周期性抖动和 backlog。回答"长期运行是否稳定"。

## 测试阶段

```text
warm-up → ramp-up → steady-state → ramp-down → recovery
```

- **warm-up**：让 JIT/缓存/连接池预热，跳过冷启动噪音。
- **ramp-up**：逐步增加负载，观察延迟拐点。
- **steady-state**：维持目标负载，观察稳定期指标。
- **ramp-down**：逐步减少，观察恢复。
- **recovery**：停止后验证资源释放和 backlog 排空。

## 环境可重复性

记录硬件、container request/limit、replicas、DB size、cache、网络、版本和配置，否则结果不可比较。

必须记录：

- 测试环境拓扑（与生产差异）；
- 数据规模与分布；
- 版本（应用/依赖/DB/OS）；
- 配置（线程池/连接池/缓存/GC）；
- 副本数与资源配额；
- 网络与位置。

## 与容量模型联动

- Load Test 输出 = 容量模型的输入（work units/s per instance、Saturation Point）。
- 每次测试后更新 capacity-model.csv，不用旧数据。
- 定期重测，因为代码、数据、依赖和硬件都会让旧结论失效。

## 结果分析

- 记录 Saturation Point（首个资源饱和的负载值）；
- 记录 Failure Mode（崩溃方式：OOM/线程耗尽/超时/拒绝）；
- 记录 Recovery（停止负载后多久恢复、积压是否排空）；
- 结果用于容量规划（Headroom、扩缩触发点）。

## 测试数据

- 请求成本分布接近生产（含 cache hit/miss、大小分布、复杂/简单混合）。
- 包含异常输入（超大、损坏、恶意）以触发最坏路径。
- 不在生产直接做高压测试，除非有隔离环境且验证过 blast radius。
