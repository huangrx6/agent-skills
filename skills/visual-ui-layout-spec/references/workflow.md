# UI Layout Spec 工作流（动态 Provider + 证据融合）

## 0. Resolve Visual Provider

按 SKILL.md 规则判断：`VISUAL_REMOTE=true` → 远端；否则 Agent 能原生读图 → Host 分支；不能读图 → 远端；都不可用 → 明确告知用户（测量轨仍可独立运行）。无需脚本判定。

## 1. Preflight

运行 `image_probe.py info`；必要时 `quality`。确定截图尺寸、缩放风险和输出位置。

## 2. One Semantic Pass

先对整图做一次 UI Semantic Pass：

- Host：当前 Agent + `assets/prompts/ui-semantic.md`；
- Remote：`visual_runtime.py remote-analyze ...`。

目标是一次拿到 regions/components/text/states/charts/tables，不要默认每区调用 VLM。

## 3. Measurement Plan

根据 Semantic 结果和原图选择最小探测：`palette/pick/runs/bands/grid/crop`。

## 4. Targeted Repair

只有低置信度小字/组件才 crop，然后重新调用 Host/Remote 或 OCR。记录 targeted pass 的原因。

## 5. Evidence Merge

Semantic evidence 与 Probe evidence 合并：

- 组件类型、视觉状态来自 Semantic；
- px、边界、色值优先来自 Probe；
- 冲突时保留双方证据并进入待确认，不静默选一个。

## 6. Spec

生成 §1–§10。Observed / Normalized / Recommended 分列。

## 7. Degradation

Remote 失败按 Resolver fallback。只有 OCR + Probe 时可以输出文字/几何的部分规格，但必须把组件语义、风格判断等标成 degraded/unknown。

## 8. Validate

运行 `validate_layout_spec.py` 和 Self-check。
