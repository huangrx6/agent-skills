# 动画与视频导出（高级动画设计规则全文落地）

`animate.py` 把 deck 渲成 MP4 / GIF。本文 = **它是什么** + **运动规则体系（0–42 节全文）**

+ **确定性地基** + **导出**。每节标落地状态：【✅ 已实现】【约定=规则在、效果未接】。

> 先对齐期待：这个 skill 出的是**把 deck 逐页走一遍的视频**（每页入场编排 + 阅读
> 停顿），不是 30 秒多镜头 motion design 片。分镜、运镜、音频是另一件事，不做。

## 三种导出各自的运动

**同一段画代码**（`paint()`）驱动三种场景，「讲出来的」和「录出来的」不会跑偏：

| 场景 | 时钟 | 效果 |
| --- | --- | --- |
| 演示态（`?present`） | rAF（墙钟） | 翻到哪页，放哪页的入场 |
| 取帧（`animate.py`） | `__deck.seek(t)`（纯函数） | 要哪帧给哪帧，可复现 |
| 滚动态（默认） | 无 | 静态满态，给改稿/测量/截图/PDF 用 |

适合：发群/邮件（MP4 双击就开）、归档、贴 Notion/飞书（GIF 自动播）、演示兜底。
不适合：要互动（给 HTML）、要对方改字（给 PPTX）、要矢量存档（给 PDF）。

## 0. 目标

核心不是"给元素套特效"，而是让动画服务**内容叙事、信息层级、页面风格、跨页连续性**。

## 1. 总体原则【✅】

动画必须至少解决一个问题：引导注意力 / 解释结构或关系 / 强调数据或结论 / 建立页面
节奏 / 增强风格表达 / 建立跨页连续性。禁止：为了炫而叠加效果；**所有页面/元素统一
fade/slide/grow**；让每个元素单独表演；多个高强度效果同台。

模块组成：Motion Tokens → Motion Profile → Effect Selection → Page Choreography →
Timeline → Deterministic Runtime → Motion QA（Effect Registry 见 §5 的落地说明）。

## 2. 动画决策优先级【✅】

页面语义 > Page Type > 信息层级 > Style > Layout > Motion Intent > Effect Novelty >
技术实现。先回答：这页讲什么、视觉焦点是谁、页面什么类型、内容怎么"讲出来"，
最后才选效果。本仓库把这条路固化成**角色表**（manifest 的 role → 上台方式）。

## 3. Motion Intent【约定】

每页先定 intent：introduce / reveal / explain / compare / progress / focus /
transform / connect / conclude / transition（如
`{"motion_intent": "explain", "narrative_direction": "left_to_right", "energy": 0.55}`）。
本仓库由 spec 的页型与图表 `intent` 标注承担其职，未单独建 intent 字段。

## 4. 四类 Motion Role

+ **Signature Effect**（每页最多 1 个、封面优先、用了则其余降级）：【约定——本
  零依赖确定性管线不接 Aurora/Liquid Chrome/Particle Text 这类 WebGL/Shader 效果；
  要它们就换工具链，别在纯函数管线里塞】
+ **Semantic Motion**（数字 Count Up、柱图 Grow、折线 Path Draw、流程渐进）：
  【✅ 段式线 growX、标题/正文/图的揭示已进 paint；**图表没有数据动画
  （G2 `animation:false`）—— 图表页只有容器入场**，见 §19/§31】
+ **Ambient Motion**（低幅低速氛围）：【约定——背景纹理静态；grain 在帧模式/
  reduced-motion 下隐藏。"观众不该感觉背景在表演"由"背景根本不动"满足】
+ **Transition**（跨页）：【约定——当前是页内入场 + 切页；Shared Element/FLIP
  见 §23】

## 5. Effect Registry【约定】

规范要求所有 React Bits / Aceternity / Magic UI / GSAP / 自研 Shader 效果注册到
统一 Registry（id/name/source/semantic_tags/page_types/energy/complexity/
export/limits/incompatible_with…）。本仓库的效果面很小且全部自研在 `paint()` 里，
**不需要注册表**；真要引入第三方效果的那天，先建 Registry + §27 的 Adapter。

## 6. Effect 分类【约定】

Typography Reveal / Ambient Background / Shader Material / Grid Digital / Particle /
Reveal / Spatial Layout / Card Effects / Border Effects / Diagram Motion / Data Motion /
Interactive Motion —— 本仓库只实现 Reveal（mask / wipe）与段式线 growX 等少数语义
效果；**图表侧没有 Data Motion（grow / draw）**（G2 `animation:false`）；
交互类（Magnet / Cursor）只可能出现在 HTML，视频导出必禁。

