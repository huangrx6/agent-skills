# Obsidian 学习 Wiki

以学习为主：把资料融入已有知识，根据笔记提问和复习，随新证据更新结论。
保留原有 PARA 目录，同时区分来源、知识和学习入口；不要求另建 raw/wiki 顶层目录。

这个 skill 可以单独安装运行，不依赖工作记录 skill、PingCode、数据库或插件。
工作笔记可作为学习来源，关联只使用普通文件链接；不会触发任务同步或自动生成工作记录。

## 怎么用

- “把这篇文章融入我的缓存专题，保留原来的个人理解，指出它改变了什么。”
- “根据已有笔记解释缓存一致性，标出还有哪些地方没证据。”
- “基于这个主题考我两个应用问题，先别给答案。”
- “这份新版本说明推翻了旧笔记的一部分，核对并更新。”
- “检查这些笔记的矛盾和过期结论，先告诉我问题。”
- “把这篇笔记改名并更新受影响的链接。”
- “这篇像模板拼起来的，围绕真正的问题重组，保留细节和我的解释。”
- “只更新这份 v2 材料影响的部分；v1 项目仍在使用的操作保留。”

资料接收、查询和检查的具体行为见 [SKILL.md](SKILL.md)。查询和复习默认不写入，
“保存”“融入”“更新”才在要求范围内修改。需求、缺陷、任务分工不属于本 skill 的业务职责。
整理项目说明、会议材料或润色已有周报时，按 [工作材料编辑](references/work-note-editing.md) 处理：
可以保留材料中已有的分工与进展，区分事实、建议和决定；仅编辑文档不会自动变更工作项主档。

## 配置

安装方式见仓库 [README](../../README.md)。脚本只依赖 Python 标准库。
下面命令从仓库根运行；安装后可换成对应 skill 的完整脚本路径。

```sh
export OBSIDIAN_VAULT_PATH="/path/to/your/vault"
python3 skills/obsidian-wiki/scripts/vault_path.py --explain
```

也可把路径写为 `~/.config/agent-skills/obsidian-vault-path` 的一行文本；
`AGENT_SKILLS_CONFIG_DIR` 可覆盖配置目录，旧文件 `~/.config/obsidian-vault-path` 仅兼容回退。
显式路径优先于环境变量，环境变量优先于配置文件；可以单独指定本次库，不要求与其他能力共用库。

## 从旧方式迁移

[渐进采用](references/adoption.md)说明如何从一个真实主题开始，不搬空现有目录。
[知识模型](references/knowledge-model.md)定义来源、结论、个人理解与可选属性。
已知归属直接更新主笔记；资料先与已有认识比较，再决定是否需要新页面。

文章没有统一章节骨架。[学习笔记](references/resource-notes.md)指导如何从问题选择讲述顺序，
[写作规范](references/writing-conventions.md)指导段落、表格、代码、提示块和图的搭配。
沿用的是文件、属性和链接约定，不是旧模板里所有章节。深入解释与简短笔记都可以成立。

[知识更新](references/knowledge-updates.md)处理“新资料怎样改变旧笔记”：对应到具体结论，
区分补充、修正、版本并存与未决分歧，修订相关示例和图，并说明实际核验范围。
收到新资料、准备应用或用户要求复核时维护；不会自动持续联网、定时改库或要求新建版本数据库。

## 验证与限制

```sh
python3 skills/obsidian-wiki/scripts/check_links.py --ignore-template
python3 skills/obsidian-wiki/scripts/check_paths.py
python3 -m unittest discover -s tests/obsidian-wiki -v
```

两个检查器支持 `--vault PATH`、`--json`、`--quiet`，不修改文件。
退出码为 `0` 无范围内失败、`1` 发现问题、`2` 输入不可用。
链接检查只验证双链/嵌入的文件目标，不覆盖普通 Markdown 链接、标题/块锚点或同名语义歧义。
配置检查只提取常见 POSIX 绝对路径，并启发式区分文件和目录，边界见 [结构检查](references/structural-checks.md)。
这些脚本不证明结论正确；证据、冲突和学习效果需按实际材料审阅。
`evals/evals.json` 是行为场景，不代表已自动执行全部场景或完成触发基准测试。
