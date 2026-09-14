# draw.io 后端

同一份 `*.diagram.json` 的第二种落笔：`scripts/emit_drawio.py` → `.drawio`。
**几何一份、判据一份**：这一层只做 mxGraph 的序列化，`layout` / `check_layout` /
`text_metrics` / `shapes` / `palette` / `validate_spec` 一行没改。

什么时候走这个后端，见 `SKILL.md` 的「两个后端：选哪个」。这里写的是它的实现细节、
**与 Excalidraw 后端有意不同的地方**，以及人怎么接手。

## 一、产物形态：不压缩的 mxGraph XML

```text
<mxfile> → <diagram> → <mxGraphModel> → <root>
                                          ├── <mxCell id="0" />          ← 图本身
                                          ├── <mxCell id="1" parent="0"/> ← 默认图层
                                          └── 我们的 cell（parent="1"）
```

三条硬事实：

| 事实 | 为什么 |
| --- | --- |
| **`id="0"` 与 `id="1"` 必须有** | 少了 draw.io 直接说文件损坏（不是"少画一个元素"） |
| **写纯 XML，不压缩** | 应用保存时默认把 `<diagram>` 的内容 deflate+base64 成一行（2014 年起）；那玩意人能读但没法 diff。程序生成必须写纯 XML |
| **顺序 = 层叠顺序** | 后面的压在前面的上面。所以写入顺序是**区域 → 节点 → 边 → 标题**；区域是背景，必须最先 |

**不写 `modified` 时间戳。** 写进去的话"同一份规格重复生成"每次都是一个不同的文件，
而幂等（重跑无 diff、可被测试钉住、图能进 git）是这个 skill 最有用的一条性质。

## 二、形状映射（唯一的封闭集合）

`scripts/emit_drawio.py` 的 `SHAPE_STYLE` 是**本后端唯一新增的封闭集合**：
把 `shapes.SHAPES` 里的语义形状名映射到 drawio 的 style 片段。
"每种形状都有对应映射"是硬要求：漏掉一种形状，校验直接报错 ——
**少一个键就报错，绝不 fallback 成矩形**（静默换形状比报错难查得多）。

| 语义形状 | 中文 | drawio style |
| --- | --- | --- |
| `rect` | 矩形 | （无） |
| `round` | 圆角矩形 | `rounded=1` |
| `capsule` | 胶囊 / 消息队列 | `rounded=1;arcSize=50` |
| `ellipse` | 椭圆 / 角色 | `ellipse` |
| `diamond` | 菱形 / 判断 | `rhombus` |
| `cylinder` | 圆柱 / 数据库 | `shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12` |
| `note` | 便签 / 注释 | `shape=note;size=12;…`（天生虚线 + 左对齐） |

颜色、线宽、虚实仍然全部来自 `palette`：`fillColor` / `strokeColor` /
`strokeWidth`（`muted|normal|primary` → `1|2|3`，Excalidraw 那边是 1/1.5/2 的花样
—— **同一条语义轴，两边的画法各自适配自己的渲染器**）。

## 二点五、配色方案：**固定推导 + 只换 4 个种子色**

这一层是照 Excalidraw 那边的架构抄的（它那边是「5 个方向 × 每个 2 个种子」）：
**每套方案只给 4 个种子色 + 几个平台旋钮，其余全部由固定配比推导** ——
所以"基准风格固定、配色可换"靠的是**推导规则固定**，而不是给每套配色各写一整套色值。

| 方案 | 气质 | 什么时候用 | 字体 | 圆角 |
| --- | --- | --- | --- | --- |
| `classic` | 经典企业扁平 | 方案、汇报、给非技术同事看的交付件 | Helvetica | 4% |
| **`engineering`（默认）** | 工程文档风 | 节点名是代码标识符的技术图；放仓库 / 文档里 | **Courier New** | 8% |
| `print` | 黑白制图 | 要打印、或嵌进黑白文档；重点靠线宽不靠颜色 | Helvetica | 直角 |
| `night` | 深色技术 | 深色文档 / 深色主题的截图 | Helvetica | 6% |
| `blueprint` | 蓝图 | 讲解 / 示意图；深蓝底浅色线 | Helvetica | 直角 |

