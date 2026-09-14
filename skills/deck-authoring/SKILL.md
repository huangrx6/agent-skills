---
name: deck-authoring
description: >-
  Build slide decks with a risograph print look (套色错位 + 颗粒 + 半调网点) from a
  structural spec. Pipeline: deck-spec.json → HTML → 每页 PNG → 16:9 PPTX. Use when the
  user asks 做一个 riso 风的 deck / 做一份孔版印刷感的 slide / 来个双色叠印的版式 deck /
  a riso-style deck for a product review. The model writes only the spec content
  (titles, bullets, colorSet, seed); scripts compute every coordinate, halftone, and
  contrast check. Do NOT use for editable PowerPoint authoring (output is rendered
  PNGs, text cannot be edited in the PPTX), for chart-only deliverables, or for
  non-riso visual styles.
---

# Deck authoring（riso 风）

把一份 `deck-spec.json` 渲成接近真实孔版印刷的 deck：套色错位、颗粒、半调网点、
两墨叠印成深色当正文。**你只写 spec，脚本算一切坐标与样式。**

## 为什么不能让你写坐标或色值

字号、折行、错位量、网点密度、对比度 —— 都是几何 / 颜色计算。让模型直接吐数字，
本质是让它做它不可靠的事，症状必然是"看起来差不多，但深色文字达不到正文对比度"
（原型实测：主 / 副色单独当文字色只有 2.35 / 2.68 ✗）。所以：

- 规格 schema 里**没有**色值字段、字号字段、坐标字段 —— 不存在，不是"不推荐填"。
  手写它们会被 `validate_spec.py` **直接判失败**（字段集封闭），不是静默忽略 ——
  静默最坏：模型以为写进去了，出的图却没变，于是跑去改别的地方。
- 文字色**只能**是 overprint（两墨叠印）；`check.py` 第 ① 条会拦"主 / 副色声明当文字色"。

换色板只改 `styles/risograph/style.json`，spec 与渲染器零改动。

## 起手流程

1. **先读 demo**：`dev-tools/demo.spec.json` —— spec 该写哪些键以它为准
   （逐键说明见 `references/style-architecture.md`；写完先跑 `validate_spec.py` 过字段集）。
2. **写 spec**：每页只有 `type` + 内容（标题 / 条目 / 时间点 / 数据），见
   `references/style-architecture.md`。`seed` 建议显式写（不写默认 1）—— 错位与颗粒
   按 (seed, 元素) 派生，不靠全局 random（两次渲染不重 = 没法回归、也没法复现）。
3. **四道门**（顺序有意义：先验输入，再渲，最后验产物）：
   - 规格：`python3 scripts/validate_spec.py your.spec.json`（字段集封闭，未知键直接失败）
   - 墨色：`python3 scripts/ink.py styles/risograph/style.json`（任一色板不达标退出 1）
   - 渲染：`python3 scripts/render.py your.spec.json -o out.html`
   - 产物：`python3 scripts/check.py your.spec.json out.html`（六项机械校验全过退出 0）
4. **可选交付**：
   - PNG 截图：`python3 scripts/shots.py out.html --out-dir pages/ --count N`
   - PPTX：`python3 scripts/make_pptx.py --png-dir pages/ -o deck.pptx`
5. **图页**：先 `python3 scripts/image_source.py --prompt "…" -o pic.png` 出图，
   再把文件名写到 spec 的 `image` 字段。几何色块拼贴是默认（无 provider），
   它本身就是 riso 的，不是灰占位图。

## 版式

`type` 字段支持：

| type | 用途 | 装饰墨块 | 风险点 |
| --- | --- | --- | --- |
| `title` | 封面 | ✓ | 副标题一行内 |
| `content-text` | 全文页 | ✓ | 条目估算宽 > 内容区会判溢出 |
| `content-image` | 图文页（左文右图） | ✗ | 图必须是 duotone + 半调产物 |
| `two-column` | 双栏 | ✗ | 每栏 660px；栏标色带是专色，正文仍叠印 |
| `timeline` | 时间线 | ✗ | 每格 300px；时间点独立错位 |
| `chart` | 柱状图 | ✓ | **柱与刻度不带错位**（riso 只做容器与页角墨块） |
| `end` | 收尾 | ✓ | 居中大字 |

`check.py` 按版式给不同的可用宽度上限（标题 / 全文用满宽，图左 820、双栏 660、
时间线 1320）—— 用同一个宽度判，必然一边误报一边漏报。

## Do NOT

- **不要在 PPTX 里改字**：每页是一张贴图，改不了字；要改字回改 spec 再重出。
  想要"能改字的 pptx"必然牺牲 riso 效果（原生 shapes 做不出套色错位 / 颗粒 / 网点），
  两条路不能兼得 —— 这个 skill 选了视觉。
- **不要调阈值放宽对比度门禁**：4.5 / 3.0 是无障碍底线；不达标就该换色板。
  `style.json` 里 `ink.rule` 已经写了"每套色板必须含一个深墨" —— 两墨都亮就压不深。
- **不要在 spec 里写 `color: <hex>`**：`color` 字段只接受 `"overprint"`；主 / 副色
  单独写 `color` 会被 `check.py` 第 ① 条判失败。
- **不要把生图模型的彩照直接塞进 image 字段**：必须先走 `image_source.py`，
  否则 check 不会有事，但视觉上立刻露馅（方案 §2 图文页那条）。
- **不要绕过 ink.py 的派生去手写叠印色**：颜色 = `overprint(primary, secondary)`，
  写死 `#xxxxxx` 在改色板时会"看起来没变"（实际已变），调试半天找不出原因。

## 出错时去哪查

- **`validate_spec.py` 说某个字段不存在** → 那是刻意不留的三类（坐标 / 字号 / 色值）。
  按它给的专门说明改：版式用 `type` 表达，换色板改 `styles/risograph/style.json`。
  **别把字段删了就交差** —— 先想清楚本来想表达什么。
- **对比度不达标** → `python3 scripts/ink.py styles/risograph/style.json` 看三套色板
  各自的叠印墨对比度；不达标的换色板，不要改 `contrast.minBody`。
- **"第 N 页 X 估算宽 > 该版式上限"** → `references/validation.md` 第 ② 条，
  按版式上限收字 / 拆行 / 缩字号。
- **错位值越界** → 检查 spec 里没硬塞 `--dx/--dy/--rot`；这些只能由脚本派生。
- **装饰压文字** → `references/validation.md` 第 ④ 条；墨块必须落在右侧两角。
- **图表柱高不成比例** → 数据 `value` 是不是数字、是不是都被图渲染了；
  `references/validation.md` 第 ④ 条里"两两比例"那段解释了为什么不按峰值归一。
