# obsidian-personal-knowledge-base

维护 Obsidian 笔记的内容、归位和导航：Projects/Areas 保持行动导向，Resources 侧重可复用知识。
记录刚完成的开发或发布事实请用 `obsidian-work-log-release-recorder`；普通笔记修订与周报仍用本 skill。

## 安装与配置

安装方式见仓库 [README](../../README.md)。脚本只依赖 Python 标准库。
下列命令均从仓库根执行：

```sh
export OBSIDIAN_VAULT_PATH="/path/to/your/vault"
python3 skills/obsidian-personal-knowledge-base/scripts/vault_path.py --explain
```

也可把 vault 路径写成单行文件 `~/.config/agent-skills/obsidian-vault-path`；先创建配置目录。
`AGENT_SKILLS_CONFIG_DIR` 可覆盖配置目录，旧文件 `~/.config/obsidian-vault-path` 仅作兼容回退。
显式路径优先于环境变量，环境变量优先于配置文件；没有硬编码 vault。

## 使用与检查

示例：“把 Inbox 的 Docker 笔记归位并更新 MOC”“审阅这篇 Resources 笔记”“整理本周周报”。
操作前会探查目标区域，沿用当前索引和模板，不依赖预存的项目清单。

```sh
python3 skills/obsidian-personal-knowledge-base/scripts/check_links.py --ignore-template
python3 skills/obsidian-personal-knowledge-base/scripts/check_paths.py
python3 -m unittest discover -s tests/obsidian-personal-knowledge-base -v
```

`--vault PATH` 可让两个检查器扫描临时目录或指定 vault；它们不会修改文件。
`--json` 输出机器可读结果，`--quiet` 只输出失败数量。退出码：`0` 无失败、`1` 发现问题、`2` 输入不可用。

检查器不是 Obsidian 渲染器：链接检查只检查 wikilink/嵌入的目标文件，不验证标题锚点、块 ID 或 Markdown 链接；
路径检查只提取 `.obsidian/` 配置中的常见 POSIX 绝对路径，并按扩展名启发式区分文件与目录。
没有扩展名的可执行文件、带点的目录及插件自己的路径展开规则需要人工判断。

规则入口在 [SKILL.md](SKILL.md)，脚本边界详见 [结构检查](references/structural-checks.md)。
`evals/evals.json` 是人工行为评审用例，不能替代脚本测试或宣称已经自动评测通过。
