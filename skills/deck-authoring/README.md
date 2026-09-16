# deck-authoring — 把结构化内容渲成能讲的 deck

把一份 `deck-spec.json` 渲成演示 deck，**风格自建**（一种风格 = `styles/<名>/` 一个目录，无内置），
交付 HTML（可演讲）/ 矢量 PDF / 可编辑 PPTX / 每页 PNG。

## 这是什么 / 不是什么

- 这是「**内容只管写，版面与颜色脚本算**」的 skill —— 字号、折行、对比度全部由脚本算
  （字号档由你在 spec 里声明），风格适配不改任何 .py。
- 它**不是**单一风格的：**内置风格已整体移除**（风格是每份 deck 的表达层），风格按 deck 项目
  自建（`styles/<名>/`），加一套 = 拷一个目录改 token 与 CSS，不改任何 .py。
- 它**不是**只能出死图的：HTML 自带走演示态（键盘翻页 / 缩放 / 页码），
  而且能用 `pptx_native.py` 出**字能改**的 PPTX。
- 它**不是**通用图表工具 —— 数据图表八类，几何由 **AntV G2** 算（vendor 锁版本内联），
  风格处理只作用于容器，柱与刻度保持干净（错位会毁掉可读性）。
- 它**不是**「换个 css 滤镜」—— 图片按原样进产物（制版后处理 `plate.py` 已退役），
  版画质地在**出图提示词**里要，不在交付链里加。

## 跑法（最快路径）

```bash
cd skills/deck-authoring/
python3 scripts/validate_spec.py your.spec.json                     # 1) 规格（字段集封闭）
python3 scripts/ink.py styles/<你的风格>/style.json                  # 2) 墨色门禁（对比度）
python3 scripts/image_source.py --prompt "现场照片占位" -o sample-treated.png
                                                                    # 3) 造占位图（几何色块拼贴）
python3 scripts/render.py your.spec.json -o out.html                # 4) 出 HTML
python3 scripts/render.py your.spec.json -o out.html --repair       #    （溢出时：降档→复检≤4轮）
python3 scripts/render.py your.spec.json -o out.html --candidates   #    （未声明布局：候选并测出表）
python3 scripts/measure.py out.html                                 # 5) 实测（真浏览器）
python3 scripts/check.py your.spec.json out.html                    # 6) 校验
python3 scripts/pdf.py out.html -o deck.pdf                         # 7) 矢量 PDF
python3 scripts/shots.py out.html --out-dir pages/ --count 6        # 8) 截图（要 Chrome）
python3 scripts/pptx_native.py --png-dir pages/ -o deck.pptx        # 9) 出 PPTX（贴图，观感 100%）
python3 scripts/pptx_native.py out.html -o deck-editable.pptx        # 或 --resolved 契约（同核同几何）       # 10) 出 PPTX（原生，能改字）
python3 scripts/animate.py out.html -o deck.mp4                     # 11) 出视频（另有 GIF）
```

第 11 步不需要 ffmpeg：取帧走 Chrome DevTools Protocol（一次启动截几百帧，比一帧一个
`chrome --screenshot` 快 51 倍），H.264 编码走 macOS 自带的 AVFoundation，GIF 走 Pillow。
抽几帧看看再编：`--stills 0,1.5,22.4,32.3`。运动设计与什么时候该用视频，见
`references/animation.md`。

设计期工具现在只剩这两个（都不在流水线上）：

```bash
python3 scripts/render.py your.spec.json -o out.html --resolved resolved.deck.json --trace
                                               # 决策留痕：每条 阶段 / 决定 / 理由
python3 scripts/grid.py --json                 # 版面几何唯一来源（12 列 / 间距令牌）
```

`style.py`（列风格 / 契约体检 / 联系表 `--sheet`）与 `fit.py`（试排）已随 v4 退役：

