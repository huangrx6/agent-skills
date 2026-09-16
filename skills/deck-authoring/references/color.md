# 配色：结构、角色、novelty、作者声明

这一层实现的是"AI 视觉配色规范"。**先说清分工**，因为这份规范里大部分讲的是
**生成过程**（怎么想），而代码能负责的只有**结构与校验**（怎么测）：

| 规范里的内容 | 谁负责 | 在哪 |
| --- | --- | --- |
| 色相关系 / 颜色数量 / 明度 / 饱和度 / 冷暖 | **代码算**（OKLCH 实测） | `palette.py::structure_of` |
| 13 个颜色角色 | **代码推导**（从色板四个角色推） | `palette.py::roles` |
| 文字可读 / 背景与主体明度不能太近 | **阻塞** | `palette.py --audit`、`ink.py` |
| 俗套组合（AI=蓝紫青、企业=蓝白…） | **按主题条件提示**，且**说清是哪一条** | `palette.py::novelty` |
| 配色选择（用哪套 `colorSets`） | **作者声明**（spec 必填具名，脚本不推断） | `validate_spec.py` / `render.resolve_color_set` |
| 外部配色站取灵感 / 搜索关键词 | **流程**（人/AI 做，见本文） | 见下 |
| "好看的配色" | **判断**（测不出来，不做假检查） | — |

```bash
python3 scripts/palette.py --audit                                  # 全部风格（用户+夹具）全审
python3 scripts/palette.py --audit --topic "AI 大模型架构"            # 带上主题判俗套
python3 scripts/palette.py --novelty swiss-grid blue --topic "AI…"   # 一个色板的 novelty 与依据
python3 scripts/palette.py --roles swiss-grid blue                   # 13 个角色的推导结果
```

## Style 存结构，不存 HEX

规范第 21 条。**存死 HEX 的后果是换一套色就得改结构**（或者更糟：改了色没改结构，
两边开始漂）。所以分工是：

- `colorSets` 存四个角色的 HEX（仓库既有形状，没改）——**primary / secondary / background / text**
- `colorStructure` 存结构（随历史八套建立；现存在于夹具与自建风格里）
- 其余九个角色**推出来**（`surface` / `surface_alt` / `accent` / `highlight` /
  `text_primary|secondary|muted` / `border` / `chart_colors` / `gradient`）——
  手写会漂，推导可测，而且推出来的关系必然自洽（surface 永远比 background 偏一点）

`colorStructure` 里**能量测的字段是从实测算出来的，不是写出来的**：
`hue_structure` / `color_count` / `lightness_structure` / `saturation_structure` /
`temperature` 都由 `structure_of()` 从 OKLCH 算得，然后 `--audit` 拿声明和实测对 ——
测出来不一致就报（这是**防止将来漂移**的守卫：现在一致，是因为它们由同一次测量产生）。

`notebook` 是唯一一个各色板结构不同的（`rule` 是三角、`marker` 是互补），所以审计
是**风格级**比对：声明落在实测集合里就算过，而不是要求逐套板全等 —— 后者会把真实差异
当错误报，而那种报告会让人开始忽略所有提示。

### 配色由作者显式声明（总编排 §17 的落地）

规则说 "Style 出语法，Theme Resolver 按实际情况融合"。v3 只有一条路：**作者按 deck
的实际情况选一套风格里手调好的 `colorSets`** —— 显式写 `deck.colorSet` 就是选它
（最稳，也是 demo/stress 的用法）。

历史那条 **auto 派生**（省略 `colorSet` 或写 `"auto"` → `palette.auto_set` 按 `mood` /
风格语法选方向做 OKLCH 变体）已退役 —— 选色是审美决策，脚本退到验收器：现在
`validate_spec.py` 把缺失或不具名的 `colorSet` 判 `MISSING_COLOR_SET`（名字不在
`colorSets` 里判 `BAD_COLOR_SET`），`render.resolve_color_set` 再拦一道直接 SystemExit
—— 不再有第二条取色路径，也不再读 `mood` / `color_creativity`。

所以 colorSets 是**人类手调的家底**（不是与规则冲突的"硬编码颜色"）；品牌色仍经由
`merge_color_sets` 同名覆盖进入（品牌协议 §5）。从语法凭空生成全新主题（不要基准）
是未实现的约定 —— 没有感知模型撑着会出丑色。

