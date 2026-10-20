# 交付格式与验收

HTML 是演示与导出的基准，按用户用途选择交付格式；用户明确要原生可编辑 PPTX 时选结构化路线。
不要为了走流程再次要求用户选择，也不需要默认导出所有格式。

自由 HTML 使用 `web_deck.py`，支持以下 PDF / PNG / 贴图 PPTX / 视频路径；不支持原生 PPTX。
其编译和验收见 [web-composition.md](web-composition.md)。本篇 `spec / resolved / check` 命令仅适用结构化路线。

| 格式 | 适用 | 限制 |
| --- | --- | --- |
| HTML | 浏览器演示、讲稿、可复现源 | 外部图片和本地字体需打包或内联，默认不是自包含文件 |
| PDF | 阅读、打印、归档 | 文字与部分形状可为矢量；照片和当前 Canvas 图表是位图 |
| PNG | 审稿、分享单页、贴图 PPTX | 内容不可编辑；默认以 3200×1800 捕获 |
| 贴图 PPTX | 保持浏览器外观、在 PowerPoint 演示 | 每页一张图，不能改文字或图表数据 |
| 原生 PPTX | 修改文字和支持的图表数据 | CSS 效果、文本引擎和字体可能不同，须回读验证 |
| MP4 / GIF | 自动播放的逐页演示 | 不包含配乐或复杂多镜头制作 |

## 导出前的两个问题

生成 HTML 后**先不导出**。先问配图，再问格式；这是交付流程的一部分，不是额外审批。
这一轮已经回答过的就跳过：配图已齐或用户已确认不要图 → 跳过第 1 问；格式已指定 → 跳过第 2 问。

1. **配图还要吗？**
   - 要：按 [配图流程](images.md) 交 `image-brief.md` 与回填路径，等用户生成或提供；不调用生图工具。回填后运行
     `image_handoff.py --check <plan> --html deck.html`：退出 0 才进入导出，退出 1 就报出待补文件或残留的占位文字。
   - 不要 / 纯文字：进入第 2 问，并在交付说明写"无配图，用户确认"。
2. **导出 PDF 还是 PPTX？** 用户本轮已指定格式就不重复问；同时要多种就都列出来，按依赖顺序导出。

只有用户明确说"不用管配图，直接导"才允许跳过第 1 问；此时导出物标为草稿，
在交付说明里列出仍缺的图，不能当成品。缺图时 `pdf.py` 仍可能成功，所以工具成功
不等于可以交付——判断依据是图位是否补齐，不是命令退出码。

| 情况 | 做法 |
| --- | --- |
| 有占位图位、用户还没回填 | 不导出；交提示词与回填路径，等图 |
| 用户说"图不要了" | 问格式，导出；记录"用户确认无配图" |
| 用户说"先导一版看看" | 明确是草稿；导出后列待补图，不能称完成 |
| 图已回填但 `--check` 退出 1 | 报哪些文件缺或无效，不导出 |
| 用户先要 PDF、后补齐图 | 第一版标草稿；补图后重导，不改口说第一版是成品 |

"占位图位缺图不阻塞编译"说的是 HTML 能打开，不是这份导出可以交付；不能拿它当跳过提问的理由。

## HTML 与讲稿

下面是结构化路线的播放器。自由 HTML 普通打开即演示、`?scroll` 为静态阅读，
方向键翻页、R 重播、F 全屏；它没有讲稿面板。

HTML 默认逐页纵向堆叠；`P` 切换演示态，也可用 `?present` 进入。
演示态支持方向键、空格、PageUp/PageDown、Home/End 和 `F` 全屏；Esc 回滚动态。
几何始终以 1600×900 为基准，演示视图等比缩放，不改布局。

`notes` 随 HTML 内嵌；`S` 打开讲稿面板，`B` 黑屏，`R` 重置计时。
讲稿面板与幻灯片处于同一窗口，投屏时观众也能看到。它不是独立双屏讲者视图。
生产文件中的壳层锚点由 `check.py` 验收，不能因只交 PDF 而手工删除壳层。

字体可用 `fonts.py --embed` 内联。这个命令只处理字体，不会把图片等全部外部资源打包。
交付 HTML 前检查每个资源路径；换目录和断网打开一次，再判断能否称为便携交付。
第三方平台是否能嵌入 HTML 取决于其功能与权限，不能保证任意平台都能直接接收。

## 统一的资源就绪条件

