# 安全测试与代码评审

## 目录

- [Diff-Based Review](#diff-based-review)
- [必测负向路径](#必测负向路径)
- [Security Unit/Integration Test](#security-unitintegration-test)
- [SAST](#sast)
- [Dependency / Secret Scan](#dependency-secret-scan)
- [Fuzz / Property Test](#fuzz-property-test)
- [Code Review](#code-review)
- [Security Exception](#security-exception)
- [发布门禁](#发布门禁)


## Diff-Based Review

优先看本次新增攻击面：

- 新 endpoint；
- 新 input；
- 新 sink；
- 新 permission；
- 新 file/network access；
- 新 dependency；
- 新 parser；
- 新 sensitive data；
- 新 admin capability。

## 必测负向路径

根据功能覆盖：

- invalid/malformed input；
- over-size/deep input；
- unauthorized；
- cross-tenant；
- IDOR/BOLA；
- injection payload；
- path traversal；
- SSRF target；
- open redirect；
- malicious file；
- duplicate/replay；
- expired/revoked token；
- CSRF；
- CORS origin；
- deserialization；
- resource exhaustion。

## Security Unit/Integration Test

测试安全不变量：

```text
user A cannot read user B resource
untrusted sort field never reaches SQL identifier
metadata IP cannot be fetched
uploaded executable is rejected
```

不要只依赖 penetration test。

## SAST

静态分析适合发现：

- dangerous API；
- injection pattern；
- secret；
- unsafe deserialization；
- crypto misuse；
- path construction。

规则必须调优，不能长期忽略大量 false positive。

## Dependency / Secret Scan

CI 至少执行：

- known vulnerability；
- secret detection；
- license/approved source（组织需要时）。

发现 secret 后不仅删除当前文件，还要 rotate 并处理 Git history 风险。

## Fuzz / Property Test

优先用于：

- parser；
- serializer；
- protocol；
- file format；
- native boundary；
- validation logic。

## Code Review

Reviewer 需要回答：

- Source 在哪？
- Sink 在哪？
- 控制在哪？
- 控制能否绕过？
- 资源上限是什么？
- authz 是否逐资源执行？
- 错误是否泄露？
- 是否使用新依赖？
- 安全失败能否被观察？

## Security Exception

无法立即满足控制时必须使用安全例外：

- 具体风险；
- 受影响资产；
- 临时补偿；
- Owner；
- expiration；
- fix plan。

禁止永久 `# nosec` / suppress without reason。

## 发布门禁

Blocker：

- credential committed；
- known exploitable critical vulnerability；
- missing authz on protected operation；
- raw SQL/command injection；
- TLS verify disabled；
- unrestricted file/path/SSRF；
- unsafe deserialization of untrusted input；
- cross-tenant access；
- security bypass left enabled。
