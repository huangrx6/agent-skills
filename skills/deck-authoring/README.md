# deck-authoring — 把结构化内容渲成能讲的 deck

把一份 `deck-spec.json` 渲成演示 deck，**风格从 `styles/` 选**（一种风格 = 一个目录），
交付 HTML（可演讲）/ 矢量 PDF / 可编辑 PPTX / 每页 PNG。

## 这是什么 / 不是什么

- 这是「**内容只管写，版面与颜色脚本算**」的 skill —— 字号、折行、对比度、
  条目密集页的字号自适应、四种风格的适配，全部由脚本管。
- 它**不是**单一风格的：`styles/` 下现在有 4 套（黑底剧场 / 瑞士栅格 / 大字报 /
  笔记本），加一套 = 拷一个目录改 token 与 CSS，不改任何 .py。
- 它**不是**只能出死图的：HTML 自带走演示态（键盘翻页 / 缩放 / 页码），
  而且能用 `pptx_native.py` 出**字能改**的 PPTX。
- 它**不是**通用图表工具 —— 数据图表只支持柱状图，且风格处理只作用于容器，
  柱与刻度保持干净（错位会毁掉可读性）。
- 它**不是**「换个 css 滤镜」—— duotone + 半调是「重新制版」，不是「加滤镜」。

## 跑法（最快路径）

```bash
cd skills/deck-authoring/
python3 scripts/validate_spec.py dev-tools/demo.spec.json           # 1) 规格（字段集封闭）
python3 scripts/ink.py styles/swiss-grid/style.json                # 2) 墨色门禁
python3 scripts/plate.py --sample -o sample-treated.png             # 3) 造演示图
python3 scripts/render.py dev-tools/demo.spec.json -o out.html      # 4) 出 HTML
python3 scripts/measure.py out.html                                 # 5) 实测（真浏览器）
python3 scripts/check.py dev-tools/demo.spec.json out.html          # 6) 校验
python3 scripts/pdf.py out.html -o deck.pdf                         # 7) 矢量 PDF
python3 scripts/shots.py out.html --out-dir pages/ --count 6        # 8) 截图（要 Chrome）
python3 scripts/make_pptx.py --png-dir pages/ -o deck.pptx          # 9) 出 PPTX（贴图，观感 100%）
python3 scripts/pptx_native.py out.html -o deck-editable.pptx       # 10) 出 PPTX（原生，能改字）
python3 scripts/animate.py out.html -o deck.mp4                     # 11) 出视频（另有 GIF）
```

第 11 步不需要 ffmpeg：取帧走 Chrome DevTools Protocol（一次启动截几百帧，比一帧一个
`chrome --screenshot` 快 51 倍），H.264 编码走 macOS 自带的 AVFoundation，GIF 走 Pillow。
抽几帧看看再编：`--stills 0,1.5,22.4,32.3`。运动设计与什么时候该用视频，见
`references/animation.md`。

第 3 步是给 demo 的图文页造图：`demo.spec.json` 的 `image` 是个占位文件名，
不先生成它就是一张裂图。要换成真照片走 `image_source.py`（再改 spec 里的文件名）。
该产物**不入库**（见「已知限制」第 7 条）。

## 测试

```bash
python3 -m unittest discover -s tests/deck-authoring -v     # 81 条
```

钉住十四项不变量：同 spec + 同种子字节一致（带随机区间的风格；确定性风格本就与 seed 无关）、
色板门禁 + 两墨乘叠印的数学、校验的变异验证（每项都造违规样例）、半调墨覆盖率随灰度单调、
缓存命中后仍过色板三角不变量、外壳行为（真开浏览器按键翻页 + letterbox 缩放比贴边不溢）、
PDF 是矢量且页数/页尺寸对、可编辑 PPTX 的**字是真字**且坐标是页内坐标、
字体提示不报废话、**每种风格的装饰落点与它声明的 `decor.types` 一致**、SKILL.md 的版式表与
`render.py` 实测行为一致、规格字段集真的封闭（坐标/字号/色值必须被指名报出）、
**同一个 t 两次独立浏览器会话取到的帧逐字节一致**（且不同 t 必须真的不同 —— 否则上一条
会假绿）、渲染路径上没混进 CSS `transition`。

## 依赖

- Python ≥ 3.10（用了 `from __future__ import annotations` + importlib 动态加载同目录脚本）
- `Pillow`（duotone + 半调）
- `python-pptx`（PPTX 拼装）
- macOS 上 `shots.py` 需要 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- **导出视频不需要 ffmpeg / gifsicle / ImageMagick**：用系统已有的三件 —— Chrome（取帧）、
  `swiftc` + AVFoundation（H.264）、Pillow（GIF）。CDP 的传输走 `websockets`（装了就走快
  路径；没装会说清代价后降级，不静默变慢）。
- 不要装 Playwright —— `--headless=new --screenshot` 就够，多装一份纯属浪费

## 已知限制

1. **贴图版 PPTX 改不了字**：要能改字就走 `pptx_native.py`（原生 shapes）。两者取舍见 `references/delivery-formats.md`。
2. **图表只支持柱状图**：折线 / 饼 / 散点都没有；柱高必须与数据成比例是硬要求
   （由 `check.py` 第 ④ 条独立复核，不是渲染器自觉）。
3. **错位只用在标题 / 时间点**：其他地方用错位会毁可读性（方案第 2 层）。
4. **生图是可选**：`image_source.py` 默认走色块拼贴（它本身就是版画式的拼贴），
   不配 `--provider-cmd` 永远不会调生图模型 —— 这是设计不是疏漏。
