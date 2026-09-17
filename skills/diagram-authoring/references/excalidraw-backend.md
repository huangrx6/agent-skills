# Excalidraw 后端

`scripts/emit_excalidraw.py` → `.excalidraw`。这是**默认后端**：手绘感、能在
Obsidian 里就地编辑、整条链路零依赖。什么时候该改用 draw.io，见 `SKILL.md` 的
「两个后端：选哪个」。

## 一、为什么是 `.excalidraw`（plain JSON），不是 `.excalidraw.md`

Obsidian 的 Excalidraw 插件把 `.excalidraw.md` 里的场景压成 **lz-string**（实测插件
`main.js` 里有 **24 处** `LZString`、`compressToBase64` / `compressToUint8Array` /
`compressToUTF16`）—— **lz-string 没有 stdlib Python 等价物**，选它就意味着手抄一份 JS
压缩算法，或者引依赖（而核心链路零依赖是这个 skill 的前提）。

`*.excalidraw` 是普通 JSON，**插件原生读写**（同目录的 `my-obsidian-library.excalidrawlib`
就是 plain JSON）。所以本 skill 输出 plain JSON，不碰 lz-string。

**同一份规格每次生成的字节相同**（seed 由元素 id 的 sha256 推出，没有 `Date.now()`
那一类），所以图能进 git，且 diff 有意义。

## 二、在 excalidraw.com 上接着手改

`scripts/open_excalidraw_com.py` 起一个只服务那一个场景文件、且只允许 excalidraw.com
这一个源的本地服务，然后打开：

```text
https://excalidraw.com/#url=http://localhost:8789/x.excalidraw
```

`#url=` 是 Excalidraw 的"从外部 JSON 地址导入场景"（PR #2726，无官方 UI 入口）。
**实测结果**：官网把 23 个元素全部加载进画布、可以直接接着画；加载完 app 会自己把
hash 清掉。

**两个坑（都踩过）**：

- `file://` fetch 不到（浏览器不让）。
- excalidraw.com 去 fetch localhost **需要 CORS 头**（`http.server` 不发，现象是
  "打开后一直空白"），所以脚本自己包了一层。

**在 Obsidian 插件里不需要它** —— 文件放进 vault 双击即可。

## 三、⚠ 限制：Excalidraw 会自己重新排版文字

`text_metrics` 的尺寸是我们对"文字占多大"的**推算**，而容器绑定的文字在 Excalidraw
里**由它自己按真实字体重新断行** —— **渲染器是第二个尺寸来源，不在我们控制之内。**
断行不一样多出一行，容器就被撑高、布局随之偏移。

**所以：规格与校验全绿不等于渲染出来就是那样。** 已实测的结论与它的边界见
`references/validation.md` 第六节。

这条是**这个后端特有**的：drawio 后端把折行写死成 `&lt;br&gt;`，渲染器不重折
（代价是用户在 drawio 里编辑文字时行宽不再自适应）。

**一个例外**：带图标的节点、以及**带说明（`detail`）的节点**，文字都是**自由文字**
（`containerId: None`）—— 图标的理由见下一节；说明的理由是一个硬约束：

> **一个容器只能有一个绑定文字。** Excalidraw 只画第一个（`getBoundTextElement` 取首个），
> 所以标题绑了容器，说明就是**写在 JSON 里也不会被画出来**。
> 2026-09-16 实测发现：之前所有带 `detail` 的图，真实渲染里都只有标题。
> 修复：有说明时标题与说明**一起**自由放置（两个绑定文字还会互相压住：
> 标题被拉回容器中心，说明按我们算的位置落在旁边）+ 同挂一个 groupId。
> 这条现在有**场景级不变量测试**钉着（任何容器最多一个绑定文字）。

这也是“自研预览与真实渲染不一致”的一个典型：预览会把两个文字都画出来，
JSON 也看不出问题，只有官方渲染器才暴露出来。

## 四、自由文字还是绑定文字（带图标的节点例外）

实测（真实 excalidraw.com + 官方导出）：绑定到容器的文字**总在容器中心**，我们写进去
的 x/y 只影响预览，渲染器一律重算。于是"图标 + 文字整组居中"在**绑定**前提下数学上
做不到：文字被钉在容器中心，图标只能贴在可见文字左边，整组重心必然偏左
`(图标宽 + 间隔) / 2`。实测 19px，在 300px 宽的节点上是 6% —— 用户一眼就看出来了
（原话："图标和文本，不应该居中吗？"）。

**现在的做法：带图标的节点，标签解绑**（自由文字，位置我们自己算），而且形状 /
图标 / 标签**同挂一个 groupId** —— 在 Excalidraw 里拖动、缩放仍然是一体。
实测定位：我们写 145.6，官方导出出来就是 145.6（自由文字不被重算）。

**代价（明写在前面）**：解绑后改标签不会自动重排，缩放节点也不会自动重折行。
所以这条路**只给带图标的节点用** —— 没图标的节点没有任何理由付这个代价，保持绑定。

认节点的判据也随之改了：**看 id（`node-<nid>`），不看有没有 groupId**。
旧判据"有 groupId 的就不是节点"在分组之后不再成立。

## 五、看真实渲染：官方导出（首选）与自研预览（备胎）

**官方导出**：`dev-tools/export_excalidraw.py` 走 Excalidraw **官方**导出的那条路
（`@excalidraw/utils` 的 `exportToBlob` / `exportToSvg`），在无头 Chrome 里跑，
出 PNG / SVG —— 这是**真实渲染器**出的图，构造上不可能与 Excalidraw 不一致：

```sh
python3 dev-tools/export_excalidraw.py x.excalidraw -o x.png --svg x.svg --scale 2
python3 dev-tools/export_excalidraw.py x.excalidraw -o x.png --width 1600 --height 900
python3 dev-tools/export_excalidraw.py x.excalidraw -o x.png --aspect 16:9
```

**固定宽高 / 固定比例**（都是实测出来的语义，不是猜的）：

| 想要 | 怎么写 | 实测行为 |
| --- | --- | --- |
| 固定宽高 | `--width 1600 --height 900` | 出图**精确** 1600×900。内容**容纳缩放**（不拉伸）、居中，不足的边补背景色 |
| 只固定一边 | `--width 1600` | 另一边按内容比例跟上（1600×949）—— 官方语义 |
| 固定比例 | `--aspect 16:9`（可配 `--width`/`--height`） | 画布往"比例不够"的那一轴**只加白**：实测内容保持原大小（容纳系数 = 1）、多出来的地方是底色 |

两条路的关键差异（实测）：**PNG 认 `config.width/height`，SVG 忽略它** —— 所以
`export_excalidraw.py` 里 SVG 那条是 Python 端改根节点（`width`/`height`/`viewBox` +
背景板 rect），改不动就报错而不是给你一张比例不对的图。回执里的尺寸是**从产物里量出来的**
（PNG 读 IHDR），不是我们自报的数。

**自研预览**：`dev-tools/preview.py` 画的是我们**自己的布局模型**（与 `layout.py`
同源），所以它**在构造上**看不见"渲染器与我们的模型不一致"这类问题，尤其是上面
第三节那种重折。它需要 PIL、零外部依赖，适合快速看结构/疏密/颜色比例；
但它**不能替代**官方导出。

两者与三档声明的关系：官方导出属于"渲染证据"那一档（可复现、可脚本化），
**感知审查（好不好看、讲没讲清楚）仍然只能由人做** —— 脚本出的图再真，
也不能自证好看。
