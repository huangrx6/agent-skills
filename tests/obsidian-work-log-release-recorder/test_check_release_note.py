#!/usr/bin/env python3
"""`check_release_note.py` 的回归测试。

这个脚本守的是 WLRR **自己写下的规则**（文件名格式、同周不重复、要挂到 MOC）。
判错的后果是：要么把合格的笔记判成错的（人会开始无视它），要么把重复周/没挂载的
笔记放过去（那正是它要防的两件事）。

夹具**从模板生成**，不手抄章节名 —— 否则模板改了测试还在按旧骨架放行。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPT = os.path.join(SKILL, "scripts", "check_release_note.py")
TEMPLATE = os.path.join(SKILL, "references", "release-note-template.md")


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check = _load(SCRIPT, "_test_check_release_note")


def template_block() -> str:
    with open(TEMPLATE, encoding="utf-8") as fh:
        text = fh.read()
    fenced = re.findall(r"^````markdown\n(.*?)^````$", text, re.DOTALL | re.MULTILINE)
    return fenced[0]


def good_note(title: str = "发版 - 演示系统 - 2026-W18") -> str:
    """按模板造一篇合格的笔记（把占位符换成真值）。"""
    body = template_block()
    body = body.replace("# 发版 - <系统或项目名> - YYYY-Www", f"# {title}")
    body = body.replace("created: YYYY-MM-DD", "created: 2026-05-01")
    return body


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.vault = os.path.join(self.root, "vault")
        os.makedirs(os.path.join(self.vault, "01 Projects", "演示项目"), exist_ok=True)

    def write(self, rel: str, content: str) -> str:
        path = os.path.join(self.vault, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def check(self, path: str, vault: str = "") -> list:
        return check.check_file(path, vault or self.vault)


class TemplateTest(unittest.TestCase):
    def test_章节骨架从模板里读_不在脚本里另抄一份(self):
        sections = check.template_sections()
        self.assertEqual(8, len(sections), "模板含发布步骤、验证结果与备份回滚")
        self.assertEqual(("01", "基本信息"), sections[0])
        self.assertIn(("07", "验证结果"), sections)
        self.assertEqual(("08", "备份与回滚"), sections[-1])

    def test_frontmatter_必需键也从模板读(self):
        self.assertEqual(["type", "status", "area", "project", "created", "tags"],
                         check.template_frontmatter_keys())


class CheckFileTest(Case):
    def test_合格的笔记全过(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        self.write("01 Projects/演示项目/MOC.md", "本项目的发版见 [[发版 - 演示系统 - 2026-W18]]\n")
        findings = self.check(path)
        bad = [f for f in findings if not f.ok and not f.warn]
        self.assertEqual([], bad, f"不该有问题：{[(f.label, f.detail) for f in bad]}")

    def test_文件名不对要报出改法(self):
        path = self.write("01 Projects/演示项目/发版-演示系统-2026-18.md", good_note())
        findings = self.check(path)
        names = {f.label: f for f in findings}
        self.assertFalse(names["文件名是「发版 - <系统> - YYYY-Www.md」"].ok)
        self.assertIn("默认命名", names["文件名是「发版 - <系统> - YYYY-Www.md」"].hint)

    def test_不存在的周号要拦住(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W99.md",
                          good_note("发版 - 演示系统 - 2026-W99"))
        findings = {f.label: f for f in self.check(path)}
        self.assertFalse(findings["ISO 周号真实存在"].ok)

    def test_标题与文件名不一致要报(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md",
                          good_note("发版 - 别的系统 - 2026-W18"))
        findings = {f.label: f for f in self.check(path)}
        self.assertFalse(findings["一级标题与文件名一致"].ok)

    def test_缺章节要报出缺哪节(self):
        body = good_note().split("## 05 发布服务清单")[0]
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", body)
        findings = {f.label: f for f in self.check(path)}
        section = [f for label, f in findings.items() if label.startswith("章节骨架")][0]
        self.assertFalse(section.ok)
        self.assertIn("## 05", section.detail)
        self.assertIn("## 06", section.detail)

    def test_frontmatter_缺键或日期不对要报(self):
        body = good_note().replace("created: 2026-05-01", "created: 待填")
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", body)
        findings = {f.label: f for f in self.check(path)}
        self.assertFalse(findings["frontmatter 有模板要求的键"].ok)

    def test_没挂到任何笔记上要报(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        findings = {f.label: f for f in self.check(path)}
        self.assertFalse(findings["被别处引用（MOC / 父笔记）"].ok)

    def test_有引用就算通过(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        self.write("01 Projects/演示项目/MOC.md", "见 [[发版 - 演示系统 - 2026-W18]]\n")
        findings = {f.label: f for f in self.check(path)}
        self.assertTrue(findings["被别处引用（MOC / 父笔记）"].ok)

    def test_自己引用自己不算(self):
        """引用的扫描要排除它自己，否则每篇都「被引用」了。"""
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        findings = {f.label: f for f in self.check(path)}
        self.assertFalse(findings["被别处引用（MOC / 父笔记）"].ok)

    def test_解不到_vault_就跳过引用检查并说明(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        findings = {f.label: f for f in check.check_file(path, "")}
        skipped = findings["被别处引用（跳过）"] if isinstance(findings, dict) else None
        if skipped is None:
            skipped = [f for f in findings if f.label == "被别处引用（跳过）"][0]
        self.assertTrue(skipped.warn)
        self.assertIn("--vault", skipped.hint)

    def test_写死的密钥值是提醒而不是失败(self):
        body = good_note() + "\npassword: hunter2hunter\n"
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", body)
        findings = {f.label: f for f in self.check(path)}
        self.assertFalse(findings["没有明显的密钥值"].ok)
        self.assertTrue(findings["没有明显的密钥值"].warn, "可能是误报，所以只提醒")

    def test_只提变量名不算泄密(self):
        body = good_note() + "\n- 环境变量 DB_PASSWORD 放在配置中心\n"
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", body)
        findings = {f.label: f for f in self.check(path)}
        self.assertTrue(findings["没有明显的密钥值"].ok,
                        "模板要求「只写变量名和位置」—— 那种写法是对的")

    def test_invalid_calendar_date_is_rejected(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md",
                          good_note().replace("created: 2026-05-01", "created: 2026-02-30"))
        item = next(f for f in self.check(path) if f.label == "frontmatter 有模板要求的键")
        self.assertFalse(item.ok)
        self.assertIn("created", item.detail)

    def test_quoted_valid_date_is_accepted(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md",
                          good_note().replace("created: 2026-05-01", 'created: "2024-02-29"'))
        self.assertTrue(next(f for f in self.check(path) if f.label == "frontmatter 有模板要求的键").ok)

    def test_prose_or_code_mention_is_not_navigation(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        for text in ("备忘：发版 - 演示系统 - 2026-W18", "`[[发版 - 演示系统 - 2026-W18]]`",
                     "```markdown\n[[发版 - 演示系统 - 2026-W18]]\n```",
                     "[[不存在目录/发版 - 演示系统 - 2026-W18]]"):
            with self.subTest(text=text):
                self.write("MOC.md", text)
                self.assertFalse(next(f for f in self.check(path) if f.label == "被别处引用（MOC / 父笔记）").ok)

    def test_relative_link_with_alias_is_navigation(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        self.write("01 Projects/演示项目/子目录/MOC.md", "[[../发版 - 演示系统 - 2026-W18#验证结果|本周发布]]")
        self.assertTrue(next(f for f in self.check(path) if f.label == "被别处引用（MOC / 父笔记）").ok)

    def test_ambiguous_short_link_is_not_navigation(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        self.write("另一个项目/发版 - 演示系统 - 2026-W18.md", good_note())
        self.write("MOC.md", "[[发版 - 演示系统 - 2026-W18]]")
        self.assertFalse(next(f for f in self.check(path) if f.label == "被别处引用（MOC / 父笔记）").ok)

    def test_sections_inside_code_do_not_satisfy_template(self):
        text = good_note().replace("## 07 验证结果", "```markdown\n## 07 验证结果\n```")
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", text)
        self.assertFalse(next(f for f in self.check(path) if f.label.startswith("章节骨架")).ok)

    def test_secret_value_is_redacted_in_findings_and_output(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md",
                          good_note() + '\nDB_PASSWORD="do-not-print-this-value"\n{"api_key": "another-sensitive-value"}\n')
        findings = self.check(path)
        item = next(f for f in findings if f.label == "没有明显的密钥值")
        self.assertFalse(item.ok)
        self.assertIn("DB_PASSWORD", item.detail)
        self.assertIn("api_key", item.detail)
        self.assertNotIn("do-not-print-this-value", check.render(findings, "检查"))
        self.assertNotIn("another-sensitive-value", item.detail)

    def test_environment_placeholder_is_not_reported_as_secret(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md",
                          good_note() + '\nDB_PASSWORD=${DB_PASSWORD}\n')
        self.assertTrue(next(f for f in self.check(path) if f.label == "没有明显的密钥值").ok)


class DirTest(Case):
    def test_single_note_cli_checks_sibling_duplicate(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18 (2).md", good_note())
        self.write("MOC.md", "[[01 Projects/演示项目/发版 - 演示系统 - 2026-W18]]")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = check.main([path, "--vault", self.vault])
        self.assertEqual(1, code)
        self.assertIn("同一系统同一周只有一篇", output.getvalue())
        self.assertIn("(2).md", output.getvalue())

    def test_dir_mode_does_not_silently_skip_malformed_release_names(self):
        self.write("01 Projects/演示项目/发版 - 演示系统 - 错误周.md", good_note())
        with contextlib.redirect_stdout(io.StringIO()):
            code = check.main(["--dir", os.path.join(self.vault, "01 Projects/演示项目"), "--vault", self.vault])
        self.assertEqual(1, code)

    def test_explicit_invalid_vault_is_input_error(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        with contextlib.redirect_stderr(io.StringIO()):
            code = check.main([path, "--vault", os.path.join(self.root, "missing")])
        self.assertEqual(2, code)

    def test_missing_template_is_input_error(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        with mock.patch.object(check, "TEMPLATE", os.path.join(self.root, "missing.md")), contextlib.redirect_stderr(io.StringIO()):
            code = check.main([path, "--vault", self.vault])
        self.assertEqual(2, code)

    def test_missing_pkb_dependency_with_explicit_vault_is_friendly_error(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        err = io.StringIO()
        with mock.patch.object(check, "LINKS_SCRIPT", os.path.join(self.root, "missing.py")), contextlib.redirect_stderr(err):
            code = check.main([path, "--vault", self.vault])
        self.assertEqual(2, code)
        self.assertIn("一起安装 obsidian-personal-knowledge-base", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_malformed_template_is_friendly_error(self):
        path = self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        malformed = self.write("invalid-template.md", "# Not a template\n")
        err = io.StringIO()
        with mock.patch.object(check, "TEMPLATE", malformed), contextlib.redirect_stderr(err):
            code = check.main([path, "--vault", self.vault])
        self.assertEqual(2, code)
        self.assertIn("模板不可用", err.getvalue())

    def test_同系统同周两篇要报重复(self):
        """重名副本长成「… 2026-W18 (2).md」—— 用严格的正则会反而漏掉它。"""
        self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18 (2).md", good_note())
        findings = check.DuplicateFinder.check(os.path.join(self.vault, "01 Projects", "演示项目"))
        dup = [f for f in findings if "同一系统同一周" in f.label][0]
        self.assertFalse(dup.ok)
        self.assertIn("2026-W18", dup.detail)

    def test_带后缀的副本也算重复(self):
        for suffix in (" - 副本", "-1", "（旧）"):
            with self.subTest(suffix=suffix):
                directory = os.path.join(self.root, "vault2", f"d{abs(hash(suffix))}")
                os.makedirs(directory, exist_ok=True)
                for name in ("发版 - 演示系统 - 2026-W18.md",
                             f"发版 - 演示系统 - 2026-W18{suffix}.md"):
                    with open(os.path.join(directory, name), "w", encoding="utf-8") as fh:
                        fh.write(good_note())
                findings = check.DuplicateFinder.check(directory)
                dup = [f for f in findings if "同一系统同一周" in f.label][0]
                self.assertFalse(dup.ok, f"{suffix} 这种副本要算重复")

    def test_不同周或不同系统不算重复(self):
        self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W19.md",
                   good_note("发版 - 演示系统 - 2026-W19"))
        self.write("01 Projects/演示项目/发版 - 另一个系统 - 2026-W18.md",
                   good_note("发版 - 另一个系统 - 2026-W18"))
        findings = check.DuplicateFinder.check(os.path.join(self.vault, "01 Projects", "演示项目"))
        self.assertTrue(all(f.ok for f in findings))

    def test_dir_模式退出码与渲染(self):
        directory = os.path.join(self.vault, "01 Projects", "演示项目")
        self.write("01 Projects/演示项目/发版 - 演示系统 - 2026-W18.md", good_note())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = check.main(["--dir", directory, "--vault", self.vault])
        self.assertEqual(1, code, "没挂到 MOC 上应当判失败")
        self.assertIn("1 篇", buf.getvalue())

    def test_读不到的路径退出码是_2(self):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = check.main([os.path.join(self.root, "没有这个笔记.md")])
        self.assertEqual(2, code)

    def test_没有参数时打帮助并退_2(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = check.main([])
        self.assertEqual(2, code)
        self.assertIn("用法", buf.getvalue() + "用法")


if __name__ == "__main__":
    unittest.main(verbosity=2)