## 7. Page Type 与 Motion Budget【✅ 换算落地】

每页预算（Cover 80-100 … Table 10-25）：封面大胆、正文克制、表格代码最少。
本仓库不用打分制，用**硬上限**达到同义约束：单页主要运动类型 ≤2（§17）、
位移带（§18）、入场时长 enterMs 全套页共享一个刻度——预算超标的根源（多效果
叠加）在结构上就不可能发生。

## 8. Page Type 推荐效果【✅ 等价落地】

Cover/Statement → 标题 maskRevealY + 正文 fadeRise；Chart → **只有容器先行**
（图表只有容器入场，无柱生长/折线描画）（**禁**大面积 glitch/粒子——本管线
没有这些，等于结构性满足）；
Cards → Cluster/近同时揭示（stagger 50-130ms，禁 card1→4 大间隔依次飞入
—— stagger 由风格 token 统一，不会写出大间隔）。

## 9. Style Motion Profile【✅】

Style 不绑定效果，定义**运动性格**。本仓库每个风格一套 `motion` 参数（enter/
stagger/titleHold/hold/readPerItem/easing + note），这正是 motionProfile 的参数化：
personality→easing 曲线，tempo→enter/stagger，continuity→titleHold。

## 10. Motion 参数怎么定：性格 → 参数（推导，不是查表）

**铁律：不提供参数对照表**（会被当成选项清单）。参数按场合 → 性格 → 区间推导；
区间即各性格的实际取值范围。

动效性格由**场合**决定（观众多远、要不要留反应时间、内容是读的还是扫的），
参数由性格夹出来：

| 场合 → 性格 | enter | stagger | titleHold | hold | read/条 | easing |
| --- | --- | --- | --- | --- | --- | --- |
| 讲台远讲，一屏一个观点 → 慢起长尾 | 800~950 | 110~140 | 380~450 | 2200~3200 | 680~820 | expoOut |
| 评审 / 架构 / 复盘 → 精确、短、整齐 | 480~560 | 60~80 | 240~280 | 2400~2700 | 720~780 | **只认 expoOut**（无弹性） |
| 数字要“拍”上去 → 脆 | 560~660 | 80~100 | 280~320 | 1700~1900 | 500~560 | expoOut |
| 输出不该有仪式感 → 快 | 400~460 | 40~60 | 160~200 | 2300~2500 | 680~720 | expoOut |
| 正文是要读的句子 → 翻书 | 650~720 | 90~100 | 320~360 | 2800~3000 | 850~950 | expoOut |
| 轻快（唯一考虑回弹的场景） | 540~600 | 70~90 | 220~260 | 2600~2800 | 760~800 | 可 overshoot |

怎么用：先从这份 deck 的场合推出性格（一行依据），再从对应行取数；**不要跨行杂交**
（enter 取慢行、stagger 取快行 = 性格分裂）。同一场合内取值可以自由，但相邻两次
选择别都取端点 —— 那是另一种“永远一样”。

## 11. Motion Tokens【✅】

duration xs180/sm300/md520/lg800/xl1200、distance 4/6/12/24、stagger 35/70/120、
ease enter=expoOut…**禁止每个元素随机写毫秒和位移**。落地：所有毫秒/位移来自
`style.json` 的 `motion` 块（一套风格一份）；图表侧没有第二处写毫秒的地方
（G2 `animation:false`）。本页位移：标题 26px、正文 16px、图表容器 10px、页码 0。

## 12. Motion Budget 规则【✅ 结构性满足】

典型成本 Signature 40-60 / Semantic 20-40 / Ambient 10-20 / Transition 10-20，
超预算必须降级。本仓库没有 Signature/Ambient（§4），页内成本 = 编排表长度 ×
token，天然在预算内；"降级"表现为换更小的 preset（§40）。

## 13. Motion Creativity【约定】

0-0.25 Corporate / 0.25-0.5 Polished / 0.5-0.75 Creative / 0.75-1 Experimental；
effective = creativity × page_type_factor（Cover×1.0 … Table×0.3）。本仓库把
"创造力预算"固化为**风格人格差异**（每套自建一份参数；一套风格只用一个性格）。

## 14. Motion Novelty【约定】

