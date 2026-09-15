# 配色：结构、角色、novelty、三个方向

这一层实现的是"AI 视觉配色规范"。**先说清分工**，因为这份规范里大部分讲的是
**生成过程**（怎么想），而代码能负责的只有**结构与校验**（怎么测）：

| 规范里的内容 | 谁负责 | 在哪 |
| --- | --- | --- |
| 色相关系 / 颜色数量 / 明度 / 饱和度 / 冷暖 | **代码算**（OKLCH 实测） | `palette.py::structure_of` |
| 13 个颜色角色 | **代码推导**（从色板四个角色推） | `palette.py::roles` |
| 文字可读 / 背景与主体明度不能太近 | **阻塞** | `palette.py --audit`、`ink.py` |
| 俗套组合（AI=蓝紫青、企业=蓝白…） | **按主题条件提示**，且**说清是哪一条** | `palette.py::novelty` |
| Safe / Creative / Experimental 三方向 | **代码生成**（OKLCH 变体，确定性） | `palette.py::directions` |
| 外部配色站取灵感 / 搜索关键词 | **流程**（人/AI 做，见本文） | 见下 |
| "好看的配色" | **判断**（测不出来，不做假检查） | — |

```bash
python3 scripts/palette.py --audit                                  # 8 套风格全审
python3 scripts/palette.py --audit --topic "AI 大模型架构"            # 带上主题判俗套
python3 scripts/palette.py --novelty swiss-grid blue --topic "AI…"   # 一个色板的 novelty 与依据
python3 scripts/palette.py --directions swiss-grid blue              # 三个方向
python3 scripts/palette.py --roles swiss-grid blue                   # 13 个角色的推导结果
```

## Style 存结构，不存 HEX

规范第 21 条。**存死 HEX 的后果是换一套色就得改结构**（或者更糟：改了色没改结构，
两边开始漂）。所以分工是：

- `colorSets` 存四个角色的 HEX（仓库既有形状，没改）——**primary / secondary / background / text**
- `colorStructure` 存结构（本次新增到 8 套风格里）
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

## 为什么用 OKLCH 而不是 HSL

规范第 19 条要求"外部色板不得直接复制，要走 OKLCH 二次变体"。非它不可的理由：
**HSL 的 L 与感知明度不成正比** —— 黄色 HSL L=50% 在感知里很亮，蓝色 HSL L=50%
在感知里暗得多。拿 HSL 做变体会出现"提亮之后对比度反而掉了"，而这个流水线里
对比度是**硬门槛**（文字必须过 4.5:1）。

变体范围按规范第 19 条：

| | 色相 | 彩度 | 明度 |
| --- | --- | --- | --- |
| 规范允许 | ±10°~30° | ±5%~20% | ±3%~12% |
| 本实现（creative） | +18° | ×1.12 | +0.02 |
| 本实现（experimental） | −28° | ×1.20 | −0.04 |

**中性色不参与色相变化**（彩度低于 `NEUTRAL_CHROMA` 就跳过）—— 挪中性色的色相只会
让它变脏。`NEUTRAL_CHROMA = 0.03` 是**按实测标定的**：`pastel-geometry` 的副色
`#8A8578` 彩度 0.020，目视就是暖灰，可它正好卡在 0.02 上，于是被算成"有色"，那套风格
被误判成互补色（实测发现）。

变化是**确定性的**（按角色取固定角度，不用随机）—— 随机会让同一份 spec 两次跑出
不同的色，那就没法回归了。

## 俗套表：说清是哪一条

规范第 18 条。扣分项**必须能说出扣的是哪一条**，否则 novelty 只是个没有说服力的数字。
每条判据都带着"为什么俗"：

