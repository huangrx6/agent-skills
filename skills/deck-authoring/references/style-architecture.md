# 样式架构

`styles/<style>/style.json` 是**单一来源** —— 渲染器、skin.css、墨色门禁都从这一处读。
改色板 / 改字号 / 改错位量，**全在 token 里改**，spec 与脚本零改动。

## 字段集（schema）

```jsonc
{
  "version": 1,                          // schema 版本号；改了字段就 +1
  "colorSets": {
    "<name>": {                          // 色板集；spec 用 colorSet 字段引用名
      "primary":   "#RRGGBB",            // 主专色 —— 只做墨层 / 色块 / 装饰
      "secondary": "#RRGGBB",            // 副专色 —— 只做墨层 / 栏标 / 装饰
      "background": "#RRGGBB"            // 纸色
      // 文字色 = overprint(primary, secondary)，**派生**，不手写
    }
  },
  // ── 以下四键是**可选 effect**（缺 = 该风格没有这个效果，不是"声明一堆零"）：
  //    ink / texture / decor / misregistration。普通风格（Swiss/Minimal/Glass…）
  //    照 dev-tools/style-fixture/minimal-baseline 起手即可，一个都不用写。
  "ink": {                                 // （可选）孔版/印刷系的叠印声明
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
    "display": "Songti SC, Georgia, serif", // 标题字体栈
    "mono":    "SF Mono, Menlo, monospace"  // 正文 / 注释字体栈
  },
  "viewerBackground": "#141414"          // 浏览器外底色（让纸色边能看见）
}
```

### 字体栈：写**意图**，回退了会告诉你

这两个值是完整的 CSS 字体栈，按意图从先到后写 —— **不是**“本机装了哪个”。

本机实测（macOS）：

| 栈 | 首选 | 实际 |
| --- | --- | --- |
| `display` | `Songti SC` ✓ 可用 | 就是它 |
| `mono` | `SF Mono` ✗ 本机没有 | 回退到 `Menlo` ✓ |

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
把八套拼成一张图，再回来看哪个适合场合。

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

有两类"加风格"：

### A. 加一套色板（同风格、新色板）

`colorSets` 里再加一个键。`ink.py` 会自动把它纳入三套色板门禁。
**唯一约束**：`rule` —— 文字色对比度必须达到 `contrast.minBody`（派生或声明都一样）。
两墨都亮时压不深（比如朱红 × 土黄只有 3.74 ✗），
至少其中一个要走深色（朱红 × 深棕 → 达标 ✓）。

`render.py` / `check.py` 不需要改 —— 它们从 token 注入一切。

### B. 加一种新视觉风格

> 之前这一节写的是「要走一个比这更大的改造，代价 ≈ 0.5~1 个工作日」。那个 seam 现在
> **已经建好了，而且不是靠分支实现的** —— 下面是实际做法。

一个风格 = `styles/<name>/` 一个目录，里面两件东西：

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

  ⚠️ **现状：八套风格全部走声明**。派生那条路只剩下 `ink.overprint()` 与它的
  单元测试 —— **没有任何一套在用**，所以它是一条"数学被钉住、但集成路径没被验证"
  的缝。要启用它（做一套真正的孔版风格）请把新风格渲出来量一遍对比度，
  别因为测试是绿的就当它已经在生产里跑过。
- **`decor.kind`**：放什么装饰（`halftone-circle` / `null`）。
  连带 `decor.types`（哪些版式放）与 `decor.zones`（放哪个角）都是**风格自报的**，
  不是写死在渲染器里的。

#### 换风格需要重审什么

`check.py` 的门槛**全部从所选风格的 token 读**，不用改代码；但要确认新 token 里
这几项填得合理：`type` 的级数（字号是否匹配观看距离）、`contrast` 门槛、
`misregistration`（要做错位才写区间 —— ③ 那条区间校验只在**写了**时生效；
不做错位的风格直接不写这个键）。

## spec 字段集（deck-spec.json）

```jsonc
{
  "deck": {
    "style":    "swiss-grid",         // 可选；缺省 swiss-grid。styles/ 下的目录名
    "colorSet": "vivid",              // 必须存在于该风格 token.colorSets
    "seed":     11,                   // 建议显式写（缺省 1）；错位/颗粒按 (seed, 元素) 派生
    "title":    "封面文案",
    "slides": [
      {
        "type": "title" | "content-text" | "content-image"
             | "two-column" | "timeline" | "chart" | "end",
        "title":    "...",            // title / content-* / timeline / chart / end 都有
        "subtitle": "...",            // 仅 title 页
        "bullets":  ["..."],          // content-text / content-image
        "image":    "pic.png",        // 仅 content-image；先经 image_source.py
        "columns":  [{title, bullets}, ...],  // 仅 two-column；至多两栏
        "nodes":    [{label, note}, ...],     // 仅 timeline
        "data":     [{label, value}, ...],    // 仅 chart
        "unit":     "%",              // 仅 chart；数值单位
        "caption":  "...",            // 仅 chart
        "color":    "overprint"       // 可选；只允许 "overprint"（不写也行）
      }
    ]
  }
}
```

**字段集是封闭的**：`validate_spec.py` 会把未知键直接判失败，并按类别给专门说明
（坐标 / 字号 / 色值三类各有自己的话）。所以 `fontSize` / `x` / `y` 这类写法一开始
就被挡下来 —— 不用等到产物那里才发现"它根本没生效"。

`check.py` **不管**字段集（它验的是产物）；它唯一会主动拦的字段是 `color`：第 ① 条
只接受 `"overprint"`，写成色值（如 `"#FF0000"`）会判失败。

## seed 的不可替代性

`(seed, 元素)` 派生 = 同一份 spec 重渲两次**逐字节一致**。
全局 random 拿掉 seed 也"看起来差不多"，但：

- 不能回归对比（昨天出的 vs 今天出的）
- 不能复现一版给别人（"我看到的"和"你看到的"差几个像素）

`render.py` 用的派生 key 是 `"|".join([str(seed)] + [str(p) for p in parts])`，
所以同一页里不同元素、不同页、不同时间段都互不相关 —— 不会出现
"整页统一向右偏移 1px"那种肉眼能看出来的相关性。

不要换成 `random.seed(seed); random.uniform(...)` —— 那会破坏可复现性。
