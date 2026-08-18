---
name: design-secure-coding
description: "设计、审查和完善可直接用于日常开发的安全编码规范，包括信任边界、输入验证、上下文输出编码、SQL/NoSQL/命令/模板注入防护、认证与授权、会话和令牌、密钥与密码学、敏感数据、文件上传与路径处理、SSRF 与出站请求、反序列化、XML、浏览器安全、CSRF/CORS/CSP、危险 API、依赖与供应链基础防护、安全测试、代码评审，以及 AI Coding 场景下的生成代码与依赖验证。用于建立组织级或项目级 Secure Coding Standard、评审高风险代码、为 AI Agent 提供安全实现约束、在任务结束前执行安全影响检查。无明确不覆盖——建议与 code-writing-standards / exception-handling / configuration-management / observability 配合使用。"
---

# 安全编码设计

## 目标

让开发者和 AI Agent 在写代码时能够快速回答：

- 哪些输入是不可信的；
- 数据会进入哪些危险解释器或敏感操作；
- 在哪里必须验证、编码、参数化、授权或限制；
- 哪些 API 不应直接使用；
- 哪些安全要求必须通过测试和静态检查证明。

本技能优先给出可执行控制，不把 OWASP/CWE 条目原样堆成检查表。

## 工作流

1. 识别资产、信任边界和数据分类。
2. 标记所有不可信 Source：
   - HTTP/RPC/GraphQL/Event/WebSocket；
   - 文件和对象存储；
   - 数据库中可被攻击者污染的数据；
   - 第三方 API；
   - 消息队列；
   - 环境和配置；
   - 用户可控 URL、路径、模板和表达式。
3. 标记危险 Sink：
   - SQL/NoSQL；
   - OS 命令；
   - HTML/DOM/JavaScript/CSS/URL；
   - 文件系统路径；
   - 模板引擎；
   - 反序列化；
   - XML parser；
   - HTTP client；
   - 动态代码执行；
   - 权限或资金操作。
4. 在“数据进入 Sink 前”选择正确控制，不使用通用 `sanitize()` 代替上下文控制。
5. 独立检查认证、授权、会话、敏感数据、密码学和秘密。
6. 对资源消耗设置大小、深度、数量、并发和时间上限。
7. 对高风险功能编写负向测试与安全回归测试。
8. AI 生成代码或新增依赖时执行额外验证。
9. 运行静态检查、依赖/秘密扫描及本 Skill 的安全影响检查。
10. 用评审清单完成任务。

## 核心原则

- 所有跨信任边界的数据都按不可信处理，包括“内部服务”和数据库中的历史数据。
- 验证分为语法验证与业务语义验证；验证不等于防注入。
- 注入防护优先使用结构化、安全 API：参数化查询、参数化命令、自动转义模板、类型安全构造器。
- 输出编码必须针对具体输出上下文；HTML、属性、JavaScript、CSS、URL 不能共用一种编码。
- 禁止通过字符串拼接构造 SQL、Shell 命令、模板代码、路径、LDAP/XPath 等解释器输入。
- 无法参数化的标识符使用应用侧 allowlist 映射，而不是直接接受用户字符串。
- 授权必须在服务端、靠近受保护资源或操作执行；认证通过不等于有权限。
- 默认拒绝；权限按最小范围授予；资源级和字段级授权不能只在列表入口做一次。
- 密钥、Token、密码、私钥和生产凭据不得硬编码、写入仓库、测试数据、日志或文档。
- 密码学使用平台和成熟库，不自行设计算法、协议、随机数或密钥派生。
- 文件名、路径、URL、Redirect、Webhook Target、XML 和反序列化都属于高风险输入，必须使用专门策略。
- 出站 HTTP 请求必须限制协议、目标、DNS/IP、重定向、端口、响应大小和超时，防止 SSRF 与资源滥用。
- 不可信数据不得进入通用对象反序列化、`eval`、动态脚本、表达式执行或反射构造路径。
- 所有输入、集合、文件、解压内容、请求正文、查询复杂度和并发都必须有硬上限。
- 客户端校验只改善体验，不能替代服务端校验。
- 安全 Header、CORS、CSRF 和 CSP 必须依据应用实际浏览器模型设置，不复制万能配置。
- 安全失败对外返回最少信息；详细错误和审计按异常/日志规范处理。
- 安全控制不能只依赖网关、WAF 或前端；应用必须保持自身安全边界。
- 生成代码、ORM、框架和 SDK 不自动安全；仍需审查其危险默认值和逃生 API。
- 安全例外必须明确风险、Owner、期限、补偿控制和退出条件。

## AI Coding 规则

