# AI PPT 布局与视觉结构规则（全文落地）

适用：布局与页面结构层（PPT / HTML Deck / PDF / MP4 / GIF 共用）。核心目标：把
Page Planner 输出的"页面意图"稳定转换为**可测量、可约束、可评分、可修复**的页面
几何。本规则负责：布局、区域、网格、信息层级、留白、对齐、视觉平衡、版式布局、
Content Fit、评分与修复。不负责：内容事实、品牌身份、最终颜色、图片 Prompt、
图表语义选型、动画特效本身。每节标落地状态：【✅ 已实现】【约定=规则在、机制未接】。

> 架构口径：规范设想"Resolved Slide JSON"作为几何层工件；本仓库的对应物是
> **渲染后的 DOM 本身**（浏览器就是 Layout Resolver：spec 无坐标 → render.py
> 派生几何 → 真浏览器排 → `measure.py` 注入探针脚本、`--dump-dom` 把实测取回，
> 不走 CDP）。语义层（Slide DSL=spec，
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

Slide Content → Page Planner → Layout Intent → Layout Family → Layout（作者声明）
→ Region Tree → Grid/Spacing/Constraints → **Layout Resolver** →
Measurement → Hard Check → Layout Score → Repair → Resolved Slide → Renderer。
本仓库：spec → `render.py`（resolve）→ `measure.py`（实测）→ `check.py`
（硬检查 + 软提示流）；Score/Repair 引擎见 §37/§52。
布局不是脚本从候选里实测选出的 —— 作者在 spec 写 `layout`，脚本只执行与验收。

## 2. 职责边界【✅】

Content Engine 决定"说什么"（content-intelligence.md）；Page Planner 决定页面
类型/主要视觉/密度/谁最重要/语义关系（作者做）；Layout Engine 决定
放哪里、占多大、间距多少、是否换版、是否拆页（render.py + grid.py）；**Renderer
只按 Resolved 布局绘制，不重新布局**（渲染分支里没有第二套几何）。

## 3. 坐标体系【✅】

Canonical Canvas = **1600×900**（设计空间，非输出格式）；导出再映射（HTML 走
`--k` 视口缩放、PDF 矢量、PNG 按宽 ×2、PPTX 转 EMU）。内部不使用 0~1 比例做
文字/gap/padding（比例只用于 focalPoint/裁切/响应映射），baseline 与间距用
Design Unit。

## 4. Safe Area【✅】

left/right = 84、top = 132（在 96~132 建议带内）、底部页脚独立带（52+24）。
硬规则落地实况：越界=阻塞（`check.py` 实测逐元素查，标题在内）；logo 压文字
=阻塞。三条**承诺未全落地**，照实标注：正文进页脚带**无阻塞检查**、页码
**无独立保护区**（重叠类阻塞目前只有 logo 压文字这一条）——这两条在路线图上；
bounds 检查**无角色豁免**（所有可见元素一视同仁，不存在"只豁免图片"）。

## 5. Grid System【✅】

12 Columns / margin 84 / gutter 24；列宽**动态计算**
`(1600 − 2×84 − 11×24) / 12 = 97.33`（非整数是刻意的），只从 `grid.py` 取。
禁止手写列宽 —— 几何只有 `grid.py` 一个来源（第二份手写常量必然漂移）。

## 6. Grid Span【✅】

核心组件宽度取整列（`grid.py` 的 ALLOWED_SPANS：2/3/4/5/6/7/8/12）：图文页 = 7+5 列、
两栏 = 6+6 列、时间线宽度按节点数从网格算（原写死 300px，6 节点超宽 538px 靠
flex 硬扛——已改为算）。例外允许：full-bleed、editorial overlap、hero 构图、
装饰元素；核心信息组件必须能解释其网格关系（对齐检查，§12）。

## 7. Region Model【约定】

页面先分 Region 再放 Component；基础 Region：HEADER/BODY/ASIDE/FOOTER/HERO/
VISUAL/META，支持嵌套。落地形态：`grid.py` 的 `REGIONS` 常量 + HTML 结构本身
（`.pad` = HEADER+BODY、`.footrow` = FOOTER、图/图表列 = VISUAL）；**没有独立
的 region-tree JSON**——要"版式族 × 布局"（§15-18）时才需要它。

## 8. Auto Layout 参数【✅ 精神落地】

父 Region 负责 direction/padding/gap/align/justify；子组件不写坐标。落地 =
CSS flex/grid：父容器 padding/gap 全走 `--sp-*` 令牌，子元素内容变化自动重排
（父容器内容变化自动重排正是容量反馈依赖的机制，§55）。

## 9. Spacing Tokens【✅】

Global Ramp：8/12/16/24/32/48/64/96；Alias：inner 16 / item 24 / block 32 / group 48 /
section 64（+hero 96）。注入产物为 CSS 变量 `--sp-*`；壳里的 gap **全部**走令牌 —— 不出现裸数字。
（`block` 这一档是**安全盒逼出来的**：body 下 16 + caption 上 12 = 28，而 ramp 里
比 24 大的下一档是 32。少了这一档，人会去写 `--sp-block` 这种不存在的令牌
——声明被静默丢弃，间距回到 16，然后门报"太近"。）
（这条有测试守着：`test_grid.py` 扫 `SHELL_CSS`，25~64px 区间的裸间距直接判失败 ——
间距无律就是这样长出来的。）

