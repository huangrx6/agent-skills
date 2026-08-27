# Git Workflow

> Sub-topic of [`engineering-architecture`](../SKILL.md). Reads as a cheat sheet for daily commits; structured so an Agent can route, classify, and act on Git operations without re-reading every reference.

## What this is

A unified Git workflow spec for engineering work — branch policy, commit format, safety gates, recovery, and review criteria. Authoritative source is the files in `references/git/` and `assets/git/`; this README is a pointer.

## How to invoke

Tell the Agent:

```text
使用 $engineering-architecture/git 帮我 <做什么>
```

Examples:

| You say | Agent does |
| --- | --- |
| 帮我提交这次改动 | inspect → propose plan → wait for explicit `yes` → `git add` filtered files → `git commit -m` (no push) |
| 我要 rebase 主干到我的 feature 分支 | check `safety-gates.md` → require branch ownership + clean status → `git rebase main` (no push) |
| 我刚误操作 reset --hard 了 | use `references/git/undo-recovery.md` and `git reflog` |
| 评审我这次的 commit 历史 | load `assets/git/git-review-checklist.csv` and check 15 items |

The Agent must always:

1. Run `git status --short` and `git diff --stat` before any write.
2. Print the commit plan (file list + full commit message) and wait for explicit confirmation.
3. Never push without a separate confirmation.
4. Never `rebase` / `reset --hard` / `push --force` on shared branches.

## Core principles

These are non-negotiable. They are the same in `references/git/safety-gates.md`, stated here so you do not need to re-read that file for daily work.

- Every commit does exactly one thing. Use `git add -p` to split a file.
- Commit messages follow Conventional Commits; `!` or `BREAKING CHANGE` for breaking changes.
- Worktree isolates parallel tasks; never mix unrelated changes in one branch.
- Shared branches (`main`/`master`/`develop`/`release/*`) never rebase, force-push, or hard-reset.
- Force-push only on personal branches, only with `--force-with-lease`.
- A recovery point exists before any destructive op (`git rev-parse HEAD > /tmp/recovery-point`).
- `.env`, secrets, private keys, and dumps are never staged without explicit approval.

## Quick reference

### Commit message

```text
<type>[scope][!]: <imperative summary]

[optional body — why, not what]

[optional footer — BREAKING CHANGE, refs, closes]
```

Full type table: [`assets/git/commit-type-catalog.csv`](../assets/git/commit-type-catalog.csv). Default body and templates: [`assets/git/commit-message.template.md`](../assets/git/commit-message.template.md).

### Safety gate for any Git operation

| Level | Commands | Required step |
| --- | --- | --- |
| Read-only | `status`, `diff`, `log`, `show`, `blame`, `reflog`, `fetch` | None — execute directly |
| Need confirm | `add`, `commit`, `branch`, `checkout`/`switch`, `stash`, `tag`, `restore` | Dry-run plan, explicit yes |
| High-risk | `merge`, `rebase`, `cherry-pick`, `reset --soft`, `push` | Explicit confirm + verify status clean |
| Dangerous | `reset --hard`, `push --force`, `filter-branch`, `branch -D`, `clean -fdx` | Record recovery point; strongly avoid |

Full matrix: [`assets/git/git-command-safety-matrix.csv`](../assets/git/git-command-safety-matrix.csv).

### Merge strategy

| Goal | Strategy | Command |
| --- | --- | --- |
| Linear history, personal branch | fast-forward | `git merge <branch>` (default when ff-able) |
| Preserve feature branch shape | no-fast-forward | `git merge --no-ff <branch>` |
| Squash WIP into one commit | squash | `git merge --squash <branch>` |
| Linear history after sync | rebase + ff merge | `git rebase <base>` then `git merge <branch>` |
| Edit commits before merge | interactive rebase | `git rebase -i <base>` |

Full matrix: [`assets/git/merge-strategy-matrix.csv`](../assets/git/merge-strategy-matrix.csv).

### Recovery

| Situation | Safe move | Avoid |
| --- | --- | --- |
| Wrong commit message, not pushed | `git commit --amend` | anything irreversible |
| Wrong commit, not pushed | `git reset HEAD~1` (mixed) | `reset --hard` |
| Wrong commit, already pushed | `git revert <commit>` | `reset` (rewrites history) |
| Lost work from `--hard` | `git reflog`, find HEAD@{n}, `git reset --hard <hash>` | panicking without reflog |
| Need to undo a revert | `git revert <revert-commit-hash>` | chain of confusing reverts |

Full recovery: [`references/git/undo-recovery.md`](../references/git/undo-recovery.md).

## Reference index

| File | When to load |
| --- | --- |
| [`references/git/git-fundamentals.md`](../references/git/git-fundamentals.md) | Need the 4-area mental model or object model |
| [`references/git/staging-commit.md`](../references/git/staging-commit.md) | Need `git add` / `git commit` semantics and edge cases |
| [`references/git/commit-message.md`](../references/git/commit-message.md) | Writing or reviewing a commit message |
| [`references/git/branching-merging.md`](../references/git/branching-merging.md) | Branch strategy, merge strategies, worktree |
| [`references/git/safety-gates.md`](../references/git/safety-gates.md) | Before any non-read-only Git op |
| [`references/git/undo-recovery.md`](../references/git/undo-recovery.md) | Recovering from a mistake |
| [`references/git/standards-sources.md`](../references/git/standards-sources.md) | Why these rules (Pro Git, Conventional Commits, SemVer, GitHub Flow, Trunk-Based, BFG, gitleaks) |

## Asset index

| File | Purpose |
| | --- |
| [`assets/git/commit-message.template.md`](../assets/git/commit-message.template.md) | Commit message skeleton with 4 worked examples + checklist |
| [`assets/git/commit-type-catalog.csv`](../assets/git/commit-type-catalog.csv) | 11 conventional types with SemVer impact and examples |
| [`assets/git/git-command-safety-matrix.csv`](../assets/git/git-command-safety-matrix.csv) | 35 Git commands classified by safety level |
| [`assets/git/merge-strategy-matrix.csv`](../assets/git/merge-strategy-matrix.csv) | 8 merge strategies with when/why/preserves-history |
| [`assets/git/git-review-checklist.csv`](../assets/git/git-review-checklist.csv) | 15 review checks (BLOCKER / MAJOR / MINOR) |

## Validation

```bash
uv run scripts/git/validate_git_assets.py --assets assets/git/
uv run python -m unittest discover -s scripts/git/tests
```

Both must pass before committing this spec's own changes.

## Worked example

See [`examples/git/git-workflow.example.md`](../examples/git/git-workflow.example.md) for an end-to-end scenario — branch, commit, rebase, merge, revert — with the exact commands the Agent would issue at each step.
