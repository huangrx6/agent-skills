# Git 误操作恢复

先保留当前状态与 reflog，暂停会删除对象或覆盖工作区的操作。不要运行 `gc --prune=now`。
取证文件放在用户认可的临时位置；不必把完整历史粘贴进聊天。

```sh
git status --porcelain=v1
git reflog --date=iso
git show --stat <候选提交>
```

找到提交后，优先创建救援分支，或在独立 worktree 检查内容；这比直接再次 reset 更容易验证。
若确实要恢复当前分支，先保存当前未提交内容，再核对 guard 与用户授权。

| 情况 | 可尝试的恢复 |
| --- | --- |
| reset/rebase/amend 丢失已提交内容 | 从 reflog 找旧 SHA，`git branch rescue/<name> <sha>` 保留它 |
| 删除分支 | HEAD reflog、其他引用或 `git fsck --unreachable` 查提交；分支自身 reflog 可能已删除 |
| stash drop/clear | `git fsck --unreachable` 查候选多父提交，先 inspect，再在干净的临时工作树 `git stash apply <sha>` |
| 进行中的 rebase/merge 出错 | 核对当前冲突及未保存内容后，按任务继续或使用对应 `--abort` |
| 丢失未暂存改动，或 clean 删除未跟踪文件 | Git 通常没有副本；检查编辑器 local history、系统备份。曾暂存的 blob 有时仍可从对象库找到 |
| 强推覆盖远端 | 检查本地/其他 clone 的 reflog、分支、标签与服务端保留能力；先保留旧 SHA，再决定如何恢复远端 |

reflog 是本地引用移动记录，不是备份。保留期限取决于仓库配置与对象回收；
对象还在时历史改写也可能恢复。找不到 reflog 不等于对象已消失；找到 SHA 也不等于它的内容就是目标。

恢复强推需要重新核对远端现状和共享分支授权。`--force-with-lease` 只能防止超出预期的引用变动，
不会判断恢复内容是否正确。只在获得明确授权时通知其他协作者。