- **选风格要的是画面，不是对照表** —— 按「跑法」渲几版并排看即可（三方向流程见
  `SKILL.md`）；风格本身怎么加见 `references/style-architecture.md`。
- **「这页装不装得下」改成写完就渲、渲完就量**：`check.py` 的实测门会点名越界的元素
  （原 `fit.py` 是把候选版式与各条目数档位摆进同一份产物渲一次、量一次）。内容怎么组织
  （一页一个观点、版式选择、观众距离）见 `references/content-intelligence.md`。

第 3 步是给 demo 的图文页造一张**占位图**（走 `--prompt` + `-o`，几何色块拼贴）：
`demo.spec.json` 的 `image` 是个占位文件名，不先生成它就是一张裂图。要换成真照片就走
下面的 `--brief` 契约。该产物**不入库**（见「已知限制」第 7 条）。

**要换成真照片**（推荐路径，三条路里最正经的一条）：

```bash
python3 scripts/image_source.py --brief your.spec.json             # → 图片提示词契约
#   契约里逐张给了：文件名 / 实测尺寸 / 比例 / 透明通道 / 色彩约束（不引入色板外的色相）/ 可粘贴的
#   中英提示词 / 负面清单。拿去出图，按文件名存到产物同目录。
python3 scripts/image_source.py --check your.spec.json             # 验尺寸与比例
```

分工是**脚本写契约 → 人出图 → 脚本验收**：脚本知道每张图进哪个槽位、那个槽位实测
多少像素、该套色板是哪几个颜色；而"出一张好看的图"这件事，人拿自己顺手的模型做得比
脚本调一个陌生 API 好。彩照**不直接塞进 image 字段**，也不做制版后处理（`plate.py`
已退役，图片按原样进产物）—— 版画质地在提示词里要到位；等图期间用占位图（`--prompt`

- `-o`，几何色块拼贴）顶住，流水线不会因为等图停住。

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
色彩来自该风格的色板，光线与风格来自气质档，限制来自这条出图管线的色彩约束
（不引入色板外的色相）。
尺寸 / 比例 / 数量**不写进提示词**（生图 API 有独立参数，写重了会打架），单列在
「参数」栏。字段分工、优先级裁决与踩过的坑见 `references/images.md`。

## 测试

```bash
python3 -m unittest discover -s tests/deck-authoring -v     # 336 条，约 4 分钟（负载敏感）（空闲时）
```

耗时说明：几乎全是**真浏览器**的开销，所以对机器负载很敏感 —— 空闲时两三分钟，
    同时在跑视频编码之类的大活时会明显变长（实测从 138s 涨到过 330s）。改了风格或渲染层
    就跑全量；只改文档可以只跑相关的那个文件。

钉住这些不变量：同 spec + 同种子字节一致（带随机区间的风格；反向也测 —— 改 seed 必须
真的变）、色板门禁 + 两墨乘叠印的数学、校验的变异验证（每项都造违规样例，验它真有牙）、
规格字段集真的封闭（坐标/字号/色值必须被指名报出，未知键不许静默放过）、
外壳行为（真开浏览器按键翻页 + letterbox 缩放比贴边不溢）、
PDF 是矢量且页数 / 页尺寸对（含"故意删掉 `@page` 必须被拦"）、
可编辑 PPTX 的**字是真字**且坐标是页内坐标、字体提示不报废话、
字体库（清单 / 映射 / `--installed` 不许假阳性 / `.otf` 与 `.ttf` 的格式优先级）、
网格数学（列宽 97.33 的精度、7+5 必须正好铺满 1432、间距令牌的关系规则）、
图片契约与验收（契约字段要说清、`--check` 不许顺手造占位图作弊）、
资产管线（manifest 契约 + assetId 只是语义引用，路径只在 resolved 里）、
**同一个 t 两次独立浏览器会话取到的帧逐字节一致**（且不同 t 必须真的不同 —— 否则上一条
会假绿）、渲染路径上没混进 CSS `transition`、
**每种风格的装饰落点与它声明的 `decor.types` 一致**（遍历的是**目录**不是写死的名单 ——
写死名单让四套新风格逃过检查过一次）、SKILL.md 的版式表与 `render.py` 实测行为一致、
**品牌资产**（优先级：品牌赢色板/字体/logo、风格赢版面；logo 内嵌且清单里给的是
技能相对路径；`cover+end` 指的是 end 版式那页而不是数组最后一页；logo 压文字会挡）、
**原生 PPTX 的三个交付级偏差**（`<a:ea>` 东亚字体 / 标题字重不写死 / 原生图表的
数值与网格线 —— 三条都只在"把 PPTX 转成图看"时才露出来）。