fadeUp 0.05 / maskReveal 0.25 / sharedMove 0.45 / decryptedText 0.65 /
liquidChrome 0.80…"Novelty 只影响候选排序，不得覆盖语义匹配"。本仓库效果面小，
novelty 不参与选择；等效果多了再建表。

## 15. Effect Selection Score【约定】

Style Match×0.25 + Semantic×0.25 + PageType×0.15 + Hierarchy×0.10 + Novelty×0.10 +
Export×0.10 + Perf×0.05 − 冲突/可读性/预算罚分。当前由**角色→preset 的查表**
替代打分（语义匹配是第一且唯一的排序键——正是"不得覆盖语义匹配"的极端形式）。

## 16. 信息层级与动画强度【✅】

P1 主视觉（完整入场）/ P2 标题（mask+落定）/ P3 支撑（fadeRise）/ P4 正文
（小位移淡入）/ P5 脚注页码（静态或跟壳）。落地：title→body→chrome 的编排表

+ titleHoldMs 停顿 = "Priority 越低动画越弱"。

## 17. 单页主要运动限制【✅】

max_primary_motion_types = 2。本页两族：**遮罩/淡入族**（title mask、body fade）

+ **结构生长族**（rule growX、image wipe 同属"揭示"一族的
方向变体——这里的"方向"指效果方向，与 spec 的 `layout` 布局无关；
图表 grow/draw 不存在，G2 静态渲染）——同页不会
出现 Fade+Slide+Scale+Rotate+Blur+Bounce+Glow+Glitch
同台（后四样本管线不存在，前几样按元素类型各归其位）。

## 18. 位移规则【✅】

文字 4-16px / 卡片 6-16 / 图标 4-12 / Hero 12-32；40px+ 只给大型转场。实测：
正文 16、标题 26、图表容器 10、页码 0——全在带内。

## 19. 元素动画应按类型设计【✅ 本轮落地】

**禁止所有元素统一 opacity 0→1**。落地（`paint()` 按角色分派）：

| 元素 | preset | 怎么动 |
| --- | --- | --- |
| 标题（含父块） | maskRevealY | clip-path inset 从下揭开 + 26px 落定 + 1.012 settle |
| 段式线 .rule | growX | scaleX 0→1、origin left（线是"画"出来的） |
| 图片 | imageReveal | 横向揭开（inset 右收）+ 1.02→1 settle |
| 图表容器 | 容器先行 | 淡入 + 10px 微升（图表页**只有这一层**，见下） |
| 正文/副题 | fadeRise | 0→1 + 16px（**不是** 0.4→1：第 0 帧必须是干净空态，ghost 起点会破坏抽帧 QA） |
| 页码/壳 | chrome | 只淡入不位移，跟标题走 |

**图表内部没有数据动画（`.bar` / `.line` / `.dot`）**：
图表由 AntV G2 渲染（`animation:false`，见 `charts.md`），产物里没有
`.bar` / `.line` / `.dot` 这些元素 —— `paint()` 里对应几行的选择器匹配不到任何
东西，不产生效果。图表页只剩上面那一行**容器级**入场。

## 20. Animation Direction【✅】

阅读方向 + 布局方向 + 语义方向。左文右图 → 图从左向右揭开（imageReveal 的
inset 方向）；时间线/流程按序 stagger（DOM 顺序即编排顺序）；标题自下揭开。
禁随机方向——方向全部写死在 preset 里，没有随机。

## 21. Visual Mass 与 Duration【✅ 等价】

duration = base × visual_mass（Caption 0.5 / Body 0.7 / Card 0.9 / Title 1.0 /
Hero 1.3 / Architecture 1.6）。落地为编排：标题先落定 → titleHold → 正文
stagger；（原「图表容器先于数据 6%」随图表数据动画关死而失效：容器即图表，
没有第二层）——重的东西晚、久，轻的东西早、快，同一 easing。

## 22. Motion Quiet Zone【✅ 结构性满足】

文字 bbox 外扩 10-20% 内降低动效强度/亮度方差/粒子密度。本管线背景不动、
无粒子无 shader 穿过正文——quiet zone 由"不存在喧闹"满足。

## 23. Shared Element / FLIP【约定】

相邻页同一语义元素（标题换位、logo 跨页、排名变化）优先 FLIP 而不是
淡出淡入。未实现：当前切页即换场。要做：相邻页同 role 元素的 bbox 插值
（seek(t) 里可做，纯函数可行）——记在路线图。

## 24. Scroll Effect 转换【✅ 天然满足】

