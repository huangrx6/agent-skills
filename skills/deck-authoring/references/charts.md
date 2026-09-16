# 图表：DSL、图形类型、muted+accent、结论先行

## 三层架构（谁负责什么）

```text
AI 只写 DSL（chart / intent / message / data / series / emphasis / annotations）
        ↓
render.py：图形类型（作者声明）+ 规则 → AntV G2 spec   ← Web / 预览 / PDF 都用它
        ↓
pptx_native.py：按类型映射成原生图表       ← 可编辑的 PPT 层
```

**Web 层用 AntV G2 渲染**（`render.py::chart_g2_spec`，render.py:837）：
G2 是声明式图形语法，**我们只出 spec（数据 → 编码），几何由 G2 算**。
（PPTX 层走 SVG 精修，见 delivery-formats.md。）

换取成熟度付出的确定性代价，用三条守住：

- **vendor 锁版本内联进产物**：`scripts/vendor/g2-5.2.10.min.js` 整段写进 HTML
  （`G2_VENDOR`，render.py:925），离线可用、无 CDN 依赖，产物仍自包含。
- **animation 关死**：G2 spec 里 `"animation": false`（render.py:837 起）—— 同 spec
  同输出，`measure.py` / `check.py` 才有稳定 DOM 可量，`animate.py` 的逐帧才有确定性。
- **壳给容器高度**：`.chartwrap .g2{height:330px}`（render.py:360）—— G2 的 `autoFit`
  从容器取尺寸，容器没有高度会在渲染时抛错（实测）。

DSL 的边界仍设计成**渲染器可替换**：`chart_g2_spec()` 的输入是纯数据 + 颜色，
换渲染器只换这一层，DSL 与 PPT 层都不用动。

## AI 只写这个（DSL）

```json
{
  "type": "chart",
  "chart": "bar",                      // 八类之一；**必写**（图形由作者显式声明）
  "intent": "comparison",              // 想表达什么（可选语义标注，不再决定图形）
  "message": "DeepSeek 调用量领先第二名 40%",   // ← 结论，会当大标题
  "title": "模型调用量统计",              // ← 数据集名，降为小标签
  "data":  [{"label": "DeepSeek", "value": 86}, ...],
  "series": [{"name": "直连", "data": [...]}, ...],   // 多系列（line/stacked/combo）
  "emphasis": {"values": ["DeepSeek"]},               // 谁是重点
  "annotations": [{"type": "reference", "value": 80, "text": "目标 80%"}],  // 字段在 schema 里但不渲染（见下「标注」）
  "unit": "%"
}
```

散点的 `data` 项是 `{label, x, y}`（`value` 视同 `y`，向后兼容）。

渲一张图表页就是渲一份 deck（图表没有单独的 CLI）：

```bash
python3 scripts/render.py your.spec.json -o out.html   # 图表页在产物里由 G2 现渲染
python3 scripts/check.py your.spec.json out.html       # 图表门：G2 就绪 + 数据形状
```

## 图形类型（规范第 3/16 条）：**作者声明**，脚本不推断

图形类型是**内容决策**：spec 必须写 `chart`，脚本不替你选图形。

```text
chart: "bar" | "bar-horizontal" | "line" | "area"
     | "bar-stacked" | "donut" | "scatter" | "combo"   （八类，封闭）
```

落地（`render.py::chart_declared_type`，render.py:785）：**缺 `chart` → SystemExit**
（缺哪一类由作者定，脚本猜不了）；**`chart` 不在八类里 → SystemExit**。
两道图前门在 `validate_spec.py`：缺类型报 `MISSING_CHART_TYPE`、写错报
`UNKNOWN_CHART_TYPE`（见 `validation.md`），本该在渲染之前就拦住。

**没有意图推断**（不按条数/标签/系列数猜图形、不缺省 bar）：
推断等于替作者选图形。`intent`（八值：trend/ranking/comparison/composition/
correlation/progress/deviation/distribution）现在是**可选语义标注**：写了对渲染
**没有影响**，`validate_spec.py` 仍校验它属于这八值；不写也不影响图形。

## 好看的三条硬规则（与图形类型无关，仍按声明渲染）

1. **muted + 1 accent**（规范第 4 条）：给了 `emphasis` 就只有被强调的那根是
   Accent，其余降成 muted（主色向纸色褪 55%）。八根柱子八种颜色是业余的第一特征。
   **没写 emphasis 时不悄悄改观感** —— 全部走主色，观感不变。
