#!/usr/bin/env python3
"""按 **Conventional Commits v1.0.0** 校验一条提交信息。

## 为什么按规范而不是按历史

规范是**写在纸上的**：16 条规则、有条目号、有 RFC 2119 的措辞强度（MUST / MAY / SHOULD）。
历史习惯不是 —— 它里面混着"当时随手写的"和"当时被工具逼的"，照它学等于把当年的将就
一起继承下来。所以这个脚本的判据只有一个来源：
<https://www.conventionalcommits.org/en/v1.0.0/>，每条结论都引用条目号。

## 两类结论必须分开说

- **规范违规**（`source: spec`）：真的违反了那 16 条之一。比如用了全角冒号、
  冒号后面没空格、`breaking change` 没大写。
- **本项目约定**（`source: project`）：规范**允许**、但这个仓库另外定了规矩。比如
  type 不在封闭列表里（规则 14 明确说其它 type 可以用，所以这是"我们的约定"而不是"违规"），
  或者 topic 用了大写（规则 15 说实现者不得区分大小写，所以这只能是建议）。

混在一起说会让人以为规范禁止了某些它其实允许的事 —— 而这类"其实允许"的规则
恰好是最容易被误传的（"必须用英文"就是典型：规范从头到尾没有限制语言）。

## 退出码

- `0` 符合规范（或者这条提交属于"不适用"类：合并 / autosquash / git 默认的回滚信息）
- `1` 有违规

## 用法

    python3 scripts/commit_style.py --check "fix(api): 修正分页越界"
    python3 scripts/commit_style.py --check-file .git/COMMIT_EDITMSG
    python3 scripts/commit_style.py --template
    printf 'feat: x\\n' | python3 scripts/commit_style.py --check -
"""

from __future__ import annotations

import argparse
import json
import re
import sys

SPEC_URL = "https://www.conventionalcommits.org/en/v1.0.0/"

# 本项目的封闭 type 表。规则 14 允许其它 type，所以**不在表里是"我们的约定"**，
# 不是规范违规 —— 报告里会分开标注。
TYPES = {
    "feat": "新功能（对应 SemVer 的 MINOR）",
    "fix": "修 bug（对应 SemVer 的 PATCH）",
    "docs": "只改文档",
    "style": "不影响语义的格式改动（空格、分号、格式化）",
    "refactor": "既不加功能也不修 bug 的改写",
    "perf": "性能",
    "test": "加或改测试",
    "build": "构建系统、外部依赖（依赖清单、镜像、打包脚本）",
    "ci": "CI 配置与脚本",
    "chore": "其它杂项（不碰 src / test 的那种）",
    "revert": "回滚某个提交（规范 FAQ 推荐用它 + Refs footer）",
}

# "不适用"类：这些不是人写的常规提交，规范也没打算管它们。
NOT_APPLICABLE = (
    (re.compile(r"^Merge (branch|remote-tracking branch|pull request|tag) "), "合并提交"),
    (re.compile(r'^Revert "'), "git 默认的回滚信息"),
    (re.compile(r"^(fixup|squash|amend)! "), "autosquash 标记"),
)

SUBJECT = re.compile(
    # type 允许带连字符：仓库里真有 `e2e-ops:` 这种写法。不允许的话解析会在
    # `e2e` 处停下，报出来的错变成“type 后面没有冒号” —— 一个误导性的诊断。
    r"^(?P<type>[A-Za-z][A-Za-z0-9-]*)"
    r"(?:\((?P<scope>[^()]*)\))?"
    r"(?P<bang>!)?"
    r"(?P<colon>:)?"
    r"(?P<space> )?"
    r"(?P<description>.*)$"
)

FOOTER = re.compile(r"^(?P<token>[^:\s][^:]*?)(?P<sep>: | #)(?P<value>.*)$")
BREAKING_OK = ("BREAKING CHANGE", "BREAKING-CHANGE")
TRAILING_PERIOD_ADVICE = "主题行末尾通常不加句号"
SUBJECT_LENGTH_ADVICE = 72


class Finding:
    def __init__(self, source: str, rule: str, where: str, detail: str, fix: str = ""):
        self.source = source      # "spec" | "project"
        self.rule = rule
        self.where = where
        self.detail = detail
        self.fix = fix

    def json(self) -> dict:
        return {"source": self.source, "rule": self.rule, "where": self.where,
                "detail": self.detail, "fix": self.fix}

    def line(self) -> str:
        label = f"规范 {self.rule}" if self.source == "spec" else f"本项目约定：{self.rule}"
        text = f"[{label}] {self.where} —— {self.detail}"
        return text + (f"\n      建议：{self.fix}" if self.fix else "")

def classify(message: str) -> tuple[str, str]:
    """返回 (类别, 说明)。类别是 conventional / not-applicable / empty。"""
    stripped = message.strip()
    if not stripped:
        return "empty", "空信息"
    first = stripped.splitlines()[0]
    for pattern, label in NOT_APPLICABLE:
        if pattern.match(first):
            return "not-applicable", label
    return "conventional", ""


