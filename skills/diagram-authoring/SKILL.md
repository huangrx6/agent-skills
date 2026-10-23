---
name: diagram-authoring
description: >-
  Create editable technical diagrams from a structure-only spec: architecture,
  dependencies, flows, states, topology, and mind maps. Use when the user asks to
  画架构图 / 画流程图 / 画依赖图 / 把说明画成图 / draw a system or flow diagram.
  Scripts calculate layout and generate .excalidraw, .drawio or Mermaid .mmd files, with optional
  image exports. Do NOT use for decorative illustrations, posters, UI wireframes,
  slide decks, or organizing notes and release records.
---

# 技术图

把有依据的节点与关系写成规格，由脚本计算布局并输出可编辑源文件。
默认用 Excalidraw；需要 draw.io 接手或 PDF 导出时用 draw.io；需要文本图或明确要求 Mermaid 时用 Mermaid。
前两者共享结构和布局；Mermaid 使用自己的布局引擎。各后端的形状、约束和样式不同，不承诺无损切换。

## 用户决定内容与视觉

默认按 **内容（含分层方向） → 配色 → 图标（Excalidraw）→ 生成** 顺序执行。
每到一个节点，先给出基于用户条件的具体提案，再提出一个确认问题，**停止并等待用户回复**；
未确认不进入下一节点、不生成最终图、不覆盖现有图或同步图片。所有图型/后端均适用内容与配色确认。
用户已明确确认的选择不重复询问；“你看着来”用于准备推荐，不默认取消等待。
只有用户明确免确认时才在其授权范围内跳过。完整提案内容、回复判定、修订与恢复见
[逐步确认](references/decision-gates.md)，开始作图前阅读。

## 工作流程

1. 从用户材料、代码、配置或运行结果确认图的主题、边界和关系。不要凭目录名猜架构；
   未证实的关系先核对，或清楚标为待确认。
2. 明确一句读者问题、受众和观看场景；需要行为解释时读 [表达模式](references/semantic-patterns.md)。
   按下表选图类型并读 [图型规则](references/type-guides.md) 的对应段；同时按内容形态给出分层方向建议（LR/TB）。
   默认方向只是起手值，不能每次都直接沿用。拿不准可用 `python3 scripts/guide.py "一句话描述"` 辅助判断。
   需要一张画布内横竖混排时，读 [混合方向](references/mixed-direction.md)，用面板式组合，不要用单图 `direction` 硬掰。
3. 提交内容提案：列清主题、图型/后端、分层方向（LR/TB 及依据）、分组节点、关系、信息取舍与单图/多图安排，等待用户确认。
   用户明确说“横着/竖着”时直接采用，不再把方向当成待猜的偏好。
   确认后读 [规格契约](references/diagram-spec.md)，写 `*.diagram.json`。规格只含结构、语义档位
   和方向约束；没有坐标、宽高、像素字号或色值。输出放在用户指定目录或当前项目中。
   新图默认一图一目录，规格与配色放该图的 `.source/`，成品放外层；具体路径优先遵守用户要求和已有引用，见 [文件组织](references/delivery-files.md)。
4. 根据用途选后端、风格和 `--preset` 场景；预设会重新测量字号、盒子与间距。沿用用户已确认的选择；未确认的视觉方向先作为提案。
   配色先看用户参考/品牌和当前图的作用，读 [自由配色](references/color-design.md)，用项目 `*.colors.json` 落实；
   不把旧方向当固定色板；默认中性节点与少量重点色，仅在有助理解时增加分类色。没有偏好时给出具体推荐。说明颜色如何分配到画布、节点、重点和分区，等待用户确认，再落实配色。仅需要比较时做小范围示意，不默认生成图片。
   分层/分区难辨时，可用 `by_group` 指定不同浅底色，独立于节点重点色；大面积纹理可能干扰连线，按实际效果选择实心底色。
   用户要求整块区域底色时，逐一核对涉及的分组都有填充，不能只给入口和基础设施上色；中间层的 neutral 名称不应使明确指定的区域配色失效。
   配色确认后，Excalidraw 提交图标方案：是否使用、具体素材/风格、节点覆盖数量与比例、大小/位置、颜色处理；
   等待用户确认后才设置 icon。draw.io/Mermaid 不支持图标，此节点说明为不适用；有图标诉求先解决后端选择。
