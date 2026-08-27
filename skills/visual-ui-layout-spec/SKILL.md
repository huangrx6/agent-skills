---
name: visual-ui-layout-spec
description: "你必须使用本 Skill 把 UI 截图、数据大屏、设计稿图片转成可直接交付前端和 AI Coding Agent 的页面布局规格（区域、组件、栅格、尺寸、间距、颜色、字号、圆角、边框、阴影、状态、组件文案、图表与表格），保留证据与置信度。视觉语义采用 Agent 原生视觉 + 远端 VLM（VISUAL_REMOTE=true 强制远端，否则优先原生）+ image_probe.py 像素级确定性测量双轨证据。仅支持 JPEG / PNG / WebP 三种格式；PDF / GIF / SVG / PSD 不支持（PDF 需先转换页面为图片）。需环境变量 VISUAL_REMOTE / VISUAL_BASE_URL / VISUAL_MODEL / VISUAL_API_KEY 写在 ~/.zshrc 并重启终端或 DSH 宿主进程才生效。路径以 `@` 开头（如 `@/path/to/img.png`）必须先去掉 `@` 再传给脚本。不负责通用图片语义理解（纯文字提取、对象关系、架构图节点解析）"
---

# UI 布局规格解析

## 目标

把 UI 截图转为"能照着实现"的规格，同时把两类证据严格分离：

- **视觉语义证据**：区域、组件、文案、状态、层级——由 Host 原生视觉或远端 VLM 提供；
- **确定性测量证据**：坐标、边界、间距、颜色——由 `image_probe.py` 提供。

本 Skill 不假设当前 Agent 一定能看图。

## 职责边界

**负责**：UI 布局规格化（区域、组件、文案、状态、栅格、间距、颜色、字号、圆角、阴影）；双轨证据融合；设计令牌 Observed / Normalized / Recommended 三态标注；Evidence Ledger。

**不负责**：通用图片语义理解（文字提取、对象关系、架构图节点）；视觉生成；前端代码实现（仅交付规格）。嵌入页面的架构图/流程图，其位置与容器规格属本 Skill，图内节点/关系不属。

## 前置条件（零配置）

本 Skill 不绑定 DSH，可在任意 Agent（Claude Code / Codex / opencode / DSH 等）下运行。**无需任何配置文件**。语义轨怎么走，按下面一条规则判断（Agent 自知能否读图，不需要脚本判定）：

```
VISUAL_REMOTE=true  →  一律走远端 VLM
否则                 →  Agent 能原生读图 → Host 分支（用原生视觉按 ui-semantic.md 输出）
                      Agent 不能读图   → 走远端 VLM
两个都不可用          →  明确告知用户"无法进行视觉语义分析"，不要编造；
                        测量轨（image_probe.py）仍可独立运行
```

- `VISUAL_REMOTE` 检查方式：`printenv VISUAL_REMOTE`（值为 `true` 才强制远端；其他值/未设置均表示"优先原生"）。
- 远端只需 `VISUAL_BASE_URL` / `VISUAL_MODEL` / `VISUAL_API_KEY` 三个环境变量（写在 `~/.zshrc`，改后需重启终端或宿主进程）；缺失时脚本会点名缺哪个并给出三行 export 指引。

依赖 `uv`（缺失时 `curl -LsSf https://astral.sh/uv/install.sh | sh`）；Pillow 由 `uv run` 按脚本内联声明自动安装。

## 双轨工作流

### 加载原则

渐进加载，**不要一次性加载全部 references**：SKILL.md 始终在上下文；按"参考文件选择"只读本次任务相关的 1–2 个 reference。简单页面（提取区域/文案）只需本文 + prompt + measurement-strategy。

### A. Semantic Track（一次完整 pass）

尽量对原图做**一次完整 UI semantic pass**，一次返回全部区域、组件、可见文字、状态、图表/表格结构和不确定项：

- **Host 分支**：Agent 用自身可用的图片读取能力（原生视觉 / 读图工具 / 用户直接提供图片内容）按 `assets/prompts/ui-semantic.md` 的要求输出 JSON。
- **Remote 分支**：

```bash
uv run scripts/visual_runtime.py remote-analyze <图片> \
  --prompt-file assets/prompts/ui-semantic.md --result-only
```

（脚本自动降采样发送、429 退避重试、修复模型 JSON 常见瑕疵并 normalize。）

