---
name: engineering-reliability
description: "用户说\"服务挂了 / 报错 / 超时 / 想加重试 / 想加熔断 / 想加限流 / 想做故障注入 / 想加监控告警 / 想加 SLO 或 SLI / 想看日志 / 想做日志规范 / 想做性能压测 / 想做容量规划 / 想排查慢请求\"时激活。覆盖异常分类与错误码、服务韧性、可观测性、日志规范、性能与容量。不要用它做：架构选型或 API 契约 → engineering-architecture；安全威胁建模或代码评审 → engineering-security；代码风格与 lint → engineering-quality。"
---

# ![engineering-reliability](assets/icons/engineering-reliability-light.svg#gh-light-mode-only) ![engineering-reliability](assets/icons/engineering-reliability-dark.svg#gh-dark-mode-only) 工程可靠性

## 目标

让系统在依赖变慢、局部失败、流量突增和资源耗尽时仍能给出可预测的服务，并且能快速判断发生了什么。

## 职责边界

本 skill 负责"运行时的可靠性与可观测性"：

- 失败分类、异常传播、错误码注册表、统一 API 错误响应、全局异常处理器；
- 重试、幂等、超时预算、熔断、舱壁、限流、降级、背压；
- OpenTelemetry metrics/traces/logs、SLI/SLO、Dashboard、告警；
- 日志级别、JSON Lines 结构化字段、滚动/压缩/保留、敏感数据脱敏；
- 性能目标、负载模型、压测、瓶颈定位、容量规划。

不负责：模块边界、API 契约、数据库设计、代码风格、密钥管理。

## 何时使用（用户原话触发）

| 用户说 | 进入本 skill 哪个子主题 |
| --- | --- |
| 错误码体系、统一错误响应、失败分类 | exception-handling |
| 重试、熔断、限流、降级、故障注入 | resilience |
| SLO、SLI、OpenTelemetry、告警 | observability |
| 日志格式、滚动保留、脱敏 | logging |
| 性能压测、容量规划、慢 SQL、Profile | performance-capacity |

## 何时不要使用（路由到其它 skill）

| 用户说 | 跳到 |
| --- | --- |
| 画架构图、模块边界、技术选型 | engineering-architecture |
| API 契约风格、Schema、版本、错误响应（协议层） | engineering-architecture |
| 数据库表设计、迁移、索引 | engineering-architecture |
| SQL 注入、密钥、认证授权、SSRF | engineering-security |
| 代码风格、命名、lint、配置中心 | engineering-quality |

## 工作流

1. 先定义用户关键旅程和 SLI/SLO，再设计 trace/metric/log，不要先选工具。
2. 失败按 `INPUT/BUSINESS/AUTH/CONFLICT/RATE_LIMIT/DEPENDENCY/SYSTEM` 分类，再分配错误码。
3. 入口边界（HTTP/gRPC/消息）一处异常出口；中间层只补充上下文。
4. 重试、超时、熔断按依赖分别定责任和上限，避免放大流量。
5. 日志只在承担责任的边界记录一次；统一结构化字段；敏感数据按策略脱敏。
6. 性能目标 → 负载模型 → 基准 → 加压找瓶颈 → 改 → 复测。

## 核心原则

- 失败语义稳定（错误码、HTTP 状态、可重试性）。
- 重试责任由依赖方承担，调用方只对幂等请求重试。
- 重试必须有上限、有抖动、有 Retry-After，不放大级联故障。
- 日志不重复记录同一异常；message 不承担机器契约。
- 性能容量是预测与实验问题，不是默认参数问题。

## 子主题与资源入口

- **exception-handling**：`references/exception-handling/` + `assets/exception-handling/` + `scripts/exception-handling/`
- **resilience**：`references/resilience/` + `assets/resilience/` + `scripts/resilience/`
- **observability**：`references/observability/` + `assets/observability/` + `scripts/observability/`
- **logging**：`references/logging/` + `assets/logging/` + `scripts/logging/`
- **performance-capacity**：`references/performance-capacity/` + `assets/performance-capacity/` + `scripts/performance-capacity/`

完整示例见 `examples/<sub>/`。

## 环境与运行

脚本统一通过 `uv` 运行（PEP 723 / `# /// script` 声明，无第三方依赖）。

```bash
uv run scripts/<sub>/validate_*.py --<args>
uv run python -m unittest discover -s scripts/tests
```

uv 缓存全局共享（`~/.cache/uv`），不会在每个 skill 目录创建 .venv。
