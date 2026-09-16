# 样式架构

风格目录里的 `style.json` 是**单一来源**（deck 项目的 `styles/<name>/`；`--style` 也吃路径）
—— 渲染器、skin.css、墨色门禁都从这一处读。
改色板 / 改字号 / 改错位量，**全在 token 里改**，spec 与脚本零改动。

## 风格从哪找：两根优先级（`DECK_STYLES` 可注入额外根）

`render.py` 按顺序找风格（`style_roots()`，render.py:68 起，**调用时求值**），先命中先用：

1. `DECK_STYLES` 环境变量（`:` 分隔）—— 风格放在 deck 项目之外时的显式入口
   （CI、/tmp 里的方向草稿）；
2. `<当前目录>/styles/` —— 风格跟着 deck 项目走（随项目交付、可移植）；
3. skill 自己的 `styles/` —— 用户**显式托管**的全局风格；**工具链永不写入**
   （写它 = 变相内置，用户明令禁止过）。

**没有内置风格、没有默认风格**：`deck.style` 必填，缺了就
`MISSING_STYLE` 并给指路报错。可拷贝的模板必然变成默认答案 ——
工具链不携带任何参考实现、示例风格或样例 spec，磁盘上也没有可找的。

`--style` 吃名字也吃路径（路径 → 临时草稿可直接渲）。

## 字段集（schema）

```jsonc
{
  // ── 必填顶层键 11 个（**形状契约**；缺键在渲染 / 校验时当场暴露：
  //    fonts.display|body 缺键渲染器 KeyError、type 缺档 deck 编译 SystemExit）──
  "version": 1,                          // schema 版本号；改了字段就 +1
  "label":       "风格显示名",               // `image_source.py --brief` 用；**从这份 deck 的内容长出来，
                                      // 不复用见过的风格名**（名字是锚：叫什么就会长成什么）
  "temperature": "一句话气质",              // 如「克制 · 冷」；--brief 按它挑提示词的气质档
  "reference":   "...",                  // 风格参考出处（--brief 的样式行显示）
  "note":        "...",                  // 设计缘由（给后人读）
  "colorSets": {
    "<name>": {                          // 色板集；spec 用 colorSet 字段引用名
      "primary":   "#RRGGBB",            // 主专色 —— 只做墨层 / 色块 / 装饰
      "secondary": "#RRGGBB",            // 副专色 —— 只做墨层 / 栏标 / 装饰
      "background": "#RRGGBB"            // 纸色
      // 文字色：声明了 "text" 用声明，否则 = overprint(primary, secondary) 派生
      // （ink.py text_color() —— 声明/派生同一个入口，见下文「两个可选字段」）
    }
  },
  // ── 以下四键是**可选 effect**（缺 = 该风格没有这个效果，不是"声明一堆零"）：
  //    ink / texture / decor / misregistration。普通风格（Swiss/Minimal/Glass…）
  //    不写 = 这套风格没有该效果（零错位、无纸纹层、无装饰）。
  "ink": {                                 // （可选）孔版/印刷系的叠印声明
    // ⚠️ **说明性元数据**：没有任何脚本读 ink.*；声明/派生的实际开关是
    // colorSets.*.text 是否存在（ink.py text_color()）。写这块只为留设计缘由。
    "derivation": "srgb-multiply",        // 叠印方式（sRGB 逐通道相乘 = 真实打印混色）
    "forText":    "overprint",            // 文字一律用叠印色
    "note":       "...",                  // 设计缘由（给后人读）
    "rule":       "每套色板必须含一个深墨 ..."  // 设计铁律
  },
  "contrast": {
    "minBody":     4.5,                   // 正文最小对比度（WCAG AA）
    "minLarge":     3.0,                  // 大字（≥ largeTextPx）最小对比度
    "largeTextPx":  32
  },
  "type": {                              // 字号级数（px）—— 15 档全必填（render.py:116）
    // ⚠️ 这组数**只是形状**，不是推荐值。实测事故：拿 128/96/84/46/32 那组
    // （海报/展厅尺度）排内页，每页都像封面页。怎么算见下方「字号怎么定」。
    "cover": 84, "compact": 48, "small": 38, "end": 84,
    "subtitle": 24, "bulletLarge": 30, "bullet": 24, "bulletSmall": 20,
    "colTitle": 26, "nodeLabel": 20, "nodeNote": 16,
    "chartValue": 16, "chartLabel": 14, "caption": 16, "foot": 14
  },
  "misregistration": {                     // （可选）错位声明；缺键 = dx/dy/rot 全 0
    "offsetRangeX": [lo, hi],             // 标题层 A 的 X 错位像素区间
    "offsetRangeY": [lo, hi],             // 标题层 A 的 Y 错位像素区间
    "rotationRange": [lo, hi],            // 整组旋转角度区间（度）
    "blendMode": "multiply"               // A / B 两层都用 multiply
  },
  "texture": {                             // （可选）纸纹声明；缺键 = 不发 .grain 层
    "grainOpacity":        [lo, hi],      // 颗粒层不透明度区间
    "grainBaseFrequency": 0.9,            // feTurbulence baseFrequency（颗粒密度）
    "halftoneDotSize":     [lo, hi]       // 装饰墨块的网点直径区间
  },
  "fonts": {
    "display": "Songti SC, Georgia, serif", // 标题字体栈（**必填**）
    "body":    "SF Mono, Menlo, monospace"  // 正文 / 注释字体栈（**必填**）
    // display / body 少一键渲染器直接 KeyError（render.py:704、726 读的就是这两键）
  },
  "viewerBackground": "#141414",         // 浏览器外底色（让纸色边能看见）
  "motion": {                            // 动效时间轴 —— 7 键必填；缺键 render.timeline 直接 KeyError（render.py:227）
    "easing":      "expoOut",                       // 只认 expoOut / overshoot（render.py:501 的 ease()）
    "cssEase":     "cubic-bezier(0.16, 1, 0.3, 1)", // 注入 CSS；现在无脚本校验（写 linear/ease 系显似 AI slop，自查）
    "enterMs": 520, "staggerMs": 70,                // 入场时长 / 逐条错峰
    "titleHoldMs": 260,                             // 标题独占期
    "holdMs": 2600, "readPerItemMs": 760            // 每页停留 / 逐条阅读时长
  }
}
```

