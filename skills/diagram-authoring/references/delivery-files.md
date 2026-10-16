# 文件组织与最少交付

用户没有指定文件结构时，新图在目标目录下独立成组。目录和文件用稳定、可辨的主题名：

```text
diagrams/
  system-overview/
    system-overview.excalidraw
    .source/
      system-overview.diagram.json
      system-overview.colors.json
  request-flow/
    request-flow.excalidraw
    .source/
      request-flow.diagram.json
```

配色文件仅在使用自定义配色时创建。`.source` 是后续修订的持久输入，不是缓存，
应随作品保留；不要为了界面干净而统一忽略或删除它。用户指定具体文件路径或项目已有约定时沿用。

## 文件取舍

- **成品：** 默认只有一种可编辑格式（Excalidraw、draw.io 或 Mermaid）。不主动生成 PNG/SVG/PDF，
  交付时简短告知需要可导出，不为此停下来询问。用户要求导出时只新增所需格式。
- **制作输入：** 规格、配色放 `.source/`；确需保留的生成参数、视图计划、覆盖回执也放这里。
- **检查：** 默认完成原生结构和几何检查（Mermaid 做官方语法检查，不能用其他后端的坐标检查代替），可在编辑器目检，不为验收例行导出图片。
  未做真实渲染检查如实说明。用户需要导出或已有图片需刷新时，再做实际渲染检查；
  必要的临时诊断、截图和对照留在临时目录，需要留证时集中到 `.source/checks/`。
- **说明：** 不例行生成每图 README、HTML 展示页、清单或压缩包。必要的业务说明可写入已有正文；
  只有正文无合适落点或用户要求时，才增加配套说明文件，不能为减少文件而删去事实。

不要预建空的 exports、versions、checks 等目录。修订覆盖同名产物，不默认累积 v2、final、final-final。
检查失败或无法导出预览时如实说明，不能把旧预览当作新图的预览。

## 生成路径

三后端都识别直接位于 `.source/` 的输入，例如：

```sh
python3 scripts/emit_excalidraw.py /project/docs/diagrams/system-overview/.source/system-overview.diagram.json --preset doc-wide --quality showcase
```

默认生成 `/project/docs/diagrams/system-overview/system-overview.excalidraw`。
`.source/entry.diagram.json`、`.source/storage.diagram.json` 分别生成外层 `entry`、`storage`，不会同名覆盖。
其他位置的输入保留旧行为：只将最后一个后缀换成 `.excalidraw` 、`.drawio` 或 `.mmd`，不会自动迁移。
`-o` 始终优先，`--stdout` 不落盘；多页 draw.io 仍须显式指定 `-o`。
生成器只写可编辑文件；预览通过官方导出工具另行生成，目录组织由作者落实。

## 更新已有导出

每次新建或更新原生图后调用（脚本路径相对 skill 根目录）：

```sh
python3 dev-tools/sync_exports.py /project/docs/diagrams/system/system.excalidraw
# 用户明确需要新增 SVG 时：
python3 dev-tools/sync_exports.py /project/docs/diagrams/system/system.excalidraw --format svg
```

- 无已有图片、无 `--format`：不调用浏览器或应用，不写图片，也不创建配置文件。
- 有同目录同名 `.png` / `.svg`：刷新已有格式；只有 SVG 就只导 SVG，不顺带生成 PNG。
  draw.io 同时支持已有 `.pdf` / `.jpg`。其他图的文件不动；自定义名称或外部目录的引用由作者检查并用后端工具显式更新。
- `--format` 可重复，取“已有格式 + 本次新增格式”的并集。删掉的预览不会因历史配置再次出现。
- 首次导出成功后在 `.source/<图名>.exports.json` 保存倍率、外边距及指定的宽高等参数，后续沿用。
  无记录的旧图无法可靠还原旧导出参数：查原命令或项目约定，用 `--scale` 等显式指定；
  仍未知时使用工具默认值并披露，不能声称保留了旧尺寸。只记录参数，不保存本机浏览器路径。
  draw.io 页码可用 `--page-index` 保存并沿用；Mermaid 目前保存 scale/padding。
  改回自然尺寸时删除配置中的 width/height/aspect；后端高级选项（如 draw.io 嵌入/透明）仍使用后端工具，需按原要求重导出。
- 全部格式在临时目录导出成功后再替换原文件；源图或目标被并发修改则停止覆盖。
  普通发布写入失败会尝试回滚；不承诺进程崩溃时多文件事务性。失败必须告知预览可能过期，不把旧图作为新版交付。
- 低层 emit 不启动浏览器；该同步步骤由作者工作流程执行，手动编辑原生文件后也适用。
  不因用户已有两种预览就删掉其中一种，也不在可编辑文件尚未成功生成时刷新图片。

## 已有文件与多视图

整理已有图时，先查 Markdown/HTML 等引用和人工编辑情况，再移动成组并同步相关引用。
不要把用户的独立版本、要求的格式或手动修订当作可删缓存；也不要恢复已经消失的目录。
只改图而未要求整理已有目录时，沿用原路径，不悄悄使旧链接失效。

同一主题的多视图可共用一个目录：外层按 `01-entry`、`02-execution` 等保存成品与预览，
各视图规格、源图、计划和覆盖回执集中放 `.source/`。拆分工具的输出目录指向 `.source/`，
没有必要再为每个视图建立同样的层级。必要的读图说明放已有文档或一份配套说明中。
公开样例库和开发测试为了验证保留多后端产物与报告，不是用户交付目录的模板。
