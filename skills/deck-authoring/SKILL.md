---
name: deck-authoring
description: >-
  Build slide decks from a structural spec. Styles are authored per deck
  (styles/<名>/ 自建，无内置，无可拷模板).
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

把一份 `deck-spec.json` 渲成能直接拿去讲的 deck。**你只写内容，脚本算一切坐标、字号
与颜色**；风格自建无内置（放 **deck 项目**的 `styles/<名>/`，随项目交付，skill 目录永不
写入），加一套＝加一个目录，不改渲染器。

## 确认门：四样大事，用户点头才动

> 硬规矩：**给可比较的选项 → 停下等选择 → 才继续**。用户没选，就停在那。

1. **内容大纲 + 每页视觉载体**：页序 + 每页一个观点 + **这页靠什么立住**（图/结构图/
   图表/纯文字），三样一起过目才写 spec；不写下来等于没决定（见 `references/planning.md`）。
2. **风格方向**：三版真出图并排（见下），停下等选择；选完记进 spec。
3. **配色**：从所选风格的 `colorSets` 挑一套具名色板（**spec 必须写名字**），
   三版小样给用户选；品牌色优先。
4. **布局+配图合同**：批量出交付物前，关键页预览过目（布局轮换可见）；
   `--brief` 的**每个图位提示词一并交给用户**（那是他要拿去出图的东西）。

### 三方向：真出图，但不落盘

**不要把风格列表丢给对方当选择题**——他没见过画面，选不了。做三版真出图：

```bash
# 三方向 = 临时目录里的草稿（按 style-architecture.md 现写，渲完即弃；绝不写进 styles/）。
for s in a b c; do mkdir -p /tmp/dir-$s && $EDITOR /tmp/dir-$s/style.json /tmp/dir-$s/skin.css
  python3 scripts/render.py spec.json --style $s -o $s.html && python3 scripts/shots.py $s.html --out-dir shots-$s --count 2; done
```

**方向从这份 deck 推（观众/场合/材料气质），不从风格史挑、不复用见过的风格名**——
任何清单都会被当成选项清单，所以只设四轴取点（骨架/字感/密度/色彩）：任意两方向至少
两轴不同且必含骨架轴。每版标**风格名 + 一句为什么配它 + 适合什么场合**，停下等选。

### 风格：自建，无内置

**风格是每份 deck 的表达层，工具链零内置**：**deck 项目**的 `styles/<名>/` 放 `style.json + skin.css`（形状与逐键说明见
`references/style-architecture.md`；字栈参考 `fonts/mapping.json`）。**没有可拷的参考实现，也不携带示例资产**
（能拷就会拷，拷出来每份 deck 一样）；按契约现写。对比度门禁归 `ink.py`，产物实测门归 `check.py`。
每个风格可带多个 `colorSet`；**spec 的 `colorSet` 必填具名**（写 auto/mood 一律被拦 ——
选色是审美决策，脚本只验对比度）。换风格/换色板只改 spec 两个字段，内容一字不动。

## 为什么不能让你写坐标或色值

字号、折行、错位量、对比度 —— 都是几何 / 颜色计算，模型直接吐数字必翻车
（原型实测：主/副色当文字色对比度只有 2.35 / 2.68 ✗）。所以：

- 规格 schema **没有**色值/字号/坐标字段（不存在，不是"不推荐填"）：手写会被 `validate_spec.py` 判失败 —— 静默最坏，模型以为写进去了、图却没变。
- 文字色**只能**是 overprint（两墨叠印）；`check.py` 第 ① 条会拦主/副色当文字色。

## 起手流程

1. **先读契约**：`references/style-architecture.md` 的 spec 逐键说明与示例（写完跑 `validate_spec.py`）。
2. **写 spec**（前置：大纲已过确认门 ①）：每页只有 `type` + 内容，见
   `references/style-architecture.md`；**写什么内容**见 `references/content-intelligence.md`
   （一页一个观点 / 容量估算 / 观众距离）。拿不准就先渲出来跑 `check.py`。
   `seed` 显式写（默认 1）：错位与颗粒按 (seed, 元素) 派生，否则没法回归。
   **deck 项目 = spec 所在目录**：风格 / 素材 / 提示词合同都随它走，别建在 `/tmp`。
   有品牌资产加一行 `deck.brand`（见 brand-assets.md：**品牌赢在“是谁”，风格赢在“怎么表达”**；
   品牌由用户提供 —— 仓库里没有示例品牌，示例资产会被直接当成可用资产用进交付）。
