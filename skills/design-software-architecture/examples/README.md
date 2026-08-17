# 示例：完整架构设计产出样例（虚构项目）

> 本项目设定：虚构公司 "NovaPay"，支付清算平台，Java 21 后端 + 云部署。
> 演示用本 skill 产出的完整架构文档套件形态：Brief → QA 场景 → 风格选择 → ADR → 风险登记 → 评审清单。
> 不抄用，作参照。实际项目以自身约束为准。

## 文件

- `architecture-brief.example.md` — Architecture Brief 示范（10+1 节）
- `qa-scenarios.example.md` — 质量属性场景 4 条（含成本）
- `adr-001.example.md` — ADR 示范（含 Alternatives 与 Supersede 关系）
- `risk-register.example.csv` — 风险登记 3 条

## 要点

1. **先约束后风格**：NovaPay 先列驱动因素（P99/合规/团队规模），再选风格——不是先选微服务再找理由。
2. **模块化单体优先**：团队 2 个小组、边界在演进，选模块化单体 + 支付异步任务队列，不默认微服务。
3. **ADR 记录被拒方案**：ADR-001 记录了"直接上微服务"被拒的理由。
4. **成本作为 QA**：成本场景与性能/安全同等列为可测场景。
5. **风险登记带退出条件**：每条风险有 likelihood/impact/owner/revisitTrigger。