- AI 生成的代码视为未审查代码，安全要求与人工代码完全相同。
- AI 建议的新包、镜像、GitHub 仓库和下载地址必须验证真实存在、名称、发布者和官方来源。
- 不因模型建议而关闭证书验证、CORS、CSRF、鉴权、类型检查或安全扫描。
- 不把生产秘密、真实用户数据或完整敏感日志提交给外部模型。
- AI 修改认证、授权、密码学、支付、文件处理、出站网络、反序列化或权限代码时，必须执行安全专项评审。
- AI 创建“临时绕过”时必须附退出条件；不得把临时 `allow all`、跳过验证或调试后门留在生产路径。
- Agent 完成任务前必须检查最终 diff，而不是只依据对话中计划的修改。

## 参考文件选择

- 安全编码工作流、信任边界、Source/Sink 与资源限制：读取 [references/security-workflow.md](references/security-workflow.md)。
- 输入验证、输出编码和注入：读取 [references/input-output-injection.md](references/input-output-injection.md)。
- 认证、授权、会话、Token 和敏感操作：读取 [references/authentication-authorization.md](references/authentication-authorization.md)。
- Secret、密码存储、密码学和敏感数据：读取 [references/secrets-crypto-data.md](references/secrets-crypto-data.md)。
- 文件上传、路径、SSRF、Redirect、XML 和反序列化：读取 [references/files-network-parsing.md](references/files-network-parsing.md)。
- XSS、CSRF、CORS、CSP、Cookie 和浏览器侧安全：读取 [references/web-browser-security.md](references/web-browser-security.md)。
- `eval`、反射、临时文件、进程、语言与框架危险 API：读取 [references/dangerous-apis-runtime.md](references/dangerous-apis-runtime.md)。
- 第三方依赖、包、构建和最小供应链规则：读取 [references/dependencies-supply-chain.md](references/dependencies-supply-chain.md)。
- AI Coding 特殊安全规则：读取 [references/ai-assisted-secure-coding.md](references/ai-assisted-secure-coding.md)。
- 测试、代码评审和发布门禁：读取 [references/security-testing-review.md](references/security-testing-review.md)。
- OWASP ASVS、Cheat Sheet、NIST SSDF、CWE 等依据：读取 [references/standards-sources.md](references/standards-sources.md)。
- 需要完整产出样例时：读取 [examples/README.md](examples/README.md) 下的虚构项目示范。

## 职责边界

- 架构信任边界、服务隔离和威胁模型：不属本 Skill 范围。
- API 协议、Schema、限流和接口安全契约：不属本 Skill 范围。
- 表权限、数据库账号、SQL 与迁移：不属本 Skill 范围。
- 错误响应与异常：不属本 Skill 范围。
- 安全日志、脱敏、审计和保留：不属本 Skill 范围。
- 一般代码风格和设计质量：不属本 Skill 范围。

本 Skill 负责代码实现中的安全控制和安全评审。

## 内置资源

- [assets/security-control-catalog.csv](assets/security-control-catalog.csv)：核心控制目录。
- [assets/taint-source-sink-catalog.csv](assets/taint-source-sink-catalog.csv)：不可信 Source 与危险 Sink 路由表。
- [assets/security-impact-rules.csv](assets/security-impact-rules.csv)：变更路径的安全影响提示。
- [assets/security-review-checklist.csv](assets/security-review-checklist.csv)：安全代码评审清单。
- [assets/security-exception.template.md](assets/security-exception.template.md)：安全例外模板。
- `scripts/security_impact.py`：根据 changed files 输出安全评审领域。
- `scripts/validate_secure_coding.py`：校验本 Skill 的目录资产。

## 环境与运行

本 Skill 脚本统一通过 **uv** 运行（不使用宿主机的原始 Python，避免环境污染）。

- 所有脚本均为纯标准库，无需安装任何第三方包；uv 仅用于隔离 Python 解释器。
- uv 使用全局缓存（`~/.cache/uv`），**不会在每个 skill 目录创建 .venv**；Python 解释器与依赖在所有 skill 间共享，不重复下载。
- 固定路径约定：
  - uv 二进制：`~/.local/bin/uv`
  - 依赖与 Python 缓存：`~/.cache/uv`（全局共享）
  - Python 解释器：`~/.local/share/uv/python/`
  - 脚本：各 skill 的 `scripts/` 目录

首次使用前确保 uv 可用（不可用则自动安装，无需用户操作）：

```bash
python scripts/ensure_uv.py
# 或手动：curl -LsSf https://astral.sh/uv/install.sh | sh
```

统一运行方式：

```bash
uv run scripts/validate_secure_coding.py --assets assets/
uv run python -m unittest discover -s scripts/tests   # 跑测试
```

