---
name: diagram-authoring
description: >-
  Create editable technical diagrams from a structure-only spec: architecture,
  dependencies, flows, states, topology, and mind maps. Use when the user asks to
  画架构图 / 画流程图 / 画依赖图 / 把说明画成图 / draw a system or flow diagram.
  Scripts calculate layout and generate .excalidraw or .drawio files, with optional
  image exports. Do NOT use for decorative illustrations, posters, UI wireframes,
  slide decks, or organizing notes and release records.
---

# 技术图

把有依据的节点与关系写成规格，由脚本计算布局并输出可编辑源文件。
默认用 Excalidraw；需要 draw.io 接手或 PDF 导出时用 draw.io。两者共享结构和布局，
但支持的图标、文字和样式有差异，不能承诺任意规格无损切换后端。

## 工作流程

1. 从用户材料、代码、配置或运行结果确认图的主题、边界和关系。不要凭目录名猜架构；
   未证实的关系先核对，或清楚标为待确认。
2. 按下表选图类型。拿不准可用 `python3 scripts/guide.py "一句话描述"` 辅助判断。
3. 读 [规格契约](references/diagram-spec.md)，写 `*.diagram.json`。规格只含结构、语义档位
   和方向约束；没有坐标、宽高、像素字号或色值。输出放在用户指定目录或当前项目中。
4. 根据用途选后端与风格。沿用用户已选方向；用户说“你看着来”就是授权自行决定。
   没有偏好时选适合内容的默认方向并说明；只有确需比较时才做主题预览，不把选主题变成制作门槛。
5. 校验并生成。emit 会校验规格、计算布局、有限调参，再原子写入；有阻塞项时不写成品。
6. 看诊断修复受影响的节点、标签、关系或分组，保留内容事实。先处理阻塞项，再看可读性和视觉。
   两轮聚焦修复仍没有进展时，报告具体限制，考虑拆成总览与细节图，不反复盲试。
7. 用真实渲染审查后交付源规格、可编辑文件和用户需要的导出格式。未做的检查明确说明。

以下命令从 skill 目录执行；在其他目录使用脚本绝对路径：

```sh
python3 scripts/validate_spec.py /path/to/system.diagram.json
python3 scripts/emit_excalidraw.py /path/to/system.diagram.json --quality showcase
# 或：
python3 scripts/emit_drawio.py /path/to/system.diagram.json --quality showcase
```

`standard` 是默认诊断档，部分连线问题只警告；`showcase` 将结构类警告升级为阻塞。
对外展示优先用 showcase。真实关系无法无交叉表达时，不删边凑过关；解释残留、拆视图，
或有依据地使用 standard 并披露限制。通过检查只证明所检查的性质，不证明图正确或好看。

## 图型与后端

| `type` | 布局 | 默认方向 |
| --- | --- | --- |
| `architecture` / `dependency` | 分层 | `LR` |
| `flow` / `state` | 分层，处理环回边 | `TB` |
| `mindmap` | 径向 | 不适用 |
| `network` | 力导向 | 不适用 |

| 后端 | 适用 | 当前边界 |
| --- | --- | --- |
| Excalidraw（默认） | 手绘感、图标、可编辑 JSON；可选 PNG/SVG | 编辑器可能重新折行；官方导出需要浏览器 |
| draw.io | 工程图、原生基本形状、多页 `.drawio`；可选 PNG/SVG/PDF | 只支持契约中的七种形状；拒绝 `icon`，不生成完整 UML/BPMN/云图元库 |

Excalidraw 用 `visual` 选择五个方向或 `auto`；draw.io 用 `--scheme` 选择五套方案，
可用 `--seed accent=<品牌色>` 覆盖种子。参数由作者落实，用户只需表达视觉意图。
需要真实比较时：

```sh
python3 scripts/direction_preview.py /path/to/system.diagram.json -o /tmp/directions/
python3 scripts/scheme_preview.py -o /tmp/schemes.drawio
```

## 可读性与交付

- 节点写短标签，细节用 `detail` 或图下 `cards`；连线标签说明关系，不复述节点名。
- `kind` 表示角色，`emphasis` 表示重点。保持少量明确焦点，同一语义使用同一形状与图标。
- 分组表达真实边界，不能为了排得整齐把无关节点归在一起。复杂图可拆视图并保留跨图对应关系。
- 图标先查名称；常见语义用内置 sigil，需要品牌图标再查素材库。draw.io 不支持图标，不能悄悄删除。
- 实测布局与真实渲染分开报告：自研 preview 只能看布局模型；官方导出后仍需目视核对文字、连线和重点。
- 只在用户要求放入 Obsidian 时解析 `$OBSIDIAN_VAULT_PATH`，其次读取
  `~/.config/agent-skills/obsidian-vault-path`；不能因默认后端是 Excalidraw 就写入外部 vault。
  官网打开工具也仅在需要官网编辑时使用。

## 按需阅读

- [规格契约](references/diagram-spec.md)：写 spec 前读；字段、枚举、分组、约束和可运行示例。
- [视觉审查](references/visual-design.md)：选重点、改善疏密与真实渲染审稿。
- [校验与修复](references/validation.md)：诊断级别、回执、有限调参和检查盲区。
- [Excalidraw 后端](references/excalidraw-backend.md)：导出、编辑和文字重排限制。
- [draw.io 后端](references/drawio-backend.md)：配色、多页、基本形状与导出限制。
- [图标](references/icons.md)：需要图标时读；内置目录、外部库、颜色和许可边界。
