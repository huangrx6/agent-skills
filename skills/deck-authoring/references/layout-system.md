# AI PPT 布局与视觉结构规则（v3.0 Final 全文落地）

适用：布局与页面结构层（PPT / HTML Deck / PDF / MP4 / GIF 共用）。核心目标：把
Page Planner 输出的"页面意图"稳定转换为**可测量、可约束、可评分、可修复**的页面
几何。本规则负责：布局、区域、网格、信息层级、留白、对齐、视觉平衡、版式变体、
Content Fit、评分与修复。不负责：内容事实、品牌身份、最终颜色、图片 Prompt、
图表语义选型、动画特效本身。每节标落地状态：【✅ 已实现】【约定=规则在、机制未接】。

> 架构口径：规范设想"Resolved Slide JSON"作为几何层工件；本仓库的对应物是
> **渲染后的 DOM 本身**（浏览器就是 Layout Resolver：spec 无坐标 → render.py
> 派生几何 → 真浏览器排 → `measure.py` 用 CDP 量回）。语义层（Slide DSL=spec，
> 字段封闭、`COORD_FIELDS` 直接判错）与几何层（DOM+实测）同样禁止混合——
> 只是几何层不是一份 JSON，是活页面。

## 0. 核心原则【✅】

**LLM 决定语义与意图，程序决定几何与坐标。** LLM 可以决定：pageType /
layoutFamily（候选）/ regions / priority / semanticRelation / visualWeight /
density / focalPoint / composition / visualRequirement。LLM 不允许决定：x / y /
width / height / dx / dy / rotate / 任意像素 gap / 任意字号 / 任意 padding。
落地：spec 里**根本没有坐标字段**（`validate_spec.py` 的 `COORD_FIELDS` 把
x/y/dx/dy/rot/width/height 全判错）；最终几何由渲染层派生。

## 1. 总体架构【✅ 下半段已在】

Slide Content → Page Planner → Layout Intent → Layout Family → Variant
Candidates → Region Tree → Grid/Spacing/Constraints → **Layout Resolver** →
Measurement → Hard Check → Layout Score → Repair → Resolved Slide → Renderer。
本仓库：`plan.py`（前半）→ spec → `render.py`（resolve）→ `measure.py`（实测）
→ `check.py`（硬检查）→ `hierarchy.py`（软尺）；Score/Repair 引擎见 §37/§52。

## 2. 职责边界【✅】

Content Engine 决定"说什么"（content-intelligence.md）；Page Planner 决定页面
类型/主要视觉/密度/谁最重要/语义关系（plan.py）；Layout Engine 决定放哪里、占
多大、间距多少、是否换版、是否拆页（render.py + grid.py + fit.py）；**Renderer
只按 Resolved 布局绘制，不重新布局**（渲染分支里没有第二套几何）。

## 3. 坐标体系【✅】

Canonical Canvas = **1600×900**（设计空间，非输出格式）；导出再映射（HTML 走
`--k` 视口缩放、PDF 矢量、PNG 按宽 ×2、PPTX 转 EMU）。内部不使用 0~1 比例做
文字/gap/padding（比例只用于 focalPoint/裁切/响应映射），baseline 与间距用
Design Unit。

## 4. Safe Area【✅】

left/right = 84、top = 132（在 96~132 建议带内）、底部页脚独立带（52+24）。
硬规则全落地：标题越界=阻塞；正文不得进页脚带；logo/页码有独立保护区（重叠
即阻塞）；full-bleed 类图可越安全区但**核心文字不行**（bounds 检查只豁免图片）。

## 5. Grid System【✅】

12 Columns / margin 84 / gutter 24；列宽**动态计算**
`(1600 − 2×84 − 11×24) / 12 = 97.33`（非整数是刻意的），只从 `grid.py` 取。
禁止手写列宽——教训实测：check.py 曾手写 `CONTENT=(…,838)` 与 render 的 824
漂了 14px，两个"唯一来源"已经漂了才发现；统一后不再漂。

## 6. Grid Span【✅】

