# 观看场景与可读性

先确定用户在哪看图，再生成和导出。观看目标在 [authoring.py](../scripts/authoring.py)，
生成字号与间距在 [presentation.py](../scripts/presentation.py)。它们不是 PNG 分辨率。

| 预设 | 观看区域 | 生成行为 |
| --- | --- | --- |
| doc-inline | 960 宽，高度随内容 | 文档字号 16 / 12 / 24，节点 / 说明 / 标题 |
| doc-wide | 1280 宽，高度随内容 | 与正文同字号，适合横向内容 |
| slide-16x9 | 1280 × 720 | 节点 24、说明/边标签 20、标题 32、区域标题 24；缩小部分间距并重新布局 |
| print-a4-landscape | 1120 × 792 | 节点 18、说明 14、标题 26；纸面场景估算，最终须实际打印尺寸复核 |
| fit（默认） | 自然内容大小 | 保持旧默认；不声称通过特定观看尺寸 |

## 生成与估算

以下在某张图的独立目录中演示，脚本路径从 skill 目录解析；实际执行时使用脚本绝对路径。
两种后端按需要选一种，文件取舍见 [文件组织](delivery-files.md)。

```sh
python3 scripts/emit_excalidraw.py .source/system.diagram.json --preset slide-16x9 --quality showcase
python3 scripts/emit_drawio.py .source/system.diagram.json --preset slide-16x9 --quality showcase
python3 scripts/check_presentation.py system.excalidraw --preset slide-16x9 --json
python3 scripts/check_presentation.py system.drawio --preset slide-16x9 --json
```

`--preset` 是生成参数，不写进结构规格。每次生成使用不可变的独立配置；节点、边标签、
区域、标题和卡片共同使用该配置。输入事实、方向约束和 detail 档位不因预设改变。
多页 draw.io 的 CLI 对各页使用同一预设；需要逐页不同预设时调用 `emit_page(..., preset=...)` 再 `build_file`。
显式预设的 draw.io 节点说明和卡片标题使用不同字号；fit 保持旧文件兼容。

生成器在指定非 fit 场景后对成品自动估算；装不下时发出 `presentation` 提示，
仍输出可编辑文件，不缩字或删边。提示不进入“增大间距”的几何调参循环。
showcase 的结构通过不等于观看通过：出现提示时调整有依据的方向、拆视图或改观看场景，再检查。

独立检查器读取本工具生成的 Excalidraw 或 draw.io（含压缩页），多页逐页评估。
按目标宽高扣边距计算缩小比例，上限 1，不用假定放大让小字号通过。
返回过小文字的 ID。退出码 0=未发现过小文字或 fit 未评估；1=有过小文字；2=不可测量。
JSON 的 `basis=editable_geometry_estimate`、`render_verified=false` 明确它不是实际渲染。

## 官方导出后检查

以下仅在有导出需求、已有图片刷新或用户明确要求真实渲染审查时执行；默认原生交付不自动运行。
`$diagram_check_dir` 为本次临时目录。按需要的格式选命令，SVG-only 可只传 `--svg`，不必生成 PNG。

```sh
diagram_check_dir=$(mktemp -d)
python3 dev-tools/export_excalidraw.py system.excalidraw -o system.png --svg "$diagram_check_dir/system.svg" --scale 1 --width 1280 --height 720
python3 dev-tools/check_render.py system.excalidraw "$diagram_check_dir/system.svg" --preset slide-16x9 --width 1280 --height 720 --json
# draw.io：width/height 只表示容纳范围，不保证补满画框
python3 dev-tools/export_drawio.py system.drawio -o system.png --scale 1
python3 dev-tools/export_drawio.py system.drawio -o "$diagram_check_dir/system.svg" --format svg --scale 1
python3 dev-tools/check_render.py system.drawio "$diagram_check_dir/system.svg" --preset slide-16x9 --json
```

`check_render.py` 把已导出的 SVG 放进真实 Chrome，测量可见文字和图形的边界、字体尺寸，
并和对应可编辑源文件核对文字及箭头路径数量。检查页禁用网络，不跟随 SVG 超链接。
支持本生成器经官方 Excalidraw utils 0.1.5 / draw.io 导出的 SVG；当前仅检查单页、无图标的场景。
多页须逐页导出并提供对应单页源文件。浏览器不存在记 skipped，无法测量记 unmeasurable，均不算通过。
退出码 0=已执行且未发现问题，1=发现问题，2=跳过或无法执行。

检查覆盖：画布裁切、缺失文字、缺失箭头/头部路径、未加载字体、声明字体的可用性，
以及指定观看尺寸下的实际字号。字体可用性采用两种回退字体的度量比较，可能存在同度量字体歧义；
新增检查：文字超出矩形 overflow 裁切区、实际文字包围盒明显重叠，以及被后绘制不透明 SVG 图形遮挡的可能。
遮挡使用实际图形填充命中采样，重叠使用字体包围盒，发现后需目视确认；不是逐字像素可见性证明。
不识别每个汉字的具体回退字体或缺字方框，也不验证任意 clipPath/mask、曲线形状内文字安全区、
图像/滤镜/透明叠层、箭头语义方向、编辑后重排或 PNG 与 SVG 像素一致。
通过后仍须目视核对；不能把它称为全面视觉验收。

`doc-inline / doc-wide` 按宽度阅读，允许页面滚动，**不限制图的总高度**。
长图在该场景通过不能推出“整图放进一屏也可读”；整屏汇报需另用 slide-16x9 检查。
卡片过长时可转为配套正文并逐项保留，主图和说明一起交付，不能以“总览”为由丢失必要事实。

开发者可运行 `python3 dev-tools/check_render_regressions.py` 复核检测能力；
七个合成 SVG 控制实验检查重叠、矩形裁切、前后绘制顺序及透明覆盖反例，不代替真实图的官方导出。

## 导出与受众

Excalidraw 支持指定宽高并补背景；draw.io 指定宽高只是容纳范围。
Excalidraw 四周默认留白 80 图内单位；固定宽高时这部分会占用内容空间，增加留白后须重新检查字号。
PNG @2/@3 只改善采样清晰度，嵌入同样大小的页面后，观看字号不变。
受众决定措辞，观看场景决定显示约束，detail 决定可见信息；三者不可互相替代。
不要把 executive 受众自动映射为 executive detail，也不要为了装进投影省掉关键条件。

[文档／投影对照样例](../examples/presentation/README.md) 有实际图片、源文件和检查回执。

Mermaid 使用自己的布局，不接受此处的 `--preset` 或几何字号检查。见 [Mermaid 后端](mermaid-backend.md)。
