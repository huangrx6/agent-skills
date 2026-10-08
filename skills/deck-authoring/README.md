# deck-authoring

把结构化内容与项目专属风格编译成可演讲的 HTML，并导出 PDF、PNG、原生或贴图 PPTX、逐页视频。
入口规则见 `SKILL.md`；字段和样式契约见 `references/style-architecture.md`。

## 安装与运行环境

Python 3.10+；Python 依赖的验证版本记录在 `requirements.txt`：

```bash
python3 -m pip install -r skills/deck-authoring/requirements.txt
```

浏览器工具当前使用 macOS 的 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`。
PNG、PDF 与视频通过 Chrome CDP 等待字体、图片与图表就绪后捕获。PDF 页尺寸验收需要
Poppler 的 `pdfinfo`，通过 PATH 查找或用 `DECK_PDFINFO` 指定可执行文件。
macOS 可用 `brew install poppler` 安装；`pip install -r requirements.txt` 不会安装该系统依赖。
MP4 编码另需 `swiftc` 与系统 AVFoundation；GIF 使用 Pillow。没有默认风格，也不自动下载品牌资产。

## 项目目录

```text
my-deck/
  deck.spec.json
  styles/<name>/style.json
  styles/<name>/skin.css
  brands/<name>/brand.json       # 可选
  assets/manifest.json          # 可选；图文件、来源与语义 id
```

风格和品牌按项目解析，不依赖启动目录。`DECK_STYLES` / `DECK_BRANDS` 可显式追加查找根；
它们的优先级高于项目目录。正式交付应带齐项目资源。字体缓存位于 `DECK_FONT_DIR` 或
`~/.config/deck-authoring/fonts/`，不写进 skill 目录。

## 制作与检查

先明确观众、观看方式、核心结论与输出格式；没有方向时用同样内容做三版预览，
已有选择时延续制作，不重复确认。`references/visual-quality.md` 给出结构选择、排印与视觉审稿方法。

以下命令中的脚本路径相对本 skill 目录：

```bash
python3 scripts/validate_spec.py /path/to/deck.spec.json
python3 scripts/ink.py /path/to/styles/<name>/style.json
python3 scripts/image_source.py --brief /path/to/deck.spec.json  # 需要素材合同才运行
python3 scripts/image_source.py --check /path/to/deck.spec.json
python3 scripts/render.py /path/to/deck.spec.json -o /path/to/deck.html --resolved /path/to/resolved.deck.json --trace
python3 scripts/check.py /path/to/deck.spec.json /path/to/deck.html
python3 scripts/shots.py /path/to/deck.html --out-dir /path/to/pages --count N
```

输入验证会拒绝错误类型、非法数量、非有限数据、丢失系列的输入形式，以及无法解析的风格或品牌。
渲染与验证共用品牌合并后的主题。图表由锁定的 G2 本地包生成，异步完成后才报告 ready。
产物检查覆盖实际文字颜色、透明度、可见性、祖先裁切、文字重叠、缺失元素与图表状态。
它不能代替语义和审美判断，完成检查后仍要看缩略图、逐页实际尺寸和最终导出。

## 交付格式

| 格式 | 能力与边界 |
| --- | --- |
| HTML | 支持键盘演示与讲稿；素材和字体可移植性需另验，不能默认称为自包含 |
| PDF | 逐页检查宽高和页数；文字可为矢量，照片与当前 Canvas 图表为位图 |
| PNG | 每页独立捕获完全入场的静帧，默认两倍像素 |
| 贴图 PPTX | 使用 PNG 保持画面，不能逐字编辑 |
| 原生 PPTX | 文字和受支持图表可编辑；保留实测字号、对齐与图片裁切，仍需目标宿主回读 |
| MP4 / GIF | 逐页演示动画，不包含多镜头剪辑与配乐 |

```bash
python3 scripts/pdf.py /path/to/deck.html -o /path/to/deck.pdf
python3 scripts/pptx_native.py --png-dir /path/to/pages -o /path/to/deck.pptx
python3 scripts/pptx_native.py /path/to/deck.html -o /path/to/editable.pptx
python3 scripts/animate.py /path/to/deck.html -o /path/to/deck.mp4
python3 scripts/animate.py /path/to/deck.html -o /path/to/deck.gif --width 960
```

组合图在 HTML/PDF/PNG 中支持同单位柱线组合，series 必须显式写 `mark:bar|line`。
原生 PPTX 暂不支持组合图，导出会明确拒绝，不能静默改成柱图；可改用贴图 PPTX。
非空 `annotations` 暂不支持，输入会拒绝，可将文字写入 `caption`。

素材按角色处理：真实截图优先，结构图用可验证的节点和关系制作，照片与插画可用生图。
`image_source.py --generate` 只在有可用后端并明确执行时生成，提示词须填写完成；
已有素材无需重生成。细节见 `references/images.md`。

## 调整工具

- `render.py … --candidates`：图文页和双栏页的候选对比；`--picks` 应用用户选择。
- `render.py … --repair`：仅尝试未明确声明的字号档；内容调整与拆页由作者完成。
- `grid.py --json`：布局几何与间距来源。
- `fonts.py --where` / `--list --urls` / `--map --a-only`：字体目录、来源和选型。
- `fonts.py --embed`：内嵌本地字体；图片与其他外部资源仍需核对。
- `measure.py deck.html`：独立读取真实浏览器测量结果。
- `deck.py`：查看项目品牌；内部 `resolve_theme` / `compile_spec` 供渲染与校验共用。
- `deckio.py`：统一文件读写错误处理，供脚本内部使用。

## 回归

从仓库根目录运行，浏览器测试需要系统 Chrome 能正常启动：

```bash
python3 -m unittest discover -s tests/deck-authoring -v
python3 skills/skill-builder/scripts/validate_skill.py skills/deck-authoring
```

测试数量以运行结果为准。新增回归覆盖数据完整性、图表真实绘制、质量门变异、项目主题解析、
字体内嵌、PPTX 裁切和排印、逐页 PDF 尺寸与 GIF 时长。最终视觉质量仍需查看实际产物。

未设置 `DECK_PDFINFO` 且 PATH 中找不到 `pdfinfo` 时，6 项 PDF 集成测试明确跳过，
其余测试继续运行；报告应分别列出通过、失败和跳过，不能称为全部通过。
显式配置的工具不可用或导出失败会记为测试错误，不会伪装成跳过或中断整套测试。
实际 PDF 导出仍必须有 `pdfinfo`，不会跳过页面尺寸验收。
