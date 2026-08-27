# 安全门控

## 危险操作分级

| 级别 | 命令 | 风险 | 门控 |
| --- | --- | --- | --- |
| 只读 | status/diff/log/show/blame/reflog/fetch | 无 | 可直接执行 |
| 需确认 | add/commit/branch/checkout/stash/tag/restore | 可控 | 默认 dry-run，显式授权 |
| 高风险 | merge/rebase/cherry-pick/reset --soft/push | 影响历史/远程 | 必须显式授权 + 验证 |
| 危险 | reset --hard/push --force/filter-branch/branch -D/clean -fdx | 不可逆 | 强烈不建议 + 记录恢复点 |

## 不可逆操作

以下操作一旦执行，数据可能永久丢失（reflog 也救不回）：

- `git reset --hard` 丢失未提交的工作区改动；
- `git clean -fdx` 删除 `.gitignore` 忽略的文件（含 node_modules、.env）；
- `git push --force` 覆盖远程历史，他人基于旧历史的 commit 变孤儿；
- `git filter-branch` 改写所有历史；
- `git branch -D` 删除未合并的分支。

执行前必须：

1. 记录当前 HEAD：`git rev-parse HEAD > /tmp/recovery-point`；
2. 确认 `git status` 干净或已 stash；
3. 确认 reflog 可恢复：`git reflog -5`；
4. 用户显式确认。

## 共享分支保护

```text
禁止在共享分支（main/master/develop/release/*）执行：
  - git rebase（改历史）
  - git reset --hard（改历史）
  - git push --force（覆盖远程）
  - git filter-branch（改写全部历史）
```

共享分支的"撤销"用 `git revert`（追加反向 commit），不改历史。

## force push 规则

- 默认禁止 `git push --force`；
- 个人分支整理历史后确需 force push，用 `--force-with-lease`（更安全，远程被他人更新时拒绝）；
- `--force-with-lease` 仍会覆盖远程，只在确信无人基于此分支时用；
- 共享分支永不 force push。

## 密钥与敏感数据保护

### 绝不提交

- `.env`、`.env.local`、`.env.production`（保留 `.env.example`）；
- 凭据文件（含 `secret/password/credentials/token/apikey` 的路径）；
- 私钥（`.pem/.key/.p12/.pfx`，`docs/` 示例证书除外）；
- 数据库 dump（`*.sql.gz/*.dump`）。

### 误提交后处理

```bash
# 从历史移除（会改写历史，需 force push）
git filter-branch --tree-filter 'rm -f .env' HEAD
# 或用 BFG Repo-Cleaner（更快）
bfg --delete-files .env

# 立即轮换泄露的密钥（改历史不能撤销已泄露）
```

- 改历史不能撤销"已泄露"——密钥一旦推送，视为已泄露，必须轮换；
- GitHub 的 secret scanning 会自动通知泄露；
- 团队通知并审计相关系统的访问记录。

## 自动化提交门控

```text
强制确认（唯一模式，无 auto 绕过通道）：
  - 只读 git status/diff
  - 输出提交计划（待提交文件清单 + 提交信息）
  - 等待用户明确确认；未确认不执行任何 add/commit

用户确认后执行：
  - git add <过滤后文件>
  - git commit -m "..."
  - 不 push

push 门控（默认不推送）：
  - git push 需用户单独明确确认
  - 不 --force
```

任何模式：

- 命中黑名单的文件单独列出，不自动 stage；
- pre-commit hook 失败立即停止；
- 任一命令失败立即停止并报告当前状态。

## 操作前后验证

```bash
# 操作前
git status --short
git rev-parse HEAD          # 记录恢复点

# 执行操作
git <command>

# 操作后
git status --short          # 确认状态
git log --oneline -3        # 确认历史
git reflog -3               # 确认可回退
```

## pre-commit hook

项目应配置 pre-commit hook 自动检查：

- 密钥扫描（gitleaks/truffleHog）；
- 格式化（prettier/black/gofmt）；
- lint（eslint/ruff/golangci-lint）；
- 大文件检测；
- commit message 格式（commitlint）。

hook 失败时提交被拒绝，不要 `--no-verify` 绕过（除非明确知道后果并记录）。