## 为什么用 OKLCH 而不是 HSL

规范第 19 条要求"外部色板不得直接复制，要走 OKLCH 二次变体"。非它不可的理由：
**HSL 的 L 与感知明度不成正比** —— 黄色 HSL L=50% 在感知里很亮，蓝色 HSL L=50%
在感知里暗得多。拿 HSL 做变体会出现"提亮之后对比度反而掉了"，而这个流水线里
对比度是**硬门槛**（文字必须过 4.5:1）。

规范第 19 条给的变体范围（**规范值**，v3 起不再由脚本自动执行）：

| | 色相 | 彩度 | 明度 |
| --- | --- | --- | --- |
| 规范允许 | ±10°~30° | ±5%~20% | ±3%~12% |

v3 起 **OKLCH 只做测量 / 推导，不再自动生成方向变体**：`palette.py` 保留 `oklch()` /
`to_hex()` / `contrast()` 这套数学，供 `hue_structure`（色相结构）、`roles`（13 角色
推导）、`novelty`（俗套计分）与配色审计使用 —— 它们都要感知均匀的坐标才算得准。
（原先按 OKLCH 生成 Safe / Creative / Experimental 三变体的那条路已退役，见下「三个方向」。）

**中性色不参与色相判定**（彩度低于 `NEUTRAL_CHROMA` 就跳过）—— 挪中性色的色相只会
让它变脏。`NEUTRAL_CHROMA = 0.03`（palette.py:143）是**按实测标定的**：`pastel-geometry`
的副色 `#8A8578` 彩度 0.020，目视就是暖灰，可它正好卡在 0.02 上，于是被算成"有色"，
那套风格被误判成互补色（实测发现）。

## 俗套表：说清是哪一条

规范第 18 条。扣分项**必须能说出扣的是哪一条**，否则 novelty 只是个没有说服力的数字。
每条判据都带着"为什么俗"：

| id | 判据 | 为什么 | 权重 |
| --- | --- | --- | --- |
| `tech_blue_purple_cyan` | 主题像 AI/科技 **且** 主色落在 H 200~320 且 C ≥ 0.10 | 训练数据里最高频的一套（规范第 23 条点名） | −0.30 |
| `corporate_blue_white` | 蓝主色（H 230~275）+ 白底 | 企业模板的默认解 | −0.18 |
| `premium_black_gold` | 深底 + 金色强调（H 60~100） | 高端感的默认解 | −0.15 |
| `even_saturation` | 主副两色饱和度都 ≥ 0.10 且相差 < 0.03，两色相隔 > 120° | 没有主次 | −0.12 |
| `low_lightness_contrast` | 背景与主体明度差 < 0.25 且底是浅的 | 重点浮不出来 | −0.15 |

加分项同理（非常规冷暖、低饱和+高纯度强调、中性+非典型强调）。

**实测：历史八套内置期，5 套的某个色板正落在名单上**（现为自建风格按同一判据提示） —— 所以这条**不能一律阻塞**，
否则仓库自己的风格先挂。它只做两件事：按**主题条件**指出"这套色 + 这个主题正好落在
最俗的组合上"，以及在你显式要求时（`--min-novelty`）当闸门。规范第 18 条给过三档
阈值（普通 PPT 0.45 / 设计型 0.65 / 创意封面 0.75），但代码里那份对应表
（`NOVELTY_MIN`，palette.py:312）**没接线，是死常量**；实际生效的闸门是风格自报的
`colorStructure.novelty_target`（palette.py:628；夹具 swiss-grid 0.5）加上显式
`--min-novelty`。

> 拿 `--topic "AI 大模型架构"` 审一遍就会看到：夹具两套的 `blue` 色板
> （`swiss-grid/blue`、`minimal-baseline/blue`）都同时命中
> `tech_blue_purple_cyan` 与 `corporate_blue_white`（实测 novelty 0.14）。
> **这说明规范那两条不是空话，而是本仓库真实存在的情况** —— 想做 AI 主题的 deck，
> 这几个色板不该默认选。

## 三个方向：自动变体已退役（配色由作者声明）