**每种方案只有这 4 个数**（`canvas` / `ink` / `accent` / `critical`），
其余（4 档 level 的填充与描边、边色、区域框色、网格色）都由 `DRAWIO_MIX` 那组配比算出来。
配比与原画**故意不同**：交付件的色块是"提示"不是"装饰"，所以填充更淡（0.10~0.14），
区域框更浅（0.25）—— 它是背景，只表示"到这儿为止"。

**怎么选** —— ⚠️ 这一条是**交互流程**，不是一条命令行：

1. **用户说了气质**（"要专业一点 / 黑白 / 深色 / 蓝图"）→ 直接对号入座，**别再问一轮**
   （规格里的 `mood` 字段也能自动选：`专业/商务/企业`→classic，`工程/代码/文档/等宽`→engineering，
   `黑白/打印/单色`→print，`深色/dark`→night，`蓝图/蓝底`→blueprint）
2. **用户没说**（含「你看着来 / 随便 / 都行」）→ 跑 `scripts/scheme_preview.py`，
   把那份**多页预览**给他，让他切页签挑。**这一步不能省** —— 方案名说明不了什么，
   要看了才知道喜不喜欢；由模型替他选一个，经常是出完才发现不是他要的那个"专业感"
3. **他要"在某套基础上改主色"**（"用 classic，但主色换成我们的品牌蓝"）→
   `--seed accent=<品牌蓝的色值>`（可重复：`canvas` / `ink` / `accent` / `critical` 四个种子色）。
   这是**用户的**颜色决定 —— 不违反"规格里不写颜色"那条硬规则：规格里照样一个颜色都没有，
   颜色是运行时输入

`--scheme` / `--seed` 是**落笔机制**（agent 在用户选定之后用的），**不是要用户记的接口**。
未知方案名/未知种子键/非 `#RRGGBB` 取值都**判失败**（列出可用值），不 fallback —— 和 `kind` 一条规矩。

### 等宽字体为什么要配缩小比例

盒子尺寸是按我们那份字宽表量的（以比例字体为基准）。**等宽字体的字更宽**，
照原字号渲染会顶出框 —— 所以 `engineering` 方案带 `font_scale: 0.88`。
这不是审美参数，是**尺寸链的一部分**：字号变了而盒子没变，就会溢出。

## 二点六、平台适配：图层 / 锁定 / 编辑数据 / 白底 / 多页

这些是"适配 drawio 这个平台"的部分，不是"画得像不像"。

| 能力 | 做法 | 为什么 |
| --- | --- | --- |
| **图层** | 区域与区域标题放进独立图层 `区域与标题（锁定）`，**声明在默认图层之前**（drawio 的图层按声明顺序叠，先声明的在下） | 区域是背景。分了图层之后，层序压过单元顺序 —— 光把区域写在前面已经不够了 |
| **锁定** | 区域框/标题/图标题带 `locked=1;movable=0;resizable=0`（`editable` 只对区域关掉，图标题保留可改字） | 手工编辑时最容易被拖歪的就是这几样，而拖歪了整张图就散了 |
| **编辑数据 + 悬停** | 节点写成 `<UserObject id=… label=… tooltip=… node_id=… kind=… group=… emphasis=… level=…>`，被包住的 `<mxCell>` **不带 id** | ① 悬停能看到 `detail`；② 将来"读回用户改过的 .drawio"（P1）有锚点 —— 否则只能靠标签字符串猜哪个框是哪个节点。⚠️ 身份只能有一处：内层再带 id 会被当成两个东西 |
| **白底** | `mxGraphModel background="…"` 显式写上（深色方案就是深色底） | 不写就吃应用默认；导出 PNG 时底色不稳定 |
| **多页** | `emit_drawio.py a.json b.json … -o book.drawio` | 一个文件多页是 drawio 的原生能力（底部页签）。21 张规格 → 一本 21 页；每页的页尺寸/背景各自算（图宽高差很远，共用页尺寸会留一大片空白） |

