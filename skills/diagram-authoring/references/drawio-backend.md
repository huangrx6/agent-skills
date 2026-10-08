# draw.io 后端

```sh
python3 scripts/emit_drawio.py system.diagram.json -o system.drawio --quality showcase
python3 scripts/emit_drawio.py overview.json detail.json -o system.drawio
python3 scripts/check_drawio.py system.drawio
```

多份 spec 可生成一个多页 `.drawio`。输出是未压缩 mxGraph XML，便于 diff；
生成器在写入前检查 ID、引用、顶点与边几何，失败不覆盖成品。
在 draw.io 桌面版打开文件，或在网页应用中使用 File → Open from → Device。

## 实际支持范围

| spec 形状 | draw.io 图形 |
| --- | --- |
| `rect` | 矩形 |
| `round` | 圆角矩形 |
| `capsule` | 大圆角胶囊 |
| `ellipse` | 椭圆 |
| `diamond` | 菱形 |
| `cylinder` | 数据库圆柱 |
| `note` | 折角便签 |

这是封闭的基本形状映射，不是 draw.io 全部云/K8s/UML/BPMN/泳道库。
当前 `icon` **报错退出**，不能声称图标也会随同一 spec 无损转换。
Excalidraw 的 hachure/cross-hatch 在这里用实心填充表达。

区域与标题在独立锁定图层，节点保留语义属性与 detail 提示；图层顺序、页面尺寸、背景由工具生成。
节点文字按脚本折行写入，一个 cell 内的标题与 detail 使用同档字号；
边标签由 draw.io 放置，位置与 Excalidraw 可能不同。手工改文字后须重新审查布局。
`check_drawio.py` 只检查未压缩形态，应用重存为压缩 XML 后会明确拒绝检查。

## 配色

| `--scheme` | 用途 |
| --- | --- |
| `engineering`（默认） | 等宽工程文档 |
| `classic` | 通用清晰的扁平图 |
| `print` | 黑白打印 |
| `night` | 深色技术图 |
| `blueprint` | 蓝图感示意 |

明确指定 scheme 优先；未指定时 mood 可辅助选择。用户授权自行决定就直接选择，
需要比较时才运行 `python3 scripts/scheme_preview.py -o /tmp/schemes.drawio`。
品牌要求可用 `--seed accent=<品牌色>`；允许种子键 canvas/ink/accent/critical，
每项使用完整 RGB 色值。可重复传参。不要在 spec 节点里写颜色。

## 官方应用导出

```sh
python3 dev-tools/export_drawio.py system.drawio -o system.png --scale 2
python3 dev-tools/export_drawio.py system.drawio -o system.svg --format svg
python3 dev-tools/export_drawio.py system.drawio -o system.pdf --format pdf --crop
```

需要 draw.io 桌面版；`--binary` 或 `DRAWIO_BIN` 指定可执行文件。
工具调用应用的 CLI，不自行重画；也可由用户在应用中导出。

| 选项 | 限制 |
| --- | --- |
| `--border` | 外留白，默认 48 图内单位；应用对四边分配可能不均 |
| `--embed` | 将可编辑图嵌入支持的导出物 |
| `--size page` | 整页；默认 diagram 按内容导出 |
| `--width` / `--height` | 保持比例；同时指定表示容纳进框，不保证补满指定画布 |
| `--aspect` | 工具明确拒绝，当前 CLI 不能保证指定比例 |
| `--crop` | 仅 PDF；PNG/SVG 组合报错 |
| `--transparent` | 源文件显式背景可能仍可见，查看回执提示 |

退出码：0 成功，1 导出器失败，2 环境/参数/输入问题。
检查导出后的文字、线和页数，不能只凭 XML 自检宣称视觉通过。
