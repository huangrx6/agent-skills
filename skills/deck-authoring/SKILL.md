---
name: deck-authoring
description: >-
  Build slide decks from a structural spec, in one of four real visual styles
  (黑底剧场 keynote-dark / 瑞士栅格 swiss-grid / 大字报 billboard / 笔记本 notebook).
  Pipeline: deck-spec.json → HTML (可演讲) → 矢量 PDF / 可编辑 PPTX / 每页 PNG / MP4·GIF 动画.
  Brand assets are a third layer (brands/<name>/: logo 含反白版 / 色号 / 字体 / 署名) — 报出
  公司名就能套上，deck.brand 一个字段.
  Use when the user asks 做一份 deck / 做幻灯片 / 做个 PPT / 把这份内容做成演示 —— 包括有明确
  风格要求时（"做成苹果发布会那样"），也要先出多个风格方向让他选。The model writes only
  the spec content (titles, bullets, style, colorSet, seed); scripts compute every
  coordinate, font size, and contrast check. Do NOT use for editable-PowerPoint-only
  jobs, for chart-only deliverables, for one-off slide images with no deck structure,
  or for multi-shot motion-design films (本 skill 只做「逐页走片」的视频).
---

# Deck authoring

把一份 `deck-spec.json` 渲成能直接拿去讲的 deck。**你只写内容，脚本算一切坐标、
字号与颜色**；风格从 `styles/` 选（黑底剧场 / 瑞士栅格 / 大字报 / 笔记本），加新风格＝加一个
目录，不改渲染器。

## 风格选择：先出三个方向，让人选

> 这是硬门。**即使对方已经说了风格，也照走**——风格词收窄的是解释空间，不转移选择权
> （"要苹果发布会那种"可以是黑底巨字、也可以是大白底衬线，选哪个是他的事）。

**不要把风格列表丢给对方当选择题。** 他没见过画面，选不了。做三版**真出图**给他看：

```bash
# 同一份内容，三个风格各渲一遍（只改 deck.style + deck.colorSet）
for s in keynote-dark swiss-grid billboard notebook; do
  python3 scripts/render.py spec.json --style $s -o $s.html
  python3 scripts/shots.py $s.html --out-dir shots-$s --count 2   # 封面 + 一页内容页
done
```

然后并排摆出来（拼图或直接发三张），每版标：**风格名 + 温度 + 一句话适合什么场合**。
摆完**停下等选择**，并把选择记进项目目录（后面所有页都按它出）。

### 现有八种风格

完整对照（温度 / 适合 / 不适合 / 构图锚点）在 `references/style-architecture.md`；
用 `python3 scripts/style.py` 看全部与它们的契约状态，`style.py --sheet -o s.png`
把**所有风格 × 同一份 demo** 拼成一张图 —— 选风格要的是画面，不是对照表。

一句话记住八个：**暗** `keynote-dark`（冷）/ `botanical-dark`（暖）；
**亮** `swiss-grid`（安静）/ `billboard`（大字报）；**纸** `notebook`（横格）/
`paper-ink`（编辑）；**另类** `terminal`（等宽）/ `pastel-geometry`（粉彩）。
每个风格支持几个 `colorSet`（`ink.py` 会列出并逐个过对比度门槛）。
**换风格/换色板只改 spec 的两个字段，内容一字不动**；改风格本身只动
`styles/<style>/style.json`，渲染器零改动。

## 为什么不能让你写坐标或色值

字号、折行、错位量、网点密度、对比度 —— 都是几何 / 颜色计算。让模型直接吐数字，
本质是让它做它不可靠的事，症状必然是"看起来差不多，但深色文字达不到正文对比度"
（原型实测：主 / 副色单独当文字色只有 2.35 / 2.68 ✗）。所以：

- 规格 schema 里**没有**色值字段、字号字段、坐标字段 —— 不存在，不是"不推荐填"。
  手写它们会被 `validate_spec.py` **直接判失败**（字段集封闭），不是静默忽略 ——
  静默最坏：模型以为写进去了，出的图却没变，于是跑去改别的地方。
- 文字色**只能**是 overprint（两墨叠印）；`check.py` 第 ① 条会拦"主 / 副色声明当文字色"。

