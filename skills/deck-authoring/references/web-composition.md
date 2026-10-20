# 自由 HTML 制作

用于 HTML 体验优先的演示。作者负责内容、构图、排印与素材；浏览器负责布局计算，
播放器负责翻页、等比缩放与确定性导出。素材方式按用户要求、证据用途和目标格式选择。

## 开始制作

设计方向、素材任务和已定交付保留在 [项目设计记录](refined-workflow.md) 中，先用真实内容试排。
本篇只说明 HTML 与工具接口。页面内部可用正常流、Grid / Flex 或经过实测的其他构图；
`assets/layout-starter.html` 是可选分区辅助，不是成品模板。需要分区计算时读 [布局计算](layout-technology.md)，
需要设计方法时读 [构图推导](composition-principles.md) 与 [排印](typography-and-space.md)。

## 源文件契约

写完整的 UTF-8 HTML，并显式关闭标签。每页是 body 的直接子元素。下面演示可选的分区辅助结构；
`slide` 与连续页码是播放器契约，内部可以自行构图，不要求每页都有标题、正文与页脚：

```html
<section class="slide" data-slide="1" data-title="本页主旨"
         data-enter="1.4" data-hold="5">
  <div class="deck-page" data-layout="statement">
    <header class="deck-header"><h1 data-reveal="rise" data-duration="0.6">本页主旨</h1></header>
    <main class="deck-body"><p class="deck-block" data-reveal="fade" data-at="0.2" data-duration="0.7">一个完整解释。</p></main>
    <footer class="deck-footer">章节与页码</footer>
  </div>
</section>
```

- `class` 精确写 `slide`，页码从 1 连续；视觉类加在页内容器上。`data-title` 供播放器识别页面。
- **页面根用 `.deck-page`**：容量、页脚侵入、区域越界这些检查只对 `.deck-page` 生效。
  自绘页面根（例如 `.pg`）不会被静默重排，但也拿不到这些检查——`web_check` 会报
  `no-capacity-contract` 提示你；此时必须逐页看截图确认没有溢出，或改回 `.deck-page`。
- 基准 1600×900；分区骨架通过 CSS Grid 排版；主题 CSS 与素材放在项目中。可用区域公式见布局参考。
- 编译器在作者 CSS 后注入基础布局；同等优先级时，后插入的规则会胜出。自定义布局用
  `.my-project.deck-page .deck-body` 等主题根限定，或调整公开的 `--deck-*` 变量，并检查最终计算样式。
  不必复制示例的视觉类名；避免把默认样式覆盖导致的对齐失效误判为内容过量。
- 运行时会加外层缩放容器；不要使用 `body > .slide` 或 `.slide:nth-of-type(2)` 这类依赖
  原有层级/同级顺序的选择器。指定页用 `.slide[data-slide="2"]`、ID 或页内容器类。
- 源与产物必须同目录、不同文件名，保留图片/字体/CSS 的相对路径；不支持 `<base>`。
- 图片与字体必须就绪，图位在加载前已有确定尺寸。异步图表等内容使用 `window.__deck_charts_ready` 接口，
  失败 reject，不能用固定等待秒数代替就绪。
- 外部素材不会自动内嵌；只有实际核对资源之后才能称“离线”或“单文件”。

## 长文本、页脚与图片的布局约束

不要给标题、副标题、正文分别写互不关联的固定 `top`：标题换成两行后，后面的元素不会自动让位。
优先用一页内的 grid 分区（页眉 / `minmax(0, 1fr)` 内容 / 页脚），标题组内部正常流式排版。
含页脚时给它保留实际所需空间；网格子项使用 `min-width:0`，长路径单独排印并按需要允许断行。
绝对定位适合经过测量的背景与图形锚点；文字变更后必须重新验证对应页。

