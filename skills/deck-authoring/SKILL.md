---
name: deck-authoring
description: >-
  Create presentation decks from a structural spec with a project-specific visual style,
  browser previews, and HTML, PDF, PNG, editable or image-based PPTX, and slide videos.
  Use when the user asks 做一份 deck / 做幻灯片 / 做个 PPT / 把材料做成演示, including a requested visual direction.
  Keep content separate from style and brand, inspect real rendered pages, and validate exports.
  Do NOT use for editing an existing PowerPoint file, chart-only deliverables, standalone
  slide images without deck structure, or multi-shot motion-design films.
---

# Deck authoring

将材料整理成有论证、有节奏的演示，写入项目规格文件，再编译为可演讲的 HTML 与所需格式。
内容层不写坐标、像素字号或色值；作者在风格层设计排印、配色与构图，浏览器计算真实几何。
风格仍按每份 deck 自建，放在 **deck 项目**的 `styles/<名>/`，不向 skill 目录写风格或示例资产。

## 工作方式

先明确观众、观看方式、核心结论、页数或时长、交付格式。已有材料足够就推进，缺失事实不要编造。
用户指定的风格、品牌、授权与前面已经做出的选择持续有效，不重复确认。

- **探索方向**：没有明确方向时，用同一份代表内容做三版真实预览。每版同时体现字体、构图、
  密度与配色，说明为什么适合本次内容；任意两版至少在两个维度不同，包含构图差异。
- **已定方向**：沿用选择做代表页，不强制重新选三轮风格和配色。用户授权自行决定时，说明取舍后继续。
- **内容与视觉一起预览**：页序、每页结论、证据载体与关键页样张放在一起审。
  优先验证封面、最密内容页、图表页和图文页，再扩展全篇。
- **素材交接按需要进行**：用户自己出图时交付逐槽位提示词；已有真实素材直接验收；
  获授权且有可用生图后端时完成生成，不要求用户替工具链搬运提示词。

方向草稿可用临时目录，选定后将风格落在项目中。显式目录路径的调用示例：

```bash
python3 scripts/render.py spec.json --style /tmp/dir-a -o /tmp/a.html
python3 scripts/shots.py /tmp/a.html --out-dir /tmp/a-pages --count 2
```

## 内容与视觉

写前读 `references/style-architecture.md` 的契约；内容规划读 `references/content-intelligence.md`
与 `references/planning.md`。视觉设计和审稿执行 `references/visual-quality.md`。

每页一个主要结论，支持它的事实保留来源。页型由信息关系决定，避免全篇只有标题与列表。
叙事骨架是可调整的工具：决策汇报可结论先行，教学可逐步推导，不用固定顺序代替论证。

每页决定 `visual`：纯文字 `{"kind":"none"}`，图表 `{"kind":"data","ratio":"3:2"}`，
素材 `{"kind":"evidence_image","ratio":"3:2"}`。旧 spec 可不写，但新作应显式决定。

- 数据图表由真实数据生成；不能为了美观删系列、改基准或补数字。
- 照片、插画、氛围图可用生图；真实截图、品牌素材与项目证据优先保持原貌。
- 架构与流程用结构化节点和连线制作，核对关系、保留可编辑源。可使用可用的 diagram 工具；
  本渲染器仍以外部素材接入，不承诺导入后变成原生 PPTX 图形。
- 截图和信息图优先完整展示；照片可裁切，但要确认焦点。不要把整页标题和正文烤进配图。

## 规格与风格

`deck.style`、具名 `deck.colorSet` 必填，`seed` 建议显式写。项目目录就是 spec 所在目录。
有品牌资产时用 `deck.brand` 接入项目的 `brands/<名>/`；资产须由用户提供或有可信来源。
观看场景可写 `deck.delivery: live | async | printable`，用于字号提示，不自动改作者的档位。

字号用风格的 `type` 档位，页级用 `titleTier` / `bulletTier` 选择；内容过载先换结构、收短或拆页。
文字色来自 `colorSets.*.text`；未声明时可用两墨乘色派生。叠印是可选风格机制，不是所有风格的限制。
`color:"overprint"` 仅保留为旧 spec 的兼容标记；不要在内容层写 HEX。

风格自带 `style.json + skin.css`；契约、CSS 钩子、字体与可选效果见 `references/style-architecture.md`。
没有内置成品风格。可以复用已经验证的结构组件与 token 接口，每次重新设计视觉表达。
自造布局可写 `data-layout` 对应 CSS；声明 `layouts` 词表可检查拼写。

