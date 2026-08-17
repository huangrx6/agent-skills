# Git 基础概念

## 四个区域

| 区域 | 含义 | 查看命令 |
| --- | --- | --- |
| 工作区（Working Directory） | 当前磁盘上的文件 | `git status` |
| 暂存区（Staging/Index） | 下次要提交的快照 | `git diff --cached` |
| 本地仓库（Local Repo） | 已提交的历史 | `git log` |
| 远程仓库（Remote） | 协作的中央仓库 | `git remote -v` |

数据流向：工作区 →（`git add`）→ 暂存区 →（`git commit`）→ 本地仓库 →（`git push`）→ 远程仓库。

反向：远程 →（`git fetch/pull`）→ 本地仓库 →（`git checkout/reset`）→ 工作区。

## 对象模型

Git 是内容寻址的对象存储，每个对象用 SHA-1 哈希标识：

| 对象 | 内容 |
| --- | --- |
| blob | 文件内容快照 |
| tree | 目录结构（指向 blob 和子 tree） |
| commit | 指向一个 tree + parent commit + 元数据（作者/时间/消息） |
| tag | 带注释的标签，指向 commit |

理解对象模型的意义：

- `git commit` 创建新对象，不修改旧对象（历史不可变）；
- "改历史"命令（reset/rebase）只是移动分支指针，旧 commit 仍在 reflog 中；
- 哈希校验保证完整性，损坏会报错而非静默损坏。

## 状态码

`git status --short` 每行两列状态码：

| 码 | 含义 |
| --- | --- |
| `??` | 未跟踪 |
| `A` | 新增到暂存区 |
| `M` | 修改（第一列=暂存区改动，第二列=工作区改动） |
| `D` | 删除 |
| `R` | 重命名 |
| `C` | 复制 |
| `U` | 冲突未解决 |

例：` M file.txt`（工作区改了但没 add）；`M  file.txt`（add 了但工作区又有新改动）；`MM file.txt`（暂存区和工作区都有改动）。

## 配置

- `git config --global user.name/user.email`：身份；
- `git config core.autocrlf`：换行符（Windows `true`，Mac/Linux `input`）；
- `.gitignore`：忽略未跟踪文件；
- `.gitattributes`：行尾、二进制、合并策略等属性。

## .gitignore 原则

- 提交 `.gitignore` 本身；
- 忽略构建产物（`node_modules/`、`dist/`、`__pycache__/`）；
- 忽略环境变量（`.env`、`.env.local`）；
- 忽略 IDE 文件（`.idea/`、`.vscode/` 但保留共享配置）；
- 不忽略已跟踪文件（`.gitignore` 对已跟踪文件无效，需先 `git rm --cached`）。

## reflog

`git reflog` 记录 HEAD 的所有移动（包括 reset、checkout、rebase），是误操作的最后一道安全网。

```text
a1b2c3d HEAD@{0}: reset: moving to HEAD~1
e4f5g6h HEAD@{1}: commit: feat: add feature
```

误删分支或 reset 后，用 `git reflog` 找回 commit hash，`git reset --hard <hash>` 恢复。reflog 默认保留 90 天。

## 只读证据采集

操作前用只读命令了解现状：

```bash
git status --short                    # 全部变更
git diff --stat                       # 工作区改动摘要
git diff --cached --stat              # 暂存区改动摘要
git log --oneline -10                 # 最近提交
git reflog -10                        # 最近 HEAD 移动
git branch -vv                        # 本地分支与跟踪关系
git remote -v                         # 远程仓库
```
