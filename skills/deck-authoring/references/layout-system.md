# 布局、候选与修复

结构规格不写像素坐标。`grid.py` 提供基准尺寸与间距，render 输出页面结构，
skin.css 定义项目视觉，浏览器计算真实盒子。下面只列当前实现，不把设计建议当作自动布局能力。

## 基准与层级

画布固定 1600×900；横向边距 84、内容顶部 132、正文底界 824。
12 栏网格和间距变量由 `grid.py` 提供，可运行 `python3 scripts/grid.py --json` 查看。
演示视图整体等比缩放，不靠视口宽度重排每页。

标题块、证据载体、正文和页脚应有清楚层级。留白用于分组和阅读停顿，
不是越少越好；视觉重量与焦点仍由作者判断，没有自动审美评分器。
皮肤应使用公共字号/间距变量，修改后用真实盒子检查，不能假定 token 合理就不会越界。

## 实现的结构布局

| 页型 | layout | 结构 |
| --- | --- | --- |
| content-image | `visual-right`（默认）/ `visual-left` | 文字 7 栏、图片 5 栏；左右镜像 |
| content-image | `even` | 6 + 6 |
| content-image | `visual-wide` | 文字 4 栏、图片 8 栏 |
| content-image | `hero` | 图片占满，标题条叠图，后续内容仍需留空间 |
| two-column | `even`（默认） | 6 + 6 |
| two-column | `lean-left` / `lean-right` | 7 + 5 / 5 + 7 |
| two-column | `lean-hard-left` / `lean-hard-right` | 8 + 4 / 4 + 8 |

two-column 至多两栏，超过会拒绝，不能截掉第三栏。
其他非空 layout 字符串是 skin 的自定义钩子，render 使用缺省结构并发出 data-layout；
字符串本身不会创建新几何。`layout:"auto"` 无效。风格声明 layouts 词表时，check 会拦拼写错误。

hero 图片高度会为正文与 caption 预留空间，但长内容仍可能装不下；不要用满版图来隐藏正文。
截图/结构图优先 contain，照片使用 cover 时检查主体焦点；实际 object-fit 由皮肤决定。

## 碰撞政策

`layout/collision.py` 用测量盒与按角色定义的安全距离检查拥挤。
同组元素与 figure 内说明可免额外安全距离，独立文字的真实重叠仍会阻塞。
显式 hero 布局允许标题条覆盖图片，不表示标题和正文可以互相压住。
装饰/pseudo-elements 并非全部进入测量清单，因此仍要查看画面。

页脚与 logo 的相对锚点应逐页一致；避免用 `.slide > * {position:relative}`
之类规则破坏壳定位。内容层样式收窄到内容容器，详见 [style-architecture.md](style-architecture.md)。

## 写前容量估算

```sh
python3 scripts/render.py deck.spec.json --contract
python3 scripts/render.py deck.spec.json --contract --json
```

按区域跨度、字号、CJK 字宽和常用缩进估算条数/行长，无需输出 HTML。
结果是写作预算，不能预测所有字体、CSS、换行与图表标签。渲染后仍以实测为准。

## 候选试排

```sh
python3 scripts/render.py deck.spec.json -o deck.html --candidates
python3 scripts/render.py deck.spec.json -o deck.html --candidates --picks picks.json
python3 scripts/render.py deck.spec.json -o deck.html --candidates --pick
```

只搜索 **未声明 layout** 的 content-image 与 two-column 页。
生成 `deck.compare.html` 与 `deck.candidates.json`，前者可逐组比较并复制选择。
`picks.json` 是页码到 layout 的映射，例如 `{"3":"visual-wide"}`。
应用选择另存 `deck.picked.spec.json`；自动采用最优另存 `deck.candidates.spec.json`。
原 spec 不会自动覆盖，后续制作要明确采用哪个文件。

单页评分依据密度、换行、视觉占比和平衡；溢出/碰撞等使候选无效。
镜像构图按同一结构计，deck 级分配对相邻与全局重复加惩罚，平局由 seed 决定。
分数不判断论证或视觉意图；例如 hero 可因占比偏大得分较低，作者仍可有依据地选择。
候选只覆盖现有结构，不生成新 CSS 或新页型。

## 有限 repair

```sh
python3 scripts/render.py deck.spec.json -o deck.html --repair
```

当前仅检测正文竖向溢出和标题横向溢出，尝试未显式声明的 bulletTier/titleTier 降一档。
作者已经声明的字段不会自动改；写入后的字段也会阻止继续自动降档。
它不自动换布局、不改文案、不拆页、不重写皮肤，不是完整的“十三步修复引擎”。

至多四轮，输出 `deck.html.repair.json`；有补丁时另存 `deck.repaired.spec.json`。
失败应看具体诊断，再决定缩文案、换结构、拆页或修 CSS。repair 成功后仍要跑完整 check。
`--contract`、候选模式与 `--repair` 相互排斥，需分开执行。

## 目视复核

先看全篇缩略图，找重复构图、密集与空洞并置、焦点漂移；
再按最终观看尺寸检查标题、图例、来源、图片和栏间距。
只改导致问题的层：事实改 spec，视觉改 style/skin，品牌身份改 brand，
内部路由或尺寸错误才改脚本。不要以截图“好看”为理由改变原始数据或删掉必要内容。
