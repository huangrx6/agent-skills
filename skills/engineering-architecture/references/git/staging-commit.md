# 暂存与提交

## add：精确暂存

`git add` 把工作区改动放入暂存区。优先精确 add，慎用 `git add -A`/`git add .`。

| 命令 | 用途 |
| --- | --- |
| `git add <file>` | 暂存单个文件 |
| `git add <dir>/` | 暂存目录 |
| `git add -p <file>` | 交互式选择 hunk 暂存（拆分提交） |
| `git add -A` | 暂存全部（含删除/新增） |
| `git add .` | 暂存当前目录 |
| `git add -u` | 暂存已跟踪文件的改动（不含新增） |

- 一个 commit 只做一件事；用 `git add -p` 把同一文件的不同改动拆成多个 commit；
- `git add` 前先 `git diff` 确认内容；
- 不要 `git add -A` 后才发现混入了密钥/大文件。

## commit：创建提交

```bash
git commit -m "<message>"             # 单行消息
git commit -m "<title>" -m "<body>"   # 标题 + 正文
git commit --amend                    # 修改最近一次提交（未推送时）
git commit --amend --no-edit          # 补充文件到上次提交，不改消息
```

- 提交信息遵循 Conventional Commits（见 commit-message.md）；
- `--amend` 只在未推送时使用；已推送的提交不要 amend（会改历史）；
- 提交前 `git diff --cached` 复核暂存内容。

## stash：临时保存

`git stash` 把工作区改动临时存起来，恢复干净工作区。

| 命令 | 用途 |
| --- | --- |
| `git stash` | 保存跟踪文件的改动 |
| `git stash -u` | 含未跟踪文件 |
| `git stash -a` | 含 .gitignore 忽略的文件 |
| `git stash list` | 查看 stash 栈 |
| `git stash pop` | 恢复并删除最近 stash |
| `git stash apply` | 恢复但保留 stash |
| `git stash drop` | 删除最近 stash |
| `git stash clear` | 清空所有 stash（危险） |

- stash 是栈，`pop` 恢复最近的；
- 长期 stash 容易遗忘，建议转成临时分支 `git stash branch <name>`；
- `stash pop` 冲突时 stash 保留，需手动解决。

## 自动 stage 安全过滤

自动化场景必须过滤高危文件。默认黑名单（跳过）：

| 类别 | 示例 |
| --- | --- |
| 环境变量 | `.env`、`.env.*`（但保留 `.env.example`） |
| 凭据关键字 | 路径含 `secret/password/credentials/token/apikey/private_key` |
| 私钥扩展名 | `.pem/.key/.p12/.pfx/.crt/.cer`（`docs/` 示例证书白名单放行） |
| 数据库 dump | `*.sql.gz/*.dump/*.bak` |
| 锁文件 | `package-lock.json/yarn.lock/poetry.lock/Cargo.lock`（`--include-locks` 启用） |
| 构建产物 | `node_modules/dist/build/__pycache__/.next/` |
| 系统文件 | `.DS_Store/Thumbs.db` |
| 大文件 | 新文件 > 10MB（`--max-size` 调整） |

白名单（放行例外）：`.gitignore`、`.env.example`、`LICENSE`、配置类代码（`tsconfig.json`/`pyproject.toml`/`conftest.py`）。

命中黑名单的文件写入"待手动确认清单"，不自动 stage。即使 `--force-include`，`.env`/凭据/私钥仍强制排除。

## 工作流总结

```text
1. git status --short           # 看全部变更
2. git diff [file]              # 确认内容
3. git add <精确文件或 -p>       # 暂存
4. git diff --cached            # 复核暂存内容
5. git commit -m "..."          # 提交
6. git status --short           # 确认干净
```