## 版式

| type | 用途 | 布局（`layout`，不写=缺省） |
| --- | --- | --- |
| `title` | 封面、章节、单句主张 | — |
| `content-text` | 结论与解释 | —；按信息量声明字号档 |
| `content-image` | 图文页 | `visual-right` / `visual-left` / `even` / `visual-wide` / `hero` |
| `two-column` | 对照或两组信息 | `even` / `lean-left` / `lean-right` / `lean-hard-left` / `lean-hard-right`；至多两栏 |
| `timeline` | 时间或阶段顺序 | — |
| `chart` | 数据证据 | `chart` 显式声明 bar / bar-horizontal / line / area / bar-stacked / donut / scatter / combo |
| `end` | 单句收束 | — |

图表详情见 `references/charts.md`。组合图每个系列必须声明 `mark:bar|line`，共用同单位纵轴；
不支持的导出能力应明确报错。`annotations` 暂不支持，非空时拦截，改用图注或完成实现后再启用。
`notes` 是逐页讲稿，不参与版面；HTML 按 `S` 显示，投屏时观众也能看到。
多条行动项使用 `content-text` 并声明 `role:"actions"`；`end` 不接受 bullets。
装饰是否出现由风格的 `decor.types` 决定，与页型能力分开。

## 渲染与验收

依赖安装与各格式差异见 `README.md`、`references/delivery-formats.md`。按依赖顺序执行，失败先修：

```bash
python3 scripts/validate_spec.py deck.spec.json
python3 scripts/ink.py <项目>/styles/<风格>/style.json
python3 scripts/image_source.py --brief deck.spec.json   # 需要素材合同才跑
python3 scripts/image_source.py --check deck.spec.json   # 素材回填后
python3 scripts/render.py deck.spec.json -o deck.html --resolved resolved.deck.json --trace
python3 scripts/check.py deck.spec.json deck.html
python3 scripts/shots.py deck.html --out-dir pages --count N
```

输入校验检查类型、数量、嵌套数据及项目品牌合并后的色板。产物校验看实际颜色、可见性、
祖先裁切、文字重叠、缺失元素、图表就绪等。实测值不能被声明值替代。
复杂背景上的文字仍需人工逐页确认；机械通过不等于审美通过。

交付前看整套缩略图、逐页实际尺寸、最终格式回读。重点看信息完整性、层级、图表语义、
字体、图片焦点与节奏。新风格至少覆盖密集、稀疏、长标题、图表与双栏内容。

`--candidates` 给图文和双栏页出候选；评分只辅助判断，不代表美观。
`--repair` 只会尝试未显式声明的字号档，不能重写内容或自动拆页；需要修内容时返回规划层。

## 交付

保留 HTML 作为演示与复现源，按用户需求交付所需格式。只有字体和素材都可移植时才称单文件交付。

```bash
python3 scripts/pdf.py deck.html -o deck.pdf
python3 scripts/pptx_native.py --png-dir pages -o deck.pptx     # 贴图，外观一致
python3 scripts/pptx_native.py deck.html -o editable.pptx      # 原生文字与支持的图表
python3 scripts/fonts.py --embed deck.html -o portable.html  # 本地字体内嵌，素材另核对
python3 scripts/animate.py deck.html -o deck.mp4
```

PDF 文字可为矢量，照片与当前 Canvas 图表仍是位图；原生 PPTX 不承诺任意 CSS 效果一致，
必须在目标宿主回读。输出时带上必要的 spec、styles、assets 与字体说明，不能只验证中间 HTML。

动画见 `references/animation.md`：演示和取帧共用 `paint(si,t)`。内容元素不加墙钟 CSS
`transition`；动画用独立 `translate` / `scale`，避免覆盖皮肤的 `transform`。
本工具做逐页演示视频，复杂转场、配乐与多镜头交给视频制作流程。

## 出错时

- 未知字段、错类型、超出支持数量：改规格，不能删掉报错字段后丢内容。
- 对比度不足：查实际背景和透明度，调整文字或背景；不降低可读性门槛。
- 越界、文字重叠、裁切：查点名元素和祖先容器，先调整结构与文案；标题可自然换行。
- 图表 pending/error、丢系列或空图：停止导出，核对图形编码和数据；图例存在不等于图形成功。
- 字体回退、导出变形：核对真实字体、实测字号、图片裁切与目标格式能力。