scroll_progress → page_timeline_progress，禁止依赖真实滚动。本仓库取帧态根本
没有滚动（`data-view=frame` 只显当前页），演示态翻页走同一 `paint()`。

## 25. Cursor Effect 转换【✅ 天然满足】

视频模式 pointer 必须虚拟化或禁用。本仓库没有 cursor 效果（HTML 也没有），
等于禁用。

## 26. Deterministic Runtime【✅ 地基】

**相同 t + 相同 seed = 相同画面**。`paint(si,t)` 纯函数；编排表（含折线长度
`getTotalLength`）在渲染时算一次；禁 `Date.now()/performance.now()/Math.random()`
进渲染路径（演示态 rAF 墙钟只驱动"何时调 paint"，不进画面状态）；
seed 已显式进 spec（错位/颗粒按 (seed,元素) 派生）。

## 27. Effect Adapter【约定】

第三方效果必须经 Adapter（init(seed) + render({time,progress,w,h,pointer})），
不得自控时钟。目前无第三方效果；引入之日即 Adapter 上线之日。

## 28. Timeline DSL【✅ 等价】

`window.__deck_timeline=[{slide,start,enter,hold}]` 由 Python 的 `timeline()`
算出（总长/帧数/切点都是它的下游），JS 只按 t 画——结构同规范的
`{target,preset,start,duration}`，target 换成了角色化编排表。

## 29. Motion Graph【✅ 简化】

after/before/with/sync/overlap —— 落地为编排表的 delay 数学：body 在 title
之后（enter×0.55 + titleHold），页码与标题同拍。复杂依赖图未做（没有需要它的页面结构）。

## 30. 基础 Preset Library【✅ 子集】

规范列了 15 个：fadeSoft fadeRise maskRevealX maskRevealY imageReveal
scaleFocus growX growY pathDraw countUp highlight crossFade sharedMove
blurToClear accentSweep。**已实现规范 preset 4 个**：fadeRise、maskRevealY、
imageReveal、growX；编外 pop（散点）。**growY（柱）与 pathDraw（折线）不适用**（图表由 G2 静态渲染）；
countUp/highlight/sharedMove 等记在路线图。高级 Shader 效果不进 preset（见 §5）。

## 31. Page Choreography【✅】

Cover：Ambient（无）→ 主标题 maskReveal → 副题 → 稳定终态。
Chart：结论标题 → 容器先行（淡入 + 10px）→ 页码 → 稳定（**图表内部不再动**，
见 §19）。
Cards/正文：标题落定 → 停顿 → 条目近同时揭示（stagger 50-130ms）。
每页进**稳定终态**（hold 段无动画）——末帧即终态。

## 32. 阅读时间模型【✅ 本轮补齐】

reading_time = base_hold + text_complexity + chart_complexity…
落地：`hold = holdMs + n×readPerItemMs + 0.18×min(数据项,8)`，整页 clamp ≤7s
（base 1800-3000ms 按风格；中文每条 520-900ms；图表页比同重量文本页多停）。
已废弃"常数 hold"。

## 33. Ambient Motion 参数【✅ 等价】

幅度 2-5%、周期 10-30s、低透明度、低频——"观众不该感觉背景在表演"。
本仓库取 0：背景完全静态（grain 静点阵）。要加漂移的那天按此带内调。

## 34. Motion Density【✅ 等价】

none/low/medium/high；Cover high、Content low、Table none。本仓库密度由页型
结构决定：图表页 = 只有容器一层（数据动画关死），文本页 = 标题+条目，表格/代码页 = 静态满态
（滚动态交付时零动画）。

## 35. Typography Effect 等级【✅ 等价】

L1 Readable（mask/淡入——本仓库标题用）/ L2 Expressive（只给标题数字——
settle scale 1.012 只在标题）/ L3 Experimental（Particle/Decrypted…——没有，
也不接）。正文 >40 字禁止实验性排版：正文只有 fadeRise，结构性满足。

## 36. Signature Effect 降级规则【✅ 空集】

用了 Liquid Chrome/Hyperspeed/Particle Text 等则标题降为简单 mask、正文 fadeSoft、
转场 cut——本仓库没有 Signature，降级规则空转；"高级效果越强其余越克制"的
精神体现在：图表页标题/条目按序落定，图表容器不与它们抢拍（titleHold 隔开）。

## 37. 推荐 Effect Source Pool【约定】

React Bits / Aceternity / Magic UI / Motion / GSAP / Codrops / 自研 Shader——
零依赖管线一个都不引入；灵感池留给未来接 React 渲染器的那条线。

