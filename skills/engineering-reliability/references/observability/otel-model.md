# OpenTelemetry 与信号模型

## 核心信号

核心信号：Metrics、Traces、Logs；Profiles 作为可选性能诊断信号。

| 信号 | 用途 | 关联 |
| --- | --- | --- |
| Metrics | 趋势、SLO、告警、容量 | Resource 属性 / exemplars |
| Traces | 单次请求跨服务路径 | trace_id / span_id |
| Logs | 事件与诊断 | trace_id / span_id / Resource |
| Profiles（可选） | 性能热点 | 与 trace 关联采样 |

## Resource Identity

统一 Resource Identity 至少包含稳定的 `service.name`，并按需要使用 `service.namespace`、`service.version`、`deployment.environment.name`、`service.instance.id`。

| 属性 | 必填 | 说明 |
| --- | --- | --- |
| service.name | 必填 | 生产环境不能长期 unknown_service |
| service.namespace | 按需 | 团队/域 |
| service.version | 按需 | 定位发布回归 |
| deployment.environment.name | 按需 | prod/staging |
| service.instance.id | 按需 | 实例级定位 |

所有信号（Metrics/Traces/Logs）必须携带同一套 Resource Identity，否则无法跨信号关联。

## 信号关联

- Trace/Log 使用 `trace_id`、`span_id` 关联；
- Metrics 可通过相同 Resource 属性或 exemplars 与 Trace 关联；
- Log 必须携带 trace_id/span_id（如果上下文可用）；
- 异步任务显式传播上下文，保证跨边界可关联。

## Instrumentation

优先使用官方/维护中的 instrumentation 与 OpenTelemetry Semantic Conventions，再补业务手工埋点。

- 框架自带 instrumentation（HTTP/gRPC/DB/queue）优先；
- Semantic Conventions 统一属性名（http.route、db.system、messaging.system）；
- 业务手工埋点只补框架未覆盖的关键操作；
- 不重复埋点同一事件。

## 边界

日志字段、格式、轮转和保留由日志规范管理，本 Skill 只定义日志怎样参与跨信号关联（trace_id/span_id/Resource 属性）。
