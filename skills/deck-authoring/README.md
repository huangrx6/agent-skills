# deck-authoring — 把结构化内容渲成能讲的 deck

把一份 `deck-spec.json` 渲成演示 deck，**风格从 `styles/` 选**（一种风格 = 一个目录），
交付 HTML（可演讲）/ 矢量 PDF / 可编辑 PPTX / 每页 PNG。

## 这是什么 / 不是什么

- 这是「**内容只管写，版面与颜色脚本算**」的 skill —— 字号、折行、对比度、
  条目密集页的字号自适应、四种风格的适配，全部由脚本管。
- 它**不是**单一风格的：`styles/` 下现在有 4 套（黑底剧场 / 瑞士栅格 / 大字报 /
  笔记本），加一套 = 拷一个目录改 token 与 CSS，不改任何 .py。
- 它**不是**只能出死图的：HTML 自带走演示态（键盘翻页 / 缩放 / 页码），
  而且能用 `pptx_native.py` 出**字能改**的 PPTX。
- 它**不是**通用图表工具 —— 数据图表只支持柱状图，且风格处理只作用于容器，
  柱与刻度保持干净（错位会毁掉可读性）。
- 它**不是**「换个 css 滤镜」—— duotone + 半调是「重新制版」，不是「加滤镜」。

## 跑法（最快路径）

```bash
cd skills/deck-authoring/
python3 scripts/validate_spec.py dev-tools/demo.spec.json           # 1) 规格（字段集封闭）
python3 scripts/ink.py styles/swiss-grid/style.json                # 2) 墨色门禁
python3 scripts/plate.py --sample -o sample-treated.png             # 3) 造演示图
python3 scripts/render.py dev-tools/demo.spec.json -o out.html      # 4) 出 HTML
python3 scripts/measure.py out.html                                 # 5) 实测（真浏览器）
python3 scripts/check.py dev-tools/demo.spec.json out.html          # 6) 校验
python3 scripts/pdf.py out.html -o deck.pdf                         # 7) 矢量 PDF
python3 scripts/shots.py out.html --out-dir pages/ --count 6        # 8) 截图（要 Chrome）
python3 scripts/make_pptx.py --png-dir pages/ -o deck.pptx          # 9) 出 PPTX（贴图，观感 100%）
python3 scripts/pptx_native.py out.html -o deck-editable.pptx       # 10) 出 PPTX（原生，能改字）
python3 scripts/animate.py out.html -o deck.mp4                     # 11) 出视频（另有 GIF）
python3 scripts/brand.py                                             # 12) 看有哪些品牌
```

第 11 步不需要 ffmpeg：取帧走 Chrome DevTools Protocol（一次启动截几百帧，比一帧一个
`chrome --screenshot` 快 51 倍），H.264 编码走 macOS 自带的 AVFoundation，GIF 走 Pillow。
抽几帧看看再编：`--stills 0,1.5,22.4,32.3`。运动设计与什么时候该用视频，见
`references/animation.md`。

设计期还有两件工具（不在流水线上）：

```bash
python3 scripts/style.py                       # 八套风格 + 契约状态
python3 scripts/style.py --sheet -o s.png      # 所有风格 × 同一份 demo → 一张图
python3 scripts/style.py --sheet -o m.png --spec dev-tools/stress.spec.json --pages 9,14
                                               # 矩阵：某份 deck 的第 9/14 页在**全部风格**下
python3 scripts/style.py swiss-grid            # 一套风格的摘要
```

`--sheet` 是「先出三个方向让人选」那个流程的实物依据 —— 选风格要的是**画面**，
不是对照表。风格本身怎么加见 `references/style-architecture.md`。

写内容时用的：

```bash
python3 scripts/fit.py --from-spec your.spec.json --slide 3   # 试排：这页哪种版式装得下
python3 scripts/fit.py --json '{"title":"结论","bullets":["…","…"]}'
```

它把候选版式与各条目数档位摆进同一份产物渲一次、量一次，报出**实测**的溢出量与
内容占位 —— 省掉"写完 → 报溢出 → 改了再跑"那几轮。内容怎么组织（一页一个观点、
版式选择、观众距离）见 `references/content-intelligence.md`（内容智能 / 内容规划系统）。

