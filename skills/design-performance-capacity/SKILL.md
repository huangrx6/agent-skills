---
name: design-performance-capacity
description: "设计、评审和验证生产级性能与容量方案，包括性能目标、工作负载模型、吞吐/并发/尾延迟、性能预算、基准测试、负载/压力/峰值/浸泡测试、瓶颈分析、CPU/内存/GC/IO/网络/数据库/队列、Profiling、容量模型、资源单位、Headroom、自动扩缩、容量预测、性能回归和成本效率。用于性能优化、上线容量评估、大促准备和 AI/OCR/VLM/复杂文档等重计算服务。服务过载保护参考独立规范；运行指标参考独立规范。"
---

# 性能与容量设计

## 目标

用可重复实验回答：系统稳定能处理多少工作、在什么 P95/P99 下、首个瓶颈是什么、故障时剩多少容量、未来多久会触顶。

## 工作流

1. 定义性能目标与关键用户场景。
2. 建立真实 Workload Model，不只写 QPS。
3. 建立可重复 Benchmark Baseline。
4. 增加负载直到找到第一个 Saturation Point。
5. 用 Profile/Trace/Query Plan 定位瓶颈。
6. 一次只改一个主要变量后重新测试。
7. 执行 Load、Stress、Spike、Soak。
8. 建立资源→吞吐/延迟模型和 Headroom。
9. 结合增长、故障和扩容 Lead Time 做 Capacity Forecast。
10. 把稳定性能预算加入回归门禁。

## 核心规则

- 性能要求必须量化场景、P95/P99、吞吐、并发、数据规模和时间窗口。
- 平均延迟不能代替尾延迟。
- QPS 不是通用容量单位；请求成本差异大时按 CPU time、pages、bytes、tokens、documents、DB work 等建模。
- 测试数据分布、缓存命中、并发模式和依赖行为要接近生产。
- Load Test 明确 warm-up、ramp、steady state、stop condition。
- 必须找到 Saturation Point 与 Failure Mode，不只证明“目标 QPS 能跑”。
- 同时记录 CPU、memory、GC、disk/network、pool、queue、DB、GPU 等资源。
- 优化前先 Profile；不要凭感觉调线程、缓存和 batch。
- 连接池、线程池、batch、queue 更大不等于更快。
- Soak 用于发现 leak、fragmentation、GC drift、连接泄漏和积压。
- Capacity Plan 包含增长、发布变化、故障余量和扩容 Lead Time。
- N+1/AZ 故障后仍要满足关键流量，正常状态不能把所有容量跑满。
- Autoscaling 要考虑冷启动、扩容延迟、指标滞后和下游瓶颈。
- Performance Regression 必须与同环境 Baseline 比较，禁止静默重置基线。
- 优化不能破坏正确性、安全性和可维护性。

## 职责边界

本 Skill 负责：

- 性能目标、工作负载模型与归一化 Work Unit；
- 端到端 Performance Budget 分解；
- Load/Stress/Spike/Soak 负载测试方法论；
- 瓶颈分析、Profiling 与优化顺序；
- 容量模型、Headroom 与扩缩容触发；
- AI/OCR/VLM 等重计算服务的容量建模。

本 Skill 不负责：

- 服务过载保护、限流、降级与熔断：不属本 Skill 范围；
- 运行指标、告警与可观测性体系：不属本 Skill 范围；
- 日志格式与生命周期：不属本 Skill 范围。

注：性能是容量建模的输入，但过载时的保护机制（限流/降级/熔断）属韧性层；运行期指标采集属可观测性层。本 Skill 只负责“测量、建模、定位与规划”。

## 参考文件选择

- 处理性能指标、Work Unit、预算分解与测试数据分布时，读取 [references/performance-model.md](references/performance-model.md)。
- 设计 Load/Stress/Spike/Soak 测试与结果分析时，读取 [references/load-testing.md](references/load-testing.md)。
- 定位瓶颈、Profiling 与优化顺序时，读取 [references/bottleneck-profiling.md](references/bottleneck-profiling.md)。
- 建立容量模型、Headroom、Forecast 与扩缩容触发时，读取 [references/capacity-planning.md](references/capacity-planning.md)。
- 处理 AI/OCR/VLM/复杂文档工作负载时，读取 [references/ai-document-workloads.md](references/ai-document-workloads.md)。
- 了解 Google SRE、AWS、Netflix 等权威来源时，读取 [references/standards-sources.md](references/standards-sources.md)。

## 输出结构

完整规范优先采用：

1. 性能目标与关键场景；
2. 工作负载模型与 Work Unit；
3. 性能预算分解；
4. 负载测试计划（Load/Stress/Spike/Soak）；
5. 瓶颈分析与 Profiling 方法；
6. 容量模型与 Headroom；
7. 扩缩容与 Forecast；
8. AI/OCR 等特殊负载附录；
9. 回归门禁与基线管理。

使用“必须、应、可”表达约束强度。性能参数没有跨系统统一最佳值，必须以本系统真实负载和实验为事实来源，不直接复制默认值。

## 内置资源

- `assets/performance-budget.csv`：性能预算（P50/P95/P99/吞吐/错误率）。
- `assets/load-test-scenarios.csv`：负载测试场景（LOAD/STRESS/SPIKE/SOAK）。
- `assets/capacity-model.csv`：容量模型（workUnit/capacity/limitingResource/headroom）。
- `assets/performance-review-checklist.csv`：性能评审清单。
- `assets/performance-experiment.template.md`：性能实验模板。
- `examples/` 目录：虚构项目性能与容量产出样例。
- `scripts/validate_performance_capacity.py`：校验上述资产与模板。

修改资产后运行：

```bash
uv run scripts/validate_performance_capacity.py --assets assets/
```

## 环境与运行

本 Skill 脚本统一通过 **uv** 运行（不使用宿主机的原始 Python，避免环境污染）。

- 所有脚本均为纯标准库，无需安装任何第三方包；uv 仅用于隔离 Python 解释器。
- uv 使用全局缓存（`~/.cache/uv`），**不会在每个 skill 目录创建 .venv**；Python 解释器与依赖在所有 skill 间共享，不重复下载。
- 固定路径约定：
  - uv 二进制：`~/.local/bin/uv`
  - 依赖与 Python 缓存：`~/.cache/uv`（全局共享）
  - Python 解释器：`~/.local/share/uv/python/`
  - 脚本：各 skill 的 `scripts/` 目录

首次使用前确保 uv 可用（不可用则自动安装，无需用户操作）：

```bash
python scripts/ensure_uv.py
# 或手动：curl -LsSf https://astral.sh/uv/install.sh | sh
```

统一运行方式：

```bash
uv run scripts/validate_performance_capacity.py --assets assets/
uv run python -m unittest discover -s scripts/tests   # 跑测试
```

