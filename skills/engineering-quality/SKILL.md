---
name: engineering-quality
description: "用户说\"建立代码风格规范 / 命名约定 / 格式化配置 / lint 规则 / 文件头与版权元数据 / 注释规范 / 评审代码 / 设计模式评审 / 配置中心接入 / Feature Flag 设计 / Secret 分离 / 动态配置 / 配置热更新 / 配置漂移检测\"时激活。覆盖代码风格与命名、文件组织、配置分类与 Schema、动态配置、Secret 边界、Feature Flag。不要用它做：架构选型 → engineering-architecture；异常/韧性/可观测 → engineering-reliability；安全威胁建模 → engineering-security。"
---

# ![engineering-quality](../assets/icons/engineering-quality-light.svg#gh-light-mode-only) ![engineering-quality](../assets/icons/engineering-quality-dark.svg#gh-dark-mode-only) 工程质量

## 目标

让代码风格可自动化执行，让配置可分类、可验证、可回滚。

## 职责边界

本 skill 负责"代码级一致性与配置体系"：

- 命名、格式化、文件组织、文件头、注释、API 文档、设计模式；
- 多语言实施附录（Java/Go/Python/JS/TS/C#/Rust/SQL）；
- 配置分类：Code Constant、Deployment Config、Secret、Dynamic Config、Feature Flag；
- 配置 Schema、来源优先级、启动校验、动态更新、热更新、灰度、回滚；
- Kubernetes ConfigMap/Secret 使用、漂移检测；
- 评审清单、自动化检查。

不负责：架构边界、运行时可靠性、日志脱敏、密钥管理细节、威胁建模。

## 何时使用（用户原话触发）

| 用户说 | 进入本 skill 哪个子主题 |
| --- | --- |
| 代码风格、命名、lint、格式化、editorconfig | code-style |
| 文件头、版权元数据、注释规范 | code-style |
| 设计模式评审、Implementation 质量 | code-style |
| 多语言命名 / 文件布局 | code-style |
| 配置分类、配置中心接入、Schema | configuration |
| 动态配置、热更新、回滚 | configuration |
| Feature Flag、灰度、漂移检测 | configuration |
| Kubernetes ConfigMap/Secret | configuration |

## 何时不要使用（路由到其它 skill）

| 用户说 | 跳到 |
| --- | --- |
| 画架构图、模块边界、技术选型 | engineering-architecture |
| API 契约风格、Schema、版本 | engineering-architecture |
| 数据库表设计、迁移 | engineering-architecture |
| 错误码体系、重试、熔断 | engineering-reliability |
| 监控告警、SLO | engineering-reliability |
| 日志规范、脱敏 | engineering-reliability |
| 密钥存储、密码学、TLS | engineering-security |
| SQL 注入、SSRF、依赖漏洞 | engineering-security |

## 工作流

1. 先有项目画像（技术栈/模块/命令），再写代码规范，再写语言附录。
2. 每条规则标注 `[必须/应/可]` 与可自动化能力，规则尽量由工具执行而非人工记忆。
3. 配置先按 5 类（Code/Deployment/Secret/Dynamic/FeatureFlag）分类，再定义 Schema 和来源优先级。
4. 启动时完成完整校验；动态配置定义刷新、版本、原子应用、失败行为、回滚。
5. Secret 与普通配置彻底分离；不同服务/环境的 Secret 隔离。
6. 评审清单可生成 CSV 自查；规范产出后用 validate 脚本验证完整性。

## 核心原则

- 命名优先表达领域含义，不泄露技术实现。
- 规范必须由工具（formatter/lint/CI）执行，不由人记忆。
- 同一事实只在一处定义（配置中心或代码常量），其它位置用链接或摘要。
- 配置变更 = 显式审计 + 灰度 + 回滚路径；漂移必须可检测。
- Secret 不进 Git/日志/示例；环境变量只是注入通道，不是秘密管理。

## 子主题与资源入口

- **code-style**：`references/code-style/` + `assets/code-style/` + `scripts/code-style/`
- **configuration**：`references/configuration/` + `assets/configuration/` + `scripts/configuration/`

完整示例见 `examples/<sub>/`。

## 环境与运行

脚本统一通过 `uv` 运行（PEP 723 / `# /// script` 声明，无第三方依赖）。

```bash
uv run scripts/<sub>/validate_*.py --<args>
uv run python -m unittest discover -s scripts/tests
```

uv 缓存全局共享（`~/.cache/uv`），不会在每个 skill 目录创建 .venv。
