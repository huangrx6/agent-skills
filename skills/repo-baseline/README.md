# repo-baseline · 工程基线检测与补齐

> 把 pre-commit、格式化、lint、类型检查、Makefile、AGENTS.md 与 CI 收敛成一套可检查的基线。只补缺失项，不覆盖已有配置，写入前先确认。

| 适合 | 产物 | 依赖 |
| --- | --- | --- |
| 新接手的仓库、基线长期漂移的项目、需要会话启动时提醒 | 检测报告 · 基线文件 · 巡检结论 | Python 3.10+ · git；`pre-commit`、`uv`、`pnpm` 可选，`--autoupdate` 需要联网 |

Agent 的执行规则见 [SKILL.md](SKILL.md)，这里只讲怎么手动跑。

## 快速开始

命令从本仓库根目录运行，`--root` 指向目标项目。

```sh
python3 skills/repo-baseline/scripts/detect.py --root /path/to/repo        # 只读，输出 JSON
python3 skills/repo-baseline/scripts/apply.py  --root /path/to/repo        # 计划模式，不写文件
python3 skills/repo-baseline/scripts/apply.py  --root /path/to/repo --write
python3 skills/repo-baseline/scripts/apply.py  --root /path/to/repo --write --install --with-ci
python3 skills/repo-baseline/scripts/hook.py   install --root /path/to/repo
```

`--install` 会装 pre-commit 并写入 git 钩子，隐含 `--autoupdate`。`--with-ci` 同时写
`.github/workflows/ci.yml` 与 `.github/dependabot.yml`，只在 GitHub 仓库且文件缺失时创建。
重复执行是安全的：脚本只补新出现的缺失项。

## 检测结果怎么读

`detect.py` 输出一个 JSON，`state` 决定下一步：

| 字段 | 含义 |
| --- | --- |
| `state` | `empty`（没有依赖清单也没有源码，先问要不要搭建）、`partial`（可初始化）、`complete`（可巡检） |
| `missing` | 基线必需项的缺失清单；非空即 `partial` |
| `blocking` | 会让 `--write` 直接拒绝的冲突（husky、`core.hooksPath`），退出码 3 |
| `conflicts` | 需要先问用户的冲突，如多项目目录、包管理器不是 pnpm、biome 与 prettier 并存 |
| `drift` | 工具已存在但 Makefile 没调用；脚本不改已有 Makefile，只报告 |
| `suggestions` | 可选改进与 Java 的推荐组合，不生成配置 |
| `risks` | 被 git 跟踪的 `.env`、备份、压缩包、私钥和大于 1MB 的文件，最多 50 条 |

`--quick` 只输出一行，供会话启动提醒使用；基线完整时没有任何输出。

## 边界

- 只创建缺失文件，只向 `.gitignore` 追加缺失行；已有文件一律不动，需要改时只给差异。
- 不 commit、不 push、不删除文件、不改业务代码、不改 git 历史，也不自动 `git init`。
- `.pre-commit-config.yaml` 里的 `rev` 是占位符，只能由 `pre-commit autoupdate` 填写；
  autoupdate 失败时不会安装钩子。
- 前端按 pnpm 生成，Python 按 uv 生成。包管理器不是 pnpm 时先确认；没有 `uv.lock` 时
  CI 不传 `--frozen`，没有 `pnpm-lock.yaml` 时不开缓存。
- Java 只给推荐组合（Spotless / Checkstyle 或 P3C / SpotBugs / JaCoCo），不碰构建文件。
- SessionStart 提醒写进 `.claude/settings.local.json`，只有读该文件的 agent 会触发；
  其他 agent 看不到这条提醒。写入前会校验 JSON，解析失败就停止，不覆盖原文件。

## 验证

```sh
python3 -m unittest discover -s tests/repo-baseline -v
```

测试用临时目录和临时 git 仓库，不触碰当前工作区。覆盖状态判定、只增不改、`.gitignore`
追加、阻断冲突与 `--accept-conflicts`、钩子安装与卸载的幂等，以及依赖与目标名解析。
