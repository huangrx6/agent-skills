---
name: diagram-authoring
description: >-
  Draw technical diagrams from a structure-only spec (architecture, dependency, flow, state,
  topology, mind maps). Two backends from one spec: editable Excalidraw in the Obsidian vault
  (default), or .drawio for standard shape libraries and PNG/PDF/SVG deliverables. Use when the
  user asks to 画图 / 画架构图 / 画流程图 / 画依赖图 / 把这段说明画出来 / draw a diagram /
  visualize a system or flow. The model describes structure only (nodes, edges, groups); scripts
  compute every coordinate. Do NOT use for editing, moving, or organizing notes, for recording
  completed work or release notes, or for decorative illustration, posters, or wireframes.
  需要 vault 路径的，从 $OBSIDIAN_VAULT_PATH 或 ~/.config/agent-skills/obsidian-vault-path 解析，不要写死。
---

# 技术图（两个后端：Excalidraw / draw.io）

把"系统怎么运作"画成可编辑的图。**你负责理解与描述结构，脚本负责一切坐标。**

## 为什么不能由你写坐标（这条不可协商）

配色、大小、字号、排版、连线长度、遮挡 —— 这些**全部是空间计算**。让模型直接吐坐标，
本质是让它做一件它没有可靠能力的事，症状必然是"看起来还行，但总有几处别扭"。

**所以规格里没有坐标字段 —— 不是"不推荐填",是不存在这个字段。**
未来任何人都不要"顺手加个可选 x/y"：

> 一旦 schema 里有 x/y，模型就会开始填数字。这个失败已经发生过 —— 参见
> `references/diagram-spec.md` 里对前作 `draw-excalidraw` 的诊断。

## 起手流程

1. **先拿证据**：图的内容来自代码／配置／文档／运行输出。不要凭目录树猜架构。
2. **判断图类型**，查下面的策略表（类型决定布局算法，不是学美规则）。拿不准时
   可以跑 `python3 scripts/guide.py "一句话描述"` —— 信号词打分，同分不硬选。
3. **写规格**：一份 `*.diagram.json`，只有结构（节点／边／分组），见 `references/diagram-spec.md`。
   写规格只需要本文件与那份契约，**不要为了写规格去读 layout.py / check_layout.py 的实现** ——
   上下文经济：先把候选做出来，实现细节只在诊断要求时才回头看。
4. **校验规格**：`python3 scripts/validate_spec.py x.diagram.json` —— 字段集是封闭的，
   未知字段会判失败（包括坐标）。
5. **选出图后端**（见下一节），然后出图：`python3 scripts/emit_excalidraw.py x.diagram.json`（或
   `emit_drawio.py`）—— 它串起整条流水线（校验 → `layout.py` 分层布局 → `check_layout.py` 十三项校验、
   失败时脚本自己调参重跑 → 同目录临时文件 + 原子换入，绝不留半张图）。**有阻塞项时不写文件。**
   交付给别人看时加 `--quality showcase`：结构类软项（交叉/重合/斜段/折点/相交/穿节点）
   升级为阻塞，有残留就不出图。成功后打印**三档回执**：确定性校验 / 自研预览 / 感知审查
   —— 三档互不冒充，感知审查必须人眼看真实渲染。
6. **修复（最多两轮）**：报告只在脚本自动调参耗尽时出现；修复时**只改报告点名的主体、
   只按报告的内容建议改**，不要改参数（报告里不会出现参数名，报告给的 `suggestedFixes`
   就是全部允许的动作）。**两轮聚焦修复都没把错误数降到新低就停**，如实报告未解决项
   —— 不硬撑、不换个说法再试第三轮。
7. **保留规格文件**，和成品放一起；以后的修改改规格再重新生成。

## 两个后端：选哪个

| 情况 | 后端 | 产物 |
| --- | --- | --- |
| 要标准图元（云 / K8s / UML / BPMN / 泳道）、要交给别人、要导出 PNG/PDF/SVG | draw.io | `.drawio` |
| 其余情况（**默认**） | Excalidraw | `.excalidraw` |

