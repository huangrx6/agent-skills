#!/usr/bin/env python3
"""validate_skill.py 的回归测试。

为什么需要：这个脚本是 skill 的机械检查器，其中「正文 ≤ 150 行」和
「无绑定声明矛盾」都是**阻塞性**的 —— 边界差一行就会误挡正常提交，判定写得宽一点
就会误报（实测已经误报过两次：WLRR 的「不绑定本机」被当成绑定声明，
skill-builder 里“描述这个失败模式”的句子被当成在犯这个错）。

检查器本身会坏，而它坏了的表现是**静默放行或静默误挡**。所以边界值和
判定规则都要有测试守住。我这次先是在临时 bash 里手动验了一遍 —— 那种验证是
一次性的，不会留下防线，所以搬到这里来。

fixture 在 setUp 里生成到临时目录，不落盘成真实 skill。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/test_validate_skill.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
VALIDATE = os.path.join(SCRIPTS, "validate_skill.py")

GOOD_DESC = "Use this skill when 整理笔记. Do NOT use for 发版."


def _load_validate():
    """按路径加载 validate_skill.py(scripts/ 不是包,不能用 import 语句)。"""
    spec = importlib.util.spec_from_file_location("validate_under_test", VALIDATE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {VALIDATE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _body_of_exactly(n: int) -> str:
    """构造一个 count("\\n") 恰好等于 n 的正文。"""
    return "- x\n" * n


def _skill(root: str, name: str, *, body: str | None = None,
           desc: str | None = None, fm_name: str | None = None) -> str:
    """在 root 下造一个 skill 目录,返回其路径。"""
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)
    front = f"---\nname: {fm_name if fm_name is not None else name}\n"
    front += f"description: {desc if desc is not None else GOOD_DESC}\n---\n"
    if body is None:
        body = "- x\n" * 30 + "\n| a | b |\n| --- | --- |\n"
    with open(os.path.join(path, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(front + body)
    return path


class ValidateSkillTest(unittest.TestCase):
    def setUp(self):
        self.mod = _load_validate()
        self.tmp = tempfile.mkdtemp(prefix="validate-skill-fixture-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self, path: str) -> dict:
        return self.mod.check_skill(path)

    def fails(self, path: str) -> bool:
        return bool(self.check(path)["errors"])

    # ── 防线 1:正文行数边界(阻塞性,差一行就会误挡或漏放) ──
    def test_body_line_limit_boundary(self):
        self.assertFalse(
            self.fails(_skill(self.tmp, "at-limit", body=_body_of_exactly(150))),
            "正文恰好 150 行应当通过",
        )
        self.assertTrue(
            self.fails(_skill(self.tmp, "over-limit", body=_body_of_exactly(151))),
            "正文 151 行应当失败",
        )

    # ── 防线 2:余量提示边界(只提示不失败) ──
    def test_headroom_notes_boundary(self):
        cases = [(139, False), (140, False), (141, True), (150, True)]
        for lines, should_note in cases:
            with self.subTest(body_lines=lines):
                r = self.check(_skill(self.tmp, f"h{lines}", body=_body_of_exactly(lines)))
                notes = r.get("notes", [])
                self.assertEqual(
                    bool(notes), should_note,
                    f"正文 {lines} 行的余量提示应为 {should_note},实得 {bool(notes)}",
                )
                self.assertFalse(r["errors"], f"正文 {lines} 行不该判失败(只提示)")

    def test_headroom_note_text_mentions_next_step(self):
        r = self.check(_skill(self.tmp, "headroom-text", body=_body_of_exactly(145)))
        self.assertTrue(r.get("notes"), "余量不足应有提示")
        self.assertIn("瘦身", r["notes"][0], "提示要说清下一步该做什么")

    # ── 防线 3:绑定声明的矛盾判定(已经误报过两次) ──
    def test_real_contradiction_is_flagged(self):
        body = ("This skill is bound to a specific machine and vault.\n"
                "\n"
                "- vault path resolves from $OBSIDIAN_VAULT_PATH\n")
        self.assertTrue(
            self.fails(_skill(self.tmp, "contradiction", body=body)),
            "分两行声明的真矛盾没被抓到 —— 这正是 WLRR 当初的形态",
        )

    # 已知的否定写法 —— 全是实测过会误报的。一个合理的“不绑定”写法被当成矛盾，
    # 会直接挡住提交，所以这些必须覆盖。不穷尽语言学变体，但这几种是关于
    # “绑定本机”的常见说法，中英文都有。
    NEGATED_FORMS = (
        "路径从配置解析,**不绑定本机**",
        "该 skill 并不绑定本机",
        "该 skill 无需绑定本机",
        "该 skill 没有绑定本机",
        "该 skill 并不需要绑定本机",
        "This skill is not bound to a specific machine.",
        "This skill isn't bound to a specific machine.",
        "This skill is no longer bound to a specific machine.",
        "This skill cannot be bound to a specific machine.",
        "This skill is never bound to a specific machine.",
    )

    def test_negated_declaration_is_not_flagged(self):
        for form in self.NEGATED_FORMS:
            with self.subTest(form=form):
                body = (f"# t\n\n- {form}\n"
                        "- path reads from ~/.config/obsidian-vault-path\n\n"
                        "| a | b |\n| --- | --- |\n")
                self.assertFalse(
                    self.fails(_skill(self.tmp, "negation", body=body)),
                    f"否定写法被当成绑定声明了: {form}",
                )

    def test_negation_in_previous_sentence_does_not_suppress(self):
        # 前看窗口不能太长，否则上一句的否定会连这一句的真声明一起豁免
        body = ("# t\n\n"
                "- This skill is not a chat toy. It is bound to a specific machine.\n"
                "- path reads from ~/.config/obsidian-vault-path\n\n"
                "| a | b |\n| --- | --- |\n")
        self.assertTrue(
            self.fails(_skill(self.tmp, "neg-cross", body=body)),
            "上一句里的否定把这一句的真声明也豁免掉了 —— 前看窗口太长",
        )

    def test_describing_the_antipattern_is_not_flagged(self):
        # skill-builder 里就有这么一句:它在讲这个失败模式本身,不是在犯它
        body = ("# t\n\n"
                "- 实测 WLRR 就是如此:上面说绑定本机,下面说路径从配置解析。\n"
                "\n"
                "- path is never hardcoded\n")
        self.assertFalse(
            self.fails(_skill(self.tmp, "describing", body=body)),
            "描述这个失败模式本身的句子被误判成矛盾了",
        )

    def test_quoted_example_is_not_flagged(self):
        body = ("# t\n\n"
                "- ✅ 不可用时显式声明(\"bound to specific machine\")\n"
                "\n"
                "- path resolves from $OBSIDIAN_VAULT_PATH\n")
        self.assertFalse(
            self.fails(_skill(self.tmp, "quoted", body=body)),
            "引号里作为例子出现的绑定表述被当成矛盾了",
        )

    def test_bound_only_is_not_flagged(self):
        # 正文要带表格/清单,否则会撞上另一条检查,测不到本意
        body = "# t\n\nThis skill is bound to a specific machine.\n\n| a | b |\n| --- | --- |\n"
        self.assertFalse(
            self.fails(_skill(self.tmp, "bound-only", body=body)),
            "真的绑定本机(没有可移植表述)不该被判矛盾",
        )

    def test_portable_only_is_not_flagged(self):
        body = "# t\n\nvault path reads from ~/.config/obsidian-vault-path\n\n| a | b |\n| --- | --- |\n"
        self.assertFalse(
            self.fails(_skill(self.tmp, "portable-only", body=body)),
            "只有可移植表述不该被判矛盾",
        )

    def test_portable_patterns_cover_common_phrasings(self):
        for text in ("never hardcode it", "reads from ~/.config/x", "从配置读取",
                     "resolves from $HOME/x", "OBSIDIAN_VAULT_PATH", "路径从配置解析"):
            with self.subTest(text=text):
                self.assertTrue(
                    any(re.search(p, text, re.I) for p in self.mod.PORTABLE_PATTERNS),
                    f"可移植表述 {text!r} 没有被任何 pattern 覆盖",
                )

    # ── 防线 4:其余结构检查 ──
    def test_missing_skill_md_fails(self):
        path = os.path.join(self.tmp, "empty")
        os.makedirs(path)
        self.assertTrue(self.fails(path), "缺 SKILL.md 应失败")

    def test_bad_yaml_fails(self):
        path = _skill(self.tmp, "bad-yaml")
        with open(os.path.join(path, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: [unclosed\ndescription: x\n---\n# t\n")
        self.assertTrue(self.fails(path), "YAML 不可解析应失败")

    def test_name_mismatch_fails(self):
        path = _skill(self.tmp, "dir-name", fm_name="other-name")
        self.assertTrue(self.fails(path), "name 与目录名不一致应失败")

    def test_long_description_fails(self):
        path = _skill(self.tmp, "long-desc", desc="Use this skill when x. Do NOT use for y. " + "字" * 800)
        self.assertTrue(self.fails(path), "description ≥ 800 字符应失败")

    def test_missing_do_not_boundary_fails(self):
        path = _skill(self.tmp, "no-boundary", desc="Use this skill when 整理笔记。")
        self.assertTrue(self.fails(path), "description 缺 Do NOT 边界应失败")

    def test_good_skill_passes(self):
        self.assertFalse(self.fails(_skill(self.tmp, "good")), "合法 skill 应通过")

    # ── CLI 行为:退出码契约 ──
    def test_cli_exit_code_is_0_when_clean(self):
        _skill(self.tmp, "good")   # 不先建一个,tmp 里没 SKILL.md 会返回 2
        proc = subprocess.run([sys.executable, VALIDATE, self.tmp],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"全部通过时退出码应为 0\n{proc.stdout}")

    def test_cli_exit_code_is_1_when_failing(self):
        _skill(self.tmp, "broken", fm_name="mismatch")
        proc = subprocess.run([sys.executable, VALIDATE, self.tmp],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, "有失败时退出码应为 1")

    def test_cli_exit_code_is_2_when_no_skill_found(self):
        proc = subprocess.run([sys.executable, VALIDATE, os.path.join(self.tmp, "nope")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2, "找不到任何 SKILL.md 时退出码应为 2")


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ── evals 的形状 ───────────────────────────────────────────────────────────
# 防线：evals 是「规则有没有被执行」的标尺，而标尺自己写错是**看不见**的 ——
# 它不会让任何测试失败，只会让评审时照着一条过期的标准看。这些用例盯的就是它。
def _with_evals(root: str, name: str, payload) -> str:
    """造一个带 evals/ 的 skill。payload 传字符串时原样写入（用来造坏 JSON）。"""
    path = _skill(root, name)
    evals_dir = os.path.join(path, "evals")
    os.makedirs(evals_dir, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    with open(os.path.join(evals_dir, "evals.json"), "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


class EvalShapeTest(unittest.TestCase):
    def setUp(self):
        self.mod = _load_validate()
        self.tmp = tempfile.mkdtemp(prefix="validate-evals-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fails(self, path: str) -> bool:
        return bool(self.mod.check_skill(path)["errors"])

    def make(self, name: str = "with-evals", payload=None) -> str:
        if payload is None:
            payload = {"skill_name": name, "evals": [
                {"id": 1, "prompt": "做点什么", "expected_output": "应该这样那样",
                 "files": []}]}
        return _with_evals(self.tmp, name, payload)

    def test_well_formed_evals_pass(self):
        self.assertFalse(self.fails(self.make()))

    def test_skill_without_evals_dir_is_fine(self):
        """没有 evals 不算错 —— 这条只查「写了的话形状对不对」。"""
        self.assertFalse(self.fails(_skill(self.tmp, "no-evals")))

    def test_skill_name_must_match_directory(self):
        self.assertTrue(self.fails(self.make(payload={"skill_name": "别的名字", "evals": [
            {"id": 1, "prompt": "p", "expected_output": "e"}]})))

    def test_duplicate_ids_are_flagged(self):
        self.assertTrue(self.fails(self.make(payload={"skill_name": "with-evals", "evals": [
            {"id": 1, "prompt": "p", "expected_output": "e"},
            {"id": 1, "prompt": "p2", "expected_output": "e2"}]})))

    def test_missing_field_is_flagged(self):
        for field in ("id", "prompt", "expected_output"):
            payload = {"skill_name": "with-evals",
                       "evals": [{"id": 1, "prompt": "p", "expected_output": "e"}]}
            del payload["evals"][0][field]
            self.assertTrue(self.fails(self.make(payload=payload)), f"缺 {field} 应当失败")

    def test_referenced_file_must_exist(self):
        self.assertTrue(self.fails(self.make(payload={"skill_name": "with-evals", "evals": [
            {"id": 1, "prompt": "p", "expected_output": "e",
             "files": ["tests/并没有这个.txt"]}]})))

    def test_existing_referenced_file_passes(self):
        """files 指向真实存在的文件时应当放过；files 整个缺掉也行。"""
        path = self.make()
        os.makedirs(os.path.join(path, "fixtures"), exist_ok=True)
        with open(os.path.join(path, "fixtures/sample.md"), "w", encoding="utf-8") as handle:
            handle.write("样例\n")
        payload = {"skill_name": "with-evals", "evals": [
            {"id": 1, "prompt": "p", "expected_output": "e", "files": ["fixtures/sample.md"]},
            {"id": 2, "prompt": "p", "expected_output": "e"}]}   # files 可以整个缺
        with open(os.path.join(path, "evals/evals.json"), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        self.assertFalse(self.fails(path))

    def test_broken_json_is_flagged(self):
        self.assertTrue(self.fails(self.make(payload="{ 这不是 json")))

    def test_empty_evals_list_is_flagged(self):
        self.assertTrue(self.fails(self.make(payload={"skill_name": "with-evals", "evals": []})))

