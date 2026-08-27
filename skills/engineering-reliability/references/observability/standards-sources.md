# 权威来源

## 官方工程指导

- OpenTelemetry Docs / Specs
  <https://opentelemetry.io/docs/>
  <https://opentelemetry.io/docs/specs/>

- OpenTelemetry Semantic Conventions
  <https://opentelemetry.io/docs/specs/semconv/>

- OpenTelemetry Sampling
  <https://opentelemetry.io/docs/concepts/sampling/>

- Google SRE — Monitoring Distributed Systems
  <https://sre.google/sre-book/monitoring-distributed-systems/>

- Google SRE — Practical Alerting
  <https://sre.google/sre-book/practical-alerting/>

- Prometheus — Querying / Alerting
  <https://prometheus.io/docs/prometheus/latest/querying/basics/>
  <https://prometheus.io/docs/alerting/latest/overview/>

## 适用主题映射

| 主题 | 权威来源 |
| --- | --- |
| 信号模型/语义约定 | OpenTelemetry Docs / SemConv |
| 采样策略 | OpenTelemetry Sampling |
| 监控与 Golden Signals | Google SRE "Monitoring Distributed Systems" |
| 告警设计 | Google SRE "Practical Alerting" |
| 指标查询/告警规则 | Prometheus Docs |

## 使用原则

- OpenTelemetry 当前按信号独立管理稳定性；Profiles 目前仍为 Alpha，因此不是本 Skill 的强制基础能力。
- Semantic Conventions 是统一属性名的标准，优先遵循而不是自创命名。
- Google SRE 的 Golden Signals 和 practical alerting 是方法论参考，具体阈值和指标由本系统业务决定。
- 不把某一平台的默认告警配置当通用标准；以本系统真实信号和故障演练验证为准。
- 区分"标准"（OpenTelemetry 语义约定）vs"方法论"（SRE）vs"工具实现"（Prometheus）。
