---
name: design-service-resilience
description: "设计、评审和完善生产级服务韧性方案，包括端到端超时预算、重试责任、指数退避与抖动、重试预算、熔断、舱壁隔离、限流、负载削减、背压、队列容量、降级、缓存兜底、异步任务恢复、健康检查和故障注入。用于微服务、分布式系统、异步任务和高并发服务。不覆盖错误分类与异常传播、架构边界和容量模型。"
---

# 服务韧性设计

## 目标

在依赖变慢、局部失败、流量突增和资源耗尽时，阻止局部问题被同步调用、重试和排队放大成级联故障，并保证核心流量获得可预测的服务。

## 工作流

1. 识别关键请求路径、依赖和共享资源池。
2. 从入口 Deadline 向下分配 Timeout Budget。
3. 为每个依赖定义重试责任、幂等条件、并发上限和降级策略。
4. 判断是否需要 Circuit Breaker、Bulkhead、Rate Limit、Load Shedding、Queue/Backpressure。
5. 为异步任务定义重复、乱序、DLQ、积压和恢复。
6. 用故障注入和超载测试验证保护机制。

## 核心规则

- 所有远程调用必须有明确 Timeout/Deadline；不能依赖无限默认等待。
- 只对瞬态、可恢复且幂等安全的失败重试。
- 一个失败只允许一个明确层负责重试，禁止多层叠加重试。
- 重试必须有 attempt、总时长、指数退避、jitter 和 retry budget。
- 过载时服务应在资源耗尽前快速拒绝、削减或降级。
- Rate Limit 负责公平与配额；Load Shedding 负责保护实例活性。
- 队列必须有容量和等待时间上限，不能无限堆积。
- Bulkhead 用于隔离线程池、连接池、租户或依赖，避免资源被单点耗尽。
- Circuit Breaker 不能替代 Timeout；Half-open 探测必须有界。
- 降级必须显式说明完整度、陈旧度和恢复条件。
- readiness 表示能否接流量；liveness 不用于处理普通依赖短暂故障。
- 异步消费者必须幂等，并支持 poison message、DLQ 和安全重放。
- 所有保护策略必须经过超载/故障测试证明。

## 职责边界

本 Skill 负责：

- 端到端超时预算、重试调度、退避抖动与重试预算；
- 过载保护、背压、限流、负载削减；
- 舱壁隔离、熔断、降级；
- 异步消费者韧性、DLQ、积压恢复；
- 健康检查与就绪/存活探针；
- 韧性测试与故障注入。

本 Skill 不负责：

- 错误分类、异常传播、错误码体系与全局异常处理；
- 架构边界、服务拆分与威胁模型；
- 容量模型、容量预测与扩缩容指标；
- API 幂等键契约设计；
- 安全编码、输入验证与依赖安全；
- 文档体系与知识沉淀。

注：HTTP 重试的幂等键契约属 API 层；本 Skill 只负责重试在超时预算内的调度与降级。异步消费者的幂等消费属错误处理层；本 Skill 负责消费者在背压、积压与 poison message 下的资源保护。

## 参考文件选择

- 处理超时、Deadline、重试、避让、退避与抖动、重试预算、重试责任时，读取 [references/timeout-retry.md](references/timeout-retry.md)。
- 处理过载、背压、限流、负载削减、舱壁隔离、熔断与降级时，读取 [references/overload-isolation.md](references/overload-isolation.md)。
- 处理异步任务、消息消费者、批处理与幂等恢复时，读取 [references/async-resilience.md](references/async-resilience.md)。
- 处理健康检查、readiness/liveness 探针、依赖健康与启动就绪时，读取 [references/health-readiness.md](references/health-readiness.md)。
- 处理韧性指标、告警、降级可观测与运行手册时，读取 [references/observability-runbooks.md](references/observability-runbooks.md)。
- 设计韧性测试、超载实验与故障注入时，读取 [references/resilience-testing.md](references/resilience-testing.md)。
- 了解 AWS Builders、Google SRE、Azure Patterns 等权威来源时，读取 [references/standards-sources.md](references/standards-sources.md)。

## 输出结构

完整规范优先采用：

1. 关键路径与依赖识别；
2. 超时与重试预算；
3. 过载与背压策略；
4. 隔离、熔断与降级；
5. 健康检查与就绪/存活探针；
6. 异步任务韧性；
7. 测试与故障注入；
8. 监控、告警与运行手册；
9. 与架构/异常/安全 Skill 的边界。

使用“必须、应、可”表达约束强度。不要把工程经验表述为适用于所有平台的官方规则；具体 Timeout/Retry/Limit 数值必须由服务的负载和故障实验决定，不应直接复制默认。

## 内置资源

- `assets/resilience-control-catalog.csv`：控制目录（超时/重试/过载/背压/异步 5 类最低要求）。
- `assets/dependency-resilience-policy.csv`：依赖韧性策略（关键性/超时/重试/限流/降级）。
- `assets/resilience-review-checklist.csv`：韧性评审清单。
- `assets/failure-injection-plan.template.md`：故障注入计划模板。
- `examples/README.md` 与 `examples/resilience-design.example.md`：虚构项目韧性产出样例。
- `scripts/validate_resilience.py`：校验上述资产与模板。

修改资产后运行：

```bash
uv run scripts/validate_resilience.py --assets assets/
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
uv run scripts/validate_resilience.py --assets assets/
uv run python -m unittest discover -s scripts/tests   # 跑测试
```

