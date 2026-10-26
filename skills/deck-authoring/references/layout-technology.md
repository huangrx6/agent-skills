# 布局计算与内容容量

使用分区辅助结构或排查布局时读本篇。利用成熟浏览器排版安排位置，用实测理解容量，再由内容与设计决定如何调整。
不能把播放器整页缩放、消除溢出和内容设计混为一件事。

## 目录

- [开源方案选择](#开源方案选择)
- [开源 skill 的方法取舍](#开源-skill-的方法取舍)
- [坐标交给浏览器，内容边界交给作者](#坐标交给浏览器内容边界交给作者)
- [看实测容量，再决定怎样调整](#看实测容量再决定怎样调整)
- [待配图也要测量](#待配图也要测量)
- [容器跟内容合身，空间留给构图](#容器跟内容合身空间留给构图)
- [SVG 形状的渲染边界](#svg-形状的渲染边界)
- [按项目选择素材策略](#按项目选择素材策略)

## 开源方案选择

2026-10-09 对照官方源码和文档：

| 项目 | 能直接借用的能力 | 本 skill 的选择 |
| --- | --- | --- |
| [Slidev](https://github.com/slidevjs/slidev) | Vue 布局组件、命名槽、章节文件、图文布局；[两栏标题布局](https://github.com/slidevjs/slidev/blob/main/packages/client/layouts/two-cols-header.vue) 用 Grid 分配标题/正文/底部 | 采用分区与组件化机制，以原生 CSS 实现；未安装或声称集成 Slidev。完整迁移适合另需 Vue 组件/讲者功能的项目，不为改布局引入整套新运行时 |
| [reveal.js](https://github.com/hakimel/reveal.js) | 成熟播放器、[章节嵌套](https://revealjs.com/vertical-slides/)、[图片占剩余空间](https://revealjs.com/layout/) | 翻页与缩放不等于重排；`r-fit-text` 的改字号不用于解决过量正文 |
| [Pretext](https://github.com/chenglou/pretext) | `prepare` + `layout` 预估真实字体下的行数和高度 | 大批量试排时可考虑；当前少量页面直接用浏览器实测，避免维护第二套文字度量。官方 Caveats 明示它不是完整 CSS 排版引擎 |
| [Paged.js](https://github.com/pagedjs/pagedjs) | [HTML 印刷分页](https://pagedjs.org/en/documentation/4-how-paged.js-works/)，溢出后搬到下一页 | 可用于长附录/讲义；它不知道何处是一个完整讲解步骤，也不会主动给演讲留白 |
| [Marp](https://github.com/marp-team/marp-core) | Markdown 演示与主题 | [默认 inlineSVG](https://github.com/marp-team/marp-core/blob/main/src/marp.ts) 需要结合项目素材约束评估；用户禁 SVG 时不能默认照用，其余项目按编辑与导出需要选择 |

以上为技术取舍，不承诺任何框架能自动把任意材料排得漂亮。本次没有复制第三方代码或新增 npm 依赖。
需要导出表格附录时可另看 [PptxGenJS autoPage](https://gitbrent.github.io/PptxGenJS/docs/api-tables.html)，
它针对表格行，不负责整套演示的语义分页；不能把缩字/自动表格续页当正文设计。

## 开源 skill 的方法取舍

2026-10-16 对照 [oh-my-ppt 固定版本](https://github.com/arcsin1/oh-my-ppt/tree/56bc56d41e6065bbb7fa21f2b3ea407575cb3aae)
的公开源码。它是桌面应用，以下只借鉴工作方法，没有复制其应用、代码、风格包或素材，也未做效果或导出基准测试。

| 源码依据 | 本 skill 的采用方式与边界 |
| --- | --- |
| [布局 skill](https://github.com/arcsin1/oh-my-ppt/blob/56bc56d41e6065bbb7fa21f2b3ea407575cb3aae/resources/skills/oh-my-ppt-layout/SKILL.md)：设计约定与逐页 HTML | 在项目保留简短设计记录，让内容、视觉、素材和交付共用同一组决定；保持自由 HTML，不要求移植桌面应用的状态或固定风格包 |
| [图片提示组织](https://github.com/arcsin1/oh-my-ppt/blob/56bc56d41e6065bbb7fa21f2b3ea407575cb3aae/src/main/image-generation/prompt-director.ts)：将图片意图转成生成要求 | 先说明图片任务、位置、文字安全区和图像语言，再写 image-brief.md 交用户出图并回填；不绑定其 provider，也不把通用图片提示当所有项目的审美默认值 |
| [PPTX 渲染器](https://github.com/arcsin1/oh-my-ppt/blob/56bc56d41e6065bbb7fa21f2b3ea407575cb3aae/src/main/io/html-pptx/renderer.ts)：转换与渲染边界 | 保留本工具现有导出，实际回读用户所需格式；没有据此宣称任意 HTML/CSS 都能保真且可编辑 |

方法是否改善本 skill，以相同真实材料的代表页和连续页面验证；源码功能列表、模板数量与检查通过均不能证明视觉质量。
未来引入转换器或外部资源前，先核对许可，再用中文多行文字、实际图片裁切和关键背景效果做小样往返比较。

## 坐标交给浏览器，内容边界交给作者

`assets/layout-starter.html` 是可选起点，内部构图可以自行实现。编译器内嵌 `assets/web-layouts.css`，
只有 `.deck-page` 使用这些分区规则；不用该类的自定义页面不被静默重排。下例演示图文页，不是必选页型。

```html
<section class="slide" data-slide="1" data-title="本页表达目的">
  <div class="deck-page" data-layout="image-right" data-viewing="screen">
    <header class="deck-header"><h1>本页表达目的</h1></header>
    <main class="deck-body">
      <div class="deck-copy">
        <p class="deck-block">第一条短解释。</p>
        <p class="deck-block">第二条短解释。</p>
      </div>
      <figure class="deck-media">
        <img src="assets/chapter-focus.png" alt="由模型生成并核对的本页配图">
        <figcaption class="deck-caption">概念配图，非真实系统截图</figcaption>
      </figure>
    </main>
    <footer class="deck-footer">章节名称 · 当前页码</footer>
  </div>
</section>
```

播放器画布 1600×900。以下为辅助骨架的可覆盖默认值：左右边距 112px，上 88px、下 56px，分区间距 48px。
标题、正文、页脚处于同一个 `auto / minmax(0,1fr) / auto` 网格，标题实际占几行就用几行的高度。
标题变长时正文自动下移并减少可用高度，页脚保留独立区域。另做绝对定位布局时须自行处理文本变长的影响。

以实测标题 112px、页脚 24px 为例：

```text
内容宽 = 1600 - 112×2 = 1376px
正文区高 = 900 - 88 - 56 - 112 - 24 - 48×2 = 524px
正文可用高 = 524 - 48px底部安全区 = 476px
```

这是测量示例，实际高度来自字体加载后的 DOM。图片预留区域，需完整展示时使用 `object-fit:contain`，
素材解码不改变页面骨架。内栏用 Grid/Flex 与 `min-width:0`，长路径另页解释或合理换行。
正文默认 26px，标题 64px、组内小标题 32px、图注 18px、页脚 16px；是演示尺度试排起点，
密集阅读可下调，投影需另行验证。
普通 `.deck-copy` 默认阅读宽度上限 820px，图文并列还会受列宽约束。项目可单独调整各角色变量。
颜色、字族和视觉风格遵循项目 brief 与授权；骨架不决定视觉方向。底部安全区只是防侵入边界，
不是“有留白”的证明；不要填完剩余容量，构图仍需在文字组之间、阅读列旁和图像周围安排空白。

各栏还要单独算账：一栏依次包含图片、图注和说明时，高度为三者实测值加所有间距、边框和内距；
两栏并排取较高的一栏，再加整行下方的补充说明及间距，才是正文实际需求高度。
图注、条件框和底部注解从一开始纳入正文预算，不能排完主图后再贴在剩余空间。
表格与代码按最长路径、中英混排和真实换行计算；节点图的标签与连线也须留空间，不能只量图片矩形。
自然流会保持页脚位置，却不会自动把过量正文拆到下一页；`minmax(0,1fr)` 也不能保证子项不溢出。

## 看实测容量，再决定怎样调整

`.deck-block` 用于标记阅读组，`.deck-caption` 用于图注；它们不规定所有页面只能有几个观点或一定含主体文字。
检查器默认只报告块数，`maxBlocks` 为 `null`。项目若需要明确预算，可在 `.deck-body` 设置
`data-max-blocks` 为任意正整数；实际超过该预算触发 `body-block-budget` 待审。
没有默认三块上限，也不因为声明五块或八块就判为过密。可读性来自实际内容和空间关系，不能靠改数字证明。

使用分区合同的页面输出 `layoutBudget`：区域矩形、真实正文可用尺寸、块数及字号。
文字越出所属区域、必要内容被裁切、图片未分区或越界、正文侵入页脚或作者声明的底部 padding 是错误。
正文容量扣除计算样式中的真实 `padding-bottom`，没有额外 32px 下限；默认 CSS 的 48px 可由项目覆盖。
这些判断只应用于选择该辅助结构的页面，不把它强加给所有自定义 HTML。

`data-viewing="screen"`（缺省）的正文建议起点为 24px，`room` 为 28px；报告字段为
`minBodyFontRecommended`，不是强制字号。未知 viewing 值仍作为接口错误处理。
辅助文字 `.deck-caption` 低于 16px、`.deck-footer` 低于 14px 会提示；显式 `--min-font N`
会对全页文字使用该提醒阈值。页内文字缩放也会报告二维字号估计，播放器整体缩放不计入。
小字、缩放、仅图注或未标记内容均为普通提示；默认不会据此否定设计，`--strict` 可按需将所有警告阻塞。
检查器无法判断每一种字体与投影条件；真正的可读性必须在目标观看尺寸下检查。

不用 `.deck-page` 也可以创作并运行全局几何检查，但报告不声称测过不存在的正文区域。
有意叠层可逐项确认；不能把内容改成图注、藏掉末行或漏标来伪造验收。

出现问题时先区分成因：CSS 覆盖或字体变化造成的位置错误，应该修实现；确实承载过量时，
优先按完整问题拆页、去除图文复述，再调整阅读列、图文比例与排印。比较型内容保留必要的同屏关系。
长清单可进附录，也可在目标允许的密集证据页展示；重要条件和来源不能在提炼时丢失。
调整后重新测量并看实际画面，不用机械缩字或隐藏内容来消除报错。

机械检查不验证精致度。还需看行长、辅助字重量、强调层次、组间空白与页面节奏。
不设“空白率达标”数字；`web_check.py` 不替作者改写内容、断章或评审美感。

## 待配图也要测量

先固定图位比例和尺寸，用真实文字、标签、图注与条件说明编译，然后运行 `web_check.py`。
把图位在 1600×900 下的渲染尺寸乘捕获倍率（PNG/贴图 PPTX 按 2×）记进 `image-plan.json` 的
`target_px`，它就是之后交给用户出图的输出参数；量一次比回填后改裁切便宜。
图片未到会产生资源失败，但检查器仍继续逐页读取几何；核对页数与 `layoutBudget` 是否实际产生，
分别处理 `body-capacity-exceeded`、`body-text-outside`、裁切、页脚侵入等问题。待图稿可以保留已登记的缺图项，
不能因此忽略其他错误或宣称整项检查通过。字体或脚本失败会影响测量有效性，应先修复。
若要用临时测量图片，只能在隔离副本中使用，结果注明是占位状态，不作为实际图片验收，也不写入交付素材目录。

交付前核对报告与最终 HTML 版本；修改文案、字号、列宽、图注或背景后重新检查受影响页面。
仅 HTML 哈希相同不足以证明报告有效：外链字体、CSS 和图片变化或删除后也要重测。
回填后重看实际裁切与文字避让，并检查最终产物；不能用一份占位阶段的通过报告证明缺图稿或回填稿已完成。

## 容器跟内容合身，空间留给构图

先找出多余尺寸从哪里来，再决定是否保留：检查计算样式中的 `height/min-height`、`flex-grow`、
Grid 的 `1fr` 行轨和父级 `align-items:stretch`。可用区域需要填满，不代表每个有底色或边框的内容组也要填满。
同一行一侧有多项内容时，stretch 会把另一侧的一小段话拉到相同高度；把边框直接画在这个布局外壳上，
就容易出现大面积无作用的框内空白。表格被 flex 拉满时，多出来的高度还可能分配到各行。

没有刻意等高设计时，可让内容组自然取高，用外层网格安排位置；需要等高比较时保留等高，
但重新安排各组信息的对齐与空间，不能只把短文字放在大框顶端。框线是否出现按分组语义判断，
不能全局删边框来破坏真正的边界、图示或表格关系。检查方法见 [视觉审稿](visual-quality.md)。

下例是可选的项目 CSS 写法，类名、间距和对齐按实际画面调整，不会由编译器自动应用：

```css
/* 一行组块各取内容高度；不把卡片表面直接拉满剩余页面。 */
.content-groups { display: grid; align-items: start; gap: 2rem; }
.content-group { min-width: 0; height: auto; }
/* 紧凑比较表按内容取高；文字横向对齐与垂直居中是两件事。 */
.comparison-table { width: 100%; height: auto; flex: 0 0 auto; border-collapse: collapse; }
.comparison-table :is(th, td) { padding: .75em 1em; vertical-align: middle; text-align: left; }
/* 长段解释需要对齐首行时可局部保留顶齐，仍有足够上下内距。 */
.comparison-table .long-explanation { vertical-align: top; }
```

原生表格用 `vertical-align`；Grid/Flex 仿表格要在实际单元格容器使用 `align-items:center` 等布局属性，
单写 `vertical-align` 不会生效。`text-align:center` 只改变水平方向，也不能修复贴顶。
用一行与多行单元格并存的实际内容验证：文字离上下分隔线是否舒服、同一行是否容易横向比较。
字体本身的上下留空会影响视觉中心，不能只看 CSS 属性已写 middle 就算完成。

### 容量超标的错误收敛与内容带

容量检查超标后最常见的错误收敛是压缩 `gap`/`padding`/字号：每压一点报错都会消失，
但累积结果是**内容全部挤在页面上半部、底部空出 15%–35% 页高**——检查通过，画面却
头重脚轻。这与"内容真的过量"是两件事，不能用同一个动作解决。

正确的顺序与 [构图原则](composition-principles.md#页面利用率内容带要有意) 一致：

1. **先定内容带**（标题、主体、收束在画面中的上下位置），目标是可用高度的 60–80%。
   内容带低于 55% 时先查主体：字号/图/数字是否太小、材料是否还没展开、要不要一个
   视觉锚点占住下半部；确认不是内容带问题，才回头拆页或减内容。
2. **再调间距层级**：内边距 < 组间距 < 页边距通常成立；组间距（900 基准）常取 24–40px，
   大字停顿页 48–64px，卡片内距从 28–32px 起。三者比例失当时，页面会显得"框很大、字很挤"。
3. **对齐位置放在最后**：内容带撑起后，整组在可用高里居中/均匀分布只用于"单纯需要对齐"的
   场合；不要用它把标题与内容拉开、给空洞收场（见 [内容理解](content-intelligence.md#全篇复核)），
   更不要把 `align-content:center` 当成修复"底部大空"的处方。

量化方法：量内容总高占 body 可用比例与内容首尾到 body 边界的间距——占比落在 60–80%、
顶部（标题下）与底部（页脚上）间距大致相称即成立；只有单侧空出页高 15% 以上且另一侧
明显更小时，才是需要回头调内容带或间距的信号。在完成态页面控制台执行一次即可：

```js
document.querySelectorAll('.slide').forEach((s, i) => {
  const b = s.querySelector('.deck-body'); if (!b) return;
  const br = b.getBoundingClientRect(); const kids = [...b.children].filter(k => k.getBoundingClientRect().height > 2);
  const t0 = Math.min(...kids.map(k => k.getBoundingClientRect().top));
  const b0 = Math.max(...kids.map(k => k.getBoundingClientRect().bottom));
  console.log(i + 1, 'fill', Math.round((b0 - t0) / br.height * 100) + '%',
    'top', Math.round(t0 - br.top), 'bottom', Math.round(br.bottom - b0));
});
```

两个附带判断：两栏页高度差超过 25% 时，把矮栏内容拆细（一个 pill 一行说明、每条路径
单独成行、补一句关键条件）向高栏靠拢，而不是只居中留空；图像位高度按正文可用高的
85–90% 取，固定小高度（如半屏）会把整页重心拉偏。压间距只允许发生在"间距明显超过
本项目其他页"的个别页上；内容真实超出（`body-capacity-exceeded` 复测仍在）时减内容、拆页
或调整图文比例。

## SVG 形状的渲染边界

内联 SVG 的 `viewBox` 是硬裁剪窗：任何坐标越界的形状都被**静默裁掉**，不报错、不警告，
页面上看就是"半截""缺了一块"。四类高发场景：

1. **角色或图标组放进矮 viewBox**——在 128px 高的横条里画 110px 高的站立角色，
   头顶天线和头部整体超出顶部，只剩下半身。
2. **装饰探出父容器再遇到上层裁剪**——印章、徽章用负 `top` 挂在卡片边缘，
   卡片或页面层有 `overflow:hidden` 时被切。
3. **贴边元素的描边被裁**——`cy = r` 的球体上缘恰好压在 viewBox 边界，
   stroke 外半圈消失，视觉上"不圆"。
4. **文字宽于所属形状**——色块内一行说明、圆内标签、卡片内编号超出形状边界，
   文字压边框或探出弧线；形状按坐标写死宽度，没给文字留够空间。

设计时给 viewBox 留余量：按**最高元素**（含天线、球杆、stroke 的一半）取上界，
不要按"主体大概高度"估。收尾前做一次程序化扫描（在完成态页面执行）：
对每个 SVG 的叶子形状（`circle/rect/path/ellipse/line/text`）比较其
`getBoundingClientRect()` 与 SVG 根的渲染盒，任一方向越界大于 3px 即为实际被裁；
`g` 组的包围盒会被 `transform` 天然放大，只以叶子形状为准。修改 viewBox 后同步检查
`width`/`height` 与容器的关系，`preserveAspectRatio` 的 letterbox 不算裁剪。

同一检查要覆盖 `text`：文字宽度超出**所属形状**（色块、圆、卡片）与越出 viewBox 一样算溢出。
实测出现过色块内一行说明文字右端压边框、圆内小字两端探出弧线的情况——把每个 text 的测量盒与
所属形状比较，或按「字号 × 每字宽 × 字符数 + 内边距」给形状留足宽度，不要依赖目测。

## 按项目选择素材策略

仅当项目明确禁止 SVG 时启用 `--raster-only`。完整新稿先按 [配图流程](images.md) 交接；素材回填后检查资源与布局：

```bash
python3 scripts/web_deck.py source.html -o deck.html --image-plan image-plan.json --raster-only --check
python3 scripts/image_handoff.py --check image-plan.json
```

`--raster-only` 静态拒绝作者 SVG 标签、可识别 SVG 媒体 URL 和内联 CSS 资源，并把策略写入产物；
浏览器检查继续查看实际 DOM 与计算样式中的 SVG。它不证明某张 PNG 来自用户所用模型，素材来源仍须
保留提示词与原始文件。用户要求只用生图时，缺图或素材瑕疵不能临时用程序绘图替代；
其他项目按用途选择真实证据、授权素材、图表或用户生成图，分别核对质量与事实。
