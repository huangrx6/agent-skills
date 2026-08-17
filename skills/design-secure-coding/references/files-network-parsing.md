# 文件、路径、网络请求与解析

## 目录

- [文件上传](#文件上传)
- [Path Traversal](#path-traversal)
- [SSRF](#ssrf)
- [Redirect](#redirect)
- [XML](#xml)
- [Deserialization](#deserialization)
- [Archive / Parser](#archive-parser)


## 文件上传

使用 defense in depth：

- 业务允许的 extension allowlist；
- 不信任 `Content-Type`；
- 检查实际文件类型；
- 文件大小上限；
- 服务端生成存储名；
- 原文件名仅作为 metadata；
- 存储在 Web Root 之外或独立对象存储；
- 上传权限；
- malware/sandbox/CDR 按风险启用；
- ZIP/归档限制解压大小、层数和文件数；
- 公共下载经过受控 handler；
- 删除 active content 风险。

不要用用户文件名构造服务器路径。

## Path Traversal

- 使用固定 base directory；
- 通过 ID 映射到服务器路径；
- canonicalize 后确认仍在允许目录；
- 拒绝绝对路径；
- symbolic link 风险需要考虑；
- 不用字符串 replace `"../"` 作为主要防护。

## SSRF

出站 HTTP 功能先决定：

```text
是否真的需要用户指定目标?
```

最好使用固定服务/allowlist。

必须限制：

- `http/https` 协议；
- hostname；
- port；
- DNS resolution；
- loopback；
- private/link-local；
- cloud metadata 地址；
- redirect；
- DNS rebinding；
- response size；
- timeout。

解析 URL 使用成熟 parser，不自行用 regex 拆 URL。

Webhook、URL preview、image fetch、PDF fetch、OAuth metadata 等都属于 SSRF 风险入口。

## Redirect

用户提供 redirect target 时：

- 只允许相对路径；
- 或固定 origin allowlist；
- 不直接返回任意 external URL。

## XML

默认禁用：

- External Entity；
- DTD；
- external resource loading。

使用安全 parser 配置。

## Deserialization

不要反序列化不可信原生对象格式。

优先：

- JSON/Proto 等数据 Schema；
- 明确类型；
- allowlist；
- 大小/深度限制。

如果遗留格式必须 native deserialization：

- 只接受可信签名数据；
- 隔离；
- 固定允许类型；
- 持续升级库；
- 安全测试。

## Archive / Parser

复杂 parser 是攻击面。

对：

- PDF；
- Office；
- image；
- media；
- archive

考虑 sandbox/process isolation、CPU/memory timeout 和库更新。
