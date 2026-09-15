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
  "ink": {
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
  "misregistration": {
    "offsetRangeX": [lo, hi],             // 标题层 A 的 X 错位像素区间
    "offsetRangeY": [lo, hi],             // 标题层 A 的 Y 错位像素区间
    "rotationRange": [lo, hi],            // 整组旋转角度区间（度）
    "blendMode": "multiply"               // A / B 两层都用 multiply
  },
  "texture": {
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

## 多风格 seam（如何加新风格）

有两类"加风格"：

### A. 加一套 riso 色板（同风格、新色板）

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

**加一种风格 = 拷一份目录改内容，不碰任何 .py。** 已经这样加了 `keynote-dark`
与 `swiss-grid` 两套，除了给 token 添了一个可选字段（`colorSets.*.text`，见下）以外，
渲染/校验/导出的代码一行未改。

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

- **`colorSets.*.text`**：显式文字色。孔版的文字色是**派生**的
  （`overprint(primary, secondary)`，两墨相乘就是真实叠印的数学）；
  黑底白字/白底黑字这类风格的文字色是**声明**的 —— 拿它们的 primary×secondary
  去推会得到一个根本不适合当文字的色。两者走同一个入口 `ink.text_color()`，
  所以对比度门槛仍然只有一条。
- **`decor.kind`**：放什么装饰（`halftone-circle` / `null`）。
  连带 `decor.types`（哪些版式放）与 `decor.zones`（放哪个角）都是**风格自报的**，
  不是写死在渲染器里的。

#### 换风格需要重审什么

`check.py` 的门槛**全部从所选风格的 token 读**，不用改代码；但要确认新 token 里
这几项填得合理：`type` 的级数（字号是否匹配观看距离）、`misregistration` 区间
（不做错位的风格写 `[0,0]`，字段别删 —— ③ 那条区间校验靠它）、`contrast` 门槛。

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