核心组件宽度取整列（ALLOWED_SPANS：2/3/4/5/6/7/8/9/12）：图文页 = 7+5 列、
两栏 = 6+6 列、时间线宽度按节点数从网格算（原写死 300px，6 节点超宽 538px 靠
flex 硬扛——已改为算）。例外允许：full-bleed、editorial overlap、hero 构图、
装饰元素；核心信息组件必须能解释其网格关系（对齐检查，§12）。

## 7. Region Model【约定】

页面先分 Region 再放 Component；基础 Region：HEADER/BODY/ASIDE/FOOTER/HERO/
VISUAL/META，支持嵌套。落地形态：`grid.py` 的 `REGIONS` 常量 + HTML 结构本身
（`.pad` = HEADER+BODY、`.footrow` = FOOTER、图/图表列 = VISUAL）；**没有独立
的 region-tree JSON**——要"版式族×变体"（§15-18）时才需要它。

## 8. Auto Layout 参数【✅ 精神落地】

父 Region 负责 direction/padding/gap/align/justify；子组件不写坐标。落地 =
CSS flex/grid：父容器 padding/gap 全走 `--sp-*` 令牌，子元素内容变化自动重排
（fit.py 试排依赖的正是这一点）。

## 9. Spacing Tokens【✅】

Global Ramp：8/12/16/24/32/48/64/96；Alias：inner 16 / item 24 / group 48 /
section 64（+hero 96）。注入产物为 CSS 变量 `--sp-*`；壳里的 gap 全部走令牌。
实测改前 10 个 gap 出现 7 种值（48/68/45/74/101/16/0），改后结构性 gap 全落
在令牌上。

## 10. 间距关系【✅】

inner < item < group < section；**组距 ≥ 1.5 × 条目距**（Gestalt 接近性）、
节距 ≥ 1.25 × 组距——成文进 `grid.py`，`--json` 自检。间距必须表达关系，
不是装饰。

## 11. Style 与 Spacing【✅】

Style 不重定义任意 spacing，只允许覆盖语义档（spacingOverrides）。禁止
gap=57/73/101——改后 skin 的手写值收敛到令牌（残余 6~8 处手写值在路线图里
继续清）。

## 12. Alignment【✅ 提示级】

必须检查：标题/正文/卡片/图/图表/表格/题注的左缘与 baseline。落地：锚点元素
（标题、栏题、图、图表）左缘必须吸附到列——提示级。实测改前左缘 7 个任意值
（418/752/800/909/1086/1281/84），改后全部落列（84=边距、448=col4、812=col7、
933=col8、1176=col10）。优先序：同 Region 左缘 > 网格列 > baseline > 光学对齐。

## 13. Optical Alignment【✅】

允许组件规则做少量视觉修正（图标超 baseline 1~3px、圆形视觉中心微移、大标题
字形边界微调）——本仓库的这类修正都在 skin.css 里**由风格作者写**，不由 LLM
生成。

## 14. Page Type 与 Layout Family 分离【 部分 ✅】

Page Type=页面语义类型，Layout Family=空间组织方式（comparison 页型 → split
族）。落地：`plan.py` 的 `PAGE_TYPES` 把页型查表映射到版式（comparison→chart、
process→timeline…）；**family/variant 两级中间层未建**（§15-18 约定）。

## 15. Layout Family【✅ 第一片已落地（content-image）】

规范至少支持 single/split/stack/grid/hero/editorial/overlay/timeline/diagram/
chart/table/dashboard/full-bleed。现状：7 种 slide type（title/content-text/
content-image/two-column/timeline/chart/end）+ 自建风格。**content-image 率先
成为显式家族**：`variant` 字段进 spec（封闭值集），其余 type 仍是单版式 ——
family 命名层全量铺开在路线图阶段 3。

## 16. Layout Variant【✅ 第一片已落地（3 变体）】

每个 Family 多 Variant（split_40_60 / split_50_50 / split_left_visual / …；
hero_center / hero_left / hero_full_bleed / …）。**content-image 已有显式变体**：
`visual-right`（文 7 栅 + 图 5 栅，默认）/ `visual-left`（图先文后，镜像换节奏）/
`even`（6+6 均分）——键值双封闭（validate_spec），显式即进 Decision Trace
（compile layout 段），fit 探针把三变体摆进同一份产物供评分。其余 type
（两栏 6+6、时间线）仍隐式 —— 等候选实测铺开。

