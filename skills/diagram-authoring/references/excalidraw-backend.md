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

## 四、容器绑定文字为什么不能解绑

实测（真实 excalidraw.com）：绑定到容器的文字**总在容器中心**，我们写进去的 x 只影响
预览。所以"图标 + 文字整体居中"在数学上做不到 —— 强行居中会让图标和文字叠在一起。
能做且正确的是：图标**紧贴可见文字的左边**。代价是整组视觉重心偏左
`(图标宽 + 间隔) / 2 ≈ 19px`（在 300px 宽的节点上是 6%，基本看不出来）；
换成"把文字解绑"能完美居中，但拖动节点时文字会留在原地 —— 那是功能倒退。

## 五、`dev-tools/preview.py` 看到的是什么

它画的是我们**自己的布局模型**（与 `layout.py` 同源），所以它**在构造上**看不见
"渲染器与我们的模型不一致"这类问题，尤其是上面第三节那种重折。它能判断结构一眼能不能
看懂、排版顺不顺眼、颜色比例、节点疏密、连线走向、标签有没有压节点；**它不能替代真实
Excalidraw**。需要 PIL，属于给人目视复核用的，不在运行时链路上。