随脚本一起退役的用例（不再有）：半调墨覆盖率随灰度单调、缓存命中后仍过色板三角不变量、
试排"装得下"与"半页空"、风格契约体检、交付演练工具的逐像素差 —— 对应的是 `plate.py` /
`fit.py` / `style.py` / `deliver.py` 的能力，删脚本时一并删了。

## 依赖

- Python ≥ 3.10（用了 `from __future__ import annotations` + importlib 动态加载同目录脚本）
- `Pillow`（截图拼装 / 几何色块拼贴 / GIF）
- `python-pptx`（PPTX 拼装）
- macOS 上 `shots.py` 需要 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- **导出视频不需要 ffmpeg / gifsicle / ImageMagick**：用系统已有的三件 —— Chrome（取帧）、
  `swiftc` + AVFoundation（H.264）、Pillow（GIF）。CDP 的传输走 `websockets`（装了就走快
  路径；没装会说清代价后降级，不静默变慢）。
- 不要装 Playwright —— `--headless=new --screenshot` 就够，多装一份纯属浪费

## 规划层（内容 → Storyline → 页规划 → spec）

渲染链之上是四层规划，**越靠近渲染 AI 自由度越低**：内容理解（中）→ Storyline（中）
→ Page Planner（低~中）→ Slide DSL（很低，封闭字段集）→ 渲染（0）。

**规划层脚本（`plan.py`）已退役** —— 它的四个入口（叙事骨架 / 页型映射 / 规划检查 /
到 spec 的桥）全没了，规划从"脚本跑一遍"变回"作者写、`validate_spec.py` 验字段集"：

```bash
python3 scripts/validate_spec.py your.spec.json     # 规划层现在只有这一道机器验
```

下面这些硬规矩**没有变**，只是不再由脚本喊出来（原 `--check` 的规矩，逐条保留）：

**缺 coreThesis**（一份 deck 必须有一句统领论断）、**brief 缺
desiredAction/desiredBelief**、**悬空引用**（message 的证据 / claim 的 derivedFrom
指向不存在的 fact）、**事实与推断不分**
（source_type 必须是 original/inferred/generated；高重要性结论只靠推断支撑要自己警觉）、
**骨架乱序**（先讲方案再讲问题不是自由是错）、**配额漂移**（sections 页数之和 ≠
target_slide_count —— "15 页做成 28 页"就是这条漏的）、**复杂度爆表不拆页**
（字符/节点/图表/图/层级加权 ≥0.70 必须标 split）、**页没有 message**（不知道自己
在讲什么的页没法排版）。

`--to-spec` 那个桥也没了 —— 规划产物现在是**手写的 spec**，同样**必须过 validate_spec**
（有测试钉死）—— 规划层产出的东西渲染器吃不下 = 全白写。分工、Schema 与规划层没做的
部分（文档抽取、候选打分、架构图页型）见 `references/planning.md`。

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
冷暖 / 强调策略 / 创意等级…）—— 这些是**作者声明**的。渲染期由脚本推导的只有文字色
（`ink.text_color`）与叠印墨（`overprint(primary, secondary)`）。

**配色审计（`palette.py --audit/--novelty/--directions/--roles`）已整体退役**：不再有脚本
替你选色或给三方向；画质门槛改由 `ink.py <style.json>`（对比度，不达标退 1）与
`check.py`（实测门）验。

