# 权威来源

## 官方工程指导

- Google SRE — Handling Overload
  https://sre.google/sre-book/handling-overload/

- Google SRE — Addressing Cascading Failures
  https://sre.google/sre-book/addressing-cascading-failures/

- Google SRE — Production Services Best Practices
  https://sre.google/sre-book/service-best-practices/

- Google SRE — Data Processing Pipelines
  https://sre.google/sre-book/data-processing/

- AWS Builders' Library — Performance
  https://aws.amazon.com/builders-library/

- Netflix Tech Blog — Performance Engineering
  https://netflixtechblog.com/

## 适用主题映射

| 主题 | 权威来源 |
| --- | --- |
| 过载与容量 | Google SRE "Handling Overload" |
| 级联失败与余量 | Google SRE "Addressing Cascading Failures" |
| 服务最佳实践（SLO/监控） | Google SRE "Production Services Best Practices" |
| 批处理/流水线吞吐 | Google SRE "Data Processing Pipelines" |
| 负载测试/性能建模 | AWS Builders' Library |
| 大规模性能工程 | Netflix Tech Blog |

## 使用原则

- Google SRE 指出，不同请求资源成本差异较大时，单纯 QPS 往往是较差的容量指标；应通过真实 Load Test 重新建立资源与容量关系。
- 性能参数没有跨系统统一最佳值，当前硬件、版本、配置和生产 Telemetry 才是事实来源。
- 不直接复制他人默认参数；用本系统真实负载和实验验证后固化。
- 区分"官方推荐"（SRE 容量方法论）vs"经验分享"（Netflix 性能工程）vs"组织决策"（本系统预算）。
- 涉及协议要求（如 Retry-After）时以协议标准为准，不把工程建议当协议。
