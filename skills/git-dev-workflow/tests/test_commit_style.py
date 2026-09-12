#!/usr/bin/env python3
"""`commit_style.py` 的回归测试。

判据来自 **Conventional Commits v1.0.0 的 16 条规则**，所以用例按「哪一条」组织，
而且每个用例都直接引条目号 —— 以后规则理解错了，失败的用例会指出是哪一条错了。

## 两条最容易写反的规则（各有一个用例守着）

- **规则 15**：实现者**不得**区分大小写 → `FEAT:` 不能判违规。
- **规则 14**：`feat`/`fix` 之外的 type **可以用** → 未知 type 只能是"本项目约定"，
  不能报成规范违规。两类结论混在一起，会让人以为规范禁止了它其实允许的事。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CS = _load("commit_style", os.path.join(SCRIPTS, "commit_style.py"))


class StyleCase(unittest.TestCase):
    def findings(self, message: str) -> list:
        return CS.check(message)[1]

    def spec_rules(self, message: str) -> set:
        return {f.rule for f in self.findings(message) if f.source == "spec"}

    def project_rules(self, message: str) -> set:
        return {f.rule for f in self.findings(message) if f.source == "project"}

    def run_cli(self, argv: list) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = CS.main(argv)
        return code, buffer.getvalue()


class TestCompliant(StyleCase):
    def test_plain_subject(self):
        self.assertEqual(set(), self.spec_rules("fix: 修正分页越界"))

    def test_scope(self):
        self.assertEqual(set(), self.spec_rules("fix(api): 修正分页越界"))

    def test_breaking_by_bang(self):
        self.assertEqual(set(), self.spec_rules("feat(api)!: 去掉 v1 分页参数"))

    def test_breaking_by_footer_needs_a_blank_line_first(self):
        message = "feat: 换掉配置来源\n\nBREAKING CHANGE: 环境变量优先于配置文件"
        self.assertEqual(set(), self.spec_rules(message))

    def test_breaking_change_hyphen_form_is_synonymous(self):
        """规则 16：`BREAKING-CHANGE` 与 `BREAKING CHANGE` 同义。"""
        message = "feat: 换掉配置来源\n\nBREAKING-CHANGE: 环境变量优先"
        self.assertEqual(set(), self.spec_rules(message))

    def test_body_and_footers(self):
        message = ("fix(worker): 主备名写反\n\n"
                   "切换后仍在读旧实例，改成按 role_code 取。\n\n"
                   "Reviewed-by: 张三\nRefs: #228")
        self.assertEqual(set(), self.spec_rules(message))


class TestSpecViolations(StyleCase):
    def test_rule_1_full_width_colon(self):
        """历史里真的出现过：`feat(管理端)：修改用户名`。"""
        self.assertIn("规则 1", self.spec_rules("feat(管理端)：修改用户名"))

    def test_rule_1_missing_colon(self):
        self.assertIn("规则 1", self.spec_rules("feat 加了个东西"))

    def test_rule_1_missing_space_after_colon(self):
        self.assertIn("规则 1", self.spec_rules("fix:没空格"))

    def test_rule_5_empty_description(self):
        self.assertIn("规则 5", self.spec_rules("fix(api):   "))

    def test_rule_4_empty_scope(self):
        self.assertIn("规则 4", self.spec_rules("fix(): 补上 scope"))

    def test_rule_4_scope_with_space(self):
        self.assertIn("规则 4", self.spec_rules("fix(a b): 补上 scope"))

    def test_rule_6_body_without_blank_line(self):
        self.assertIn("规则 6", self.spec_rules("fix: 小修\n正文直接接上了"))

    def test_rule_6_footer_without_blank_line(self):
        self.assertIn("规则 6", self.spec_rules("fix: 小修\nRefs: #1"))

    def test_rule_9_footer_token_with_space(self):
        message = "fix: 小修\n\nReviewed by: 张三"
        self.assertIn("规则 9", self.spec_rules(message))

    def test_rule_12_lowercase_breaking_change(self):
        message = "feat: 换配置\n\nbreaking change: 环境变量优先"
        self.assertIn("规则 12", self.spec_rules(message))

    def test_rule_12_mixed_case_breaking_change(self):
        message = "feat: 换配置\n\nBreaking Change: 环境变量优先"
        self.assertIn("规则 12", self.spec_rules(message))


class TestDiagnosisPointsAtTheRightThing(StyleCase):
    """诊断必须指出**真正的**病因。

    两类问题都会让正则匹配不上，如果按"匹配不上就报规则 1"，读的人会去改冒号 ——
    而冒号本来是对的。两个都真实发生过：
    """

    def test_misplaced_bang_is_rule_13_not_rule_1(self):
        """`feat!(api): x` —— `!` 位置错，但会先被误报成"没有冒号"。"""
        rules = self.spec_rules("feat!(api): 去掉分页参数")
        self.assertIn("规则 13", rules)
        self.assertNotIn("规则 1", rules, "病因说错了：冒号是在的，错的是 `!` 的位置")

    def test_hyphenated_type_is_not_reported_as_missing_colon(self):
        """`e2e-ops: x` —— type 不在表里，但会先被误报成"没有冒号"。"""
        rules = self.spec_rules("e2e-ops: 36/36 全过")
        self.assertNotIn("规则 1", rules, "病因说错了：冒号是在的，问题是 type 不在表里")

    def test_valid_bang_placement_is_clean(self):
        for message in ("feat!: 去掉分页参数", "feat(api)!: 去掉分页参数"):
            with self.subTest(message=message):
                self.assertEqual(set(), self.spec_rules(message))


class TestCaseSensitivityIsNotARule(StyleCase):
    def test_rule_15_uppercase_type_is_not_a_violation(self):
        """规则 15 明说实现者**不得**区分大小写 —— 所以 `FEAT:` 不违规。

        只允许提醒"最好统一"（本项目约定），不允许报成规范违规。
        把它写成硬规则，等于在一个说"无所谓"的地方自己造了一个错。
        """
        message = "FEAT: 加个东西"
        self.assertEqual(set(), self.spec_rules(message))
        self.assertIn("统一小写", self.project_rules(message))


class TestProjectConventions(StyleCase):
    def test_unknown_type_is_project_only(self):
        """规则 14 允许其它 type → 未知 type 只能是"本项目约定"。"""
        message = "e2e-ops: 36/36 全过"
        self.assertEqual(set(), self.spec_rules(message))
        self.assertIn("type 表", self.project_rules(message))

    def test_hyphenated_type_is_parsed_as_one_token(self):
        """回归：type 正则曾经不接受连字符，于是 `e2e-ops:` 被解析成 type=`e2e`，
        报出来的错变成"type 后面没有冒号" —— 一个误导性的诊断。"""
        findings = self.findings("e2e-ops: 36/36 全过")
        self.assertNotIn("规则 1", {f.rule for f in findings if f.source == "spec"})
        self.assertTrue(any("e2e-ops" in f.detail for f in findings),
                        "诊断里必须出现完整的 type，而不是被截断的 e2e")

    def test_long_subject_is_only_advice(self):
        message = "docs: " + "很长的说明" * 20
        self.assertEqual(set(), self.spec_rules(message))
        self.assertIn("可读性提示", self.project_rules(message))

    def test_trailing_period_is_only_advice(self):
        message = "docs: 更新说明。"
        self.assertEqual(set(), self.spec_rules(message))
        self.assertIn("可读性提示", self.project_rules(message))


class TestNotApplicable(StyleCase):
    def test_merge_commit(self):
        kind, findings = CS.check("Merge remote-tracking branch 'origin/dev' into dev")
        self.assertEqual("not-applicable", kind)
        self.assertEqual([], findings)

    def test_git_default_revert(self):
        self.assertEqual("not-applicable", CS.check('Revert "feat: x"')[0])

    def test_autosquash_markers(self):
        for marker in ("fixup! feat: x", "squash! feat: x", "amend! feat: x"):
            with self.subTest(marker=marker):
                self.assertEqual("not-applicable", CS.check(marker)[0])

    def test_not_applicable_exits_zero(self):
        """挂了 commit-msg 钩子的仓库必须还能合并 —— 所以这类要放行。"""
        code, _ = self.run_cli(["--check", "Merge branch 'dev' into main"])
        self.assertEqual(0, code)


class TestExitCodes(StyleCase):
    def test_compliant_exits_zero(self):
        self.assertEqual(0, self.run_cli(["--check", "fix: 小修"])[0])

    def test_spec_violation_exits_one(self):
        self.assertEqual(1, self.run_cli(["--check", "fix:没空格"])[0])

    def test_project_only_violation_exits_zero(self):
        """本项目约定不挡提交 —— 否则一个新加的 type 就再也提交不了了。"""
        self.assertEqual(0, self.run_cli(["--check", "e2e-ops: 小修"])[0])

    def test_empty_message_is_rejected(self):
        code, output = self.run_cli(["--check", "   \n"])
        self.assertEqual(1, code)
        self.assertIn("空", output)


class TestCli(StyleCase):
    def test_template_lists_every_type(self):
        code, output = self.run_cli(["--template"])
        self.assertEqual(0, code)
        for name in CS.TYPES:
            self.assertIn(name, output)

    def test_json_output_is_machine_readable(self):
        code, output = self.run_cli(["--check", "fix:没空格", "--json"])
        payload = json.loads(output)
        self.assertEqual(1, code)
        self.assertEqual("conventional", payload["kind"])
        self.assertTrue(any(item["source"] == "spec" for item in payload["findings"]))

    def test_check_file_ignores_comment_lines(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as handle:
            handle.write("fix(api): 修正分页越界\n\n# 这是 COMMIT_EDITMSG 里的注释\n")
            path = handle.name
        self.addCleanup(os.unlink, path)
        code, _ = self.run_cli(["--check-file", path])
        self.assertEqual(0, code)

    def test_check_file_when_comments_come_first(self):
        """回归：注释写在**前面**时，剥掉注释后正文顶部会剩下一个空行。

        去掉首尾空行是 git 默认就会做的事（cleanup=strip）—— 不做的话，完全合规
        的信息会被报成「规则 1：看不出一行以 type 开头」，诊断指到了错的地方。
        上面那条用例把注释放在**末尾**（用户手打的顺序），正好绕开了这个朝向。
        """
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as handle:
            handle.write("# 注释在前（git 的模板就是这样）\n\nfix: 从文件读\n")
            path = handle.name
        self.addCleanup(os.unlink, path)
        code, output = self.run_cli(["--check-file", path])
        self.assertEqual(0, code, output)

    def test_leading_blank_lines_are_not_a_spec_violation(self):
        """同一条清理的另一个朝向：开头多了空行，信息本身是合规的。"""
        code, output = self.run_cli(["--check", "\n\nfix: 从命令行来\n"])
        self.assertEqual(0, code, output)


if __name__ == "__main__":
    unittest.main()
