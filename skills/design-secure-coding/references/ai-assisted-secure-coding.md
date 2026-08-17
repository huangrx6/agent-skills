# AI 辅助编码安全

## 目录

- [信任模型](#信任模型)
- [开始任务](#开始任务)
- [生成代码](#生成代码)
- [新增依赖](#新增依赖)
- [敏感上下文](#敏感上下文)
- [高风险修改](#高风险修改)
- [完成任务](#完成任务)

## 信任模型

模型输出不是安全事实来源。

视为：

```text
experienced but untrusted contributor draft
```

它可以提高速度，但不能替代：

- compiler；
- tests；
- SAST；
- dependency scanner；
- secret scanner；
- human/security review。

## 开始任务

Agent 先读取：

- 项目安全规范；
- 相关架构信任边界；
- API/数据库契约；
- 附近安全封装和已有模式。

不要为“完成任务快”自行发明新的 auth、crypto、HTTP client 或 secret 方案。

## 生成代码

Agent 必须特别检查：

- string query；
- shell command；
- path；
- redirect；
- URL fetch；
- `eval`；
- unsafe deserialization；
- auth bypass；
- insecure random；
- TLS verification；
- broad CORS；
- debug endpoint；
- logging secrets。

## 新增依赖

在安装前验证真实来源。

对于陌生 package：

1. 查询官方 registry；
2. 确认 exact package；
3. 确认 publisher/repository；
4. 检查项目是否维护；
5. 检查安全与 license；
6. 再安装。

如果无法确认，不得“试着装一下”。

## 敏感上下文

不要把以下内容发送给不允许接收该数据的外部 AI 服务：

- production secret；
- access token；
- private key；
- complete customer data；
- protected source code；
- confidential incident dump。

使用脱敏、最小上下文或组织批准的 AI 环境。

## 高风险修改

以下修改升级评审级别：

- authentication；
- authorization；
- session/token；
- cryptography；
- payment；
- admin；
- data export；
- file upload/parser；
- SSRF/HTTP fetch；
- serialization；
- template；
- command execution；
- sandbox；
- secrets；
- multi-tenant isolation。

至少增加：

- threat review；
- negative tests；
- diff review；
- static/security scans。

## 完成任务

Agent 在结束前检查最终 diff：

```text
1. 有没有新 Source?
2. 有没有新 Sink?
3. 权限边界是否变化?
4. 是否新增 Secret/敏感数据?
5. 是否新增 dependency?
6. 是否扩大网络/文件访问?
7. 是否降低验证/安全 Header?
8. 是否需要新的安全测试?
9. 有没有临时 bypass?
```

最终总结应说明安全影响，而不是只说“测试通过”。
