# worktree：放哪、怎么用、怎么收

## 放哪（已定：**仓库同级**）

```text
~/Documents/workspace/project-personal/
├── specforge/                                  ← 仓库
└── specforge-feat-ui-shadcn-vue/               ← 它的 worktree
```

路径公式就是 `dirname(repo_root) + "/" + basename(repo_root) + "-" + slug(分支名)`，
`worktree.py create` 默认走它。

**为什么不在仓库里**（`.worktrees/` 那种）：放在仓库里就得往 `.gitignore` 加规则，
而且每拉一个新分支都多一次「记得别提交它」的自觉 —— 而自觉是这一整套东西里最不可靠
的一环。放在同级等于把这条规则改成**结构上不可能犯**。

**为什么不用 `~/workspace/`**：你原来那个 `~/workspace/specforge-flow-optimization`
是 agent 自己挑的位置，和仓库不在一个父目录下 —— 于是「这个 worktree 属于谁」只能靠
名字猜。同级之后，`ls` 一眼就能把仓库和它的 worktree 连起来看。

## 命名

分支名里的 `/` 不能留在目录名里（会变成多一层目录），所以换成 `-`：

| 分支 | 目录 |
| --- | --- |
| `feat/ui-shadcn-vue` | `specforge-feat-ui-shadcn-vue` |
| `codex/specforge-flow-optimization` | `specforge-codex-specforge-flow-optimization` |

**不强制小写**。macOS 的文件系统默认不区分大小写 —— `Feat/x` 与 `feat/x` 会撞到同一个
目录上。撞上时脚本会拒绝（目标已存在），不会替你二选一。

## 生命周期

```sh
# 建：分支从 main 起，目录自动放到同级
python3 scripts/worktree.py create feat/ui --from main

# 看：每个 worktree 的干净度、未推送数、以及**能不能回收**
python3 scripts/worktree.py list

# 只列能回收的
python3 scripts/worktree.py list --stale

# 收：先过判据，判据说不行就不动手
python3 scripts/worktree.py remove ../specforge-feat-ui
```

## 回收判据（**按实测改过一次**）

原来的写法是「三项前置：已并入基线 / 无未推送 / 无未提交」。**实测证明那个前提是错的**：
用例断言过 —— `git worktree remove` **只拿掉工作目录和记录，不删分支、不删提交**。
分支和它的提交留在共享的对象库里，`git branch` 里照样看得到。

错在哪：把「未推送」当成了数据丢失条件。可它防的那种情况（"那份工作没人管了"）是**提醒**，
不是损失；而且在没有远端的仓库里「未推送」恒为真 —— 会把回收**永久卡死**。

现在的判据按事实分两档：

| 情况 | 结论 | 为什么 |
| --- | --- | --- |
| 那个目录里有**未提交改动** | **BLOCK** | 这是唯一真会丢的东西 —— 未提交的内容只存在于那个目录里 |
| 分支**没并进基线** | WARN | 不丢东西（分支还在），但先确认你不是正在做到一半 |
| 干净且已并入 | SAFE | 没有可丢的 |

**回收不会顺手删分支** —— 删分支是另一件事、另一道判据（`git_guard.py delete-branch`），
它关心的是"那些提交在别处还有没有"。

## prune 和 remove 不是同一件事

| 命令 | 干什么 | 什么时候用 |
| --- | --- | --- |
| `prune` | 只清掉**目录已经不存在**的那些记录 | 你手删过目录、或者别人删过（实测你那个 `codex/specforge-flow-optimization` 就是这样，`worktree list` 里标着 `prunable`） |
| `remove <路径>` | 把一个**目录还在**的 worktree 收回去（过判据） | 活干完了 |

`prune` 是安全的：它只动那些指向不存在目录的记录。

## 交给并行的 agent

你已经在这么做（`codex/specforge-flow-optimization`、`pi-parallel-<uuid>` 这类分支名就是
这么来的）。两条经验：

1. **一个 worktree 同时只给一个写者** —— 这是 worktree 存在的意义；两个 agent 写同一个
   目录，就是两个 agent 改同一份工作区，跟没用 worktree 一样。
2. **agent 的分支名会攒下来**。`pi-parallel-<uuid>` 这种带 UUID 的名字，事后没人认得出它
   是干什么的 —— 所以回收时要看它**有没有并进基线**，而不是看名字。

## 四个坑

| 坑 | 后果 | 脚本怎么处理 |
| --- | --- | --- |
| 同级目录落在**另一个仓库**里 | 那个仓库会把新目录当成未跟踪内容收进去 | `create` 前用 `rev-parse --show-toplevel` 查上一级，撞上就拒绝 |
| **手删目录**而不 `prune` | 留下一堆 `prunable` 记录（你已经有一个） | `list` 会标出来，`prune` 清掉 |
| 同一个分支挂两个 worktree | git 自己就不允许 | 不用管 |
| 大小写不敏感的文件系统 | `Feat/x` 与 `feat/x` 撞目录 | 撞上时拒绝，不猜 |

## 这个脚本不做的事

- **不 `--force`**：判据说不行就是不行。
- **不删还有文件的目录**：那是 `rm -rf` 的活，`git worktree remove` 会拒绝，这里不替它绕。
- **不碰你的分支合并策略**：它只负责把目录建出来、把目录收回去。
