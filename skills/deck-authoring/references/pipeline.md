# 总链路：从原始材料到一个好 PPT

这一篇回答一个问题：**所有层怎么串起来**。每层各自的规则在各自的 reference 里，
这里是"哪一站、跑哪个脚本、产物是什么、过不了会怎样"。

## 一张图

```text
原始材料（文档 / 脑子 / 口述）
   │   AI 按 Schema 写三份规划 JSON（plan.py 校验，不替你生成）
   ▼
content.json ──── ① plan.py --check ── 内容理解
storyline.json ── ② plan.py --check ── 叙事骨架
pageplan.json ─── ③ plan.py --check ── 页规划
   │        plan.py --to-spec（确定性桥）
   ▼
deck.spec.json ── ④ validate_spec.py ── Slide DSL（封闭字段集）
   │
   │        image_source.py --brief ── ⑤ 图像契约（人出图）
   │              ↓ 人 / 外部图像模型
   │        image_source.py --check ── ⑥ 验图
   ▼
   ────────── render.py ──────────── ⑦ 渲染（风格+品牌+字体+图表+网格解析进产物）
   │        check.py ── ⑧ 视觉 QA
   ▼
deliver.py / pdf.py / pptx_native.py / animate.py ── ⑨ 交付
                                              PDF / PPTX / PNG / MP4 / GIF
```

## 每一站：入口、出口、谁拦你

| 站 | 产物 | 跑什么 | **阻塞**（不过就停） | 提示（开口但不拦） |
| --- | --- | --- | --- | --- |
| ① 内容理解 | `content.json` | `plan.py --check` | facts 空；悬空 `evidence_refs`；`source_type`/fact `type` 不在封闭集；**缺 `coreThesis`**；brief 给了却缺 `desiredAction/desiredBelief` 或枚举非法；claim 的 `derivedFrom` 悬空；message 的 `claimId` 悬空 | 高重要性只靠推断支撑；变化词没数字（"全面提升"）；两条 message 是同一句话；没有 brief |
| ② 叙事骨架 | `storyline.json` | `plan.py --check` | archetype 不在十个预定义骨架里；beats 乱序（可跳不可乱）；角色不属于骨架；sections 页数之和 ≠ `target_slide_count`；权重和 ≠ 1 | — |
| ③ 页规划 | `pageplan.json` | `plan.py --check` | 页型不在表里；复杂度 ≥0.70 未标 `split`；页数不对齐 storyline 配额 | 标了 split 但复杂度没到（拆太碎） |
| ④ Slide DSL | `deck.spec.json` | `plan.py --to-spec` + `validate_spec.py` | 封闭字段集；版式 / colorSet 不认识；**页没有 message**（to_spec 报错）；图表页没数据；图页没 image | 字体回退；没封面 |
| ⑤ 图像契约 | `image-brief.md` + 占位图 | `image_source.py --brief` | —（出合同） | 零插槽时建议哪几页该有图 |
| ⑥ 验图 | 真图（spec 同目录） | `image_source.py --check` | 缺文件 / 宽度不足 / 比例不对 / 同名重复 | — |
| ⑦ 渲染 | `deck.html` | `render.py` | （渲染即崩：缺图 KeyError 等都在 ④⑤⑥ 拦住了） | — |
| ⑧ 视觉 QA | 修改后的 spec | `check.py` | 越界 / 重叠 / 溢出 / 对比度不足；content-image 没图；**图占满整页（≥60%）** | 密度 / 焦点 / 层级预算 / 网格对齐；全篇 0 图 |
| ⑨ 交付 | PDF/PPTX/PNG/MP4/GIF | `deliver.py` 等 | 字体嵌入超限（建议改 PDF） | 各格式的接收方须知（见 delivery-formats.md） |

**原则：客观规则阻塞，上下文规则提示**——对比度、结构声明 vs 实测、越界重叠是客观的；
密度合不合适、novelty 高不高是上下文的，提示太多会让人全部忽略。

## 自由度表：越靠近渲染，AI 越不许自由发挥

| 层 | 谁决定 | AI 自由度 | 程序确定性 |
| --- | --- | --- | --- |
| 内容理解 | 人 + AI | 中 | Schema + 引用完整 + 事实/推断分离（`plan.py`） |
| Storyline | 人 + AI | 中 | 十个骨架 + 配额自洽（`plan.py`） |
| Page Planner | AI | 低~中 | 复杂度评分 + 页型查表（`plan.py`） |
| Slide DSL | AI | 很低 | 封闭字段集（`validate_spec.py`） |
| 布局 | **程序** | 0 | 网格 + 间距令牌（`grid.py`，坐标唯一来源） |
| 颜色 | **程序** | 0 | OKLCH 角色 + 结构声明（`palette.py`） |
| 图表 | AI 选意图 | 低 | 意图→类型查表 + 手写 SVG（`chart.py`） |
| 字体 | 人 + 映射表 | 低 | 126 库 + 风格映射 + 严格 A 级（`fonts.py`） |
| 品牌 | 人 | 0 | 字段封闭 + 局部亮度选 logo 正反白（`brand.py`） |
| 渲染 / 动画 | **程序** | 0 | `paint(si,t)` 纯函数，同 t 同 seed 必同帧 |