第 3 步是给 demo 的图文页造图：`demo.spec.json` 的 `image` 是个占位文件名，
不先生成它就是一张裂图。该产物**不入库**（见「已知限制」第 7 条）。

**要换成真照片**（推荐路径，三条路里最正经的一条）：

```bash
python3 scripts/image_source.py --brief dev-tools/demo.spec.json   # → 图片提示词契约
#   契约里逐张给了：文件名 / 实测尺寸 / 比例 / 透明通道 / 会被制版怎么处理 /
#   可粘贴的中英提示词 / 负面清单。拿去出图，按文件名存到产物同目录。
python3 scripts/image_source.py --check dev-tools/demo.spec.json   # 验尺寸与比例
```

分工是**脚本写契约 → 人出图 → 脚本验收**：脚本知道每张图进哪个槽位、那个槽位实测
多少像素、会被双色调+半调怎么处理；而"出一张好看的图"这件事，人拿自己顺手的模型
做得比脚本调一个陌生 API 好。`--brief` 会顺便放占位图，所以流水线不会因为等图停住。

提示词按**固定字段顺序**给，顺序就是优先级：

```text
主体 → 场景 → 构图 → 镜头 → 光线 → 色彩 → 风格 → 细节 → 文字 → 限制
```

先"画什么"、再"怎么画"、最后"绝对不能错"。**图片该要就要，别嫌麻烦少要，多了也没事**：`content-image` 版式**必须**给 `image`
（缺了渲染器会崩，`validate_spec.py` 拦）；全篇一张图都没有时 `check.py` 会开口并点名
最容易加图的那几页。什么时候该有图、什么时候版式本身已经承担了视觉功能，见
`references/content-intelligence.md`。

**一页的信息永远由版面用真文字排**：图只有两种角色 —— **配图**（占一栏）或**点缀**
（更小），背景那种大图也不承载信息。**一张图盖住整页是禁止的**（实测配图只占整页
17%，`check.py` 在 ≥60% 时拦）；提示词里也明写"不要把这一页的信息画进去"。
理由（可编辑 / 可搜索 / 可翻译 / 可被读屏器读，以及为什么贴图版 PPTX 不算违规）见
`references/content-intelligence.md`。

**「主体 / 场景 / 细节」留空给人填**
（写作 `〈…〉`）—— 工具只看得见 spec 里的文字，读不到你脑子里的画面，就不该替你编。
脚本填的是它真知道的部分：构图来自实测槽位与版式（图独立成栏、文字在旁边），
色彩来自该风格的色板，光线与风格来自气质档，限制来自制版管线。
尺寸 / 比例 / 数量**不写进提示词**（生图 API 有独立参数，写重了会打架），单列在
「参数」栏。字段分工、优先级裁决与踩过的坑见 `references/images.md`。

## 测试

```bash
python3 -m unittest discover -s tests/deck-authoring -v     # 456 条，约 6 分钟（负载敏感）（空闲时）
```

耗时说明：几乎全是**真浏览器**的开销，所以对机器负载很敏感 —— 空闲时约 2.5 分钟，
    同时在跑视频编码之类的大活时会涨到 5 分钟以上（实测 138s → 330s）。其中约 30 秒是
    **压测回归**（每套风格 × 真实形状的 deck 各开一次 Chrome）。改了风格或渲染层就跑全量；
    只改文档可以只跑相关的那个文件。

