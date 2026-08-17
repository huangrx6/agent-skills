# Remote VLM / vLLM 实施说明

## 协议

Skill 只依赖 **OpenAI-compatible multimodal Chat Completions**，不依赖 vLLM 私有 Python API。因此后端可以是 vLLM，也可以替换为其他兼容网关。

vLLM 当前支持多模态模型通过 OpenAI-compatible server 接收图片输入，但前提是部署的具体模型本身支持 image modality，并具有可用 chat template。

## 图片传输

默认使用本地文件转 Base64 Data URL：

```text
local image
→ data:image/...;base64,...
→ image_url content part
→ /chat/completions
```

优点：

- VLM Server 不需要访问调用方提供的 URL；
- 避免任意 URL fetch 带来的 SSRF；
- 本地/私有图片不需要先上传公网地址。

## URL 模式

如果企业网关需要 URL 输入，必须单独设计受控上传服务或 allowlist。

vLLM 官方多模态文档建议在允许媒体 URL 时配置：

```text
--allowed-media-domains ...
VLLM_MEDIA_URL_ALLOW_REDIRECTS=0
```

同时限制 VLM 节点网络访问范围。

## Capability 声明

配置中的：

```json
"capabilities": {
  "image": true,
  "multi_image": true,
  "json_object": false,
  "max_images": 4
}
```

是**部署能力声明**，不是 Skill 猜测。

换模型、chat template、`--limit-mm-per-prompt` 等服务参数后，需要同步更新能力声明。

## Structured Output

只有确认当前服务/模型组合支持 JSON object/structured output 时才配置 `json_object=true`。

否则 Prompt 仍要求输出 JSON，然后由本地 validator 解析和校验；不要因为服务返回 HTTP 200 就假设结构正确。