"AI 只选参数，程序负责执行"——这是整条链不出 slop 的根：**LLM 写内容与选择，
几何、颜色、字体、帧全部是确定性计算**。

## 做一个好 PPT，每站问的问题

- ① 我们**知道**什么？哪些是事实、哪些是推断？观众看完要**做什么**
  （desiredAction）？一句话论断（coreThesis）是什么？
- ② 按什么顺序让他**相信**？骨架（问题→方案 / SCR / 复盘…）配目的吗？页数配额分给谁？
- ③ 这一页让观众记住的**那一句话**是什么？该用数字、图、流程还是两栏讲？
  一页塞不下就拆。
- ④ 图表先问**意图**（趋势 / 对比 / 构成），类型是查表查出来的；
  图页先有 `image` 契约。
- ⑤⑥ 图：AI 把"需要什么图"写成合同（实测几何、比例、管线提示、prompt），
  人负责生成，`--check` 验收。**图不承载信息，版面用真文字排。**
- ⑦⑧ 版面：网格对齐、留白分级、墨量预算、对比度 —— 全部**测出来**，不靠感觉。
- ⑨ 交付格式按接收方选（PDF 子集嵌入最稳；原生 PPTX 会字体替换；MP4/GIF 光栅化）。

## 完整命令序列（一个真实 deck 的走法）

```bash
S=skills/deck-authoring/scripts

# 1-3 规划层：写三份 JSON（AI 按 Schema 写），然后校验
python3 $S/plan.py --check content.json storyline.json pageplan.json

# 4 桥到 Slide DSL，过封闭字段校验
python3 $S/plan.py --to-spec pageplan.json content.json -o deck.spec.json
python3 $S/validate_spec.py deck.spec.json

# 5-6 图像契约 → 人出图 → 验收
python3 $S/image_source.py --brief deck.spec.json    # 出 image-brief.md
#    …按 brief 出图，文件放 deck.spec.json 同目录…
python3 $S/image_source.py --check deck.spec.json

# 7-8 渲染 + 视觉 QA（改 spec 重跑直到绿）
python3 $S/render.py deck.spec.json -o deck.html
python3 $S/check.py deck.spec.json deck.html

# 9 交付
python3 $S/pdf.py deck.html -o deck.pdf              # 矢量 PDF（字体子集嵌入）
python3 $S/pptx_native.py deck.spec.json -o deck.pptx # 可编辑 PPTX
python3 $S/animate.py deck.html --mp4 deck.mp4       # 逐帧 seek 的确定性视频
```

## 分层规则地图（哪份文档管哪层）

| 层 | 文档 | 落地脚本 |
| --- | --- | --- |
| 说什么 / 为什么这样说 | `content-intelligence.md`（内容智能 · v3.0） | `plan.py --check` |
| 骨架 / 配额 / 页型 / 拆页 | `planning.md` | `plan.py` |
| 版式语法 / 8 风格 | `style-architecture.md` | `render.py` / `style.py` |
| 网格 / 间距 / 层级 / 留白 | `layout-system.md` | `grid.py` / `hierarchy.py` |
| 颜色 | `color.md` | `palette.py` |
| 字体 | `fonts.md` | `fonts.py` |
| 图表 | `charts.md` | `chart.py` |
| 图像契约 | `images.md` | `image_source.py` |
| 品牌 / 资产协议 | `brand-assets.md`（v2.0） | `brand.py` |
| 动画 | `animation.md` | `render.py` 时间轴 + `animate.py` |
| 交付格式 | `delivery-formats.md` | `deliver.py` 等 |
| 校验哲学 | `validation.md` | `check.py` |

## 反悔成本（为什么按这个顺序走）

改 spec 的标题 = 30 秒；改完 ④ 之后每往下一步，反悔成本翻倍：⑦ 之后改文案要重渲染，
⑨ 之后改版面要重出全部交付物。所以**所有内容层的决定（①②③）必须在 ④ 之前做完**，
图像契约（⑤⑥）在渲染前验收，视觉 QA（⑧）在交付前清零。这不是官僚流程，是
把"改东西"最便宜的位置留给最容易改错的那类决定。
