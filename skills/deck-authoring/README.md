# deck-authoring — riso 风的 slide deck 工具集

把一份结构化的 `deck-spec.json` 渲成 risograph 印刷风的 deck，最终交付物
是 16:9 PPTX（一页一张贴图）。

## 这是什么 / 不是什么

- 这是「**视觉做到极近真实孔版**」的 skill —— 套色错位、颗粒、半调网点、
  两墨叠印成深色当正文色。
- 它**不是**「能改字的 PowerPoint 编辑器」—— PPTX 里每页是一张 PNG 贴图，
  字改不了；要改字就回改 spec 再重出。
- 它**不是**通用图表工具 —— 数据图表只支持柱状图，且 riso 效果只作用于容器，
  柱与刻度保持干净（错位会毁掉可读性）。
- 它**不是**「换个 css 滤镜」—— duotone + 半调是「重新制版」，不是「加滤镜」。

## 跑法（最快路径）

```bash
cd skills/deck-authoring/
python3 scripts/validate_spec.py dev-tools/demo.spec.json           # 1) 规格（字段集封闭）
python3 scripts/ink.py styles/risograph/style.json                  # 2) 墨色门禁
python3 scripts/plate.py --sample -o sample-treated.png             # 3) 造演示图
python3 scripts/render.py dev-tools/demo.spec.json -o out.html      # 4) 出 HTML
python3 scripts/measure.py out.html                                 # 5) 实测（真浏览器）
python3 scripts/check.py dev-tools/demo.spec.json out.html          # 6) 校验
python3 scripts/pdf.py out.html -o deck.pdf                         # 7) 矢量 PDF
python3 scripts/shots.py out.html --out-dir pages/ --count 6        # 8) 截图（要 Chrome）
python3 scripts/make_pptx.py --png-dir pages/ -o deck.pptx          # 9) 出 PPTX
```

第 3 步是给 demo 的图文页造图：`demo.spec.json` 的 `image` 是个占位文件名，
不先生成它就是一张裂图。要换成真照片走 `image_source.py`（再改 spec 里的文件名）。
该产物**不入库**（见「已知限制」第 7 条）。

## 测试

```bash
python3 -m unittest discover -s tests/deck-authoring -v     # 50 条
```

钉住九项不变量：墨色推导 + 三套色板门禁、同 spec + 同种子字节一致、校验的
变异验证（每项都造违规样例，且变异替换的是产物里**真实存在**的值）、半调墨覆盖率
随灰度单调（100% → 0%）、缓存命中后仍过色板三角形不变量、外壳行为（真开浏览器
按键翻页 + letterbox 缩放比贴边不溢）、PDF 是矢量且页数/页尺寸对（连"删掉 @page
能不能拦"都有用例）、SKILL.md 的版式表与
`render.py` 实测行为一致、规格字段集真的封闭（坐标/字号/色值必须被指名报出）。

## 依赖

- Python ≥ 3.10（用了 `from __future__ import annotations` + importlib 动态加载同目录脚本）
- `Pillow`（duotone + 半调）
- `python-pptx`（PPTX 拼装）
- macOS 上 `shots.py` 需要 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- 不要装 Playwright —— `--headless=new --screenshot` 就够，多装一份纯属浪费

## 已知限制

1. **PPTX 里改不了字**：见上。要可编辑 PPT 就走原生 shapes，riso 效果必然打折。
2. **图表只支持柱状图**：折线 / 饼 / 散点都没有；柱高必须与数据成比例是硬要求
   （由 `check.py` 第 ④ 条独立复核，不是渲染器自觉）。
3. **错位只用在标题 / 时间点**：其他地方用错位会毁可读性（方案第 2 层）。
4. **生图是可选**：`image_source.py` 默认走色块拼贴（它本身就是 riso 的），
   不配 `--provider-cmd` 永远不会调生图模型 —— 这是设计不是疏漏。
5. **缓存命中不等于可信**：缓存里的图也会过"只在色板三角形内"的不变量，
   塞彩图会被拒绝并丢弃重做。
