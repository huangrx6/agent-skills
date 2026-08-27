# 权威来源

## 官方工程指导

- AWS Builders' Library — Timeouts, retries and backoff with jitter
  <https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/>

- AWS Architecture Blog — Exponential Backoff And Jitter
  <https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/>

- Google SRE Book — Handling Overload
  <https://sre.google/sre-book/handling-overload/>

- Google SRE Book — Addressing Cascading Failures
  <https://sre.google/sre-book/addressing-cascading-failures/>

- Azure Architecture Center — Cloud Design Patterns
  <https://learn.microsoft.com/azure/architecture/patterns/>

- Netflix Tech Blog — Fault Tolerance in a High Volume, Distributed System
  <https://netflixtechblog.com/fault-tolerance-in-a-high-volume-distributed-system-91abfb1fea24>

- Martin Fowler — Circuit Breaker
  <https://martinfowler.com/bliki/CircuitBreaker.html>

## 适用主题映射

| 主题 | 权威来源 |
| --- | --- |
| 超时/重试/退避/jitter | AWS Builders' Library（官方标准实践） |
| 过载处理 | Google SRE "Handling Overload" |
| 级联失败 | Google SRE "Addressing Cascading Failures" |
| 熔断/舱壁/重试模式 | Azure Cloud Design Patterns、Martin Fowler |
| 生产韧性 | Netflix Tech Blog（故障注入经验） |

## 使用原则

- 这些是工程指导，不是协议标准。具体 Timeout、Retry、Limit 和容量数值必须由服务负载和故障实验决定。
- 不直接复制 AWS/Google 的默认参数；它们给出的是模式和权衡，不是配置模板。
- 区分"官方推荐"（AWS Builders 超时/退避）vs"经验分享"（Netflix 故障注入）vs"组织决策"（本服务预算）。
- 涉及协议要求（如 HTTP Retry-After 语义）时，以协议标准（RFC 9110 等）为准，不把工程建议当协议要求。
- 数值随负载和版本变化，应通过韧性测试验证后固化，不写入 skill 作为静态默认。

## 边界

本 Skill 的权威来源聚焦韧性机制。错误处理与错误码标准见异常 Skill 的 standards-sources；容量模型见容量 Skill；架构模式见架构 Skill。
