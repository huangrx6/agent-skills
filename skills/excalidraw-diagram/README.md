# excalidraw-diagram

> 把「系统怎么运作」画成**可编辑**的 Excalidraw 图（架构 / 依赖 / 流程 / 状态 / 部署拓扑 / 思维导图 / 网状）。
> **模型只描述结构，坐标全由脚本算。**
> **不画**装饰性插图、海报、线框图；**不整理**笔记，**不记录**发版。

## 解决什么问题

让模型直接吐坐标，本质是让它做一件它没有可靠能力的事（配色、字号、折行、间距、遮挡全是空间计算），
症状必然是「看起来还行，但总有几处别扭」。这个 skill 把那条路堵死：

**规格 schema 里没有 `x` / `y` / `width` / `height` —— 不是"不推荐填"，是不存在这些字段。**
一旦有，模型就会开始填数字；这个失败在前作 `draw-excalidraw` 上真实发生过。

触发语：`画个架构图` / `把这段说明画成图` / `画流程图` / `draw a diagram`。

## 安装

```sh
python3 tools/install_skills.py            # 默认装软链（推荐）
npx skills add <repo> --skill excalidraw-diagram --global
```

依赖：**核心链路零依赖**（只用 Python 标准库）。
只有 `dev-tools/preview.py`（用它自己目视复核 PNG 时）需要 PIL —— 它刻意放在 `dev-tools/`
而不是 `scripts/`，就是为了让「出图零依赖」这句话不被含糊掉。

## 配置

| 配置项 | 从哪里读 | 说明 |
| --- | --- | --- |
| vault 路径 | `$OBSIDIAN_VAULT_PATH` → `~/.config/obsidian-vault-path` | 只在往 vault 里放图时需要；路径不写死，换机器只改一处 |
| 图标素材库 | `--library` 参数；默认走素材库约定路径 | 库里的项自带固有宽高，是第一个**外部尺寸来源**，见 `references/icons.md` |

## 快速开始

```sh
cd skills/excalidraw-diagram

# 1. 写一份规格：只有结构（节点 / 边 / 分组），没有任何坐标
#    完整字段见 references/diagram-spec.md

# 2. 校验规格（字段集封闭：未知字段、含坐标、未知 kind 都会判失败）
python3 scripts/validate_spec.py my.diagram.json

# 3. 出图：这一条串起整条流水线（校验 → 分层布局 → 十项校验 → 失败自己调参重跑 → 写文件）
python3 scripts/emit_excalidraw.py my.diagram.json
```

用仓库自带的示例规格跑一遍（已实测）：

```sh
$ python3 scripts/emit_excalidraw.py tests/fixtures/specs/01-architecture.json -o /tmp/arch.excalidraw
✓ /tmp/arch.excalidraw  （14 个节点 / 14 条边 / 50 个元素 / 交叉 0）
```

同一份规格**每次生成的字节完全相同**（seed 由元素 id 的 sha256 推出），所以图能进 git、diff 有意义 ——
上面这条命令连跑两次 `cmp` 无差异。

## 能力详解

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| 出图 | `emit_excalidraw.py x.diagram.json` | 串起整条流水线；**有阻塞项时不写文件** |
| 只校验规格 | `validate_spec.py x.diagram.json` | 封闭字段集检查 |
| 只看布局 | `layout.py x.diagram.json --explain` | 用的哪个算法、层/环内顺序、坐标、交叉数 |
| 只看校验与调参报告 | `check_layout.py x.diagram.json` | 退出码：`0` 无阻塞项 / `1` 有阻塞项 / `2` 读不到规格 |
| 量文字尺寸 | `text_metrics.py "节点标题"` | 文字 → 容器尺寸的实际推算 |
| 看色板 | `palette.py` | 打印色板与 `kind` 的合法取值 |
| 挑主题方向 | `direction_preview.py` | **用户没指定风格时**出图前跑它，5 个方向并排给人挑 |
| 在官网接着画 | `open_excalidraw_com.py x.excalidraw` | 起一个只服务单文件、只允许 excalidraw.com 的本地服务，用 `#url=` 导入官网画布（已实测：23 个元素全进画布、可直接接着改） |
| 目视复核 | `dev-tools/preview.py x.excalidraw out.png` | **需要 PIL**；给我自己看排版用的，不是运行时的一部分 |

