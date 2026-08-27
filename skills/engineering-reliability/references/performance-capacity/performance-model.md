# 性能模型

## 关键指标

- Latency（P50/P95/P99）；
- Throughput；
- Concurrency；
- Error；
- Saturation。

平均延迟不能代替尾延迟。P99 反映最差用户的体验，也是排队和非线性退化的最早信号。

## Throughput 单位

Throughput 单位应匹配系统：requests/s、documents/min、pages/s、messages/s、tokens/s、MB/s、images/s。

不要把不同成本的请求混在同一 QPS 里。

## 归一化 Work Unit

复杂请求成本不同时，建立 normalized work unit，而不是把所有请求视为同一 QPS。

### 建模步骤

1. 识别请求的主要成本维度（CPU time、pages、bytes、tokens、documents、DB work、GPU work）。
2. 为每个维度定义基准成本（如"1 页 OCR = 1 work unit"）。
3. 把真实流量分布映射为 work unit 分布（路由比例加权）。
4. 用 work units/s 作为容量单位，而不是 requests/s。

示例（文档处理）：

```text
native text  = 0.2 unit
OCR          = 1.0 unit   (基准)
VLM image    = 4.0 units
full-page    = 8.0 units
```

若流量分布为 60% text + 30% OCR + 10% full-page，则平均请求成本：

```text
0.6×0.2 + 0.3×1.0 + 0.1×8.0 = 0.12 + 0.3 + 0.8 = 1.22 units/request
```

容量评估用 1.22 units/request × 目标吞吐，而不是用裸 requests/s。

## Performance Budget

端到端 Performance Budget 要分解到主要阶段，例如：upload → parse → OCR → VLM → merge → index → response。

### 分解方法

1. 总 SLO（如 P99 ≤ 3s）来自业务目标。
2. 按阶段分配预算，预留自身处理时间。
3. 每个阶段用可重复实验验证实际耗时 vs 预算。
4. 预算超支时定位是哪个阶段，而不是笼统调优。

### 预算表

| 阶段 | 预算 | 实测 P99 | 状态 |
| --- | --- | --- | --- |
| upload | 200ms | 180ms | ✓ |
| parse | 500ms | 620ms | ✗ 超支 |
| OCR | 800ms | 750ms | ✓ |
| VLM | 1000ms | 980ms | ✓ |
| merge+index+response | 500ms | 480ms | ✓ |
| 总 | 3000ms | 3010ms | ✗ 超支 |

## 测试数据分布

覆盖 small/median/large、simple/complex、cache hit/miss、hot/cold 和异常输入。

- 测试数据的请求成本分布要接近生产，否则结果不可比。
- 缓存命中率要按生产比例模拟（全命中会掩盖真实瓶颈，全 miss 会夸大）。
- 异常输入（超大、损坏、恶意）要包含，因为它们可能触发最坏路径。

## 延迟-吞吐关系

- 系统在 Saturation Point 前，延迟接近平坦；超过后排队导致延迟非线性上升。
- CPU 80% 不等价于还能线性增加 20% 流量。
- 通过逐步加压找到"延迟开始拐弯"的点，而不是只看某个 QPS 的延迟。
