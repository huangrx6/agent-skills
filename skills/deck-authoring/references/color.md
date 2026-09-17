# 配色：结构、角色、novelty、作者声明

这一层实现的是"AI 视觉配色规范"。**先说清分工**，因为这份规范里大部分讲的是
**生成过程**（怎么想），而代码能负责的只有**结构与校验**（怎么测）。
**分工**：配色由作者声明；画质门槛由 `ink.py`（对比度）与 `check.py`（实测门）承担：

| 规范里的内容 | 谁负责 | 在哪 |
| --- | --- | --- |
| 色相关系 / 颜色数量 / 明度 / 饱和度 / 冷暖 | **作者声明**（按 OKLCH 判据写，脚本不再算） | 风格 `style.json` 的 `colorStructure`（见下） |
| 13 个颜色角色 | **不存在**（色板只有四个角色） | 见下「Style 存结构，不存 HEX」 |
| 文字可读 / 背景与主体明度不能太近 | **阻塞** | `ink.py`（对比度） |
| 俗套组合（AI=蓝紫青、企业=蓝白…） | **作者自查**（判据见下「俗套表」） | 见下「俗套表」 |
| 配色选择（用哪套 `colorSets`） | **作者声明**（spec 必填具名，脚本不推断） | `validate_spec.py` / `render.resolve_color_set` |
| 外部配色站取灵感 / 搜索关键词 | **流程**（人/AI 做，见本文） | 见下 |
| "好看的配色" | **判断**（测不出来，不做假检查） | — |

```bash
python3 scripts/ink.py styles/<你的风格>/style.json   # 逐色板验对比度（任一不达标退出码 1）
```

## Style 存结构，不存 HEX

规范第 21 条。**存死 HEX 的后果是换一套色就得改结构**（或者更糟：改了色没改结构，
两边开始漂）。所以分工是：

- `colorSets` 存四个角色的 HEX（仓库既有形状，没改）——**primary / secondary / background / text**
- `colorStructure` 存结构（作者声明；随自建风格建立）。它是**作者声明的
  设计意图**：`hue_structure` / `color_count` / `lightness_structure` /
  `saturation_structure` / `temperature` 这些字段按 OKLCH 判据自己写，脚本不再替你
  推算、也不再拿声明和实测对。

**色板只有上面四个角色**，不做 9 角色推导层（`surface` / `surface_alt` / `accent` /
`highlight` / `text_primary|secondary|muted` / `border` / `chart_colors` /
`gradient`）：渲染器读 `primary` / `secondary` / `background` 与文字色
（`ink.text_color()`），图表的 muted / 多系列深浅阶在渲染器里按「主色向纸色褪」
现算（`render.py::chart_muted` / `chart_series_colors`）。

**`colorStructure` 没有脚本消费** —— 它是留给风格作者的设计备注，写岔了不会报错。真正带牙的门槛是**对比度**（`ink.py`）与产物实测（`check.py`），见下。

### 配色由作者显式声明（总编排 §17 的落地）

规则说 "Style 出语法，Theme Resolver 按实际情况融合"。落地只有一条路：**作者按 deck
的实际情况选一套风格里手调好的 `colorSets`** —— 显式写 `deck.colorSet` 就是选它。

**没有 auto 派生**（省略 `colorSet` 或写 `"auto"` 一律被拦）—— 选色是审美决策，
脚本只做验收：
`validate_spec.py` 把缺失或不具名的 `colorSet` 判 `MISSING_COLOR_SET`（名字不在
`colorSets` 里判 `BAD_COLOR_SET`），`render.resolve_color_set` 再拦一道直接 SystemExit
—— 取色只有这一条路径。

所以 colorSets 是**人类手调的家底**（不是与规则冲突的"硬编码颜色"）；品牌色仍经由
`deck.merge_color_sets` 同名覆盖进入（品牌协议 §5）。从语法凭空生成全新主题（不要基准）
是未实现的约定 —— 没有感知模型撑着会出丑色。

## 为什么用 OKLCH 而不是 HSL

规范第 19 条要求"外部色板不得直接复制，要走 OKLCH 二次变体"。非它不可的理由：
**HSL 的 L 与感知明度不成正比** —— 黄色 HSL L=50% 在感知里很亮，蓝色 HSL L=50%
在感知里暗得多。拿 HSL 做变体会出现"提亮之后对比度反而掉了"，而这个流水线里
对比度是**硬门槛**（正文 4.5:1 —— 判据与检查在 `validation.md`）。

规范第 19 条给的变体范围（**规范值，作者手动执行**）：

| | 色相 | 彩度 | 明度 |
| --- | --- | --- | --- |
| 规范允许 | ±10°~30° | ±5%~20% | ±3%~12% |

