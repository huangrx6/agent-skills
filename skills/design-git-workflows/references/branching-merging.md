# 分支、合并与 Worktree

## branch：分支管理

| 命令 | 用途 |
| --- | --- |
| `git branch` | 列出本地分支 |
| `git branch -vv` | 含跟踪关系与最新 commit |
| `git branch <name>` | 创建分支（不切换） |
| `git branch -d <name>` | 删除已合并的分支（安全） |
| `git branch -D <name>` | 强制删除（危险，丢失未合并 commit） |
| `git branch -m <new>` | 重命名当前分支 |
| `git branch --merged` | 列出已合并到当前分支的分支 |

- 分支是指向 commit 的可变指针；
- `main`/`master` 是默认主分支；
- 已合并的分支用 `-d` 删除安全；`-D` 会丢失未合并的工作。

## checkout / switch：切换

```bash
git checkout <branch>          # 切换分支（旧语法）
git switch <branch>            # 切换分支（新语法，Git 2.23+）
git checkout -b <new>          # 创建并切换
git switch -c <new>            # 创建并切换（新语法）
git checkout <commit>          # 分离 HEAD（detached HEAD）
git checkout -                 # 回上一个分支
```

- `switch` 更语义化，推荐；
- 分离 HEAD 状态下提交会变成"孤儿"commit，需手动建分支保存；
- 切换前确保工作区干净，否则可能冲突。

## merge：合并

| 策略 | 命令 | 特点 |
| --- | --- | --- |
| fast-forward | `git merge <branch>`（默认，能 ff 时） | 不产生 merge commit，历史线性 |
| no-fast-forward | `git merge --no-ff <branch>` | 强制产生 merge commit，保留分支历史 |
| squash | `git merge --squash <branch>` | 压缩为一次改动，需手动 commit |

```bash
git merge <branch>                  # 合并到当前分支
git merge --no-ff <branch>          # 保留 merge commit
git merge --squash <branch>         # 压缩
git merge --abort                   # 合并冲突时放弃合并
git merge --no-commit <branch>      # 合并但不自动提交（复核用）
```

选择策略：

- **--no-ff**：功能分支合并到主干，保留"这是一次功能合并"的历史；
- **squash**：多个 WIP commit 合并成一个干净的 feature commit；
- **ff**：简单更新，无需记录合并点；
- 默认能 ff 就 ff；需要保留分支历史用 `--no-ff`。

合并冲突：

```text
<<<<<<< HEAD
当前分支内容
=======
被合并分支内容
>>>>>>> feature-branch
```

- 冲突必须人工解决，`git add` 标记已解决，`git commit` 完成；
- 不盲目 `--theirs`/`--ours`（会丢一边的改动）；
- 复杂冲突分文件逐个解决，解决后编译/测试验证。

## rebase：变基

`git rebase` 把当前分支的 commit"嫁接"到目标分支顶端，产生线性历史。

```bash
git rebase <base>             # 当前分支变基到 base
git rebase -i <base>          # 交互式（squash/reword/reorder/drop）
git rebase --abort            # 放弃 rebase
git rebase --continue         # 解决冲突后继续
git rebase --onto <new> <old> <branch>  # 精确变基
```

**黄金法则**：不要在共享分支（已推送的）上 rebase。rebase 改写 commit hash，会导致他人历史混乱。

- 个人分支 rebase 到最新主干是安全的；
- 已推送的分支 rebase 后必须 `--force` 推送，会破坏他人工作；
- 交互式 rebase（`-i`）用于整理历史：squash 合并、reword 改消息、reorder 排序、drop 删除。

## cherry-pick：挑选提交

```bash
git cherry-pick <commit>           # 把指定 commit 应用到当前分支
git cherry-pick <c1>..<c2>         # 范围
git cherry-pick --abort            # 放弃
```

- 用于把某个 bugfix 从一个分支移植到另一个；
- 会产生新 commit（不同 hash，相同改动）；
- 冲突处理同 merge。

## worktree：工作树隔离

`git worktree` 让同一仓库的多个分支同时在不同目录检出，无需 stash 或 clone。

| 命令 | 用途 |
| --- | --- |
| `git worktree add <path> <branch>` | 在新目录检出已有分支 |
| `git worktree add <path> -b <new>` | 在新目录创建并检出新分支 |
| `git worktree add <path> HEAD` | 分离 HEAD 检出（临时查看） |
| `git worktree list` | 列出所有工作树 |
| `git worktree remove <path>` | 删除工作树 |
| `git worktree prune` | 清理已删除目录的元数据 |
| `git worktree lock/unlock` | 锁定/解锁（防止被 prune） |

使用场景：

- **并行任务**：一边在 feature-A 改代码，一边在 feature-B 紧急修 bug，无需 stash；
- **代码审查**：检出同事的分支到独立目录，不影响自己的工作区；
- **长期运行**：主工作区跑测试，worktree 里继续开发；
- **对比版本**：同时检出两个版本对比差异。

注意事项：

- 同一分支不能在多个 worktree 同时检出（会报错）；
- worktree 共享同一个 `.git` 仓库（对象、远程、配置）；
- 删除 worktree 目录前用 `git worktree remove`（避免残留元数据）；
- 主工作区在仓库根，worktree 是附加的。

## 分支命名约定

```text
feature/<jira-id>-<short-desc>     # 新功能
fix/<jira-id>-<short-desc>         # bug 修复
hotfix/<short-desc>                # 紧急修复
chore/<short-desc>                 # 杂项
release/<version>                  # 发布分支
```