### 字号怎么定：**算术夹出来的，不是审美挑的**

画布是恒定的事实：**1600×900**，正文带 = 900 − 132（上边）− 52（下边距）− 24（页脚）
= **692px**（`grid.py`）。所有字号都被同一组算式夹住：

```text
① 装得下：标题块 + 最满那页的各条文字 × 行高(1.5~1.7) ≤ 692
② 有层级：标题 : 正文 ≈ 2~3 倍；**相邻两档 ≥ 1.15 倍**（低于这个数，两级分不出来）
③ 看得清：观众距离 = 一臂之内/笔记本 → 正文 22~26；投影到 3m 外 → 30~34
```

按这三条算出来的区间（1600×900）：

| 档 | 区间 | 怎么想这件事 |
| --- | --- | --- |
| `cover` / `end` | 72~96 | 一页一句话，可以大；这是**全 deck 唯一**的大字场景 |
| `compact`（内页标题） | 40~56 | 内页标题是路牌，不是宣言 —— 用 96 就变成每页都是封面 |
| `small`（图/表/看板页标题） | 34~44 | 图是主角时，标题退半步 |
| `subtitle` | 22~28 | 跟正文档拉开 1~2 级，别和标题抢焦点 |
| `bulletLarge` | 28~34 | **只用于 1~2 条**的宣言页 |
| `bullet` | 22~26 | 4~6 条内容页的主力档 |
| `bulletSmall` | 18~21 | 7 条以上 / 双栏 |
| `colTitle` | 24~30 | 图内文字比正文再小一级 |
| `nodeLabel` / `nodeNote` | 18~22 / 15~18 | 图内文字比正文再小一级 |
| `chartValue` / `chartLabel` | 15~18 / 13~15 | 图表里的字只在凑近看时读 |
| `caption` / `foot` | 15~18 / 13~15 | 注释与页脚：全场最小 |

**字号跟内容量走**，不是跟风格气质走：同一套风格里，1 条的宣言页用 `bulletLarge`，
6 条的内容页用 `bullet` —— 条目数变了，档就换（`bulletTier` 由你在 spec 里声明）。

`check.py` 有**字号体检**（提示级，四条线）—— 装得下就没人报错，所以必须有人开口：