## 10. 间距关系【✅】

inner < item < group < section；**组距 ≥ 1.5 × 条目距**（Gestalt 接近性）、
节距 ≥ 1.33 × 组距（`grid.py` 的 SECTION_RATIO）——成文进 `grid.py`，
`--json` 自检。间距必须表达关系，
不是装饰。

## 11. Style 与 Spacing【✅】

Style 不重定义任意 spacing，只允许覆盖语义档（spacingOverrides）。skin 里的
`gap` 只能引用 `--sp-*`，`gap=57` 这种手写值没有合法来源。

## 11b. 安全盒（Clearance Box）与碰撞政策【✅ layout/ 包】

页面元素除**视觉边界**外还有一个**安全盒**（四向外扩的视觉安全范围）。
两个不同视觉组的元素安全盒相交 = 按重叠处理（阻塞）—— 只查真实边界
看不见「没撞但只剩 3px」的那种挤。

数学在 `scripts/layout/model.py`（`Rect` / `Insets` / `expand_rect` /
`intersects` / `gap_between` / `required_gap`），政策在
`scripts/layout/collision.py`。判据全部来自 `measure.py` 的实测元素盒。

**五个性状分组**（同组是一个视觉整体，不互判）：

| 组 | 成员 |
| --- | --- |
| title | 标题块（title + subtitle） |
| body | 正文（bullets / 栏题） |
| visual | 视觉（chart / image / 时间线节点） |
| caption | 说明（caption / chartValue / chartLabel） |
| foot | 页脚行（foot / brandfoot / logo） |

**政策三种**：`deny`（默认，相交即违规）；`decorative`（装饰无 `data-m`、
不进测量清单，天然不参与）；`intentional`（**只有 hero**：实心反色标题条
压图是设计本身 —— `spec.layout == "hero"` 声明它）。

**豁免三条**（豁免的是「视觉整体」，不是放水）：

1. 同组成员（列表条目之间、标题块内部、页脚行内部）；
2. caption 被 visual 包含（figure 的 DOM 子节点；**全幅图包含标题不在此列**
   —— 那是压字，必须走 hero 声明）；
3. 同页 visual×caption（caption 属于 figure；图内间距由 figure 自己的
   padding 管，实测画布→说明 48px）。

**安全距离表**（px，四向外扩；需要间距 = 主导方向两侧外扩量之和）：

| 元素 | 外扩 |
| --- | --- |
| title | bottom 28 |
| subtitle | bottom 20 |
| bullet | top 20 / bottom 16 |
| chart | 四向 24 |
| image | 上 16 / 其余 24 |
| caption | 四向 12 |
| foot | top 24 |

报告必须带两个数（只说"撞了"没法修）：

```text
第 9 页 s9.chart 与 s9.caption 太近（visual×caption：需要 ≥44px，实际 24px）
```

## 11c. 标题块与装饰锚定【✅】

标题块高度是**内高的下限**（`min-height`），不是钉死的盒子：标题换行 /
换字体 / 换字号时块随内容长，皮肤锚在 `.titleblock` 上的装饰（侧条 / 下划线）
跟着真实几何走。`measure.py` 对标题元素额外输出**逐行真实矩形**
（`lineRects`，Range API）—— 行数与行高变了，装饰是否跟得上拿它验证。

## 11d. 间距治理【✅】

块与块的间距**全部由父容器（`.pad`）的邻接规则给**；组件自身零外距。
当前只有标题块带 `margin-bottom: var(--sp-section)`（64）；下方组件不写
`margin-top`（块布局的相邻外距折叠取大者，写不写结果一样，写两处必漂移）。
安全距离表的最低线（标题底 28 + 正文顶 20 = 48）由这 64 兜住。

## 11e. Repair 修复梯【✅ render --repair】

```bash
python3 scripts/render.py spec.json -o out.html --repair
```

流程：渲 → 实测 → 硬问题 → 梯子 → 再渲（≤4 轮）。触发信号只有两种**硬**问题：
竖向溢出（内容底超过正文带底）与标题横向写出列；提示级问题不进梯子。

**主权规则**：

- 只修改 spec **能表达**的字段（`bulletTier` / `titleTier`）—— 每步写进补丁
  清单，另出 `*.repaired.spec.json`：可采纳、可拒绝、可复现。不改 CSS、
  不改风格、不写运行期魔法变量。
- **作者声明过的字段一律不碰**：显式写了 `bulletTier` / `titleTier` 的页只出
  诊断（"声明过，不自动改"），决定权在作者。
- **缩字号是最后手段且只降一档一轮**：`bulletLarge → bullet → bulletSmall`，
  到最小档就停 —— 再装不下是内容问题（拆页 / 收短文案），不是字号问题。

产物：`out.html`（最后一轮即交付物）、`out.html.repair.json`
（iterations / fixed / patches / diagnostics）、`out.repaired.spec.json`（有补丁时）。
退出码：全部修好 = 0；仍有问题 = 1（不能假装修好了）。

## 12. Alignment【✅ 提示级】

