---
name: diagram-authoring
description: >-
  Draw technical diagrams from a structure-only spec (architecture, dependency, flow, state,
  topology, mind maps). Two backends from one spec: editable Excalidraw in the Obsidian vault
  (default), or .drawio for standard shape libraries and PNG/PDF/SVG deliverables. Use when the
  user asks to 画图 / 画架构图 / 画流程图 / 画依赖图 / 把这段说明画出来 / draw a diagram /
  visualize a system or flow. The model describes structure only (nodes, edges, groups); scripts
  compute every coordinate. Do NOT use for editing, moving, or organizing notes (use
  `obsidian-personal-knowledge-base`), for recording completed work or release notes (use
  `obsidian-work-log-release-recorder`), or for decorative illustration, posters, or wireframes.
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
2. **判断图类型**，查下面的策略表（类型决定布局算法，不是学美规则）；拿不准跑 `python3 scripts/guide.py "一句话描述"`（信号词打分，同分不硬选）。
3. **写规格**：一份 `*.diagram.json`，只有结构（节点／边／分组），见 `references/diagram-spec.md`。写规格只需要本文件与那份契约，**不要为了写规格去读 layout.py / check_layout.py 的实现**（有界阅读，模仿 archify 的 fast authoring path）。
4. **校验规格**：`python3 scripts/validate_spec.py x.diagram.json` —— 字段集是封闭的，未知字段会判失败（包括坐标）。**先写候选再读实现**：出图之前不需要理解渲染器内部。
5. **选出图后端**（见下一节），出图：`python3 scripts/emit_excalidraw.py x.diagram.json`（或 `emit_drawio.py`）—— 一条命令串起整条流水线（校验 → 布局 → 十三项校验、失败自动调参重跑 → 原子写入，**有阻塞项不写文件**）。交付给别人看加 `--quality showcase`：结构类软项升级为阻塞，有残留不出图；成功后打印三档回执（见下）。
6. **修复（最多两轮）**：报告只在自动调参耗尽时出现；只改报告点名的主体、只按报告的**内容**建议改，不改参数（报告里不会出现参数名）。**两轮聚焦修复都没把错误数降到新低就停**，如实报告未解决项 —— 不硬撑（模仿 archify 的 correction_rounds 上限）。
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
| 图标只取图形 | 素材自带的文字缩到节点尺寸会糊成噪点，默认剥掉（见 `references/icons.md`） |
| 先让用户挑主题 | **用户没指定风格时**：Excalidraw 跑 `scripts/direction_preview.py`（5 个方向并排）、drawio 跑 `scripts/scheme_preview.py`（5 套配色**一页一套**，让他切页签看），**把文件给他挑**。**「你看着来 / 随便 / 都行」也算没指定** —— 那是把选择权交给你，而选风格正是硬规则不让模型单方面做的那些空间/视觉决定之一；真说了"要绿色/要深色/像手绘/要专业/黑白"就直接照办，别再多问一轮 |
| 别让用户记参数 | 挑完之后**由你**把选择落成参数（`--scheme` / `--seed`），**不要把这几个参数名教给用户**。用户说的是"要专业一点""主色用我们的品牌蓝"，说得出这个就够了 —— 把"审美的话"翻译成"参数"是你的活 |

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

十三项校验（元素间隙／连线过短／文字溢出／越界颜色／边交叉数／连线穿节点／区域重叠／连线重合／连线斜段／折点过多／连线相交／区域标题溢出／桌面可读性）的阈值与级别见 `references/validation.md`，实现在 `scripts/check_layout.py`；切分与排序在 `scripts/layout.py`。

两个容易看错的点：

- **交叉数是“软”项**：不挡输出但**仍会被调参**；把它当“不报错”就不知道它调过没调过。
- **“元素间隙”与“文字溢出”是后置断言**：坐标与尺寸同源于间距参数与文字测量，构造上不可能失败；
  一旦报，是**脚本内部不一致**，不是你的内容有问题（详见 `references/validation.md` 的“已知局限”）。

## 脚本