```text
· 内页标题是封面尺度：第2页 96px（= type.compact）（共 4 页超过 72px）—— 内页标题的合理区是 40~56px
· 条目多但用的是宣言档字号：第3页 5条×46px —— 大字配 1~2 条是气质，配 4 条以上就挤
· 内页正文整体偏大：中位数 46px（推荐 20~28px）
```

### 字体栈：写**意图**，回退了会告诉你

这两个值是完整的 CSS 字体栈，按意图从先到后写 —— **不是**“本机装了哪个”。

本机实测（macOS）：

| 栈 | 首选 | 实际 |
| --- | --- | --- |
| `display` | `Songti SC` ✓ 可用 | 就是它 |
| `body` | `SF Mono` ✗ 本机没有 | 回退到 `Menlo` ✓ |

`check.py` 会把这件事**当提示报出来**，并且说清**谁顶上了**：

```text
· 字体回退（启发式提示）：声明的 'SF Mono' 在本机不可用，实际用的是 'Menlo'
```

它不阻塞交付（启发式，衬线撞衬线会误报），但值得看一眼 —— **排版会随机器变**，
而“排版随机器变”直接影响版面越界（`measure.py` 量的是**当前这台机器**的样子）。

两条容易踩的：

- **通用族不是字体**：`serif` / `monospace` / `sans-serif` 是**回退目标**。
  拿它们比宽度会得到“与不存在的族一样宽”，从而误报“缺失”。已经排除。
- **没有文字的元素不该有字体意见**：`<figure class="imgwrap">` 这类不渲染字形的
  元素，它的 `font-family` 只是浏览器给 CJK 的 UA 默认值（实测报过一次
  `PingFang SC`，而页面上根本没写这个族）。现在只统计**真有文字**的元素。

### 方向怎么来：从这份 deck 推，不从风格史挑

**铁律：不设风格清单。** 任何样式清单（对照表 / 参数表 / 目录）都会被读者当成
选项清单 —— 方向只能按下面的程序从内容生成。

选风格看的是**画面**：每渲一页出来看（`render.py` + `shots.py`），不是对着文字想象。

**第 1 步 · 从内容推气质**（一行一个依据，写在草稿里）：

- 观众是谁？他们**信什么**（数字 / 权威 / 现场演示 / 逻辑链）？
- 场合是什么（投屏远讲 / 桌面近读 / 评审答辩 / 发布会）？
- 材料本身的气质（工程 / 商业 / 学术 / 创意 / 行政）？

**第 2 步 · 在四条轴上各取一个点**（轴是坐标系，不是风格名）：

- 骨架：版心式 / 边轨式 / 分栏式 / 满版式 / 网格式
- 字感：衬线 / 无衬线 / 等宽 / 混排
- 密度：疏（一页一句）/ 中（3~5 条）/ 密（看板）
- 色彩策略：纸感单色 / 双色对撞 / 深底反白 / 大色场

**第 3 步 · 三个方向必须互斥**：任意两方向至少在**两条轴**上不同，且其中一条必须是
**骨架**轴 —— 只差色板的三个方向是三张同构皮肤（用户实测踩过的坑）。

**第 4 步 · 命名从内容长出来**：用这份 deck 自己的隐喻 / 领域词命名；
**不复用你见过的任何风格名** —— 名字是锚：叫什么就会长成什么。

两个诚实的说明：

- **字体全部映射到本机可用的族**。网上抄来的 preset 大多写 Google Fonts 的名字
  （Archivo Black / Space Grotesk / Fraunces / Clash Display…），
  本机没有，直接抄进来会静默回退成默认字体 —— 那比不设计还糟（"看着差不多"但品味全丢）。
  所以取的是它们的**意图**（衬线/等宽/几何/高饱和），落在本机真有的族上。
- **中文没有可用的等宽族**，所以“等宽感”主要由拉丁字母、数字和标点承担，
  中文落黑体。这是取舍，不是遗漏。

## 多风格 seam（如何加新风格）

有三类"加风格"：

### A. 加一套色板（同风格、新色板）

`colorSets` 里再加一个键。`ink.py` 会自动把该风格**全部色板**纳入门禁
（有几套查几套）。
**唯一约束**：`rule` —— 文字色对比度必须达到 `contrast.minBody`（派生或声明都一样）。
两墨都亮时压不深（比如朱红 × 土黄只有 3.74 ✗），
至少其中一个要走深色（朱红 × 深棕 → 达标 ✓）。

