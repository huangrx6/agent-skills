# Git 工作流端到端示范（虚构项目 NovaPay）

## 场景 1：功能开发提交

### 初始状态

```bash
git status --short
```

```text
 M src/orders/export.py
 M src/orders/api.py
?? src/orders/bulk_export.py
?? tests/test_bulk_export.py
?? .env.local
```

### 评估

- 两个 Python 改动 + 两个新文件属于"批量导出"功能 → 1 个 commit；
- `.env.local` 命中黑名单（环境变量），不 stage。

### 执行（dry-run 计划）

```text
待提交计划（1 个 commit，工作树涉及 5 个文件）：

[1] feat(orders): add bulk export endpoint
    4 files
    src/orders/export.py
    src/orders/api.py
    src/orders/bulk_export.py
    tests/test_bulk_export.py

⚠️ 已过滤 1 个文件，未纳入本次提交：
    .env.local（黑名单：环境变量）

用户明确确认（例如回复「确认提交」）后，再执行以下命令。
```

### 执行（确认后）

```bash
git add src/orders/export.py src/orders/api.py src/orders/bulk_export.py tests/test_bulk_export.py
git commit -m "feat(orders): add bulk export endpoint"
git status --short
```

## 场景 2：分支合并

### 功能分支合并到 main（保留历史）

```bash
# 记录恢复点
git rev-parse HEAD                    # a1b2c3d

# 切到 main 并拉取最新
git switch main
git pull

# 合并功能分支（保留 merge commit）
git merge --no-ff feature/bulk-export -m "Merge feature/bulk-export: add bulk export endpoint"

# 验证
git log --oneline --graph -5
```

### 合并冲突解决

```bash
git merge feature/bulk-export
# CONFLICT (content): Merge conflict in src/orders/api.py

# 打开文件，解决冲突标记（<<<<<<< ======= >>>>>>>）
# 解决后：
git add src/orders/api.py
git commit                            # 完成合并

# 放弃合并：
git merge --abort
```

## 场景 3：回退操作

### 撤销未推送的 commit（保留改动）

```bash
git log --oneline -3
# a1b2c3d feat: add x
# e4f5g6h fix: handle y

git reset HEAD~1                      # 撤销 a1b2c3d，改动回到工作区（--mixed 默认）
git status --short                    # 改动还在，可重新提交
```

### 撤销已推送的 commit（用 revert，不改历史）

```bash
# 错误：已推送的 commit 不能 reset
# 正确：用 revert

git revert a1b2c3d                    # 创建反向 commit
git push                              # 推送 revert commit
```

### 恢复误删的分支

```bash
git branch -D feature/old             # 误删
git reflog                            # 找回 hash：f1e2d3c
git branch feature/recovered f1e2d3c  # 从 hash 恢复
```

### 恢复 reset --hard 丢失的改动

```bash
git reset --hard HEAD~1               # 误操作，丢了工作区改动
git reflog                            # 找回之前的 HEAD：a1b2c3d
git reset --hard a1b2c3d              # 恢复
```

## 场景 4：worktree 隔离并行任务

### 在主工作区开发时，紧急修 bug

```bash
# 主工作区正在开发 feature-A（未完成，不想 stash）

# 创建 worktree 检出 hotfix 分支
git worktree add ../novapay-hotfix -b hotfix/critical-bug

cd ../novapay-hotfix
git status                            # 干净的 hotfix 工作区
# 修复 bug...
git add fix.py
git commit -m "fix(auth): handle null token"
git push origin hotfix/critical-bug

# 完成后清理
cd ../novapay-main
git worktree remove ../novapay-hotfix
git worktree list                     # 确认已清理
```

### 同时对比两个版本

```bash
git worktree add ../novapay-v1.0 v1.0-tag
# 现在有两个目录：主工作区（最新）和 ../novapay-v1.0（v1.0）
diff -r src/ ../novapay-v1.0/src/
```

## 场景 5：整理历史（个人分支）

### 交互式 rebase 合并 WIP commit

```bash
# 个人分支，未推送
git log --oneline -5
# a1b2 wip
# c3d4 wip
# e5f6 wip
# g7h8 feat: add export base

git rebase -i g7h8
# 编辑器打开：
#   pick e5f6 feat: add export base
#   pick c3d4 wip
#   pick a1b2 wip
# 改为：
#   pick e5f6 feat: add export base
#   squash c3d4 wip
#   squash a1b2 wip
# 保存后修改 commit message

git log --oneline -3
# newhash feat(orders): add bulk export endpoint
# g7h8 ...
```

## 场景 6：标签发布

```bash
# 创建带注释的标签
git tag -a v1.2.0 -m "Release 1.2.0: bulk export feature"

# 推送标签
git push origin v1.2.0

# 查看标签
git tag -l
git show v1.2.0
```

## 通用操作前后检查

```bash
# 操作前
git status --short
git rev-parse HEAD > /tmp/recovery-point

# 执行操作
# ...

# 操作后
git status --short
git log --oneline -3
git reflog -3
```
