# 组件、图表与表格

## 组件

只有跨区复用或典型设计系统组件进入 §4。

记录：

- anatomy；
- width/height；
- padding/gap；
- typography；
- background/border/radius；
- visible states；
- evidence。

图中未出现的 hover/disabled 不属于 observed。

## 图表

记录：

- chart type；
- plot bbox；
- axes/ticks；
- series colors；
- legend；
- visible labels；
- approximate geometry。

从 y 坐标推算数值标 estimated。不要补图中未显示的 tick。

## 表格

记录：

- header height/background；
- row height；
- column widths/ratios；
- alignment；
- separators；
- cell padding；
- exact visible text。

## UI 库映射

可以说“视觉接近某类设计体系”，只能作为 implementation hint，不能断言原页面使用了某组件库。
