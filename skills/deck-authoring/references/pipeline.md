# AI PPT 总编排与交付协议（v1.0 Highest-Level Final 全文落地）

定位：整个 AI Presentation Design Engine 的**最高层总规则**。适用 PPTX / HTML Deck /
PDF / PNG / MP4 / GIF。统一规定从原始材料到最终交付物的完整链路、每层职责、
数据契约、质量门、修复闭环、可复现规则、缓存失效规则和交付验证规则。本篇只定义
"全局怎么串起来"；各模块细节在对应规则文件（§55 的映射表）。每节标落地状态：
【✅ 已实现】【约定=规则在、机制未接】。

> 三处架构口径（全文通用）：
> **① Resolved 层**：规范的 `resolved.deck.json` 在本仓库 = 渲染后的 DOM +
> `measure.py` 实测矩形（浏览器即 Layout Resolver；语义层 spec 无坐标，几何层
> 是活页面）——详见 layout-system.md 顶部注。
> **② 脚本名**：规范要求最高层协议不绑脚本名（§48）；本仓库的 references 是
> **实现伴生文档**，点名 `render.py`/`deck.py`/`check.py` 正是"规则↔实现"的对照表，
> 这是落地文档的职责，不是违规。

## 0. 最高原则

### 0.1 语义与执行分离【✅】

AI 决定：内容语义、页面意图、风格意图、视觉需求、动画意图，以及**全部
审美声明**（色板名 / 布局 / 档位 / 图形类型 —— 作者写、脚本只验收）。
程序决定：坐标、字号档对应的取值、色值推导、字体文件、图片文件、图表几何、
动画时间线、最终帧、导出格式。一句话：**AI 只做语义决策与受控选择，程序负责
确定性执行。**
落地：spec 只有语义字段（封闭集），几何/字体/帧全部由脚本派生；色值来自
风格数据的 `colorSets`，spec 只写色板名（§11/§17）。

### 0.2 越靠近渲染，AI 自由度越低【✅】

内容理解 中 → Storyline 中 → Page Planner 低~中 → Slide DSL 很低 →
Compile/Resolve 极低 → Layout 0 → Color 0 → Asset 0 → Render 0 → Export 0。
完整 13 行对照表见 §51。

### 0.3 所有模块必须有边界【✅】

禁止：Renderer 临时决定颜色；Layout Engine 临时改文案；Image Pipeline 临时改变
Page Message；Motion Engine 改变信息层级；Brand 覆盖整个 Style；Content Engine
直接输出 x/y；Chart Engine 修改事实数据；Export 层重新排版。落地：各引擎的
边界表在 layout-system.md §72-78；渲染分支里没有第二套几何、没有文案改写、
没有颜色决策。

## 1. 总体链路（14 站 → 本仓库 9 站）【✅ 结构对应】

```text
原始材料 → ①Brief → ②Content → ③Storyline → ④PagePlanning → ⑤ContentQA
  → ⑥SlideDSL ──┬─ ⑦AssetRequests      Style/Brand/Tokens
                └─ 外部生成/提供素材 → ⑧AssetQA
  → ⑨Compile/Resolve（Theme/Typography/Asset/Chart/Diagram/Layout/Motion）
  → resolved（本仓库=DOM） → ⑩LayoutQA → ⑪Renderer → ⑫VisualQA
  → 不通过→Repair→回 ⑨ ／ 通过 → ⑬Deliver → ⑭ExportQA → Final Artifacts
```