对齐体检三条（提示级）：**左缘吸附**（锚点在列起点上）、**右缘在栅格缘**
（视觉容器的宽度数学 —— content-box 的 width+padding 会把右缘顶出内容界）、
**同级左缘一致**（标题与副标题共一条左缘线，差 >1px 即提示）。判据全来自
实测盒；风格有意的偏移（悬挂缩进 / 出血）走提示的豁免口径，不阻塞。

必须检查：标题/正文/卡片/图/图表/表格/题注的左缘与 baseline。落地：锚点元素
（标题、subtitle（副标题）、图、图表——`check.py` 的 anchors 表，check.py:248）
左缘必须吸附到列——提示级。锚点元素的合法左缘是这 5 个位置：
**84**（边距）、**448**（col4）、**812**（col7）、**933**（col8）、**1176**（col10）。
优先序：同 Region 左缘 > 网格列 > baseline > 光学对齐。

## 13. Optical Alignment【✅】

允许组件规则做少量视觉修正（图标超 baseline 1~3px、圆形视觉中心微移、大标题
字形边界微调）——本仓库的这类修正都在 skin.css 里**由风格作者写**，不由 LLM
生成。

## 14. Page Type 与 Layout Family 分离【 部分 ✅】

Page Type=页面语义类型，Layout Family=空间组织方式（comparison 页型 → split
族）。落地：页型→版式的映射由作者声明 `layout`（§17）。**family/layout
两级中间层未建**（§15-18；两族已带 layout 字段，全量铺开在阶段 3）。

## 15. Layout Family【✅ 第一片已落地（content-image）】

规范至少支持 single/split/stack/grid/hero/editorial/overlay/timeline/diagram/
chart/table/dashboard/full-bleed。现状：7 种 slide type（title/content-text/
content-image/two-column/timeline/chart/end）+ 自建风格。**content-image 率先
成为显式家族**：`layout` 字段进 spec（作者声明的自由字符串）；two-column
已跟上（3 个结构布局，§16）；其余 type 仍是单版式 ——
family 命名层全量铺开在路线图阶段 3。

## 16. Layout（布局）【✅ 结构布局已落地（content-image 4 + two-column 3）】

每页一个布局：spec 写 `layout`（**自由字符串**），渲染器给**结构**，皮肤/风格
负责细排。分工是"渲染器能力 + 作者自由"：

- **结构布局**是渲染器的能力清单（`render.IMAGE_LAYOUTS` /
  `render.TWO_COL_LAYOUTS`，是**能力**不是封闭枚举禁令）：
  - content-image：`visual-right`（文 7 栅 + 图 5 栅，缺省）/ `visual-left`
    （图先文后，镜像换节奏）/ `even`（6+6 均分）/ `hero`（满幅 12 栅 + 底部实心
    标题条 —— 图就是主角：无条目 648px 占整页 64%，check 的全页图禁令对它
    role-aware，因为标题/条目仍是真 DOM 文本、"信息烤进图里"的禁止不适用；
    满图是特性，不是空页）。
  - two-column：`even`（6+6 均分，缺省 —— flex 等分即 704px=span(6)，不加类，
    默认路径逐字节不变）/ `lean-left`（左 7 栅 825.33px + 右 5 栅 582.67px，左栏
    承重 —— 对照页主张在左、细节在右）/ `lean-right`（左 5 右 7，镜像）；宽度全
    由网格算（825.33+582.67+24=1432 不变）。
- **自造布局名**：spec 写任何其它字符串 → 渲染器套**缺省结构** + 加
  `data-layout="<名>"`（content-image 缺省 visual-right、two-column 缺省 even），
  排法由 skin.css 的属性选择器写。核心口径：**布局语言是作者的自由，
  脚本只提供结构与验收**，不枚举审美。

`layout` **显式声明**才进 Decision Trace（`render.py --trace` 的 layout 段，由
`deck.py` 的 `compile_spec` 产出）；自造名会在
trace 里注明"缺省结构 + data-layout，排法由 skin.css 写"。不写 `layout` 时
静默走该版式的结构缺省，不留痕。

版式字段叫 `layout`（**自由字符串**）：`variant` 不被接受（写它 = `UNKNOWN_FIELD`，
HINTS 指路 layout）、`auto` 被 `validate_spec.py` 拦（`BAD_LAYOUT`）。其余 type（时间线）
仍是隐式单版式。

## 17. 布局选择依据【✅ 作者声明】

不得随机选版式；必须考虑内容量/视觉角色/图比例/优先级/语义关系/风格/密度/
平衡/前后页节奏。口径：**这些判断是作者的内容决策，写在 spec 的
`layout` 里**。脚本不替作者选 —— 不推断、不随机、也不实测排名（§18/§57）。
不写 `layout` 就走该版式的结构缺省（content-image 缺省
visual-right、two-column 缺省 even，§16）；写自造名由 skin.css 排。
其余 type 仍页型查表（确定性，不随机）。

## 18. Layout Candidate Ranking【✅ --candidates（声明页钉死）】

页级**候选**：每页给出 **3 个结构不同**的候选 + 1 个"当前/缺省"，整份 deck 联合
择优，并输出一页**对比页**供作者挑。