**没有自动变体，也没有测量/推导代码** —— OKLCH 留在文档里，是**你读着规则
自己判色时的判据来源**：它感知均匀，比 HSL 更适合判明度与色相结构。唯一带牙的
颜色门是**对比度**，由 `ink.py` 用 sRGB 相对亮度算（`ink.contrast`）。
（三个方向怎么产，见下「三个方向」。）

**中性色不参与色相判定**（彩度低于一个阈值就跳过）—— 挪中性色的色相只会让它变脏。
经验阈值 `NEUTRAL_CHROMA = 0.03`（实测标定：一个目视为暖灰的 `#8A8578` 彩度
0.020，按 0.02 阈值会被算成"有色"、整套被误判成互补色）。

## 俗套表：说清是哪一条

规范第 18 条。扣分项**必须能说出扣的是哪一条**，否则"俗不俗"只是个没有说服力的
感觉。这张表是**作者选色时对着自查的清单**，没有跑分工具；每条判据都带着"为什么俗"：

| id | 判据 | 为什么 | 权重 |
| --- | --- | --- | --- |
| `tech_blue_purple_cyan` | 主题像 AI/科技 **且** 主色落在 H 200~320 且 C ≥ 0.10 | 训练数据里最高频的一套（规范第 23 条点名） | −0.30 |
| `corporate_blue_white` | 蓝主色（H 230~275）+ 白底 | 企业模板的默认解 | −0.18 |
| `premium_black_gold` | 深底 + 金色强调（H 60~100） | 高端感的默认解 | −0.15 |
| `even_saturation` | 主副两色饱和度都 ≥ 0.10 且相差 < 0.03，两色相隔 > 120° | 没有主次 | −0.12 |
| `low_lightness_contrast` | 背景与主体明度差 < 0.25 且底是浅的 | 重点浮不出来 | −0.15 |

加分项同理（非常规冷暖、低饱和+高纯度强调、中性+非典型强调）。

**这条不阻塞**（规范第 18 条的三档阈值 0.45/0.65/0.75 只作参考）：
**名单只作自查**，配色选哪套由作者声明
（`colorSet`）；带牙的画质门槛是**对比度**（`ink.py`）与产物实测（`check.py`）。

> 拿 AI 主题的 deck 自查一遍：`#0033CC` 这类蓝主色 + 白底的色板会同时命中
> `tech_blue_purple_cyan`（H 200~320、C ≥ 0.10）与 `corporate_blue_white`
> —— **想做 AI 主题的 deck，这类色板不该默认选**（照判据对着色值自己看）。

## 三个方向：配色由作者声明（无自动变体）

规范第 17 条：Safe / Creative / Experimental。**方向变体由作者手动产**（换色相 /
明度 / 饱和度各出一版再挑）：选色是审美决策，脚本只做验收。

替代做法是**作者显式声明**：`spec.deck.colorSet` 必填具名（缺失或写 `auto` 会被
`validate_spec.py` 判 `MISSING_COLOR_SET`、被 `render.resolve_color_set` 直接
SystemExit）。要"更 creative"就往风格的 `colorSets` 里加一套**手调**色板
（同风格加色板的 seam 见 `references/style-architecture.md`），不是让脚本去挪色相。

规范说"Creative 不满足可读性再回退 Safe" —— 可读性是**能测的**，但没有自动回退
这道工序：色板的对比度要验，跑
`ink.py <style.json>`（任一色板不达标退出码 1）—— 这是现在唯一还带牙的配色门。

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
对比度检查 → 角色映射）。**角色映射作者自己做**：取回色后把角色填进
`colorSets` 的 `primary` / `secondary` /
`background` / `text`（只这四个角色），再用 `ink.py` 验对比度。

## 页面一致性

规范第 22 条。这一条在本流水线里**天然成立**，因为整套 deck 只有一个 `colorSet`
（`deck.colorSet` 是 deck 级字段，不是页级）—— 所以"每页随机换主色"在结构上就做不到。
允许的变化（封面更大胆、内容页更克制）由版式承担，不由色板承担。

## 还没实现的（写清楚，别假装做了）

规范里有几条**本流水线还没有对应能力**，列在这里而不是含糊带过：

1. **渐变**。规范第 13 条那十种渐变类型（mesh / aurora / glow / conic…）都还没做 ——
   外壳里没有渐变。色板也没有 `gradient` 这条角色。
2. **玻璃拟态 / Glow / Mesh**。规范第 12 条的背景策略里有这些，当前只支持
   `solid` 与 `texture`（颗粒）。
3. **强调色占比的实测**。规范第 11 条说 5%~20%。`measure.py` 已经记了每个元素的
   `color`（measure.py:164；`measuredColor` 只是 pptx 导出侧的改名，
   pptx_native.py:409），所以**算得出来**（按元素盒面积统计），但还没接进 `check.py`。
4. **外部配色源的自动检索**。没有任何脚本联网取色 —— 取灵感这一步是流程（见上）。
