# 浏览器与前端安全

## XSS

首选：

- framework 默认自动编码；
- 安全 DOM API；
- textContent 而不是 innerHTML；
- 禁止将不可信字符串传入危险 DOM Sink。

富文本使用成熟 sanitizer。

禁止：

```text
innerHTML = userInput
document.write(userInput)
eval(userInput)
new Function(userInput)
```

除非经过专门安全设计。

## CSP

CSP 是 defense in depth，不是 XSS 修复替代品。

优先：

- nonce/hash based；
- 限制 script source；
- 减少 unsafe-inline/unsafe-eval；
- Report-Only 观察后收紧。

不要复制一个无法维护的巨大域名 allowlist。

## CSRF

Cookie 自动随请求发送的认证模式需要 CSRF 防护。

选择：

- SameSite；
- synchronizer token；
- double submit cookie；
- framework built-in。

状态改变操作不能使用 GET。

## CORS

CORS 是浏览器读取权限，不是身份认证。

- 固定允许 origins；
- credentials 与 `*` 不兼容；
- 不反射任意 Origin；
- 只允许需要的方法/Header；
- preflight cache 按策略设置。

服务器端授权仍必须执行。

## Cookie

敏感 Cookie：

- Secure；
- HttpOnly；
- SameSite；
- 合理 Path/Domain；
- 最小生命周期。

避免过宽 Domain。

## Clickjacking

敏感页面使用：

- `frame-ancestors` CSP；
- 必要时 X-Frame-Options 兼容。

## 前端 Secret

浏览器代码中不存在真正 Secret。

API key 如果发给浏览器，就必须按公开凭据设计并限制能力。

Source Map 是否公开需要根据源代码敏感度和调试策略决定，但不能把 Secret 编译进 bundle。

## Redirect / URL

前端和服务端都防止 open redirect。

不要用 URL fragment/query 承载 access token，除非协议明确要求且风险已评估。
