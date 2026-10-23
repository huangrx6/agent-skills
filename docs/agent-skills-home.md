# Agent Skills 的本机目录

这个仓库里的 skill 共用**一个家目录**，默认 `~/.agent-skills`；换位置时设
`AGENT_SKILLS_HOME`。配置与运行数据都在这里，不再散落到
`~/.config/<skill>` 与 `~/.cache/<skill>`。

它**不是** `~/.agents`：后者是 Pi / Codex / skills CLI 约定发现 skill 的目录，
只放安装位（软链），不放本项目的配置和缓存。

```text
~/.agent-skills/
  config/                    # 小而需要人编辑的配置
    skill-name-blocklist.txt
    obsidian-vault-path
    pingcode/{credentials,token,context,cache}.json
    deck-authoring/font-index.json
    excalidraw-library-path
  data/                      # 可重建的运行数据
    learning-scout/venv/
    deck-authoring/fonts/
    diagram-authoring/libraries/
```

安装位仍在各 agent 自己的目录（默认 `~/.agents/skills`，Claude 是
`~/.claude/skills`，项目级是 `.agents/skills`），只放指向仓库的软链或副本。
输出目录不在这里：报告、构建产物仍写到 `~/Downloads/<skill>/`，方便直接打开。

## 路径解析

| 变量 | 默认 | 用途 |
| --- | --- | --- |
| `AGENT_SKILLS_HOME` | `~/.agent-skills` | 项目家目录根；`config/`、`data/` 都在其下 |
| `AGENT_SKILLS_CONFIG_DIR` | `$AGENT_SKILLS_HOME/config` | 共享配置根；单独指定时优先 |
| `AGENT_SKILLS_DATA_DIR` | `$AGENT_SKILLS_HOME/data` | 共享运行数据根 |

各 skill 仍保留自己的覆盖变量，例如 `PINGCODE_CONFIG_DIR`、`DECK_FONT_DIR`、
`DECK_FONT_INDEX`、`LEARNING_SCOUT_VENV`；显式值优先于上面的默认值。

## 旧位置

迁移脚本会把旧目录搬进来；脚本本身也保留**只读回退**，未迁移的机器不会立刻坏：

| 旧位置 | 新位置 |
| --- | --- |
| `~/.config/agent-skills/` | `~/.agent-skills/config/` |
| `~/.config/deck-authoring/fonts/` | `~/.agent-skills/data/deck-authoring/fonts/` |
| `~/.config/deck-authoring/font-index.json` | `~/.agent-skills/data/deck-authoring/font-index.json` |
| `~/.cache/diagram-authoring/` | `~/.agent-skills/data/diagram-authoring/` |
| `~/.cache/agent-skills/` | `~/.agent-skills/data/deck-authoring/legacy-cache/` |
| `<skill>/.venv/` | `~/.agent-skills/data/<skill>/venv/` |
| `~/.config/excalidraw-library-path` | `~/.agent-skills/config/excalidraw-library-path` |

迁移命令：

```sh
python3 tools/migrate_skill_home.py            # 预演
python3 tools/migrate_skill_home.py --apply    # 执行
```

脚本不覆盖已有文件；冲突会列出来，由人决定。
