# Visual Runtime：语义轨选择 + 远端 VLM

## 目标

`visual-*` Skill 不绑定某个模型或某个 Agent。语义分析走 Agent 原生视觉还是远端 VLM，由一条规则决定。

## 选择规则（无配置文件，无检测脚本）

```
VISUAL_REMOTE=true  →  一律走远端 VLM
否则                 →  Agent 能原生读图 → 原生视觉执行（本脚本不参与）
                      Agent 不能读图   →  远端 VLM
都不可用             →  明确告知用户"无法进行视觉语义分析"；测量轨（image_probe）仍可独立运行
```

- **Agent 自知能否读图**：多模态 Agent 直接看图，不需要任何脚本判定；无视觉的 Agent 也清楚自己看不到。唯一的外部开关是 `VISUAL_REMOTE`（`printenv VISUAL_REMOTE` 检查，值为 `true` 才强制远端）。
- 典型场景：宿主为纯文本模型（如 glm-5.3）时设置 `VISUAL_REMOTE=true`，或依赖"Agent 不能读图 → 自动走远端"的默认路径，两者等效。

## 远端 Provider

OpenAI-compatible Chat Completions，仅需三个环境变量：

```text
VISUAL_BASE_URL=https://open.bigmodel.cn/api/paas/v4
VISUAL_MODEL=glm-4.6v-flash
VISUAL_API_KEY=<你的Key>
```

调用（脚本自检变量；缺哪个点名哪个，并给出三行 export 指引）：

```bash
uv run scripts/visual_runtime.py remote-analyze image.png \
  --prompt-file assets/prompts/<profile>.md --result-only
```

内置行为：发送前降采样 + JPEG 压缩（省 token，`--no-downscale` 关闭）、429 退避重试（读 Retry-After）、模型 JSON 输出自动修复（围栏剥离/尾逗号/CJK 未转义引号）、`--result-only` 时自动 normalize。

## 安全

本地图片以 Base64 Data URL 发送，不让远端 VLM 抓取任意 URL，减少 SSRF 面。自部署 vLLM 若开放媒体 URL，见 [remote-vllm.md](remote-vllm.md)。历史版本的 `.visual/` 配置文件与 `VISUAL_RUNTIME_CONFIG` / `--config` 已移除（`--config` 仍被接受但静默忽略）。
