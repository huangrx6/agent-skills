# Skills Index

> 4 个 `engineering-*` skill 替代了 13 个旧的 `design-*` skill。本目录是入口；按问题挑 skill，按子主题挑 references/。

## 4 个 skill 一图速览

| Skill | 何时使用 | 子主题 |
| --- | --- | --- |
| [`engineering-architecture`](engineering-architecture/SKILL.md) | 画架构图 / 选单体vs微服务 / 评审架构 / 写 ADR / 划分服务边界 / 选部署形态 / 做技术选型 / 跨团队集成 / 重构系统 / 治理架构文档 / 设计或评审 API / 设计或评审数据库 / 写文档 / Git / 发布 | `architecture` / `api-contracts` / `database` / `documentation` / `git` |
| [`engineering-reliability`](engineering-reliability/SKILL.md) | 服务挂了 / 报错 / 超时 / 想加重试 / 想加熔断 / 想加限流 / 想做故障注入 / 想加监控告警 / 想加 SLO/SLI / 想看日志 / 想做日志规范 / 想做性能压测 / 想做容量规划 | `exception-handling` / `resilience` / `observability` / `logging` / `performance-capacity` |
| [`engineering-security`](engineering-security/SKILL.md) | 代码评审找安全风险 / 做威胁建模 / 做认证授权 / 密钥管理 / TLS / SQL注入 / XSS / CSRF / SSRF / 文件上传 / 反序列化 / 危险 API 评审 / 依赖漏洞 / AI 生成代码的安全审计 / 安全 exception 申请 | `secure-coding` |
| [`engineering-quality`](engineering-quality/SKILL.md) | 建立代码规范 / 命名 / lint / 文件头 / 注释 / 设计模式 / 配置中心 / Feature Flag / Secret 分离 / 动态配置 | `code-style` / `configuration` |

## 触发语法

```text
使用 $engineering-<area>[/<sub-topic>] 帮我 <做什么>
```

示例：

| 你说 | 触发 |
| --- | --- |
| 帮我做架构设计 | `$engineering-architecture/architecture` |
| 评审我的 OpenAPI | `$engineering-architecture/api-contracts` |
| 帮我提交这次改动，遵守 git 规范 | `$engineering-architecture/git` |
| 服务挂了怎么定位 | `$engineering-reliability/exception-handling` |
| 我想加重试 | `$engineering-reliability/resilience` |
| 加 SLO 告警 | `$engineering-reliability/observability` |
| 帮我写日志规范 | `$engineering-reliability/logging` |
| 慢 SQL 排查 | `$engineering-reliability/performance-capacity` |
| 评审代码安全 | `$engineering-security/secure-coding` |
| 建立命名规范 | `$engineering-quality/code-style` |
| 接入配置中心 | `$engineering-quality/configuration` |

每个 skill 的 description 第一句就是"用户说什么时激活"，完整路由表在每个 skill 的 SKILL.md。

## 子主题入口

每个子主题都有自己的 `README.md` 作快速参考 + 链接到完整 references/ 和 assets/。

| Skill | Sub-topics |
| --- | --- |
| [engineering-architecture](engineering-architecture/SKILL.md) | [architecture](engineering-architecture/architecture/README.md) · [api-contracts](engineering-architecture/api-contracts/README.md) · [database](engineering-architecture/database/README.md) · [documentation](engineering-architecture/documentation/README.md) · [git](engineering-architecture/git/README.md) |
| [engineering-reliability](engineering-reliability/SKILL.md) | [exception-handling](engineering-reliability/exception-handling/README.md) · [resilience](engineering-reliability/resilience/README.md) · [observability](engineering-reliability/observability/README.md) · [logging](engineering-reliability/logging/README.md) · [performance-capacity](engineering-reliability/performance-capacity/README.md) |
| [engineering-security](engineering-security/SKILL.md) | [secure-coding](engineering-security/secure-coding/README.md) |
| [engineering-quality](engineering-quality/SKILL.md) | [code-style](engineering-quality/code-style/README.md) · [configuration](engineering-quality/configuration/README.md) |

## 运行验证

```bash
# 资源完整性 + 表头/枚举校验
uv run scripts/<sub-topic>/validate_*.py [args]

# 单元测试
uv run python -m unittest discover -s scripts/<sub-topic>/tests
```

每个 sub-topic 的 `README.md` 都有具体命令。

## 与 13 个旧 `design-*` 的对应

13 个旧 `design-*` skill 已删除。其内容已整合到 4 个新 `engineering-*` skill 的对应子主题：

| 旧 skill | 新位置 |
| --- | --- |
| `design-software-architecture` | `engineering-architecture/architecture` |
| `design-api-contracts` | `engineering-architecture/api-contracts` |
| `design-database-standards` | `engineering-architecture/database` |
| `design-engineering-documentation` | `engineering-architecture/documentation` |
| `design-git-workflows` | `engineering-architecture/git` |
| `design-exception-handling` | `engineering-reliability/exception-handling` |
| `design-service-resilience` | `engineering-reliability/resilience` |
| `design-observability` | `engineering-reliability/observability` |
| `design-application-logging` | `engineering-reliability/logging` |
| `design-performance-capacity` | `engineering-reliability/performance-capacity` |
| `design-secure-coding` | `engineering-security/secure-coding` |
| `design-code-writing-standards` | `engineering-quality/code-style` |
| `design-configuration-management` | `engineering-quality/configuration` |

git 历史保留完整迁移记录。

## 何时**不**用本目录

- **看产品 / 工具 / 业务的 README**：本目录是 engineering 标准，不是产品说明
- **看其它 skill**：`obsidian-*` / `skill-creator` / `visual-*` / `draw-processon` 是独立 skill，与本目录的工程标准无关
- **修改本目录外的 skill**：本 README 不约束其它 skill 的演进