## 起手流程

1. **先读 demo**：`dev-tools/demo.spec.json` —— spec 该写哪些键以它为准
   （逐键说明见 `references/style-architecture.md`；写完先跑 `validate_spec.py` 过字段集）。
2. **写 spec**：每页只有 `type` + 内容（标题 / 条目 / 时间点 / 数据），见
   `references/style-architecture.md`；**写什么内容**见 `references/content-design.md`
   （一页一个观点 / 容量估算 / 观众距离）。拿不准一页装不装得下就先跑 `fit.py`，别猜。
   `seed` 显式写（默认 1）：错位与颗粒按 (seed, 元素) 派生，不靠全局 random（否则没法回归）。
   公司有品牌资产（logo / 色号 / 字体 / 署名）就加一行 `deck.brand`，见
   `references/brand-assets.md` —— **品牌赢在"是谁"，风格赢在"怎么表达"**。
   字体与配色：字体清单/映射见 `references/fonts.md`（`fonts.py --fetch`）；色彩结构、novelty、三方向见 `references/color.md`（`palette.py --audit`）。
3. **五道门**（顺序有意义：先验输入，再渲，再量，最后判）：
   - 规格：`python3 scripts/validate_spec.py your.spec.json`（字段集封闭，未知键直接失败）
   - 墨色：`python3 scripts/ink.py styles/<style>/style.json`（任一色板不达标退出 1）
   - 渲染：`python3 scripts/render.py your.spec.json -o out.html`
   - 实测+判定：`python3 scripts/check.py your.spec.json out.html`（真浏览器量完再判，全过退 0；
     只想单独量就 `measure.py out.html`）
4. **可选交付**：
   - 演示：直接把 `out.html` 给人（`out.html?present` 一页一屏、`←/→` 翻页、`F` 全屏）
   - PDF：`python3 scripts/pdf.py out.html -o deck.pdf`（矢量、能打印；脚本会验页数与页尺寸）
   - PNG 截图：`python3 scripts/shots.py out.html --out-dir pages/ --count N`
   - PPTX（观感 100%）：`python3 scripts/make_pptx.py --png-dir pages/ -o deck.pptx`
   - PPTX（**对方要改字**）：`python3 scripts/pptx_native.py out.html -o deck-editable.pptx`
   - 视频：`python3 scripts/animate.py out.html -o deck.mp4`（GIF：`-o deck.gif --width 960`；
     无需 ffmpeg）。运动设计与什么时候别用见 `references/animation.md`。
5. **图页**：spec 里 `image` 只填**文件名**，用 `image_source.py --brief spec.json` 出**提示词
   契约**（人拿它出图、存产物同目录，再 `--check` 验）—— 分工与理由见 `references/images.md`。

## 版式

`type` 字段支持：

| type | 用途 | 风险点 |
| --- | --- | --- |
| `title` | 封面 | 副标题一行内 |
| `content-text` | 全文页 | 条目太多会撞出该页下缘（实测判） |
| `content-image` | 图文页（左文右图） | 图必须先过 `image_source.py`，不能直接塞彩照 |
| `two-column` | 双栏 | 每栏 660px，字号固定走小档（不参与条目数自适应） |
| `timeline` | 时间线 | 每格 300px；节点标签用数字档字号 |
| `chart` | 柱状图 | **柱与刻度不做质感**（风格只碰容器） |
| `end` | 收尾 | 居中大字 |

「装饰墨块」那一列已经删掉了：「放不放装饰」是**风格**的属性（`decor.types`），
不是版式的属性 —— 拿一张写死的表去对版式，只会对出一个错的前提（测试已改成验契约）。

版面判断**全部靠实测**（`measure.py` 开真浏览器量真盒子）：越出**该页**边界、或
被自己会裁的容器切掉，都报。文字宽不再估算 —— 估算对同一行汉字会差 2 倍多，
而且偏差随字体/字距/折行变，永远修不准。

## 动画：同一段画代码，三种时钟

演示态的入场和录进 MP4 的帧由**同一个纯函数** `paint(si,t)` 画 —— 「讲出来的」和
「录出来的」不会跑偏。运动参数在**风格**里（`style.json` 的 `motion`），四种风格故意
各不相同：keynote-dark 慢起长尾、swiss-grid 短而齐、billboard 拍上去、notebook 像翻册子。

