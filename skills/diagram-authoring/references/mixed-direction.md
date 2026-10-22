# 同画布混合方向（面板式）

单张图只有一根主轴：`direction` 只能是 `LR` 或 `TB`。需要一张画布内同时出现横向和竖向时，
不要在一张连通图里硬掰方向；把阅读问题拆成若干个**独立面板**，分别生成、检查，再拼到同一张
Excalidraw 画布。

这是面板式组合，不是复合布局：

- 每个面板仍然独立计算层、端口和走线；
- 面板之间没有自动连线，跨面板关系写在边标签或图外说明；
- 适合主链路 + 异常/部署视角并排，不适合“同一张连通图局部旋转 90°”的需求。

需要多张阅读视图而不是同一画布时，优先用 [阅读视图](reading-views.md) 的 `split_views.py`。

## 计划文件

路径相对于计划文件所在目录：

```json
{
  "version": 1,
  "layout": "row",
  "gap": 80,
  "padding": 24,
  "panels": [
    {"name": "main", "file": ".source/main.excalidraw"},
    {"name": "ops", "file": ".source/ops.excalidraw"}
  ]
}
```

- `layout`：`row`（并排）或 `column`（上下）。
- `gap`：面板外框之间的空档，默认 80。
- `padding`：面板内容到外框的内边距，默认 24。
- `name`：面板 ID 前缀，必须唯一；会做安全字符转换。
- `file`：已生成的 `.excalidraw`；先分别通过各自的检查。

## 生成

每个面板用独立的规格和方向生成：

```sh
python3 scripts/emit_excalidraw.py .source/main.diagram.json -o .source/main.excalidraw
python3 scripts/emit_excalidraw.py .source/ops.diagram.json -o .source/ops.excalidraw
python3 scripts/compose_panels.py .source/panels.json -o combined.excalidraw
```

例如 `main.diagram.json` 用 `"direction": "LR"`，`ops.diagram.json` 用 `"direction": "TB"`。
合成器只平移和隔离 ID，不会改变每个面板内部的布局。

## 边界

- 每个面板的布局、字号和连线仍需独立检查；合成通过只证明元素没有 ID 冲突、没有越出画布。
- 合成后的文件是新的成品。重新生成某个面板后重新运行合成，不要手改合成文件。
- 跨面板箭头没有自动生成；需要表达跨面板关系时，用边标签、卡片或正文说明。
- 面板背景取自各自 `appState.viewBackgroundColor`，整体画布是白底；深色面板会保留自己的底色。
- 带图片资源的面板会一并重映射 `files` 与 `fileId`；仍应目检图片是否完整。
