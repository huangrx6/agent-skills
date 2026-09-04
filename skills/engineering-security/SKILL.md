---
name: engineering-security
description: "用户说\"代码评审找安全风险 / 做威胁建模 / 做认证或授权 / 密钥管理 / TLS 配置 / 防止 SQL 注入 / 防止 XSS / 防止 CSRF / 防止 SSRF / 文件上传安全 / 反序列化安全 / 危险 API 评审 / 依赖漏洞扫描 / AI 生成代码的安全审计 / 安全 exception 申请\"时激活。覆盖威胁建模、输入验证、输出编码、注入防护、认证授权、密钥与密码学、文件与路径、网络与 SSRF、反序列化、依赖供应链、安全测试与发布门禁。不要用它做：架构边界与 API 契约 → engineering-architecture；运行时重试/熔断 → engineering-reliability；代码风格 → engineering-quality。"
---

# ![engineering-security](assets/icons/engineering-security-light.svg#gh-light-mode-only) ![engineering-security](assets/icons/engineering-security-dark.svg#gh-dark-mode-only) 工程安全

## 目标

在写代码时能立即回答：哪些输入不可信、数据会进入哪些危险解释器或敏感操作、在哪里必须验证或编码或授权、哪些 API 不应直接使用、哪些安全要求必须通过测试证明。

## 职责边界

本 skill 负责"代码与依赖的安全实现"：

- 威胁建模、信任边界、Source/Sink 分析；
- 输入验证、SQL/NoSQL/命令/模板注入、参数化 Query；
- 输出编码（HTML/属性/URL/JS/CSS）；
- 认证、授权、Session/Cookie、Token、敏感操作 MFA；
- 密钥、密码学、TLS、敏感数据；
- 文件上传、Path Traversal、SSRF、出站请求限制；
- 反序列化、XML/XXE、Parser 配置；
- 危险 API（eval/exec/Runtime/shell/unsafe）、整数/大小、随机数；
- 依赖漏洞扫描、Secret 扫描、License；
- SAST、Fuzz、Security Review、发布门禁；
- AI 辅助生成代码的安全验证。

不负责：API 契约设计、运行时重试策略、性能与容量、代码风格。

## 何时使用（用户原话触发）

| 用户说 | 进入本 skill 哪个子主题 |
| --- | --- |
| 输入验证、SQL/NoSQL/命令注入、参数化查询 | secure-coding |
| 认证、授权、Session、Token、MFA | secure-coding |
| 密钥、密码学、TLS、敏感数据 | secure-coding |
| 文件上传、Path Traversal、SSRF、Redirect | secure-coding |
| 反序列化、XML/XXE、Parser 配置 | secure-coding |
| 危险 API、整数溢出、随机数 | secure-coding |
| 依赖漏洞、Secret 扫描、供应链 | secure-coding |
| SAST、Fuzz、安全评审、发布门禁 | secure-coding |
| AI 生成代码的安全审计 | secure-coding |

## 何时不要使用（路由到其它 skill）

| 用户说 | 跳到 |
| --- | --- |
| 架构边界、API 契约设计 | engineering-architecture |
| 数据库表设计、迁移 | engineering-architecture |
| 错误码体系、统一错误响应（业务失败语义） | engineering-reliability |
| 重试、超时、熔断 | engineering-reliability |
| 监控告警、SLO | engineering-reliability |
| 日志规范、脱敏（属于运行时可靠性） | engineering-reliability |
| 代码风格、命名、lint | engineering-quality |

## 工作流

1. 先识别不可信 Source 与危险 Sink（diff-based），再决定控制点。
2. 信任边界用 allowlist，不依赖黑名单。
3. 每个外部输入尽早验证语法 + 语义；危险解释器使用参数化 API。
4. 认证与授权按 (subject, action, resource, tenant, context) 检查，不只看 role。
5. 密钥从 Secrets Manager 注入；最小权限；按服务和环境隔离；支持 rotation。
6. 依赖漏洞扫描、Secret 扫描、SAST 进入 CI/CD。
7. 高风险变更上 PR 必须附带 Security Review；失败路径写测试。

## 核心原则

- 不可信数据进危险解释器前必须验证或编码或参数化。
- 默认拒绝；每个 endpoint/field 显式定义权限。
- 密钥不进入 Git/日志/示例；改历史不能撤销已泄露，必须 rotation。
- TLS 关闭验证 = 漏洞；hostname verification 必须开启。
- 富文本输出用成熟 sanitizer + 上下文二次编码。
- 客户端隐藏按钮不是授权控制。
- 高风险操作（支付/权限变更/密钥）需 re-auth + audit + 限速。

## 子主题与资源入口

- **secure-coding**：`references/secure-coding/` + `assets/secure-coding/` + `scripts/secure-coding/`

完整示例见 `examples/secure-coding/`。

## 环境与运行

脚本统一通过 `uv` 运行（PEP 723 / `# /// script` 声明，无第三方依赖）。

```bash
uv run scripts/secure-coding/security_impact.py ...
uv run scripts/secure-coding/validate_secure_coding.py ...
uv run python -m unittest discover -s scripts/tests
```

uv 缓存全局共享（`~/.cache/uv`），不会在每个 skill 目录创建 .venv。
