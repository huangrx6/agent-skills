---
name: visual-image-understanding
description: 你必须在以下场景使用本 Skill：(a) 用户发来图片（截图、照片、文档、图表、对话/聊天截图、漫画、海报等）要求看图、读图、读界面、读报错、对比多图；(b) 你当前任务过程中涉及到任何需要理解、描述或提取信息的图片。用户只是文字提及一张图（如引用图里说过的某句话）时不调。仅支持 JPEG / PNG / WebP 三种格式；PDF / GIF / SVG / PSD 不支持（PDF 用其它工具解析、GIF 取首帧或换格式）。需三个环境变量 VISUAL_BASE_URL / VISUAL_MODEL / VISUAL_API_KEY（默认推荐智谱 glm-4.6v-flash），写在 ~/.zshrc 后重启终端或 DSH 宿主进程才生效。一条命令：`uv run scripts/visual_runtime.py <图> [多个图...]`，稠密小字 / 大图精确读取加 `--no-downscale`，针对性提问用 `--prompt "..."`，需结构化 JSON 加 `--json`。注意：路径若以 `@` 开头（如用户输入 `@/path/to/img.png`），必须先去掉 `@` 再传给脚本。不负责把 UI 截图转成可交付前端的布局规格（区域、组件、栅格、设计令牌）——那是 visual-ui-layout-spec 的工作。
---

# 快速看图

把图片发给远端视觉模型，一条命令返回详细的 Markdown 描述（概述、布局、逐字文本、关键对象、细节）。不依赖当前 Agent 自身的视觉能力。

## 唯一前置：三个环境变量

```
export VISUAL_BASE_URL=https://open.bigmodel.cn/api/paas/v4
export VISUAL_MODEL=glm-4.6v-flash
export VISUAL_API_KEY=<你的Key>
```

写在 `~/.zshrc`；**改完需重启终端/DSH 宿主进程才生效**。脚本每次运行自检，缺哪个会直接报错指出，无需单独预检步骤。

依赖 `uv`（缺失时先执行 `curl -LsSf https://astral.sh/uv/install.sh | sh`）；Pillow 由 `uv run` 按脚本内联声明自动安装。

## 用法（一条命令）

```bash
uv run scripts/visual_runtime.py <图片路径>
```

- 默认加载 `assets/prompts/quick-look.md`，输出 Markdown，**直接转述给用户即完成**，不要再压缩、表格化或二次总结。
- 稠密小字 / 大图精确读取：加 `--no-downscale`（保留原分辨率，较慢）。
- 针对性提问：`--prompt "图里的报错是什么原因"`（或 `--prompt-file`）。
- 确需机器可读 JSON：`--json`（自动修复模型常见的引号/尾逗号瑕疵）。
- 多图对比：参数里给多个路径即可。

## 行为准则

- 收到"看看这图 / 读下文字 / 界面什么样"的请求：直接跑默认命令，一次调用完成。
- 模型输出已经是分节 Markdown，转述时可原样给出；除非用户明确要求，不要改写格式。
- 错误处理：缺环境变量 → 按报错里的三行 export 指引用户配置；429 → 脚本自动退避重试；其他错误 → 原样告知用户。