钉住二十项不变量：同 spec + 同种子字节一致（带随机区间的风格；确定性风格本就与 seed 无关）、
色板门禁 + 两墨乘叠印的数学、校验的变异验证（每项都造违规样例）、半调墨覆盖率随灰度单调、
缓存命中后仍过色板三角不变量、外壳行为（真开浏览器按键翻页 + letterbox 缩放比贴边不溢）、
PDF 是矢量且页数/页尺寸对、可编辑 PPTX 的**字是真字**且坐标是页内坐标、
字体提示不报废话、**每种风格的装饰落点与它声明的 `decor.types` 一致**、SKILL.md 的版式表与
`render.py` 实测行为一致、规格字段集真的封闭（坐标/字号/色值必须被指名报出）、
**同一个 t 两次独立浏览器会话取到的帧逐字节一致**（且不同 t 必须真的不同 —— 否则上一条
会假绿）、渲染路径上没混进 CSS `transition`、
**品牌资产**（优先级：品牌赢色板/字体/logo、风格赢版面；logo 内嵌且清单里给的是
技能相对路径；`cover+end` 指的是 end 版式那页而不是数组最后一页；logo 压文字会挡）、
**试排**（"装得下"与"半页空"是两个判据，混成一个就会把稀疏页判成装不下 —— 真踩过）、
**风格契约**（字号档 / 运动参数 / 色板门槛 / 装饰声明，逐项造违规样例验它有牙；
遍历的是**目录**不是写死的名单 —— 写死名单让四套新风格逃过检查过一次）、
**压测**（每套风格 × 真实形状的 deck 过 check：7 条密页 / 5+5 两栏 / 6 节点时间线 /
6 柱图表 / 带图注的图文页 / 18 字长标题 / 收尾页）、
**原生 PPTX 的三个交付级偏差**（`<a:ea>` 东亚字体 / 标题字重不写死 / 原生图表的
数值与网格线 —— 三条都只在"把 PPTX 转成图看"时才露出来）、
**交付演练工具**（逐像素差对"一样/不一样"都要给对答案；"只打印第 N 页"要真的只出一页
且页码保持原样 —— 后者错了会让对比图说谎，而差异只有 0.3% 不会报警）。

## 依赖

- Python ≥ 3.10（用了 `from __future__ import annotations` + importlib 动态加载同目录脚本）
- `Pillow`（duotone + 半调）
- `python-pptx`（PPTX 拼装）
- macOS 上 `shots.py` 需要 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- **导出视频不需要 ffmpeg / gifsicle / ImageMagick**：用系统已有的三件 —— Chrome（取帧）、
  `swiftc` + AVFoundation（H.264）、Pillow（GIF）。CDP 的传输走 `websockets`（装了就走快
  路径；没装会说清代价后降级，不静默变慢）。
- 不要装 Playwright —— `--headless=new --screenshot` 就够，多装一份纯属浪费

## 规划层（内容 → Storyline → 页规划 → spec）

渲染链之上是四层规划，**越靠近渲染 AI 自由度越低**：内容理解（中）→ Storyline（中）
→ Page Planner（低~中）→ Slide DSL（很低，封闭字段集）→ 渲染（0）。

```bash
python3 scripts/plan.py --archetypes       # 十个叙事骨架（问题→方案 / SCR / 复盘 / …）
python3 scripts/plan.py --page-types       # 页型 → 版式的确定性映射
python3 scripts/plan.py --check content.json storyline.json pageplan.json
python3 scripts/plan.py --to-spec pageplan.json content.json -o deck.spec.json
```

会失败的硬规矩：**缺 coreThesis**（一份 deck 必须有一句统领论断）、**brief 缺
desiredAction/desiredBelief**、**悬空引用**（message 的证据 / claim 的 derivedFrom
指向不存在的 fact）、**事实与推断不分**
（source_type 必须是 original/inferred/generated；高重要性结论只靠推断支撑会开口）、
**骨架乱序**（先讲方案再讲问题不是自由是错）、**配额漂移**（sections 页数之和 ≠
target_slide_count —— "15 页做成 28 页"就是这条漏的）、**复杂度爆表不拆页**
（字符/节点/图表/图/层级加权 ≥0.70 必须标 split）、**页没有 message**（不知道自己
在讲什么的页没法排版）。

`--to-spec` 产出的 spec **必须过 validate_spec**（有测试钉死）—— 规划层产出的东西
渲染器吃不下 = 全白写。分工、Schema 与还没做的部分（文档抽取、候选打分、架构图页型）
见 `references/planning.md`。

## 字体

内置 **126 款免费商用中文字体清单**（六类各 21 款）+ **字体 ↔ 风格映射表**。
仓库里只有清单与映射（纯文本）—— 字体文件 5–28MB 一款，**不进仓库**，也**不落在
skill 目录里**（skill 目录是可分发的代码，不该长出自下载的二进制）。字体进用户级缓存：

| 顺序 | 位置 | 什么时候用 |
| --- | --- | --- |
| 1 | `$DECK_FONT_DIR` | 显式指定，让调用方决定下载到哪 |
| 2 | `~/.config/deck-authoring/fonts/` | 默认、持久（单款 5–28MB，重下太浪费） |
| 3 | 临时目录（`--fetch --temp`） | 不想在这台机器上留东西 |

`fonts.py --where` 看当前目录。换台机器跑一次 `fonts.py --fetch` 就回来了。

