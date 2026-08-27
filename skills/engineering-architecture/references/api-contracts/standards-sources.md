# 标准与权威来源

## 目录

- [HTTP](#http)
- [错误响应](#错误响应)
- [OpenAPI 与 JSON Schema](#openapi-与-json-schema)
- [生命周期与链接](#生命周期与链接)
- [RPC 与事件](#rpc-与事件)
- [使用原则](#使用原则)

## HTTP

- RFC 9110 — HTTP Semantics  
  <https://www.rfc-editor.org/rfc/rfc9110>

定义 HTTP 方法、安全性、幂等性、状态码、字段和内容协商等核心语义。

- RFC 9111 — HTTP Caching  
  <https://www.rfc-editor.org/rfc/rfc9111>

- RFC 6585 — Additional HTTP Status Codes  
  <https://www.rfc-editor.org/rfc/rfc6585>

包含 428 和 429 等状态码。

- RFC 7240 — Prefer Header for HTTP  
  <https://www.rfc-editor.org/rfc/rfc7240>

- RFC 8288 — Web Linking  
  <https://www.rfc-editor.org/rfc/rfc8288>

## 错误响应

- RFC 9457 — Problem Details for HTTP APIs  
  <https://www.rfc-editor.org/rfc/rfc9457>

RFC 9457 已取代 RFC 7807。详细落地由异常处理层负责。

## OpenAPI 与 JSON Schema

- OpenAPI Specification 官方索引  
  <https://spec.openapis.org/oas/>

官方索引列出已发布的 3.2、3.1 和 3.0 系列。项目应固定工具链完整支持的精确版本。

- JSON Schema Draft 2020-12  
  <https://json-schema.org/draft/2020-12>

OpenAPI 3.1 系列与 JSON Schema 2020-12 语义对齐；其他版本按对应规范能力使用。

## 生命周期与链接

- RFC 9745 — Deprecation HTTP Response Header Field  
  <https://www.rfc-editor.org/rfc/rfc9745>

- RFC 8594 — Sunset HTTP Header Field  
  <https://www.rfc-editor.org/rfc/rfc8594>

Deprecation 表达已弃用状态；Sunset 表达预计停止响应的时间。

## RPC 与事件

- gRPC Status Codes  
  <https://grpc.io/docs/guides/status-codes/>

- gRPC Deadlines  
  <https://grpc.io/docs/guides/deadlines/>

- Protocol Buffers Programming Guides  
  <https://protobuf.dev/programming-guides/>

- Protocol Buffers Best Practices  
  <https://protobuf.dev/best-practices/dos-donts/>

- AsyncAPI Specification  
  <https://www.asyncapi.com/docs/reference/specification/latest>

## 使用原则

- 优先使用标准发布方和官方项目文档。
- 标准文本与辅助 Schema 冲突时，以标准文本为准。
- 实施时检查当前勘误、版本和工具链支持。
- 区分协议强制要求、官方建议和组织风格选择。
- 不把某一家公司的 API 指南描述为所有项目的官方规则。