## 17. Variant 选择依据【✅ 第一片已落地（content-image）】

不得随机选版式；必须考虑内容量/视觉角色/图比例/优先级/语义关系/风格/密度/
平衡/前后页节奏。现状（content-image）：spec 写 `variant: "auto"` →
`fit --recommend` 把三变体 × 真图摆进同一份探针**实测**（CandidateScore，
图的高宽比是真实输入）→ 落盘 JSON → `compile --fit-variants` 按分选最佳；
平局偏默认，无数据回退默认并留痕。**显式 variant 永远赢**——实测数据
不越权改内容决策。其余 type 仍页型查表（确定性，不随机）。

## 18. Variant Candidate Ranking【✅ 第一片已落地（content-image）】

Page Planner 输出候选+分数，Resolver 实测后定版。现状（content-image 闭环）：
`fit recommend`（纯函数）从实测选每页最佳 + 对手分数；`compile` 的
auto 决策吃同一份数据、Decision Trace 带分数对比。全类型铺开待各家族
有真变体（hero / cards / editorial …）。

## 19. Information Hierarchy【部分 ✅】

每个核心组件 priority 1..5（P1 主视觉/P2 标题结论/P3 关键证据数字/P4 支撑/
P5 来源页脚）。落地：`grid.py` 有 PRIORITY 表；`hierarchy.py` 的三把尺（文本
预算/视觉焦点/密度）承担 P 判定的量化。

## 20. Priority 影响【✅ 精神落地】

Priority 影响字号 tier/字重/明度/面积/位置/留白/动画强度/突出度，**不能只靠
"字号越大越重要"**。落地：风格 type 阶梯（cover/subtitle/bullet/colTitle 分
级）+ 动画按角色分强度（title mask / body fadeRise / chrome 只淡）+
`style.py --check` 把同级碰撞与倒挂判错（4 套风格曾 subtitle==bullet 同字号，
两级之间没有层级——已修）。

## 21. Focal Point【✅】

primary ≤1、secondary ≤2；多元素同等抢眼 → focal_conflict。落地：
`hierarchy.py` 的 weights()：相对焦点间距 ≥25% 才算明确 + ≤3 个重元素。实测
demo 与压测 deck 每页第一焦点领先第二名 90%+（标题永远最大字、图/图表永远
最大面积——不是偶然，是阶梯的结构结果）。

## 22. Visual Weight【✅】

visualWeight = 面积 × 对比 × 字重 × 饱和 × 孤立度 × 语义优先。落地：
`hierarchy.py` 用墨宽×高度/页面积×10 做简化质量；主焦点应显著领先（提示阈值
top1/top2 ≥ 1.25 → 我们用 25% 间距同义）。

## 23. Density【✅】

density = 占用核心面积 / 安全内容面积；参考带：Minimal 35-50 / Normal 45-65 /
Information 55-75 / Dashboard 65-82。落地：`hierarchy.py` 四带区（提示级，
工程启发式不是硬标准）。

## 24. 留白规则【✅】

留白分 micro/component/group/structural/narrative 五级；服务分组/焦点/呼吸/
节奏/视觉方向。落地：令牌 ramp 即五级的参数化（inner=组件内、item=条目间、
group=组间、section=节间、hero=剧场级）；**禁止为填满页面消灭留白**（§47 的
反面检查：密度带提示 + 空洞内容不加）。

## 25. Balance【约定】

检查左右/上下视觉质量、焦点周围空间、标题正文关系、模块间质量分布；不要求数学
对称，允许 intentional asymmetry。原则成立（风格的非对称构图是刻意的）；**无
balance_score 计算**（§26）。

## 26. Balance Score【约定】

`1 − normalized_mass_difference`，mass = 面积 × visualWeight——软指标未实现；
要做时 `hierarchy.py` 的 weights 已备好输入。

## 27. Composition【约定】