```bash
# 一、出候选：实测打分 + 联合择优 + 对比页（同内容不同结构）
python3 scripts/render.py spec.json -o out.html --candidates
#    → out.compare.html（N 组 × 最多 4 页 + 选择面板）
#    → out.candidates.json（逐候选分数 / 选定 / 惩罚项 / 诊断）

# 二、在 out.compare.html 上挑，点「复制选择」得到 {"3":"hero"} 存成 picks.json

# 三、回写并渲染正式产物（产出 out.picked.spec.json）
python3 scripts/render.py spec.json -o out.html --candidates --picks picks.json

# 或：不问作者，直接采用联合择优的结果
python3 scripts/render.py spec.json -o out.html --candidates --pick
```

**边界**：只搜**未声明** `layout` 的页（content-image 5 个名字 / two-column 5 个
名字，来自渲染器能力清单）；声明过 = 钉死不搜。

**结构指纹**（`layout/fingerprint.py`）：`composition = family + 排序后的区域跨度集`。
镜像折叠成同一个构图 —— `visual-right` 与 `visual-left` 是**同一个结构**，不得占两个
候选位（摆三个近亲候选等于没给选择）。当前真构图表：

| 页型 | 结构（composition） | 名字 |
| --- | --- | --- |
| content-image | `split\|5,7` | visual-right / visual-left |
| content-image | `split\|6,6` | even |
| content-image | `split\|4,8` | visual-wide |
| content-image | `hero\|12,12` | hero |
| two-column | `columns\|6,6` | even |
| two-column | `columns\|5,7` | lean-left / lean-right |
| two-column | `columns\|4,8` | lean-hard-left / lean-hard-right |

类名 = layout 名（皮肤按名字就能选到）；`visual-left` 额外保留历史短名 `v-left`。

**打分（单页，实测驱动）**：

| 维度 | 权重 | 判据 |
| --- | --- | --- |
| 密度 | 0.30 | **区间满意度**（content-image 40~68% / two-column 45~72%），两端线性衰减 —— 越满不是越好 |
| 可读 | 0.25 | 条目换行惩罚（实测行数 − 1 每行 −0.18） |
| 视觉 | 0.25 | 视觉占比区间 [0.35, 0.60]；满幅（hero 的 1.0）在区间外 → 0 分：hero 是作者声明的设计，不是自动选优的答案 |
| 平衡 | 0.20 | 视觉质量中心偏离版心的距离（图按面积折半计质量） |

**作废**：竖向溢出 / 标题写出列 / 安全盒碰撞，任一命中即无效（不进排序）。

**deck 级联合择优**（`layout/allocation.py`）：逐页各挑各的最优会得到"每页都还行、
整份却一个版式用五遍" —— 重复是 deck 级的病，就得用 deck 级的目标函数治：

```text
score = 拟合损失×150 + 页内重复 + 跨页重复
```

| 项 | 权重 | 治什么 |
| --- | --- | --- |
| 拟合损失 | ×150 | 别为了多样性牺牲"装得下"；带 `FIT_BAND`=0.16（**接近最优即可**，否则永远锁死在逐页最优上） |
| 页内同 family / 同构图 | ×300 / ×450 | 三条候选不能是近亲 |
| 与上一页 family 重叠 | ×90 | 相邻页换构图最容易被眼睛记住 |
| 全局重复 layout / 组合 / family | ×600 / ×1400 / ×14 | 按 n(n-1)/2 增长：用得越多惩罚越陡 |

平局用 `hash_seed(seed\|页码\|组合)` 决 —— **同 seed 同输入必得同结果**（`--seed`
或 spec 的 `deck.seed`）。诊断带次数（"版式 'even' 用了 5 次"）。

**回写**：`--picks` 接受 `{页码: 候选名}`；值写 `null` / `""` / `"缺省"` = **撤掉
layout**、回到渲染缺省。坏键（非数字 / 页码越界）逐个报错，不当成静默跳过。
语义契合、风格契合不打分 —— 决定权在作者，面板与 `*.candidates.json` 只把事实摆出来。

### 写前预算（`render --contract`）

```bash
python3 scripts/render.py spec.json -o out.html --contract        # 人读
python3 scripts/render.py spec.json -o out.html --contract --json  # 程序读
```

**先读预算再写字**。修复梯里"缩字号"排在第 13 位，而"装不下"最省事的动作就是
先压字号 —— 容量必须在落笔前就拿到，不能等渲完再发现（`layout/contracts.py`）：

| 给什么 | 怎么算 |
| --- | --- |
| 区域宽度 | `grid.span(n)`（跨度的唯一来源）—— 双栏按栏跨度、图页按文字栏跨度 |
| 每行字数 | 按 CJK 全角估（1 字 ≈ 1 字号）；拉丁实际更宽裕 → **保守**估计 |
| 可用高度 | 正文带 `CONTENT_BOTTOM − CONTENT_TOP`（692px） |
| 条目缩进 | 默认 80px（常见皮肤悬挂缩进的量级，再保守一档） |

例（swiss-grid 的档位）：content-image 的 7 栅文字栏 → 条目 **≤ 8 条 × 23 字**；
`visual-wide`（4 栅）→ ≤ 8 条 × **11 字** —— 同一个内容换结构就装得下了，
这正是"先换结构、别先压字号"的依据。

