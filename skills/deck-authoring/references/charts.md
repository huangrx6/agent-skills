# 图表：DSL、图形类型、muted+accent、结论先行

## 三层架构（谁负责什么）

```text
AI 只写 DSL（chart / intent / message / data / series / emphasis / annotations）
        ↓
chart.py：图形类型（作者声明）+ 规则 + 确定性 SVG   ← Web / 预览 / PDF 都用它
        ↓
pptx_native.py：按类型映射成原生图表       ← 可编辑的 PPT 层
```

**为什么 Web 层是手写 SVG 而不是 G2/ECharts** —— 不是没考虑，是按本仓库的四条硬
约束选的：

1. **零依赖**（仓库的老规矩：GIF 用 Pillow、H.264 用 AVFoundation、截帧用系统
   Chrome）—— G2 minified 几百 KB，要么打进每份产物、要么走 CDN 断网即裂；
2. **自包含产物**（logo base64、字体 @font-face 本地路径）—— JS 依赖会破坏它；
3. **PDF 矢量** —— SVG 直接进 PDF 的文字与形状层；Canvas 出来是位图；
4. **确定性** —— `animate.py` 靠"同一 t 渲出同一帧"做 MP4，手写 SVG 的几何是纯函数。

DSL 的边界设计成**渲染器可替换**：`svg()` 的输入是纯数据 + 颜色，哪天要换 G2 渲染器，
把这层换掉即可，DSL 与 PPT 层都不用动。

## AI 只写这个（DSL）

```json
{
  "type": "chart",
  "chart": "bar",                      // 八类之一；**必写**（v3：图形由作者显式声明）
  "intent": "comparison",              // 想表达什么（可选语义标注，不再决定图形）
  "message": "DeepSeek 调用量领先第二名 40%",   // ← 结论，会当大标题
  "title": "模型调用量统计",              // ← 数据集名，降为小标签
  "data":  [{"label": "DeepSeek", "value": 86}, ...],
  "series": [{"name": "直连", "data": [...]}, ...],   // 多系列（line/stacked/combo）
  "emphasis": {"values": ["DeepSeek"]},               // 谁是重点
  "annotations": [{"type": "reference", "value": 80, "text": "目标 80%"}],
  "unit": "%"
}
```

散点的 `data` 项是 `{label, x, y}`（`value` 视同 `y`，向后兼容）。

```bash
python3 scripts/chart.py --demo all       # 八类各渲一个样例
python3 scripts/chart.py --explain spec.json   # 打印每页声明的图形类型
```

## 图形类型（规范第 3/16 条）：**作者声明**，脚本不推断

v3 起图形类型是**内容决策**：spec 必须写 `chart`，脚本不替你选图形。

```text
chart: "bar" | "bar-horizontal" | "line" | "area"
     | "bar-stacked" | "donut" | "scatter" | "combo"   （八类，封闭）
```

落地（`chart.py` 的 `declared_type()`）：**缺 `chart` → SystemExit**（缺哪一类
由作者定，脚本猜不了）；**`chart` 不在八类里 → SystemExit**。`--explain` 打印
每页声明的类型，并在该页没写 `message` 时点名提醒（规范第 5 条：标题应是结论）。
两道图前门在 `validate_spec.py`：缺类型报 `MISSING_CHART_TYPE`、写错报
`UNKNOWN_CHART_TYPE`（见 `validation.md`），本该在渲染之前就拦住。

历史备注：这里原有一条 `resolve_type()` / `infer_chart_type()` 的**意图推断**
（按条数/标签是否像时间/系列数分支，没写就缺省 bar）—— 已按 v3 退役：
推断等于替作者选图形。`intent`（八值：trend/ranking/comparison/composition/
correlation/progress/deviation/distribution）现在是**可选语义标注**：写了对渲染
**没有影响**，`validate_spec.py` 仍校验它属于这八值；不写也不影响图形。