symmetric/asymmetric/centered/editorial/radial/directional/layered；Style 可
偏好 composition，但内容和 Page Type 优先。现状：每套风格的构图倾向写在
style-architecture 的对照表里（swiss=栅格对称、botanical=编辑式非对称）。

## 28. Content Fit 修复顺序【✅ 顺序成文】

布局失败**禁止第一步缩字体**：1 删无关内容 → 2 更短 Copy → 3 删低优先级 →
4 调 gap → 5 调 padding → 6 调区域比 → 7 换 Variant → 8 换组件档 → 9 缩
非核心视觉 → 10 拆内容 → 11 拆页 → **12 最后才降字号 tier**。落地：这条顺序
写进 `hierarchy.py` 的报错文本（人唯一一定会读的那段字）；`bullet_tier()`
的自动降档是**兜底**不是第一手段（退位到阶段 3，见附录路线图）。

## 29. 字号降级【✅】

只允许 tier down（body.lg → body.md），禁止任意压缩（32→31→29→27）。
落地：`bullet_tier()` 按条目数在 type 阶梯里**选档**，不是连续缩放；风格
阶梯封闭（style.py 校验同级/倒挂）。

## 30. Component Constraints【约定】

minWidth/maxWidth/minHeight/aspectPolicy/maxLines/grow/shrink 每组件声明。
现状：无组件清单；等价约束散在渲染分支（时间线最小节点宽、图列宽 7 列）。
MetricCard 式声明表未建。

## 31. Image Constraints【✅】

aspect ratio（实测插槽比）/ minResolution（盒子 ×2）/ bleedAllowed / 无放大
（check 阻塞）都在图像契约与 check.py；**禁止非等比拉伸、无 focal 的盲裁、
小图强放大**——放大检查阻塞，比例在 brief 阶段对齐。

## 32. Chart Constraints【✅】

Chart Container 负责 chart box/title box/标注区/标签安全区；**Chart Engine
不得突破 Container**（chartwrap 1100×330 钉死，SVG 就画这么大）；**Layout
不决定 chart type**（chart.py 意图树查表）。

## 33. Diagram Constraints【部分 ✅】

页面布局只负责 Diagram Container，内部 node/edge/connector/间距由引擎自管，
**页面网格不强行控制每个节点**。落地：timeline 容器宽从网格算，节点内部排布
自管；独立 diagram 引擎未建（无架构图版式——plan.py 页型表里故意没有它）。

## 34. Table Constraints【约定】

表格过高优先拆表/分页/转附录而不是缩到不可读。现状：无 table 版式（表格数据
走 chart 或截图）；规则留给将来。

## 35. Hard Constraints【✅ 全对上】

失败即阻塞：overlap（重叠）✓、out of bounds（越界）✓、text clipping（溢出）✓、
unreadable min font（对比度+最小字号）✓、image excessive upscale（图放大）✓、
chart label clipping（图表成比例）✓、logo overlap（logo 压字）✓、footer
collision（页脚带）✓、impossible aspect（比例冲突）✓、unresolved required
asset（缺图）✓ —— `check.py` 8+ 条，`deliver.py` 在 check 失败时直接中止
（"把已知有问题的 deck 做成五种格式只是把问题复制五份"）。

## 36. Soft Constraints【✅】

进入提示不阻塞：grid alignment / hierarchy / whitespace / focal clarity /
density / style consistency / decoration restraint —— `hierarchy.py` +
`check.py` 提示流。做成阻塞的话第一份正常 deck 就被挡住，然后所有人开始忽略
检查。

## 37. Layout Score【约定】

建议权重：Grid 15 / Hierarchy 15 / Whitespace 15 / Focal 10 / Balance 10 /
Density 10 / Style 10 / Readability 10 / Decoration 5，总分 100；Hard Fail →
invalid。未实现分数引擎；等价物：Hard Fail = 退出 1（invalid 的机器形态），
软项各有独立提示。可测项清单已备（见 §38 注），汇总成分数是加法。

## 38. Score Threshold【约定】

≥90 excellent / 85-89 pass / 75-84 repair recommended / <75 repair required。
未实现；阈值要等 §83 benchmark 校准后才有意义。