5. **缓存命中不等于可信**：缓存里的图也会过"只在色板三角形内"的不变量，
   塞彩图会被拒绝并丢弃重做。
6. **同 spec + 同种子 = 字节级一致**：用 random.Random(seed, parts) 派生错位 / 颗粒，
   不是全局 random。如果改了 seed 输出没变，多半是 spec 里没把 seed 传进去。
7. **demo 的图文页要先造图**：`dev-tools/demo.spec.json` 的 `image` 是占位文件名，
   按「跑法」跑一遍才有图。产物是本地文件，不进仓库（仓库只收文本 + 两个 SVG 图标）。
8. **IO 收在 `deckio.py`（一个刻意留的例外）**：读 / 写 / 数字解析全走那里。例外是
   `validate_spec.py` —— 它的职责就是用退出码 2 报「输入有问题」，所以要自己分辨
   「读不到」和「不是合法 JSON」（两者给用户的信息不一样），合并了反而变差。

## 仓库布局

```text
skills/deck-authoring/          # 可消费面：AI 调用 skill 时读的就是这棵树的这部分
├── SKILL.md                 # 给模型看的触发条件 + 流程
├── README.md                # 给"想跑一下"的人看的
├── scripts/                 # 流水线十三件（另有 1 个 Swift 编码器）
│   ├── validate_spec.py     # 输入层校验：字段集封闭（坐标/字号/色值直接判失败）
│   ├── ink.py               # 墨色推导 + 三色板门禁（唯一消费者）
│   ├── plate.py             # 图片 → duotone + 半调（制版）
│   ├── image_source.py      # 缓存 / 生图 / 几何色块拼贴
│   ├── render.py            # deck-spec.json → HTML（语义骨架 + 风格 skin + 演示壳 + 运动引擎）
│   ├── measure.py           # 实测层：真浏览器量真盒子（不估算）
│   ├── check.py             # 校验：越界/裁切/对比度/图表/图片/报错
│   ├── pdf.py               # HTML → 矢量 PDF（并验页数/页尺寸/位图/字体）
│   ├── shots.py             # HTML → PNG（系统 Chrome 截图）
│   ├── make_pptx.py         # PNG → PPTX（贴图版）
│   ├── pptx_native.py       # HTML → PPTX（原生 shapes，字能改）
│   ├── animate.py           # HTML → MP4 / GIF（逐帧 seek 录制，可复现）
│   ├── h264_encode.swift    # 帧序列 → H.264（AVFoundation，无需 ffmpeg）
│   └── deckio.py            # IO 收口（try/except 不散落）
├── styles/                   # 风格目录：一种风格 = 一个目录（token + skin），不碰 .py
│   ├── keynote-dark/         # 黑底剧场：纯黑底 + 巨号字 + 一屏一观点（大胆·暗）
│   │   ├── style.json        #   token：色板 / 字号级数 / 字体 / 纹理 / 装饰 / 错位 / 对比度
│   │   └── skin.css          #   视觉层：颜色、字体、纹理、装饰观感
│   ├── swiss-grid/           # 瑞士栅格：白底 + 编号列表 + 左轨 + 巨号页码（安静·冷）
│   ├── billboard/            # 大字报：巨号数字 + 通栏色条 + 色场（大胆·亮）
│   └── notebook/             # 笔记本：横格纸 + 红边线 + 侧边索引签（中性·暖）
├── dev-tools/
│   └── demo.spec.json       # 一份能跑的样例
├── evals/evals.json         # 行为评估用例
└── references/
    ├── style-architecture.md    # 多风格 seam、字段集
    ├── validation.md            # 校验的口径（阻塞 vs 提示）
    ├── delivery-formats.md      # HTML / PDF / PNG / PPTX / MP4 的取舍
    └── animation.md             # 运动设计、取帧的确定性、视频导出
tests/deck-authoring/           # 测试住在仓库顶层（不在 skill 目录里）
├── test_ink.py
├── test_determinism.py
├── test_check_mutations.py
├── test_halftone_monotonic.py
├── test_cache_invariant.py
├── test_skill_md_consistency.py
├── test_validate_spec.py
├── test_shell.py
├── test_pdf.py
├── test_pptx_native.py
├── test_font_advisory.py
└── test_animation.py
```

测试**刻意不放在 skill 目录里** —— AI 调用 skill 时读的是 `skills/deck-authoring/`
那棵树，测试放进去会被顺手读走；同理 `SKILL.md` 与 `references/*.md` 里也不许
出现指向测试的指针（`validate_skill.py` 会把那种回流判为失败）。

## 跟外层仓库的关系

- 同目录模块用 `importlib.util` + `sys.modules` 加载（见 `_load_sibling`），
  不靠 `sys.path.insert` —— 这条 Pyright 才会过。
- IO 走 `deckio.py`（读 / 写 / 数字解析一处收口，自然带上 try/except）。唯一的例外是
  `validate_spec.py`，它要自己分辨「读不到」与「不是合法 JSON」才能给出对的退出码。
- **确定性地基**：产物里 `window.__deck_timeline` / `__deck_motion` 跟 HTML 一起走，
  所以 `animate.py` 不需要 spec、也不需要 style.json —— 给的 HTML 就是唯一事实来源。
- 渲染层不写死任何颜色 / 尺寸 —— 全从 `style.json` 注入，CSS 里只有 `var()`。
