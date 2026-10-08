# git-dev-workflow

本地 Git 状态、破坏性动作预检、提交信息检查与 worktree 管理。Agent 的选择规则见
[SKILL.md](SKILL.md)，详细操作按其中的参考链接读取。

依赖：Python 3.10+ 与 Git。下面命令从本仓库根目录运行；检查别的仓库时加 `--repo`。

```sh
python3 skills/git-dev-workflow/scripts/git_state.py --repo /path/to/repo
python3 skills/git-dev-workflow/scripts/git_guard.py --list
python3 skills/git-dev-workflow/scripts/git_guard.py delete-branch feature --repo /path/to/repo
python3 skills/git-dev-workflow/scripts/commit_style.py --check 'fix(api): 修正分页'
python3 skills/git-dev-workflow/scripts/worktree.py list --repo /path/to/repo
```

`git_guard.py` 只输出证据和建议命令，不执行。SAFE/WARN/BLOCK 的退出码为 0/3/4。
`worktree.py remove` 只自动执行 SAFE；WARN 时会给出预检结果及可供授权后使用的命令。
仓库不需要安装钩子才能使用本 skill；若已有钩子，`bypass-hooks` 会报告它们。

可选审计：动手前 `git_report.py --capture`，完成后 `git_report.py`。
默认快照放在 Git 公共元数据目录，多个 worktree 共用；并行审计请各自指定 `--file`。
没有事前快照时，可以报告当前状态和已知提交，但不能倒造“操作前”的证据。

验证从本仓库根目录运行：

```sh
python3 -m unittest discover -s tests/git-dev-workflow -v
```

测试使用临时 Git 仓库，不修改当前工作区。覆盖状态、guard、worktree、报告、分组和提交语法。
文件分类仍是命名启发式，远端信息仍取决于本地跟踪引用；bare、shallow 及旧版 Git 未作全面兼容验证。
