---
name: excalidraw-diagram
description: >-
  Draw technical diagrams as editable Excalidraw files in the Obsidian vault: architecture, dependency,
  flow, state, deployment topology, and mind maps. Use when the user asks to 画图 / 画架构图 / 画流程图 /
  画依赖图 / 把这段说明画出来 / draw a diagram / visualize a system or flow. The model only describes
  structure (nodes, edges, groups); a script computes every coordinate — never hand-write positions.
  Do NOT use for editing, moving, or organizing notes (use `obsidian-personal-knowledge-base`), for
  recording completed work or release notes (use `obsidian-work-log-release-recorder`), or for
  decorative illustration, posters, or wireframes — this skill draws explanatory technical diagrams only.
  需要 vault 路径的，从 $OBSIDIAN_VAULT_PATH 或 ~/.config/obsidian-vault-path 解析，不要写死。
---

# Excalidraw 技术图

把"系统怎么运作"画成可编辑的 Excalidraw 图。**你负责理解与描述结构，脚本负责一切坐标。**

## 为什么不能由你写坐标（这条不可协商）

配色、大小、字号、排版、连线长度、遮挡 —— 这些**全部是空间计算**。让模型直接吐坐标，
本质是让它做一件它没有可靠能力的事，症状必然是"看起来还行，但总有几处别扭"。

**所以规格里没有坐标字段 —— 不是"不推荐填",是不存在这个字段。**
未来任何人都不要"顺手加个可选 x/y"：

> 一旦 schema 里有 x/y，模型就会开始填数字。这个失败已经发生过 —— 参见
> `references/diagram-spec.md` 里对前作 `draw-excalidraw` 的诊断。

## 起手流程

1. **先拿证据**：图的内容来自代码／配置／文档／运行输出。不要凭目录树猜架构。
2. **判断图类型**，查下面的策略表（类型决定布局算法，不是学美规则）。
3. **写规格**：一份 `*.diagram.json`，只有结构（节点／边／分组），见 `references/diagram-spec.md`。
4. **跑脚本**生成 `.excalidraw`。脚本自己会布局、校验、失败时调参重跑。
5. **看报告**：只有脚本自动重试耗尽时才有报告，此时按报告建议改**内容**，不要改参数。
6. **保留规格文件**，和 `.excalidraw` 放一起；以后的修改改规格再重新生成。

## 图类型 → 布局策略

| 图类型 | 关系形态 | 布局算法 | 默认方向 |
| --- | --- | --- | --- |
| `architecture` | 有向、近似无环 | 分层（简化 Sugiyama） | `LR` |
| `flow` / `state` | 有向、可能有环 | 分层 + 环回边特殊处理 | `TB` |
| `dependency` | 有向、层级明显 | 分层 | `LR` |
| `mindmap` | 中心辐射 | 径向／树形 | 无 |
| `network` | 网状、无明显层级 | 力导向 + 最小间距后处理 | 无 |

**判断类型是你的活；判断完之后的计算全是脚本的活。** 类型拿不准时问用户，不要混着套。

## 硬规则

| 规则 | 说明 |
| --- | --- |
| 不写坐标 | schema 没有 `x` / `y` / `width` / `height`。布局参数也不在 schema 里 |
| 不写颜色 | 只写 `kind`（语义角色），颜色由色板文件映射 |
| 不写字号 | 容器按文字长度落尺寸档位，字号跟档位联动 |
| `kind` 只能取色板里的值 | **未知 kind 直接判失败**，不会 fallback 到默认色 |
| 一张图一个文件 | 信息量用 `detail` 控制，不拆多视图 |
| v1 不上图标 | 图标是新的漂移源，等布局与校验闭环跑稳再加 |

## 校验与「自动调参」循环

校验由脚本做，**调参也由脚本做 —— 中间不经过你的判断**：

```text
layout(参数) → 校验 ──通过──→ 输出
                 │
                 └─失败且轮次未耗尽 → 参数按固定步长递增 → 重跑
                 └─轮次耗尽 → 出报告
```

**报告只在你无法自动收敛时出现**，而且只建议**内容层面**的修改（拆节点／缩短标签／降 `detail`／
调整分组）。报告会列出**已经试过哪些参数** —— 看到"建议调大某某间距"这种话是设计事故，请上报。

五项校验（重叠／连线过短／文字溢出／越界颜色／边交叉数）的阈值与级别见 `references/validation.md`。

## 引用文件

- `references/diagram-spec.md`：内容层契约 —— 允许写什么、刻意不存在的字段、`kind` 封闭枚举与色板、尺寸档位与字号。
- `references/validation.md`：五项校验的阈值与级别、自动调参循环的细节、报告该说什么。

## 与 PKB 的关系

`obsidian-personal-knowledge-base` 的 `references/resource-notes.md` 里原本写着"图示默认风格"
（白底／浅灰网格／浅色系／排除深色）。**风格定义已收拢到本 skill 的色板文件**，那份文档应改为指针 ——
可被机械校验的东西只有一处定义，否则必然漂移。