**预算只是估算，不替代实测**：`check.py` 只在超出 `TOLERANCE`（15%）时开口，
提示里第一句是"改文案 / 换更宽的结构"；渲染后的越界 / 碰撞 / 死白仍是**硬门**。

## 19. Information Hierarchy【部分 ✅】

每个核心组件 priority 1..5（P1 主视觉/P2 标题结论/P3 关键证据数字/P4 支撑/
P5 来源页脚）。落地：`grid.py` 有 PRIORITY 表；量化 P 判定的三把尺（文本预算/
视觉焦点/密度）由作者声明与人审。

## 20. Priority 影响【✅ 精神落地】

Priority 影响字号 tier/字重/明度/面积/位置/留白/动画强度/突出度，**不能只靠
"字号越大越重要"**。落地：风格 type 阶梯（cover/subtitle/bullet/colTitle 分
级）+ 动画按角色分强度（title mask / body fadeRise / chrome 只淡）。同级碰撞
与倒挂的体检由作者守（相邻档 ≥1.15 倍，见 style-architecture「字号怎么定」；
色板对比度
另有 `ink.py`，§29）。

## 21. Focal Point【✅】

primary ≤1、secondary ≤2；多元素同等抢眼 → focal_conflict。判据（相对焦点
间距 ≥25% 才算明确 + ≤3 个重元素）原由 `hierarchy.py` 的 `weights()` 量化，
由作者/人审视。每页第一
焦点领先第二名 90%+（标题永远最大字、图/图表永远最大面积——不是偶然，是阶梯
的结构结果），人眼可复核。

## 22. Visual Weight【✅】

visualWeight = 面积 × 对比 × 字重 × 饱和 × 孤立度 × 语义优先。简化质量
（墨宽×高度/页面积×10）由作者估；主焦点应显著
领先（阈值 top1/top2 ≥ 1.25 → 我们用 25% 间距同义）保留为规则。

## 23. Density【✅】

density = 占用核心面积 / 安全内容面积；参考带：Minimal 35-50 / Normal 45-65 /
Information 55-75 / Dashboard 65-82。参考带是工程启发式（不是硬标准），由作者/人审。

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
要做时须重建权重输入。

## 27. Composition【约定】

symmetric/asymmetric/centered/editorial/radial/directional/layered；Style 可
偏好 composition，但内容和 Page Type 优先。现状：每套风格的构图倾向写在
风格的气质声明里（网格骨架取对称，编辑式骨架取非对称）。

## 28. Content Fit 修复顺序【✅ 顺序成文】

布局失败**禁止第一步缩字体**：1 修事实/必需内容 → 2 删无关装饰 → 3 更短
Copy → 4 删低优先级 → 5 调 gap → 6 调 padding → 7 调区域比 → 8 换 layout
→ 9 换组件档 → 10 缩非核心视觉 → 11 拆内容 → 12 拆页 → **13 最后才降字号
tier**（权威表：`pipeline.md` §31 的 13 步修复顺序，这里是同一张）。
落地：这条顺序的权威文本在 `pipeline.md` §31（原写进 `hierarchy.py` 的报错
文本）。**没有自动降档**：
缩字号完全由作者显式声明（`slide.bulletTier` / 风格
`bulletDefault`，§29）—— 脚本不再替内容悄悄缩小字。

## 29. 字号降级【✅ 作者声明】

只允许 tier down（body.lg → body.md），禁止任意压缩（32→31→29→27）。
落地：档位由**作者声明** —— 标题档 `slide.titleTier`（缺省映射在风格
`titleTiers`，再缺省 `render.TITLE_TIER`）、条目档 `slide.bulletTier`（缺省
风格 `bulletDefault`，再缺省 `"bullet"`）；`render.DEFAULT_BULLET_TIER="bullet"`，
two-column 条目档固定 `bulletSmall`（结构事实）。**没有按条数自动升降档**
）：内容多就拆页/收短或显式换小档，
不让字自己变小（§28）。风格阶梯的形状（同级/倒挂）由作者守
（色板对比度另有 `ink.py`）——没有脚本门，因为这是审美判断。

## 30. Component Constraints【约定】

minWidth/maxWidth/minHeight/aspectPolicy/maxLines/grow/shrink 每组件声明。
现状：无组件清单；等价约束散在渲染分支（时间线最小节点宽、图列宽 7 列）。
MetricCard 式声明表未建。

## 31. Image Constraints【✅】

aspect ratio（实测插槽比）/ minResolution（盒子 ×2）/ bleedAllowed / 无放大
（check **提示**）都在图像契约与 check.py；**禁止非等比拉伸、无 focal 的盲裁、
小图强放大**——放大检查是 notes 提示不是阻塞（check.py：渲染宽 > 原始宽 5%
即提示"会糊"），比例在 brief 阶段对齐。

## 32. Chart Constraints【✅】

Chart Container 负责 chart box/title box/标注区/标签安全区；**Chart Engine
不得突破 Container**（chartwrap 占内容宽 1432，壳给 `.g2` 容器 330px 高；
几何由 AntV G2 在容器内算，G2 的 autoFit 必须有这个高度才不抛错）；
**Layout 不决定 chart type**（图形类型由 spec 显式声明，见 charts.md）。

