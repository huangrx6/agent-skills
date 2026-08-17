# 示例：工程文档体系产出样例（虚构项目）

> 本项目设定：虚构公司 "NovaPay"（与 design-software-architecture 示例同项目），
> 演示用本 skill 产出的完整文档体系形态：四层模型 + 唯一事实来源 + doc_impact 路由。
> **本示例不抄用、仅作参照——实际项目以自身约束为准。**

## 文件

- `doc-tree.example.md` — 按 project-documentation-tree.template 落地的完整目录
- `project-context.example.md` — PROJECT_CONTEXT.md 示范（L1，稳定快照）
- `docs-index.example.md` — docs/index.md 导航示范（L2，问题导向）
- `agents.example.md` — AGENTS.md 示范（L0，只放执行指令）
- `impact-routing.example.md` — 用 doc_impact.py 对示例变更路径的路由输出

## 要点

1. **四层分离**：AGENTS（指令）/ PROJECT_CONTEXT（快照）/ docs/index（导航）/ handoffs（时间性）各司其职，不合并。
2. **CONTRACTS/DATA 落地**：契约与数据都有独立 canonical 位置（对应 type-policy 的 CONTRACTS_INDEX/DATA_OWNERSHIP）。
3. **问题导向索引**：docs/index 按"我要做什么→读哪个文档"组织，不是文件列表 dump。
4. **doc_impact 路由**：变更路径 → 应检查的文档区域，防止文档漂移。