3. **五道门**（顺序有意义：先验输入，再渲，再量，最后判；九站总图见 `references/pipeline.md`）：
   - 规格：`python3 scripts/validate_spec.py your.spec.json`（字段集封闭，未知键直接失败）
   - 墨色：`ink.py styles/<你的风格>/style.json`（deck 项目里跑；任一色板不达标退 1）
   - 渲染：`python3 scripts/render.py your.spec.json -o out.html`（中间产物就加 `--resolved resolved.deck.json --trace`）
   - 实测+判定：`python3 scripts/check.py your.spec.json out.html`（真浏览器量完再判，全过退 0；
     只想单独量就 `measure.py out.html`）
4. **交付**（**HTML 不能漏** —— 它是唯一带演示态的形态、自包含单文件，也是其余格式的源头）：
   - HTML：直接把 `out.html` 给人（`?present` 一页一屏、`←/→` 翻页、`S` 讲稿层、`F` 全屏）
   - PDF：`python3 scripts/pdf.py out.html -o deck.pdf`（矢量、能打印；脚本会验页数与页尺寸）
   - PNG 截图：`python3 scripts/shots.py out.html --out-dir pages/ --count N`
   - PPTX：观感 100% 用 `pptx_native.py --png-dir pages/ -o deck.pptx`；**对方要改字**用 `pptx_native.py out.html -o deck.pptx`（原生 shapes，字是真字）
   - 视频：`python3 scripts/animate.py out.html -o deck.mp4`（GIF：`-o deck.gif --width 960`，无需 ffmpeg；何时别用见 `references/animation.md`）。
5. **素材**：逐页决定这页靠什么立住，写进 spec 的 `visual` 四档 —— 纯文字 `{"kind":"none"}`
   （不必配图，但必须**决定过**）｜图表 `{"kind":"data"}`（chart 版式）｜结构图/流程图/拓扑/
   架构 `{"kind":"diagram"}`（**excalidraw.com** 或 **draw.io** 画好导出 PNG 放进 deck 项目）｜
   **图不由脚本手画**（SVG / PIL / 画布都不行 —— 图里出现卡片、分栏、页标题，那它本来就该是一页 spec）｜
   两者的 `ratio` **必填**（如 `"3:2"` / `"1:1"`）—— 比例写下来才算定，槽位按它定高｜
   照片/插画/主视觉 `{"kind":"evidence_image"}`（`--brief` 出**提示词** → 你出图 → 放回目录 →
   `--check`）。`image` 只填文件名；**不用 SVG 手搓插图与流程图**（一眼假）—— SVG 只做风格的
   装饰与几何。真实素材优先，细节见 `references/images.md`。

## 版式

`type` 字段支持：

| type | 用途 | 布局（`layout`，不写=缺省） |
| --- | --- | --- |
| `title` | 封面 | —（副标题一行内） |
| `content-text` | 全文页 | —（条目太多给提示，档位作者声明） |
| `content-image` | 图文页 | 结构布局：`visual-right` 缺省 / `visual-left` 图先文后 / `even` 6+6 / `hero` 图为主角满幅+标题条 |
| `two-column` | 双栏 | 结构布局：`even` 缺省 / `lean-left` 左栏宽 / `lean-right` 右栏宽 |
| `timeline` | 时间线 | —（节点标签走数字档） |
| `chart` | 图表 | 图形由 **`chart` 字段显式声明**（八类：bar/bar-horizontal/line/area/bar-stacked/donut/scatter/combo；HTML 路径由 **AntV G2** 画 —— vendor 锁版本内联、动画关死）；`intent` 是可选语义标注、不参与渲染 |
| `end` | 收尾 | —（居中大字） |

逐页可选写 `notes`（讲稿）：**给人读的文本，不参与排版**（不发元素、不进清单），
随产物走一份 JSON 载荷，现成时按 `S` 弹出 —— 它是给你自己看的，投屏时别开。