`render.py` / `check.py` 不需要改 —— 它们从 token 注入一切。

### B. 加一种新视觉风格

> 之前这一节写的是「要走一个比这更大的改造，代价 ≈ 0.5~1 个工作日」。那个 seam 现在
> **已经建好了，而且不是靠分支实现的** —— 下面是实际做法。

一个风格 = **deck 项目**里 `styles/<name>/` 一个目录，里面两件东西：

```text
styles/<name>/
  style.json   token：色板 / 字号级数 / 字体 / 纹理 / 装饰 / 错位区间 / 对比度门槛
  skin.css     视觉层：颜色、字体、纹理、装饰观感
```

**加一种风格 = 写一个目录（style.json + skin.css），不碰任何 .py，不留可拷的参考实现
（模板必然变成默认答案）。** 这条 seam 需要 token 添过一个可选字段
（`colorSets.*.text`，见下）以外，渲染/校验/导出的代码一行未改。

**为什么要做成目录而不是 CSS 分支**：分支意味着每加一种风格就多一个 if，
而且校验层也得跟着分支 —— 最后没人愿意加第三种。目录意味着新风格**碰不到别人**。

#### 风格契约（skin.css 只能长在这几个钩子上）

渲染器只出**语义骨架**：`section.slide` + `.title` / `.subtitle` / `.bullets` /
`.col` / `.tl` / `.chartwrap` / `.foot` 加几何。skin.css 负责它们的"长相"，
并把风格专属零件（纸纹 `.grain`、装饰 `.halftone`）接上去。

必须提供的 CSS 变量：

| 变量 | 含义 |
| --- | --- |
| `--paper` / `--text` | 底色 / 正文色 |
| `--accent` / `--accent-2` | 主色 / 副色（做色块、细线、图表、装饰） |
| `--display` / `--body` | 标题字体 / 正文字体 |
| `--viewer` | 浏览器外底色 |

字号不走变量硬写：token 的 `type` 级数整份注入为 `--t-*`，每种版式再用 `--s-title` /
`--s-bullet` … 指向其中一档。**字号只有这一处来源** —— Python 侧写进语义清单的
也是同一份（字号两张表必然写岔）。

#### token 里的两个可选字段

- **`colorSets.*.text`**：显式文字色。两种来路，走同一个入口 `ink.text_color()`，
  所以对比度门槛仍然只有一条：
  - **声明**（`"derivation": "explicit"`）：直接给文字色。黑底白字 / 白底黑字 /
    粉彩纸这类风格必须这样 —— 拿它们的 primary×secondary 去推会得到一个
    根本不适合当文字的色。
  - **派生**（`overprint(primary, secondary)`，两墨相乘就是真实叠印的数学）：
    给"两墨叠印"那种印刷隐喻的风格用。

  ⚠️ **现状：显式声明（`text`）是唯一在用的路径**。派生那条路只剩下
  `ink.overprint()` 与它的单元测试 —— 集成路径没有被验证过。要启用它
  （做一套真正的孔版风格）请把新风格渲出来量一遍对比度，
  别因为测试是绿的就当它已经在生产里跑过。
- **`decor.kind`**：放什么装饰 —— `halftone-circle`（网点圆）/ `accent-block`
  （大色块，render.py:271）；不写或 `null` = 无装饰（render.py:268 提前返回）。
  写了 kind 就要配 **`decor.sizes`**（装饰尺寸池，渲染器按 (seed, index) 从里抽，
  render.py:279-280、285-286）。连带 `decor.types`（哪些版式放）与 `decor.zones`（放哪个角）
  都是**风格自报的**，不是写死在渲染器里的。

#### token 里的三个可选**作者数据**键

这三个键**脚本不推断**，是风格自报的数据（缺省 = 走内置缺省）：

- **`titleTiers`**：`{版式: 档名}`，覆盖渲染器的缺省映射 `render.TITLE_TIER`
  （`{title: cover, content-text: compact, end: end}`，render.py:105）。值域 =
  `REQUIRED_TYPE_TIERS`（render.py:116 的档名集合）。合并顺序：缺省映射 →
  风格 `titleTiers` → spec 逐页 `titleTier`（deck.py:484、490）。
