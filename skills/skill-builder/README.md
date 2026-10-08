# skill-builder

用于创建 skill、评审触发描述与范围；包含仓库维护需要的结构、引用和名称泄露检查器。
普通正文或脚本修改直接进行，不需要重新论证“要不要建 skill”。

## 使用

- “把这个可复用流程整理成 skill。”
- “这个 skill 经常误触发，帮我检查 description。”
- “评审这两个 skill 的边界，看看是否需要合并。”

先明确输入、产物与相邻能力，再写最小流程；没有历史使用统计也可以建立待验证的初版。
详细操作在 [SKILL.md](SKILL.md)，目录约定在 [anatomy-and-scope.md](references/anatomy-and-scope.md)。

## 安装与依赖

在仓库根目录运行 `python3 tools/install_skills.py`，默认安装为软链；
`python3 tools/install_skills.py --check` 检查安装状态。单独分发时保留 scripts 与 references。
检查器使用 Python 标准库，若安装了 PyYAML 则使用它解析 frontmatter。

## 检查命令

以下命令均从仓库根目录执行：

```sh
python3 skills/skill-builder/scripts/preflight.py
python3 skills/skill-builder/scripts/preflight.py --json
python3 skills/skill-builder/scripts/validate_skill.py skills/skill-builder
python3 skills/skill-builder/scripts/check_pointers.py --root . skills
python3 -m unittest discover -s tests/skill-builder -v
```

| 工具 | 检查范围 | 限制 |
| --- | --- | --- |
| `validate_skill.py` | frontmatter、名称、入口描述、正文预算、eval 格式、不可分发的测试引用 | 不验证文字指令是否正确 |
| `check_leakage.py` | 工作区或指定历史中的自定义敏感名称 | 未配置词表时跳过，不是完整秘密扫描 |
| `check_pointers.py` | 文档中可识别的本地引用是否存在 | 内容是否接住条款仍需审阅 |
| `preflight.py` | 上述三项检查、正文与测试文件快照、安装状态 | 不运行测试；未提及的脚本仅提示人工核对 |

泄露词表按 `--blocklist`、`$SKILL_NAME_BLOCKLIST`、用户配置目录解析。
词表不要入库；`--show-blocklist` 会输出词条，不要把它的结果用于公开报告。

仓库 hook 的回归测试默认只提示失败，`AGENT_SKILLS_GATE=1` 可启用阻塞模式。
具体行为和安装方法见根 README；不要把 preflight 与完整测试混为一谈。

## 维护

- [slimming.md](references/slimming.md)：清理重复、过时和没有消费者的内容。
- [reporting.md](references/reporting.md)：区分实测、跳过与未验证。
- [skill-readme-template.md](references/skill-readme-template.md)：使用文档的参考结构。
- `evals/evals.json`：人工或独立执行器可使用的行为样例，不会由 unittest 自动执行。

测试覆盖检查器边界和报告准确性；行为样例用来评审流程与触发，二者不能替代彼此。
