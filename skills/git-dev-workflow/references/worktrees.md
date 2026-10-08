# Worktree 路径与回收

`worktree.py create BRANCH [--from REF]` 创建新分支和工作树，默认从 HEAD 开始；
目录为 `<仓库父目录>/<仓库名>-<分支slug>`，分支中的 `/` 转为 `-`。
已有分支可按实际占用情况使用 Git 原生 `worktree add`；包装脚本仅提供新分支创建接口。

`--at PATH` 可指定仓库外路径。已有目录、当前仓库内部、Git 元数据目录、其他仓库内部均拒绝。
路径比较解析符号链接；名称碰撞时换目录或检查既有工作树，不覆盖。

```sh
python3 scripts/worktree.py create codex/ui --from main
python3 scripts/worktree.py list
python3 scripts/worktree.py list --stale
python3 scripts/git_guard.py delete-worktree /path/to/worktree
python3 scripts/worktree.py remove /path/to/worktree
python3 scripts/worktree.py prune
```

以上路径相对本 skill；在目标仓库执行时应改为脚本绝对路径或带 `--repo`。

| 目标状态 | 结论与处理 |
| --- | --- |
| 有未提交改动，或状态读不到 | BLOCK；先保存或核实 |
| 忽略项包含凭据、未知本地内容，或忽略项读不到 | BLOCK；忽略不代表可删除，先保存这些文件 |
| 忽略项全部按名称分类为构建产物 | 可继续按提交/分支状态判断；回收会明确说明这些产物一并删除 |
| detached HEAD 且没有其他分支/标签保留提交 | BLOCK；先创建保留引用 |
| 命名分支未并入基线 | WARN；分支仍保留，确认回收在现有授权范围内 |
| 干净且提交已被保留 | SAFE；`remove` 可以回收工作目录 |
| 目录已不存在 | 用 `prune` 清理失效记录；挂载盘暂时离线时不要 prune，应使用 worktree lock |

`git worktree remove` 会删除工作目录里的已跟踪文件和忽略文件，保留命名分支。
包装脚本检查目标工作树的忽略项，阻止删除 `.env` 等凭据和无法归为构建产物的本地内容。
构建目录如 `dist/`、`node_modules/` 仅按路径名称归类，不读取内容证明可再生成；
Git 将整个目录报为忽略项时，目录内部没有逐文件审计，应先确认其中没有手工保留的数据。
它与“删除分支”是两件事；后者另用 `git_guard.py delete-branch` 核验。
包装脚本不使用 `--force`，只自动执行 SAFE；WARN 时按 guard 列出的具体命令处理。

并行任务尽量各用一个工作树；同一工作树需要多写者时明确文件归属，避免相互覆盖。