## 39. Decoration Restraint【部分 ✅】

检查装饰面积占比/是否穿正文/假焦点/重复/匹配风格。落地：装饰压文字=阻塞；
decor 类型与角位由风格 token 限定（版心已满的版式不放装饰）；面积占比审计在
`style.py`。不能只看"装饰少不少"。

## 40. Deck-level Rhythm【约定】

不能只评单页：连续同 Variant 数、visual/text 节奏、full-bleed 频率、chart
连续页数、纯文字连续页数。未实现（单页检查为主）；stress deck 提供测试面。

## 41. Repetition Rule【约定】

同一 layoutVariant 连续 ≤2 页，超过提示（附录、数据连续比较可例外）。未实现。

## 42. Layout Novelty【约定】

0..1；Corporate 0.2-0.4 / Technical 0.3-0.5 / Creative 0.5-0.8；Novelty 不得
破坏可读性。由风格性格承担（自建几套 = 几档事实上的 novelty），无数值。

## 43. Style 与 Layout【✅】

Style 控制：对称偏好/密度偏好/overlap 倾向/留白倾向/editorial 程度/容器倾向；
**不直接规定每页几何**。落地：风格只出 tokens（type 阶梯/motion/decor/
spacing 覆盖），几何全部来自 render+grid。

## 44. Shape Language 接口【约定】

Layout 只消费 Shape Profile（cornerRadius/strokeStyle/shadowStyle/
surfaceStyle/lineStyle/geometry/decorationDensity/iconStyle 八参）。未建独立
shape 层（圆角/描边等散在各 skin.css）——路线图阶段 4。

## 45. Graphic Grouping【✅】

相关元素优先靠 proximity/alignment/共享容器/共享样式/connector 分组，**不要
一上来就加边框**。落地：两栏=共享容器+对齐；bullet 组=proximity+左对齐；
时间线 connector 表达流程。

## 46. Container Usage【✅】

Card/Container 只用于独立单元/可比模块/明确分组/浮层层级；**禁止所有内容
卡片化**。落地：多数版式无卡片（文字直接上版面），容器只在两栏/时间线节点。

## 47. Connector Rule【✅】

连接线只表达流程/方向/依赖/数据流/关系；纯装饰连接线禁止——本仓库连接线只在
timeline（语义=顺序），没有装饰线。

## 48. Visual Direction【✅】

页面应有明确阅读方向（left_to_right / top_to_bottom / center_out / radial）；
**Layout 与 Motion 共享 direction**。落地：DOM 顺序即 stagger 顺序（自上而
下）；图在右列=左读文右看图；动画方向与版面方向同源（§20）。

## 49. Layout Intent【部分 ✅】

Page Planner 输出 layoutIntent（family/composition/density/direction/
focalPoint/visualWeight/whitespace）。落地：`plan.py` 的 PAGE_TYPES 行携带
visual（主视觉类型）与 density 提示；family/composition 字段未建。

## 50. Resolved Layout【✅ 架构差异见顶部注】

只有 Resolved 层可含坐标：`{canvas, variant, regions:{x,y,w,h},
components:{…}}`。本仓库的 Resolved 层 = 渲染后的 DOM + `measure.py` 的实测
矩形（语义清单记意图、几何由测量层量回——两者对不上就是 bug）。无独立 JSON
工件；要接 Layout Score（§37）时再物化它。

## 51. Schema 分层【✅】

Slide DSL=语义层、Resolved Slide=几何层，**禁止混合**。落地：spec 字段封闭
且无坐标（COORD_FIELDS 判错）；几何只存在于渲染产物与测量结果。

## 52. Repair Engine【✅ 等价形】

Repair 不重生成整页，输出 Patch（switch_copy_level / switch_variant…）。
落地：`check.py`/`hierarchy.py` 的提示就是诊断（指名哪个元素、什么问题、按
§28 顺序修）；Patch=人改 spec 的那几行，重跑门。无机器自动改写（人在环是
刻意的：修复决策里"删什么内容"是价值判断）。

## 53. Repair Priority【✅ 成文】

