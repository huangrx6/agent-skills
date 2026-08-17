# 证据与置信度

## Evidence Ledger

每条可重跑证据分配 ID：

```text
EV-001: info shot.png --json
EV-002: runs shot.png --row 120 --tol 3 --min-len 5
EV-003: pick shot.png --points 24,24 --radius 2
```

正文写：`Evidence: EV-002`。

临时 crop/grid 路径不进入最终文档；记录生成命令和 bbox 即可复现。

## High

- 明确实心色；
- 扫描线稳定边界；
- 清晰可读文本；
- 明确 bbox。

## Medium

- 缩放换算；
- token 归一；
- 抗锯齿文字色；
- 图表几何数值；
- 圆角近似。

## Low

- 字体族；
- 精确阴影参数；
- 未提供状态；
- 单图响应式；
- 动效时长。

Low 必须进入 §9；strict 模式下需用户确认后才能提升为实现规格。