拿不准就问一句"**给谁看、要不要导出成图片**"。**同一份规格两个后端都能出** —— 换后端只换一条命令，
不重写规格：几何、校验、调参、文字全是同一份推导。

**drawio 侧有五套配色方案**（`classic` / `engineering`[默认，白底+等宽标签+灰边框] / `print` /
`night` / `blueprint`）。选择流程和上面那条硬规则一样是**先问**：

- 用户说了气质（"专业 / 商务 / 黑白 / 深色 / 蓝图"）→ 直接对号入座，别多问一轮；
- **没说 → 跑 `scripts/scheme_preview.py`，把那一份多页预览给他，让他切页签挑**；
- 他说"在某套基础上把主色换成我们的品牌蓝"→ 用 `--seed accent=<那个色值>`
  （颜色是**他**的决定；规格里照样一个颜色都不写）。

`--scheme` / `--seed` 是**你落笔用的机制**，不是要他记的接口。五套方案共用同一套语义档位，
只换 4 个种子色 + 字体/圆角那几个平台旋钮 —— 细节见 `references/drawio-backend.md`。

**Excalidraw 侧的颜色不走配色方案**：`visual` 视觉方向（6 个方向 + `auto`）决定色相，
机制与"先问"的规矩见 `references/diagram-spec.md` 的"视觉方向"一节与下文的颜色说明。

## 图类型 → 布局策略

| 图类型 | 关系形态 | 布局算法 | 默认方向 |
| --- | --- | --- | --- |
| `architecture` | 有向、近似无环 | 分层（简化 Sugiyama） | `LR` |
| `flow` / `state` | 有向、可能有环 | 分层 + 环回边特殊处理 | `TB` |
| `dependency` | 有向、层级明显 | 分层 | `LR` |
| `mindmap` | 中心辐射 | 径向（同心环，子树按叶子数分扇区） | 不适用 |
| `network` | 网状、无明显层级 | 力导向（确定性初值 + 收尾分离） | 不适用 |

**能力边界：三种布局算法 —— 分层（Sugiyama）、径向（同心环）、力导向；按 `type` 自动选，你不选算法。**

**判断类型是你的活；判断完之后的计算全是脚本的活。** 类型拿不准时问用户，不要混着套。

## 硬规则

| 规则 | 说明 |
| --- | --- |
| 不写坐标 | schema 没有 `x` / `y` / `width` / `height`。布局参数也不在 schema 里 |
| 不写颜色 | 只写 `kind` + `emphasis`。**没有角色默认是强调色** —— 谁是重点由每张图决定 |
| 不写字号 | 容器按文字长度落尺寸档位，字号跟档位联动 |
| `kind` 只能取色板里的值 | **未知 kind 直接判失败**，不会 fallback 到默认色 |
| 一张图一个文件 | 信息量用 `detail` 控制，不拆多视图；解释性清单放 `cards`（图下方的结论卡），不堆进节点和边 |
| 图标只取图形 | 素材自带的文字缩到节点尺寸会糊成噪点，默认剥掉（见 `references/icons.md`；内置 sigil 不用素材库） |
| 图标先搜再选 | 内置 sigil 只有十来个；**要更丰富的图标就去官方素材库目录里搜**（`icons_fetch.py --search <中文关键词>`），取到本地缓存后用 `--library <库名>`。不要把几个熟名字反复用在不同语义上。节点框会为图标**自动适配宽度**，不会溢出也不会把图标丢掉 |
| 图标风格由脚本统一，颜色分两种待遇 | 描边粗细 / 粗糙度 / 填充一律统一（否则同图出现粗黑 + 细线两套语言）。颜色：**多色素材（品牌 logo）保留配色**，读不出来的颜色保留色相压暗到 3:1；**单色素材换成节点墨色**。要严格单色用 `"style": {"icons": "ink"}`，要原样保留用 `"native"` |
| 先让用户挑主题 | **用户没指定风格时**：Excalidraw 跑 `scripts/direction_preview.py`（5 个方向并排）、drawio 跑 `scripts/scheme_preview.py`（5 套配色**一页一套**，让他切页签看），**把文件给他挑**。**「你看着来 / 随便 / 都行」也算没指定** —— 那是把选择权交给你，而选风格正是硬规则不让模型单方面做的那些空间/视觉决定之一；真说了"要绿色/要深色/像手绘/要专业/黑白"就直接照办，别再多问一轮 |
| 别让用户记参数 | 挑完之后**由你**把选择落成参数（`--scheme` / `--seed` / `visual`），**不要把这几个参数名教给用户**。用户说的是"要专业一点""主色用我们的品牌蓝"，说得出这个就够了 —— 把"审美的话"翻译成"参数"是你的活 |

