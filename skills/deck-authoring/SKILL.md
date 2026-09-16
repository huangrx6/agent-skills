---
name: deck-authoring
description: >-
  Build slide decks from a structural spec. Styles are authored per deck
  (styles/<名>/ 自建，无内置；dev-tools/style-fixture/swiss-grid 为参考实现).
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
字号与颜色**；风格自建无内置（`styles/` 是**用户自己的目录，skill 不主动写入**，
参考实现在 `dev-tools/style-fixture/`），加新风格＝加一个目录，不改渲染器。

## 确认门：四样大事，用户点头才动

> 硬规矩：**给可比较的选项 → 停下等选择 → 才继续**。用户没选，就停在那。

1. **内容大纲**：页序 + 每页一个观点，先过目；点头才写 spec（见 `references/planning.md`）。
2. **风格方向**：三版真出图并排（见下），停下等选择；选完记进 spec。
3. **配色**：从所选风格的 `colorSets` 挑（或 auto/mood），三版小样给用户选；品牌色优先。
4. **布局预览**：批量出交付物前，封面 + 1~2 页关键页过目，点头才出全套。

### 三方向：真出图，但不落盘

**不要把风格列表丢给对方当选择题**——他没见过画面，选不了。做三版真出图：

```bash
# 三个方向 = **临时目录**里的三套草稿（拷 dev-tools/style-fixture 改，渲完即弃）。
# 绝不写进 styles/（落盘=变相内置）；styles/ 只放用户明确要保存的东西。
for s in a b c; do cp -r dev-tools/style-fixture/swiss-grid /tmp/dir-$s   # 改完再渲
  python3 scripts/render.py spec.json --style $s -o $s.html && python3 scripts/shots.py $s.html --out-dir shots-$s --count 2; done
```

并排摆出来，每版标：**风格名 + 温度 + 一句话适合什么场合**；摆完**停下等选择**。

### 风格：自建，无内置

**内置八套已整体移除**（styles/ 删除，按用户决定）——风格是每份 deck 的表达层，
不该预置。自建：`styles/<名>/` 放 `style.json + skin.css`（形状与逐键说明见
`references/style-architecture.md`；字栈参考 `fonts/mapping.json`）。参考实现：
`dev-tools/style-fixture/swiss-grid`（demo/测试走它，可拷改）。`style.py` 列出
全部（用户 + 夹具）并逐套过契约；`style.py --sheet -o s.png` 拼对照图。
每个风格可带多个 `colorSet`；省略 colorSet 或写 auto = 按语义决策方向
（mood → 风格语法；seed 只管可复现，不做审美决策）。换风格/换色板只改 spec
两个字段，内容一字不动。

## 为什么不能让你写坐标或色值

字号、折行、错位量、对比度 —— 都是几何 / 颜色计算，模型直接吐数字必翻车
（原型实测：主/副色当文字色对比度只有 2.35 / 2.68 ✗）。所以：

- 规格 schema **没有**色值/字号/坐标字段（不存在，不是"不推荐填"）；手写会被
  `validate_spec.py` 直接判失败 —— 静默最坏：模型以为写进去了，图却没变。
- 文字色**只能**是 overprint（两墨叠印）；`check.py` 第 ① 条会拦主/副色当文字色。

## 起手流程

1. **先读 demo**：`dev-tools/demo.spec.json` —— spec 该写哪些键以它为准
   （逐键说明见 `references/style-architecture.md`；写完先跑 `validate_spec.py` 过字段集）。
2. **写 spec**（前置：大纲已过确认门 ①）：每页只有 `type` + 内容（标题 / 条目 / 时间点 / 数据），见
   `references/style-architecture.md`；**写什么内容**见 `references/content-intelligence.md`（内容智能 / 内容规划系统）
   （一页一个观点 / 容量估算 / 观众距离）。拿不准一页装不装得下就先跑 `fit.py`，别猜。
   `seed` 显式写（默认 1）：错位与颗粒按 (seed, 元素) 派生，不靠全局 random（否则没法回归）。
   公司有品牌资产（logo / 色号 / 字体 / 署名）就加一行 `deck.brand`，见
   `references/brand-assets.md` —— **品牌赢在"是谁"，风格赢在"怎么表达"**；demo 的 example/ACME 是演示品牌，抄模板记得删（check 会提醒）。
   字体与配色：字体清单/映射见 `references/fonts.md`（`fonts.py --fetch`）；色彩结构、novelty、三方向见 `references/color.md`（`palette.py --audit`）。
3. **五道门**（顺序有意义：先验输入，再渲，再量，最后判；九站总图见 `references/pipeline.md`）：
   - 规格：`python3 scripts/validate_spec.py your.spec.json`（字段集封闭，未知键直接失败）
   - 墨色：`python3 scripts/ink.py styles/<style>/style.json`（任一色板不达标退出 1）
   - 渲染：`python3 scripts/render.py your.spec.json -o out.html`
   - 实测+判定：`python3 scripts/check.py your.spec.json out.html`（真浏览器量完再判，全过退 0；
     只想单独量就 `measure.py out.html`）
4. **可选交付**：
   - 演示：直接把 `out.html` 给人（`out.html?present` 一页一屏、`←/→` 翻页、`F` 全屏）
   - PDF：`python3 scripts/pdf.py out.html -o deck.pdf`（矢量、能打印；脚本会验页数与页尺寸）
   - PNG 截图：`python3 scripts/shots.py out.html --out-dir pages/ --count N`
   - PPTX：观感 100% 用 `make_pptx.py --png-dir pages/`；**对方要改字**用
     `pptx_native.py out.html`（原生 shapes，字是真字）
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

「放不放装饰」是**风格**的属性（`decor.types`），不是版式的 —— 写死的对照表只会
对出错的前提。

版面判断**全部靠实测**（`measure.py` 开真浏览器量真盒子）：越出**该页**边界、或
被自己会裁的容器切掉，都报。文字宽不再估算 —— 估算对同一行汉字会差 2 倍多，
而且偏差随字体/字距/折行变，永远修不准。

## 动画：同一段画代码，三种时钟

演示态的入场和录进 MP4 的帧由**同一个纯函数** `paint(si,t)` 画，「讲出来的」和
「录出来的」不会跑偏。运动参数在**风格**里（`motion`，每套一个性格；夹具 swiss-grid
= 短而齐；历史参数表见 animation.md）。

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
- **不要在内容元素上加 CSS `transition`**：见「动画」节 —— 帧不可复现。
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
- **`... 越出版面：下缘 ... 越出该页下边界 ...`** → 内容真的撑出这页了（实测）。跑
  `fit.py --slide N` 看哪种版式装得下，再收字 / 拆页。
- **`... 越出版面：右缘 ...`**（多半在标题）→ 标题是 `nowrap` 的，不折行、直接裁；改短。
- **`图片没加载`** → 相对路径的产物挪个目录就全员裂图；同目录交付，或 base64 内嵌
  （图从哪来 / 怎么出 / 怎么验见 `references/images.md`）。
- **字体回退提示** → 声明的族本机没有，后面栈顶上；不阻塞，交付前确认。
- **错位值越界** → spec 不能硬塞 `--dx/--dy/--rot`，只能脚本派生。
- **装饰压文字** → validation.md 第 ⑤ 条；墨块只落右侧两角。
- **图表柱高不成比例** → 数据 `value` 是不是数字、是不是都被图渲染了；
  `references/validation.md` 第 ⑤ 条里"两两比例"那段解释了为什么不按峰值归一。
