# 2026-09-16 首轮自跑（author self-run）

## 这是什么、不是什么

harness 的**冒烟运行 + 首轮基线数据**，不是独立的模型成绩（协议参考了同类工具的 ordinary-model-floor 惯例）：

- **跑者 = 作者本人**（同时是本 skill 与 manifest 的作者），语义门存在对齐偏置 ——
  案例就是我照着典型用法写的，"能绑上别名"不足为奇；
- 人审全部如实记 `skipped`（跑者无图像查看能力），按三门规则 `first_pass_usable`
  全部为 false —— **这不代表候选有缺陷**，代表第三门还没人看。

## 结果（5 案例，attempt 1，0 轮修复）

| 案例 | 语义门 | 校验门（showcase） | 人审 | usable | 修复轮 |
| --- | --- | --- | --- | --- | --- |
| web-runtime-architecture | pass | pass（13/13） | skipped | false* | 0 |
| release-flow | pass | pass（13/13） | skipped | false* | 0 |
| module-dependency | pass | pass（13/13） | skipped | false* | 0 |
| order-state | pass | pass（13/13） | skipped | false* | 0 |
| service-network | pass | pass（13/13） | skipped | false* | 0 |

\* false 仅因人审 skipped（设计如此：skipped 永远不能算 usable）。
**确定性可证的结论是：5/5 首轮通过语义门 + showcase 校验门，0 轮修复。**

每案例产物：`candidate.diagram.json`（冻结 attempt 1）、`render.excalidraw`、
`run.json`、`receipt.json`；逐行汇总在 `results.jsonl`。

## 过程记录（可复现）

1. 每案例以"拿到 prompt 的作者"身份按 SKILL.md 起手流程写规格（不读 manifest 的
   必须项清单，只用 prompt 原文）；
2. `validate_spec` → `emit_excalidraw --quality showcase`，全部首轮通过；
3. 候选冻结后跑 `verify.py`（三门），receipt 原样存档，无任何事后编辑。

## 下一步才是真数据

拿这套协议跑 **2~3 个未经参与开发的模型**（外部 runner 交付 prompt、冻结候选、
人工做视觉审查），才产出可发布的 first-pass 成绩 —— 那份成绩同时是
`validation.md` 里"待验证"阈值（12px/24px/交叉比）的第一批校准数据来源。
