# git-dev-workflow

> 在**动 git 之前**把仓库的真实状态读出来，并在不可逆动作（丢弃改动 / 删分支 / 删 worktree /
> 丢 stash / 改写历史 / force push / 绕过钩子）前跑一次机械预检。
> **不做** PR / review / CI / 托管平台操作，也不承诺「能救回所有误操作」。

## 解决什么问题

两件事驱动它：**不可逆动作没有第二遍**（`reset --hard` / `clean -f` / `branch -D` /
`worktree remove` / `stash drop`，而「这个应该没用了吧」从来不可靠）；而**状态凭记忆答一定会错**
（分支可能早被切走、工作区可能是上一个 agent 留下的、上游可能根本不存在，而这些错法都不报错）。
所以状态一律从 `git_state.py` 里**抄**，不从记忆里**编**；不可逆动作先过 `git_guard.py`。

触发语：`帮我提交` / `把工作区清干净` / `这个分支不要了` / `开个 worktree 并行干活` /
`我刚才 reset --hard 弄丢了东西` / `这个仓库推上去了吗`。

## 安装

```sh
python3 tools/install_skills.py      # 默认装软链（推荐：改仓库即时生效）
python3 tools/install_skills.py --check
npx skills add <repo> --skill git-dev-workflow --agent claude-code --global   # 副本方式
```

依赖：**只用 Python 标准库**，加上本机可用的 `git`。脚本按 `python3 scripts/<名>.py` 跑。

## 配置

**不需要凭据，也没有自己的配置文件** —— 它读的是仓库的真实状态。两个前置条件：

| 条件 | 为什么 | 怎么确认 |
| --- | --- | --- |
| 仓库装了 git 钩子 | `git_guard.py bypass-hooks` 只在**装了钩子**的仓库拦 `--no-verify`；没钩子就没得拦 | `git config core.hooksPath`；本仓库一次配置：`git config core.hooksPath .githooks` |
| 有 `git` 与 `python3` | 脚本是 git 的壳 | `git --version` / `python3 -V` |

`git_report.py` 的快照默认藏在 `.git/git-dev-workflow-snapshot.json`（在 `.git` 里，不会被跟踪）；
换位置用 `--file`。

## 快速开始

```sh
S=skills/git-dev-workflow/scripts

python3 $S/git_state.py                  # 1. 先看状态（分支/基线/未提交构成/未推送/worktree/stash/钩子）
python3 $S/git_state.py --json           #    给 agent 读的版本
python3 $S/git_guard.py --list           # 2. guard 认识哪八个不可逆动作
python3 $S/git_guard.py delete-branch my-feature   # 预检一个：SAFE 0 / WARN 3 / BLOCK 4
python3 $S/commit_style.py --template    # 3. 提交信息骨架 + type 表
python3 $S/commit_style.py --check "fix(api): 修正分页越界"
python3 $S/git_report.py --capture       # 4. 动手前存快照
python3 $S/git_report.py                 #    动手后出对照（末尾那段可原样粘贴）
```

`git_state.py` 输出的**形状**（数字随仓库状态变，这里只示范长什么样 —— 真值请自己跑）：

```text
分支     <当前分支>（基线 <基线分支>）
上游     origin/main  领先 N / 落后 M
未推送   N 条
未提交   N 项  已暂存 a / 未暂存 b / 未跟踪 c / 冲突 d
         分类（按文件名猜的）：<类别>
钩子     core.hooksPath = .githooks  已启用：pre-commit
```

> **没把某一次的真实数字抄进来，是故意的**：文档里的状态数字从写下的那一刻就开始过期，
> 而《未提交 13 项》这种具体数一旦对不上，读者会开始怀疑整份文档。要看真值就跑上面那条命令。

被拦时长这样（**BLOCK 不给命令** —— 给了就等于在暗示「其实可以做」）：

```text
动作     discard-worktree
会丢什么
         - 未提交改动：N 项（other 10、source 3）：<路径> …
结论     BLOCK
         原因：有 N 项不是构建产物 —— 它们是源码/文档/配置，丢了要重写
```