目录放不下就拆成独立页；流程太长就按阶段或职责拆解。不要靠 `overflow:hidden`、极小字号或
把最后一行藏到画布外来“解决”超量。外部空白大而内部文字仍挤，不是有意留白。
若内容很少但边框拉得很高，检查项目自身的 flex/stretch/固定高度；不要把布局外壳与可见卡片混为一层。
表格行内对齐与容器自然高度的实施示例见 [容器与内容](layout-technology.md#容器跟内容合身空间留给构图)。

使用分区辅助结构时，可用 `.deck-block` 标记阅读组，`.deck-caption` 标记图注。标记反映真实用途，
不为消除提示改变内容角色。是否需要图注或主要文字、同屏多少组内容，由当前页面决定。
骨架默认正文 26px、标题 64px；封面与陈述页分别使用 `cover`、`statement` 的展示档，可通过项目 CSS 调整。`data-viewing="screen"` 的 24px 与 `room` 的 28px 是
可读性提醒起点，不是强制下限；还要按真实字体、行长、观看距离检查。默认不限制块数；
需要项目预算时，`.deck-body` 可声明正整数 `data-max-blocks`，超过该明确预算才列为待审。
正文可用区扣除实际 CSS 底部 padding，默认 48px，可调整，不另设硬下限。

数量、字号与空间尺寸写入报告，用来理解构图。通栏文字、多个并列块或大幅图片都不自动等于拥挤，
应看阅读目的、层级、分组及实际负担；底部安全距离也不等于视觉留白合格。

## 配图与素材接入

完整新稿执行 [素材流程](images.md)：实际交付 `image-plan.json`、`image-brief.md` 与已接好的图位；
位图由用户按 brief 生成或提供，作者不调用生图工具、不下载素材站图片。
不能把“用户会出图”当成省略 brief 的理由。
将 HTML 的 `img src` 接到约定路径，按设计设置尺寸、裁切与叠层。留出真实图位和“待素材”状态，
不能改为纯文字后把本页宣称为设计完成。用户生成的功能配图需核实结构；生成图片不能证明数据或系统事实。

## 动效与交互

内置入场使用 `data-reveal="fade|rise|wipe"`：透明度、轻移、横向揭示；这是工具能力列表，
不限制项目实现其他动效。无动效页面也可正常编译。
`data-at` 与 `data-duration` 单位为秒，默认 0 / 0.6；该页默认 enter=0.9、hold=3。
每个 reveal 必须在 `data-enter` 内结束，编译器会拒绝非有限时间、负数或未能完成的入场。
把标题、证据、注解按意义分组，不逐字抖动，不让父子两层重复动画同一段文字。
节点已有独立 `translate` 时，rise 降级为淡入；已有 `clip-path` 时，wipe 降级为淡入，
保留作者布局与裁切。需要这些入场效果时，把 reveal 放在没有上述属性的专门包裹元素上。

**落定要等于静态态。** 图和文字有重叠时（哪怕只压住一角），两者各自要有明确的 `z-index` 层号
（背景 0 / 装饰 10 / 图 20 / 遮罩 25 / 文字 30），不靠 DOM 顺序；也不要用一个容器同时包住图和文字。
`translate` / `filter` / 半透明会让元素在播放期间临时成层，落定后消失，层序如果只靠 DOM 顺序，
就会在这一瞬间换位。入场前、中、落定各看一次，并与 `?scroll` 完成态对照，
规则见[播放与动效](animation.md#落定后层级不能变)。

内置播放器每次翻页只播入场，然后停止；缩放不重播。尊重 `prefers-reduced-motion`。
CSS 动画与任意自定义脚本不自动具备可复现性；需要扩展时让同一时间产生同一状态，
为交互保留默认可读的静态画面，核对打印与取帧。背景动效不能承担不可见的事实或使正文持续移动。

普通打开即演示，方向键或 PageUp / PageDown 翻页、R 重播、F 全屏。没有常驻控制栏，也不为控件预留底部空间；
翻页状态由屏幕阅读器播报。输入框和页面交互元素保留自己的按键行为。
`?scroll` 显示所有页完成态。导出用 `window.__deck.seek(t)`，它会切到无控件取帧态。
本播放器没有结构化路线的讲稿面板或独立讲者窗口；不能把两条路线的快捷键混用。

## 编译、预览与导出

以下路径相对 skill；在项目目录编写源文件再编译：

```bash
python3 scripts/web_deck.py /path/to/source.html -o /path/to/deck.html --image-plan /path/to/image-plan.json
python3 scripts/web_check.py /path/to/deck.html --json /path/to/draft.check.json
# 素材回填后：
python3 scripts/web_deck.py /path/to/source.html -o /path/to/deck.html --image-plan /path/to/image-plan.json --check
python3 scripts/shots.py /path/to/deck.html --out-dir /path/to/pages --count N
python3 scripts/pdf.py /path/to/deck.html -o /path/to/deck.pdf
python3 scripts/pptx_native.py --png-dir /path/to/pages -o /path/to/deck.pptx
python3 scripts/animate.py /path/to/deck.html -o /path/to/deck.mp4
```

完整新稿使用 `--image-plan`，编译前验证当前配图 Markdown 与源文件图位，任一缺失不写出新产物；
文档默认位于计划旁的 `image-brief.md`，另存版本可用 `--image-brief briefs/v2.md`（相对计划目录）。
它允许图片待回填，但不等于资源、几何或美感通过；图位里残留“待配图”等可见文字会阻塞编译。缺图时不能据此交付最终 PDF。局部改稿或用户明确要求纯文字可省略。
待配图阶段也运行独立检查：资源失败仍会返回 1，但逐页几何继续测量。按 [待配图测量](layout-technology.md#待配图也要测量)
区分已登记的缺图与实际布局错误，不延后处理文字溢出，也不抹去缺图记录。

项目明确禁 SVG 时，在编译命令加入 `--raster-only`；通用流程不默认启用这项素材策略。
原生可编辑 PPTX 不支持本路线的任意 DOM/CSS；需要可编辑交付时重新选择结构化路线。
编译成功只证明 HTML 页序、结构和入场时间合同有效，**不证明布局或设计合格**。
每次编译还打印源文件的 `img`、内联 SVG 与 reveal 数量；`--check` 报告保留逐页 `sourceCoverage`。
这只清点作者标记，不把注入的播放器当作动效，不检测 CSS 背景、动态图片或自定义动画，
也不证明图像存在或可见。底层编译器兼容用户明确要求的纯文字稿和局部编辑，完整新稿仍须完成配图规划与交接（`image-brief.md`）；不能把数量当美感分。
`--check` 另做 Chrome 实测并保存同目录 `<产物名>.check.json`；上面的独立检查命令用于已有产物，
没有修改时不必重复跑两遍。检查等待字体、图片和图表就绪，逐页 seek 完成态，读取文本 Range
与裁切容器，并短时复测几何是否稳定。

- 退出 1：资源失败、文字越界/裁切、正文侵入呼吸区/页眉页脚、违反已声明的无 SVG 策略或完成态漂移，先修再导出。
- 退出 2：文字重叠、遮挡、媒体被容器裁掉或盖住、正文小于 16px、超出显式块数预算等需目检处理项。
- 退出 0：无上述未处理项；字号、缩放、图注与块标记的启发式提醒不默认阻塞。
  `--strict` 可主动将全部警告也设为阻塞。是否美观、是否适合观看场景仍看实际画面。

报告保留元素、文本片段、相交面积或溢出像素，逐项看实际截图。只有确认有意设计时，才在局部元素写
`data-web-check-allow="text-overlap media-clipped media-occluded"` 和非空 `data-web-check-reason`；
媒体被容器裁切或被不透明层盖住时，`--check` 会报 `media-clipped` / `media-occluded`；豁免仍保留在报告中。
硬错误不能豁免，不要添加整页豁免来消除提示。
检查范围是完成态 DOM；伪元素、Canvas 内文字、复杂遮罩、`pointer-events:none` 的覆盖物、
实际字体回退以及所有实时播放状态仍需人工检查。分区辅助结构会报告作者缩放文字的二维字号估计，
它仍不能代替实际投影目检；自定义 HTML 没有该分区测量时仍运行全局几何检查。
旧 `check.py` 依赖结构化 spec/manifest，不适用自由 HTML，不能报告它已通过。

续写中的局部 HTML 标注“制作中 / 当前 N 页”；计划总数另写，页脚与播放器不能各写一套。
正在被其他进程改写的文件先保存稳定副本再审查，不用同一路径的旧报告证明新版本已合格。
报告的 `htmlSha256` 对应检查开始时的 HTML 字节，`capturedAt` / `checkedAt` 记录 UTC 起止时间；
检查前后 HTML 不同或文件消失时，以 `input-changed` 硬失败。该哈希不包含外链 CSS、字体和图片，
这些资源变更后也要重新验收，不能仅凭 HTML 哈希相同复用旧报告。
几何检查不验证用户是否选过风格、是否满足配图要求或审美质量，交付时分别核对。

`scripts/design_signals.py` 另读完成态帧，报告字阶、字体家族、色彩数量、对齐轴、留白、
图像面积、行长、等宽卡片和连续页轮廓等可观测信号。它是审稿提醒，不是审美分数；
逐条判断是否成立，不能为了清零机械改值。扩展条件与证据要求见 [审美闸门](design-review.md)。

## 真实验收

按 [视觉审稿](visual-quality.md) 检查整套缩略图、逐页实际尺寸与最终交付格式，修后看新图。
图片回填前只评结构，回填后核对主体与图文关系；动效检查入场前、中、完成态，并试用翻页、缩放和减弱动画。
只读源代码或生成截图不算实际审阅。编译、素材、播放和最终格式检查各自对应其已验证范围。
