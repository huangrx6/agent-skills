# Excalidraw 后端

```sh
python3 scripts/emit_excalidraw.py .source/system.diagram.json --quality showcase
```

输出标准 `.excalidraw` JSON，可在 Excalidraw 或支持该格式的 Obsidian 插件中编辑。
不生成插件专用的压缩 `.excalidraw.md`。直接位于 `.source/` 的输入默认在上级生成 `system.excalidraw`；
其他输入保留同目录换最后后缀的旧规则，`-o` 始终优先。不自动写 vault。目录约定见 [文件组织](delivery-files.md)。

## 编辑边界

几何与元素 ID 确定性生成；保留 spec，结构修改优先回到 spec 再生成。
编辑器内手工调整不会自动同步回 spec，下一次生成可能覆盖它们。

- 普通节点使用绑定文字，真实字体可能导致应用重新折行、撑大容器。
- 带图标或 detail 的节点使用自由文字，并与形状归组；一个容器最多绑定一个文字元素。
- 自由文字能保持脚本计算的位置，但手工改标签或调整框大小后不会自动重新排版。

因此布局模型通过检查之后，还要用实际编辑器或官方导出复核文字、关系和遮挡。

## 官方导出

仅在用户需要图片或刷新已有图片时执行；一般通过 [同步导出](delivery-files.md) 保存并沿用参数。

```sh
diagram_check_dir=$(mktemp -d)
python3 dev-tools/export_excalidraw.py system.excalidraw -o system.png --svg "$diagram_check_dir/system.svg" --scale 2
# 以下为不同观看尺寸的替代命令，不需要全部执行：
python3 dev-tools/export_excalidraw.py system.excalidraw -o system.png --width 1600 --height 900
python3 dev-tools/export_excalidraw.py system.excalidraw -o system.png --aspect 16:9
```

仅指定 `--svg system.svg` 而不指定 `-o` 时只生成 SVG；只指定 `-o system.png` 时只生成 PNG。
需要两者时同时传入；不要为了交付 SVG 先多写一张 PNG。命令直接调用且两者都未指定仍按旧接口导出 PNG，
这是显式调用导出器的行为，不能作为默认制作步骤。SVG 可用于 [实际渲染检查](output-presets.md)。
本工具的 PNG/SVG 四周默认各留 **80 图内单位**，可用 `--padding` 调整。
自然尺寸导出以内容包围盒为基准扩边，节点位置和字号不变；倍率 2 时每边约 160 输出像素。
不把浏览器视口大小当作导出边界，也不通过添加可见背景框来撑大图片。
固定宽高时，增大留白会减少内容可用面积，需要重新核对观看字号。
这属于本工具的导出参数，不是承诺官网普通导出窗口提供同名设置。
需要受支持浏览器（可用 `--browser` 指定），加载官方 JS 包需要网络。
工具调用官方 `exportToBlob` / `exportToSvg`；它提供真实渲染证据，仍不替代目视审查，
也不能保证与所有未来版本的在线编辑器完全一致。

| 尺寸选项 | 行为 |
| --- | --- |
| `--scale` | 按内容导出倍率 |
| `--width` 或 `--height` | 固定一边，另一边按比例 |
| 同时 width + height | 保持比例容纳、居中，补背景到指定画布 |
| `--aspect 16:9` | 扩展不足的轴满足比例，不拉伸、不裁内容 |

PNG 尺寸从产物读取；SVG 画布由工具修改根节点/背景以满足目标尺寸。
无法完成时看 `--json` 回执，不把“调用完成”当作导出成功。

## 预览与官网编辑

```sh
python3 dev-tools/preview.py system.excalidraw "$diagram_check_dir/preview.png"
python3 scripts/open_excalidraw_com.py system.excalidraw
```

preview 需要 Pillow，画的是本项目自己的布局模型，适合快速查疏密与颜色；不能发现所有渲染器差异。

官网工具仅在需要官网编辑时使用：它在本机起一个只服务指定文件、仅允许
`https://excalidraw.com` 跨源读取的服务，并在该网站用 `#url=` 导入场景。
网站加载确认完成后可停止服务；这个入口与浏览器本地网络策略可能随版本变化。
用户要求仅本地处理时，使用本地编辑器，不打开官网。
