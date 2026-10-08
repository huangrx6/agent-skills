# diagram-authoring

从结构规格生成可编辑的技术图：架构、依赖、流程、状态、思维导图和网络拓扑。
模型理解节点与关系；Python 负责布局、路由、检查和序列化。

## 安装与依赖

从仓库根目录安装：

```sh
python3 tools/install_skills.py
```

核心生成链只用 Python 标准库。可选工具各有依赖：

| 功能 | 依赖 |
| --- | --- |
| 自研布局预览 `dev-tools/preview.py` | Pillow |
| Excalidraw 官方 PNG/SVG 导出 | Chrome/Chromium 等受支持浏览器；加载官方 JS 包需要网络 |
| draw.io PNG/SVG/PDF/JPG 导出 | draw.io 桌面版，支持 `DRAWIO_BIN` / `--binary` 指定路径 |
| 官方图标库搜索/下载 | 网络；缓存默认在 `~/.cache/diagram-authoring/libraries/` |

## 快速开始

在 skill 目录运行；规格示例和字段见 [diagram-spec.md](references/diagram-spec.md)：

```sh
python3 scripts/validate_spec.py system.diagram.json
python3 scripts/emit_excalidraw.py system.diagram.json --quality showcase
python3 scripts/emit_drawio.py system.diagram.json --quality showcase
```

输出默认与 spec 同目录，可用 `-o` 指定。保留 spec，修改结构后重新生成。
同一输入、同一版本与素材生成确定性文件；手工编辑源成品的变化不会自动读回 spec。

| 工具 | 用途 |
| --- | --- |
| `scripts/guide.py` | 按场景信号推荐图型 |
| `scripts/check_layout.py --json` | 布局诊断、自动调参回执 |
| `scripts/check_drawio.py` | 未压缩 draw.io XML 结构检查 |
| `scripts/layout.py --explain` | 开发时查看布局推导 |
| `scripts/direction_preview.py` / `scheme_preview.py` | 按需比较视觉方向或 draw.io 配色 |
| `scripts/sigils.py` / `icons.py` / `icons_fetch.py` | 内置图标、本地素材和官方库查询 |
| `dev-tools/export_excalidraw.py` / `export_drawio.py` | 调用真实渲染器导出 |

默认 Excalidraw；draw.io 支持多份 spec 合成多页文件。两者共有七种基本形状，
但 draw.io 当前拒绝图标、不支持完整云/UML/BPMN图元库。不要把“应用本身支持”当成“本生成器支持”。

## 质量边界

`standard` 允许部分连线警告；`showcase` 将结构类警告升级为阻塞。
阻塞时 emit 不写成品，已有文件不会被半成品覆盖。真实渲染检查仍不可省：
Excalidraw 可能重新折行，字体与应用版本也可能改变结果。

默认在当前项目交付文件，不自动写 Obsidian。用户指定 vault 后才解析环境变量
`OBSIDIAN_VAULT_PATH` 或 `~/.config/agent-skills/obsidian-vault-path`。

详见 [使用入口](SKILL.md)、[校验](references/validation.md) 与两份后端说明。
`evals/evals.json` 覆盖代理行为；`benchmarks/first-pass/` 保留首轮可用性的协议、验证器与历史证据，
历史截图不代表当前版本已通过视觉验收。

## 开发验证

从仓库根目录执行（测试包含核心不变量与外部导出的 mock 合同）：

```sh
python3 -m unittest discover -s tests/diagram-authoring -v
```

浏览器/应用实际导出需单独运行并检查产物；单元测试通过不能替代它。
