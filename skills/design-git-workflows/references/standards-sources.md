# 权威来源

## 官方文档

- Git 官方文档
  https://git-scm.com/doc

- Git Reference（命令速查）
  https://git-scm.com/docs

- Pro Git Book（开源，全面）
  https://git-scm.com/book/zh/v2

- Git Worktree 教程
  https://git-scm.com/docs/git-worktree

- Atlassian Git Tutorials（图解清晰）
  https://www.atlassian.com/git/tutorials

## 提交信息规范

- Conventional Commits 1.0.0
  https://www.conventionalcommits.org/

- commitlint（工具校验）
  https://commitlint.js.org/

- Angular Commit Convention（Conventional Commits 的来源）
  https://github.com/angular/angular/blob/main/CONTRIBUTING.md#commit

## 版本管理

- Semantic Versioning 2.0.0
  https://semver.org/

- Git Tagging
  https://git-scm.com/book/en/v2/Git-Basics-Tagging

- Keep a Changelog
  https://keepachangelog.com/

## 合并与分支模型

- Git Flow（经典分支模型）
  https://nvie.com/posts/a-successful-git-branching-model/

- GitHub Flow（简化模型）
  https://docs.github.com/en/get-started/quickstart/github-flow

- Trunk-Based Development
  https://trunkbaseddevelopment.com/

- Git merge strategies（官方）
  https://git-scm.com/docs/git-merge

## 安全

- BFG Repo-Cleaner（清理历史）
  https://rtyley.github.io/bfg-repo-cleaner/

- git-filter-repo（替代 filter-branch）
  https://github.com/newren/git-filter-repo

- GitHub Secret Scanning
  https://docs.github.com/code-security/secret-scanning

- gitleaks（密钥扫描）
  https://github.com/gitleaks/gitleaks

## 适用主题映射

| 主题 | 权威来源 |
| --- | --- |
| 基础概念/对象模型 | Pro Git Book |
| 命令速查 | Git Reference |
| worktree | Git Worktree 教程 |
| 合并/分支图解 | Atlassian Tutorials |
| 提交信息 | Conventional Commits |
| 版本号 | Semantic Versioning |
| 分支模型 | Git Flow / Trunk-Based |
| 历史清理 | BFG / git-filter-repo |
| 密钥泄露 | GitHub Secret Scanning / gitleaks |

## 使用原则

- Git 命令行为以官方 Reference 和 Pro Git Book 为准；社区教程仅作图解参考。
- Conventional Commits 是规范本体，commitlint 是校验工具，项目可按需收紧规则。
- 合并策略（ff/no-ff/squash）是团队决策，没有唯一正确答案；根据项目分支模型选择。
- 危险操作（filter-branch）已被官方标记为不推荐，优先用 git-filter-repo 或 BFG。
- 区分"规范"（Conventional Commits/SemVer）vs"工具"（commitlint/BFG）vs"方法论"（Git Flow）。