```bash
python3 scripts/fonts.py --list --urls        # 126 款 + 来源页
python3 scripts/fonts.py --fetch --tier A     # 取 OFL/开源那批（直链已验证）
python3 scripts/fonts.py --map               # 8 套风格 × display/body/numeral 该配哪款
```

样式里直接写清单名就生效（渲染时自动注入 `@font-face`，**不靠把字体装进系统** ——
实测 macOS 字体缓存不刷新：装对了、名字也对，Chrome 仍然回退）：

```json
"fonts": { "display": "得意黑 Smiley Sans, sans-serif", "body": "霞鹜文楷, sans-serif" }
```

**"分享出去对方没字体"影响什么 —— 逐格式不同，都是实测的**：

| 交付格式 | 对方没装字体 | 依据 |
| --- | --- | --- |
| **PDF** | **没事** | Chrome 把用到的字形子集内嵌（`AAAAAA+SmileySans-Oblique` + `/FontFile2`）；另一款走 **Type3**（12 个 `/CharProcs`，字形是 PDF 内部绘图指令，同样自包含）。25MB 的霞鹜文楷出成 PDF 总共 113KB |
| PNG / 贴图 PPTX / MP4 / GIF | **没事** | 已栅格化 |
| **原生 PPTX** | **有事** ⚠️ | python-pptx 只写字体名（`<a:latin>` / `<a:ea>`），不嵌字体文件 —— 对方没装就由宿主替换 |
| HTML | **有事** | 用读者的字体；`--embed` 可把字体内联成单文件（CJK 太大会拒绝并建议走 PDF） |

**没有 license 就只走 A 档，连 `A/B` 也别碰** —— `A/B` 意味着某个来源标了 B
（署名 / 地区 / 禁商标 / **禁嵌入**），而把字体嵌进交付物属于再分发。
`--fetch` **默认就只取严格 A**（`--tier all` 才要 B/C），`--map --a-only` 给一套
**完整的**纯 A 替代方案（8 套风格 × 三档，所以不会变成"有几套风格不能用"）。
OFL 唯一要记住的：**再分发字体文件本身**时要带上版权声明与 License 文本；
只拿它排版、或把字形子集嵌进 PDF，不受影响。
四个实测踩过的坑（`.otf` 那份 Chrome 完全不嵌所以要优先 `.ttf`、`format()` 写错会**静默
不用这款字**、字族真名与清单中文名不是一回事、短记号子串匹配必然误报）见
`references/fonts.md`。

## 配色

**Style 存结构，不存 HEX**：`colorSets` 里是四个角色（primary / secondary /
background / text），`colorStructure` 里是结构（色相关系 / 颜色数量 / 明度 / 饱和度 /
冷暖 / 强调策略 / 创意等级…），其余九个角色由 `palette.py` **推导**。手写会漂，推导可测。

```bash
python3 scripts/palette.py --audit --topic "AI 大模型架构"   # 审配色 + 按主题判俗套
python3 scripts/palette.py --novelty swiss-grid blue        # 一个色板的 novelty 与**依据**
python3 scripts/palette.py --directions swiss-grid blue     # Safe / Creative / Experimental
python3 scripts/palette.py --roles swiss-grid blue          # 13 个角色的推导结果
```

用 **OKLCH** 而不是 HSL，因为 HSL 的 L 与感知明度不成正比（提亮之后对比度反而会掉，
而对比度在这里是硬门槛）。二次变体范围按规范：色相 ±10~30°、彩度 ±5~20%、明度 ±3~12%，
**中性色不旋色相**（C≈0 时旋了是空操作，实测会产出重复色）。

**俗套会被指出，而且说清是哪一条**（`tech_blue_purple_cyan` / `corporate_blue_white` /
`premium_black_gold`…）。实测**本仓库 8 套风格里 5 套的某个色板正落在名单上**
（历史内置期实测：`swiss-grid/blue` 同时命中前两条、`terminal/cyan`、
`billboard/electric` 等 5 套 —— 现按同一判据对自建风格提示）—— 所以它是**按主题条件的提示**而不是
阻塞（规范原文是"不得**自动**绑定"，不是"这个色不许用"）。

