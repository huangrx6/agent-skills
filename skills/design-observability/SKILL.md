---
name: design-observability
description: "设计、评审和完善生产级可观测性体系，包括服务与资源身份、OpenTelemetry traces/metrics/log correlation、上下文传播、指标与基数治理、SLI/SLO、Golden Signals、分布式追踪、采样、Dashboard、告警、黑盒/白盒监控、Telemetry Pipeline 和成本控制。用于新服务可观测性设计、现有监控重构和告警降噪。日志格式与生命周期参考独立规范；韧性参考独立规范；性能容量参考独立规范。"
---

# 可观测性设计

## 目标

让工程师无需临时加日志或改代码，就能判断系统是否正常、谁受影响、哪一层失败、与哪个版本/配置/依赖相关。

## 工作流

1. 从用户关键旅程定义 SLI/SLO。
2. 统一 Service/Resource Identity。
3. 为入口、依赖和异步边界设计 Trace。
4. 设计 RED/USE/业务 Metrics，并控制 Cardinality。
5. 将日志与 Trace/Resource 关联。
6. 设计 Dashboard、Alert、Sampling 和 Telemetry Budget。
7. 通过故障演练验证信号能解释真实问题。

## 核心规则

- Metrics、Traces、Logs 使用统一 Resource Identity。
- 明确设置 `service.name`，生产环境不能长期使用 `unknown_service`。
- Trace Context 跨 HTTP/gRPC/消息/异步任务传播。
- Metric label 必须有界；user_id、order_id、request_id、raw URL 等高基数字段通常进入 Trace/Log。
- SLI 从用户可见行为定义，不用 Pod Running 代替用户成功率。
- Alert 只针对需要人行动的问题；优先 SLO burn、用户影响和容量风险。
- Dashboard 按排障问题组织，不按“指标数量”组织。
- Span 记录真正跨边界或重要操作，不为每个 helper 建 Span。
- Sampling 策略必须能保留错误、慢请求等高价值 Trace。
- Telemetry Pipeline 自身有队列、丢弃计数、健康指标和成本预算。
- Profiles 可作为性能诊断补充；OpenTelemetry Profiles 当前仍为 Alpha，不作为基础必选能力。
- 可观测性必须通过故障演练证明，而不是只看图表是否存在。

## 职责边界

本 Skill 负责：

- SLI/SLO 定义与 error-budget burn 告警；
- 统一 Service/Resource Identity 与跨信号关联；
- Trace 设计、上下文传播与采样；
- Metric 设计与基数治理；
- Dashboard 组织与告警分级；
- Telemetry 预算、Pipeline 与成本控制。

本 Skill 不负责：

- 日志字段、格式、轮转与保留：不属本 Skill 范围；
- 服务过载保护、限流与降级：不属本 Skill 范围；
- 性能测量、容量建模与扩缩容：不属本 Skill 范围。

注：本 Skill 只定义日志怎样参与跨信号关联（trace_id/span_id/Resource），不定义日志内容本身；可观测性是性能测量的基础，但容量建模与保护机制属其他层。

## 参考文件选择

- 处理 OpenTelemetry 信号模型、Resource Identity 与 instrumentation 时，读取 [references/otel-model.md](references/otel-model.md)。
- 处理 Golden Signals、SLI/SLO、延迟与基数治理时，读取 [references/metrics-sli-slo.md](references/metrics-sli-slo.md)。
- 设计 Span、上下文传播、采样、Dashboard 与告警时，读取 [references/tracing-alerting.md](references/tracing-alerting.md)。
- 管理 telemetry 预算、Pipeline、基数与敏感数据时，读取 [references/telemetry-governance.md](references/telemetry-governance.md)。
- 了解 OpenTelemetry、Google SRE、Prometheus 等权威来源时，读取 [references/standards-sources.md](references/standards-sources.md)。

## 输出结构

完整规范优先采用：

1. 服务与资源身份；
2. SLI/SLO 与 error budget；
3. 信号目录（Metrics/Traces/Logs/Profiles）；
4. Trace 设计与上下文传播；
5. Metric 设计与基数治理；
6. Dashboard 组织；
7. 告警分级与 burn 告警；
8. Telemetry 预算与 Pipeline；
9. 敏感数据与验证。

使用“必须、应、可”表达约束强度。指标和告警阈值必须以本系统真实信号和故障演练为事实来源，不直接复制默认值。

## 内置资源

- `assets/telemetry-signal-catalog.csv`：信号目录（含 cardinalityPolicy）。
- `assets/sli-catalog.csv`：SLI 目录（numerator/denominator/window/target）。
- `assets/alert-policy.csv`：告警策略（severity/action/runbook）。
- `assets/observability-review-checklist.csv`：可观测性评审清单。
- `examples/` 目录：虚构项目可观测性产出样例。
- `scripts/validate_observability.py`：校验上述资产。

修改资产后运行：

```bash
uv run scripts/validate_observability.py --assets assets/
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
uv run scripts/validate_observability.py --assets assets/
uv run python -m unittest discover -s scripts/tests   # 跑测试
```

