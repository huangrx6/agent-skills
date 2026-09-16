# 样式架构

风格目录里的 `style.json` 是**单一来源**（deck 项目的 `styles/<name>/`；`--style` 也吃路径）
—— 渲染器、skin.css、墨色门禁都从这一处读。
改色板 / 改字号 / 改错位量，**全在 token 里改**，spec 与脚本零改动。

## 风格从哪找：三根优先级

`render.py` 按固定顺序找风格（`STYLE_ROOTS`，render.py:68-70），先命中先用：

1. `<当前目录>/styles/` —— 风格跟着 deck 项目走（随项目交付、可移植）；
2. skill 自己的 `styles/` —— 用户**显式托管**的全局风格；**工具链永不写入**
   （写它 = 变相内置，用户明令禁止过；`style.py --new` 有守卫，见下文「从脚手架起手」）；
3. `dev-tools/style-fixture/` —— 开发夹具（minimal-baseline / swiss-grid），当参考拷改。

缺省风格 `swiss-grid`（render.py:71 `DEFAULT_STYLE`）；`--style` 吃名字也吃路径。

## 字段集（schema）

```jsonc
{
  // ── 必填顶层键 11 个（style.py:64 REQUIRED_KEYS；缺一个 --check 当场指名报）──
  "version": 1,                          // schema 版本号；改了字段就 +1
  "label":       "瑞士栅格 Swiss Grid",   // 风格显示名（style.py 摘要 / 联系表用）
  "temperature": "安静 · 冷",            // 一句话气质（联系表行标签）
  "reference":   "...",                  // 风格参考出处（style.py 摘要显示）
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
  //    照 dev-tools/style-fixture/minimal-baseline 起手即可，一个都不用写。
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
    "cover": 128, "compact": 96, "small": 84, "end": 128,
    "subtitle": 36, "bulletLarge": 46, "bullet": 32, "bulletSmall": 26,
    "colTitle": 40, "nodeLabel": 28, "nodeNote": 22,
    "chartValue": 20, "chartLabel": 18, "caption": 24, "foot": 20
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
    // display / body 少一键渲染器直接 KeyError（render.py:765、787 读的就是这两键）
  },
  "viewerBackground": "#141414",         // 浏览器外底色（让纸色边能看见）
  "motion": {                            // 动效时间轴 —— 7 键必填（style.py:73 REQUIRED_MOTION）
    "easing":      "expoOut",                       // 只认 expoOut / overshoot（style.py:78）
    "cssEase":     "cubic-bezier(0.16, 1, 0.3, 1)", // 注入 CSS；linear/ease 系 --check 拦
    "enterMs": 520, "staggerMs": 70,                // 入场时长 / 逐条错峰
    "titleHoldMs": 260,                             // 标题独占期
    "holdMs": 2600, "readPerItemMs": 760            // 每页停留 / 逐条阅读时长
  }
}
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

### 历史八套风格对照（内置已删 —— 表保留作自建参考）

选风格看的是**画面**，不是这张表 —— 先跑 `python3 scripts/style.py --sheet -o s.png`
把现有的每套风格拼进一张图（内置八套已删；现在渲的是夹具两套
minimal-baseline / swiss-grid，外加你自建的），再回来看哪个适合场合。

| `style` | 温度 | 构图锚点 | 适合 | 不适合 |
| --- | --- | --- | --- | --- |
| `keynote-dark` | 大胆·暗 | 字够大 + 负空间 | 会议室投屏站着讲、一屏一个观点 | 高密度汇报（一页只能装几条） |
| `botanical-dark` | 大胆·暖 | 右侧细竖线 + 描边圆环 | 品牌发布、客户提案（要"贵"不要"响"） | 数据密集的汇报（衬线小字投影吃亏） |
| `billboard` | 大胆·亮 | 色场 + 巨号数字 | 路演 / QBR / 年度复盘（只关心几个数） | 需要慢慢读的长文页 |
| `swiss-grid` | 安静·冷 | 左轨 + 标题下实线 + 巨号页码 | 路演、评审、研报、要被反复翻阅的文档型 deck | 需要"气势"的发布会 |
| `paper-ink` | 安静·暖 | 粗细线夹标题 + 段首悬挂短横 + 书眉 | 研究结论、行业观察、白皮书式 deck | 站着讲的发布会（衬线小字吃亏） |
| `notebook` | 中性·暖 | 横格纸 + 红边线 + 侧边索引签 | 培训、工作坊、读书笔记（观众会凑近） | 投影远距离演讲（字号偏小） |
| `terminal` | 中性·冷 | 标题前的 `$` + 右上状态行 | 技术评审、架构决策、事故复盘 | 给非技术受众的路演（等宽显冷） |
| `pastel-geometry` | 中性·暖 | 页角圆角色块 + 竖药丸标记 | 内部培训、新人引导、跨部门沟通 | 投影远距离讲、或要讲坏消息 |

两个诚实的说明：

- **字体全部映射到本机可用的族**。社区那些 preset（frontend-slides / html-ppt-skill）
  大多写 Google Fonts 的名字（Archivo Black / Space Grotesk / Fraunces / Clash Display…），
  本机没有，直接抄进来会静默回退成默认字体 —— 那比不设计还糟（"看着差不多"但品味全丢）。
  所以取的是它们的**意图**（衬线/等宽/几何/高饱和），落在本机真有的族上。
- **中文没有可用的等宽族**，所以 `terminal` 的"等宽感"主要由拉丁字母、数字和标点承担，
  中文落黑体。这是取舍，不是遗漏。

## 多风格 seam（如何加新风格）

有三类"加风格"：

### A. 加一套色板（同风格、新色板）

`colorSets` 里再加一个键。`ink.py` 会自动把该风格**全部色板**纳入门禁
（有几套查几套 —— 夹具 swiss-grid 现在是 4 套）。
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

**加一种风格 = 拷一份目录改内容，不碰任何 .py。** 历史八套全部是这样做出来的（已移除；参考实现 dev-tools/style-fixture/swiss-grid）
（`keynote-dark` / `swiss-grid` / `billboard` / `notebook` / `botanical-dark` /
`terminal` / `paper-ink` / `pastel-geometry`），除了给 token 添了一个可选字段
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
也是同一份（早先 Python 一张表、CSS 另一张表，实测写岔过：清单说 86、CSS 是 180）。

#### token 里的两个可选字段

- **`colorSets.*.text`**：显式文字色。两种来路，走同一个入口 `ink.text_color()`，
  所以对比度门槛仍然只有一条：
  - **声明**（`"derivation": "explicit"`）：直接给文字色。黑底白字 / 白底黑字 /
    粉彩纸这类风格必须这样 —— 拿它们的 primary×secondary 去推会得到一个
    根本不适合当文字的色。
  - **派生**（`overprint(primary, secondary)`，两墨相乘就是真实叠印的数学）：
    给"两墨叠印"那种印刷隐喻的风格用。

  ⚠️ **现状：现存两套夹具（minimal-baseline / swiss-grid）的色板全部走声明**（显式
  `text`）。派生那条路只剩下 `ink.overprint()` 与它的
  单元测试 —— **没有任何一套在用**，所以它是一条"数学被钉住、但集成路径没被验证"
  的缝。要启用它（做一套真正的孔版风格）请把新风格渲出来量一遍对比度，
  别因为测试是绿的就当它已经在生产里跑过。
- **`decor.kind`**：放什么装饰 —— `halftone-circle`（网点圆）/ `accent-block`
  （大色块，render.py:279）；不写或 `null` = 无装饰（render.py:273 提前返回）。
  写了 kind 就要配 **`decor.sizes`**（装饰尺寸池，渲染器按 (seed, index) 从里抽，
  render.py:283、297）。连带 `decor.types`（哪些版式放）与 `decor.zones`（放哪个角）
  都是**风格自报的**，不是写死在渲染器里的。

#### token 里的三个可选**作者数据**键（v3）

这三个键**脚本不推断**，是风格自报的数据（缺省 = 走内置缺省）：

- **`titleTiers`**：`{版式: 档名}`，覆盖渲染器的缺省映射 `render.TITLE_TIER`
  （`{title: cover, content-text: compact, end: end}`，render.py:105）。值域 =
  `REQUIRED_TYPE_TIERS`（render.py:116 的档名集合）。合并顺序：缺省映射 →
  风格 `titleTiers` → spec 逐页 `titleTier`（compile.py:134、140）。
- **`bulletDefault`**：content-text / content-image 页的缺省条目档名，缺省值
  `"bullet"`（`render.DEFAULT_BULLET_TIER`，render.py:129）；spec 逐页 `bulletTier`
  覆盖它（compile.py:136、148）。two-column 仍固定 `bulletSmall`（结构事实，
  不受此键影响）。
- **`layouts`**：这套风格自报的**布局词表**（非空字符串数组）。渲染器认的结构布局
  （`IMAGE_LAYOUTS`、`TWO_COL_LAYOUTS`，render.py:84、88）之外，作者自造的布局名
  写法受它约束：`check.py::_layout_vocab_problems`（check.py:405）在风格声明了
  `layouts` 时，把不在词表里、又不是结构布局的 `spec.layout` 判成**阻塞** problem
  —— 自造名写错一个字母，skin 里那条规则就永远不生效，最难查的那种静默。

`style.py --check`（`audit()`，style.py:174-190）会校验三者的形状与值域：
`titleTiers` 的每个值、`bulletDefault` 都得是 `REQUIRED_TYPE_TIERS` 里的档名，
`layouts` 必须是非空字符串数组 —— 形状/值域不对当场报，不等它静默走默认
（静默最难查）。

#### 换风格需要重审什么

`check.py` 的门槛**全部从所选风格的 token 读**，不用改代码；但要确认新 token 里
这几项填得合理：`type` 的级数（字号是否匹配观看距离）、`contrast` 门槛、
`motion` 的时间轴（快慢节奏要配风格气质 —— 缓动只认 expoOut / overshoot，
style.py:78；7 个时间键缺一个，style.py:73 的 REQUIRED_MOTION 会报）、
`misregistration`（要做错位才写区间 —— ③ 那条区间校验只在**写了**时生效；
不做错位的风格直接不写这个键）。

### C. 从脚手架起手（`style.py --new`）

不想从零拷目录时，`style.py --new` 先替你拷一份**契约完整**的脚手架 ——
底座取夹具 tokens（字号档 / 字栈 / 动效 / 契约齐全），再拷一份夹具 `skin.css`：

```bash
python3 scripts/style.py --new my-style            # 写 <当前目录>/styles/my-style/
python3 scripts/style.py --new my-style --dir /项目/styles
```

行为（`new_style()`，style.py:81）：

- v3 **不再有方向预设**（`PRESETS` 已删除）—— 方向是模型读规则后按题目自己造的，
  预设等于内置（用户明令禁止）。脚手架只保证"起手就过契约"，字号档 / 字栈 /
  色板 / 气质都由作者按题目改；
- **缺省写 `<当前目录>/styles/<name>/`**（风格跟 deck 项目走），`--dir` 可指到别处；
- 生成后立刻过契约体检（`--new` 会调 `audit()`），不过当场退出 1；
- **守卫：拒绝写进 skill 自己的 `styles/`**（style.py:107）—— 那里是用户显式托管的
  全局风格，工具链往里写 = 变相内置（用户明令禁止过，实测踩过两次）。

## spec 字段集（deck-spec.json）

```jsonc
{
  "deck": {
    "style":    "swiss-grid",         // 可选；缺省 swiss-grid。风格名（三根顺序查找）或路径
    "colorSet": "vivid",              // **必填具名**（v3：auto/mood 派生已退役）——
                                      // 写名 = 该风格 token.colorSets 的键；缺失或写
                                      // "auto" → validate_spec 判 MISSING_COLOR_SET，
                                      // render.resolve_color_set 再拦一道 SystemExit
    "seed":     11,                   // 建议显式写（缺省 1）；错位/颗粒按 (seed, 元素) 派生
    "title":    "封面文案",
    "brand":    "acme",               // 可选；品牌协议 —— 字体并入、色板同名键品牌赢
                                      // （compile.py:124）
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
                                      //   combo 八类，chart.py:92）；缺失 = MISSING_CHART_TYPE
        "intent":   "comparison",     // 仅 chart；可选**语义标注**（不决定图形）——
                                      //   trend / ranking / comparison / correlation /
                                      //   deviation / distribution / composition /
                                      //   progress，八值封闭，validate_spec 校验
        "message":  "结论一句话",      // 仅 chart；写了就当图表**大标题**（render.py:1118），
                                      // 原 title 降为数据集名
        "data":     [{label, value}, ...],    // 仅 chart（scatter 豁免 x/y）
        "series":   [{name, data}, ...],      // 仅 chart；多序列
        "emphasis": {"values": ["标签"]},     // 仅 chart；命中的用主色，其余灰化
        "annotations": [{type, target, text, value}, ...],  // 仅 chart
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

- **相对路径**（旧语义，全兼容）：spec 同目录没有 `assets/manifest.json` 时照旧用；
- **assetId**（语义引用）：放了 manifest 时，`image` 写清单里的 id。清单是**封闭
  schema v1**：`{"schemaVersion": 1, "assets": {id: {file, source, note}}}`
  （render.py:851-855），`file` 相对 `assets/` 目录。

解析只发生在 compile：assetId → `"assets/<file>"`（§14 优先级链 v1 —— **manifest 即
选择**），页对象携带最终路径，渲染器不见 assetId；每条解析写进 compile trace
（compile.py:180-193）。缺文件由 `check.py` 的「图片加载」门实测拦。
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
