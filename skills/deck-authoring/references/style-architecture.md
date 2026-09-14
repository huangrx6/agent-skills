# 样式架构

`styles/risograph/style.json` 是**单一来源** —— 渲染器、CSS、墨色门禁都从这一处读。
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

## 多风格 seam（如何加新风格）

有两类"加风格"：

### A. 加一套 riso 色板（同风格、新色板）

`colorSets` 里再加一个键。`ink.py` 会自动把它纳入三套色板门禁。
**唯一约束**：`rule` —— 叠印墨对比度必须达到 `contrast.minBody`。
两墨都亮时压不深（比如朱红 × 土黄只有 3.74 ✗），
至少其中一个要走深色（朱红 × 深棕 → 达标 ✓）。

`render.py` / `check.py` 不需要改 —— 它们从 token 注入一切。

### B. 加一种新视觉风格（比如 watercolor / screenprint / letterpress）

那要走一个比这更大的改造：

1. `styles/` 下加一个目录（如 `styles/watercolor/`），自带一套 `style.json`。
2. `render.py` 的 `TOKENS` 默认值改成可注入；spec 增 `style` 字段。
3. `render.py` 的 CSS 块按风格切换（或拆出多个 HEAD 模板）—— **这是 seam**：
   token 里**只有视觉参数**，HTML 结构与 DOM 不变；
   CSS 才允许按风格分支。
4. `check.py` 内的字号限制、错位区间、装饰 zone 都需要按风格重审。
5. 新风格的视觉检查项（watercolor 没套色错位、letterpress 不需要网点）需要新校验。

这条 seam 的代价 ≈ 0.5 ~ 1 个工作日。**不要为了"统一性"硬合并**两种风格
—— 它们的"硬规矩"不重叠，并存比合并清爽。

## spec 字段集（deck-spec.json）

```jsonc
{
  "deck": {
    "colorSet": "vivid",              // 必须存在于 token.colorSets
    "seed":     11,                   // 必填；错位 / 颗粒按 (seed, 元素) 派生
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

`check.py` 不认识 `type` 之外的字段；写错（比如手塞 `color: "#FF0000"`）会被判失败。

## seed 的不可替代性

`(seed, 元素)` 派生 = 同一份 spec 重渲两次**逐字节一致**。
全局 random 拿掉 seed 也"看起来差不多"，但：

- 不能回归对比（昨天出的 vs 今天出的）
- 不能复现一版给别人（"我看到的"和"你看到的"差几个像素）

`render.py` 用的派生 key 是 `"|".join([str(seed)] + [str(p) for p in parts])`，
所以同一页里不同元素、不同页、不同时间段都互不相关 —— 不会出现
"整页统一向右偏移 1px"那种肉眼能看出来的相关性。

不要换成 `random.seed(seed); random.uniform(...)` —— 那会破坏可复现性。