# skill-builder

> 仓库维护工具：编写和评审 skill，并检查结构、引用与名称泄露。**不进入 `skills/`，不会被安装到 agent。**

| 适合 | 产物 | 依赖 |
| --- | --- | --- |
| 写新 skill · 评审触发边界 · 检查仓库一致性 | SKILL.md · README · 检查报告 | Python 3.10+；解析 frontmatter 时可选 PyYAML |

它原来放在 `skills/` 里，但同时承担了“作者指南”和“仓库检查器”两种角色。现在移到 `tools/`：
`skills/` 只留可分发的技能；这里的脚本服务 pre-commit、测试和维护，不再占用 agent 的安装位。

## 使用

写作方法、触发描述、范围与报告规范见 [GUIDE.md](GUIDE.md)；
目录约定见 [anatomy-and-scope.md](references/anatomy-and-scope.md)。

以下命令均从仓库根目录执行：

```sh
python3 tools/skill-builder/scripts/preflight.py
python3 tools/skill-builder/scripts/preflight.py --json
python3 tools/skill-builder/scripts/validate_skill.py skills/deck-authoring
python3 tools/skill-builder/scripts/check_pointers.py --root . skills tools
python3 tools/skill-builder/scripts/check_leakage.py skills tools
```

## 检查范围

| 工具 | 检查范围 | 限制 |
| --- | --- | --- |
| `validate_skill.py` | frontmatter、名称、入口描述、正文预算、eval 格式、不可分发的测试引用 | 不验证文字指令是否正确 |
| `check_leakage.py` | 工作区或指定历史中的自定义敏感名称 | 未配置词表时跳过，不是完整秘密扫描 |
| `check_pointers.py` | 文档中可识别的本地引用是否存在 | 内容是否接住条款仍需审阅 |
| `preflight.py` | 上述三项检查、正文与测试文件快照、安装状态 | 不运行测试；未提及的脚本仅提示人工核对 |

泄露词表按 `--blocklist`、`$SKILL_NAME_BLOCKLIST`、`$AGENT_SKILLS_HOME/config/skill-name-blocklist.txt` 解析。
词表不要入库；`--show-blocklist` 会输出词条，不要把它的结果用于公开报告。

## 边界

- 它不再是可安装 skill；根目录的 `tools/install_skills.py` 只遍历 `skills/`。
- 仓库 hook 的回归测试默认只提示失败，`AGENT_SKILLS_GATE=1` 可启用阻塞模式。
- 检查通过只代表结构与引用成立，不代表文字质量、触发准确度或产物可用。

## 维护

- [GUIDE.md](GUIDE.md)：写 skill 的完整流程与判断标准。
- [slimming.md](references/slimming.md)：清理重复、过时和没有消费者的内容。
- [reporting.md](references/reporting.md)：区分实测、跳过与未验证。
- [skill-readme-template.md](references/skill-readme-template.md)：使用文档的参考结构。
- `evals/evals.json`：人工或独立执行器可使用的行为样例，不会由 unittest 自动执行。