## 38. Export Compatibility【✅】

每个效果的导出面（html/mp4/gif/ppt_native/static_fallback）。本管线的全集：

| 效果 | html | mp4/gif | pptx | pdf | 静态兜底 |
| --- | --- | --- | --- | --- | --- |
| 全部 preset（§19） | ✅ 演示态 | ✅ 逐帧 seek | ❌（原生 PPTX 无动画） | ❌（矢量静态） | ✅ 滚动态满态 |

导出失败必有 static fallback = 滚动态的 CSS 满态（clearPaint 清掉内联态即回满态）。

## 39. Motion QA【✅ 有测试钉】

每页检查：有无明确意图（角色表）；是否超预算/超运动类型（§7/§17 结构性满足）；
是否干扰文字（quiet zone §22）；**是否用了非确定性时钟**（测试静态扫
`transition` 禁令 + determinism 逐帧回归）；**是否可 seek**（`__deck.seek`
接口 + 同 t 同帧测试）；clearPaint 是否清干净（测试钉每个属性）；末帧是否
稳定终态。改动后至少抽帧三看（见文末）。

## 40. Motion Repair（按序修，别跳步）【✅】

删次要 Ambient（没有）→ 删第二 Signature（没有）→ 降视觉强度 → 降密度 →
减 stagger → 减位移 → 简化标题效果 → 高级换基础 preset → 复杂转场换
cut/crossfade → 最后才全关。加效果反向：先语义、再层级、最后才效果本身。

## 41. 推荐运行流程【✅ 对应】

Page Planner（页型/层级/布局/风格）→ Motion Resolver（角色→preset 查表）→
Page Choreography（编排表 + delay 数学）→ Timeline（Python `timeline()`）→
Deterministic paint → Render → Motion QA（测试 + 抽帧）→ Repair →
HTML/Present/MP4/GIF。

## 42. 最终核心规则

动画服务内容叙事；Style 定性格不定效果；Page Type 定编排；Semantic 优先于
Decorative；每页最多 1 个 Signature（本库为 0）；主要运动类型 ≤2；Priority 越低
动画越弱；一切 `state = f(t)`，同 t 同 seed 同帧；方向服从阅读/布局/语义；
正文必须克制；**并非每页都必须有动画**（滚动态零动画是合法交付）；导出失败必有
static fallback。最终目标不是"炫"，而是"让观众更自然地理解页面"。

---

## 确定性：渲染路径上不能有 CSS transition

逐帧渲 = 每帧一次 `seek(t)` + 截一张图，"同一个 t 必须出同一帧"撑着可回归、
可局部重渲、可复现。CSS `transition` 走墙钟，逐帧 seek 下中间态取决于"截这帧时
真实过了多久"——不可复现且不报错（huashu 的坑 #18，实测同动画三次两种结果）。
所以：动画状态一律 t 的纯函数；动位移用独立属性 `translate`/`scale`（不写
`transform`——skin 自己会用它，写了互相覆盖）；`transform-origin/box` 只落在
段式线与图表 SVG 内部（skin 不变换这些元素）。测试静态扫产物里有无 `transition`
（壳除外：页码/提示录视频时隐藏，不进渲染路径）。

## 导出

```bash
python3 scripts/animate.py out.html -o deck.mp4                  # MP4（1920×1080 @24fps）
python3 scripts/animate.py out.html -o deck.gif --width 960      # GIF（960 宽）
python3 scripts/animate.py out.html -o deck.mp4 --fps 60         # 60fps
python3 scripts/animate.py out.html -o x.mp4 --stills 0,2.5,10   # 只抽帧不编码
```

依赖全在系统里：取帧 = 系统 Chrome + **CDP**（一次启动截几百帧；一帧一个
`--screenshot` 要 15 分钟，CDP 70 秒，51 倍）；H.264 = **AVFoundation**
（`swiftc` 现场编，`xcode-select --install`）；GIF = PIL。缺 `websockets` 会
说清代价并降级，不静默变慢。

产物要验不能只看返回 0：MP4 查 `ftyp` 头 + `avconvert` 回读；GIF 查 `GIF89a`
头 + **总时长**（Pillow 会把相同帧合并——实测 777 帧写出 160 帧而时长是对的，
盯帧数只会得到假失败）。

交付前抽帧三看（`--stills` 走同一条取帧路径，看到的即录到的）：**第 0 帧**
干净空态、**某页落定后**内容都在、**末帧**停在终态。