规范第 17 条：Safe / Creative / Experimental。**v3 起自动生成三方向变体的那条路已退役**
—— `palette.py` 里 `directions` / `variant` / `choose_direction` / `auto_set` /
`MOOD_DIRECTIONS` / `DIRECTIONS` 与 `--directions` CLI 全部删除：选色是审美决策，
脚本退到验收器。

替代做法是**作者显式声明**：`spec.deck.colorSet` 必填具名（缺失或写 `auto` 会被
`validate_spec.py` 判 `MISSING_COLOR_SET`、被 `render.resolve_color_set` 直接
SystemExit）。要"更 creative"就往风格的 `colorSets` 里加一套**手调**色板
（同风格加色板的 seam 见 `references/style-architecture.md`），不是让脚本去挪色相。

规范说"Creative 不满足可读性再回退 Safe" —— 可读性是**能测的**，但工具边界要说清：
v3 不再自动产出变体，也就没有那道自动回退。色板的对比度要验，跑
`ink.py <style.json>`（任一色板不达标退出码 1）或 `palette.py --audit`。

## 检索关键词：搜 Style，不搜行业

规范第 4 条。这条是流程，不是代码，但很关键 —— 搜"AI 科技配色"一定会得到蓝紫青，
那正是要避免的。**优先级：Style > Mood > Color Character > Content > Industry。**

要搜的是这类短语（按 Style 挑，不是按行业）：

```text
editorial sophisticated palette      dark cinematic unexpected palette
neo brutalism bold palette           muted futuristic palette
acid accent neutral palette          warm technical palette
unusual gradient palette             premium low-saturation palette
```

规范给的对照例子：主题「AI 大模型架构」+ Style「Editorial」+ Mood「理性/高级/前沿」，
要搜 `editorial sophisticated palette` / `editorial high contrast palette` /
`unusual editorial gradient`，**而不是** `AI blue purple palette`。

## 外部配色源：用来学关系，不是抄色

规范第 3 条，五个源各有分工：

| 源 | 学什么 | 注意 |
| --- | --- | --- |
| [中国色](https://zhongguose.com/) | 低饱和东方色、高级灰、复古 | **不只用于中国风** —— 任何要"非标准、克制"的风格都能用 |
| [WebGradients](https://webgradients.com/) | 颜色关系 + stop 分布 + 方向 | 不照搬；重点看 stop 的不均匀分布 |
| [Happy Hues](https://www.happyhues.co/palettes/) | **角色如何分工** | 它的角色划分和规范第 20 条的 13 个角色可以对上 |
| [Color Hunt](https://colorhunt.co/) | 提升新鲜感 | 按 Style + Mood 检索，不按行业 |
| [Huemint](https://huemint.com/) | 高创造力候选 | 适合高创造力那一档（手工取色、再加进风格） |

**取回来的色不得直接复制**：走第 19 条的变体流程（保留色相关系 → OKLCH 变体 →
对比度检查 → 角色映射）。`palette.py --roles` 是最后一步的现成工具。

## 页面一致性

规范第 22 条。这一条在本流水线里**天然成立**，因为整套 deck 只有一个 `colorSet`
（`deck.colorSet` 是 deck 级字段，不是页级）—— 所以"每页随机换主色"在结构上就做不到。
允许的变化（封面更大胆、内容页更克制）由版式承担，不由色板承担。

## 还没实现的（写清楚，别假装做了）

规范里有几条**本流水线还没有对应能力**，列在这里而不是含糊带过：

1. **渐变**。`palette.py::roles` 会推出 `gradient`（含非线性 stop：0 / 0.23 / 0.68 / 1.0），
   但**渲染层没有用它** —— 历史八套的 `gradient_strategy` 都是 `none`，外壳里没有渐变。
   规范第 13 条那十种渐变类型（mesh / aurora / glow / conic…）都还没做。
2. **玻璃拟态 / Glow / Mesh**。规范第 12 条的背景策略里有这些，当前只支持
   `solid` 与 `texture`（颗粒）。
3. **强调色占比的实测**。规范第 11 条说 5%~20%。`measure.py` 已经记了每个元素的
   `color`（measure.py:164；`measuredColor` 只是 pptx 导出侧的改名，
   pptx_native.py:409），所以**算得出来**（按元素盒面积统计），但还没接进 `check.py`。
4. **外部配色源的自动检索**。`palette.py` 不联网 —— 取灵感这一步是流程（见上）。
