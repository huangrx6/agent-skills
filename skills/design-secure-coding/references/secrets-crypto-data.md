# 密钥、密码学与敏感数据

## 目录

- [Secret](#secret)
- [Secret 使用](#secret-使用)
- [密码学](#密码学)
- [Hash vs Encryption](#hash-vs-encryption)
- [TLS](#tls)
- [敏感数据](#敏感数据)
- [Token / Identifier](#token-identifier)


## Secret

包括：

- password；
- API key；
- OAuth secret；
- private key；
- signing key；
- database credential；
- cloud credential；
- webhook secret；
- encryption key。

不得存放：

- 源码；
- Git history；
- Dockerfile；
- README/AGENTS/PROJECT_CONTEXT；
- 示例；
- 测试 fixture；
- 日志。

## Secret 使用

- 从 Secrets Manager / Vault / Platform Secret 注入；
- 最小权限；
- 按服务和环境隔离；
- 支持 rotation；
- 不同目的使用不同 key；
- 内存中尽可能缩短生命周期。

环境变量不是秘密管理系统本身，只是可能的一种注入通道。

## 密码学

原则：

- 不自创算法；
- 使用维护中的平台库；
- 选择当前推荐算法；
- 使用 CSPRNG；
- nonce/IV 规则严格遵循算法要求；
- 加密与签名用途分离；
- key version 可追踪；
- rotation 不造成历史数据不可读。

## Hash vs Encryption

需要验证相等且无需恢复：

```text
hash
```

需要恢复原文：

```text
encryption
```

需要证明来源和完整性：

```text
MAC/signature
```

不要用“加密密码”。

## TLS

- 外部和跨信任边界通信使用 TLS；
- 禁止关闭证书验证；
- hostname verification 必须开启；
- 内部 mTLS 是否需要由架构威胁模型决定；
- 不固定过时协议和 cipher。

## 敏感数据

数据进入代码前明确分类。

控制：

- 最小采集；
- 最小返回；
- 最小日志；
- 最小缓存；
- retention；
- encryption；
- access control；
- deletion。

敏感字段不能因为“内部 API”就无限传播。

## Token / Identifier

如果 token 承载授权能力：

- 高熵；
- 不可预测；
- 有过期；
- 可撤销或范围受控。

普通业务 ID 不应被当作秘密，但不能依赖其不可猜测性实现授权。