R1 删无关装饰 → R2 短 Copy → R3 删低优先级 → R4 调 gap → R5 调 padding →
R6 调区域比 → R7 换 variant → R8 换组件档 → R9 缩非核心视觉 → R10 拆内容
→ R11 拆页 → **R12 降字号 tier**。与 §28 同一张表，写进 hierarchy 报错。

## 54. Repair Loop【✅ 人在环版】

resolve → measure → check → score → repair → resolve again，最多 3~5 轮。
落地：改 spec → `render` → `check` 循环（每轮秒级）；超过几轮应停下来想
（fail with diagnostic 的精神——check 的报错就是 diagnostic）。

## 55. Fit Engine【✅】

fit 只做真实测量：text height / line count / occupied area / overflow /
image fit / chart fit；**不决定内容价值**（值不值得说是 content-intelligence
的事——元规则 14）。落地：`fit.py` 把候选版式与条目数档位摆进同一产物渲一次
量一次，报实测溢出与占比。

## 56. Browser Measurement【✅】

HTML 路径优先真浏览器测量：actual font metrics / wrapping / SVG bounds /
DOM rect / image natural size。落地：`measure.py` 走 CDP 拿真矩形；
**字符宽度估算只能做预判**（fit 的粗筛），最终判断全靠实测。

## 57. Candidate Testing【约定】

一次生成多个 Variant，同一浏览器批量测量后排名；选择 = hard pass + 最高分。
雏形：fit.py 多档位试排；多 variant 并测未实现（等 §16 变体表）。

## 58. Candidate Score【约定】

Fit×0.35 + Layout×0.35 + StyleMatch×0.15 + RhythmMatch×0.15。未实现。

## 59. Deck-level Layout Planner【约定】

页面不能完全独立选 layout；需读 previousVariant/nextIntent/sectionRole/
pageImportance，避免连续同构页。未实现（配合 §40-41 一起做）。

## 60. Cover Layout【✅】

Cover 允许 hero/大量留白/非对称/full-bleed/overlap/editorial 构图；必须保证
标题清楚、Logo 安全、主视觉不压信息。落地：title 版式 + 品牌 logoOn=cover

+ 装饰角块（不压字，阻塞检查守着）。

## 61. Statement Layout【✅】

目标只有一个：强化一个 Message；优先大标题/单数字/单焦点，避免多卡片多图表
多层 bullet。落地：statement 页型 → content-text sparse 密度（plan.py 表）。

## 62. Comparison Layout【✅】

优先 split/成对卡/图表/前后对照，**必须真正表达"对照"**。落地：comparison
页型 → chart:bar（含 emphasis 弱化对照）或 two-column。

## 63. Process Layout【✅】

优先 timeline/sequence/pipeline，必须明确方向。落地：process → timeline，
方向=自左向右（DOM 序=阅读序）。

## 64. Architecture Layout【约定】

优先 layered/hub-spoke/左到右/matrix/cluster，页面布局优先给 Diagram 足够
面积。**页型表里故意没有它**：渲染器无架构图版式，映射过去是死路（等 diagram
引擎，见 planning.md 的未做清单）。

## 65. Chart Layout【✅】

Chart 是 Primary Evidence 时建议占核心视觉面积 ≥50%，不被正文挤成小角落。
落地：chart 版式全宽 chartwrap（1100×330 是版心主体），标题=结论先行。

## 66. Table Layout【约定】

Table 是 Primary 时优先 full-width、减少额外卡片装饰。无 table 版式，规则
预留。

## 67. Image Role 与面积【✅ 启发式对齐】

hero 40-75% / evidence 30-55 / supporting 20-40 / decoration <20（不是硬
限制）。落地：content-image 的图列 = 5 列 ≈ 版心 40%（supporting~evidence
带）；**图占满整页（≥60% 全页面积）= 阻塞**（反 slop 的硬边界）。

## 68. Full Bleed【✅ 限定】

主要用于 Cover/Section/Image Story/Mood/特殊过渡页；**正文页默认不用**。
落地：无 full-bleed 版式；装饰角块是唯一的出血元素且受角位限定。

## 69. Overlap【✅ 限定】