## 33. Diagram Constraints【部分 ✅】

页面布局只负责 Diagram Container，内部 node/edge/connector/间距由引擎自管，
**页面网格不强行控制每个节点**。落地：timeline 容器宽从网格算，节点内部排布
自管；独立 diagram 引擎未建（无架构图版式——页型表里就没有它）。

## 34. Table Constraints【约定】

表格过高优先拆表/分页/转附录而不是缩到不可读。现状：无 table 版式（表格数据
走 chart 或截图）；规则留给将来。

## 35. Hard Constraints【部分 ✅——四项在路线图】

失败即阻塞：out of bounds（越界，实测）✓、text clipping（溢出/容器裁切）✓、
对比度（叠印墨 vs 纸色——"unreadable min font"的对比度半边）✓、chart label
clipping（= G2 真渲染出来了 + 数据形状，见 `validation.md` 第 ⑤ 条）✓、
logo overlap（logo 压字）✓、decor overlap（墨块压文字栏）✓、unresolved asset
（图没加载/脚本报错）✓、full-page image（图盖整页，hero role-aware）✓ ——
`check.py` 阻塞 10 余条。`check.py` 失败时**不得导出**（"把已知有问题的 deck
做成五种格式只是把问题复制五份"）——这条由交付步骤守（任一步非零即停，
见 `delivery-formats.md`）。

四项**承诺未落地**（路线图，先别当已有的牙）：unreadable min font 的**最小字号**
半边、overlap（**文字互压**——重叠类阻塞目前只有 logo 压文字一条）、footer
collision（**正文进页脚带**）、impossible aspect（**比例冲突**）。另：image
excessive upscale（图放大）是 **notes 提示**不是阻塞（渲染宽 > 原始宽 5% 即提示）。

## 36. Soft Constraints【✅】

进入提示不阻塞：grid alignment / whitespace / focal clarity /
density / style consistency / decoration restraint —— `check.py` 的提示流
（`advisories()`）。层级三条（文本预算/焦点/密度）是提示，由作者自查 ——
做成阻塞的话第一份正常 deck 就被挡住，然后所有人开始忽略检查。

## 37. Layout Score【约定】

建议权重：Grid 15 / Hierarchy 15 / Whitespace 15 / Focal 10 / Balance 10 /
Density 10 / Style 10 / Readability 10 / Decoration 5，总分 100；Hard Fail →
invalid。未实现分数引擎；等价物：Hard Fail = 退出 1（invalid 的机器形态），
软项各有独立提示。可测项清单已备（见 §38 注），汇总成分数是加法。

## 38. Score Threshold【约定】

≥90 excellent / 85-89 pass / 75-84 repair recommended / <75 repair required。
未实现；阈值要等有分数引擎时才有意义（§83）。

## 39. Decoration Restraint【部分 ✅】

检查装饰面积占比/是否穿正文/假焦点/重复/匹配风格。落地：装饰压文字=阻塞；
decor 类型与角位由风格 token 限定（版心已满的版式不放装饰）；面积占比由人审。
不能只看"装饰少不少"。

## 40. Deck-level Rhythm【约定】

不能只评单页：连续同 layout 数、visual/text 节奏、full-bleed 频率、chart
连续页数、纯文字连续页数。未实现（单页检查为主）；stress deck 提供测试面。

## 41. Repetition Rule【✅ 已落地（提示级）】

同一 type+layout 连排 **n≥2** 即提示轮换（仅 content-image / two-column，
`check.LAYOUT_TYPES`；`check.py` 的 `_layout_rotation_notes`，check.py:377-402）
——比规范原案的"≤2 页后提示"开口更早；附录、数据连续比较可例外（提示本就不阻塞）。

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
focalPoint/visualWeight/whitespace）。落地：`visual`（主视觉类型）与 density
由作者写；family/composition 字段未建。

## 50. Resolved Layout【✅ 架构差异见顶部注】

只有 Resolved 层可含坐标：`{canvas, layout, regions:{x,y,w,h},
components:{…}}`。本仓库的 Resolved 层 = 渲染后的 DOM + `measure.py` 的实测
矩形（语义清单记意图、几何由测量层量回——两者对不上就是 bug）。无独立 JSON
工件；要接 Layout Score（§37）时再物化它。

## 51. Schema 分层【✅】

Slide DSL=语义层、Resolved Slide=几何层，**禁止混合**。落地：spec 字段封闭
且无坐标（COORD_FIELDS 判错）；几何只存在于渲染产物与测量结果。

## 52. Repair Engine【✅ 等价形】

Repair 不重生成整页，输出 Patch（switch_copy_level / switch_layout…）。
落地：`check.py` 的提示就是诊断（指名哪个元素、什么问题、按 §28 顺序修）。
Patch=人改 spec 的那几行，重跑门。无机器
自动改写（人在环是刻意的：修复决策里"删什么内容"是价值判断）。

## 53. Repair Priority【✅ 成文】

