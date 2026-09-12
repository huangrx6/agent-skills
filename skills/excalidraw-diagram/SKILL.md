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
4. **校验规格**：`python3 scripts/validate_spec.py x.diagram.json` —— 字段集是封闭的，未知字段会判失败（包括坐标）。
5. **出图**：`python3 scripts/emit_excalidraw.py x.diagram.json` —— 它串起整条流水线（校验 → `layout.py` 分层布局 → `check_layout.py` 五项校验、失败时脚本自己调参重跑 → 写出 `.excalidraw`）。**有阻塞项时不写文件。**
6. **看报告**：只有脚本自动重试耗尽时才有报告，此时按报告建议改**内容**，不要改参数。报告里不会出现参数名。
7. **保留规格文件**，和 `.excalidraw` 放一起；以后的修改改规格再重新生成。

## 图类型 → 布局策略

| 图类型 | 关系形态 | 布局算法 | 默认方向 |
| --- | --- | --- | --- |
| `architecture` | 有向、近似无环 | 分层（简化 Sugiyama） | `LR` |
| `flow` / `state` | 有向、可能有环 | 分层 + 环回边特殊处理 | `TB` |
| `dependency` | 有向、层级明显 | 分层 | `LR` |
| `mindmap` | 中心辐射 | **暂用分层**（径向／树形尚未实现） | `LR` |
| `network` | 网状、无明显层级 | **暂用分层**（力导向尚未实现） | `LR` |

**能力边界：只有分层一种布局算法，上表所有类型都走它** —— 思维导图/网状图不是中心辐射/力导向。

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

五项校验（重叠／连线过短／文字溢出／越界颜色／边交叉数）的阈值与级别见 `references/validation.md`，实现在 `scripts/check_layout.py`；切分与排序在 `scripts/layout.py`。

两个容易看错的点：

- **交叉数是“软”项**：它不挡输出，但**仍然会被调参**。把它当成“不报错”就会连它调过没调过都不知道。
- **“元素间隙”与“文字溢出”是后置断言**：坐标是从间距参数算出来的，尺寸也是从同一份文字测量算出来的 —— 在今天的推导下它们**构造上不可能失败**。一旦报，报的是脚本内部不一致，不是你的内容有问题。详见 `references/validation.md` 的“已知局限”。

## 脚本

```sh
python3 scripts/emit_excalidraw.py x.diagram.json     # 出图：串起整条流水线，写 .excalidraw
python3 scripts/open_excalidraw_com.py x.excalidraw   # 在 excalidraw.com 官网上打开它、接着手改
python3 scripts/validate_spec.py x.diagram.json       # 只校验规格（封闭字段集）
python3 scripts/layout.py x.diagram.json --explain    # 只算布局：分层与层内顺序、坐标、交叉数
python3 scripts/check_layout.py x.diagram.json        # 只跑校验 + 调参报告
python3 scripts/text_metrics.py "节点标题"            # 看文字 → 容器尺寸的实际推算
python3 scripts/palette.py                            # 打印色板与 kind 取值
```

`check_layout.py` 退出码：0 = 无阻塞项，1 = 有阻塞项，2 = 读不到规格。

## 在官网（excalidraw.com）上接着画

**能做到，已实测跑通。** `scripts/open_excalidraw_com.py` 起一个只服务那一个场景文件、
且只允许 excalidraw.com 这一个源的本地服务，然后打开：

```text
https://excalidraw.com/#url=http://localhost:8789/x.excalidraw
```

`#url=` 是 Excalidraw 的“从外部 JSON 地址导入场景”（PR #2726，无官方 UI 入口）。
实测结果：官网把 23 个元素全部加载进画布、可以直接接着画；加载完 app 会自己把 hash 清掉。

**两个坑（都踩过）**：`file://` 不会被 fetch 到；而且 excalidraw.com 去 fetch localhost
**需要 CORS 头**（python 自带的 http.server 不发，现象是“打开后一直空白”）。所以那个脚本
自己包了一层。**在 Obsidian 插件里用则完全不需要它** —— 文件放进 vault 双击就行。

## `dev-tools/preview.py` —— 不是运行时的一部分

把 `.excalidraw` 画成 PNG，给我自己**目视复核**用。它**需要 PIL**，而上面那条链跑图
**不需要**——用户用这个 skill 出图仍然是零依赖。放在 `dev-tools/` 而不是 `scripts/`，
就是为了让“核心链路零依赖”这句话不被含糊掉。

**它能判断**：结构一眼能不能看懂、排版顺不顺眼、颜色比例、节点疏密、连线走向、
标签有没有压在节点上。

**它不能判断**：它画的是我们**自己的布局模型**（与 `layout.py` 同源），
所以它**在构造上**看不见“渲染器与我们的模型不一致”这类问题 —— 尤其是容器绑定文字
在 Excalidraw 里的实际断行。那类问题只有真实 Excalidraw 才算数，见 `references/validation.md`。

```sh
python3 dev-tools/preview.py x.excalidraw out.png
```

## 输出格式：`.excalidraw`（plain JSON）

**不是 `.excalidraw.md`** —— 后者的场景用 **lz-string** 压缩，而 lz-string 没有 stdlib Python
等价物（用它就得手抄一份 JS 压缩算法）。理由与实测证据在 `emit_excalidraw.py` 的文档注释里。

同一份规格每次生成的字节相同（seed 由元素 id 的 sha256 推出），所以图能进 git、diff 有意义。

## ⚠ 限制：Excalidraw 会自己重新排版文字

`text_metrics` 的尺寸是我们对“文字占多大”的**推算**，而容器绑定的文字在 Excalidraw 里
**由它自己按真实字体重新断行** —— **渲染器是第二个尺寸来源，不在我们控制之内。**
断行不一样多出一行，容器就被撑高、布局随之偏移。

**所以：规格与校验全绿不等于渲染出来就是那样。** 已实测的结论与它的边界见 `references/validation.md` 第六节。

## 引用文件

- `references/visual-design.md`：视觉设计规范 —— 总原则（不追求统一颜色，而追求统一审美）、"好看/大气" 这类不可机械校验项与可校验项的**分界**，以及实测出来的 9 条问题清单。
- `references/diagram-spec.md`：内容层契约 —— 允许写什么、刻意不存在的字段、`kind` 封闭枚举与色板、尺寸档位与字号。
- `references/validation.md`：五项校验的阈值与级别、自动调参循环的细节、报告该说什么。
- `references/icons.md`：图标/素材库 —— 怎么查、按语义怎么选、怎么写进规格，以及它为什么是第一个**外部尺寸来源**。

## 与 PKB 的关系

`obsidian-personal-knowledge-base` 的 `references/resource-notes.md` 里原本写着"图示默认风格"
（白底／浅灰网格／浅色系／排除深色）。**风格定义已收拢到本 skill 的色板文件**，那份文档应改为指针 ——
可被机械校验的东西只有一处定义，否则必然漂移。
