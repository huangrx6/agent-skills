---
name: git-dev-workflow
description: >-
  Use this skill for local Git commits, branches, worktrees, discarding changes, deleting references,
  rewriting history, force pushes, repository sync checks, and recovery after Git mistakes.
  中文：提交、建分支、清理改动或 worktree、改写历史、确认是否已推送、恢复误操作。
  Provides read-only state and destructive-action guards. Do NOT use for PR reviews, CI, or hosting UI operations.
---

# Git 本地工作流

先读取目标仓库的当前状态，再执行用户授权的动作。脚本均位于本 skill 的 `scripts/`；
从目标仓库运行，或加 `--repo /path/to/repo`，不要假定当前目录就是 skill 目录。

## 按风险选择流程

- **提交、建分支、建 worktree**：用 `git_state.py` 或等价只读 Git 命令确认分支、已有改动及进行中的操作。
  普通提交只暂存本次任务内容；遵循目标仓库的提交约定。使用 Conventional Commits 时可跑
  `commit_style.py --check 'fix(api): 修正分页'`。用户已经授权的操作无需再次确认。
- **丢弃、清理、删除引用、改写、强推或跳过钩子**：执行前跑 `git_guard.py` 对应动作。
  `SAFE`（0）可在授权范围内执行；`WARN`（3）说明风险，并判断是否已在授权范围内；
  `BLOCK`（4）先解决列出的原因。guard 结论本身不构成用户授权，也不证明其他动作安全。
- **中间态**：状态退出码 2 表示 merge/rebase/cherry-pick 或冲突。若任务就是处理该操作，继续解决；
  若要开始无关操作，先厘清当前状态。不要把它一律变成确认门。
- **报告**：简要说明实际完成的动作、验证和仍未解决的问题，结论来自本次读取。
  需要前后审计时才用 `git_report.py --capture` → `git_report.py`；不必每次粘贴全部原始输出。

## 工具入口

| 工具 | 用途 |
| --- | --- |
| `git_state.py [--json]` | 状态快照；0 正常、1 非仓库或读取失败、2 中间态 |
| `git_guard.py --list` | 列出预检动作；只检查，不执行 |
| `commit_style.py --check/--check-file/--template` | 提交信息语法检查；1 表示规范问题，项目建议不阻断 |
| `commit_plan.py [--json]` | 按目录给候选分组和暂存命令；不自动暂存或提交 |
| `worktree.py list/create/remove/prune` | worktree 生命周期；默认建在仓库同级，`--at` 指定仓库外路径 |
| `git_report.py --capture [--file PATH]` | 可选前后快照；默认写 Git 元数据目录 |

`git_guard.py` 动作：`discard-worktree`、`clean-untracked [--include-ignored]`、
`delete-branch NAME`、`delete-worktree PATH`、`drop-stash REF`、`rewrite-history [--shared]`、
`force-push [--branch NAME] [--remote origin]`、`bypass-hooks`。

## 核验边界

- 文件分类只看名字；“像构建产物”不等于已有备份。预检之后工作区仍可能变化，执行前核对目标。
- 分支是否推送、改写是否共享，依据本地远端跟踪引用；需要确认远端最新状态时先刷新它。
  不把过期引用或查询失败当成远端安全。`rewrite-history` 只检查当前 HEAD，重写多条时另核对完整范围。
- worktree 回收不删除命名分支，但 detached HEAD 必须先确认有其他引用保留提交。
  回收也会删除忽略文件；凭据和未知本地内容阻止回收，按名称归类的构建产物会明确提醒后随目录删除。
- stash 的工作区 patch 匹配历史不代表暂存区或未跟踪内容也已保留；这两类独立内容不能仅凭 patch-id 判 SAFE。
- 不顺带改 Git 配置、不批量删除未指定的对象、不自动绕过钩子、不发送协作通知。

## 按需参考

- [提交信息](references/commit-messages.md)：Conventional Commits 的检查范围与建议。
- [Worktree](references/worktrees.md)：路径、回收和并行写入。
- [误操作恢复](references/recovery.md)：先保留现场，再找提交；未保存内容的恢复边界。
- [历史改写](references/history-surgery.md)：改写范围、备份、共享历史与强推。
- [运行与验证](README.md)：人工运行入口及本地测试。
