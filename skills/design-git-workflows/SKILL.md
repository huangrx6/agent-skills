---
name: design-git-workflows
description: "设计、审查和执行生产级 Git 工作流，覆盖工作区与暂存区管理、分支与合并策略、worktree 隔离、提交信息（Conventional Commits）、回退与恢复（reset/revert/reflog）、标签与版本、远程协作、冲突解决和危险操作门控。用于建立项目级 Git 规范、安全执行 add/commit/merge/rebase/reset、评审 Git 操作风险、自动化提交归类，以及在误操作后可靠恢复。不覆盖代码审查内容、持续集成配置与发布流水线编排。"
---

# Git 工作流设计

## 目标

让每个 Git 操作都有明确的意图、安全边界、可回退路径和可验证结果，避免"一条命令毁掉工作"或"提交历史无法追溯"。本 Skill 覆盖从基础 add/commit 到 worktree 隔离、合并策略、回退恢复的完整链路。

## 职责边界

本 Skill 负责：

- 工作区与暂存区管理（add/reset/restore/stash）；
- 提交与提交信息（commit + Conventional Commits）；
- 分支与合并（branch/merge/rebase/cherry-pick + worktree 隔离）；
- 回退与恢复（reset/revert/reflog/checkout）；
- 标签与版本（tag + SemVer）；
- 远程协作（remote/fetch/pull/push）；
- 冲突解决与危险操作门控。

本 Skill 不负责：

- 代码审查内容本身（逻辑、设计、安全审查）：不属本 Skill 范围；
- 持续集成与发布流水线编排：不属本 Skill 范围；
- 仓库托管平台的权限管理与 PR/MR 审批流程：不属本 Skill 范围。

## 工作流

1. **先看状态**：任何操作前运行 `git status --short`，识别工作区、暂存区、未跟踪文件。
2. **判断意图**：是要暂存、提交、分支、合并、回退还是恢复？
3. **评估风险**：查命令安全矩阵，确认是否需要用户确认、是否影响历史、是否可回退。
4. **执行最小操作**：优先只读命令确认，再做写操作；默认 dry-run；`git commit` 必须先展示提交计划并等待用户明确确认，未确认不执行。
5. **验证结果**：操作后用 `git status`/`git log`/`git reflog` 确认预期。
6. **记录可回退点**：危险操作前记录当前 HEAD，确保能用 reflog 恢复。

## 核心规则

- **先看再改**：任何写操作前先 `git status`；不混入未跟踪的密钥、环境变量、大文件。
- **提交必须确认**：任何 `git commit` 前必须先展示提交计划（待提交文件清单 + 提交信息），等待用户明确确认；未获得确认绝不执行 commit。
- **不自动 push**：`git push` 必须显式授权；默认不推送，不 `--force`。
- **保护历史**：不在共享分支上 `rebase`/`reset --hard`/`filter-branch`；已推送的提交不强制改写。
- **保护密钥**：`.env`、凭据、私钥、构建产物默认不 stage；命中黑名单必须单独确认。
- **原子提交**：按功能单元分组提交；一个 commit 只做一件事；Conventional Commits 规范。
- **可回退优先**：危险操作前记录 HEAD；优先 `revert`（不改历史）而非 `reset`（改历史）。
- **worktree 隔离**：并行任务用 worktree 隔离，不在主工作区同时做多件事。
- **冲突不猜测**：冲突必须人工解决并验证；不盲目 `--theirs`/`--ours` 覆盖。
- **reflog 是安全网**：误操作后先用 `git reflog` 找回历史 HEAD，再用 `reset --hard <hash>` 恢复。

## 命令安全分级

| 等级 | 命令 | 默认行为 |
| --- | --- | --- |
| 只读 | status/diff/log/show/blame/reflog/fetch | 可直接执行 |
| 需确认 | add/commit/branch/checkout/stash/tag | commit 必须先展示计划并等用户确认；其余默认 dry-run，显式授权执行 |
| 高风险 | merge/rebase/cherry-pick/reset/push | 必须显式授权 + 操作前后验证 |
| 危险 | reset --hard/push --force/rebase -i（共享分支）/filter-branch/branch -D | 强烈不建议，需额外确认 + 记录恢复点 |

## 参考文件选择

- 处理工作区/暂存区概念、对象模型、配置时，读取 [references/git-fundamentals.md](references/git-fundamentals.md)。
- 处理 add/commit/stash/自动归类过滤时，读取 [references/staging-commit.md](references/staging-commit.md)。
- 处理分支、合并策略、rebase、cherry-pick、worktree 时，读取 [references/branching-merging.md](references/branching-merging.md)。
- 处理 reset/revert/restore/reflog 回退恢复时，读取 [references/undo-recovery.md](references/undo-recovery.md)。
- 撰写 Conventional Commits 提交信息时，读取 [references/commit-message.md](references/commit-message.md)。
- 处理危险操作门控、auto-stage 过滤、密钥保护时，读取 [references/safety-gates.md](references/safety-gates.md)。
- 了解 Git 官方文档、Conventional Commits、SemVer 权威来源时，读取 [references/standards-sources.md](references/standards-sources.md)。

## 输出结构

Git 操作方案优先采用：

1. 当前状态摘要（git status 输出解读）；
2. 操作意图与风险评估；
3. 执行计划（按功能单元分组 + 命令序列）；
4. 安全过滤结果（被排除的文件及原因）；
5. 验证步骤（操作后的确认命令）；
6. 回退方案（如何撤销本次操作）。

任何提交都必须先展示计划（待提交文件清单 + 提交信息）并等待用户明确确认，确认后才执行 add+commit；`git push` 同样需要用户单独明确确认，默认不推送、不 `--force`。不存在绕过确认的 `auto` 通道。

## 内置资源

- `assets/git-command-safety-matrix.csv`：命令安全等级矩阵。
- `assets/commit-type-catalog.csv`：Conventional Commits 类型目录。
- `assets/merge-strategy-matrix.csv`：合并策略选择矩阵。
- `assets/git-review-checklist.csv`：Git 操作评审清单。
- `assets/commit-message.template.md`：提交信息模板。
- `examples/` 目录：Git 工作流端到端示例。
- `scripts/validate_git_assets.py`：校验上述资产。

修改资产后运行：

```bash
uv run scripts/validate_git_assets.py --assets assets/
```

## 环境与运行

本 Skill 脚本统一通过 **uv** 运行（不使用宿主机的原始 Python，避免环境污染）。

- 所有脚本均为纯标准库，无需安装任何第三方包；uv 仅用于隔离 Python 解释器。
- uv 使用全局缓存（`~/.cache/uv`），**不会在每个 skill 目录创建 .venv**；Python 解释器与依赖在所有 skill 间共享，不重复下载。
- 固定路径约定：
  - uv 二进制：`~/.local/bin/uv`
  - 依赖与 Python 缓存：`~/.cache/uv`（全局共享）
  - Python 解释器：`~/.local/share/uv/python/`
  - 脚本：各 skill 的 `scripts/` 目录

首次使用前确保 uv 可用（不可用则自动安装，无需用户操作）：

```bash
python scripts/ensure_uv.py
# 或手动：curl -LsSf https://astral.sh/uv/install.sh | sh
```

统一运行方式：

```bash
uv run scripts/validate_git_assets.py --assets assets/
uv run python -m unittest discover -s scripts/tests   # 跑测试
```