| id | 判据 | 为什么 | 权重 |
| --- | --- | --- | --- |
| `tech_blue_purple_cyan` | 主题像 AI/科技 **且** 主色落在 H 200~320 且 C ≥ 0.10 | 训练数据里最高频的一套（规范第 23 条点名） | −0.30 |
| `corporate_blue_white` | 蓝主色（H 230~275）+ 白底 | 企业模板的默认解 | −0.18 |
| `premium_black_gold` | 深底 + 金色强调（H 60~100） | 高端感的默认解 | −0.15 |
| `even_saturation` | 两个高饱和色相且饱和度接近 | 没有主次 | −0.12 |
| `low_lightness_contrast` | 背景与主体明度差 < 0.25 且底是浅的 | 重点浮不出来 | −0.15 |

加分项同理（非常规冷暖、低饱和+高纯度强调、中性+非典型强调）。

**实测：本仓库 8 套风格里 5 套的某个色板正落在名单上** —— 所以这条**不能一律阻塞**，
否则仓库自己的风格先挂。它只做两件事：按**主题条件**指出"这套色 + 这个主题正好落在
最俗的组合上"，以及在你显式要求时（`--min-novelty`）当闸门。阈值按规范第 18 条：
普通 PPT 0.45 / 设计型 0.65 / 创意封面 0.75。

> 拿 `--topic "AI 大模型架构"` 审一遍就会看到 `swiss-grid/blue` 同时命中
> `tech_blue_purple_cyan` 与 `corporate_blue_white`，`keynote-dark/blue` 命中前者。
> **这说明规范那两条不是空话，而是本仓库真实存在的情况** —— 想做 AI 主题的 deck，
> 这几个色板不该默认选。

## 三个方向

规范第 17 条：Safe / Creative / Experimental。本实现把它们做成**同一套色的三个 OKLCH
变体**（而不是三套无关的色），因为规范要求"保留原 Palette 的视觉关系"：

- **Safe** —— 原样。稳定、克制、可用于正式汇报
- **Creative** —— 色相挪 18°、彩度提 12%、明度微提。**默认优先选它**
- **Experimental** —— 反方向挪 28°、彩度提 20%、明度降。制造冷暖反差，用在封面/视觉页

规范说"Creative 不满足可读性再回退 Safe" —— 可读性是**能测的**，所以这个回退是
可执行的：跑 `--directions` 看哪一套过 `ink.py` 的对比门槛。

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
| [Huemint](https://huemint.com/) | 高创造力候选 | 适合 Creative / Experimental 那一档 |

**取回来的色不得直接复制**：走第 19 条的变体流程（保留色相关系 → OKLCH 变体 →
对比度检查 → 角色映射）。`palette.py --roles` 是最后一步的现成工具。

## 页面一致性

规范第 22 条。这一条在本流水线里**天然成立**，因为整套 deck 只有一个 `colorSet`
（`deck.colorSet` 是 deck 级字段，不是页级）—— 所以"每页随机换主色"在结构上就做不到。
允许的变化（封面更大胆、内容页更克制）由版式承担，不由色板承担。

## 还没实现的（写清楚，别假装做了）

规范里有几条**本流水线还没有对应能力**，列在这里而不是含糊带过：

1. **渐变**。`palette.py::roles` 会推出 `gradient`（含非线性 stop：0 / 0.23 / 0.68 / 1.0），
   但**渲染层没有用它** —— 8 套风格的 `gradient_strategy` 都是 `none`，外壳里没有渐变。
   规范第 13 条那十种渐变类型（mesh / aurora / glow / conic…）都还没做。
2. **玻璃拟态 / Glow / Mesh**。规范第 12 条的背景策略里有这些，当前只支持
   `solid` 与 `texture`（颗粒）。
3. **强调色占比的实测**。规范第 11 条说 5%~20%。`measure.py` 已经记了每个元素的
   `measuredColor`，所以**算得出来**（按元素盒面积统计），但还没接进 `check.py`。
4. **外部配色源的自动检索**。`palette.py` 不联网 —— 取灵感这一步是流程（见上）。
