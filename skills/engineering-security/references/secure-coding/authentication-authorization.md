# 认证、授权、会话与敏感操作

## 目录

- [认证](#认证)
- [密码](#密码)
- [授权](#授权)
- [默认拒绝](#默认拒绝)
- [Session / Cookie](#session-cookie)
- [Token](#token)
- [敏感操作](#敏感操作)

## 认证

优先使用成熟身份平台和标准协议。

不要：

- 自建密码协议；
- 自签 Token 格式替代标准机制；
- 在 URL 中传长期凭据；
- 把账号是否存在暴露给攻击者。

高风险操作需要按业务风险考虑重新认证或 MFA。

## 密码

如果应用必须存密码：

- 使用现代 password hashing；
- 每个密码独立 salt；
- 参数可升级；
- 可选 pepper 存在独立 secrets system；
- 不使用普通 SHA-256/MD5 直接哈希密码；
- 不可逆存储。

算法和参数遵循当前平台/OWASP 密码存储建议。

## 授权

授权必须检查：

```text
subject
action
resource
tenant
context
```

不要只检查：

```text
role == ADMIN
```

需要覆盖：

- Object-Level Authorization；
- Function-Level Authorization；
- Field-Level Authorization；
- Tenant Isolation；
- Batch Item Authorization；
- Export/Download；
- Admin impersonation；
- background job acting on behalf of user。

资源 ID 不可猜不能替代授权。

## 默认拒绝

没有明确 Allow 时拒绝。

新增 endpoint、GraphQL field、RPC、message handler 时必须定义权限，而不是继承“默认公开”。

## Session / Cookie

浏览器 Session：

- 随机、高熵 ID；
- Secure；
- HttpOnly；
- 合理 SameSite；
- 登录/提权后 rotation；
- logout 和 revoke；
- idle/absolute timeout；
- 不在 URL 中传 session ID。

## Token

验证：

- signature；
- issuer；
- audience；
- expiry；
- not-before；
- algorithm policy；
- scope/permission。

不能只“JWT decode 成功”。

不要接受由 Token Header 任意指定不受信任 key/JWK URL。

## 敏感操作

支付、权限变更、删除、密钥操作等必须考虑：

- re-auth；
- anti-replay；
- idempotency；
- step-up authorization；
- dual control；
- audit；
- transaction limits。

客户端 UI 隐藏按钮不是授权控制。