**实测（真实 app.diagrams.net，2026-09-14）**：图层面板里确实出现 `区域与标题（锁定）` 并带锁图标；
区域渲染在节点**下面**；底部两个页签可切换；等宽标签在白底节点里不溢出。

### 已知边界（工具链层面）

- ⚠️ **试过但没成**：在页面上下文里数"渲染出来的元素"（`g[data-cell-id]`）会恒为 0 ——
  新版 drawio 不是那个 DOM 结构，会让人误判成"导入失败"（其实图已经画出来了）。
- **`#U<url>` + 本地服务走不通**（Chrome 的本地网络访问策略），详见 §5.1。

## 三、与 Excalidraw 后端**有意不同**的地方

这些差异是渲染器不同导致的，不是漂移。两边的**文字逐行相等**由
两个后端会被逐图对照：同一份规格生成的 drawio 与 excalidraw，节点与边必须一一对上。

| 项 | Excalidraw 后端 | drawio 后端 | 说明 |
| --- | --- | --- | --- |
| 节点文字 | 形状 + **两个** text 元素（标题、`detail` 各一个，字号不同） | **一个** cell，折行拼在 `value` 里 | drawio 一个 cell 只有一档字号；`detail` 因此与标题同字号 |
| 断行 | 我们给宽度，**Excalidraw 自己重折**（见 `excalidraw-backend.md`） | 写死 `&lt;br&gt;`，**不重折** | 盒子尺寸本来就是按我们这份折行量的，只量一遍 |
| 边标签 | 独立 text 元素（要躲障碍、可能挪位） | 边 cell 自己的 `value`（drawio 摆在线的中点） | |
| 区域标题 | 宽过区域时铺一块画布色底 | 无底色 | 标题带（`REGION_HEAD`）本来就是预留空白的，节点不会压上去 |
| `fill: hachure`（默认） | 斜线填充 | **实心填充** | 图案填充是 P2 |
| 图标 | 支持 | **报错退出** | 图标要映射到 image / custom shape，P2；报错而不是悄悄丢一个视觉元素 |

## 四、结构自检：`scripts/check_drawio.py`

`emit` 在**写文件之前**跑它；不过就报错退出，**坏文件一个字节都不落盘**。也可以单独用：

```sh
python3 scripts/check_drawio.py x.drawio          # 退出码 1 = 有问题
```

守的六条事实：`id="0"` / `id="1"` 存在、cell id 唯一、`parent` 指向存在的 id、
顶点几何的数值是有限数、边折点是有限数、宽高 > 0；边的 `source`/`target` 必须指向
存在的**顶点**。**边的几何不带宽高是对的**（它是相对几何，路由由 source/target
与折点决定）—— 第一版 checker 在这里误判过三张正确的图。

**为什么不 vendor 官方 `mxfile.xsd`**：多一个第三方文件就多一处要同步的源，
而真正会让人吃亏的只有上面那几条。换成 xsd 校验随时可以，但那要连"xsd 变了怎么发现"
一起解决，那是另一件事。

**压缩过的文件不解**：明确报"这是 app 保存的压缩形态"而不是当空文件放行。
读回压缩文件是 P1（要 zlib + base64 + 再解析）。

## 五、人接手：怎么看、怎么导出

**编辑**：`app.diagrams.net`（draw.io 官网，免登录）→ File → Open from → Device，
选这个 `.drawio`。本地装了 draw.io 桌面版的话双击也行。

**导出**（图上左上角 File → Export as）：PNG（勾 *Crop* 去掉空白）、PDF（矢量，适合放文档）、
SVG。中文在导出 PDF/SVG 后仍是文字（不会变路径），要继续改字就回 drawio 改。

