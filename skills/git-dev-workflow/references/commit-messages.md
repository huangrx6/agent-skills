# 提交信息检查

优先遵循目标仓库的明确约定。需要 Conventional Commits 时，使用
[规范 v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) 与 `scripts/commit_style.py`。

```text
fix(parser): 修正空输入处理

解释原因与影响。

Refs: #123
```

检查器检查前缀形状、非空 scope/描述、正文分隔空行及部分 footer 规则。
破坏性变更可用紧贴冒号的 `!`，或全大写 `BREAKING CHANGE:` / `BREAKING-CHANGE:`。
它不能判断 feat/fix 的语义是否准确、是否真的有兼容性破坏，也不是完整语法解析器；
footer 仅扫描最后一个连续段落，多段 footer 仍需人工核对。

以下只提示，不作为规范错误：不在内置 type 表、type 大写、scope 含空格、主题超过 72 字符、句末标点。
规范允许其他 type 与大小写，并未限定描述或 scope 的语言。内置常见 type 为
feat/fix/docs/style/refactor/perf/test/build/ci/chore/revert，目标仓库可采用自己的约定。

合并提交、Git 默认 revert 信息及 autosquash 标记由本检查器跳过；这是工具兼容策略，
并非规范声明这些提交“不适用”。

```sh
python3 scripts/commit_style.py --check 'fix(api): 修正分页'
python3 scripts/commit_style.py --check-file /path/to/message.txt
python3 scripts/commit_style.py --template
```

退出码 1 表示空信息或发现规范问题；0 表示本检查未发现阻断项。`--json` 区分 `spec` 与 `project`。
`--check-file` 会剥除以 `#` 开头的行，适合默认 COMMIT_EDITMSG；自定义 commentChar 或正文需要保留
`#` 时，通过 `--check` 或标准输入提供已清理文本。