原 `palette.py` 在 **OKLCH** 里推导（不用 HSL：HSL 的 L 与感知明度不成正比，提亮之后
对比度反而会掉，而对比度在这里是硬门槛）—— 这条结论仍然成立，只是现在由人执行：改色板时
**用感知均匀的空间调明度**，别拿 HSL 的 L 当明度。

随之退役的还有它那套“二次变体”生成规则（色相 ±10~30°、彩度 ±5~20%、明度 ±3~12%，
**中性色不旋色相** —— C≈0 时旋了是空操作，实测会产出重复色）—— 规则保留作手调依据：
要在一个色板上多一套近亲色板，就按这个范围改，别另外发明。

**俗套提醒**（`tech_blue_purple_cyan` / `corporate_blue_white` / `premium_black_gold`…）
随 `palette.py` 一起退役、不再自动出现 —— 名单与判据留在 `references/color.md` 供自查。
它本来就只是**按主题条件的提示**而不是阻塞（规范原文是"不得**自动**绑定"，不是"这个色
不许用"）：历史内置期实测本仓库 8 套风格里 5 套的某个色板落在名单上（`swiss-grid/blue`
同时命中前两条、`terminal/cyan`、`billboard/electric`…）。

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
- **阶梯**：4 套风格曾有 subtitle == bullet（同级碰撞 = 没有层级），已修（内置期）；
  判它的 `style.py --check` 已退役 —— 同级碰撞 / 倒挂不再有脚本门，靠作者自查

## 布局与信息层级

**我们的布局不是模板系统，也不是约束系统** —— 是**固定画布 + 7 种手写版式 + 真浏览器
实测校验**。画布 1600×900、`PAD 84/132`、正文带 132→824 是几何常量的唯一来源。

**规范里最核心的那条原则（"不要让 LLM 决定 x=327，程序负责精确布局"）从第一版就是
那样做的**：spec 里根本没有 x/y —— `validate_spec.py` 把 `x`/`y`/`dx`/`dy`/`rot`/
`width`/`height` 直接判错。所以那是**加法**，不是重构。

`hierarchy.py`（信息层级提示：文本预算 / 视觉焦点 / 内容密度）**已退役** —— 那三条阈值
取决于语境（封面就该空、看板就该满），做成门会把第一份正常的 deck 挡住；而**装不装得下**
这件事已由 `measure.py` 实测的越界 / 裁切两道定死。**规矩本身保留**，现在靠作者自查：

- **文本预算**（规范第 22 条）—— 封面标题 ≤12 字、内页标题 ≤24、单条 ≤60…；超了就按
  这个顺序修：删字 → 拆信息 → 换版式 → 拆页 → **最后才允许缩字号**（字号档由你声明，
  没有按条数自动升降）
- **视觉焦点**（规范第 8 条）—— 要求第一名领先第二名 ≥25%，且达首名 60% 权重的元素不超
  过 3 个（实测我们的版式稳定领先 **90%+**）
- **内容密度** —— 占正文带的百分比，按 Minimal 35~50% / Normal 45~65% /
  Information 55~75% / Dashboard 65~82% 分档

**硬约束与软约束是分开的**（规范第 21 条）：越界 / 裁切 / 对比度 / 图片没加载 / 装饰压文字 /
logo 压文字 / 一张图盖满整页 / 图表没渲染出来 → `check.py` **阻塞**；字体回退 / 网格对齐 /
图被放大 / 布局轮换 / 品牌与形状 → **提示**。混淆的后果是第一份正常的 deck 就被挡住，
然后所有人开始忽略检查。

五块（布局 / 层级 / 留白 / 图形 / 图表）的现状、该借谁的规则（Fluent 2、Figma Auto
Layout、Design Tokens、**IBCS + ISO 24896**、AntV）、缺什么、以及**分四步的路线图**
（哪步是加法、哪步要动 8 套 skin、风险在哪）见 `references/layout-system.md`。