**Electron CLI 不是基线能力**：`/Applications/draw.io.app/Contents/MacOS/draw.io --export …`
在 macOS 上要 GUI 会话（没有 xvfb 这条路），所以"能不能导出"不依赖它 ——
导出是**人在应用里点一下**的事，而 `.drawio` 本身是我们可以自己生成的纯 XML。
（这也正是"不需要安装任何东西"这个结论的由来。）

### 5.1 自动化验证：真实 draw.io 怎么打开我们的文件

**走不通的路（已实测，别再试）**：本地起一个带 CORS 的服务，然后用
`https://app.diagrams.net/#Uhttp%3A%2F%2F127.0.0.1%3A8790%2Fd.drawio` 打开。
页面自己的 `fetch` 会直接 **`TypeError: Failed to fetch`** —— 这是 Chrome 的
**本地网络访问**策略（公网 https 页面取 127.0.0.1 要过私有网络预检），实测即使响应带上
`Access-Control-Allow-Private-Network: true` 仍然被挡（现在还要用户授权提示）。
`#U<url>` 与老的 `url=` 参数都会撞这堵墙，**不要**围绕它写 dev-tool。

**走得通的路（已实测）**：在页面上下文里**造一个 File 再派发 drop 事件** ——
等价于人把文件拖进画布：

```js
const dt = new DataTransfer();
dt.items.add(new File([xmlText], 'x.drawio', {type: 'application/xml'}));
const el = document.querySelector('.geDiagramContainer') || document.body;
['dragenter', 'dragover', 'drop'].forEach(t => (t === 'drop' ? document : el)
  .dispatchEvent(new DragEvent(t, {bubbles: true, cancelable: true, dataTransfer: dt})));
```

之后会弹对话框，要各点一次：**「在当前窗口打开」**与**「放弃更改」**
（后者只在当前图有未保存改动时出现）。

⚠️ **别用 `g[data-cell-id]` 去数渲染出来的元素** —— 新版 draw.io 不是那个 DOM 结构，
查到 0 会让人误判成“导入失败”（其实图已经画出来了，截图看一下就知道）。
本轮就在这上面白跑了几步。

### 5.2 已实测的渲染结论（真实 app.diagrams.net，不只是结构自检）

| 项 | 结果 |
| --- | --- |
| 7 种形状映射 | 全部按设计渲染：椭圆 / 圆角 / 胶囊（`arcSize=50` = 两端半圆）/ 菱形 / **圆柱真的有椭圆顶盖** / 便签有折角且虚线 / 矩形 |
| 区域 | 圆角 + 虚线边框 + 填充 ✓，标题居中于区域顶部 ✓ |
| 图标题 | 24px 居中、在内容上方 ✓（只写 `<diagram name>` 的话导出的 PNG 上没有它） |
| 边 | 正交走向 + 箭头 ✓；async 虚线 / sync 实线 ✓；标签在线中点 ✓ |
| 大图 | 25 节点 / 3 区域、`detail: diagnostic` 的实测图打开即自动适应整页（落在 20%）✓；节点文字全在框内 ✓ |
| 已知观感差异 | 边标签用 draw.io 自己的中点摆放，两个节点靠得近时会**贴到形状边上**（Excalidraw 后端会躲障碍）。算 P0 可接受；真要躲需自己算偏移（P2） |

## 六、已知边界与后续

- **P1**：读回压缩过的 `.drawio`（把 app 存过的文件也能改进后再生成）。
- **P2**：图标（→ image / custom shape）、图案填充（`hachure` / `cross-hatch`）、
  泳道（`swimlane`）、厂商标框图库（AWS / K8s / Azure 的那几套 stencil）。
- 命令行为：`emit_drawio.py <规格> [-o 输出] [--stdout]`；默认输出名 = 规格名换后缀
  （`a.diagram.json` → `a.diagram.drawio`）。退出码 0 = 出图，1 = 阻塞/自检不过（不写文件），
  2 = 读不到规格。
