#!/usr/bin/env python3
"""校验一篇周发版笔记：守住这个 skill **自己写下的规则**。

为什么是这个范围
----------------
它原本是 0 脚本 0 测试。但「补机械校验」不等于「发明一套笔记格式」——那只会校验出我自己
想象出来的东西。能机械校验的，只能是 SKILL.md 与 `references/release-note-template.md`
里**已经写明的**规则：

| 检查 | 依据 |
| --- | --- |
| 文件名是 `发版 - <系统> - YYYY-Www.md` | SKILL.md 的「Default naming」 |
| 那个 ISO 周号真实存在 | 同上（`2026-W53` 这种要拦住） |
| 一级标题与文件名一致 | 模板里 `# 发版 - … - YYYY-Www` |
| frontmatter 有 `type` / `created` | 模板 |
| `## 01`…`## 06` 骨架齐 | 模板（**章节列表从模板文件里读，不在这里抄一份**） |
| 同一系统同一周只有一篇 | SKILL.md：「已存在就更新，不要再建一份」 |
| 笔记被别处引用 | SKILL.md：「挂到最近的 MOC 或父笔记上」 |
| 没有明显的密钥值 | 模板：「不写密钥、令牌、密码」 |

**链接是否失效不在这里查** —— 那是 PKB 的 `check_links.py`（SKILL.md 已经要求跑它）。

用法
----
    python3 check_release_note.py <笔记路径> [--vault <vault 根>]
    python3 check_release_note.py --dir <目录> [--vault <vault 根>]

退出码：0 通过或只有提醒 / 1 有问题 / 2 用法或读不到
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import os
import re
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
TEMPLATE = os.path.join(SKILL_ROOT, "references", "release-note-template.md")
VAULT_PATH_SCRIPT = os.path.join(
    os.path.dirname(SKILL_ROOT), "obsidian-personal-knowledge-base", "scripts", "vault_path.py")

NAME_RE = re.compile(r"^发版 - (?P<system>.+) - (?P<year>\d{4})-W(?P<week>\d{2})\.md$")
# 重复检测用**宽松**的形状：现实里重名副本长成「发版 - X - 2026-W18 (2).md」「… - 副本.md」。
# 用严格的正则会反而漏掉它真正要抓的那种情况（这个缺口是测试拓出来的）。
DUP_NAME_RE = re.compile(r"^发版 - (?P<system>.+) - (?P<year>\d{4})-W(?P<week>\d{2})(?P<extra>.*)\.md$")
FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
SECTION_RE = re.compile(r"^## (\d{2}) (.+)$", re.MULTILINE)

# 明显的密钥赋值（要拦住）。只匹配「赋值 + 看起来是值」的形状：
# 「- 环境变量 DB_PASSWORD 放在配置中心」这种只提名字的不算 —— 模板明确要求的是
# 「只写变量名和位置」，那种写法是对的。
SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key)\b\s*[:=]\s*(?P<value>\S+)")
SECRET_OK_VALUES = ("待确认", "见配置中心", "略", "-", "", "…")


class Finding:
    def __init__(self, ok: bool, label: str, detail: str = "", hint: str = "",
                 warn: bool = False) -> None:
        self.ok = ok
        self.label = label
        self.detail = detail
        self.hint = hint
        self.warn = warn


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def listdir(path: str) -> list[str]:
    """列目录；读不到就当空目录（检查工具不该因为一个目录没权限就整体失败）。"""
    try:
        return os.listdir(path)
    except OSError:
        return []


def template_sections() -> list[tuple[str, str]]:
    """从模板里读章节骨架 —— 不在脚本里再抄一份（抄了必然漂移）。"""
    text = read_text(TEMPLATE)
    fenced = re.findall(r"^````markdown\n(.*?)^````$", text, re.DOTALL | re.MULTILINE)
    body = fenced[0] if fenced else text
    return [(number, title.strip()) for number, title in SECTION_RE.findall(body)]


def template_frontmatter_keys() -> list[str]:
    text = read_text(TEMPLATE)
    fenced = re.findall(r"^````markdown\n(.*?)^````$", text, re.DOTALL | re.MULTILINE)
    body = fenced[0] if fenced else text
    match = FM_RE.match(body)
    if not match:
        return []
    keys: list[str] = []
    for line in match.group(1).splitlines():
        if line and not line.startswith((" ", "\t", "-")) and ":" in line:
            keys.append(line.split(":", 1)[0].strip())
    return keys


def vault_root(explicit: str | None) -> str:
    """解析 vault 根：显式 > PKB 的 vault_path.py > 空（空就跳过需要 vault 的检查）。"""
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    if not os.path.isfile(VAULT_PATH_SCRIPT):
        return ""
    spec = importlib.util.spec_from_file_location("_wlrr_vault_path", VAULT_PATH_SCRIPT)
    if spec is None or spec.loader is None:
        return ""
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        path, _source = module.resolve(None)
    except Exception:  # noqa: BLE001 - 拿不到就当没有，由调用方跳过相关检查
        return ""
    return path if path and os.path.isdir(path) else ""


def check_file(path: str, vault: str) -> list[Finding]:
    findings: list[Finding] = []
    name = os.path.basename(path)
    text = read_text(path)
    if not text:
        return [Finding(False, "读得到文件", path, "确认路径对不对")]

    match = NAME_RE.match(name)
    findings.append(Finding(
        bool(match), "文件名是「发版 - <系统> - YYYY-Www.md」",
        "" if match else name,
        "按 SKILL.md 的 Default naming 改名；已存在当周笔记时应当是**更新它**，不是再建一份"))
    week_ok = False
    if match:
        try:
            datetime.date.fromisocalendar(int(match.group("year")), int(match.group("week")), 1)
            week_ok = True
        except ValueError:
            week_ok = False
    findings.append(Finding(week_ok, "ISO 周号真实存在",
                            "" if week_ok else "这个年份没有这一周",
                            "核对年份与周号（例如有些年没有第 53 周）"))

    headings = [line.strip() for line in text.splitlines() if line.startswith("# ")]
    expected_title = f"# {name[:-3]}" if match else ""
    title_ok = bool(headings) and headings[0] == expected_title
    findings.append(Finding(title_ok, "一级标题与文件名一致",
                            "" if title_ok else f"标题={headings[0] if headings else '（没有）'}",
                            "模板里的 H1 就是文件名（去掉 .md）"))

    fm = FM_RE.match(text)
    keys = template_frontmatter_keys()
    present: list[str] = []
    if fm:
        for line in fm.group(1).splitlines():
            if ":" in line and not line.startswith((" ", "\t")):
                present.append(line.split(":", 1)[0].strip())
    missing = [k for k in keys if k not in present]
    created = ""
    if fm:
        found = re.search(r"^created:\s*(\S+)", fm.group(1), re.MULTILINE)
        created = found.group(1) if found else ""
    date_ok = bool(re.match(r"^\d{4}-\d{2}-\d{2}$", created))
    findings.append(Finding(not missing and date_ok, "frontmatter 有模板要求的键",
                            "" if not missing else f"缺 {'、'.join(missing)}",
                            "type / status / created / tags 见模板"))

    wanted = template_sections()
    have = {(number, title) for number, title in SECTION_RE.findall(text)}
    absent = [f"## {n} {t}" for n, t in wanted if (n, t) not in have]
    findings.append(Finding(not absent, f"章节骨架齐（模板里共 {len(wanted)} 节）",
                            "" if not absent else f"缺：{'、'.join(absent)}",
                            "章节列表是从 references/release-note-template.md 读的"))

    leaked: list[str] = []
    for line in text.splitlines():
        for found in SECRET_RE.finditer(line):
            value = found.group("value").strip("`'\"")
            if value and value not in SECRET_OK_VALUES and not value.startswith("{{"):
                leaked.append(f"{found.group(1)}={value}")
    findings.append(Finding(not leaked, "没有明显的密钥值", "" if not leaked else "、".join(leaked),
                            "只写变量名和位置，不写值（模板里的规则）", warn=True))

    if vault:
        findings.extend(check_referenced(path, name, vault))
    else:
        findings.append(Finding(True, "被别处引用（跳过）", "没解析到 vault 根",
                                "加 --vault，或配置 $OBSIDIAN_VAULT_PATH", warn=True))
    return findings


def check_referenced(path: str, name: str, vault: str) -> list[Finding]:
    """SKILL.md：「挂到最近的 MOC 或父笔记上」。查整份 vault 里有没有别处提到它。"""
    stem = name[:-3]
    hits = 0
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(vault):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            if not filename.endswith(".md"):
                continue
            candidate = os.path.join(dirpath, filename)
            if os.path.abspath(candidate) == os.path.abspath(path):
                continue
            scanned += 1
            body = read_text(candidate)
            if stem in body:
                hits += 1
    return [Finding(hits > 0, "被别处引用（MOC / 父笔记）",
                    f"扫了 {scanned} 篇笔记，{hits} 处提到它" if hits else "没有任何笔记引用它",
                    "把这篇挂到最近的 MOC 或父笔记上 —— 否则它只存在于文件系统里")]


class DuplicateFinder:
    """同一系统同一周只应有一篇（SKILL.md：已存在就更新，不要再建一份）。"""

    @staticmethod
    def check(directory: str) -> list[Finding]:
        groups: dict[tuple[str, str], list[str]] = {}
        for filename in sorted(listdir(directory)):
            match = DUP_NAME_RE.match(filename)
            if match:
                groups.setdefault((match.group("system"), f"{match.group('year')}-W{match.group('week')}"),
                                  []).append(filename)
        dups = {key: value for key, value in groups.items() if len(value) > 1}
        if not dups:
            return [Finding(True, "同一系统同一周只有一篇",
                            f"目录里共 {len(groups)} 个（系统, 周）组合")]
        detail = "；".join(f"{system} {week}：" + "、".join(names)
                          for (system, week), names in sorted(dups.items()))
        return [Finding(False, "同一系统同一周只有一篇", detail, "合并成一篇，别留两份")]


def render(findings: list[Finding], title: str) -> str:
    lines = [title, ""]
    for item in findings:
        mark = "✓" if item.ok else ("⚠" if item.warn else "✗")
        line = f"  {mark} {item.label}"
        if item.detail:
            line += f" —— {item.detail}"
        lines.append(line)
        if not item.ok and item.hint:
            lines.append(f"      改法：{item.hint}")
    bad = [f for f in findings if not f.ok and not f.warn]
    warned = [f for f in findings if not f.ok and f.warn]
    lines.append("")
    lines.append(f"共 {len(findings)} 项：{len(findings) - len(bad) - len(warned)} 通过、"
                 f"{len(bad)} 有问题、{len(warned)} 提醒")
    if not bad and not warned:
        lines.append("（链接是否失效不在这里查 —— 那是 PKB 的 check_links.py）")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="校验周发版笔记（守住 SKILL.md 写明的规则）")
    parser.add_argument("note", nargs="?", help="笔记路径")
    parser.add_argument("--dir", help="改成一个目录：检查目录里所有发版笔记 + 重复周")
    parser.add_argument("--vault", help="vault 根（不给就按配置解析；拿不到就跳过引用检查）")
    args = parser.parse_args(argv)

    vault = vault_root(args.vault)
    if args.dir:
        directory = os.path.abspath(os.path.expanduser(args.dir))
        if not os.path.isdir(directory):
            print(f"读不到目录：{directory}", file=sys.stderr)
            return 2
        findings: list[Finding] = []
        names = [f for f in sorted(listdir(directory)) if NAME_RE.match(f)]
        for name in names:
            findings.extend(check_file(os.path.join(directory, name), vault))
        findings.extend(DuplicateFinder.check(directory))
        print(render(findings, f"发版笔记检查  {directory}（{len(names)} 篇）"))
        return 1 if any(not f.ok and not f.warn for f in findings) else 0

    if not args.note:
        parser.print_help()
        return 2
    path = os.path.abspath(os.path.expanduser(args.note))
    if not os.path.isfile(path):
        print(f"读不到笔记：{path}", file=sys.stderr)
        return 2
    findings = check_file(path, vault)
    print(render(findings, f"发版笔记检查  {path}"))
    return 1 if any(not f.ok and not f.warn for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