## 好看的三条硬规则（与图形类型无关，仍按声明渲染）

1. **muted + 1 accent**（规范第 4 条）：给了 `emphasis` 就只有被强调的那根是
   Accent，其余降成 muted（主色向纸色褪 55%）。八根柱子八种颜色是业余的第一特征。
   **没写 emphasis 时不悄悄改观感** —— 全部主色，与从前一致。
2. **结论先行**（规范第 5 条）：`message` 当大标题（"DeepSeek 调用量领先"），
   `title` 降为小标签（数据集名）。没写 message 时维持旧行为，`--explain` 会点名。
3. **不画图例、不画坐标轴数字、不画网格线**：数值直接标在图形上（这本来就是本仓库
   的既定风格，PDF/PPTX 两侧都验证过）。折线只标**首/尾/峰**三处 —— 一排数字会把
   线埋掉。多系列的名字标在线尾，不画图例。

## 标注（规范第 12 条）

好图表与普通图表的差距多半不在图形，在标注。第一版支持三种（**封闭集**，
`type` 写集外直接 ERROR —— 与 manifest 同款纪律）：

| 类型 | 需要 | 效果 |
| --- | --- | --- |
| `reference` | `value`（+可选 `text`） | 虚线水平参考线 + 标签 |
| `callout` | `target`（data 里的标签名）+ `text` | 指向该数据点的引线 + 文字 |
| `peak` | `text`（自动找最大值） | 峰值标注 |

`target` 在 data 里找不到会**报错**（而不是默默不画）。

## 动画令牌（规范第 6~9 条）—— 数值已成文，接线在第二阶段

动画的"高级感"不在效果多，而在**克制且一致**。令牌不先定下来，每张图各写各的
731ms/1247ms，那就是"弹跳杂耍"的来源：

```python
MOTION_TOKENS = {"chart_enter": 700, "chart_stagger": 60, "highlight": 300,
                 "page_total_max": 1500, "story_total_max": 3000, ...}
```

每类图形的动画语言（第二阶段接进 `animate.py` 的时间线）：

| 图形 | 进入 | | 图形 | 进入 |
| --- | --- | --- | --- | --- |
| bar | growInY（0→高度） | | donut | sweep + 中心数字 fade |
| bar-horizontal | growInX | | scatter | scale 0.6→1 + fade |
| line / area | pathIn（左到右画） | | axis / grid / label | fade（永远不是主角） |

规范定的预算：普通进入 500~800ms、整张图 < 1.5s、storytelling 页 < 3s。
**禁止** bounce / spin / fly-in / 疯狂 zoom。

## PPT 层（`pptx_native.py`）

| DSL | PowerPoint 原生类型 |
| --- | --- |
| bar / combo | COLUMN_CLUSTERED（combo **如实降级**为柱 —— python-pptx 一个图表一个 plot，组合图是第二阶段） |
| bar-horizontal | BAR_CLUSTERED |
| line | LINE_MARKERS |
| area | AREA |
| bar-stacked | COLUMN_STACKED |
| donut | DOUGHNUT（标签用 CENTER —— OUTSIDE_END 对环图非法；没有 value_axis，访问就抛） |
| scatter | XY_SCATTER（要 `XyChartData`，不是 CategoryChartData） |

多系列会画**底部小图例**（不画分不开系列；单系列坚决不画）；系列上色用 accent 向
纸色分档褪色（与 SVG 层同一条规则，不是彩虹）。

## 第二阶段（还没做，别假装做了）

- Sankey / Treemap / Heatmap / Radar / Gauge / Waterfall / Funnel
- 组合图的原生输出（目前 combo 在 PPT 层降级为柱）
- 数据驱动动画（growInY/pathIn 接进 `animate.py` 的时间线；目前图表作为一个整体
  元素跟随页面的进场动效）
- 每根柱子单独的 `data-m`（可以逐根 stagger；这会改变现有动画测试的预期，
  所以单独一步做）