配色规范里**大部分讲的是生成过程**（怎么想），代码只能负责结构与校验。哪些是代码强制、
哪些是流程判断、哪些**还没实现**（渐变渲染、玻璃拟态、强调色占比实测），
逐条列在 `references/color.md`。

## 布局：网格与间距（`grid.py`，几何唯一来源）

版面几何只有这一个来源 —— 此前 `check.py` 手写的 `CONTENT=(…,838)` 与 `render.py`
推导的 824 差 14px，两个"唯一来源"已经漂了才发现。

```bash
python3 scripts/grid.py            # 12 列 / 列距 24 / 列宽 97.33 / 间距令牌 / 关系规则
python3 scripts/grid.py --json     # 机读（跨度、区域、令牌）
```

- **12 列网格**：图文页 7+5 列（825+24+583=1432 分毫不差），两栏 6+6，
  时间线宽度按节点数从网格算（原来写死 300px，6 节点超宽 538px）
- **间距令牌**：ramp 8/12/16/24/32/48/64/96 + 语义档 inner/item/group/section，
  注入产物为 `--sp-*`，壳里的 gap 全走令牌 —— **实测改前 10 个 gap 有 7 种值**
  （48/68/45/74/101/16/0），改后全部落在令牌上
- **关系规则**：组距 ≥ 1.5 × 条目距（Gestalt 接近性），`grid.py` 自检
- **对齐**：锚点（标题/栏题/图/图表）左缘必须吸附列 —— `check.py` 提示。
  改前左缘是 7 个任意值，改后全部落在列上（84/448/812/933/1176 = 边距+第4/7/8/10列）
- **阶梯**：4 套风格曾有 subtitle == bullet（同级碰撞 = 没有层级），已修；
  `style.py --check` 把同级碰撞与倒挂判错

## 布局与信息层级

**我们的布局不是模板系统，也不是约束系统** —— 是**固定画布 + 7 种手写版式 + 真浏览器
实测校验 + 试排**。画布 1600×900、`PAD 84/132`、正文带 132→824 是几何常量的唯一来源。

**规范里最核心的那条原则（"不要让 LLM 决定 x=327，程序负责精确布局"）从第一版就是
那样做的**：spec 里根本没有 x/y —— `validate_spec.py` 把 `x`/`y`/`dx`/`dy`/`rot`/
`width`/`height` 直接判错。所以那是**加法**，不是重构。

新加的 `hierarchy.py` 只做三件事，**全是提示级**（阈值取决于语境：封面就该空、
看板就该满）：

- **文本预算** —— 封面标题 ≤12 字、内页标题 ≤24、单条 ≤60…；超了不是只说"超了"，
  而是把**修复顺序**写进报错：删字 → 拆信息 → 换版式 → 拆页 → **最后才允许缩字号**
  （规范第 22 条。本仓库的 `bullet_tier()` 是"缩字号第一"，这条提示是为了在它之前
  把话说完）
- **视觉焦点** —— 给每个元素算视觉权重（文字用**墨迹宽** `textW` × 高度，不是整栏宽
  —— 实测标题的 `w` 是 1432px 而墨迹只占一小块），要求第一名领先第二名 ≥25%，
  且达首名 60% 权重的元素不超过 3 个（规范第 8 条）。实测我们的版式稳定领先 **90%+**
- **内容密度** —— 占正文带的百分比，按 Minimal 35~50% / Normal 45~65% /
  Information 55~75% / Dashboard 65~82% 分档

**硬约束与软约束是分开的**（规范第 21 条）：越界 / 重叠 / 文字溢出 / 图被放大 →
`check.py` **阻塞**；焦点 / 密度 / 预算 / 对齐 / 平衡 → **提示**。混淆的后果是第一份
正常的 deck 就被挡住，然后所有人开始忽略检查。

五块（布局 / 层级 / 留白 / 图形 / 图表）的现状、该借谁的规则（Fluent 2、Figma Auto
Layout、Design Tokens、**IBCS + ISO 24896**、AntV）、缺什么、以及**分四步的路线图**
（哪步是加法、哪步要动 8 套 skin、风险在哪）见 `references/layout-system.md`。

## 已知限制