**图类型决定布局算法**（`type` 自动选，人不用选算法）：

| 图类型 | 布局 | 默认方向 |
| --- | --- | --- |
| `architecture` / `dependency` | 分层（简化 Sugiyama） | `LR` |
| `flow` / `state` | 分层 + 环回边特殊处理 | `TB` |
| `mindmap` | 径向（同心环，子树按叶子数分扇区） | — |
| `network` | 力导向（确定性初值 + 收尾分离） | — |

三种布局算法：分层、径向、力导向。**判断图类型是人的活，判断完之后的计算全是脚本的活。**

## 目录结构

```text
excalidraw-diagram/
├── SKILL.md                # 给 Agent 的规则（不写坐标等硬规则、图类型策略表）
├── README.md               # 本文件
├── references/
│   ├── diagram-spec.md     # 内容层契约：允许写什么、刻意不存在的字段、kind 封闭枚举、groups、style、detail
│   ├── validation.md       # 十项校验的阈值与级别、自动调参循环、报告该说什么
│   ├── visual-design.md    # 审美总原则 + 可校验 / 不可校验的分界 + 9 条实测问题清单
│   └── icons.md            # 图标素材库：怎么查、怎么选、为什么它是外部尺寸来源
├── scripts/                # 10 个：校验 / 布局 / 出图 / 文字测量 / 色板 / 素材 / 主题预览 / 官网打开
├── dev-tools/preview.py    # 出 PNG 供目视复核（需 PIL，非运行时）
├── tests/                  # 11 个测试文件、348 条
└── evals/
    └── evals.json          # 6 条行为评估（不写坐标 / 类型判断 / 风格先问 / 报告改内容）
```

## 边界（不该用它的时候）

- 想**写 / 整理 / 归位**笔记 → `obsidian-personal-knowledge-base`。
- 想**记录已完成的工作、写发版文档** → `obsidian-work-log-release-recorder`。
- 想做装饰性插图、海报、线框图 → 它只画解释性技术图，这类需求不接。

## 验证

```sh
cd skills/excalidraw-diagram
python3 -m unittest discover -s tests -v     # 348 条，全绿（约 10 秒）
python3 scripts/emit_excalidraw.py tests/fixtures/specs/07-regions.json -o /tmp/a.excalidraw
```

「通过」的意思是：规格的封闭字段集挡住了含坐标/未知 kind 的写法；七份示例规格都能出图；
同一规格重复生成字节一致；十项校验的阈值有边界测试。

## 已知限制与未验证项

| 项 | 状态 |
| --- | --- |
| **没有 evals** | 仓库维护约定要求「核心行为必须有 eval 覆盖」，这个 skill 目前只有测试、没有 `evals/`（`tools/skill_health.py` 会报出来） |
| **Excalidraw 会自己重排文字** | `text_metrics` 是对「文字占多大」的推算，而容器绑定的文字在 Excalidraw 里由它按真实字体重新断行 —— **渲染器是第二个尺寸来源，不在我们控制内**。多断一行就会撑高容器、偏移布局。所以**规格与校验全绿 ≠ 渲染出来就是那样** |
| 「元素间隙」「文字溢出」两项校验 | 是**后置断言**：坐标与尺寸出自同一批参数，构造上不可能失败。真报了是脚本内部不一致，不是内容有问题 |
| 「交叉数」是软项 | 不挡输出，但**仍然会被调参** —— 把它当成「不报错」会不知道它到底调没调 |
| 一批常量标着**待验证** | 断行档位 10/16/24、`nodeSeparation`/`rankSeparation` 120、阈值 12/24px、车道步长 34、区域标题字号 20…… 都来自前作数值与常识起点，**没有用真实数据校准过**（清单在 `references/diagram-spec.md` 的参数表里） |
| `dev-tools/preview.py` 的盲区 | 它画的是我们自己的布局模型（与 `layout.py` 同源），所以**构造上**看不见「渲染器与模型不一致」这类问题 —— 那类只有真实 Excalidraw 才算数 |
| `#url=` 导入官网 | 实测跑通，但它依赖 Excalidraw 的一个无 UI 入口（PR #2726）；官网改版就可能失效 |