## 能力详解

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| 状态快照 | `git_state.py [--json]` | 只读。退出码 `2` = 正处于中间态（rebase / merge / cherry-pick / 有冲突），这时候先停下问清楚，别接着动 |
| 不可逆预检 | `git_guard.py <动作> [名字]` | 八个动作：`discard-worktree` / `clean-untracked` / `delete-branch` / `delete-worktree` / `drop-stash` / `rewrite-history` / `force-push` / `bypass-hooks` |
| 提交信息校验 | `commit_style.py --check` / `--check-file` / `--template` | 按 Conventional Commits v1.0.0 的 16 条。只有**规范违规**退 `1`；「本项目约定」类问题退出码仍是 `0`（别把后者当规范禁止） |
| 前后对照 | `git_report.py --capture` → `git_report.py` | 末尾给一段「命令 + 原始输出」，报告里贴那一段，而不是转述成「改了几处」 |
| worktree | `worktree.py list [--stale]` / `create <分支>` / `remove <路径>` / `prune` | 默认放**仓库同级**；`remove` 只在判据过了才动手，脏的一律拦 |
| 分组提交计划 | `commit_plan.py` | 把改动按区域分组、给候选前缀、列出可粘贴的 `git add`；**只出计划，不 add 不 commit** |

手册在 `references/`：提交信息（16 条逐条落地 + 中文怎么写 + 哪些其实是规范允许的）、
worktree（放哪、回收判据、交给并行 agent）、误操作救援（能救什么、**救不回什么**）、
改写历史（四种手段的代价 + 脱敏重写的实际顺序）。

## 目录结构

```text
skills/git-dev-workflow/
├── SKILL.md          # 给 Agent 的规则（四条硬规则、起手流程、能力边界）
├── README.md         # 本文件
├── references/       # 四本手册：commit-messages / worktrees / recovery / history-surgery
├── scripts/          # state / guard / commit_style / worktree / report / commit_plan
└── evals/            # 7 条触发与行为评估
```

## 边界（不该用它的时候）

- 做 PR / review / merge、配 CI、操作托管平台（GitHub / GitLab 的 UI、issue、release）：
  这些不是本地 git 写操作 —— 需要时直接用平台自己的工具。
- 想从零学 git（它讲的是「动手前的核对」，不是教程）；
  或者要版本化的目录根本不是 git 仓库（脚本会说「不是一个 git 仓库」然后停）。
- 想要一键批量删分支、拆到 hunk 级的提交、让工具替你改 git 配置（`pull.rebase` 之类）：都不做。

## 验证

```sh
cd skills/git-dev-workflow
python3 -m unittest discover -s tests/<skill> -v     # 约 40 秒；在 tempfile 里真 git init 一个仓库来造状态
```

「通过」的意思是：`git_state.py` / `git_guard.py` 的判据在**真仓库**上验过（脏工作区、
只在本地存在的提交、已并入/未并入的分支、detached HEAD、merge 中间态、目录已被删掉的
worktree）；`commit_style.py` 的用例按**规范条目号**组织 —— 哪一条理解错了，失败的用例会
直接指出是哪一条。跑得慢是故意的：用假 JSON 喂这两个脚本，测的就不是它们了。

## 已知限制与未验证项

| 项 | 状态 |
| --- | --- |
| 判断 type 用得**对不对**（该 `feat` 还是 `fix`） | **不做**：语义判断，机器只能看形状 |
| 校验**历史**提交的信息 | **不做**：`commit_style.py` 只管将要提交的那一条 |
| 一键批量删分支 / hunk 级拆分 / 替你改 git 配置 | **不做**（不是「还没做」） |
| 承诺「能救回所有误操作」 | **不做** —— `references/recovery.md` 写清了救不回什么（`clean` 掉、`checkout --` 丢的内容基本救不回） |
| 远端状态问不到时的结论 | 按最坏处理（`force-push` 拿不到远端就拦）。这是设计选择，不是缺陷 |
| 旧版 git / 特殊环境（CI 容器、bare 仓库、shallow clone） | **未实测**：脚本用到的都是标准子命令，但没有在旧版 git 上逐个验过 |