只在 editorial/hero/creative/共享元素构图用；必须文字可读、层级清楚、不遮
核心信息。落地：装饰块可越安全区但压字=阻塞；文字元素之间重叠=阻塞。

## 70. Layout QA【✅】

每页硬查：bounds/overlap/text overflow/min font/image distortion/chart
clipping/logo collision/required region missing；软查：grid/hierarchy/
whitespace/focal/balance/density/repetition/style consistency/decoration
restraint。落地：`check.py`（硬，阻塞）+ `hierarchy.py`（软，提示）。

## 71. QA 输出【✅ 等价形】

规范 `{valid, hardErrors, warnings, score, metrics}` ≈ 本仓库：退出码
（0=valid）+ 阻塞报错清单 + 提示清单；metrics 分项在 hierarchy 各尺里，
汇总 score 未建（§37）。

## 72. 与 Content Rules 的边界【✅】

Content 决定 message/claim/evidence/copy/contentBudget；Layout 决定放哪里/
占多大/是否换版/是否拆页。复杂度 ≥0.70 该拆是 plan.py 拦（内容层），
装不装得下是 fit.py 量（布局层）——同一张表的两侧。

## 73. 与 Typography Rules 的边界【✅】

Typography 决定 font family/type scale/line height/tracking/最小字号；
**Layout 只选 type tier，不自行造字号**（阶梯在 style.json，封闭校验）。

## 74. 与 Color Rules 的边界【✅】

Color 决定 theme/accent/surface/contrast；Layout 只读视觉权重用于焦点评分
（hierarchy 的 weights 用墨量，不定义颜色）。

## 75. 与 Brand Rules 的边界【✅】

Brand 决定 logo asset/logoOn/锁定政策；Layout 决定 logo region/size/spacing
（`.brandlogo` 高 56、右上、安全边距——风格侧）。

## 76. 与 Image Rules 的边界【✅】

Image Rules 决定 prompt/focal/asset/裁切容差；Layout 决定 image box/角色/
比例要求（brief 从实测插槽反推比例——布局先行，§15 的图像协议）。

## 77. 与 Chart Rules 的边界【✅】

Chart Rules 决定 type/encoding/labels/annotations；Layout 决定 chart
container/结论标题区/图表面积占比（§32/§65）。

## 78. 与 Motion Rules 的边界【✅】

Layout 提供 direction/region hierarchy/focal point/shared element geometry；
Motion 基于这些决定动画。落地：动画按 manifest 角色分派 preset，方向=版面
方向（§48），强度=层级（§20）。

## 79. Geometry Single Source of Truth【✅ 用血换的】

canvas/safe area/grid/margin/gutter/spacing tokens/footer zone/logo zone
全部来自 `grid.py` 一个模块。禁止 render.py 一份、check.py 一份、pptx.py
又一份——本仓库就栽过（824 vs 838 漂 14px），统一后再没漂过。

## 80. Token Single Source of Truth【✅】

至少统一 grid/spacing/typography tier/radius/stroke/shadow；
**Renderer/Checker/Fit/Export 读同一套**。落地：几何=grid.py、字号=style
阶梯、颜色=colorSets，check 与 render 不再各持常量。

## 81. 反 AI-Slop 布局规则【✅】

禁止：所有页都是标题+3 卡片（无卡片化默认）；所有内容卡片化（§46）；无意义
居中；每页完全对称；每页都 50/50（7+5/6+6 按内容选）；任意圆角矩形墙；每个
区域加边框；纯装饰连接线（§47）；无语义图标墙（无图标系统）；为填满页面消灭
留白（§24）。

## 82. 合法例外【✅】

允许极端留白/非对称/大图压版/Overlap/Full bleed/单句占页/非网格装饰，但必须
意图明确、信息清楚、可读、不违反 Hard Constraints——statement 页单句占页是
设计而非空页（密度带提示会解释）。

## 83. Benchmark【部分 ✅】

固定测试集覆盖：Cover/Text/Text+Image/Comparison/Timeline/Chart/长中文/长
英文/中英混排/Image-heavy/Data-heavy —— `dev-tools/stress.spec.json` 21 页
真实形状（长标题/密页/疏页/全部版式）+ demo。缺：Table/Architecture/
Dashboard 版式。