**结构布局 = 渲染器能力（像图表的八类图形），名字由你定**：写一个表外的
`layout`（如 `poster-split`）就套缺省结构 + `data-layout="poster-split"`，
怎么排由 `skin.css` 写（`[data-layout=...] .main{...}`）—— 脚本不枚举审美。
风格可声明 `layouts: [...]` 自封闭词表，`check.py` 按表验拼写。
**同型页连排换布局换节奏**（右图页接左图页、纯文页后配 hero）——每页同构图是
反 slop 第一条。
**字号档也由你声明**（无按条数自动升降）：`titleTier`/`bulletTier` 逐页覆写，
风格可写 `titleTiers`/`bulletDefault` 定缺省；内容多就拆页/收短，不靠悄悄缩字。

「放不放装饰」是**风格**的属性（`decor.types`），不是版式的。

版面判断全靠实测（`measure.py` 真浏览器量真盒子）；文字宽不估算（汉字折行误差 2 倍多）。

## 动画：同一段画代码，三种时钟

演示态的入场和录进 MP4 的帧由**同一个纯函数** `paint(si,t)` 画，「讲出来的」和
「录出来的」不会跑偏。运动参数在**风格**里（`motion`，每套一个性格；性格 → 参数的
推导见 animation.md）。

两条硬约束：

- **渲染路径上不许有 CSS `transition`**：走墙钟，逐帧 seek 不可复现（测试盯着；壳除外）。
- **位移用 `translate`/`scale` 独立属性**：skin 用 `transform`，两边都写会动画期互相覆盖。

导出前抽帧看：`animate.py out.html -o x.mp4 --stills 0,1.5,22.4,32.3`。

## Do NOT

- **不要用动画掩盖内容问题**：它只解决「怎么上台」，装太多仍是装太多；`animate.py` 也不做转场/配乐/多镜头。
- **不要在内容元素上加 CSS `transition`**：见「动画」节 —— 帧不可复现。
- **不要在贴图版 PPTX 里改字**：那种每页是一张贴图，改不了字；要改字回改 spec 再重出。
  要「能改字的 pptx」走 `pptx_native.py`（原生 shapes，字是真字）——代价是错位、
  颗粒、网点做不出来。两种 pptx 都有，**别拿一种的局限当成整个 skill 的局限**。
- **不要调阈值放宽对比度门禁**：4.5 / 3.0 是无障碍底线；不达标就该换色板。
  `style.json` 里 `ink.rule` 已经写了"每套色板必须含一个深墨" —— 两墨都亮就压不深。
- **不要把品牌色/字体写进 spec**：`deck` 里只有 `brand` 一个入口；要改品牌去改
  `brands/<name>/brand.json`。logo 放哪个角也**不归品牌管**（那是构图，归风格）。
- **不要在 spec 里写 `color: <hex>`**：`color` 只接受 `"overprint"`（主/副色载不住正文）。
- **不要把生图模型的彩照直接塞进 image 字段**：先走 `image_source.py`（`--brief`）。
- **不要绕过 ink.py 手写叠印色**：颜色 = `overprint(primary, secondary)`；写死的
  `#xxxxxx` 在改色板时会“看起来没变”（实际已变），调试半天找不出原因。

## 出错时去哪查

- **字段不存在** → 刻意不留的三类（坐标/字号/色值）：版式用 `type`+`layout` 表达，
  换色板改 style.json；别把字段删了就交差。
- **对比度不达标** → `ink.py styles/<你的风格>/style.json` 查色板；换色板别动阈值。
- **`... 越出版面：下缘 ... 越出该页下边界 ...`** → 内容真的撑出这页了（实测）。
  `measure.py` 点名越界元素；或 `render --repair`（修复梯）/`--candidates`（页级 3+1 候选）。
- **不知道该用哪种版式** → `render --candidates` 出对比页（同内容不同结构 + 选择面板），
  在页面上挑，点「复制选择」得 picks JSON，再 `--picks picks.json` 回写。
- **`... 越出版面：右缘 ...`**（多半在标题）→ 标题是 `nowrap` 的，不折行、直接裁；改短。
- **`图片没加载`** → 相对路径挪目录就裂图；同目录交付或 base64（见 images.md）。
- **字体回退提示** → 声明的族本机没有，后面栈顶上；不阻塞，交付前确认。
- **错位值越界** → spec 不能硬塞 `--dx/--dy/--rot`，只能脚本派生。
- **装饰压文字** → validation.md 第 ⑤ 条；墨块只落右侧两角。
- **图表那页是空的 / `check.py` 报 G2 渲染失败** → `measure.py out.html` 看该页 `chartReady`
  是 `pending` 还是 `error`；再查数据 `label` 非空、`value` 是数字（几何由 G2 算，不再量柱高）。
