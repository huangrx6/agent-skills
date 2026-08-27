# NovaPay 文档树（按 project-documentation-tree.template 落地）

```
novapay/
├── README.md                 # 人类入口：是什么、怎么启动
├── AGENTS.md                 # L0：AI 执行指令（短小有界）
├── PROJECT_CONTEXT.md        # L1：稳定快照 + 知识路由
└── docs/
    ├── index.md              # L2：问题导向导航
    ├── project/
    │   ├── overview.md       # 项目当前范围与行为
    │   ├── glossary.md       # 领域术语（交易/清算/商户）
    │   └── constraints.md    # 合规（PCI-DSS/GDPR）、平台约束
    ├── architecture/
    │   ├── overview.md       # 模块化单体当前结构
    │   ├── diagrams/         # Context/Container 图
    │   └── decisions/        # ADR-001 模块化单体（历史决策）
    ├── development/
    │   ├── setup.md          # 本地启动
    │   ├── workflows.md      # 如何新增 API
    │   └── testing.md        # 测试分层
    ├── contracts/
    │   └── index.md          # ★ CONTRACTS_INDEX：契约事实来源位置 + 生成方式
    ├── data/
    │   ├── ownership.md      # ★ DATA_OWNERSHIP：数据 Owner 与敏感分类
    │   └── lifecycle.md      # 数据生命周期与保留
    ├── operations/
    │   ├── overview.md       # 部署/故障域
    │   └── runbooks/         # 清算积压恢复等
    ├── working-agreements.md # 团队约定（迁移必须 dry-run）
    └── handoffs/
        └── active/           # 未完成任务交接（有关闭条件）
```
