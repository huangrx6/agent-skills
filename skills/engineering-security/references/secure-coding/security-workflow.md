# 安全编码工作流

## 目录

- [资产与信任边界](#资产与信任边界)
- [Source](#source)
- [Sink](#sink)
- [Source 到 Sink](#source-到-sink)
- [资源消耗](#资源消耗)
- [安全控制放置](#安全控制放置)
- [失败方式](#失败方式)

## 资产与信任边界

代码评审前先识别：

- 身份；
- 权限；
- 资金；
- 密钥；
- 个人/客户数据；
- 文件；
- 内部网络；
- 管理接口；
- 计算资源。

边界包括：

- Internet → API；
- Browser → Server；
- Service → Service；
- Queue → Consumer；
- Partner → Integration；
- DB/Cache → Application；
- User Content → Renderer；
- Application → Internal/External Network。

“内部来源”仍可能被攻击者、错误配置或上游漏洞污染。

## Source

常见不可信输入：

```text
HTTP path/query/header/body/cookie
GraphQL variables
gRPC request
WebSocket/SSE message
message queue event
uploaded file
database content originally derived from users
third-party API response
URL / redirect target
filesystem metadata
environment/config controlled by deployment
```

不要只给 Controller 参数贴“不可信”标签，必须跟踪数据经过转换后的去向。

## Sink

高风险 Sink：

```text
SQL/NoSQL query
shell/process execution
HTML/DOM/JS/CSS
template engine
filesystem path
HTTP client
redirect
XML parser
native/object deserializer
eval/script/expression engine
LDAP/XPath
email/header construction
authorization decision
money transfer / destructive operation
```

## Source 到 Sink

评审顺序：

```text
source
↓
decode/canonicalize
↓
syntactic validation
↓
semantic/business validation
↓
authorization
↓
context-specific safe construction
↓
sink
```

不是每一步都适用，但不得用一个通用 `sanitize()` 替代整个流程。

## 资源消耗

为不可信输入设置：

- request body 上限；
- string 长度；
- collection 数量；
- nesting 深度；
- file 大小；
- archive 解压大小和比例；
- image/document 处理资源；
- query complexity；
- regex 时间；
- concurrent jobs；
- downstream response size；
- timeout。

防止“输入合法但把系统耗死”。

## 安全控制放置

控制尽量靠近真正安全边界：

- Schema/DTO 验证负责结构；
- 领域服务负责业务约束；
- 数据访问层负责参数化；
- Resource/Action 层负责授权；
- HTTP client wrapper 负责出站策略；
- 模板系统负责上下文编码。

中央安全库用于复用正确实现，不应用一个全能 helper 隐藏上下文。

## 失败方式

常见错误：

- 黑名单过滤危险字符；
- 先 decode 一次，后续组件又 decode；
- 输入验证被当作 XSS/SQLi 主要防线；
- 前端已校验所以后端不校验；
- 管理员输入被认为可信；
- 从数据库读出后直接拼到命令；
- WAF 存在所以代码无需安全；
- 安全控制只覆盖正常 endpoint，遗漏 batch/export/admin。