## 已知限制

1. **贴图版 PPTX 改不了字**：要能改字就走 `pptx_native.py`（原生 shapes）。两者取舍见 `references/delivery-formats.md`。
2. **图表八类（AntV G2 渲染，vendor 锁版本内联进产物、动画关死保确定性）**：bar /
   bar-horizontal / line / area / bar-stacked / donut / scatter / combo。spec 仍**必须显式写**
   `chart`（推断已退役）；`intent` / `message` / `emphasis`（muted + 1 accent）/ `annotations`
   是语义标注，其中 `message` 当大标题、`title` 降为数据集名小标签（结论先行）；
   不画图例/坐标轴数字/网格线（既定风格）。PPT 层按类型映射原生图表（环图/散点
   各有坑，见 `references/charts.md`）。`check.py` 的图表门换了判据：不再查"柱高与数据
   成比例"（几何由 G2 算），改查 (a) **G2 真渲染出来了**（`measure.py` 实测 `chartReady`：
   `ready` / `pending` / `error`，静态 HTML 判断不出来）与 (b) **数据形状**（`label` 非空、
   `value` 是数字）。
3. **错位只用在标题 / 时间点**：其他地方用错位会毁可读性（方案第 2 层）。
4. **生图不由脚本做**：推荐路径是 `--brief` 写提示词契约、人出图、`--check` 验收
   （见上）。另有色块拼贴（它本身就是版画式拼贴）与 `--provider-cmd`（有 API 的人用）。
   不配 provider 就永远不会调生图模型 —— 这是设计不是疏漏，见 `references/images.md`。
5. **缓存命中不等于可信**：`image_source.py` 命中缓存后仍会过"只在色板三角形内"那道判据，
   不合规就丢弃重做。但这道判据对**真实照片**已不成立（照片本就有千百种颜色，v4 随
   `plate.py` 退役，相关用例也删了）—— 它现在只兜住占位 / 拼贴那条路；真照片的色彩
   约束改由 `--brief` 的提示词承担。
6. **同 spec + 同种子 = 字节级一致**：用 random.Random(seed, parts) 派生错位 / 颗粒，
   不是全局 random。如果改了 seed 输出没变，多半是 spec 里没把 seed 传进去。
7. **图文页要先造占位图**：spec 里 `image` 写的是占位文件名时，
   按「跑法」第 3 步跑一遍才有图（`--prompt` + `-o` 出几何色块拼贴）。产物是本地文件，
   不进仓库（仓库只收文本 + 两个 SVG 图标）。
8. **IO 收在 `deckio.py`（一个刻意留的例外）**：读 / 写 / 数字解析全走那里。例外是
   `validate_spec.py` —— 它的职责就是用退出码 2 报「输入有问题」，所以要自己分辨
   「读不到」和「不是合法 JSON」（两者给用户的信息不一样），合并了反而变差。

## 仓库布局