1. **贴图版 PPTX 改不了字**：要能改字就走 `pptx_native.py`（原生 shapes）。两者取舍见 `references/delivery-formats.md`。
2. **图表八类**（`chart.py`）：bar / bar-horizontal / line / area / bar-stacked /
   donut / scatter / combo。AI 只写 DSL（intent / message / emphasis / annotations），
   图形类型按**意图树**确定性地映射，不随便选；**muted + 1 accent**（给了 emphasis
   才启用）；**结论先行**（`message` 当大标题，`title` 降为数据集名小标签）；
   不画图例/坐标轴数字/网格线（既定风格）。PPT 层按类型映射原生图表（环图/散点
   各有坑，见 `references/charts.md`）。柱高/条宽与数据成比例由 `check.py` 独立复核。
3. **错位只用在标题 / 时间点**：其他地方用错位会毁可读性（方案第 2 层）。
4. **生图不由脚本做**：推荐路径是 `--brief` 写提示词契约、人出图、`--check` 验收
   （见上）。另有色块拼贴（它本身就是版画式拼贴）与 `--provider-cmd`（有 API 的人用）。
   不配 provider 就永远不会调生图模型 —— 这是设计不是疏漏，见 `references/images.md`。
5. **缓存命中不等于可信**：缓存里的图也会过"只在色板三角形内"的不变量，
   塞彩图会被拒绝并丢弃重做。
6. **同 spec + 同种子 = 字节级一致**：用 random.Random(seed, parts) 派生错位 / 颗粒，
   不是全局 random。如果改了 seed 输出没变，多半是 spec 里没把 seed 传进去。
7. **demo 的图文页要先造图**：`dev-tools/demo.spec.json` 的 `image` 是占位文件名，
   按「跑法」跑一遍才有图。产物是本地文件，不进仓库（仓库只收文本 + 两个 SVG 图标）。
8. **IO 收在 `deckio.py`（一个刻意留的例外）**：读 / 写 / 数字解析全走那里。例外是
   `validate_spec.py` —— 它的职责就是用退出码 2 报「输入有问题」，所以要自己分辨
   「读不到」和「不是合法 JSON」（两者给用户的信息不一样），合并了反而变差。

## 仓库布局

