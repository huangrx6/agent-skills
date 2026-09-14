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
`tests/test_emit_drawio.py::test_every_shape_has_a_drawio_mapping` 钉住"一一对应" ——
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

## 三、与 Excalidraw 后端**有意不同**的地方

这些差异是渲染器不同导致的，不是漂移。两边的**文字逐行相等**由
`tests/test_emit_drawio.py::TestCrossBackendAgreement` 钉住（7 个夹具 × 默认档 + 诊断档）。

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

## 六、已知边界与后续

- **P1**：读回压缩过的 `.drawio`（把 app 存过的文件也能改进后再生成）。
- **P2**：图标（→ image / custom shape）、图案填充（`hachure` / `cross-hatch`）、
  泳道（`swimlane`）、厂商标框图库（AWS / K8s / Azure 的那几套 stencil）。
- 命令行为：`emit_drawio.py <规格> [-o 输出] [--stdout]`；默认输出名 = 规格名换后缀
  （`a.diagram.json` → `a.diagram.drawio`）。退出码 0 = 出图，1 = 阻塞/自检不过（不写文件），
  2 = 读不到规格。
