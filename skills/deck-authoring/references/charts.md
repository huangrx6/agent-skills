# 图表契约与验收

HTML 使用本地锁定的 AntV G2，原生 PPTX 使用 python-pptx。数据、图形意图、系列与标注的
支持范围必须明确，不能以降级图形或丢数据的方式完成导出。

## 输入

```json
{
  "type": "chart",
  "chart": "line",
  "title": "调用量统计",
  "message": "两条渠道的变化需要分别观察",
  "series": [
    {"name": "渠道 A", "data": [{"label": "Q1", "value": 20}, {"label": "Q2", "value": 30}]},
    {"name": "渠道 B", "data": [{"label": "Q1", "value": 30}, {"label": "Q2", "value": 25}]}
  ],
  "visual": {"kind": "data", "ratio": "3:2"},
  "unit": "次"
}
```

上例是结构示意数据，不是业务事实。`data` 与 `series` 选择一种，不能同时提供非空值。
数值必须有限，不能用布尔值、NaN 或 Infinity。系列名须唯一，类别标签不能空。
`intent` 是可选语义标注：trend / ranking / comparison / correlation / deviation /
distribution / composition / progress；它不自动选择图形。

| chart | 数据 | HTML | 原生 PPTX |
| --- | --- | --- | --- |
| bar | 单系列 label/value | 柱图 | 柱图 |
| bar-horizontal | 单系列 label/value | 横柱图 | 横柱图 |
| line | data 或多个 series | 按系列画线并标末值 | 折线图 |
| area | data 或多个 series | 按系列画面积并标末值 | 面积图 |
| bar-stacked | 非空 series | 堆叠柱图 | 堆叠柱图 |
| donut | 单系列非负数，总和大于零 | 环图，分类色与图例 | 环图，分类色与图例 |
| scatter | 单系列 label/x/y；value 可兼容 y | 数值横纵轴散点 | 散点图 |
| combo | 非空 series，每组显式 mark | 柱线组合，共用同单位纵轴 | 暂不支持，明确拒绝 |

bar、bar-horizontal、donut、scatter 暂不支持多个系列，输入会拒绝，不截取第一组。
组合图每组写 `"mark":"bar"` 或 `"mark":"line"`，必须至少各一种；不推断哪组应该画柱。
双轴、不同单位组合尚未提供契约。需要 PPTX 保持组合图外观时使用 PNG 贴图模式。

## 排印与视觉

`message` 写结论，使用真实标题 DOM 和测量标记；原 `title` 成为数据集小标题。
没有 message 时正常使用 title，不能把 HTML 标签当文字输出。
轴标签、数据标签与图例读取风格字体及字号；按观看场景检查，不能只要求“装得下”。

单系列柱图可用 `emphasis:{"values":["类别"]}` 强调类别；多系列和构成图必须保留可辨认的
分类编码与图例，不把“一种强调色”误用成“所有类别都同色”。按目标输出检查深浅背景下的辨识度。
多系列折线与面积图只标各系列末端数值，长标签、重叠线和极端值仍需视觉审稿。

## 标注与动画的边界

非空 `annotations` 当前会被规格验证和渲染入口明确拒绝，防止悄悄丢失参考线或说明。
可先把说明写进 `caption`，需要图内 reference / callout 时补齐实现与回归后再启用。

G2 使用 `animate:false` 关闭内部动画；逐页视频只做图表容器入场。
`window.__deck_charts_ready` 等待所有 `chart.render()` 完成，成功后设置每图
`data-chart-ready="1"`；失败记录 `data-chart-error`。pending、error 和缺图都不能导出为成功。
仅存在 canvas、图例或空容器不能证明数据完整，新增图形必须检查实际标记数与系列数。

## 验证

```bash
python3 scripts/validate_spec.py deck.spec.json
python3 scripts/render.py deck.spec.json -o deck.html
python3 scripts/check.py deck.spec.json deck.html
```

回归样张覆盖：多系列、长标签、正负数、空数据、环图类别、真实数值 x/y、组合 mark、异步失败。
检查图上数据与输入对应，不能只检查 render Promise 是否成功。最终 PDF/PPTX 仍需回读，
不同导出后端的图例、类别顺序、单位和颜色对应关系必须一致。

## 导出时的数据一致性

HTML 图旁显示单位，不自动换算原值。原生 PPTX 的分类图按标签并集对齐系列，
缺值保留为缺口；同系列重复标签会拒绝，避免覆盖。散点的 `y` 优先于兼容字段 `value`。
数值标签保留小数，不能为整齐而把小数截成整数。

图表在隐藏其他页之前读取真实容器尺寸，并以固定尺寸绘制；演示与截图只缩放整页。
这样切页不会因隐藏容器宽度归零而把图表挤窄。坐标文字显式保持不透明，避免主题削弱文字色。