## 校验与「自动调参」循环

校验由脚本做，**调参也由脚本做 —— 中间不经过你的判断**：

```text
layout(参数) → 校验 ──通过──→ 输出
                 │
                 └─失败且轮次未耗尽 → 参数按固定步长递增 → 重跑
                 └─轮次耗尽 → 出报告
```

**报告只在你无法自动收敛时出现**，而且只建议**内容层面**的修改（拆节点／缩短标签／降 `detail`／
调整 rank 分层）。报告会列出**已经试过哪些参数** —— 看到"建议调大某某间距"这种话是设计事故，请上报。

十三项校验（元素间隙／连线过短／文字溢出／越界颜色／边交叉数／连线穿节点／区域重叠／连线重合／
连线斜段／折点过多／连线相交／区域标题溢出／桌面可读性）的阈值与级别、质量两档（standard /
showcase）的语义见 `references/validation.md`，实现在 `scripts/check_layout.py`；切分与排序在
`scripts/layout.py`。

两个容易看错的点：

- **交叉数是"软"项**：它不挡输出，但**仍然会被调参**。把它当成"不报错"就会连它调过没调过都不知道。
- **"元素间隙"与"文字溢出"是后置断言**：坐标是从间距参数算出来的，尺寸也是从同一份文字测量
  算出来的 —— 在今天的推导下它们**构造上不可能失败**。一旦报，报的是脚本内部不一致，
  不是你的内容有问题。详见 `references/validation.md` 的"已知局限"。

## 脚本

```sh
python3 scripts/emit_excalidraw.py x.diagram.json     # 默认后端：串起整条流水线，写 .excalidraw
python3 scripts/emit_drawio.py x.diagram.json         # 另一个后端：.drawio（不压缩 XML；多份规格 = 一个文件多页）
python3 scripts/check_drawio.py x.drawio              # .drawio 结构自检（打不开的图在这里拦住）
python3 scripts/scheme_preview.py -o /tmp/schemes.drawio  # 五套配色一页一套：给用户切着挑
python3 scripts/direction_preview.py x.diagram.json -o /tmp/directions/  # 五个视觉方向并排：给用户挑
python3 scripts/open_excalidraw_com.py x.excalidraw   # 在 excalidraw.com 官网上打开它、接着手改
python3 scripts/validate_spec.py x.diagram.json       # 只校验规格（封闭字段集）
python3 scripts/layout.py x.diagram.json --explain    # 只算布局：用的哪个算法、层/环内顺序、坐标、交叉数
python3 scripts/check_layout.py x.diagram.json --quality showcase --json  # 只跑校验 + 机器可读回执
python3 scripts/text_metrics.py "节点标题"            # 看文字 → 容器尺寸的实际推算
python3 scripts/palette.py                            # 打印色板与 kind 取值
python3 scripts/sigils.py                             # 内置语义图标目录（不碰素材库就能用的那批）
python3 scripts/icons_fetch.py --search 数据库         # 去**官方素材库目录**里搜图标（200+ 库、几千个图形）
python3 scripts/icons_fetch.py --get "IT icons"       # 取到本地缓存，之后 --library it-icons 直接用
python3 scripts/guide.py "一句话描述"                 # 场景 → 图型推荐（信号词打分，同分不硬选）
```

