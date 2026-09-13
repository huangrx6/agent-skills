# skill-builder

> 建 skill 之前的 5 分钟决策：**该不该建**、触发描述怎么写、范围定 P0 还是 P1、起一版 `SKILL.md`；
> 外加一套能跑的机械检查器（结构 / 泄露 / 指针 / 报告前取证）。
> **不做**：编辑现有 skill 的正文、写一次性 prompt、跑 formal eval、替别的 skill 维护 `references/` 与 `assets/`。

## 解决什么问题

建 skill 的失败方式有两种，都很安静。

**建了不该建的**：想到一个点子就建一个目录，半年后发现十几个 skill 里只有两个真的在被触发 ——
本仓库立身之本是避开这件事，所以它把「要不要建」压成 5 个必须回答的问题。

**建了但没人检查**：「正文 ≤ 150 行」这类硬约束在实测中被**连续违反两次**（256 行、174 行），
两次都是脚本抓出来的，肉眼没发现。手工勾选的 checklist 不可靠，所以这里的规则**每一条都绑在一个脚本上**。

触发语：`这个需求要不要包成 skill` / `帮我起一版 SKILL.md` / `这个触发描述是不是太宽了` /
`我这个 skill 老是不触发`。

## 安装

```sh
python3 tools/install_skills.py            # 默认装软链（推荐：改仓库即时生效）
python3 tools/install_skills.py --check    # 看指向对不对
npx skills add <repo> --skill skill-builder --agent claude-code --global   # 副本方式
```

依赖：脚本**只用 Python 标准库**，不需要 `pip install`。

## 配置

| 配置项 | 从哪里读 | 说明 |
| --- | --- | --- |
| 泄露词表 | `--blocklist PATH` → `$SKILL_NAME_BLOCKLIST` → `~/.config/skill-name-blocklist.txt` | **刻意不放在仓库里** —— 放进去它自己就泄露了。未配置时扫描跳过、不阻塞提交 |
| git hook | `git config core.hooksPath .githooks` | 每个 clone 做一次。之后提交触及 `skills/` 或 `tools/` 时会自动跑四道检查 |

> `check_leakage.py --show-blocklist` 会**打出真实词条** —— 别把它的输出贴进任何要外发的地方。

## 快速开始

```sh
cd <仓库根>

python3 skills/skill-builder/scripts/preflight.py                  # 报告前跑：四道检查 + 事实快照
python3 skills/skill-builder/scripts/validate_skill.py skills/pingcode  # 只校验一个 skill
python3 skills/skill-builder/scripts/preflight.py --json            # 机器可读（喂给别的脚本）
```

`preflight.py` 的真实输出（数字都从这里抄，别凭印象写）：

```text
检查
  ✓ 结构校验    检查 6 个 skill，全部通过
  ✓ 泄露扫描  ✓ 未发现不该外发的名称
  ✓ 指针目标      真的接住了那些条款（这条留给人和 skill-builder 的检查项）。

事实快照（报告里的数字从这里抄，不要凭印象写）
  skill                                     正文    余量  desc  refs  tests
  skill-builder                        147/150     3   636     2     48

  测试合计 662
  ✓ 无孤儿脚本
```

## 能力详解

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| 5 分钟决策树 | `SKILL.md` 的 Q1–Q5 | 频率 / 触发词 / 边界 / 范围档位 / 15 分钟能写完吗。**任何一题答不上来 = 不建** |
| 触发描述规范 | `SKILL.md` | description 是 Agent **唯一的**触发器，占整张 SKILL.md 工作量的 60%；边界必须写进 description，写在正文等于没写 |
| 结构校验 | `scripts/validate_skill.py` | 9 项机械检查：frontmatter 可解析、`name` == 目录名、description < 800 字符、含触发表达、含 Do NOT 边界、正文 ≤ 150 行…… 退出码 0 通过 / 1 有失败 / 2 没找到 SKILL.md |
| 泄露扫描 | `scripts/check_leakage.py` | 真实客户名 / 内部系统名 / 内网路径。`--history` 额外扫 git 历史，用来定位泄露是哪次提交引入的 |
| 指针检查 | `scripts/check_pointers.py` | **只找出来、不判定** —— 「指针写对了」和「内容搬过去了」是两件事，后者留给人逐词核对 |
| 报告前取证 | `scripts/preflight.py` | 四道检查 + 事实快照 + **孤儿脚本**（`scripts/` 里有文件却没人叫你去跑 = 没接线） |
| README 模版 | `references/skill-readme-template.md` | 每个 skill 该配一份给人看的 `README.md`，模版与硬约束在这里 |

