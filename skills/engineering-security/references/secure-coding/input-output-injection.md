# 输入、输出与注入防护

## 目录

- [输入验证](#输入验证)
- [SQL / NoSQL](#sql-nosql)
- [OS Command](#os-command)
- [Template / Expression](#template-expression)
- [LDAP / XPath / Header](#ldap-xpath-header)
- [输出编码](#输出编码)
- [Sanitization](#sanitization)
- [Regex](#regex)

## 输入验证

在外部数据进入工作流时尽早验证。

### 语法验证

验证：

- 类型；
- 编码；
- 长度；
- 格式；
- 枚举；
- 范围；
- 对象结构。

### 语义验证

验证：

- start < end；
- amount 符合业务规则；
- 状态转换合法；
- ID 属于当前租户；
- 文件类型符合当前操作。

优先 allowlist。

黑名单可作为补充检测，不能作为主要安全边界。

## SQL / NoSQL

必须：

- 使用参数化 Query/Prepared Statement；
- ORM 查询 API 必须保持参数绑定；
- 用户提供的 sort/table/column 等不能直接拼接，使用 allowlist 映射。

禁止：

```text
"SELECT ... WHERE id = " + userInput
```

转义不是参数化的等价替代。

NoSQL 同样防止将用户对象直接作为 Query Operator。

例如不要接受客户端任意：

```json
{"$where": "..."}
```

## OS Command

最优先避免调用 Shell。

优先：

1. 使用语言/库 API 完成操作；
2. 使用参数数组调用固定 executable；
3. 对不可避免的动态参数做严格 allowlist；
4. 最小 OS 权限。

禁止：

```text
sh -c <user-controlled-string>
cmd.exe /c <user-controlled-string>
```

## Template / Expression

- 模板名来自固定 allowlist；
- 不让用户提供服务端模板源码；
- 禁止把不可信输入传给 EL、SpEL、OGNL、Jinja expression、Velocity expression 等可执行表达式；
- Sandbox 不是无限可信，仍要限制能力和资源。

## LDAP / XPath / Header

使用库提供的结构化构造和上下文编码。

用户数据不得直接拼入：

- LDAP filter；
- XPath/XQuery；
- HTTP response header；
- email header。

换行符必须特殊处理，防 Header Injection。

## 输出编码

输出编码取决于目标上下文：

| Context | 控制 |
| --- | --- |
| HTML text | HTML entity encoding |
| HTML attribute | attribute-safe encoding + quoted attribute |
| URL parameter | URL component encoding |
| JavaScript | JS context-safe encoding；优先不内联 |
| CSS | CSS context-safe encoding；优先避免不可信值 |
| JSON in HTML | 使用安全 serializer 和正确 script embedding 策略 |

不要把 HTML escaping 用在 JavaScript context。

## Sanitization

只有需要允许富文本 HTML 等“部分主动内容”时使用成熟 sanitizer。

规则：

- 固定 allowlist；
- 库持续更新；
- sanitize 后不要再次拼接进不同上下文；
- sanitizer 输出仍需按最终上下文处理。

## Regex

- 复杂正则评估 ReDoS；
- 设置输入长度上限；
- 避免高风险嵌套量词；
- 对攻击者可控长文本使用线性时间策略或 timeout 能力。