## 84. Benchmark 指标【部分 ✅】

已记录（测试形态）：hard fail rate（每次跑套件）、overflow/overlap（check
阻塞）、render 时间。未记录：average layout score（无分数引擎）、repair
iterations、variant diversity、repetition rate、human rating。

## 85. 最终规则【✅ 逐条在文内】

LLM 不写坐标（§0）；页型与族分离（§14）；Region 先于组件（§7）；网格/间距/
几何单一来源（§79）；所有间距来自令牌（§9）；层级显式 priority 化（§19）；
每页最多一个主要焦点（§21）；**留白是结构不是剩余空间**（§24）；变体必须有
候选和实测（§17-18 约定）；Hard 失败不得导出（§35+deliver 中止）；Soft 用
评分不宜全阻塞（§36）；Content Fit 不得第一步缩字号（§28）；Repair 必须
patch 不重生成（§52）；坐标只在 Resolved 层（§50-51）；Chart/Diagram 内部
归各自引擎（§32-33）；Style 管性格不管几何（§43）；Deck 级查节奏（§40 约定）；
测量渲染同一套 Token（§80）；复杂布局提供安全 fallback（fit 兜底）。最终
目标不是"把内容塞下"，而是**清晰结构、正确关系、明确焦点、稳定可读**。

## 86. 推荐运行流程【✅ 对应】

Slide Content → Page Planner → Layout Intent →（Family/Variants 约定期）→
Region/Grid+Tokens → Resolve（render）→ Browser Measurement（measure）→
Hard Check（check）→（Score 约定期）→ Repair（人改 spec）→ Resolve Again
→ Resolved Slide（DOM）→ Renderer → Visual QA。九站总图见 `pipeline.md`。

## 87. 一句话定义【✅】

优秀的 AI PPT 布局系统，不是维护更多模板，而是把页面语义转换成有限的 Layout
Family 与 Variant，再用 Grid、Region、Spacing、Priority、Constraint、
Measurement、Scoring 和 Repair 共同求出稳定、清晰且有设计感的最终几何。
本仓库已兑现：Grid/Region 语义/Spacing/Priority 尺/Constraint（硬+软）/
Measurement；Family×Variant 与 Scoring 在路线图上（见下）。

---

## 附录 A：落地阶段记录（实测数字）

+ **阶段 1**（✅）：文本预算 + 视觉焦点 + 密度三把尺（hierarchy.py，提示级）；
  修复顺序写进报错文本。
+ **阶段 2**（✅）：`grid.py` 唯一几何来源；12 列 84/24/97.33；间距 ramp +
  语义档 + 关系规则；`--sp-*` 注入；时间线宽从网格算；锚点对齐检查（左缘
  7 任意值 → 全落列）；subtitle==bullet 同级碰撞修复 + style.py 校验。
+ **阶段 3**（路线图）：版式族 × 变体表（§15-18/§57-59）+ `bullet_tier`
  退位（换变体/拆页优先，缩字号最后——现在它是兜底不是第一手段）。
+ **阶段 4**（路线图）：Shape 8 参数（§44）+ Layout Score/Repair 引擎
  （§37-38/§52-54）+ skin 残余手写间距清零。

## 附录 B：参考标准清单（要深入时看这些）

| 模块 | 主参考 | 具体借什么 |
| --- | --- | --- |
| 布局 | Fluent 2 Layout + Figma Auto Layout | 12 列 / 4px 基准 / 五件套；父容器 padding/gap/direction，子元素自动重排 |
| 信息层级 | Fluent Typography + IBCS Message | 阶梯是层级不是"重要就放大"；图表标题写结论 |
| 留白 | Fluent Spacing + Auto Layout | ramp 只许取档；间距表达关系（越近越相关） |
| 图形语言 | Design Tokens（Fluent/Atlassian） | Global→Alias；形状可替换而布局逻辑不变 |
| 图表 | IBCS 2.0 + ISO 24896:2026 + AntV | 时间横向/结构纵向；去图例去网格；语义配色 |
