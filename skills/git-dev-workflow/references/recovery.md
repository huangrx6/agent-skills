# 误操作之后：能救什么、救不回什么

## 先说边界（这段最重要）

**reflog 只覆盖本地，而且只在对象被回收之前。** 它不是备份：

- 它记的是"这个仓库里的 HEAD 和分支引用移动过哪些位置"。
- 默认保留 `gc.reflogExpire` = 90 天（可达的）、`gc.reflogExpireUnreachable` = 30 天
  （不可达的）—— 但**跑过一次 `git gc --prune=now` 就可能立刻没**。
- 别人的 clone 里没有你的 reflog；你也没有别人的。

所以这份文档的承诺是「**多数误操作有救，但别把它当保险**」，不是「什么都能救」。

## 第一件事：先取证，再动手

出事之后**不要马上在同一个仓库里继续操作**。先把现场抄下来：

```sh
git reflog > /tmp/reflog-$(date +%s).txt      # 这是最重要的证据
git status --porcelain > /tmp/status.txt
python3 scripts/git_report.py                  # 如果之前存过快照，这里有前后对照
```

理由：reflog 的顺序本身是线索（"我是什么时候把它弄丢的"），而后续操作会往上面继续写。

## 分类：能不能救

| 你做了什么 | 还能救吗 | 怎么做 |
| --- | --- | --- |
| `reset --hard` 丢掉了**提交过**的东西 | **能** | `git reflog` 找到那个 sha，`git reset --hard <sha>` |
| `reset --hard` 丢掉了**未提交**的改动 | **基本不能** | 没进过对象库就没有副本。`git fsck --lost-found` 偶尔能捡回 blob，那是碰运气 —— 别指望 |
| `checkout -- .` / `restore .` 丢掉未暂存改动 | **基本不能** | 同上 |
| `clean -fd` 删掉未跟踪文件 | **不能** | 未跟踪文件从来没进过对象库 |
| `clean -x` 删掉被 ignore 的文件（`.env` 之类） | **不能** | 同上 —— 这正 `git_guard.py clean-untracked` 要拦它的原因 |
| `branch -D` 删掉已并入的分支 | **能** | `git reflog` 或 `git branch <名> <sha>` |
| `branch -D` 删掉**未并入**的分支 | **通常能** | 分支自己的 reflog 没了，但那些提交还在对象库里：`git reflog`、或 `git fsck --unreachable \| grep commit` 找回来 |
| `stash drop` / `stash clear` | **通常能** | `git fsck --unreachable \| grep commit`，对每个候选 `git stash apply <sha>` 试 |
| `rebase` 中途乱了 | **能** | `git rebase --abort` 回起点；已经结束的用 `git reflog` 找 rebase 之前的 HEAD |
| `commit --amend` 之后想找回旧提交 | **能** | `git reflog`（amend 前的那个 sha 还在） |
| 强推覆盖了远端 | **看情况** | 本地还有的话直接推回去；本地也没有，就得找**某个还没 fetch 过的 clone** —— 这是唯一真正棘手的 |

## 具体步骤

### 找回被 reset / rebase 弄丢的提交

```sh
git reflog --date=iso | head -30        # 找那一行：reset: moving to …
git show <sha>                          # 先看清楚是不是你要的那个
git reset --hard <sha>                  # 确认之后再动
```

**先 `git show` 再 `reset`** —— reflog 里相邻两行长得一样很常见（"reset: moving to HEAD"
出现好几次），点错了就又丢一次。

### 找回被删的分支

```sh
git reflog | grep -i checkout           # 那个分支最后一次被 checkout 的 sha
git branch <分支名> <sha>               # 重建指针（此时还没动任何内容）
```

### 找回被 drop 的 stash

```sh
git fsck --unreachable 2>/dev/null | grep commit | awk '{print $3}' \
  | while read sha; do git log -1 --format='%h %s' "$sha"; done | head -20
git stash apply <看起来对的那个 sha>
```

stash 的提交是**普通提交**（有多个父），所以 `git stash apply <sha>` 能直接吃它。

### 强推之后的远端

```sh
git reflog show <分支>                  # 本地还留着的话，直接推回去
git push --force-with-lease origin <分支>
```

远端没有本地也没有，就只能找别人的 clone —— 所以**强推之前先 `--force-with-lease`**，
让"远端被别人动过"这种情况直接被挡下来。

## 什么时候可以确定放弃

- 丢的是**未提交**内容（`clean`、`checkout --`、`reset --hard` 的那部分）—— 除非捡到 blob。
- 已经跑过 `git gc --prune=now` 且超过了 `gc.reflogExpireUnreachable`。
- 丢的内容从未 commit 过，而我们也没有别的副本（编辑器自动保存、IDE 的 local history
  是可以试一试的地方 —— 但那不在 git 的范围里）。

**判断不了就说不确定**，不要说"应该没事" —— 这句话会让人停止寻找。