5. 适用节点均确认后，校验规格并运行 `scripts/check_semantics.py`，对照来源处理语义提示；不自动删改事实。
   Mermaid 路径先读 [Mermaid 后端](references/mermaid-backend.md)：使用 `emit_mermaid.py`，再用 `check_mermaid.py` 做官方语法检查；不运行下面的几何/观看检查，完成后进入第 8 步。
   Excalidraw/draw.io 的 emit 会校验规格、计算布局、有限调参，再原子写入；有阻塞项时不写成品。
6. 看诊断修复受影响的节点、标签、关系或分组，保留内容事实。先处理阻塞项，再看可读性和视觉。
   两轮聚焦修复仍没有进展时，报告具体限制，考虑拆成总览与细节图，不反复盲试。
7. 运行 `scripts/check_presentation.py 成品 --preset 场景` 检查预计观看字号；
   生成器提示装不下时调整方向、拆视图或换观看场景，不缩字删边。默认不为验收额外导出 PNG/SVG；
   可在编辑器中目检，未做真实渲染检查时如实标明。需要导出时再检查实际渲染；能力边界见 [观看场景](references/output-presets.md)。
   Excalidraw 密集图另跑 `scripts/readable_routing.py 成品.excalidraw`，检查近距离平行线、实际交叉及标签到线/边框的间隔；它检查原生几何，不代替真实字体审查。
8. 新建或更新原生图后运行 `dev-tools/sync_exports.py 成品`：没有已有导出时不生成任何图片；
   有同名 PNG/SVG（Mermaid 同样适用，draw.io 还支持 PDF/JPG）则同步全部已有格式，失败要明确提示旧图未同步。
   用户本次要求的新格式用 `--format` 添加；没有导出需求时交付原生图，并简短提示“需要时可导出 PNG/SVG”，无需为此停下来追问。

以下命令在适用确认节点完成后从 skill 目录执行；在其他目录使用脚本绝对路径：

```sh
python3 scripts/validate_spec.py /path/to/diagrams/system/.source/system.diagram.json
python3 scripts/check_semantics.py /path/to/diagrams/system/.source/system.diagram.json --json
python3 scripts/emit_excalidraw.py /path/to/diagrams/system/.source/system.diagram.json --quality showcase
python3 dev-tools/sync_exports.py /path/to/diagrams/system/system.excalidraw
# 或：
python3 scripts/emit_drawio.py /path/to/diagrams/system/.source/system.diagram.json --quality showcase
python3 dev-tools/sync_exports.py /path/to/diagrams/system/system.drawio
```

`standard` 是默认诊断档，部分连线问题只警告；`showcase` 将结构类警告升级为阻塞。
对外展示优先用 showcase。真实关系无法无交叉表达时，不删边凑过关；解释残留、拆视图，
或有依据地使用 standard 并披露限制。通过检查只证明所检查的性质，不证明图正确或好看。

## 图型与后端

| `type` | 布局 | 默认方向（起手值） |
| --- | --- | --- |
| `architecture` | 分层 | `LR` |
| `dependency` | 分层 | `TB` |
| `flow` | 分层，处理环回边 | `TB` |
| `state` | 分层，处理环回边；暂不支持自环 | `LR` |
| `mindmap` | 径向 | 不适用 |
| `network` | 力导向 | 不适用 |

默认方向只用于起手，不是锁定值；分层图用规格里的 `direction` 覆盖。
横向流水线、阶段推进、分支并排或 16:9 幻灯片优先 `LR`；纵向步骤、窄栏文档或移动端优先 `TB`。
用户说“横着/竖着”时按其选择执行；拿不准可用 `python3 scripts/direction_preview.py` 对比，
不要每次都落回 `flow`/`dependency` 的默认 `TB`。
同一画布需要横竖混排时，用 `scripts/compose_panels.py` 把独立面板拼起来；跨面板连线不自动生成。

| 后端 | 适用 | 当前边界 |
| --- | --- | --- |
| Excalidraw（默认） | 手绘感、图标、可编辑 JSON；可选 PNG/SVG | 编辑器可能重新折行；官方导出需要浏览器 |
| draw.io | 工程图、原生基本形状、多页 `.drawio`；可选 PNG/SVG/PDF | 七种基本形状；无图标/完整专用图库；多页图片需指定页码，PDF 默认全页 |
| Mermaid | 文本 `.mmd`；架构、依赖、流程、普通状态图；可选 PNG/SVG | 自有布局；不支持 icon/rank/pin；状态图转换限制见后端说明 |