R1 删无关装饰 → R2 短 Copy → R3 删低优先级 → R4 调 gap → R5 调 padding →
R6 调区域比 → R7 换 layout → R8 换组件档 → R9 缩非核心视觉 → R10 拆内容
→ R11 拆页 → **R12 降字号 tier**——在统一表里这是**第 13 位**（第 1 位
"修事实/必需内容"属内容层，见 `pipeline.md` §31）。与 §28 同一张表（靠作者按序修，没有脚本门）。

## 54. Repair Loop【✅ 人在环版】

resolve → measure → check → score → repair → resolve again，最多 3~5 轮。
落地：改 spec → `render` → `check` 循环（每轮秒级）；超过几轮应停下来想
（fail with diagnostic 的精神——check 的报错就是 diagnostic）。

## 55. Fit Engine【✅】

fit 只做真实测量：text height / line count / occupied area / overflow /
image fit / chart fit；**不决定内容价值**（值不值得说是 content-intelligence
的事——元规则 14）。落地："装不装得下"由 `measure.py` 实测（越界/裁切）在 `check.py` 里定死
（§56）；候选并测见 §18/§57。

## 56. Browser Measurement【✅】

HTML 路径优先真浏览器测量：actual font metrics / wrapping / SVG bounds /
DOM rect / image natural size。落地：`measure.py` 注入探针脚本、`--dump-dom`
取回（不走 CDP，见文件头注），拿真矩形；
**字符宽度估算只能做预判**，最终判断全靠实测。

## 57. Candidate Testing【✅ --candidates（§18）】

落地：`render --candidates`（§18）—— 未声明布局的页把结构候选各渲一遍、
整渲实测（每轮套同一候选序号）、打分出表；`--pick` 才落盘。"装不装得下"
由 `measure.py` 实测在 `check.py` 里定死（§55/§56）。

## 58. Candidate Score【✅ 可测子集（§18 的表）】

只打**可测**维度（密度区间满意 / 换行 / 视觉占比区间 / 平衡），权重见 §18；
语义契合、风格契合、deck 节奏不打分 —— 表摆出来，决定权在作者。
分数的价值观显式声明：**越满不是越好**（区间满意度），满幅 hero 不加分
（那是作者声明的设计）。

## 59. Deck-level Layout Planner【约定】

页面不能完全独立选 layout；需读 previousLayout/nextIntent/sectionRole/
pageImportance，避免连续同构页。未实现（配合 §40 一起做；§41 的轮换提示
可作起点）。

## 60. Cover Layout【✅】

Cover 允许 hero/大量留白/非对称/full-bleed/overlap/editorial 构图；必须保证
标题清楚、Logo 安全、主视觉不压信息。落地：title 版式 + 品牌 logoOn=cover

- 装饰角块（不压字，阻塞检查守着）。

## 61. Statement Layout【✅】

目标只有一个：强化一个 Message；优先大标题/单数字/单焦点，避免多卡片多图表
多层 bullet。落地：无 statement 页型；要单句占页就用 `content-text` 写一条
短句（声明 `bulletTier: bulletLarge`），密度由作者掌握（§23）。

## 62. Comparison Layout【✅】

优先 split/成对卡/图表/前后对照，**必须真正表达"对照"**。落地：对照页用
`chart:bar`（含 emphasis 弱化对照）或 `two-column` 双栏。

## 63. Process Layout【✅】

优先 timeline/sequence/pipeline，必须明确方向。落地：顺序/流程页用 `timeline`，
方向=自左向右（DOM 序=阅读序）。

## 64. Architecture Layout【约定】

优先 layered/hub-spoke/左到右/matrix/cluster，页面布局优先给 Diagram 足够
面积。**渲染器没有架构图版式**：映射过去是死路（页型表里也没有它；等 diagram 引擎，
见 planning.md 的未做清单）。

## 65. Chart Layout【✅】

Chart 是 Primary Evidence 时建议占核心视觉面积 ≥50%，不被正文挤成小角落。
落地：chart 版式全宽 chartwrap（占内容宽 1432，`.g2` 容器高 330 是版心主体，
§32），标题=结论先行。

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

## 69. Overlap【部分 ✅】

只在 editorial/hero/creative/共享元素构图用；必须文字可读、层级清楚、不遮
核心信息。落地：装饰块可越安全区但压字=阻塞（墨块×文字栏）；**文字元素之间
重叠=阻塞还未实现**——重叠类阻塞目前只有 logo 压文字这一条（`check.py` 的
`_check_brand`），通用互压检查在路线图上。

## 70. Layout QA【✅】

每页硬查：bounds/overlap/text overflow/min font/image distortion/chart
clipping/logo collision/required region missing；软查：grid/hierarchy/
whitespace/focal/balance/density/repetition/style consistency/decoration
restraint。落地：`check.py`（硬，阻塞 + 软项进其提示流）；软尺由作者守。

## 71. QA 输出【✅ 等价形】

规范 `{valid, hardErrors, warnings, score, metrics}` ≈ 本仓库：退出码
（0=valid）+ 阻塞报错清单 + 提示清单；metrics 分项与汇总 score 不做（§37）。

## 72. 与 Content Rules 的边界【✅】