def check(message: str) -> tuple[str, list[Finding]]:
    """校验一条完整提交信息。返回 (类别, 问题列表)。"""
    kind, _ = classify(message)
    if kind != "conventional":
        return kind, []

    lines = message.rstrip("\n").splitlines()
    subject = lines[0]
    findings: list[Finding] = []
    match = SUBJECT.match(subject)

    # ── 规则 1：type + 可选 scope + 可选 ! + **必需的冒号和空格** ──
    full_width = "：" in subject
    if not match or not match.group("type"):
        findings.append(Finding("spec", "规则 1", "主题行",
                                "看不出一行以 type 开头",
                                "写成 <type>(<scope>)!: <描述>，冒号是 ASCII 的 `:`"))
        return kind, findings

    # 规则 13：`!` 必须紧贴在冒号前（`feat(api)!:` ✓；`feat!(api):` ✗）。
    #
    # 这个判断必须在规则 1 之前 —— `!` 位置错时正则根本找不到那个冒号，
    # 于是会报成“type 后面没有冒号”：**病因说错了**，而读的人会去改冒号。
    # （同一个毛病在 `e2e-ops:` 上犯过一次：正则不认连字符，也报成没冒号。）
    prefix = subject.split(":", 1)[0]
    misplaced_bang = "!" in prefix and not prefix.endswith("!")

    if misplaced_bang:
        findings.append(Finding("spec", "规则 13", "主题行",
                                f"`!` 的位置不对：{prefix!r}",
                                "写 `feat(api)!: <描述>` —— `!` 要紧贴在冒号前面"))
    elif full_width and not match.group("colon"):
        findings.append(Finding("spec", "规则 1", "主题行",
                                "用了全角冒号「：」",
                                "换成 ASCII 冒号 `:` —— 规范 1 要求的是 terminal colon"))
    elif not match.group("colon"):
        findings.append(Finding("spec", "规则 1", "主题行",
                                "type 后面没有冒号",
                                "写成 `<type>: <描述>`"))
    elif not match.group("space"):
        findings.append(Finding("spec", "规则 1", "主题行",
                                "冒号后面没有空格",
                                "冒号后面**必须**紧跟一个空格，再写描述"))

    # ── 规则 5：描述必须紧跟冒号+空格，而且是"短的总结" ──
    description = (match.group("description") or "").strip()
    if not description:
        findings.append(Finding("spec", "规则 5", "主题行", "描述是空的",
                                "描述要写清这次改了什么"))

    # ── 规则 4：scope 是被括号包住的"名词" ──
    scope = match.group("scope")
    if scope is not None:
        if not scope.strip():
            findings.append(Finding("spec", "规则 4", "主题行", "scope 括号里是空的",
                                    "去掉括号，或者写上具体模块名"))
        elif re.search(r"\s", scope):
            findings.append(Finding("spec", "规则 4", "主题行",
                                    f"scope {scope!r} 里有空格",
                                    "scope 是名词，不能含空格；用 `-` 连起来"))

    commit_type = match.group("type")
    if commit_type.lower() not in TYPES:
        findings.append(Finding("project", "type 表",
                                "主题行", f"{commit_type!r} 不在本项目的 type 表里"
                                f"（规范规则 14 明确允许其它 type，所以这不是规范违规）",
                                "可用：" + "、".join(TYPES)))
    elif commit_type != commit_type.lower():
        findings.append(Finding("project", "统一小写",
                                "主题行", f"type {commit_type!r} 用了大写",
                                "规范 15 说实现者不得区分大小写，所以这**不是**规范问题；"
                                "但同一仓库里最好一致，按小写写"))

    # ── 规则 6：正文必须在描述之后**空一行** ──
    if len(lines) > 1:
        if lines[1].strip():
            findings.append(Finding("spec", "规则 6", "第 2 行",
                                    "描述下面直接接了内容，没有空行",
                                    "描述与正文之间必须空一行"))

    # ── 规则 8/9/12/16：footer 的形状 ──
    findings.extend(_check_footers(lines))

    # ── 规范**没有**规定、但写出来更容易读的（只提示，不算违规） ──
    if description.endswith(("。", ".", "．")):
        findings.append(Finding("project", "可读性提示", "主题行", TRAILING_PERIOD_ADVICE,
                                "规范没有禁止，只是多数工具链的习惯"))
    if len(subject) > SUBJECT_LENGTH_ADVICE:
        findings.append(Finding("project", "可读性提示", "主题行",
                                f"主题行 {len(subject)} 字符，超过 {SUBJECT_LENGTH_ADVICE}",
                                "规范没有限制长度；超过之后在 log --oneline 里会被截断"))
    return kind, findings