三后端都支持 `--colors 项目.colors.json`：任意颜色、节点角色/ID 分配、自由填充比例，
可从网站、参考图、品牌或任意主色起步，详见 [自由配色](references/color-design.md)。
Excalidraw 的 `visual` 和 draw.io 的 `--scheme` 保留旧画法；自定义配色覆盖其中颜色。
旧 draw.io `--seed` 仍兼容，与 `--colors` 不混用。参数由作者落实，用户只需表达视觉意图。
需要真实比较时：

```sh
python3 scripts/direction_preview.py -o /tmp/directions.excalidraw
python3 scripts/scheme_preview.py -o /tmp/schemes.drawio
```

## 可读性与交付

- 默认只交付一种可编辑格式，不主动生成 PNG/SVG/PDF。用户要求导出时生成指定格式；更新图时刷新已存在的格式，不额外增加格式。
  规格、配色和必要的导出参数保存在 `.source/`；需运行的诊断和试稿放临时目录，不借验收之名默认生成一套图片。
  不为每张图另生成 README、HTML 展示页或多个版本副本；修订更新原路径，必要的正文说明仍须保留。
- Excalidraw/Mermaid 图片默认留白 80 图内单位，PNG/SVG 一致；draw.io 名义留白也为 80，但官方四边分配可能不均。自然尺寸按内容边界向外扩展。
  用户要求加大图片边距时调整导出留白，不用拉开节点代替。固定宽高时增加留白会压缩内容可用空间，须复核字号。
- 节点写短标签，细节用 `detail` 或图下 `cards`；连线标签说明关系，不复述节点名。
  已确认的长文先扩宽、按段落换行并增加内边距，不能缩字、截断或擅自摘要。长说明卡在主图之后，
  不作为孤立业务节点挤到顶部；若仍过长，提交拆图或移入正文的方案，等待内容确认。
- `kind` 表示角色，`emphasis` 表示重点。保持少量明确焦点，同一语义使用同一形状与图标。
- 分组表达真实边界，不能为了排得整齐把无关节点归在一起。复杂图可拆视图并保留跨图对应关系。
  上下分层要看分组外框之间的净空；节点间距还会被标题带和内边距占用。标题较长且通道密集时可保留全文换行。
  多条长线难以追踪时，先调整节点次序、引出端口和层间空间；仍拥挤时按读者问题拆图，使用 [视图覆盖核对](references/reading-views.md) 防止漏边。
- 图标方案先查实际素材，再提交确认；常见语义可推荐内置 sigil，需要品牌图标再查素材库。draw.io/Mermaid 生成器不支持图标，不能悄悄删除。
- 实测布局与真实渲染分开报告：自研 preview 只能看布局模型；官方导出后仍需目视核对文字、连线和重点。
- 只在用户要求放入 Obsidian 时解析 `$OBSIDIAN_VAULT_PATH`，其次读取
  `~/.agent-skills/config/obsidian-vault-path`；不能因默认后端是 Excalidraw 就写入外部 vault。
  官网打开工具也仅在需要官网编辑时使用。

## 按需阅读

- [逐步确认](references/decision-gates.md)：作图前必读；内容、配色、图标提案与等待规则。

- [表达模式](references/semantic-patterns.md)：先确定要解释的行为与必要信息。
- [图型规则](references/type-guides.md)：选型后读对应段；专属语义、反例与能力限制。
- [混合方向](references/mixed-direction.md)：同画布 LR/TB 面板式组合的边界与命令。
- [观看场景](references/output-presets.md)：文档、投影与打印检查的命令及边界。
- [文件组织](references/delivery-files.md)：一图一目录、最少交付格式、源文件保留与旧引用迁移。
- [标准样例](examples/README.md)：起手前选同图型参考；样例不代替当前产物验收。

- [规格契约](references/diagram-spec.md)：写 spec 前读；字段、枚举、分组、约束和可运行示例。
- [视觉审查](references/visual-design.md)：选重点、改善疏密与真实渲染审稿。
- [校验与修复](references/validation.md)：诊断级别、回执、有限调参和检查盲区。
- [Excalidraw 后端](references/excalidraw-backend.md)：导出、编辑和文字重排限制。
- [draw.io 后端](references/drawio-backend.md)：配色、多页、基本形状与导出限制。
- [Mermaid 后端](references/mermaid-backend.md)：文本生成、官方语法检查、按需导出与映射边界。
- [图标](references/icons.md)：需要图标时读；内置目录、外部库、颜色和许可边界。