- **`bulletDefault`**：content-text / content-image 页的缺省条目档名，缺省值
  `"bullet"`（`render.DEFAULT_BULLET_TIER`，render.py:129）；spec 逐页 `bulletTier`
  覆盖它（deck.py:486、496-498）。two-column 仍固定 `bulletSmall`（结构事实，
  不受此键影响）。
- **`layouts`**：这套风格自报的**布局词表**（非空字符串数组）。渲染器认的结构布局
  （`IMAGE_LAYOUTS`、`TWO_COL_LAYOUTS`，render.py:84、88）之外，作者自造的布局名
  写法受它约束：`check.py::_layout_vocab_problems`（check.py:405）在风格声明了
  `layouts` 时，把不在词表里、又不是结构布局的 `spec.layout` 判成**阻塞** problem
  —— 自造名写错一个字母，skin 里那条规则就永远不生效，最难查的那种静默。

这三者的校验**随 `style.py --check` 退役后分给了两处**：`titleTiers` / `bulletDefault`
的档名由 `deck.py::compile_spec`（deck.py:504-509）在编译时报 —— 档名不在风格的
`type` 块里直接 SystemExit；`layouts` 的词表门由 `check.py::_layout_vocab_problems`
（check.py:405）在产物校验时按词表拦拼写。形状的其余部分（如 `layouts` 必须是
非空字符串数组）没有单独的"契约体检"了 —— 写错会在用到它的那条路上暴露。

#### 换风格需要重审什么

`check.py` 的门槛**全部从所选风格的 token 读**，不用改代码；但要确认新 token 里
这几项填得合理：`type` 的级数（字号是否匹配观看距离）、`contrast` 门槛、
`motion` 的时间轴（快慢节奏要配风格气质 —— 缓动只认 expoOut / overshoot，
render.py:501；7 个时间键缺一个，`render.timeline` 读 `tokens["motion"]` 时直接
KeyError，render.py:227）、
`misregistration`（要做错位才写区间 —— ③ 那条区间校验只在**写了**时生效；
不做错位的风格直接不写这个键）。

### C. 从零写（没有脚手架，也没有可拷的参考实现）

**从零写，没有别的方式。** 契约全在本文档里（顶层键 / 字号档 / 色板 / motion / 可选
effect）：

```bash
mkdir -p <deck项目>/styles/<名> && $EDITOR <deck项目>/styles/<名>/style.json
```

（在 **deck 项目的 `styles/`** 里现写；skill 自己的 `styles/` 只放用户显式托管的
全局风格，工具链与手工都不往里写 —— 写它 = 变相内置。）

## spec 字段集（deck-spec.json）