6. **同 spec + 同种子 = 字节级一致**：用 random.Random(seed, parts) 派生错位 / 颗粒，
   不是全局 random。如果改了 seed 输出没变，多半是 spec 里没把 seed 传进去。
7. **demo 的图文页要先造图**：`dev-tools/demo.spec.json` 的 `image` 是占位文件名，
   按「跑法」跑一遍才有图。产物是本地文件，不进仓库（仓库只收文本 + 两个 SVG 图标）。
8. **IO 还没走 `deckio.py`**：那个模块是按仓库「调用文件 IO 必须有 try/except」
   那条约定预留的收口点，但**目前没有任何脚本用它** —— 也就是说那条约定现在**没被满足**
   （`open()` / `json.load()` 直接散在 check / render / plate / image_source / ink 里）。
   这是已知缺口，不是设计选择：见下方「跟外层仓库的关系」。

## 仓库布局

```text
skills/deck-authoring/          # 可消费面：AI 调用 skill 时读的就是这棵树的这部分
├── SKILL.md                 # 给模型看的触发条件 + 流程
├── README.md                # 给"想跑一下"的人看的
├── scripts/                 # 流水线十一件
│   ├── validate_spec.py     # 输入层校验：字段集封闭（坐标/字号/色值直接判失败）
│   ├── ink.py               # 墨色推导 + 三色板门禁（唯一消费者）
│   ├── plate.py             # 图片 → duotone + 半调（riso 制版）
│   ├── image_source.py      # 缓存 / 生图 / 几何色块拼贴
│   ├── render.py            # deck-spec.json → HTML（语义清单 + 演示壳 + 打印 CSS）
│   ├── measure.py           # 实测层：真浏览器量真盒子（不估算）
│   ├── check.py             # 校验：越界/裁切/对比度/图表/图片/报错
│   ├── pdf.py               # HTML → 矢量 PDF（并验页数/页尺寸/位图/字体）
│   ├── shots.py             # HTML → PNG（系统 Chrome 截图）
│   ├── make_pptx.py         # PNG → PPTX
│   └── deckio.py            # IO 收口（try/except 不散落）
├── styles/risograph/
│   └── style.json           # 色板 / 错位 / 颗粒 / 字体 token
├── dev-tools/
│   └── demo.spec.json       # 一份能跑的样例
├── evals/evals.json         # 行为评估用例
└── references/
    ├── style-architecture.md    # 多风格 seam、字段集
    ├── validation.md            # 校验的口径（阻塞 vs 提示）
    └── delivery-formats.md      # HTML / PDF / PNG / PPTX 的取舍

tests/deck-authoring/           # 测试住在仓库顶层（不在 skill 目录里）
├── test_ink.py
├── test_determinism.py
├── test_check_mutations.py
├── test_halftone_monotonic.py
├── test_cache_invariant.py
├── test_skill_md_consistency.py
├── test_validate_spec.py
├── test_shell.py
└── test_pdf.py
```

测试**刻意不放在 skill 目录里** —— AI 调用 skill 时读的是 `skills/deck-authoring/`
那棵树，测试放进去会被顺手读走；同理 `SKILL.md` 与 `references/*.md` 里也不许
出现指向测试的指针（`validate_skill.py` 会把那种回流判为失败）。

## 跟外层仓库的关系

- 同目录模块用 `importlib.util` + `sys.modules` 加载（见 `_load_sibling`），
  不靠 `sys.path.insert` —— 这条 Pyright 才会过。
- IO **目前散在各脚本里**（`with open(...)` 管关闭），**没走** `deckio.py` ——
  那个模块是为此预留的收口点，却一次都没被用上。所以仓库那条「调用文件 IO 必须有
  try/except」的约定**目前没被满足**，详见「已知限制」第 8 条。
- 渲染层不写死任何颜色 / 尺寸 —— 全从 `style.json` 注入，CSS 里只有 `var()`。
