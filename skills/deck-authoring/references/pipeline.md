# 制作管线

当前实现以 spec、项目风格与品牌为输入，生成 HTML，再通过真实浏览器测量和格式导出完成交付。
这是执行地图；内容如何组织见 [内容规划](content-intelligence.md)，字段见 [样式与规格契约](style-architecture.md)。

## 输入与产物

```text
来源材料 → 事实与页序规划 → deck.spec.json
                            + styles/<name>/{style.json,skin.css}
                            + brands/<name>/brand.json（可选）
                            + 图片/资产清单（可选）
              ↓ validate_spec
              ↓ deck.resolve_theme / compile_spec
              ↓ render_resolved
           deck.html → 浏览器测量 → check + 目视审稿
              ↓ 按需导出 PDF / PNG / PPTX / MP4 / GIF
```

`deck.py` 统一合并品牌字体/色板、解析资产引用与档位，记录 trace。
`render.py` 负责页面结构、样式注入和 G2 图表；浏览器负责最终文字与 CSS 几何。
`--resolved` 会额外启动测量，保存语义清单与真实几何，供原生 PPTX 使用；它不是无需浏览器的纯编译选项。

没有独立的 content.json / storyline.json / pageplan.json 解析器，也没有自动事实核查器。
简单 deck 可直接用页序表规划；复杂项目可保存中间说明，但无需为流程额外交三份 JSON。

## 建议顺序

1. 确认观众、观看场景、结论和所需格式；整理证据与缺口。
2. 已有风格则沿用；探索方向时用同一内容做真实代表页，包含密集页与图表页。
3. 建立 spec 与项目风格，运行输入校验和 token 对比度预检。
4. 需要素材时生成槽位合同，取得真实/生成素材并验收；已有素材无需重新生成。
5. 渲染 HTML，运行 check；看整套缩略图和关键页实际尺寸，修内容、版式或风格。
6. 只导出用户需要的格式；回读最终文件，检查页数、字体、图表、裁切与播放时长。

## 常用命令

从 skill 目录执行，路径换成当前项目，N 换成实际页数；HTML 默认与 spec 同目录，避免相对素材路径改变：

```sh
python3 scripts/validate_spec.py /project/deck.spec.json
python3 scripts/ink.py /project/styles/project-style/style.json
python3 scripts/render.py /project/deck.spec.json -o /project/deck.html --resolved /project/resolved.deck.json --trace
python3 scripts/check.py /project/deck.spec.json /project/deck.html --resolved /project/resolved.deck.json
python3 scripts/shots.py /project/deck.html --out-dir /project/pages --count N
```

素材流程见 [images.md](images.md)，格式命令和依赖见 [delivery-formats.md](delivery-formats.md)
与 [README](../README.md)。没有图文页时不必运行素材工具，只交 HTML 时不必导出全部格式。

## 调整模式是独立步骤

`render --contract`、`--candidates/--pick/--picks`、`--repair` 相互排斥，不能一次叠加。

| 模式 | 实际功能 | 边界 |
| --- | --- | --- |
| `--contract` | 按结构跨度与字号估算文字容量 | 不能代替真实字体测量 |
| `--candidates` | 对未指定 layout 的图文/双栏页试排、实测评分、输出对比页 | 不自动判断论证是否合适 |
| `--pick` / `--picks` | 自动择优或应用对比页选择，另存 spec | 不能改数据来凑版式 |
| `--repair` | 至多四轮，尝试未声明的标题/条目档位下降 | 不改文案、拆页、重写 CSS 或实现所有修复建议 |

详细用法见 [layout-system.md](layout-system.md)。候选和 repair 产物仍要重新 check 与目视审稿。
修复成功只表示对应信号消除，不能作为整套验收结论。

## 可复现与环境

相同输入、seed、版本与资源可重复编译；字体、浏览器、图片或 CSS 变化会改变实测结果。
图表等待 `window.__deck_charts_ready`；图片和字体也必须完成加载。不能仅凭 canvas 存在就判断图表完整。

工具存在测量/素材缓存；修改外部资源后确认产物已重渲，并重新生成依赖它的 resolved。
HTML 默认可能引用图片与本地字体；`fonts.py --embed` 只内嵌字体，不能称为全资源打包器。
PDF 中 Canvas 图表仍是位图，原生 PPTX 支持范围也不同；不要许诺所有格式逐像素一致。