本仓库的站合并：①-⑤ = 作者/AI 自审（规则见 §3-§9）；⑥ = `validate_spec.py`
（字段集封闭；spec 由作者写）；⑦⑧ = `image_source.py --brief/--check`；⑨ =
`render.py`（**决策与绘制已分家**：内部调 `deck.py` 的 `compile_spec` 出
resolved.deck.json——职责是**合并作者声明 + 解析资产 + 留痕**：色板名/档位/布局/
图形类型都是 spec 或风格数据声明的（compile 一概不推断），它把品牌并入、assetId
解析成路径、算错位与时间轴，并把每条决策记进 trace；`render_resolved` 只画不想。
要单独拿中间产物：`render.py spec.json -o out.html --resolved resolved.deck.json
--trace`；`render(spec)` 仍是一步到位，字节级不变）；⑩⑫ = `check.py`
（Layout QA 与 Visual QA 都在实测 DOM 上做，因为 resolved 层就是 DOM）；
⑬⑭ = 各导出脚本（pdf / pptx_native / shots / animate）+ 各导出自己的回读验证
（交付按 delivery-formats.md 手工逐条跑）。

## 2. 五类核心中间产物

| 类 | 规范 | 本仓库 | 状态 |
| --- | --- | --- | --- |
| 2.1 Planning | content/storyline/pageplan.json | 同名三份（自查） | 约定 |
| 2.2 Slide DSL | deck.spec.json 无坐标 | 同名（`COORD_FIELDS` 判错） | ✅ |
| 2.3 Asset Contracts | assets/requests/*.json + manifest | `image-brief.md`（结构化小节，人直接读） | ✅ 等价形 |
| 2.4 Resolved Deck | resolved.deck.json | 渲染后 DOM + measure 实测 | ✅ 架构差异（顶部注①） |
| 2.5 Build Manifest | build.manifest.json（hashes/版本） | `__deck_manifest` 内嵌产物（元素 id/slide/role/text/字号/图表数据）；hashes 与版本号未记 | 部分 |

"知道什么/为什么讲/按什么顺序讲/每页讲什么"——前四问由 2.1 回答；
**resolved 是最重要的可调试中间层**：改一处、渲一次、量回来，全部可对账。

## 3. Presentation Brief【✅】

规划前必须有 Brief（purpose/audience/delivery/targetSlides/durationMinutes/
desiredAction/desiredBelief）。最重要的是 **desiredAction**；推不出至少
desiredBelief。落地（作者/AI 自审）：brief 给了却缺
desiredAction/desiredBelief = 阻塞；枚举封闭；缺席 = 提示。

## 4. Content Understanding【✅】

只做知识结构化：facts/metrics/entities/events/problems/causes/solutions/
results/risks/evidence/relationships；不得排版、选色、选字体、写坐标、选动画。
**所有事实必须保留来源**。落地：content-intelligence.md §8 封闭输出集。

## 5. Source Traceability【✅】

original / derived(inferred) / generated 三分；**generated 不得伪装为事实**。
`source_type` 封闭集=阻塞；高重要性结论只靠 inferred 支撑=提示。

## 6. Core Thesis【✅】

每 deck 唯一 Core Thesis：一句话可表达、支撑 desiredAction、可被 Evidence
支撑、能统领全篇。**没有 Core Thesis = Content QA 阻塞**（作者/AI 自审）。

## 7. Storyline【✅】

让观众按什么顺序相信；从有限 Archetype 选（五个规范骨架 ⊂ 本仓库十个，
多出 overview_detail/product/incident/tech_proposal/project_report）；可组合
最多两种主骨架。乱序 = 阻塞（人审）。

## 8. Page Planning【✅】

每页明确 purpose/message/claim/evidence/semanticRelation/visualRequirement/
contentBudget（由 message_ref+页型+数据承载）；**一页只允许一个主要
Takeaway，多事实必须支撑同一个**。页无 message = 内容层违规（§9）。

## 9. Content QA Gate【✅】

Slide DSL 之前必须过：Thesis/Evidence Coverage/Unsupported Claim/Narrative
Gap/Redundancy/Audience Fit/One Takeaway/Traceability/Density Risk/Relevance
（人/AI 自审）。**JSON 合法 ≠ 内容
优秀——Schema Validation 与 Semantic QA 必须分开**：本仓库物理上只剩
`validate_spec.py` 这一个程序，Semantic QA 由人/AI 自审。

## 10. QA 等级（四级）【✅ 等价映射】

ERROR=阻塞（退出≠0：数据冲突/悬空引用/缺素材/越界/重叠/导出打不开）；
WARNING+SUGGESTION=提示流（过密/logo 缺 inverse/重复布局/低清图/0 图建议）；
INFO（记录系统决策）= manifest 承担元素级事实 + `render.py --trace` 的 Resolver
决策（§26）；其余 Resolver（时间轴/图表）的决策日志未系统化【约定】。
每门都有 errors/warnings（§52）。

## 11. Slide DSL【✅】

语义层不是几何层。允许 pageType/layoutIntent/regions/components/priority/
assetId/chartIntent/motionIntent/styleRef/brandRef；**禁止 x/y/w/h/dx/dy/
rotation/任意字号/任意 hex** —— `validate_spec.py` 的封闭字段集 + COORD_FIELDS。

两类声明**必写**（都是内容决策，脚本不替作者选）：`colorSet`（具名 ——
缺失或 `"auto"` = MISSING_COLOR_SET）与图表页的 `chart`（八类图形，缺失或
未知 = 拦）。可选声明：`layout`（只 content-image / two-column 页可写；非空
字符串，`"auto"` = BAD_LAYOUT；不写走缺省结构布局）、`titleTier` /
`bulletTier`（不写取风格缺省）、`intent`（**只作语义标注**，不再决定图形）。

## 12. Asset Pipeline【✅ 简化形】

所有图/截图/品牌素材进统一管线；推荐目录的对应：spec 同目录（交付整体拷走
不断链），图像合同（`--brief` 产出的 image-brief 文件，非仓库文档）即
requests，`brands/` 即官方素材——对照表见 brand-assets.md §25。

## 13. Image Request【✅】

先知道布局需求再生成 Prompt（Page Plan → Layout Intent → Role/Aspect/Focal/
Negative Space → Prompt Builder → 合同 → 外部生成）。**禁止先生成图再想怎么
塞**。落地：`--brief` 从渲染后实测插槽几何反推。

## 14. Asset Resolver【✅】

assetId → 实际文件；优先级 manifest.selected → exact generated → provided →
brand asset → fallback（本仓库：spec image 字段精确名 → 同目录 → brands/）。
**禁止缺图偷偷联网找**——结构上没有这条路径。

## 15. Asset QA【✅ 子集】

查文件存在/分辨率/宽高比/重复（`--check` 阻塞）；解码深度/alpha/watermark/
品牌冲突=抽帧人审（brand-assets §32 的诚实清单）。required 缺失 = ERROR。

## 16. Brand / Style / Theme 关系【✅】

Brand=是谁，Style=怎么表达，Theme Resolver=怎么融合。禁止 Brand Palette
直接覆盖 Style Palette——本仓库是字段级并入（同名赢、不删原有），三层模型
见 brand-assets §5。

## 17. Theme Resolver【✅ 等价】

输入 Brand Identity + Style 色板（`colorSets`，由 spec **显式具名** `colorSet`
选定，v3 无 auto 派生/无按语义推方向）→ 合并出 Resolved 色板表；**Renderer
不得重新选颜色**（渲染分支只读 tokens）。

## 18. Typography Resolver【✅ 等价】

Brand 字体政策 + Style 字栈 → `merge_fonts` 整体替换或保持；含字体文件
（@font-face 指本地文件）、role 映射、type 阶梯、fallback（fonts.py 的
approved→system 链）；**Renderer 不得临时换字体**。

## 19. Chart Resolver【✅】

输入 图形类型（`chart`，spec 必写的八类之一）/ Intent（可选语义标注）/Data/
Message/Emphasis/Style/Theme → Resolved Chart Spec（本仓库 = AntV G2 的 chart
spec，`render.chart_g2_spec` 产出，vendor 锁版本内联、animation 关死保确定性；
pptx_native 的原生图表是第二种执行器）。**总链路不绑定具体技术实现** ✓。

## 20. Diagram Resolver【部分 ✅】

独立于 Chart；页面 Layout 只管 Container，内部自算 Node/Edge。落地：timeline
容器宽从网格算、节点自管；独立 diagram 引擎未建（页型表原也没有 architecture，
该表 v4 随 plan.py 退役；映射过去是死路——见 planning.md 未做清单）。

## 21. Layout Resolver【✅】

输入 Page Type/Layout Intent/Content Budget/Components/Grid/Spacing/
Typography/Assets → Resolved Geometry（grid.py + render 分支 + CSS）。
**LLM 不写坐标**（§0.1）。

## 22. Layout Candidate【约定】

生成 2~4 个合法版面候选（规范原词 Variant，本仓库 spec 侧统一叫 `layout`）
→ 批量测量 → Hard Check → Score → 选最佳。**脚本不选版式** —— `layout`
由作者声明（§11）。"装不装得下"由 `measure.py` 实测（越界/裁切）在
`check.py` 里定死。

## 23. Geometry Single Source of Truth【✅】

canvas/safe area/grid/margin/gutter/footer zone/logo zone/spacing tokens
全部出自 `grid.py`。**禁止 render 一套、check 一套、pptx 又一套**——本仓库
栽过（824 vs 838 漂 14px），统一后再没漂。

## 24. Motion Resolver【✅】

输入 Page Type/Motion Intent/Style Motion Profile/Hierarchy/Layout Direction/
Effect Registry/Motion Creativity → Resolved Timeline（`timeline()` + 编排表

+ preset 查表）。**same t + same seed = same frame**（有测试钉）。

## 25. Compile / Resolve 阶段【✅ 等价】

系统核心：语义 DSL 编译为可直接渲染的 Resolved Deck，含 resolver decisions/
fallback decisions/warnings/geometry/theme/typography/assets/charts/motion。
本仓库 = `deck.py` 的 `compile_spec` 把语义 spec 编译成 `resolved.deck.json`
（v1：内容与决策合并的自足层——`resolved = read_json(...); html = render(resolved)`），
再由 `render_resolved` 直渲。render 入口内置编译（要中间产物用
`render.py … --resolved resolved.deck.json`）；**决策 trace 已系统化**（§26）。

## 26. Decision Trace【约定】

每个 Resolver 的关键决策可追踪（`{"decision":"split_40_60","reason":[…]}`
式）。现状：决策理由写在代码注释与各规则文档（"为什么这样设计"人可查）；
已落：`render.py --trace` 输出每条决策与理由（品牌并入 / colorSet /
assetId→路径 / **作者声明的**档位与布局 / logo 选版）；消费者是人和 check
门禁（条目多且未声明 bulletTier 时在门禁处再响一声）。

## 27. Layout QA【✅】

Resolved 后先做：Hard = bounds/overlap/text overflow/min font/logo collision/
image distortion/chart clipping/required region missing；Soft = grid/hierarchy/
whitespace/balance/density/repetition/focal clarity。`check.py`（硬，阻塞；软项并入
其提示流）。原 `hierarchy.py` 的层级三条（文本预算/焦点/密度）v4 随脚本退役。

## 28. Renderer【✅】

**只画，不想。** 输入 resolved（DOM 意图 + tokens），输出 HTML/PPTX 原语/
PDF。不应改颜色、改字体、换图片、换 Layout、改文案、选 Chart Type、选
Motion Effect——渲染分支里这些一个都没有。

## 29. Visual QA【✅】

真实视觉检查：拥堵/焦点/留白/对齐真实成立/图文冲突/图表过小/模板化/失衡/
AI-slop 特征/跨页一致。落地：Deterministic QA = `check.py` 实测（真浏览器量）；
Vision QA = 人（`--stills` 抽帧三看：第 0 帧干净/落定满页/末帧终态）。

## 30. Repair Loop【✅ 人在环】

QA 不是最后报错而是闭环：Resolve → Render → QA → Patch → Resolve Again。
**Repair 优先输出 patch 而不是重生成整页** —— patch=人改 spec 的那几行，
重跑门（秒级）。修复决策里"删什么内容"是价值判断，人在环是刻意的。

## 31. Repair 顺序【✅ 两张表齐】

统一顺序：1 修事实/必需内容 → 2 删无关装饰 → 3 短 Copy → 4 删低优先级 →
5 调 gap → 6 调 padding → 7 调 region ratio → 8 换 `layout`（改 spec 声明的
布局）→ 9 换 Component 档 → 10 调非核心视觉 → 11 拆内容 → 12 拆页 → **13
最后才降字号 tier**。内容侧表在 content-intelligence §61/§13，布局侧 R1-R12 在
layout-system §53——第 1 条（修事实）属于内容层，其余同构。

## 32. Repair Iteration【✅ 人在环版】

max_iterations 3~5；超过应 ERROR+diagnostic、禁无限循环。落地：改 spec →
render → check 循环每轮秒级；转了几轮还在报同一错 = 停下来读 diagnostic
（check 的报错指名元素与问题），不是继续盲试。

## 33. Deliver【✅】

只在 Content QA ✓ + Asset QA ✓ + Layout/Visual QA ✓ 后执行。原 `deliver.py` 在
`check.py` 失败时**直接中止**（"把一份已知有问题的 deck 做成五种格式只是把问题
复制五份"）；该编排脚本 v4 退役，这条承诺落到交付步骤本身：Hard 失败不得导出
（§58），交付按 delivery-formats.md 手工逐条跑，任一步退出码非零即停。

## 34. Export Targets【✅】

HTML / PDF / PPTX / PNG / MP4 / GIF 六格式；各格式不同 Exporter
（pdf.py / pptx_native.py / shots.py / animate.py）但**同一 resolved**
（同一份 HTML / 同一份 spec+tokens）。

## 35. Export QA【✅】

导出成功 ≠ 交付成功。PDF：能打开（回读）+ 页数 + 尺寸 + 字体子集嵌入。
PPTX：能打开 + 页数 + 媒体完整 + 字体替换可接受（tests 回读校验）。
MP4：`ftyp` 头 + `avconvert` 回读 + 分辨率/时长 + 首/中/末帧（抽帧三看）。
GIF：`GIF89a` 头 + **总时长**（帧数会假失败——Pillow 合并相同帧是坑）。

## 36. Delivery Strategy【✅】

要编辑→原生 PPTX；要最稳视觉→PDF（子集嵌入，接收方零依赖）；网页展示→
HTML；自动播放→MP4/GIF；归档→PNG。对照表在 delivery-formats.md（实测口径）。

## 37. Decision Freeze Gates【✅ 四门齐】

Gate A Content Freeze = 作者/AI 自审（原 `plan.py --check` 全绿，v4 退役）；
Gate B Asset Freeze = `--check` 验图 + brand 加载通过；Gate C Design Freeze = `check.py` 全绿
（硬约束零错）；Gate D Delivery Freeze = 导出回读通过。上游门不过，下游
不开工（§1 的站序即门序）。

## 38. 上游修改自动失效下游【✅ 手动等价】

改 Content → 回 ① 重跑全链（改标题 30 秒）；只改一张图 → 只影响引用该
asset 的页面（HTML 全渲但秒级；效果等价于局部）。**失效规则由链路的
单向性保证**：没有跨层缓存就没有"忘了失效"这类 bug。

## 39. Cache【约定】

推荐 cache key = inputHash+styleHash+brandHash+assetHash+resolverVersion+
rendererVersion+seed。现状无显式缓存系统——**确定性使缓存成为优化而非
正确性需求**（§41 保证了同输入同输出，重算即命中）。

## 40. 局部重渲染【部分 ✅】

page-level invalidation：HTML 渲染秒级全量（等价满足）；MP4/GIF 目前全量
重录——**规范明说"若实现复杂可阶段性全量"** ✓。改第 8 页不必重渲整份的
精神已由秒级渲染承担。

## 41. Determinism【✅ 有测试钉】

same input + same version + same seed = same resolved output（时间轴两次算
必须全等、逐帧回归）；动画 same t + same seed = same frame。

## 42. 随机性【✅】

所有随机来自 seededRandom（`_rng(seed, "域", 元素)`：错位/颗粒/装饰角位全按
(seed,元素) 派生）。**禁 Math.random/Date.now/performance.now 直接影响输出**
——渲染路径纯函数；演示态墙钟只驱动"何时调 paint"不进画面。

## 43. Fallback Strategy【✅】

Font：exact → approved（严格 A 级库）→ system safe；Image：契约缺失=阻塞
（不静默换）+ 占位图给 brief 阶段；Chart：AntV G2 内联 vendor 即主路径（无第二
引擎可退；vendor 读不到 render 直接报错，页面里 G2 缺失/渲染失败 →
`data-chart-error`，由 check 实测的 chartReady 拦）；Motion：高级 preset →
基础 fadeRise → 静态满态；Layout：spec 不写 `layout` 就套该版式的缺省结构布局
（写了自造名 = 缺省结构 + `data-layout`，排法由 skin.css 写）。websockets 缺失
→ 说清代价降级，不静默变慢。

## 44. Fallback 不能静默【✅】

字体回退=提示（"声明的 X 本机不可用"）；logo 栅格化失败=明说跳过；色板不
达标=ink.py 退出 1。每个 fallback 都开口。

## 45. Single Source of Truth【✅】

Geometry=grid.py；Color Tokens=colorSets+colorStructure；Typography Tokens=
style 阶梯；Spacing=grid 令牌；Brand=brand.json；Asset 清单=spec image 字段；
Chart Data=spec data（渲染只读）；Build Manifest=内嵌 manifest。
**禁止同一事实复制到多个配置各自修改**（824/838 的教训）。

## 46. Schema Versioning【部分】

所有核心 JSON 带 schemaVersion：brand.json 有 `version`；spec 无版本字段
——由封闭校验变相承担"可检测"（字段变化被指名报出）。迁移工具未建【约定】。

## 47. Closed Schema【✅】

核心协议字段集封闭，未知字段=ERROR：`validate_spec`（spec）、`BRAND_FIELDS`
（品牌）；原 `plan.py` 的枚举集（brief/页型/source_type/骨架）v4 随脚本退役。
**避免 LLM 发明字段** ✓。

## 48. Tooling 与规则分离【✅ 见顶部注②】

规则定义 Content QA/Asset Resolver/Layout Resolver/Renderer；实现叫
`validate_spec.py`/`image_source.py`/`render.py`/`check.py`。脚本名属于实现层——
本仓库文档点名脚本是"规则↔实现对照"的落地文档职责，协议本身（本篇的规则句）
不依赖脚本名。

## 49. Registry 思路【部分 ✅】

Style Registry=styles/ 目录；Font Registry=fonts/catalog.json（126 款）；
Chart Type 由 spec 的 `chart` 字段封闭八类（原 `chart.py` 类型表 v4 退役，判据在
`validate_spec.py`）；Effect 面小无需 Registry（animation §5）。
**禁止业务逻辑硬编码数量** ✓（版式数/骨架数都在表里，代码只遍历）。

## 50. 反 AI-Slop 总规则【✅ 分层落地】

内容无结论→coreThesis 阻塞；标题+三卡片→无卡片默认；同构图→节奏检查约定中；
默认蓝紫渐变→novelty 惩罚；全元素 Fade Up→按角色 preset；圆角卡片墙→§46
容器纪律；Logo 重生成→禁止；图片承担文字→阻塞（图不载信息）；图表标题=
数据集名→消息先行；填满页面→密度带；字号硬塞→修复顺序第 13 位；页面同强度→
风格人格分档；缺素材乱找→结构上无此路径；效果堆叠→单 Signature=0；Renderer
做设计→§28。

## 51. AI 自由度总表【✅】

| 层 | AI 负责 | 程序负责 |
| --- | --- | --- |
| Brief | 理解目的与受众 | 原 `plan.py` 拦 Schema，v4 退役（人/AI 自审） |
| Content | 提炼与推理 | 原 `plan.py` 的引用校验、来源三分，v4 退役 |
| Storyline | 选择叙事 | 原 `plan.py` 的骨架表 / 配额，v4 退役 |
| Page Plan | 页面意图 | 原 `plan.py` 的合法页型 / 复杂度，v4 退役 |
| Slide DSL | 语义结构 | 封闭 Schema（`validate_spec.py`） |
| Color | 选色板（显式具名 colorSet） | 色板名解析（`render.resolve_color_set`）/ 对比度门禁（`ink.py` + `check.py` ①） |
| Typography | 字体意图 / 档位声明（titleTier·bulletTier） | 字体文件 / 档值 / 档名拼错当场报 |
| Image | 需求 / Prompt 填空 | 插槽实测 / 解析 / 验收 |
| Chart | 图形类型（chart 八类）/ Intent / Message | 编码（AntV G2）/ 类型与数据校验 |
| Diagram | 关系意图 | 节点布局 / 连接 |
| Layout | 布局声明（layout，自由字符串） | Geometry（grid）/ 词表验收 |
| Motion | Intent / Creativity | Timeline / Frame |
| Render | 无 | 100% |
| Export | 无 | 100% |

## 52. 五道 QA 门【✅】

Gate1 Content（作者/AI 自审）/ Gate2 Asset（--check）/
Gate3 Layout（check.py 硬约束）/ Gate4 Visual（check.py 实测+抽帧）/ Gate5 Export
（回读）。每门有 errors（阻塞清单）+ warnings（提示流）；score 未建【约定】；info
由 manifest 承担一部分。

## 53. Benchmark【手工】

基线集**自备**：一份 21 页左右的压测 spec（长中文 / 长英文 / 中英混排 /
Chart-heavy / Image-heavy / 全部版式）+ 一份八类图形展示面。没有回归基准
脚本：手工 render + check 看。缺：Table-heavy / Diagram-heavy 版式
（版式本身未建，建了才进基线）、五类真实场景语料。

## 54. Benchmark 指标【手工】

原 `benchmark.py` 逐 fixture 记录的指标（全实测）：check_problems
（`check.py` 的 `check()` 只返回阻塞清单，没有 notes 指标）、script_errors、
render_ms（机器相关仅参考）、字节可复现/编译确定性（§41）、逐页密度分布、
focal/budget issues、unique_kinds/max_consecutive（版式/布局多样性 /
repetition rate）。指标定义随 `benchmark.py` 退役，需要时照这份清单重写脚本；
留白项：repair iterations（Repair 引擎未建）、export 回读（测试套件盖着，慢
不进常规基线）、human rating。

## 55. 最高层目录 ↔ 本仓库映射

规范 22 份 rules/ ↔ 本仓库 references/（协议即"全文落地"系列）：
00_orchestration=本篇；01_content+02_storyline=content-intelligence+planning；
03_brand=brand-assets；04_style=style-architecture；05_color=color；
06_typography=fonts；07_image=images；08_chart=charts；09_diagram=约定（§20）；
10_shape_icon=阶段 4；11_table=约定；12_motion=animation；13_slide_dsl=
validation+style-architecture；14_component=约定；15_layout=layout-system；
16_quality+17_repair=validation+各篇 Repair 节；18_accessibility=约定；
19_delivery=delivery-formats；20_fallback=各篇 fallback 节；21_benchmark=§53。

## 56. 推荐项目目录【✅ 简化形】

规范的 planning/ + assets/ + qa/ + out/ 全目录树，本仓库简化为：spec 同目录
放图（交付整体拷走不断链）、三份规划 JSON 平铺、qa=各门的输出（退出码+清单）、
out=交付文件。目录是给单机用户的，不是给服务端的——服务端化那天再展开。

## 57. 最终运行状态机【✅ 命令即状态】

DRAFT→CONTENT_READY→CONTENT_PASS→ASSET_PENDING→ASSET_READY→RESOLVED→
LAYOUT_PASS→RENDERED→VISUAL_PASS→EXPORTED→DELIVERED；任何 ERROR→
REPAIR_REQUIRED。落地：状态由九站命令的执行序体现（跑过哪站=到哪个状态），
无持久状态对象——单机工具链的状态就是文件系统里存在什么产物。

## 58. 关键不可违反规则【✅ 逐条对照】

Content 未通过不进设计（§9 门序）✓；Required Asset 未过不进最终 Resolve
（§15+§33）✓；Slide DSL 无最终坐标（§11）✓；Renderer 不做设计决策（§28）✓；
resolved 是渲染唯一输入（§25 顶部注①的等价物）✓；Hard 失败不得交付（§33
deliver 中止）✓；fallback 可追踪（§44）✓；随机必有 seed（§42）✓；交付必过
Export QA（§35）✓；上游修改正确失效下游（§38）✓；核心状态可缓存可重放可调试
（§41+manifest）✓；核心事实 SSOT（§45）✓；高级视觉可安全降级（§43）✓；
模块支持诊断（报错指名元素/路径/期望值）✓。**系统目标不是"能生成"，而是
"稳定地产出可解释、可复现、可交付的好 PPT"** ✓。

## 59. 最终一句话定义【✅】

这套系统不是"LLM 直接做 PPT"，而是一条**受控编译链**：AI 负责理解、判断和
选择，Resolver 负责把语义编译成确定性的设计结果，Renderer 只执行，QA 与
Repair 保证质量，Export QA 保证最终交付。本仓库的兑现度见各节标记；
未兑现项都挂在路线图上（阶段 3-4）。

---

## 附：每站速查（阻塞 / 提示）与命令序列

| 站 | 产物 | 跑什么 | **阻塞** | 提示 |
| --- | --- | --- | --- | --- |
| ①-③ 规划 | 三份 JSON | 作者/AI 自审（原 `plan.py --check`，v4 退役） | 见 content-intelligence 落点表 | 推断当事实讲 / 空话无数字 / 同一句话两遍 |
| ④ DSL | deck.spec.json | `validate_spec.py` | 封闭字段 / 缺必填字段 / 图表缺类型或数据 / 图页无图 / colorSet 没具名 | 字体回退 / 没封面 |
| ⑤⑥ 图像 | brief + 真图 | `image_source --brief/--check` | 缺图 / 宽度 / 比例 / 重复 | 零插槽建议 |
| ⑦⑧ 渲染+QA | deck.html | `render.py` + `check.py` | 越界 / 重叠 / 溢出 / 对比度 / 全页图 / 图表就绪 | 字体回退 / 对齐 / 档位 / 布局轮换 |
| ⑨ 交付 | 六格式 | `pdf.py` / `pptx_native.py` / `shots.py` / `animate.py` | 规格/校验不过中止 · PDF 或原生 PPTX 导出失败 | 接收方须知 |

> ⑨ 没有"嵌入超限"这道门：唯一嵌入上限在 `fonts.py embed()` 单独内联时
> （fonts.py:474），交付链不调它。交付**手工逐步跑，任一步退出码非零即停**
> （失败点：规格 / 校验 / PDF 导出 / 原生导出）。

```bash
S=skills/deck-authoring/scripts
# ①-③ 规划由作者/AI 写三份 JSON（无脚本校验）
python3 $S/validate_spec.py deck.spec.json
python3 $S/image_source.py --brief deck.spec.json   # 人出图后：
python3 $S/image_source.py --check deck.spec.json
python3 $S/render.py deck.spec.json -o deck.html    # 加 --resolved / --trace 出中间产物
python3 $S/check.py deck.spec.json deck.html
python3 $S/pdf.py deck.html -o deck.pdf             # / shots.py / pptx_native.py / animate.py
```

**反悔成本**：改 spec 标题 30 秒；过 ④ 后每步翻倍——内容决定压在 ④ 前，
图在渲染前验收，QA 在交付前清零。这不是官僚流程，是把"改东西"最便宜的
位置留给最容易改错的那类决定。