```jsonc
{
  "deck": {
    "style":    "my-style",          // **必填**（缺 = `MISSING_STYLE`）——没有默认风格，
                                      // 也不内置任何风格。风格名（两根顺序查找：
                                      // <cwd>/styles → skill 的 styles/，另有 DECK_STYLES
                                      // 环境变量可注入额外根）或**显式目录路径**（临时
                                      // 草稿直接渲：--style /tmp/dir-a）
    "colorSet": "blue",               // **必填具名**（auto/mood 一律判失败）——
                                      // 写名 = 该风格 token.colorSets 的键；缺失或写
                                      // "auto" → validate_spec 判 MISSING_COLOR_SET，
                                      // render.resolve_color_set 再拦一道 SystemExit
    "seed":     11,                   // 建议显式写（缺省 1）；错位/颗粒按 (seed, 元素) 派生
    "title":    "封面文案",
    "brand":    "acme",               // 可选；品牌协议 —— 字体并入、色板同名键品牌赢
                                      // （deck.py:462）
    "note":     "...",                // 可选；deck 级备注（封闭字段集放行，工具链不消费）
    "slides": [
      {
        "type": "title" | "content-text" | "content-image"
             | "two-column" | "timeline" | "chart" | "end",
        "title":    "...",            // 所有版式都有
        "subtitle": "...",            // 仅 title 页
        "bullets":  ["..."],          // content-text / content-image
        "image":    "pic.png",        // 仅 content-image；相对路径或 assetId（见下节）
        "layout":   "visual-right",   // 可选；非空字符串自由值（"auto" 判 BAD_LAYOUT）。
                                      // 结构布局（渲染器能力）：content-image 的
                                      //   visual-right（缺省）/ visual-left / even / hero；
                                      //   two-column 的 even（缺省）/ lean-left / lean-right。
                                      // 其它字符串 = 作者自造布局名 → 套缺省结构 +
                                      //   data-layout="<名>"，排法由 skin.css 写；风格声明的
                                      //   layouts 词表按词表验拼写（check 阻塞，见上文「token 里的三个可选作者数据键」）
        "titleTier":  "compact",      // 可选；标题档名（风格 type 块里的键）—— 风格
                                      //   titleTiers 定缺省映射，这里逐页覆盖（chart 除外）
        "bulletTier": "bullet",       // 可选；条目档名（content-text / content-image /
                                      //   two-column）—— 缺省取风格 bulletDefault
        "columns":  [{title, bullets}, ...],  // 仅 two-column；至多两栏
        "nodes":    [{label, note}, ...],     // 仅 timeline
        "chart":    "bar",            // 仅 chart；**必填**的显式图形（bar / bar-horizontal /
                                      //   line / area / bar-stacked / donut / scatter /
                                      //   combo 八类，render.py:780 / validate_spec.py:41）；缺失 = MISSING_CHART_TYPE
        "intent":   "comparison",     // 仅 chart；可选**语义标注**（不决定图形）——
                                      //   trend / ranking / comparison / correlation /
                                      //   deviation / distribution / composition /
                                      //   progress，八值封闭，validate_spec 校验
        "message":  "结论一句话",      // 仅 chart；写了就当图表**大标题**（render.py:1252-1258），
                                      // 原 title 降为数据集名
        "data":     [{label, value}, ...],    // 仅 chart（scatter 豁免 x/y）
        "series":   [{name, data}, ...],      // 仅 chart；多序列
        "emphasis": {"values": ["标签"]},     // 仅 chart；命中的用主色，其余灰化
        "annotations": [{type, target, text, value}, ...],  // 仅 chart；v4 不渲染（见 charts.md「标注」）
        "unit":     "%",              // 仅 chart；数值单位
        "caption":  "...",            // 仅 chart / content-image
        "color":    "overprint"       // 可选；只允许 "overprint"（不写也行）
      }
    ]
  }
}
```

**字段集是封闭的**：`validate_spec.py` 会把未知键直接判失败，并按类别给专门说明
（坐标 / 字号 / 色值三类各有自己的话）。所以 `fontSize` / `x` / `y` 这类写法一开始
就被挡下来 —— 不用等到产物那里才发现"它根本没生效"。

v3 退役的两个字段现在都是未知键，写它们会被判 `UNKNOWN_FIELD`，提示里各有一条
指路：`variant`（改叫 `layout`）、`mood`（配色不再由语义推导，直接写 `colorSet`）。

`check.py` **不管**字段集（它验的是产物）；它唯一会主动拦的字段是 `color`：第 ① 条
只接受 `"overprint"`，写成色值（如 `"#FF0000"`）会判失败。

## 图怎么进来：assetId → `assets/<file>`（§14 管线 v1）

图文页的 `image` 有两种写法：

- **相对路径**（相对 spec 所在目录）：没有 `assets/manifest.json` 时用这种；
- **assetId**（语义引用）：放了 manifest 时，`image` 写清单里的 id。清单是**封闭
  schema v1**：`{"schemaVersion": 1, "assets": {id: {file, source, note}}}`
  （render.py:977-978），`file` 相对 `assets/` 目录。

解析只发生在 compile：assetId → `"assets/<file>"`（§14 优先级链 v1 —— **manifest 即
选择**），页对象携带最终路径，渲染器不见 assetId；每条解析写进 compile trace
（deck.py:522-530）。缺文件由 `check.py` 的「图片加载」门实测拦。
清单的上游（`assets/requests/<槽位id>.json` 先要、图回来登记进 manifest）见
`references/images.md`。

## seed 的不可替代性

`(seed, 元素)` 派生 = 同一份 spec 重渲两次**逐字节一致**。
全局 random 拿掉 seed 也"看起来差不多"，但：

- 不能回归对比（昨天出的 vs 今天出的）
- 不能复现一版给别人（"我看到的"和"你看到的"差几个像素）

`render.py` 用的派生 key 是 `"|".join([str(seed)] + [str(p) for p in parts])`，
所以同一页里不同元素、不同页、不同时间段都互不相关 —— 不会出现
"整页统一向右偏移 1px"那种肉眼能看出来的相关性。

不要换成 `random.seed(seed); random.uniform(...)` —— 那会破坏可复现性。
