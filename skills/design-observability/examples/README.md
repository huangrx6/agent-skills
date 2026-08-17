# 示例：可观测性产出样例（虚构项目）

> 本项目设定：虚构公司 "NovaPay" 的订单服务，Java 21 + OpenTelemetry。
> 演示用本 skill 产出的 SLI/SLO、信号目录、Trace 设计、告警策略端到端示范。
> **本示例不抄用、仅作参照——指标和告警阈值必须以本系统真实信号和故障演练为事实来源。**

## 文件

- `observability-design.example.md` — SLI/SLO + 信号目录 + Trace 设计 + 告警策略端到端示范

## 要点

1. **SLI 从用户可见行为定义**：下单成功率，不用 Pod Running 代替。
2. **高基数治理**：order_id 进 Trace/Log，不进 Metric。
3. **error-budget burn 告警**：不用瞬时失败率阈值。
4. **故障演练证明**：信号必须能解释真实问题，不只建图。
5. **统一 Resource Identity**：跨信号关联。
