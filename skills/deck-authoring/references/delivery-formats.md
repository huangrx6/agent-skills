# 交付格式的取舍

一条流水线，三种交付物：`out.html` / `pages/*.png` / `deck.pptx`。
这条决策线是 #77 拍下来的，写在这里给后人读。

## HTML

**是什么**：浏览器可直接打开的整页 deck（每页一个 `<section class="slide">`，垂直堆叠）。

**什么时候用**：

- 在交付前**自己看效果**（浏览器 DevTools 调字号、查对比度最快）
- 嵌入网页 / Notion / 飞书云文档（HTML 是这三处都能吃的东西）
- 给做评审 / 改稿的人发链接

**什么时候不用**：

- 要带去会议现场演示 —— 投影接电脑看浏览器容易被打断（弹通知、切窗口）
- 要存档发给别人反复看 —— 纯 HTML 没有"页"的概念

## PNG（每页一张）

**是什么**：用系统 Chrome headless 模式截的 1600×900 2x 分辨率 PNG。

**什么时候用**：

- 进 PPTX（一页一张贴图 —— 见下）
- 归档（PNG 不会因浏览器升级而渲染漂移；五年前的截图今天打开还是那个样子）
- 发给别人"看一眼"（PNG 不需要对方有浏览器）

**依赖**：macOS 上 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`。
**不装 Playwright**：原生 `--headless=new --screenshot` 就够，多装一份纯属浪费
（实测一次跑 6 页 ≈ 8 秒，瓶颈是 Chrome 启动不是 PIL）。

**2x 缩放**：投影 / 打印不糊。`shots.py` 里 `--force-device-scale-factor=2`，
截图后按 1600×900×2 实际像素裁开，每页产物仍是 1600×900 物理像素 × 2 倍 DPI。

## PPTX

**是什么**：16:9 pptx，每页**一张满版贴图**（不是 native shapes）。

**什么时候用**：

- 带去现场演示（PPT 切页不会被打断、不用担心字号自适应）
- 给非技术受众 / 客户演示（"PPT"是他们的默认预期）

**已知限制**（**这是设计，不是 bug**）：

- **改不了字**：每页是一张图，要改字回改 `deck-spec.json` 再重渲再重截。
- **改不了图**：同上。
- **改不了版式**：同上。

**为什么是贴图而不是 native shapes**：riso 的识别点（套色错位、颗粒、半调网点）
在 pptx 原生形状里做不出原味 —— 浏览器渲染是唯一能 100% 还原的路径。

**要"能改字的 pptx"**只能走 native shapes，效果必然打折（没有错位、没有网点、
颗粒要么走纹理填充要么没有）—— 两条路**不能兼得**。

这个 skill 选了"视觉做到极近真实孔版"。如果某个 deck 真的需要对方改字，
那它就不该用这个 skill 出 —— 用 PowerPoint 自己做一个普通的。

## 三种交付物的相互依赖

```
deck-spec.json ─┐
                ├──→ render.py ──→ out.html ──→ shots.py ──→ pages/*.png ──→ make_pptx.py ──→ deck.pptx
style.json  ───┘            │
                            └──→ check.py（验 HTML，对 PNG 产物里读 HTML 已有
                                          的字段再核一次 —— 同一份事实两个视角）
```

`check.py` 是**对 HTML 跑的**，不是对 PNG 跑的。但它会从 PNG 的产物上下文里读
（错位区间从 HTML 里读，柱高从 HTML 里读）—— 同一份事实两个视角，避免
"渲染器自觉"导致的自检失效。

## 关于"为什么不直接给 PDF"

PPT 想要 + Web 想要 + 打印想要，加 PDF 听起来对。但：

- PDF 是**静态**的 —— 客户不能像看 PPT 那样切页看（演示用 PPT 顺手）
- PDF **改版式**要重出（演示者改不了字号），同上 PNG 的局限
- PDF 在飞书 / Notion / Slack 里要预览，**没有 PPTX 顺手**

PPT + Web（HTML / Notion 嵌入）覆盖了 90% 的实际使用场景。
如果某天真的需要 PDF，`make_pptx.py` 之后接 `libreoffice --headless --convert-to pdf`
就够 —— 但目前没有真实需求驱动这个加法，**别为了"完整性"加**。