```text
skills/deck-authoring/          # 可消费面：AI 调用 skill 时读的就是这棵树的这部分
├── SKILL.md                 # 给模型看的触发条件 + 流程
├── README.md                # 给"想跑一下"的人看的
├── scripts/                 # 流水线十七件（另有 1 个 Swift 编码器）
│   ├── validate_spec.py     # 输入层校验：字段集封闭（坐标/字号/色值直接判失败）
│   ├── ink.py               # 墨色推导 + 三色板门禁（唯一消费者）
│   ├── plate.py             # 图片 → duotone + 半调（制版）
│   ├── image_source.py      # 提示词契约(--brief) / 验收(--check) / 生图 / 色块拼贴
│   ├── fonts.py             # 字体库：清单(--list) / 取字体(--fetch) / 映射(--map) / 内嵌
│   ├── palette.py           # 配色：OKLCH / 结构实测(--audit) / novelty / 三方向 / 角色
│   ├── hierarchy.py         # 信息层级：文本预算 / 视觉焦点 / 内容密度（全是提示级）
│   ├── grid.py              # 网格与间距：12 列 / 令牌 ramp / 关系规则（几何唯一来源）
│   ├── chart.py             # 图表引擎：意图树 / 八类 SVG / muted+accent / 标注
│   ├── plan.py              # 规划层：内容理解 / 叙事骨架 / 页型 / 到 spec 的桥
│   ├── compile.py           # 决策层：spec → resolved.deck.json（色板/档位/时间轴 + trace）
│   │                          （brief / coreThesis / claims / 空话 / 重复也在这查）
│   ├── brand.py             # 品牌资产：logo 内嵌 / 色板与字体合并 / SVG 栅格化
│   ├── fit.py               # 试排：给定一页内容，实测哪些版式装得下（真渲真量）
│   ├── style.py             # 风格层：列表 / 契约体检 / 摘要 / 联系表（八套拼一张图）
│   ├── deliver.py           # 交付演练：整条链跑一遍 + 画面与逐像素比对
│   ├── render.py            # deck-spec.json → HTML（语义骨架 + 风格 skin + 演示壳 + 运动引擎）
│   ├── measure.py           # 实测层：真浏览器量真盒子（不估算）
│   ├── check.py             # 校验：越界/裁切/对比度/图表/图片/报错
│   ├── pdf.py               # HTML → 矢量 PDF（并验页数/页尺寸/位图/字体）
│   ├── shots.py             # HTML → PNG（系统 Chrome 截图）
│   ├── make_pptx.py         # PNG → PPTX（贴图版）
│   ├── pptx_native.py       # HTML → PPTX（原生 shapes，字能改）
│   ├── animate.py           # HTML → MP4 / GIF（逐帧 seek 录制，可复现）
│   ├── h264_encode.swift    # 帧序列 → H.264（AVFoundation，无需 ffmpeg）
│   └── deckio.py            # IO 收口（try/except 不散落）
├── styles/                   # 用户自建风格（**无内置**）：一种风格 = 一个目录
│                             #   （style.json token + skin.css 视觉层），不碰 .py；
│                             #   历史八套已整体移除，参数表留在文档里作自建参考
├── brands/                   # 品牌资产：一个品牌 = 一个目录，不碰 .py
│   └── example/              #   示例品牌（logo 正版 + 反白版 + 署名）
├── dev-tools/
│   ├── demo.spec.json       # 一份能跑的样例（已引用 example 品牌）
│   ├── stress.spec.json     # **压测**用：21 页真实形状（长标题/密页/疏页/全部版式）
│   └── style-fixture/
│       └── swiss-grid/      # 开发/测试夹具风格（demo、stress、测试套件走它；
│                             #   不是交付物，自建风格时可拷改）
├── evals/evals.json         # 行为评估用例
└── references/
    ├── pipeline.md             # **总编排协议 0-59 全文**：链路/五门/失效/可复现/交付
    ├── style-architecture.md    # 多风格 seam、字段集
    ├── validation.md            # 校验的口径（阻塞 vs 提示）
    ├── delivery-formats.md      # HTML / PDF / PNG / PPTX / MP4 的取舍
    ├── animation.md            # 运动规则 0-42 全文落地、按角色 preset、确定性、导出
    ├── brand-assets.md         # 品牌与资产协议（v2.0）：四层、优先级链、v2 对照表
    ├── content-intelligence.md  # 内容智能与规划系统（v3.0）：Brief / 论断 / 一页一 Takeaway
    ├── planning.md             # 规划层模块：schema、骨架表、复杂度、到 spec 的桥
    ├── layout-system.md        # 布局规则 0-87 全文落地：网格/令牌/层级/约束/路线图
    ├── charts.md               # 图表引擎：意图树、八类、弱化强调、消息先行
    ├── color.md                # OKLCH 结构/novelty/三方向/auto 派生（省 colorSet）
    ├── fonts.md                # 126 字体库、风格映射、严格 A 级、用户缓存
    └── images.md               # 图像契约：AI 出合同、人出图、--check 验收
tests/deck-authoring/           # 测试住在仓库顶层（不在 skill 目录里）
├── test_ink.py
├── test_determinism.py
├── test_check_mutations.py
├── test_halftone_monotonic.py
├── test_cache_invariant.py
├── test_skill_md_consistency.py
├── test_validate_spec.py
├── test_shell.py
├── test_pdf.py
├── test_pptx_native.py
├── test_font_advisory.py
├── test_animation.py
├── test_brand.py
├── test_fit.py
├── test_style.py
└── test_deliver.py
```

测试**刻意不放在 skill 目录里** —— AI 调用 skill 时读的是 `skills/deck-authoring/`
那棵树，测试放进去会被顺手读走；同理 `SKILL.md` 与 `references/*.md` 里也不许
出现指向测试的指针（`validate_skill.py` 会把那种回流判为失败）。

## 跟外层仓库的关系

- 同目录模块用 `importlib.util` + `sys.modules` 加载（见 `_load_sibling`），
  不靠 `sys.path.insert` —— 这条 Pyright 才会过。
- IO 走 `deckio.py`（读 / 写 / 数字解析一处收口，自然带上 try/except）。唯一的例外是
  `validate_spec.py`，它要自己分辨「读不到」与「不是合法 JSON」才能给出对的退出码。
- **确定性地基**：产物里 `window.__deck_timeline` / `__deck_motion` 跟 HTML 一起走，
  所以 `animate.py` 不需要 spec、也不需要 style.json —— 给的 HTML 就是唯一事实来源。
- 渲染层不写死任何颜色 / 尺寸 —— 全从 `style.json` 注入，CSS 里只有 `var()`。