两条硬约束：

- **渲染路径上不许有 CSS `transition`**：它走墙钟，逐帧 seek 下不可复现（不报错，画面
  只是慢慢偏掉）。测试有静态检查盯着；壳（页码/提示）除外，它不录进视频。
- **位移用 `translate`/`scale` 独立属性，不用 `transform`**：skin 自己会用 `transform`，
  两边都写会在动画期间互相覆盖（最难查的那类 bug）。

导出前抽帧看：`animate.py out.html -o x.mp4 --stills 0,1.5,22.4,32.3`（走同一条路径）。

## Do NOT

- **不要用动画掩盖内容问题**：它只解决「怎么上台」，解决不了「一页装太多」。先过五道门
  再谈动效；也别把 `motion` 调到眼花（停下来读的时间才是主体）。同样地，`animate.py`
  不做转场花样 / 配乐 / 多镜头 —— 要那些是另一条产线。
- **不要在内容元素上加 CSS `transition`**：见上面「动画」那节，会让录出来的帧不可复现。
- **不要在贴图版 PPTX 里改字**：那种每页是一张贴图，改不了字；要改字回改 spec 再重出。
  要「能改字的 pptx」走 `pptx_native.py`（原生 shapes，字是真字）——代价是错位、
  颗粒、网点做不出来。两种 pptx 都有，**别拿一种的局限当成整个 skill 的局限**。
- **不要调阈值放宽对比度门禁**：4.5 / 3.0 是无障碍底线；不达标就该换色板。
  `style.json` 里 `ink.rule` 已经写了"每套色板必须含一个深墨" —— 两墨都亮就压不深。
- **不要把品牌色/字体写进 spec**：`deck` 里只有 `brand` 一个入口；要改品牌去改
  `brands/<name>/brand.json`。logo 放哪个角也**不归品牌管**（那是构图，归风格）。
- **不要在 spec 里写 `color: <hex>`**：`color` 字段只接受 `"overprint"`；主 / 副色
  单独写 `color` 会被 `check.py` 第 ① 条判失败。
- **不要把生图模型的彩照直接塞进 image 字段**：必须先走 `image_source.py`，
  否则 check 不会有事，但视觉上立刻露馅（方案 §2 图文页那条）。
- **不要绕过 ink.py 去手写叠印色**：颜色 = `overprint(primary, secondary)`；写死的
  `#xxxxxx` 在改色板时会"看起来没变"（实际已变），调试半天找不出原因。

## 出错时去哪查

- **`validate_spec.py` 说某个字段不存在** → 那是刻意不留的三类（坐标 / 字号 / 色值）。
  按它给的专门说明改：版式用 `type` 表达，换风格/色板改 `styles/<style>/style.json`。
  **别把字段删了就交差** —— 先想清楚本来想表达什么。
- **对比度不达标** → `python3 scripts/ink.py styles/<style>/style.json` 看该风格的
  各套色板对比度；不达标的换色板，不要改 `contrast.minBody`。
- **`... 越出版面：下缘 ... 越出该页下边界 ...`** → 内容真的撑出这一页了（实测量的，
  不是估的）。先跑 `fit.py --from-spec … --slide N` 看哪种版式装得下，再收字 / 拆页。
- **`... 越出版面：右缘 ...`**（多半在标题）→ 标题是 `nowrap` 的，不折行、直接裁；改短。
- **`图片没加载`** → 相对路径的产物挪个目录就全员裂图；同目录交付，或 base64 内嵌
  （图从哪来 / 怎么出 / 怎么验见 `references/images.md`）。
- **字体回退提示** → 声明的族本机没有，栈里后面的族顶上了；不阻塞，交付前确认一下。
- **错位值越界** → spec 里不能硬塞 `--dx/--dy/--rot`；这些只能由脚本派生。
- **装饰压文字** → `references/validation.md` 第 ⑤ 条；墨块只落右侧两角。
- **图表柱高不成比例** → 数据 `value` 是不是数字、是不是都被图渲染了；
  `references/validation.md` 第 ⑤ 条里"两两比例"那段解释了为什么不按峰值归一。
