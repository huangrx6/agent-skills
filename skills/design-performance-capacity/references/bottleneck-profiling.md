# 瓶颈分析与 Profiling

## 先找最先饱和的资源

候选资源：CPU、memory/GC、disk IO、network、thread/event-loop、connection pool、DB、queue、GPU。

方法：

1. 加压直到 Saturation Point。
2. 观察哪个资源先到 100%（或明显排队）。
3. 只针对该资源深入，不要同时调多个。

## 瓶颈必须关联请求

性能瓶颈必须关联具体请求/Span/Profile，而不是只看机器总体 CPU。

- 用 trace 找到慢请求的 Span；
- 用 profile 定位该 Span 内的热点函数；
- 用 DB plan 看慢查询执行计划；
- 用网络 trace 看跨服务延迟。

## 排队与非线性的警告

接近饱和后 Queueing 会导致延迟非线性上升；CPU 80% 不等价于还能线性增加 20% 流量。

- 延迟开始拐弯 = 接近饱和；
- 不要用"还有 20% CPU 空闲"判断还能加负载。

## 工具

- CPU profile（on-cpu 热点）；
- allocation/heap profile（GC/内存压力）；
- lock/wait profile（线程竞争）；
- flame graph（调用链聚合）；
- DB explain/analyze（执行计划）；
- network trace（跨服务/IO 延迟）；
- event loop lag（异步框架）。

## 一次只改一个变量

一次实验主要只改变一个变量，例如 batch 16→32；不要同时改 batch、thread、cache、JVM 和 DB。

如果同时改多个变量，无法归因是哪个改动带来的提升或退化。

## 优化顺序

优先减少无效工作、IO/网络次数、算法复杂度，再考虑 batch/concurrency/cache 和微优化。

1. 减少无效工作（重复计算、无用请求）；
2. 减少 IO/网络次数（批处理、连接复用）；
3. 降低算法复杂度（N+1 → join、O(n²) → O(n log n)）；
4. 增加 batch/concurrency（利用并行）；
5. 加缓存（最后，且要评估一致性成本）；
6. 微优化（避免过早优化）。

## 典型瓶颈特征

| 瓶颈 | 特征 |
| --- | --- |
| CPU 饱和 | CPU 100%，延迟随排队上升，吞吐到顶 |
| 内存/GC | GC 时间占比高，heap 增长，full GC 停顿 |
| DB | 连接池耗尽、慢查询、锁等待、索引缺失 |
| 线程/连接池 | pool exhausted 异常、等待获取连接 |
| 网络 | 带宽满、TCP 重传、跨服务延迟 |
| 队列 | depth 增长、oldest age 增加 |
| GPU | utilization 高、显存不足、kernel 等待 |
