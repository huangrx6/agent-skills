# 回退与恢复

## reset：移动分支指针（改历史）

`git reset` 移动当前分支指针到指定 commit，可选影响暂存区和工作区。

| 模式 | 暂存区 | 工作区 | 效果 |
| --- | --- | --- | --- |
| `--soft` | 不变 | 不变 | 只移动 HEAD，改动保留在暂存区 |
| `--mixed`（默认） | 重置 | 不变 | 暂存区重置，改动保留在工作区 |
| `--hard` | 重置 | 重置 | 彻底丢弃（危险，工作区改动丢失） |

```bash
git reset HEAD~1               # 撤销最近 commit，改动回到工作区（--mixed 默认）
git reset --soft HEAD~1        # 撤销 commit，改动保留在暂存区
git reset --hard HEAD~1        # 撤销 commit 并丢弃改动（危险）
git reset <file>               # 取消暂存某文件（不丢改动）
git reset HEAD <file>          # 同上（旧语法）
```

- `--hard` 是危险操作，会永久丢失工作区改动；
- `--hard` 丢失的改动**可能**通过 reflog 找回（如果之前 commit/stash 过）；
- reset 改写当前分支历史，已推送的不要 reset。

## revert：反向提交（不改历史）

`git revert` 创建一个新 commit，内容是撤销指定 commit 的改动。历史是追加的，不改写。

```bash
git revert <commit>            # 撤销单个 commit
git revert <c1>..<c2>          # 撤销范围
git revert --no-commit <c>     # 撤销但不自动提交（批量时用）
git revert --abort             # 放弃
```

- **已推送的提交用 revert，不用 reset**；
- revert 产生新 commit，他人 pull 不会冲突；
- revert 一个 merge commit 需要 `-m 1`（指定保留哪边）；
- 多次 revert 可能互相抵消，注意顺序。

## restore：恢复文件（Git 2.23+）

`git restore` 是 `checkout` 文件恢复部分的语义化替代。

```bash
git restore <file>             # 工作区文件恢复到暂存区版本
git restore --staged <file>    # 暂存区文件取消暂存（等同 reset <file>）
git restore --source=<commit> <file>  # 恢复到指定 commit 的版本
git restore --source=HEAD --staged --worktree <file>  # 彻底恢复到 HEAD
```

- `restore` 只影响文件，不影响分支指针；
- 比 `checkout <file>` 语义更清晰；
- `--staged --worktree` 同时重置两个区域（等同 `reset --hard <file>` 但不碰 HEAD）。

## checkout：恢复与切换（旧语法）

```bash
git checkout -- <file>         # 丢弃工作区改动（等同 restore <file>）
git checkout HEAD -- <file>    # 恢复到 HEAD（工作区+暂存区）
git checkout <commit> -- <file>  # 恢复某文件到指定 commit
```

`--` 用于区分文件名和分支名。Git 2.23+ 推荐用 `restore`/`switch` 替代。

## reflog：找回丢失的提交

`git reflog` 记录 HEAD 的所有移动，是误操作的最后一道安全网。

```bash
git reflog                     # 查看所有 HEAD 移动
git reflog -20                 # 最近 20 条
git reflog <branch>            # 查看指定分支的移动
```

恢复误删/误 reset：

```bash
git reflog                     # 找到丢失 commit 的 hash
git reset --hard <hash>        # 恢复到那个点
# 或创建新分支保存
git branch <recover-branch> <hash>
```

- reflog 是本地的，不影响他人；
- 默认保留 90 天（可达的）/30 天（不可达的）；
- `git gc` 会清理过期 reflog 条目；
- 分支被 `-D` 删除后，commit 仍在 reflog，可恢复。

## clean：删除未跟踪文件

```bash
git clean -n                  # 预览（dry-run）
git clean -f                  # 删除未跟踪文件
git clean -fd                 # 删除未跟踪文件和目录
git clean -fdx                # 含 .gitignore 忽略的（危险）
git clean -i                  # 交互式
```

- `clean` 只删未跟踪文件（`??` 状态）；
- 已跟踪文件的改动不受影响（用 `restore`/`reset`）；
- `-x` 会删除 `.gitignore` 忽略的（如 `node_modules`），极其危险；
- 永远先 `-n` 预览再 `-f`。

## 回退决策表

| 场景 | 推荐命令 | 是否改历史 |
| --- | --- | --- |
| 撤销未推送的 commit，保留改动 | `git reset HEAD~1` | 改本地历史（安全） |
| 撤销未推送的 commit，丢弃改动 | `git reset --hard HEAD~1` | 改本地历史（危险） |
| 撤销已推送的 commit | `git revert <commit>` | 不改历史（安全） |
| 取消暂存某文件 | `git restore --staged <file>` | 不改历史 |
| 丢弃工作区改动 | `git restore <file>` | 不改历史 |
| 恢复误删的分支/commit | `git reflog` + `reset --hard` | 改本地历史 |
| 删除未跟踪的临时文件 | `git clean -n` 预览后 `-f` | 不改历史 |