## 目录结构

```text
skills/skill-builder/
├── SKILL.md                     # 给 Agent 的规则：决策树 + 描述规范 + checklist + 报告纪律
├── README.md                    # 本文件
├── references/
│   ├── anatomy-and-scope.md     # skill 目录该放什么、哪些内容该进 references
│   ├── slimming.md              # 正文余量不足时怎么搬（搬什么 / 留什么 / 搬完怎么核对）
│   ├── reporting.md             # 报告纪律的实测经过、这条防线为什么没闭合
│   └── skill-readme-template.md # 每个 skill 的 README 模版与硬约束
├── scripts/
│   ├── validate_skill.py        # 结构校验（挡提交的那一道）
│   ├── check_leakage.py         # 泄露扫描
│   ├── check_pointers.py        # 指针目标存在性
│   └── preflight.py             # 全部检查 + 事实快照
├── tests/                       # 48 条：三个检查器的边界值
└── evals/
    └── evals.json               # 6 条行为评估（频率证据 / 边界写进 description / 已量不算）
```

## 边界（不该用它的时候）

- 想改某个 skill 的**正文规则** → 直接改那个 `SKILL.md`，不用回来重做「要不要建」的决策。
- 想写一次性 prompt / alias → 那本来就不该是 skill。
- 想跑**正式的触发准确度评估** → 另起流程，本 skill 明确不做。
- 想给某个 skill 补 `references/` / `assets/` → 直接补。
- 想做视觉资源生成、Agent 加载机制的兼容性测试 → 不做（前者不是本 skill 的产出，后者归各 Agent 维护者）。

## 验证

```sh
cd skills/skill-builder
python3 -m unittest discover -s tests -v     # 48 条
```

守的东西分三层，都是**边界值**（按仓库定的停止判据：元工具只要求边界值测试）：

- `validate_skill.py`：正文 150 / 151 行差一行、余量提示的触发点、「绑定本机 + 从配置读」的自相矛盾判定
  —— 这两处**实测误报过两次**，收错了会静默误挡正常提交。
- `check_pointers.py`：五条分界 —— 指针目标缺失要**阻塞**；只是提到一个像路径的词则只列不阻塞；
  `.excalidraw.md` 是扩展名不是路径；代码块里忽略；目标存在则通过。
- `check_leakage.py` / `preflight.py`：注释行不算词条、没配 blocklist 不算错、测试数要**读真实文件**而不是估算。

「通过」= 三个脚本退出码都是 0，且 preflight 的四道检查全 ✓、无孤儿脚本。

## 已知限制与未验证项

| 项 | 状态 |
| --- | --- |
| 本 skill 自己**没有 `evals/`** | 未做。仓库的停止判据写着「核心行为必须有 eval 覆盖」，这条恰好没覆盖 —— `tools/skill_health.py` 每次都会把它列出来 |
| 「每个 skill 都要有 README」**没有机械校验** | 未做。`validate_skill.py` 不查 README 的存在与结构，所以这条目前仍靠人记得 |
| 「报告纪律」那条防线**没有闭合** | 已知。报告是自由文本，没有东西验证它 —— 第三次实测正是「跑了工具但仍然抄错数字」。`SKILL.md` 里写明了，**别当成已经堵住** |
| Q1 的「去数频率」 | 依赖会话日志 / git log / 笔记。本仓库**目前没有触发日志**，数不出来时只能如实说「数不出来」，不许用「感觉经常」充当证据 |
| 正文余量只剩 3 行（147/150） | 事实。下一条真规则加进来之前，**先做 references 瘦身**；`preflight.py` 每次都会把余量报出来 |