Content 决定 message/claim/evidence/copy/contentBudget；Layout 决定放哪里/
占多大/是否换版/是否拆页。复杂度 ≥0.70 该拆由作者判断（内容层）；装不装得下
由 `measure.py` 实测的越界/裁切判（布局层，§55）——同一张表的两侧。

## 73. 与 Typography Rules 的边界【✅】

Typography 决定 font family/type scale/line height/tracking/最小字号；
**Layout 只选 type tier，不自行造字号**（阶梯在 style.json，封闭校验）。

## 74. 与 Color Rules 的边界【✅】

Color 决定 theme/accent/surface/contrast；Layout 只读视觉权重用于焦点评分
（权重看墨量，不定义颜色）。

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
英文/中英混排/Image-heavy/Data-heavy —— 压测 21 页
真实形状（长标题/密页/疏页/全部版式）+ demo。缺：Table/Architecture/
Dashboard 版式。

## 84. Benchmark 指标【部分 ✅】

已记录（测试形态）：hard fail rate（每次跑套件）、overflow/overlap（check
阻塞）、render 时间。未记录：average layout score（无分数引擎）、repair
iterations、layout diversity、repetition rate、human rating。

## 85. 最终规则【✅ 逐条在文内】

LLM 不写坐标（§0）；页型与族分离（§14）；Region 先于组件（§7）；网格/间距/
几何单一来源（§79）；所有间距来自令牌（§9）；层级显式 priority 化（§19）；
每页最多一个主要焦点（§21）；**留白是结构不是剩余空间**（§24）；布局由
作者声明、脚本只验收（§17-18，v3）；Hard 失败不得导出（§35；由交付步骤守）；Soft 用评分不宜全阻塞（§36）；Content Fit 不得
第一步缩字号（§28）；Repair 必须 patch 不重生成（§52）；坐标只在 Resolved 层
（§50-51）；Chart/Diagram 内部归各自引擎（§32-33）；Style 管性格不管几何（§43）；
Deck 级查节奏（§40 约定）；测量渲染同一套 Token（§80）；复杂布局提供安全
fallback（不写 `layout` 就走缺省结构，§16）。最终目标
不是"把内容塞下"，而是**清晰结构、正确关系、明确焦点、稳定可读**。

## 86. 推荐运行流程【✅ 对应】

Slide Content → Page Planner → Layout Intent →（Family/Layout 约定期）→
Region/Grid+Tokens → Resolve（render）→ Browser Measurement（measure）→
Hard Check（check）→（Score 约定期）→ Repair（人改 spec）→ Resolve Again
→ Resolved Slide（DOM）→ Renderer → Visual QA。九站总图见 `pipeline.md`。

## 87. 一句话定义【✅】

优秀的 AI PPT 布局系统，不是维护更多模板，而是把页面语义转换成有限的 Layout
Family 与 Layout，再用 Grid、Region、Spacing、Priority、Constraint、
Measurement、Scoring 和 Repair 共同求出稳定、清晰且有设计感的最终几何。
本仓库已兑现：Grid/Region 语义/Spacing/Priority 尺/Constraint（硬+软）/
Measurement；Family×Layout 已落地第一片（content-image 4 + two-column 3 结构
布局），全量铺开在路线图上（见下）。v3 口径：审美决策交作者声明，脚本退到
验收器（§17-18）。

---

## 附录 A：落地阶段记录（实测数字）

- **阶段 1**（✅ 规则保留）：文本预算 + 视觉焦点 + 密度三把尺（提示级，
  作者自查）；规则文本在 §19/§21-§23，修复顺序在 §28/§53 与 pipeline §31。
- **阶段 2**（✅）：`grid.py` 唯一几何来源；12 列 84/24/97.33；间距 ramp +
  语义档 + 关系规则；`--sp-*` 注入；时间线宽从网格算；锚点对齐检查（左缘
  7 任意值 → 全落列）；subtitle==bullet 同级碰撞修复。风格契约由
  ink.py 与 check.py 覆盖。
- **阶段 3**（路线图）：版式族 × 布局表全量铺开（§15-18/§57-59；content-image/
  two-column 两片结构布局已先行落地）+ 档位由作者声明（没有自动降档：
  换布局/拆页优先，缩字号由作者显式写，脚本不再自动兜底）。
- **阶段 4**（路线图）：Shape 8 参数（§44）+ Layout Score/Repair 引擎
  （§37-38/§52-54）+ skin 残余手写间距清零。

## 附录 B：参考标准清单（要深入时看这些）

| 模块 | 主参考 | 具体借什么 |
| --- | --- | --- |
| 布局 | Fluent 2 Layout + Figma Auto Layout | 12 列 / 4px 基准 / 五件套；父容器 padding/gap/direction，子元素自动重排 |
| 信息层级 | Fluent Typography + IBCS Message | 阶梯是层级不是"重要就放大"；图表标题写结论 |
| 留白 | Fluent Spacing + Auto Layout | ramp 只许取档；间距表达关系（越近越相关） |
| 图形语言 | Design Tokens（Fluent/Atlassian） | Global→Alias；形状可替换而布局逻辑不变 |
| 图表 | IBCS 2.0 + ISO 24896:2026 + AntV | 时间横向/结构纵向；去图例去网格；语义配色 |
