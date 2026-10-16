# draw.io 后端

```sh
python3 scripts/emit_drawio.py .source/system.diagram.json --quality showcase
# 多页时改用：
python3 scripts/emit_drawio.py .source/overview.diagram.json .source/detail.diagram.json -o system.drawio
python3 scripts/check_drawio.py system.drawio
```

多份 spec 可生成一个多页 `.drawio`。直接位于 `.source/` 的单份输入默认生成上级 `system.drawio`；
其他输入保留同目录换最后后缀的旧规则，`-o` 始终优先，见 [文件组织](delivery-files.md)。
输出是未压缩 mxGraph XML，便于 diff；
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
节点文字按脚本折行写入；fit 保持同档字号，显式观看预设的 detail 使用较小字号。
说明卡在主图下方按可用宽度排布：短卡保持紧凑，按短卡行宽估算超过八行时扩宽，放不下则另起一行，
不挤成窄长框。标题加粗、正文左对齐，标题和正文留间隔，条目之间保留空行；HTML 行高与尺寸计算共用参数。
正文作为文本转义后写入 HTML/XML，保留 `<`、`&` 等原文字面含义。长文不得靠截断或缩字解决；需移出图时先确认。
显式观看预设复用连线与标签间隔改善，并将标签偏移写入 XML；应用重排仍可能与 Excalidraw 不同。手工改文字后须重新审查布局。
`check_drawio.py` 支持未压缩和编辑器保存的压缩 XML；解压后检查相同的结构规则。
观看检查也能读取压缩页，但嵌套相对坐标、旋转或隐式字号会明确报为不可测量，需实际渲染审查。

## 配色

| `--scheme` | 用途 |
| --- | --- |
| `engineering`（默认） | 等宽工程文档 |
| `classic` | 通用清晰的扁平图 |
| `print` | 黑白打印 |
| `night` | 深色技术图 |
| `blueprint` | 蓝图感示意 |

明确指定 scheme 优先；未指定时 mood 可辅助准备提案。按 [逐步确认](decision-gates.md) 完成配色确认后使用，
需要比较时才运行 `python3 scripts/scheme_preview.py -o /tmp/schemes.drawio`。
品牌要求可用 `--seed accent=<品牌色>`；允许种子键 canvas/ink/accent/critical，
每项使用完整 RGB 色值。可重复传参。不要在 spec 节点里写颜色。

## 官方应用导出

默认不导出图片。下面命令仅在用户需要相应格式或刷新已有导出时使用，通常通过 [同步导出](delivery-files.md) 管理。
检查用 SVG 在需要时放临时目录，见 [观看场景](output-presets.md)。

```sh
python3 dev-tools/export_drawio.py system.drawio -o system.png --scale 2
python3 dev-tools/export_drawio.py system.drawio -o system.svg --format svg
python3 dev-tools/export_drawio.py system.drawio -o system.pdf --format pdf --crop
```

需要 draw.io 桌面版；`--binary` 或 `DRAWIO_BIN` 指定可执行文件。
工具调用应用的 CLI，不自行重画；也可由用户在应用中导出。

| 选项 | 限制 |
| --- | --- |
| `--border` | 外留白，默认 80 图内单位；应用对四边分配可能不均 |
| `--embed` | 将可编辑图嵌入支持的导出物 |
| `--size page` | 整页；默认 diagram 按内容导出 |
| `--width` / `--height` | 保持比例；同时指定表示容纳进框，不保证补满指定画布 |
| `--aspect` | 工具明确拒绝，当前 CLI 不能保证指定比例 |
| `--crop` | 仅 PDF；PNG/SVG 组合报错 |
| `--transparent` | 源文件显式背景可能仍可见，查看回执提示 |

退出码：0 成功，1 导出器失败，2 环境/参数/输入问题。
检查导出后的文字、线和页数，不能只凭 XML 自检宣称视觉通过。

## 多页同步

图片只容纳选定页，多页输入必须提供 `--page-index 2`（从 1 开始）；不再无提示只导第一页。
PDF 未指定页码时导出全页。`sync_exports.py` 同样接受页码并保存在 `.source`，后续沿用；
已有多页图片却没有页码记录时，先核对要保留的页面再同步。跨页全套图片需要显式分别命名导出，不自动制造一批文件。