def _check_footers(lines: list[str]) -> list[Finding]:
    """只在**最后一段**里查 footer。

    规范 10 允许 footer 的值跨行，所以从后往前找；更早的段落当正文 ——
    正文里出现 `Note: xxx` 这种句子很常见，一律当 footer 会造出一堆噪音，
    而**全是噪音的检查比没有检查更糟**（会被忽略，然后连它对的那部分也被忽略）。
    """
    out: list[Finding] = []
    block_start = len(lines)
    for index in range(len(lines) - 1, 0, -1):
        if not lines[index].strip():
            block_start = index + 1
            break
        block_start = index
    for line in lines[block_start:]:
        if not line.strip():
            continue
        match = FOOTER.match(line)
        if not match:
            continue
        token = match.group("token").strip()
        # 规则 12 / 15：作为 footer 出现时 **必须大写**
        if token.upper() in ("BREAKING CHANGE", "BREAKING-CHANGE") and token not in BREAKING_OK:
            out.append(Finding("spec", "规则 12", f"footer {token!r}",
                               "破坏性变更的 footer 必须全大写 BREAKING CHANGE",
                               "改成 `BREAKING CHANGE: <说明>`"))
            continue
        # 规则 9：token 里用 `-` 代替空白
        if re.search(r"\s", token) and token not in BREAKING_OK:
            out.append(Finding("spec", "规则 9", f"footer {token!r}",
                               "token 里不能有空格",
                               f"用 `-` 连起来，例如 {token.replace(' ', '-')!r}"))
    return out


def template() -> str:
    lines = ["<type>(<scope>)!: <一句话说清这次改了什么>", "",
             "<为什么这么改、影响什么、还有什么没做 —— 正文从第二段起随便写>", "",
             "Refs: #123",
             f"（破坏性变更写在 footer：BREAKING CHANGE: <哪里不兼容了>）", "",
             "可用 type：" + "、".join(f"{name}（{desc}）" for name, desc in TYPES.items())]
    return "\n".join(lines)


def render(kind: str, findings: list[Finding], subject: str) -> str:
    if kind == "empty":
        return "✗ 提交信息是空的"
    if kind == "not-applicable":
        label = classify(subject)[1]
        return (f"— 不适用 Conventional Commits（{label}）\n"
                "  这类提交不是手写的常规提交，规范也没打算管它们。")
    spec_issues = [f for f in findings if f.source == "spec"]
    project_issues = [f for f in findings if f.source == "project"]
    if not spec_issues and not any(f.rule != "可读性提示" for f in project_issues):
        head = "✓ 符合 Conventional Commits v1.0.0"
    elif not spec_issues:
        head = "✓ 符合规范；有几条本项目的约定可以看看"
    else:
        head = f"✗ 违反规范 {len(spec_issues)} 处"
    body = [head]
    body.extend(f.line() for f in spec_issues)
    body.extend(f.line() for f in project_issues)
    return "\n".join(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按 Conventional Commits v1.0.0 校验提交信息")
    parser.add_argument("--check", metavar="MESSAGE", help="要校验的信息（- 表示从 stdin 读）")
    parser.add_argument("--check-file", metavar="PATH", help="从文件读（例如 .git/COMMIT_EDITMSG）")
    parser.add_argument("--template", action="store_true", help="打印骨架与 type 表")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    if args.template:
        print(template())
        return 0
    if args.check_file:
        try:
            with open(args.check_file, encoding="utf-8") as handle:
                # COMMIT_EDITMSG 里 `#` 开头的行是注释，不是信息的一部分
                message = "".join(line for line in handle if not line.startswith("#"))
        except OSError as exc:
            print(f"读不了 {args.check_file}：{exc}", file=sys.stderr)
            return 1
    elif args.check == "-" or (args.check is None and not sys.stdin.isatty()):
        message = sys.stdin.read()
        if not message.strip():
            print("没有拿到提交信息（用 --check 或 --check-file，或从 stdin 喂）", file=sys.stderr)
            return 1
    elif args.check is not None:
        message = args.check
    else:
        print("要给一条信息：--check \"…\" / --check-file PATH / 从 stdin 读", file=sys.stderr)
        return 1

    # 和 git 自己的清理对齐：默认 cleanup=strip（编辑器路径）与 -m 路径都会
    # 去掉开头/结尾的空行、去掉行尾空白。不做的后果实测过：COMMIT_EDITMSG 里
    # 注释写在前面时，剥掉注释后正文顶部会剩一个空行 —— 于是完全合规的信息
    # 被报成「规则 1：看不出一行以 type 开头」，诊断指到了错的地方。
    message = "\n".join(line.rstrip() for line in message.splitlines()).strip("\n")

    kind, findings = check(message)
    subject = message.strip().splitlines()[0] if message.strip() else ""
    if args.json:
        print(json.dumps({"kind": kind, "subject": subject,
                          "findings": [f.json() for f in findings]},
                         ensure_ascii=False, indent=2))
    else:
        print(render(kind, findings, subject))
    if kind == "empty":
        return 1          # 空信息是错的（render 那边也是这么说的），退出码必须跟结论一致
    if kind == "not-applicable":
        return 0
    return 1 if any(f.source == "spec" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
