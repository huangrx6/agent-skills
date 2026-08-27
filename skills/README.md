# ![engineering-architecture icon](assets/icons/engineering-architecture-light.svg#gh-light-mode-only) ![engineering-architecture icon](assets/icons/engineering-architecture-dark.svg#gh-dark-mode-only) **Engineering Skills**

> 11 个 skill：4 个工程标准（`engineering-*`，本仓库主线）+ 7 个工具与流程（视觉 / Obsidian / 流程）。按问题挑 skill。

---

## 1. 工程标准（4 个 `engineering-*`）

覆盖软件工程生命周期的 4 个维度：架构 / 可靠性 / 安全 / 质量。

| Icon | Skill | 覆盖 |
| --- | --- | --- |
| ![architecture](assets/icons/engineering-architecture-light.svg#gh-light-mode-only) ![architecture](assets/icons/engineering-architecture-dark.svg#gh-dark-mode-only) | [**engineering-architecture**](engineering-architecture/SKILL.md) | 系统骨架与契约：边界 · 风格 · API · 数据库 · 文档 · Git |
| ![reliability](assets/icons/engineering-reliability-light.svg#gh-light-mode-only) ![reliability](assets/icons/engineering-reliability-dark.svg#gh-dark-mode-only) | [**engineering-reliability**](engineering-reliability/SKILL.md) | 运行时可靠性与可观测性：异常 · 韧性 · 监控 · 日志 · 性能容量 |
| ![security](assets/icons/engineering-security-light.svg#gh-light-mode-only) ![security](assets/icons/engineering-security-dark.svg#gh-dark-mode-only) | [**engineering-security**](engineering-security/SKILL.md) | 代码与依赖的安全实现：威胁建模 · 注入防护 · 认证授权 · 密钥 · SAST |
| ![quality](assets/icons/engineering-quality-light.svg#gh-light-mode-only) ![quality](assets/icons/engineering-quality-dark.svg#gh-dark-mode-only) | [**engineering-quality**](engineering-quality/SKILL.md) | 代码级一致性与配置体系：代码规范 · 命名 · 配置分类 · Feature Flag |

### 1.1 何时使用哪个

| 你说 | 跳到 |
| --- | --- |
| 画架构图 · 选单体 vs 微服务 · 评审方案 · 写 ADR · 划分服务边界 · 选部署形态 · 做技术选型 · 重构系统 · 跨团队集成 · 治理架构文档 · 设计或评审 API · 设计或评审数据库 · 写文档 · Git · 发布 | `engineering-architecture` |
| 服务挂了 · 报错 · 超时 · 想加重试 / 熔断 / 限流 · 想做故障注入 · 想加监控告警 · 想加 SLO / SLI · 想看日志 · 想做日志规范 · 想做性能压测 · 想做容量规划 | `engineering-reliability` |
| 代码评审找安全风险 · 做威胁建模 · 做认证 / 授权 · 密钥管理 · TLS · SQL 注入 · XSS · CSRF · SSRF · 文件上传 · 反序列化 · 危险 API 评审 · 依赖漏洞 · AI 生成代码安全审计 · 安全 exception | `engineering-security` |
| 建立代码规范 · 命名 · lint · 文件头 · 注释 · 设计模式 · 配置中心 · Feature Flag · Secret 分离 · 动态配置 · 配置热更新 | `engineering-quality` |

### 1.2 触发语法

```text
使用 $engineering-<area>[/<sub-topic>] 帮我 <做什么>
```

### 1.3 4 个 skill 的子主题

| Skill | Sub-topics |
| --- | --- |
| **engineering-architecture** | [architecture](engineering-architecture/architecture/README.md) · [api-contracts](engineering-architecture/api-contracts/README.md) · [database](engineering-architecture/database/README.md) · [documentation](engineering-architecture/documentation/README.md) · [git](engineering-architecture/git/README.md) |
| **engineering-reliability** | [exception-handling](engineering-reliability/exception-handling/README.md) · [resilience](engineering-reliability/resilience/README.md) · [observability](engineering-reliability/observability/README.md) · [logging](engineering-reliability/logging/README.md) · [performance-capacity](engineering-reliability/performance-capacity/README.md) |
| **engineering-security** | [secure-coding](engineering-security/secure-coding/README.md) |
| **engineering-quality** | [code-style](engineering-quality/code-style/README.md) · [configuration](engineering-quality/configuration/README.md) |

每个子主题都有自己的 `README.md` 作快速参考 + 链接到完整 references/ 和 assets/。

### 1.4 运行验证

```bash
# 资源完整性 + 表头/枚举校验
uv run scripts/<sub-topic>/validate_*.py [args]

# 单元测试
uv run python -m unittest discover -s scripts/<sub-topic>/tests
```

### 1.5 与旧 skill 的对应

git 历史记录了本仓库曾有的 `design-*` skill 演化轨迹。无需在 README 重复——通过 `git log --diff-filter=D` 可追溯。

---

## 2. 工具与流程（7 个）

围绕 `engineering-*` 标准做事的辅助 skill：阅读图片 / 写文档 / 操作 Obsidian / 创建新 skill 等。

| Icon | Skill | 用途 |
| --- | --- | --- |
| ![readme](assets/icons/developer-readme-design-light.svg#gh-light-mode-only) ![readme](assets/icons/developer-readme-design-dark.svg#gh-dark-mode-only) | [**developer-readme-design**](developer-readme-design/SKILL.md) | 把仓库 README 改造成成熟的开发者工具 landing page（monochrome / restrained / technical） |
| ![draw](assets/icons/draw-processon-light.svg#gh-light-mode-only) ![draw](assets/icons/draw-processon-dark.svg#gh-dark-mode-only) | [**draw-processon**](draw-processon/SKILL.md) | 统一调用 ProcessOn 画架构图 / 流程图 / ER 图 / 思维导图等 |
| ![vault](assets/icons/obsidian-personal-knowledge-base-light.svg#gh-light-mode-only) ![vault](assets/icons/obsidian-personal-knowledge-base-dark.svg#gh-dark-mode-only) | [**obsidian-personal-knowledge-base**](obsidian-personal-knowledge-base/SKILL.md) | 操作 Huangrx6 的 Obsidian vault（Inbox / Projects / Areas / Resources / Archive） |
| ![record](assets/icons/obsidian-work-log-release-recorder-light.svg#gh-light-mode-only) ![record](assets/icons/obsidian-work-log-release-recorder-dark.svg#gh-dark-mode-only) | [**obsidian-work-log-release-recorder**](obsidian-work-log-release-recorder/SKILL.md) | 任务完成后把 landed / 可复用 / 运维事实沉淀到 Obsidian 长期知识 |
| ![create](assets/icons/skill-creator-light.svg#gh-light-mode-only) ![create](assets/icons/skill-creator-dark.svg#gh-dark-mode-only) | [**skill-creator**](skill-creator/SKILL.md) | 创建新 skill / 改进现有 skill / 跑 eval 测触发准确度 / 优化 description |
| ![image](assets/icons/visual-image-understanding-light.svg#gh-light-mode-only) ![image](assets/icons/visual-image-understanding-dark.svg#gh-dark-mode-only) | [**visual-image-understanding**](visual-image-understanding/SKILL.md) | 读图片（截图 / 照片 / 文档 / 图表 / 对话截图等），OCR + 视觉理解 |
| ![layout](assets/icons/visual-ui-layout-spec-light.svg#gh-light-mode-only) ![layout](assets/icons/visual-ui-layout-spec-dark.svg#gh-dark-mode-only) | [**visual-ui-layout-spec**](visual-ui-layout-spec/SKILL.md) | UI 截图 / 数据大屏转可交付前端的布局规格（双轨证据：原生视觉 + 远端 VLM） |

---

## 3. 工作流：先工程标准，再工具

```text
1. 写 / 评审 / 改代码   →  用 engineering-* 决定 "该不该做、怎么做对"
2. 需要写 README       →  developer-readme-design
3. 需要画图             →  draw-processon
4. 需要读图             →  visual-image-understanding 或 visual-ui-layout-spec
5. 任务完成要沉淀       →  obsidian-work-log-release-recorder
6. 跨会话 / 项目上下文   →  obsidian-personal-knowledge-base
7. 新建 / 改 skill      →  skill-creator
```

## 4. 本 README 自身

- 本文件是 `skills/` 目录的入口，不约束其他 skill 的演进
- 修改本文件前先读 `developer-readme-design` 的视觉规范
- 增加新 skill 时在本文件 §2 添加一行 + 同步加 icon 到 `assets/icons/`