`check_layout.py` 退出码：0 = 无阻塞项，1 = 有阻塞项，2 = 读不到规格。
`--quality showcase` 把结构类软项升级为阻塞（交付档，standard / showcase 两档的完整语义见
`references/validation.md`）；`--json` 打印机器可读回执 —— 每条诊断带
`code / severity / message / subject / evidence / suggestedFixes`，给上游的修复循环、
基准验证器和任何机器消费方用。修复时只从 `suggestedFixes` 里选动作。

### 交付三档声明（互不冒充，不许拿第一档冒充第三档）

emit 成功后固定打印三档，汇报时也按这三档说：

1. **确定性校验** —— 脚本可证（十三项 + showcase 档）。它能说"没有一处是坏的"，
   说不了"这张图讲清楚了"；
2. **自研预览渲染** —— `dev-tools/preview.py` 出 PNG 供目视复核；它看到的是我们自己的
   布局模型，看不见渲染器差异，所以它过了**不等于**真实 Excalidraw 里长那样。
   要看**渲染器自己画的图**就用 `dev-tools/export_excalidraw.py`（官方导出，PNG/SVG）——
   两者都是第二档的证据，都不能冒充第三档；
3. **感知审查** —— 只能人眼看真实渲染（excalidraw.com 打开 / 导出图片）。
   **校验全绿 ≠ 图讲清楚了**；没有看图能力时如实说"未看"，不要升级成"应该没问题"。

`dev-tools/preview.py` 与两个后端的细节（`.excalidraw` 为什么是 plain JSON、
Excalidraw 会自己重排文字这个限制、drawio 的形状映射与导出步骤）都在
`references/` 里对应的后端文档里。

```sh
python3 dev-tools/preview.py x.excalidraw out.png                        # 自研预览（需 PIL）
python3 dev-tools/export_excalidraw.py x.excalidraw -o x.png --scale 2   # 官方导出（需 Chrome）
```

官方导出走 Excalidraw 自己的 `exportToBlob` / `exportToSvg`，出的是真实渲染器画的图；
自研预览只画布局模型。两者的边界写在 `references/excalidraw-backend.md`。

## ⚠ 限制：Excalidraw 会自己重新排版文字

容器绑定的文字在 Excalidraw 里**由它自己按真实字体重新断行**，所以
**规格与校验全绿不等于渲染出来就是那样**。实测结论与边界见
`references/excalidraw-backend.md` 第三节；drawio 后端不重折（折行写死）。

## 引用文件

- `references/visual-design.md`：视觉设计规范 —— 总原则（不追求统一颜色，而追求统一审美）、"好看/大气" 这类不可机械校验项与可校验项的**分界**，以及实测出来的 18 条问题清单。
- `references/diagram-spec.md`：内容层契约 —— 允许写什么、刻意不存在的字段、`kind` 封闭枚举与色板、**区域（`groups`）**、**结论卡（`cards`）**、**五组样式轴（`style`，含图标颜色策略）**、`detail` 信息量档位、视觉方向与颜色派生、尺寸档位与字号。
- `references/validation.md`：十三项校验的阈值与级别、质量两档（standard/showcase）、机器可读回执、自动调参循环的细节、报告该说什么。
- `references/icons.md`：图标（内置 sigil + 素材库）—— 怎么查、按语义怎么选、怎么写进规格，以及它为什么是第一个**外部尺寸来源**。
- `references/excalidraw-backend.md`：默认后端的细节 —— plain JSON 的理由、在官网上接着手改、**它自己重排文字**这个限制、`dev-tools/preview.py` 看到什么。
- `references/drawio-backend.md`：另一个后端 —— 为什么写不压缩的 XML、形状映射表、与 Excalidraw 后端**有意不同**的地方、结构自检、人怎么导出 PNG/PDF。