2. **结论先行**（规范第 5 条）：`message` 当大标题（"DeepSeek 调用量领先"），
   `title` 降为小标签（数据集名）（render.py:1252-1258）。没写 message 时维持旧行为。
3. **图形上只标数值，不画坐标系杂物**：数值直接标在图形上（这本来就是本仓库
   的既定风格，PDF/PPTX 两侧都验证过）—— 具体落点见下，都是 `chart_g2_spec`
   （render.py:837 起）里显式写下的编码：
   - 柱图（含横柱）：每根标数值（`labels` position outside）；
   - 折线 / 面积：只标**最后一个点**（`selector: last`）—— 一排数字会把线埋掉；
   - 散点 / 堆叠 / 组合：当前不标数值；
   - 坐标轴**标题**在折线 / 面积 / 散点 / 堆叠 / 组合上关掉（`axis.*.title:false`），
     环图整条轴关掉（`axis:false`）；
   - 环图例外地画**右侧颜色图例**（扇区名字必须能对上），其余图形不画图例。

   坐标系里的其它东西**也从 token 来，不跟 G2 主题默认走**（深底风格里默认轴文字
   直接看不见）。每个图的 `axis` 都显式写：标签色 = `text`，轴线/刻度线 = muted，
   网格线 = muted 虚线、柱图 x 轴不画网格；排印三层全部注入 —— 轴标签（色/字号/
   字体）、数值标签（字号/字体）、环图图例文字（色/字号/字体）：
   - 字号取 `type.chartLabel`（轴与图例）、`type.chartValue`（数值标签）；
   - 字体取风格的正文栈（`fonts.body`）—— **图表不是版面飞地**。
   键名是 `labelFontFamily` / `itemLabelFontFamily`：这两个字符串在 G2 5.2.10 包里
   搜不到（运行期按「部件 + 通用样式属性」拼出来的），但实测有效 —— 场景图里能读到
   注入值，且画布像素随之改变。

   柱形圆角**不做**：像素级实测 `radius` / `cornerRadius` / `radiusTopLeft…` 四组在
   G2 5.2.10 的 interval 上全部被忽略（画布哈希与基线全等）。想要圆角柱只能绕开
   spec 自绘 —— 不值得：方柱是这套版面的既有语言。

## 标注（规范第 12 条）—— 不渲染

好图表与普通图表的差距多半不在图形，在标注 —— 规则成立，但**当前渲染器不画
标注**：`annotations` 字段在封闭 schema 里（`validate_spec.py` 不拦），渲染器
**不消费它** —— 写了不报错，也不会有标注。

现在图表上有的标注是 G2 自带的：**数值标签**（柱 / 折线末端，见上「好看的三条硬
规则」第 3 条）与**环图的右侧颜色图例**。要恢复 reference / callout / peak，
需要把 `annotations` 翻译成 G2 的 mark / annotation —— 记在文末「第二阶段」。

## 图表动画（规范第 6~9 条）—— 关死

动画的"高级感"不在效果多，而在**克制且一致**。**图表动画整体关死**：G2 spec 里
`"animation": false`（保确定性）—— 图表在产物里是**一次画完的静态图**，
不逐柱生长、不逐线描画；图表页的动效只有容器入场（见 animation.md）。

所以在 MP4/GIF 里，图表页只有**页面级**的进入动效：图表容器跟随页面进场淡入 +
微升（见 `animation.md` 的角色表），容器里的图本身不动。规范定的预算
（普通进入 500~800ms、整张图 < 1.5s、storytelling 页 < 3s）与禁令
（**禁止** bounce / spin / fly-in / 疯狂 zoom）仍然成立 —— 只是现在没有"逐图形动画"
这一层来违反它们。

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
纸色分档褪色（与 Web 层同一条规则：主色向纸色分档褪色，不是彩虹）。

## 第二阶段（还没做，别假装做了）

- Sankey / Treemap / Heatmap / Radar / Gauge / Waterfall / Funnel
- 组合图的原生输出（目前 combo 在 PPT 层降级为柱）
- 把 `annotations`（reference / callout / peak）翻译成 G2 的 mark / annotation
  （见上「标注」）
- 每根柱子单独的 `data-m`（可以逐根 stagger）

**已取消**：数据驱动动画（growInY / pathIn 接进 `animate.py` 的时间线）—— 图表动画
关死（G2 `animation: false`）：图表在产物里是静态图，只跟随页面容器入场。
