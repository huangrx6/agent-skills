# NovaPay 文档处理平台性能与容量示范

> 场景：文档解析服务（native text / OCR / VLM / full-page 多路由），GPU worker 集群。

## 1. 性能目标（量化场景）

| 操作 | 场景 | P95 | P99 | 吞吐 | 错误率 |
| --- | --- | --- | --- | --- | --- |
| 文档解析（中位 20 页） | 在线 | ≤ 1500ms | ≤ 3000ms | 20 docs/s | < 0.5% |
| VLM 图片分析（1080p） | 在线 | ≤ 1500ms | ≤ 3000ms | 50 img/s | < 1% |
| 离线批量解析 | 离线 | 不约束 | 不约束 | 最大吞吐 | < 1% |

## 2. Work Unit 模型（归一化）

| 路由 | 成本（unit） | 流量占比 | 加权 |
| --- | --- | --- | --- |
| native text | 0.2 | 60% | 0.12 |
| OCR | 1.0（基准） | 30% | 0.30 |
| VLM image | 4.0 | 5% | 0.20 |
| full-page | 8.0 | 5% | 0.40 |
| **平均请求成本** | | | **1.02 units/request** |

容量评估用 1.02 units/request，不是裸 requests/s。

## 3. 性能预算分解（端到端 SLO = 3000ms）

| 阶段 | 预算 | 实测 P99 | 状态 |
| --- | --- | --- | --- |
| upload | 200ms | 180ms | ✓ |
| parse | 500ms | 620ms | ✗ 超支（优化方向） |
| OCR | 800ms | 750ms | ✓ |
| VLM | 1000ms | 980ms | ✓ |
| merge+index+response | 500ms | 480ms | ✓ |
| 总 | 3000ms | 3010ms | ✗ |

parse 阶段超支是首个优化对象（一次只改一个变量）。

## 4. 负载测试计划

| 场景 | 类型 | 时长 | 负载 | 目标 | 停止条件 |
| --- | --- | --- | --- | --- | --- |
| 稳态 | LOAD | 30m | production_mix | 目标峰值 | 错误率 > 2% |
| 峰值 2x | SPIKE | 10m | production_mix | 2x 峰值 | 关键错误 |
| 找饱和 | STRESS | until_limit | production_mix | 逐步加压 | 服务不稳定 |
| 内存泄漏 | SOAK | 8h | production_mix | 0.7x 峰值 | 内存增长超预算 |

## 5. 瓶颈定位（示例）

STRESS 测试结果：

- 首个饱和资源：GPU（utilization 92% 时 VLM 延迟拐弯）；
- 次级瓶颈：parse 阶段 CPU（GC 占 18% 时间）；
- 结论：VLM worker 先饱和 → 需加 GPU worker；parse 需减少 GC 压力。

## 6. 容量模型

| 组件 | workUnit | 单实例容量 | 限制资源 | 安全利用率 | headroom |
| --- | --- | --- | --- | --- | --- |
| parser | pages/s | 120 | CPU | 70% | 30% |
| vlm-worker | images/s | 8 | GPU | 80% | 20% |

- 正常状态 ≤ safeUtilization；
- 单 AZ 故障后仍满足关键流量（利用率跳升不崩溃）。

## 7. Forecast 与扩缩容

- 增长：月均 +15%（7/30/90 天趋势）；
- 触发点 = 预计到达 safeUtilization 的时间 - 扩容 lead time（如 15min）；
- 指标：GPU utilization + queue age（与真正瓶颈相关）；
- 冷启动：新 worker 就绪需 3min，纳入 lead time。

## 8. 回归门禁

- 每次性能相关变更跑同环境 Benchmark；
- 与 Baseline 比较（P95/P99/吞吐），不静默重置基线；
- 超预算（如 P99 恶化 > 10%）阻止合并。
