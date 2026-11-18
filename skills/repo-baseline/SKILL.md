---
name: repo-baseline
description: >-
  Use when 给已有代码仓库建立或补齐工程基线：.editorconfig、.pre-commit-config.yaml、
  Makefile（setup/lint/test/fmt/check）、AGENTS.md 与 CLAUDE.md、ruff 配置、GitHub Actions 与 dependabot；
  也用于巡检 make check、会话启动时提醒基线不完整。中文：初始化工程基线、统一格式化和 lint、
  补 pre-commit、补 Makefile、补 AGENTS.md、补 CI、检查工程规范。
  Do NOT use for: 提交、分支、worktree 与误操作恢复（→ git-dev-workflow）、新项目脚手架与技术选型、
  业务代码实现、PingCode 工作项。
  Not for commits/branches/worktrees, project scaffolding, feature code, or work-item tracking.
compatibility: Requires Python 3.10+ and git; pre-commit / uv / pnpm are optional, --autoupdate needs network.
---

# repo-baseline

规范由脚本检测和执行，不靠人读文档。AI 的职责是解释脚本输出，并在写入前征得确认。

下文 `<S>` 指本 skill 的 scripts 目录绝对路径，即 SKILL.md 所在目录下的 `scripts/`。`DIR` 指项目根目录。

## 脚本

| 命令 | 作用 | 写文件 |
|---|---|---|
| `python3 <S>/detect.py --root DIR` | 输出 JSON：技术栈、已有文件、缺失项、冲突、风险 | 否 |
| `python3 <S>/apply.py --root DIR` | 计划模式，列出将要做的事和需要确认的事项 | 否 |
| `python3 <S>/apply.py --root DIR --write [--with-ci] [--autoupdate] [--install]` | 执行写入 | 是 |
| `python3 <S>/hook.py install\|remove\|status --root DIR` | 管理 SessionStart 提醒 | 是，写 `.claude/settings.local.json` |

脚本只用 Python 标准库，不需要额外安装依赖。

## 第一步：判断状态（只读）

运行 `detect.py`，读取 `state`：

- `empty`：没有 git、代码或依赖清单。只问用户"这里还没有项目，要先搭建吗？"，然后停止，不运行 apply。
- `complete`：基线完整，进入巡检模式。
- `partial`：进入初始化模式。

## 巡检模式（complete）

1. 若 Makefile 有 `check` 目标，运行 `make check`，记录结果。
2. 读取 `drift`（工具已存在，但 Makefile 没有调用）、`risks` 和 `conflicts`。
3. 输出不超过 5 行：结论、失败项前 3 条、漂移与风险、建议。不写文件。
4. 有 `drift` 时，问用户是否要更新 Makefile。脚本不改已有 Makefile，由你手动补充对应行。

## 初始化模式（partial）

### 1. 汇报

用不超过 10 行说明：每个目录的技术栈、缺什么、有什么冲突、有什么风险。文件状态可以用一张小表。

冲突必须先问，不自动选择。其中 `blocking` 列出的冲突（husky 或 core.hooksPath）会让 `--write` 直接拒绝执行（退出码 3）。用户确认处理方式之后，才能加 `--accept-conflicts` 重试。其他冲突包括：CLAUDE.md 有自定义内容、多个项目目录、包管理器不是 pnpm、biome 与 prettier 或 eslint 并存、新旧 eslint 配置并存。

### 2. 计划

运行 `apply.py --root DIR`（计划模式），读取 `actions` 和 `needs_confirm`。

把所有需要确认的事项合并成一次提问，不要一项一问。例如：

> 将新建 .editorconfig、.pre-commit-config.yaml、Makefile、AGENTS.md、CLAUDE.md、backend/ruff.toml，并在 .gitignore 追加 3 行。另外还需要确认：安装 pre-commit 并写入 git 钩子（--install）、新增 CI（--with-ci）、SessionStart 提醒（hook.py install）。要执行哪些？

### 3. 写入

用户确认后，按所选内容运行 `apply.py --write ...`。脚本是幂等的：重复执行只会补新出现的缺失项。

- 只写文件：`--write`
- 联网更新 hook 版本：加 `--autoupdate`。这一步是必需的，模板里的 rev 是占位符，没有 autoupdate 就不能安装钩子。
- 安装 pre-commit 并写入钩子：加 `--install`，会隐含 autoupdate。
- 新增 CI：加 `--with-ci`。同时写 `.github/workflows/ci.yml` 与 `.github/dependabot.yml`，只在缺失时创建，且仅限 GitHub 仓库。

用户确认了 SessionStart 提醒，再运行 `hook.py install --root DIR`。

### 4. 验证

- 运行 `make setup`，再运行 `make check`。
- `make check` 失败时，只汇报数量和前 5 条，不自动修复已有代码。
- `make fmt`（即 `pre-commit run --all-files`）会改动格式，可能涉及大量文件。这一步必须先征得同意，并建议在干净的工作区执行，然后单独提交。

### 5. 收尾

用一两句话说明状态（完整、部分完整或未搭建），列出新增和修改的文件，待办最多 3 项。

## 规则

- 不覆盖已有文件。脚本只创建缺失文件，只向 .gitignore 追加缺失行。需要改已有文件时，只给出差异，由用户决定。
- 不 git commit、不 push、不删除文件、不改业务代码、不改 git 历史，不自动执行 `git init`。
- 不安装前端依赖（eslint、prettier、stylelint）和 Python 开发依赖（ruff、pyright、pytest），除非用户确认。
- 不硬编码 hook 版本号。rev 只由 `pre-commit autoupdate` 填写。
- 发现 .env、dump、压缩包或私钥被 git 跟踪时，只报告。提示轮换密钥，并考虑用 git filter-repo 清理历史。清理历史需要用户明确同意。
- Java 只在报告里给推荐组合，不生成配置，不改构建文件。
- Makefile 已存在时不改写，只报告缺失的 target。
- pre-commit、uv、pnpm 不存在时，说明缺什么和怎么装，不直接装，除非用户已经选择 `--install`。

## 注意

- 前端的 Makefile 和 hook 按 pnpm 生成，CI 的 pnpm 版本取 `package.json` 的 `packageManager`，没有就用 9。包管理器不是 pnpm 时，先确认再继续。
- prettier 未安装时不生成格式检查命令；格式检查会跳过 `pnpm-lock.yaml`、`package-lock.json`、
  `yarn.lock`，与 git 钩子的 exclude 一致。lint 命令取决于 `package.json` 的 `lint` 脚本，
  若脚本调用 eslint 但 eslint 未声明，`make check` 会失败，报告里会标出来。
- `make check` 只检查，不修改文件。只有 `make fmt` 会修改文件。
- SessionStart 提醒写在 `.claude/settings.local.json`，只有读这个文件的 agent（如 Claude Code）会触发；其他 agent 看不到这条提醒，需要人工跑一次 `detect.py`。它的输出会进入对话上下文，收到提示时简短问用户一次，不要展开。