```text
skills/deck-authoring/          # 可消费面：AI 调用 skill 时读的就是这棵树的这部分
├── SKILL.md                 # 给模型看的触发条件 + 流程
├── README.md                # 给"想跑一下"的人看的
├── scripts/                 # 流水线十四件 + layout/ 包（另有 1 个 Swift 编码器 + 1 个 vendor）
│   ├── layout/              # 布局层包：几何模型(Rect/安全盒) + 碰撞政策(分组/距离表/豁免)
│   ├── validate_spec.py     # 输入层校验：字段集封闭（坐标/字号/色值直接判失败）
│   ├── ink.py               # 墨色推导 + 三色板对比度门禁（不达标退 1）
│   ├── image_source.py      # 提示词契约(--brief) / 验收(--check) / 生图(--provider-cmd) / 色块拼贴
│   ├── fonts.py             # 字体库：清单(--list) / 取字体(--fetch) / 映射(--map) / 内嵌
│   ├── grid.py              # 网格与间距：12 列 / 令牌 ramp / 关系规则（几何唯一来源）
│   ├── deck.py              # 决策层：品牌资产并入 + spec → resolved（色板/档位 + trace）
│   ├── render.py            # deck-spec.json → HTML（语义骨架 + skin + 演示壳 + 运动引擎 + 内联 G2）
│   ├── measure.py           # 实测层：真浏览器量真盒子（不估算；图表报 chartReady）
│   ├── check.py             # 校验：越界/裁切/对比度/图表就绪/图片/报错
│   ├── pdf.py               # HTML → 矢量 PDF（并验页数/页尺寸/位图/字体）
│   ├── shots.py             # HTML → PNG（系统 Chrome 截图）
│   ├── pptx_native.py       # PPTX：HTML → 原生 shapes（能改字）/ --png-dir → 贴图版
│   ├── animate.py           # HTML → MP4 / GIF（逐帧 seek 录制，可复现）
│   ├── h264_encode.swift    # 帧序列 → H.264（AVFoundation，无需 ffmpeg）
│   ├── vendor/              # g2-5.2.10.min.js（版本锁死，渲染时内联进产物）
│   └── deckio.py            # IO 收口（try/except 不散落）
├── styles/                   # 用户自建风格（**无内置**，可选目录、不随仓库分发）：一风格一目录
│                             #   （style.json token + skin.css 视觉层），不碰 .py；
│                             #   历史八套已整体移除，参数表留在文档里作自建参考
├── brands/                   # 品牌资产：一个品牌 = 一个目录，不碰 .py
│                             #   （**没有示例品牌** —— 示例资产会被直接当成可用资产，
│                             #    实测把示例 logo 带进过真实交付。品牌由用户建：
│                             #    brand.json + logo 文件，契约见 references/brand-assets.md）
# 注意：styles/ 零内置、零示例 —— 风格按契约自建，磁盘上没有可找的样例
#（可拷贝的模板必然变成默认答案）。
├── evals/evals.json         # 行为评估用例
└── references/
    ├── pipeline.md             # **总编排协议 0-59 全文**：链路/五门/失效/可复现/交付
    ├── style-architecture.md    # 多风格 seam、字段集
    ├── validation.md            # 校验的口径（阻塞 vs 提示）
    ├── delivery-formats.md      # HTML / PDF / PNG / PPTX / MP4 的取舍
    ├── animation.md            # 运动规则 0-42 全文落地、按角色 preset、确定性、导出
    ├── brand-assets.md         # 品牌与资产协议（v2.0）：四层、优先级链、v2 对照表
    ├── content-intelligence.md  # 内容智能与规划系统（v3.0）：Brief / 论断 / 一页一 Takeaway
    ├── planning.md             # 规划层规则：schema、骨架表、复杂度（`plan.py` 已退役，规则改由作者执行）
    ├── layout-system.md        # 布局规则 0-87 全文落地：网格/令牌/层级/约束/路线图
    ├── charts.md               # 图表：八类、弱化强调、消息先行（几何由 G2 算）
    ├── color.md                # OKLCH 结构、配色规范里哪些是代码强制 / 流程判断（`palette.py` 已退役）
    ├── fonts.md                # 126 字体库、风格映射、严格 A 级、用户缓存
    └── images.md               # 图像契约：AI 出合同、人出图、--check 验收
tests/deck-authoring/           # 测试住在仓库顶层（不在 skill 目录里）
├── test_validate_spec.py
├── test_ink.py
├── test_grid.py
├── test_check_mutations.py
├── test_determinism.py
├── test_shell.py
├── test_pdf.py
├── test_pptx_native.py
├── test_animation.py
├── test_fonts.py
├── test_font_advisory.py
├── test_image_brief.py
├── test_cache_invariant.py
├── test_asset.py
└── test_skill_md_consistency.py
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
