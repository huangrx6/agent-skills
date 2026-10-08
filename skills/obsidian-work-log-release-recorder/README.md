# obsidian-work-log-release-recorder

应用户要求，把已完成开发、配置和发布工作写入 Obsidian，保留命令、状态、证据和恢复信息。
只有涉及发布的工作才维护周发版记录。普通笔记整理、周计划和周报交给 `obsidian-personal-knowledge-base`（PKB）。

## 安装与使用

与 PKB 一起安装，安装方式见仓库 [README](../../README.md)。两者共享 vault 路径配置，
详见 [PKB 配置说明](../obsidian-personal-knowledge-base/README.md)。脚本只依赖 Python 标准库。

示例：“把刚才跑通的回归测试记录到项目页”“这次发布记一下”“补本周发版文档”。
仅要求记录时不会执行笔记里的命令或自动发布。

以下从仓库根执行：

```sh
python3 skills/obsidian-personal-knowledge-base/scripts/vault_path.py --explain
python3 skills/obsidian-work-log-release-recorder/scripts/check_release_note.py "<笔记路径>" --vault "<vault 路径>"
python3 skills/obsidian-personal-knowledge-base/scripts/check_links.py --ignore-template
python3 -m unittest discover -s tests/obsidian-work-log-release-recorder -v
```

## 校验范围

`check_release_note.py` 针对本 skill 的默认周发版格式；`--dir PATH` 检查目录中的发版笔记。
单篇模式也检查同目录的重复周。退出码：`0` 无失败或只有提示、`1` 格式/引用/重复问题、`2` 输入或模板不可用。
显式 `--vault` 不可用时失败；未配置 vault 时跳过引用检查并明确提示。

校验器从 [模板](references/release-note-template.md) 读取字段和章节要求，不检查正文事实是否真实、
每个章节是否已完整填写、命令是否可执行或回滚是否有效。引用检查只认其他笔记中的 wikilink，
不是证明该链接来自 MOC；普通文字提及不算导航。明显凭据赋值仅作提示，输出隐藏值，也不代表完整密钥扫描。

已有自定义格式优先保留；默认格式检查不适用的部分人工审阅，不能为了返回 `0` 改坏本地约定。
链接目标是否失效由 PKB 检查器负责。`evals/evals.json` 是人工行为评审用例，尚无自动评分器。