PNG、PDF 和动画复用 `animate.py` 的 CDP 浏览器捕获路径，等待字体、图片解码与
`window.__deck_charts_ready` 完成。缺图或图表失败会停止，不能把不完整画面当成功导出。
需要系统 Chrome 与 `websockets`，依赖安装见 `../README.md`。

PNG 按时间轴逐页捕获入场完成的静帧，不再按固定页间距裁超长图。`--count` 可选前 N 页预览，
不能大于实际页数；最终交付应与 spec 页数一致。

## 两种 PPTX

```bash
python3 scripts/pptx_native.py --png-dir pages -o deck.pptx
python3 scripts/pptx_native.py deck.html -o editable.pptx
python3 scripts/pptx_native.py --resolved resolved.deck.json -o editable.pptx
```

后两条共用构建核。`--resolved` 读取保存的测量合同，改过 spec、字体或风格后必须重新生成。
导出前运行 `check.py spec.json deck.html --resolved resolved.deck.json` 检查合同一致性。

原生版采用实际测量的位置、字号、字重、对齐与行距，图片按 `object-fit` 和
`object-position` 保持比例和焦点，中文另写东亚字体族。它记录字体名字，不嵌入字体文件；
目标电脑缺字体仍可能替换。截图本身也不会变成可编辑的 UI 元素。

原生版的当前边界：

- `combo` 尚无原生导出实现，会明确拒绝；需要这种图时，可交 HTML/PDF/贴图版，
  或另行实现原生图表支持。不要把柱线组合图静默改成柱图。
- 不支持任意 CSS、滤镜、颗粒、双墨错位与所有装饰效果。
- SVG 支持有限：导出器可能栅格化，或只保留部分形状；需要矢量时改原生形状，或在导出前转成 PNG 并回读。
- CSS `::before` 项目标记不会自动变成 PowerPoint 项目符号。
- 浏览器与 PowerPoint 的换行机制不同；位置相同不代表排版逐像素相同。

因此先用一张长标题页、一张图文页和一张图表页验证原生导出，再批量导出整套。

## PDF

```bash
python3 scripts/pdf.py deck.html -o deck.pdf
```

走 Chrome 打印路径，基准页尺寸 1200×675 pt（对应 1600×900 CSS px）。打印 CSS 会隐藏
演示壳层并关闭颗粒。文字通常保留为字体/矢量，图片、Canvas 与部分合成效果会栅格化。
不能把“PDF”直接等同于“全矢量”。

`pdf.py` 通过 Poppler 的 `pdfinfo` 逐页检查页数和页面尺寸，需在 PATH 中可用，或设
`DECK_PDFINFO=/完整路径/pdfinfo`。工具缺失会给出明确提示，不能跳过尺寸验证。
字体与位图统计用于辅助检查，不能代替打开文件检查缺字、分页和图表完整性。
缺图时它可能仍然成功，输出只能叫草稿；先走[导出前的两个问题](#导出前的两个问题)。

## 交付演练

先完成[导出前的两个问题](#导出前的两个问题)，再按依赖顺序运行；`N` 换成实际页数，只执行用户选定且素材就绪的格式：

```bash
python3 scripts/validate_spec.py deck.spec.json
python3 scripts/render.py deck.spec.json -o deck.html --resolved resolved.deck.json
python3 scripts/check.py deck.spec.json deck.html --resolved resolved.deck.json
python3 scripts/image_handoff.py --check image-plan.json --html deck.html   # 退出 1 就停，回去问图
python3 scripts/shots.py deck.html --out-dir pages --count N
python3 scripts/pdf.py deck.html -o deck.pdf
python3 scripts/pptx_native.py --png-dir pages -o deck.pptx
python3 scripts/pptx_native.py deck.html -o editable.pptx
python3 scripts/animate.py deck.html -o deck.mp4
```

`check.py` 验 HTML，不替代最终格式的检查。验收至少覆盖：

1. 整套缩略图：页数正确，节奏与主题统一，没有空白或重复页。
2. 关键页实际尺寸：标题、正文、图例、来源可读，图片完整，数据系列齐全。
3. 最终格式回读：PDF 逐页渲染；PPTX 在目标宿主或可用 LibreOffice 中打开；视频抽查
   起始、入场完成与结束画面。没有宿主时说明原生 PPTX 只完成结构验证。

像素差只辅助发现偏移，不能当作审美分数；颜色改变、数据丢失、错字和不合理换行应直接核对。
发布前的视觉检查项见 `visual-quality.md`。
