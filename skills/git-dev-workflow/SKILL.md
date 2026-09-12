---
name: git-dev-workflow
description: >-
  Use this skill before any local git write operation: committing, branching, discarding
  uncommitted changes, deleting branches or worktrees, rewriting history, or force-pushing.
  It reads the repository's real state first (never describes it from memory), runs a
  mechanical pre-check before irreversible actions, and reports facts by quoting raw output.
  Also use it when judging whether uncommitted changes can be safely thrown away, or when a
  worktree or branch cleanup is needed.
  Do NOT use for: creating, reviewing or merging pull requests; CI configuration; hosting
  platform operations (GitHub/GitLab UI, issues, releases); teaching git from scratch;
  versioning content outside a repository.
---

# git-dev-workflow — 本地开发里的 git

## 四条硬规则

这个 skill 的规则**不靠自觉**，每一条都绑在一个脚本上。

| 规则 | 怎么做 | 为什么 |
| --- | --- | --- |
| **R1 先探后动** | 任何写操作前先跑 `git_state.py`；报告里的状态**只能来自它** | 分支可能早被切走、工作区可能是上一个 agent 留下的、上游可能根本不存在 —— 凭记忆答一定会错 |
| **R2 不可逆先过 guard** | `reset --hard` / `clean -f` / `branch -D` / `worktree remove` / `stash drop` / `rebase` / `push --force` / `--no-verify` 之前跑 `git_guard.py`，**把它的原始输出贴进报告** | 这些命令执行完没有第二遍；而"这个应该没用了吧"这个判断从来不可靠 |
| **R3 报告只抄不编** | 报告里的分支名、提交数、文件数一律从脚本输出里抄 | 叙述会和事实漂移，而漂移看不出来 |
| **R4 拿不到就当最坏** | 远端状态问不到时按"可能丢东西"处理 | 少拦一次和误删一次，代价不对称 |
| **R5 提交信息按规范** | `git commit` 之前先过 `commit_style.py`；报告里说的是「规范哪一条」，不是「我觉得不好」 | 判据是**写在纸上的规范**（Conventional Commits v1.0.0，16 条），不是历史习惯 |

## 起手流程

1. `python3 scripts/git_state.py`（要看细节加 `--json`）。
   退出码 `2` = **正处于中间态**（rebase / merge / cherry-pick / 有冲突）—— 这时候先停下来问清楚，别接着动。
2. 从输出里**读**出当前分支、基线分支、未提交构成、未推送条数、worktree 与 stash 状态。
3. 要动手时先过 guard，再看结论：
   - `SAFE`（退出码 0）→ 可以做
   - `WARN`（3）→ 可以做，但**先把列出来的那几项说给用户听**
   - `BLOCK`（4）→ **不做**。要么先解决列出来的原因，要么让用户显式改主意
4. 要做提交时，先把信息喂给 `commit_style.py --check`（`--template` 能打出骨架和 type 表）。
5. 做完用 `git_report.py` 出前后对照（动手前先 `--capture`），报告里贴的是它末尾那段**命令 + 原始输出**，不是转述。

## 脚本

| 脚本 | 干什么 | 退出码 |
| --- | --- | --- |
| `git_state.py` | 只读状态快照：分支 / 基线 / 工作区分类 / 上游与未推送 / worktree / stash / 子模块指针 / 中间态 / 钩子 | `0` 正常，`1` 不是仓库，`2` 中间态 |
| `git_guard.py` | 八个不可逆动作的预检，输出「会丢什么 + 结论 + 确认则执行这一条」 | `0` SAFE，`3` WARN，`4` BLOCK |
| `commit_style.py` | 按 Conventional Commits v1.0.0 的 16 条校验一条提交信息 | `0` 合规或不适用，`1` 有规范违规 |
| `worktree.py` | 建 / 列 / 查 stale / prune / 回收 worktree；默认放**仓库同级** | `0` 成功，`1` 被拒，`3`/`4` 沿用 guard 的结论 |
| `git_report.py` | 动手前后的事实对照 + 一段**可原样粘贴**的命令与原始输出 | `0` 有对照，`1` 没有快照/坏快照 |
| `commit_plan.py` | 把改动分成候选提交（按区域，疑似凭据单独成组）；**只出计划** | `0` |

`git_guard.py` 认识的动作（`--list` 也能列）：

| 动作 | 看什么 |
| --- | --- |
| `discard-worktree` | 未提交里有没有**不是构建产物**的东西 |
| `clean-untracked` | 未跟踪里有没有非产物；加了 `--include-ignored` 还要看 `.gitignore` 挡住的文件里有没有**凭据** |
| `delete-branch <名>` | 是不是当前分支、**是不是基线分支**、是否已并入、有没有**只存在于本地的提交** |
| `delete-worktree <路径>` | 脏 → BLOCK；未并入基线 → WARN；干净且已并入 → SAFE（**旧版那三条前置已作废**，理由在 `references/worktrees.md`） |
| `drop-stash <ref>` | 同样的改动在最近提交里有没有对应（有界比对，会标注范围） |
| `rewrite-history` | 要改写的提交**在不在远端**；远端有就必须用 `--shared` 显式声明 |
| `force-push` | 是不是基线分支；远端有没有本地没有的提交；拿不到远端状态就拦 |
| `bypass-hooks` | 仓库装了钩子就一律拦 |

## worktree：放同级，回收看两件事

`worktree.py create` 默认把新 worktree 放在**仓库同级**（在仓库之外：不用改 `.gitignore`，
`git status` 也看不见它）。

回收的判据只有一件是硬的：**那个目录里有没有未提交改动**（有 → 拦 —— 未提交的内容只存在
于那个目录里）。分支没并进基线只是**提醒**：`git worktree remove` 不删分支、不删提交，
所以那不算数据丢失。目录已经被删掉的那种用 `prune`，不是 `remove`。

## 能力边界（当前实现到哪，别读成承诺）

- **已实现**：`git_state.py`（R1）、`git_guard.py`（R2）、`commit_style.py`（R5）、`worktree.py`、`git_report.py`、`commit_plan.py`。
- **明确不做**（不是"还没做"）：见下面那行。
- **本 skill 不做**：PR / review / CI / 托管平台操作；一键批量删分支；拆到 hunk 级的提交拆分；自动改你的 git 配置（比如 `pull.rebase`）；绕过钩子；承诺"能救回所有误操作"。

## 参考

- `references/commit-messages.md` —— 规范的 16 条逐条落地、本仓库的 type 表、
  **哪些是规范其实允许的**（`FEAT:` 不违规、其它 type 可以用）、中文怎么写。
- `references/worktrees.md` —— 放哪（同级，含为什么）、命名、回收判据
  （含**改过一次**的理由）、交给并行 agent 的用法、四个坑。
- `references/recovery.md` —— 误操作之后能救什么、**救不回什么**（reflog 的边界）、
  每一类的可执行步骤、以及第一步先取证。
- `references/history-surgery.md` —— 什么时候值得改写、四种手段的代价、
  脱敏重写的实际顺序（备份 → 改写 → 逐项核验 → 强推 → 记档）。

## 判据写在代码里，不写在文档里

`git_guard.py` 的每一档结论都来自代码里的判据。想改判据就改代码 ——
**不要在这里再抄一份**：两份判据必然漂移，而漂移的那一份会让你在错误的一侧得到安全感。