```sh
python3 scripts/emit_excalidraw.py x.diagram.json     # 默认后端：串起整条流水线，写 .excalidraw
python3 scripts/emit_drawio.py x.diagram.json         # 另一个后端：.drawio（不压缩 XML；多份规格 = 一个文件多页）
python3 scripts/check_drawio.py x.drawio              # .drawio 结构自检（打不开的图在这里拦住）
python3 scripts/scheme_preview.py -o /tmp/schemes.drawio  # 五套配色一页一套：给用户切着挑
python3 scripts/open_excalidraw_com.py x.excalidraw   # 在 excalidraw.com 官网上打开它、接着手改
python3 scripts/validate_spec.py x.diagram.json       # 只校验规格（封闭字段集）
python3 scripts/layout.py x.diagram.json --explain    # 只算布局：用的哪个算法、层/环内顺序、坐标、交叉数
python3 scripts/check_layout.py x.diagram.json --quality showcase --json  # 只跑校验 + 机器可读回执
python3 scripts/text_metrics.py "节点标题"            # 看文字 → 容器尺寸的实际推算
python3 scripts/palette.py                            # 打印色板与 kind 取值
python3 scripts/sigils.py                             # 内置语义图标目录（不碰素材库就能用的那批）
python3 scripts/guide.py "一句话描述"                 # 场景 → 图型推荐（信号词打分，同分不硬选）
```

退出码：0 = 无阻塞项，1 = 有阻塞项，2 = 读不到规格；`--quality showcase` 升级交付档；
`--json` 打印机器可读回执（`code / severity / subject / evidence / suggestedFixes`，供修复循环与基准消费）。

### 交付三档声明（互不冒充，不许拿第一档冒充第三档）

① **确定性校验** —— 脚本可证（十三项 + showcase 档）；② **自研预览渲染** —— 需 `dev-tools/preview.py`
或真实 Excalidraw 核对；③ **感知审查** —— 只能人眼看真实渲染，**校验全绿 ≠ 图讲清楚了**。

`dev-tools/preview.py` 与两个后端的细节（`.excalidraw` 为什么是 plain JSON、
Excalidraw 会自己重排文字这个限制、drawio 的形状映射与导出步骤）都在
`references/` 里对应的后端文档里。

```sh
python3 dev-tools/preview.py x.excalidraw out.png
```

它看到的只是我们自己的布局模型，看不见渲染器差异 —— 边界写在 `references/excalidraw-backend.md`。

## ⚠ 限制：Excalidraw 会自己重新排版文字

容器绑定的文字在 Excalidraw 里**由它自己按真实字体重新断行**，所以
**规格与校验全绿不等于渲染出来就是那样**。实测结论与边界见
`references/excalidraw-backend.md` 第三节；drawio 后端不重折（折行写死）。

## 引用文件

- `references/visual-design.md`：视觉设计规范 —— 总原则（不追求统一颜色，而追求统一审美）、"好看/大气" 这类不可机械校验项与可校验项的**分界**，以及实测出来的 9 条问题清单。
- `references/diagram-spec.md`：内容层契约 —— 允许写什么、刻意不存在的字段、`kind` 封闭枚举与色板、**区域（`groups`）**、**四组样式轴（`style`）**、`detail` 信息量档位、尺寸档位与字号。
- `references/validation.md`：十三项校验的阈值与级别、质量两档（standard/showcase）、JSON 回执、自动调参循环的细节、报告该说什么。
- `references/icons.md`：图标/素材库 —— 怎么查、按语义怎么选、怎么写进规格，以及它为什么是第一个**外部尺寸来源**。
- `references/excalidraw-backend.md`：默认后端的细节 —— plain JSON 的理由、在官网上接着手改、**它自己重排文字**这个限制、`dev-tools/preview.py` 看到什么。
- `references/drawio-backend.md`：另一个后端 —— 为什么写不压缩的 XML、形状映射表、与 Excalidraw 后端**有意不同**的地方、结构自检、人怎么导出 PNG/PDF。

## 与 PKB 的关系

`obsidian-personal-knowledge-base` 里原有的“图示默认风格”已收拢到本 skill 色板文件，那边应改为指针 ——
可被机械校验的东西只有一处定义，否则必然漂移。