只有某区域看不清时才 `crop → targeted pass`；**禁止默认每个区域都重新调用一次 VLM**。

### B. Measurement Track

根据证据缺口运行最小探测集：

- `info/quality`：画布与质量；
- `palette/pick`：颜色；
- `runs`：卡片宽、间距、边界；
- `bands/grid`：复杂区域切分；
- `crop`：局部放大与定向再分析。

最终把两个 Track 合并为 Evidence Ledger 和 §1–§10 布局规格。

## 最小证据集

普通页面至少：1 次 `info`；2 轮 `palette`；1 次完整 Semantic Pass；对关键容器至少一个 `runs` / `pick` / crop 测量证据。不强制每页 `grid + bands`，不强制每区域 crop。

## 硬规则

- VLM 不能提供精确像素事实；具体 px/hex 优先以 `image_probe.py` 为准。
- `observed`、`normalized`、`recommended` 不混写。
- 文案逐字；看不清则 unknown/待确认。
- 单图无法证明 hover/loading/error/响应式断点。
- 不添加图中不存在的按钮、分页、字段和交互。
- Agent 不能读图且 `VISUAL_REMOTE=true` 但远端变量缺失时，按脚本指引配置；不得"试着假装看图"或编造语义。
- Remote 失败时向用户报告具体错误；只剩 OCR 时必须标记语义能力降级。

## Remote 安全

本地截图以 Base64 Data URL 发送给远端 VLM，不让 VLM Server 抓取任意图片 URL。vLLM 自部署的 SSRF 限制见 [references/remote-vllm.md](references/remote-vllm.md)。

## 输出结构

完整布局规格优先采用：

1. §1 来源、画布与页面骨架（含 ASCII 线框 + 区域索引 + 页面级栅格）；
2. §2 设计令牌（颜色/字号/间距/圆角/边框/阴影；Observed/Normalized/Recommended）；
3. §3 分区详解（每个 R-n：bbox、布局、容器、组件、文案、状态、Evidence IDs）；
4. §4 复用组件规格库；
5. §5 图表与表格规格；
6. §6 文案与数据清单；
7. §7 状态与响应式；
8. §8 实现提示；
9. §9 待确认清单（Low Confidence 项必入）；
10. §10 自检与 Evidence Ledger。

输出模式：Markdown（默认，按 `assets/layout-spec.template.md` 填充）；JSON（用户显式要求时按 `assets/ui-layout-model.schema.json`）。

默认交付位置：`openspec/sdlc-agent/页面布局说明/<页面名>-布局说明.md`；目录不存在时用 `artifacts/ui-layout/<页面名>-布局说明.md`。

## 参考文件选择

- Provider 解析细节、Host 视觉检测链、远端变量：[references/visual-runtime.md](references/visual-runtime.md)
- vLLM 自部署、SSRF 防护：[references/remote-vllm.md](references/remote-vllm.md)
- 端到端执行流程：[references/workflow.md](references/workflow.md)
- 区域、尺寸测量、grid/runs/bands 策略：[references/measurement-strategy.md](references/measurement-strategy.md)
- 字号、颜色、圆角、阴影、设计令牌：[references/typography-color-style.md](references/typography-color-style.md)
- 组件、图表、表格规格化：[references/components-charts-tables.md](references/components-charts-tables.md)
- 状态与响应式断点：[references/states-responsive.md](references/states-responsive.md)
- Evidence Ledger、置信度：[references/evidence-confidence.md](references/evidence-confidence.md)

## 内置资源

- `assets/prompts/ui-semantic.md`：Host/Remote 共用 UI 语义 Profile
- `assets/layout-spec.template.md`：Markdown 输出模板（§1–§10）
- `assets/ui-layout-model.schema.json`：机器结果 Schema
- `assets/self-check.csv`：布局规格自检清单
- `examples/`：虚构页面布局规格样例（仅作结构参照）
- `scripts/visual_runtime.py`：零配置 Provider 解析 + 远端 VLM Adapter
- `scripts/image_probe.py`：像素级确定性测量（info/quality/grid/bands/crop/palette/pick/runs）
- `scripts/validate_layout_spec.py`：布局规格 Markdown 校验
- `scripts/validate_skill_assets.py`：Skill 资产校验

修改资产后运行：`uv run scripts/validate_skill_assets.py .`
