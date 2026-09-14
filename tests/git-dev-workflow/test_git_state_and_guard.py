#!/usr/bin/env python3
"""`git_state.py` / `git_guard.py` 的回归测试。

## 夹具为什么是"真建一个仓库"

这两个脚本的输入就是**仓库的真实状态**：脏工作区、只在本地存在的提交、已并入/未并入
的分支、detached HEAD、merge 中间态、目录被删掉的 worktree。用假的 JSON 去喂它们，
测的就不是它们了。

所以每个用例在 `tempfile` 里 `git init` 一个真仓库，用真的 `git` 造出那个状态。
慢一点（每个用例几十毫秒），但这是唯一能验到判据的办法。

## 夹具在 `_fixtures.py`

真建仓库这件事三个测试文件都要用，所以抽成一份 —— 复制三份的结果必然是其中两份忘了改。
环境隔离（`GIT_*` 先清掉、全局配置指向 /dev/null）也写在那里，理由在那边。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# 测试住在仓库顶层 `tests/<skill>/`（**刻意不在 skill 目录里**：AI 调用 skill 时读的是
# `skills/<skill>/` 那棵树，测试放在里面会被顺手读进去）。
# 所以从 `tests/<skill>/` 往上两级到仓库根，再进 `skills/<skill>/`。
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")


def _load(name: str, path: str):
    """按显式路径加载同目录模块（先注册 sys.modules 再 exec）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


STATE = _load("git_state", os.path.join(SCRIPTS, "git_state.py"))
GUARD = _load("git_guard", os.path.join(SCRIPTS, "git_guard.py"))
WORKTREE = _load("worktree", os.path.join(SCRIPTS, "worktree.py"))
REPORT = _load("git_report", os.path.join(SCRIPTS, "git_report.py"))
PLAN = _load("commit_plan", os.path.join(SCRIPTS, "commit_plan.py"))


# ── 夹具 ──────────────────────────────────────────────────────────────────
#
# 这段在三个测试文件里**故意各留一份**，没有抽成共用模块：抽出去之后基类变成运行时
# 对象，静态分析就看不见 `state()` / `guard()` 这些继承来的方法，会报一屏
# “Cannot access attribute”。本仓其它测试文件也是各自定义夹具 —— 不是懒，
# 是让检查器看得见。真建仓库这件事本身的说明在下面这段 docstring 里。
class Repo:
    """一个临时建出来的真仓库。"""

    def __init__(self, path: str):
        self.path = path

    def git(self, *args: str) -> str:
        proc = subprocess.run(["git", "-C", self.path, *args],
                              capture_output=True, text=True, check=False)
        # merge / checkout 允许失败（用例就是要制造冲突与中间态）
        if proc.returncode != 0 and args[:1] not in (("merge",), ("checkout",)):
            raise AssertionError(f"git {' '.join(args)} 失败：{proc.stderr.strip()}")
        return proc.stdout

    def write(self, relpath: str, text: str = "x\n") -> str:
        full = os.path.join(self.path, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text)
        return full

    def commit(self, message: str, relpath: str = "a.txt") -> str:
        self.write(relpath, message + "\n")
        self.git("add", "-A")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def add_remote(self, name: str = "origin") -> str:
        bare = tempfile.mkdtemp(prefix="gitdev-remote-")
        subprocess.run(["git", "init", "--bare", "-b", "main", bare],
                       capture_output=True, text=True, check=True)
        self.git("remote", "add", name, bare)
        return bare


class RepoCase(unittest.TestCase):
    """建/拆一个仓库，隔离 git 环境，并提供跑脚本的帮手。"""

    def setUp(self):
        self._saved_env = dict(os.environ)
        # 先清场：钩子（比如 pre-commit）跑测试时会带着 GIT_DIR / GIT_INDEX_FILE
        # 这类变量进来，它们会泄进夹具里的临时仓库 —— 表现出来就是同一个用例
        # “手动跑过、在钩子里挂”。实测：只带一个 GIT_DIR，一半用例失败。
        for name in [k for k in os.environ if k.startswith("GIT_")]:
            os.environ.pop(name, None)
        os.environ.update({
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
        })
        self.tmp = tempfile.mkdtemp(prefix="gitdev-test-")
        subprocess.run(["git", "init", "-b", "main", self.tmp],
                       capture_output=True, text=True, check=True)
        self.repo = Repo(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        # 同级的 worktree（create 建的）也要一起清，不然 /tmp 里会攒东西
        for suffix in ("-feat-x", "-feat-a", "-side"):
            shutil.rmtree(self.tmp + suffix, ignore_errors=True)
        os.environ.clear()
        os.environ.update(self._saved_env)

    # ── 帮手：跑脚本、取状态 ───────────────────────────────────────────────
    def state(self) -> dict:
        return STATE.snapshot(self.repo.path)

    def cli(self, module, *argv: str) -> tuple[int, str]:
        """跑一个脚本的 main()，把 stdout / stderr 一起收下来。"""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = module.main(list(argv))
        return code, buffer.getvalue()

    def guard(self, action: str, *extra: str) -> tuple[int, dict]:
        """跑一次 guard，返回 (退出码, JSON 结论)。"""
        code, output = self.cli(GUARD, action, *extra, "--repo", self.repo.path,
                                "--json")
        return code, json.loads(output)


# ── git_state ─────────────────────────────────────────────────────────────
class TestState(RepoCase):
    def test_clean_repo_reports_clean(self):
        self.repo.commit("一")
        state = self.state()
        self.assertTrue(state["is_repo"])
        self.assertEqual(0, state["dirty"]["total"])
        self.assertEqual("main", state["branch"]["branch"])
        self.assertEqual("main", state["branch"]["baseline"])
        self.assertFalse(state["branch"]["in_worktree"])

    def test_without_a_remote_every_commit_is_local_only(self):
        """没有远端时「未推送」= 全部提交 —— 这是**保守但正确**的读法。

        它和下一个用例（没有上游 → ahead 是 None）不是同一件事：那一条是
        「问不出来」，这一条是「问出来了，而答案就是全部」。混为一谈会让 guard
        在该拦的时候放行。
        """
        self.repo.commit("一")
        self.repo.commit("二")
        state = self.state()
        self.assertFalse(state["unpushed"]["has_remote"])
        self.assertEqual(2, state["unpushed"]["count"])
        self.assertIn("没有任何远端", state["unpushed"]["note"])

    def test_no_upstream_is_not_zero(self):
        """没有上游时 ahead/behind **是 None，不是 0** —— 这两件事意思完全不同。"""
        self.repo.commit("一")
        state = self.state()
        self.assertEqual("", state["upstream"]["upstream"])
        self.assertIsNone(state["upstream"]["ahead"])
        self.assertIn("无从谈起", state["upstream"]["note"])

    def test_unpushed_counts_only_local_commits(self):
        """这条同时钉住 `--not --remotes` 的**参数顺序**：ref 必须写在 --not 之前。

        写成 `--not --remotes HEAD` 时 `--not` 会把 HEAD 也一起否定掉，结果是空 ——
        而且不报错。踩过一次。
        """
        self.repo.add_remote()
        self.repo.commit("一")
        self.repo.git("push", "-u", "origin", "main")
        self.assertEqual(0, self.state()["unpushed"]["count"])

        self.repo.commit("二")
        state = self.state()
        self.assertEqual(1, state["unpushed"]["count"])
        self.assertEqual(["二"], [s.split(" ", 1)[1] for s in state["unpushed"]["subjects"]])

    def test_detached_head_is_reported(self):
        first = self.repo.commit("一")
        self.repo.commit("二")
        self.repo.git("checkout", "--detach", first)
        state = self.state()
        self.assertFalse(state["branch"]["branch"])
        self.assertTrue(state["branch"]["detached"])

    def test_untracked_secret_is_surfaced(self):
        self.repo.commit("一")
        self.repo.write(".env.local", "TOKEN=1\n")
        state = self.state()
        self.assertEqual(1, state["dirty"]["by_kind"].get("secret", 0))
        self.assertEqual([".env.local"], [e["path"] for e in state["dirty"]["protected"]])

    def test_ignored_secret_is_surfaced_too(self):
        """被 .gitignore 挡住的凭据**不在版本库里** —— 它们被删掉就是真的没了。

        所以不能只数「被挡住多少项」：得把像凭据的那些单独报出来。
        """
        self.repo.write(".gitignore", ".env\n")
        self.repo.commit("一", relpath="a.txt")
        self.repo.write(".env", "SECRET=1\n")
        state = self.state()
        self.assertEqual(1, state["ignored_count"])
        self.assertEqual([".env"], [e["path"] for e in state["ignored_protected"]])

    def test_artifact_and_source_are_classified_apart(self):
        self.repo.commit("一")
        self.repo.write("dist/bundle.js", "build\n")
        self.repo.write("src/app.py", "print(1)\n")
        kinds = self.state()["dirty"]["by_kind"]
        self.assertEqual(1, kinds.get("artifact", 0))
        self.assertEqual(1, kinds.get("source", 0))

    def test_merge_conflict_is_a_mid_operation(self):
        self.repo.commit("一", relpath="a.txt")
        self.repo.git("checkout", "-b", "other")
        self.repo.commit("二", relpath="a.txt")
        self.repo.git("checkout", "main")
        self.repo.commit("三", relpath="a.txt")
        self.repo.git("merge", "other")                       # 会冲突
        state = self.state()
        self.assertIn("merge", state["mid_operation"])
        with contextlib.redirect_stdout(io.StringIO()):
            code = STATE.main(["--repo", self.repo.path])
        self.assertEqual(2, code, "中间态必须用退出码 2 说出来")

    def test_worktree_with_missing_directory_is_flagged(self):
        """目录被人删掉的 worktree：`exists=False` + `prunable` —— 这正是现实里那一个。"""
        self.repo.commit("一")
        branch_dir = os.path.join(self.tmp + "-wt")
        self.repo.git("worktree", "add", "-b", "side", branch_dir)
        shutil.rmtree(branch_dir, ignore_errors=True)
        item = [w for w in self.state()["worktrees"] if w["branch"] == "side"][0]
        self.assertFalse(item["exists"])
        self.assertTrue(item["prunable"])

    def test_not_a_repo_exits_one(self):
        empty = tempfile.mkdtemp(prefix="gitdev-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        self.assertFalse(STATE.snapshot(empty)["is_repo"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, STATE.main(["--repo", empty]))


# ── git_guard ─────────────────────────────────────────────────────────────
class TestGuardDiscard(RepoCase):
    def test_source_file_blocks(self):
        self.repo.commit("一")
        self.repo.write("src/app.py")
        code, verdict = self.guard("discard-worktree")
        self.assertEqual(GUARD.BLOCK, code)
        self.assertEqual("BLOCK", verdict["level"])
        self.assertTrue(any("不是构建产物" in r for r in verdict["reasons"]))
        self.assertIn("src/app.py", " ".join(verdict["evidence"]))

    def test_only_artifacts_warns_not_blocks(self):
        """**分档要准**：构建产物能重新生成 → WARN；混进源码才是 BLOCK。"""
        self.repo.commit("一")
        self.repo.write("dist/bundle.js")
        code, verdict = self.guard("discard-worktree")
        self.assertEqual(GUARD.WARN, code)
        self.assertEqual("WARN", verdict["level"])

    def test_clean_repo_is_safe(self):
        self.repo.commit("一")
        code, verdict = self.guard("discard-worktree")
        self.assertEqual(GUARD.SAFE, code)
        self.assertIn("工作区是干净的", " ".join(verdict["evidence"]))


class TestGuardClean(RepoCase):
    def test_untracked_source_blocks(self):
        self.repo.commit("一")
        self.repo.write("notes.md")
        code, verdict = self.guard("clean-untracked")
        self.assertEqual(GUARD.BLOCK, code)
        self.assertTrue(any("未跟踪不等于没用" in r for r in verdict["reasons"]))

    def test_clean_x_with_ignored_secret_blocks(self):
        """`-x` 会删掉 .gitignore 挡住的东西，而 `.env` 正躺在那里 —— 那不是"产物"。"""
        self.repo.write(".gitignore", ".env\n")
        self.repo.commit("一", relpath="a.txt")
        self.repo.write(".env", "SECRET=1\n")
        code, verdict = self.guard("clean-untracked", "--include-ignored")
        self.assertEqual(GUARD.BLOCK, code)
        self.assertTrue(any("不在版本库里" in r for r in verdict["reasons"]))


class TestGuardBranch(RepoCase):
    def test_delete_merged_branch_is_safe(self):
        self.repo.commit("一")
        self.repo.git("branch", "side")
        code, _ = self.guard("delete-branch", "side")
        self.assertEqual(GUARD.SAFE, code)

    def test_delete_unmerged_branch_with_local_only_commits_blocks(self):
        self.repo.commit("一")
        self.repo.git("checkout", "-b", "side")
        self.repo.commit("只在这里", relpath="b.txt")
        self.repo.git("checkout", "main")
        code, verdict = self.guard("delete-branch", "side")
        self.assertEqual(GUARD.BLOCK, code)
        self.assertTrue(any("只存在于这一条分支上" in r for r in verdict["reasons"]))

    def test_delete_current_branch_blocks(self):
        self.repo.commit("一")
        code, verdict = self.guard("delete-branch", "main")
        self.assertEqual(GUARD.BLOCK, code)
        self.assertTrue(any("当前分支" in r for r in verdict["reasons"]))

    def test_missing_branch_blocks(self):
        self.repo.commit("一")
        code, verdict = self.guard("delete-branch", "并没有这个分支")
        self.assertEqual(GUARD.BLOCK, code)
        self.assertTrue(any("没有名为" in r for r in verdict["reasons"]))


class TestGuardWorktree(RepoCase):
    def test_worktree_with_missing_directory_is_safe_to_prune(self):
        self.repo.commit("一")
        branch_dir = self.tmp + "-wt2"
        self.repo.git("worktree", "add", "-b", "side", branch_dir)
        shutil.rmtree(branch_dir, ignore_errors=True)
        code, verdict = self.guard("delete-worktree", branch_dir)
        self.assertEqual(GUARD.SAFE, code)
        self.assertIn("git worktree prune", verdict["command"])

    def test_worktree_with_uncommitted_changes_blocks(self):
        self.repo.commit("一")
        branch_dir = self.tmp + "-wt3"
        self.repo.git("worktree", "add", "-b", "side", branch_dir)
        self.addCleanup(shutil.rmtree, branch_dir, ignore_errors=True)
        with open(os.path.join(branch_dir, "dirty.txt"), "w", encoding="utf-8") as handle:
            handle.write("x\n")
        code, verdict = self.guard("delete-worktree", branch_dir)
        self.assertEqual(GUARD.BLOCK, code)
        self.assertTrue(any("未提交" in r for r in verdict["reasons"]))


class TestGuardHooks(RepoCase):
    def test_bypass_blocks_when_a_hook_is_installed(self):
        self.repo.commit("一")
        hooks = os.path.join(self.repo.path, ".git", "hooks")
        hook = os.path.join(hooks, "pre-commit")
        with open(hook, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\nexit 0\n")
        os.chmod(hook, 0o755)
        code, verdict = self.guard("bypass-hooks")
        self.assertEqual(GUARD.BLOCK, code)
        self.assertIn("pre-commit", " ".join(verdict["evidence"]))

    def test_bypass_is_safe_when_there_are_no_hooks(self):
        self.repo.commit("一")
        code, _ = self.guard("bypass-hooks")
        self.assertEqual(GUARD.SAFE, code)

    def test_core_hooksPath_is_honoured(self):
        """用户的两个仓库就是用 `core.hooksPath` 指到 `.githooks/` 的。"""
        self.repo.commit("一")
        hooks = os.path.join(self.repo.path, ".githooks")
        os.makedirs(hooks, exist_ok=True)
        hook = os.path.join(hooks, "pre-commit")
        with open(hook, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\nexit 0\n")
        os.chmod(hook, 0o755)
        self.repo.git("config", "core.hooksPath", ".githooks")
        code, _ = self.guard("bypass-hooks")
        self.assertEqual(GUARD.BLOCK, code)


class TestGuardPushAndRewrite(RepoCase):
    def test_force_push_baseline_blocks(self):
        self.repo.commit("一")
        code, verdict = self.guard("force-push", "--branch", "main")
        self.assertEqual(GUARD.BLOCK, code)
        self.assertTrue(any("基线分支" in r for r in verdict["reasons"]))

    def test_force_push_with_unknown_remote_state_blocks(self):
        """拿不到远端状态时**按最坏处理**，不是"应该没事"。"""
        self.repo.commit("一")
        self.repo.git("branch", "feature")
        code, verdict = self.guard("force-push", "--branch", "feature")
        self.assertEqual(GUARD.BLOCK, code)
        self.assertTrue(any("按最坏处理" in r for r in verdict["reasons"]))

    def test_rewrite_blocks_when_the_tip_is_on_a_remote(self):
        self.repo.add_remote()
        self.repo.commit("一")
        self.repo.git("push", "-u", "origin", "main")
        code, verdict = self.guard("rewrite-history")
        self.assertEqual(GUARD.BLOCK, code)
        self.assertTrue(any("已经在远端" in r for r in verdict["reasons"]))

    def test_rewrite_escape_hatch_downgrades_to_warn(self):
        """`--shared` 是**显式**声明；用了它必须能在结论里看到这个声明。"""
        self.repo.add_remote()
        self.repo.commit("一")
        self.repo.git("push", "-u", "origin", "main")
        code, verdict = self.guard("rewrite-history", "--shared")
        self.assertEqual(GUARD.WARN, code)
        # 逃生阀用了之后，结论里必须看得出「这是显式声明的共享历史改写」——
        # 否则报告里就成了一次普通的本地清理，而那不是实际发生的事。
        self.assertIn("--shared", verdict["caveat"])
        self.assertIn("共享历史", verdict["caveat"])
        self.assertTrue(any("共享历史" in r for r in verdict["reasons"]))

    def test_rewrite_is_safe_on_a_local_only_clean_repo(self):
        """纯粹本地、工作区干净的历史改写：真没有别人会受影响 → SAFE。

        这里不是“改写历史很危险所以至少 WARN”—— 判据说的是**会不会影响到别人**，
        而不是“这个动作听起来吓人”。分档要跟判据走，不跟感觉走。
        """
        self.repo.commit("一")
        code, _ = self.guard("rewrite-history")
        self.assertEqual(GUARD.SAFE, code)

    def test_rewrite_warns_on_a_dirty_tree(self):
        """工作区不干净时改写历史会把未提交的改动卷进冲突 —— 不阻塞，但要说出来。"""
        self.repo.commit("一")
        self.repo.write("src/app.py")
        code, verdict = self.guard("rewrite-history")
        self.assertEqual(GUARD.WARN, code)
        self.assertTrue(any("不干净" in r for r in verdict["reasons"]))


class TestGuardMidOperation(RepoCase):
    def test_everything_blocks_during_a_merge(self):
        """中间态下一律先拦：这些命令在 rebase/merge 没结束时含义和平时不一样。"""
        self.repo.commit("一", relpath="a.txt")
        self.repo.git("checkout", "-b", "other")
        self.repo.commit("二", relpath="a.txt")
        self.repo.git("checkout", "main")
        self.repo.commit("三", relpath="a.txt")
        self.repo.git("merge", "other")
        for action in ("discard-worktree", "clean-untracked", "delete-branch"):
            with self.subTest(action=action):
                code, verdict = self.guard(action, "main")
                self.assertEqual(GUARD.BLOCK, code)
                self.assertTrue(any("先结束或中止" in r for r in verdict["reasons"]))


class TestUnknownAction(RepoCase):
    def test_unknown_action_blocks_and_lists_the_real_ones(self):
        self.repo.commit("一")
        code, verdict = self.guard("git-reset-please")
        self.assertEqual(GUARD.BLOCK, code)
        self.assertIn("clean-untracked", verdict["reasons"][0])


# ── worktree ──────────────────────────────────────────────────────────
class WorktreeCase(RepoCase):
    def wt(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = WORKTREE.main([*argv, "--repo", self.repo.path])
        return code, buffer.getvalue()

    def beside(self, branch: str) -> str:
        return WORKTREE.target_path(self.repo.path, branch)


class TestWorktreePlacement(WorktreeCase):
    def test_create_puts_it_beside_the_repo(self):
        """放置约定（已拍板）：**仓库同级**。

        这条用例是那个约定的看门人 —— 换位置就得改这里，而改的时候会看到为什么：
        同级意味着在仓库之外，不用改 .gitignore、`git status` 也看不见它。
        """
        self.repo.commit("一")
        target = self.beside("feat/x")
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        code, output = self.wt("create", "feat/x")
        self.assertEqual(0, code, output)
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(os.path.dirname(os.path.abspath(self.repo.path)),
                         os.path.dirname(target))
        self.assertEqual("feat/x", WORKTREE.S.run_git(
            target, "branch", "--show-current")[1].strip())

    def test_slug_flattens_slashes(self):
        self.assertEqual("feat-ui-shadcn", WORKTREE.slug_for("feat/ui-shadcn"))
        self.assertEqual("hotfix-1", WORKTREE.slug_for("hotfix/1"))
        self.assertTrue(WORKTREE.slug_for("///"), "极端输入也要出一个能当目录名的结果")

    def test_create_refuses_when_the_branch_exists(self):
        self.repo.commit("一")
        self.repo.git("branch", "feat/x")
        code, output = self.wt("create", "feat/x")
        self.assertEqual(1, code)
        self.assertIn("已经有分支", output)

    def test_create_refuses_when_the_target_exists(self):
        self.repo.commit("一")
        target = self.beside("feat/x")
        os.makedirs(target, exist_ok=True)
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        code, output = self.wt("create", "feat/x")
        self.assertEqual(1, code)
        self.assertIn("已经存在", output)

    def test_create_refuses_when_the_sibling_is_inside_another_repo(self):
        """同级目录落在**另一个**仓库里的话，那个仓库会把新目录当成未跟踪内容收进去。"""
        outer = tempfile.mkdtemp(prefix="gitdev-outer-")
        self.addCleanup(shutil.rmtree, outer, ignore_errors=True)
        subprocess.run(["git", "init", "-b", "main", outer],
                       capture_output=True, text=True, check=True)
        inner = os.path.join(outer, "inner")
        subprocess.run(["git", "init", "-b", "main", inner],
                       capture_output=True, text=True, check=True)
        clone = Repo(inner)
        clone.git("commit", "--allow-empty", "-m", "一")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = WORKTREE.main(["create", "feat/x", "--repo", inner])
        self.assertEqual(1, code)
        self.assertIn("另一个 git 仓库", buffer.getvalue())


class TestWorktreeLifecycle(WorktreeCase):
    def test_prune_clears_records_whose_directory_is_gone(self):
        self.repo.commit("一")
        self.wt("create", "feat/x")
        shutil.rmtree(self.beside("feat/x"), ignore_errors=True)
        self.assertEqual(2, len(STATE.snapshot(self.repo.path)["worktrees"]))
        code, output = self.wt("prune")
        self.assertEqual(0, code, output)
        self.assertEqual(1, len(STATE.snapshot(self.repo.path)["worktrees"]))

    def test_remove_refuses_while_there_are_uncommitted_changes(self):
        self.repo.commit("一")
        self.wt("create", "feat/x")
        target = self.beside("feat/x")
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        with open(os.path.join(target, "dirty.txt"), "w", encoding="utf-8") as handle:
            handle.write("x\n")
        code, output = self.wt("remove", target)
        self.assertEqual(GUARD.BLOCK, code)
        self.assertIn("只存在于那个目录里", output)   # 真正的损失是未提交的改动
        self.assertTrue(os.path.isdir(target), "被拒绝时不许动它")

    def test_remove_works_when_clean_and_merged(self):
        self.repo.commit("一")
        self.wt("create", "feat/x")
        target = self.beside("feat/x")
        code, output = self.wt("remove", target)
        self.assertEqual(0, code, output)
        self.assertFalse(os.path.isdir(target))
        # 回收 worktree 不该顺手删分支 —— 那是另一件事，另一道判据
        self.assertIn("feat/x", self.repo.git("branch", "--format=%(refname:short)"))

    def test_repo_option_works_after_the_subcommand(self):
        """回归：`--repo` 曾经只能写在子命令前面，写在后面会被 argparse 拒掉。

        人两个位置都会写（我自己第一次就是这么跑的），所以两边都得认。
        """
        self.repo.commit("一")
        code, output = self.wt("list")
        self.assertEqual(0, code)
        self.assertIn(self.repo.path, output)

    def test_list_stale_hides_healthy_worktrees(self):
        self.repo.commit("一")
        self.wt("create", "feat/x")
        target = self.beside("feat/x")
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        with open(os.path.join(target, "dirty.txt"), "w", encoding="utf-8") as handle:
            handle.write("x\n")
        code, output = self.wt("list", "--stale")
        self.assertEqual(0, code)
        self.assertNotIn("feat/x", output, "有未提交的不算可回收")


if __name__ == "__main__":
    unittest.main()


# ── git_report ────────────────────────────────────────────────────────────
class ReportCase(RepoCase):
    def report(self, *argv: str) -> tuple[int, str]:
        return self.cli(REPORT, *argv, "--repo", self.repo.path)


class TestReport(ReportCase):
    def test_capture_then_unchanged(self):
        self.repo.commit("一")
        code, output = self.report("--capture")
        self.assertEqual(0, code, output)
        self.assertIn("快照已存", output)
        code, output = self.report()
        self.assertEqual(0, code)
        self.assertIn("没变", output)

    def test_new_commit_shows_up(self):
        self.repo.commit("一")
        self.report("--capture")
        self.repo.commit("二", relpath="b.txt")
        code, output = self.report()
        self.assertEqual(0, code)
        self.assertIn("新增 1 条提交", output)
        self.assertIn("二", output)

    def test_lost_commit_is_flagged(self):
        """提交“消失了”要单独标出来 —— 那是 reflog 能救、但必须先知道的事。

        顺序要紧：先在「二」的位置 capture，再 reset 回「一」——
        这样「二」才是"之前可达、现在不可达"。
        """
        self.repo.commit("一")
        first = self.repo.git("rev-parse", "HEAD").strip()
        self.repo.commit("二", relpath="b.txt")
        self.report("--capture")
        self.repo.git("reset", "--hard", first)
        code, output = self.report()
        self.assertEqual(0, code)
        self.assertIn("消失了", output)
        self.assertIn("二", output)

    def test_missing_snapshot_says_capture_first(self):
        self.repo.commit("一")
        code, output = self.report()
        self.assertEqual(1, code)
        self.assertIn("--capture", output)

    def test_snapshot_from_another_repo_is_refused(self):
        self.repo.commit("一")
        other = tempfile.mkdtemp(prefix="gitdev-other-")
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        subprocess.run(["git", "init", "-b", "main", other],
                       capture_output=True, text=True, check=True)
        elsewhere = os.path.join(other, "snap.json")
        code, _ = self.cli(REPORT, "--capture", "--file", elsewhere, "--repo", other)
        self.assertEqual(0, code)
        code, output = self.report("--file", elsewhere)
        self.assertEqual(1, code)
        self.assertIn("另一个仓库", output)

    def test_raw_block_has_commands_and_real_output(self):
        """粘贴块必须是「命令 + 原始输出」—— 那才是报告里该出现的东西。"""
        self.repo.commit("一")
        self.report("--capture")            # 报告要先有快照比，不然它是拒绝跑的
        code, output = self.report()
        self.assertEqual(0, code)
        self.assertIn("$ git rev-parse --short HEAD", output)
        self.assertIn(self.repo.git("rev-parse", "--short", "HEAD").strip(), output)
        self.assertIn("$ git status --porcelain", output)
        self.assertIn("$ git stash list", output)

    def test_json_is_machine_readable(self):
        self.repo.commit("一")
        self.report("--capture")
        self.repo.write("src/app.py")
        code, output = self.report("--json")
        self.assertEqual(0, code)
        payload = json.loads(output)
        self.assertEqual(0, payload["before"]["dirty_total"])
        self.assertEqual(1, payload["after"]["dirty_total"])


# ── commit_plan ───────────────────────────────────────────────────────────
class PlanCase(RepoCase):
    def plan(self, *argv: str) -> tuple[int, dict]:
        code, output = self.cli(PLAN, *argv, "--repo", self.repo.path, "--json")
        return code, json.loads(output) if output.strip().startswith("{") else {}

    def groups_of(self, result: dict) -> dict:
        return {group["kind"] if group["kind"] != "normal" else group["label"]: group
                for group in result["groups"]}


class TestPlanGroups(PlanCase):
    def test_secret_is_its_own_group_and_nowhere_else(self):
        """**硬规矩**：疑似凭据单独成组，且不出现在任何别的组里 —— 它是提交前最该看的。"""
        self.repo.commit("一")
        self.repo.write(".env.local", "TOKEN=1\n")
        self.repo.write("src/app.py")
        _, result = self.plan()
        secret = [g for g in result["groups"] if g["kind"] == "secret"]
        self.assertEqual(1, len(secret))
        self.assertEqual([".env.local"], secret[0]["files"])
        others = [path for g in result["groups"] if g["kind"] != "secret"
                  for path in g["files"]]
        self.assertNotIn(".env.local", others, "凭据混进别的组就等于会被顺手提交")

    def test_every_group_has_an_add_command(self):
        self.repo.commit("一")
        self.repo.write("src/app.py")
        self.repo.write("docs/readme.md")
        _, result = self.plan()
        self.assertTrue(result["groups"])
        for group in result["groups"]:
            self.assertTrue(group["add_command"].startswith("git add -- "))

    def test_clean_tree_says_there_is_nothing(self):
        self.repo.commit("一")
        code, output = self.cli(PLAN, "--repo", self.repo.path)
        self.assertEqual(0, code)
        self.assertIn("干净", output)

    def test_untracked_file_reports_its_line_count(self):
        self.repo.commit("一")
        self.repo.write("src/app.py", "one\ntwo\nthree\n")
        _, result = self.plan()
        found = [group["untracked_lines"] for group in result["groups"]
                 if group["untracked_lines"]]
        self.assertTrue(found)
        self.assertEqual("3 行", found[0]["src/app.py"])


class TestPrefixRule(PlanCase):
    """前缀规则是纯函数，直接测规则本身。"""

    def test_all_tests_gets_test(self):
        prefix, _ = PLAN.candidate_prefix(["tests/test_a.py", "tests/test_b.py"], {"M"})
        self.assertEqual("test", prefix)

    def test_mixed_group_must_not_be_called_test(self):
        """回归：规则曾经用 `any`，一组 scripts + tests 被报成 test —— 源码改动被盖住。

        候选前缀存在的意义就是「你能一眼反驳它」，指向错的东西比不指更糟。
        """
        prefix, reason = PLAN.candidate_prefix(["tests/test_a.py", "scripts/x.py"], {"M"})
        self.assertEqual("", prefix)
        self.assertIn("需要你定", reason)
        self.assertIn("含测试文件", reason)

    def test_docs_ci_build_and_delete_only(self):
        self.assertEqual("docs", PLAN.candidate_prefix(["a.md", "b.md"], {"M"})[0])
        self.assertEqual("ci", PLAN.candidate_prefix([".github/workflows/ci.yml"], {"M"})[0])
        self.assertEqual("build",
                         PLAN.candidate_prefix(["Dockerfile", "docker-compose.yml"], {"M"})[0])
        self.assertEqual("chore", PLAN.candidate_prefix(["src/old.py"], {"D"})[0])

    def test_source_only_says_you_decide(self):
        prefix, reason = PLAN.candidate_prefix(["src/app.py"], {"M"})
        self.assertEqual("", prefix)
        self.assertIn("需要你定", reason)


# ── stash 回收判据 ────────────────────────────────────────────────────────
class TestGuardStash(RepoCase):
    def stash_something(self, relpath: str, text: str) -> None:
        self.repo.write(relpath, text)
        self.repo.git("add", "-A")
        self.repo.git("stash", "push", "-m", "待处理")

    def test_stash_content_nowhere_else_warns(self):
        """回归：`git log --all` 把 refs/stash 也算进去 → stash 匹配到它自己。

        症状是「drop-stash 对任何非空 stash 都给 SAFE」，那条 WARN 分支成了死代码。
        实测：stash 的 patch-id 原样出现在 `--all` 的扫描结果里。
        """
        self.repo.commit("一")
        self.stash_something("brand-new.txt", "只在 stash 里\n")
        code, output = self.cli(GUARD, "drop-stash", "stash@{0}", "--repo", self.repo.path)
        self.assertEqual(3, code, output)
        self.assertIn("找不到", output)

    def test_stash_content_already_committed_is_safe(self):
        """反向：同样的改动已经在提交里 —— 那才是这条判据存在的意义。"""
        self.repo.commit("一")
        self.stash_something("brand-new.txt", "内容\n")
        self.repo.git("stash", "apply")
        self.repo.git("add", "-A")
        self.repo.git("commit", "-m", "二")
        code, output = self.cli(GUARD, "drop-stash", "stash@{0}", "--repo", self.repo.path)
        self.assertEqual(0, code, output)
        self.assertIn("已经在提交", output)


# ── 基线分支不能当普通分支删 ──────────────────────────────────────────────
class TestGuardBaseline(RepoCase):
    def test_baseline_branch_delete_is_blocked(self):
        """回归：站在别的分支上删基线分支时曾给 SAFE，还递上 `git branch -D main`。

        两件事让它必须拦：主干上的提交可能只被它指着；而且删掉它之后，
        这个工具所有「已并入基线」的判断都没有参照了。
        """
        self.repo.commit("一")
        self.repo.git("checkout", "-b", "feature")
        code, output = self.cli(GUARD, "delete-branch", "main", "--repo", self.repo.path)
        self.assertEqual(4, code, output)
        self.assertIn("基线分支", output)

    def test_ordinary_merged_branch_still_gets_safe(self):
        """反向：普通分支该 SAFE 还是 SAFE —— 别顺手把范围放大。"""
        self.repo.commit("一")
        self.repo.git("branch", "helper")
        code, output = self.cli(GUARD, "delete-branch", "helper", "--repo", self.repo.path)
        self.assertEqual(0, code, output)


# ── prune 的报告必须和条目数一致 ───────────────────────────────────────────
class TestWorktreePrune(WorktreeCase):
    def test_prune_report_matches_the_count(self):
        """回归：`git worktree prune -v` 实测会**静默**清记录（输出为空）。

        照它的输出判，就会在同一屏上说「没有可以清理的记录」和「条目：2 → 1」。
        """
        self.repo.commit("一")
        target = self.beside("feat/gone")
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        code, output = self.wt("create", "feat/gone")
        self.assertEqual(0, code, output)
        shutil.rmtree(target)                 # 目录被手删了 → 记录还在，可 prune
        code, output = self.wt("prune")
        self.assertEqual(0, code, output)
        self.assertIn("2 → 1", output)
        self.assertIn("清理掉的记录", output)
        self.assertNotIn("没有可以清理的记录", output)


# ── 去重缓存的边界：它只活一次读取 ─────────────────────────────────────────
class TestCacheFreshness(RepoCase):
    def test_second_snapshot_in_the_same_process_is_fresh(self):
        """回归：去重缓存**只活一次快照** —— snapshot() 开头必须清它。

        这条是承重的那条。变异测试验证过：把 snapshot() 开头那句 clear_cache()
        去掉，这里就会失败（第二次快照拿的是第一次的状态）。盯的三件事都是会被
        缓存的：工作区条目、短 HEAD、已并入基线的分支集合。
        """
        self.repo.commit("一")
        first = self.state()
        self.assertEqual(0, first["dirty"]["total"])
        # main 已并入它自己 —— 批量实现就是这么定义的（旧实现同义）
        self.assertEqual(["main"], [b["name"] for b in first["branches"] if b["merged"]])

        # 提交在前、写文件在后：夹具的 commit() 会把未跟踪文件一起收进去
        # （和 E2E 脚本那次同一个坑），写在前面的话这个文件已经被提交了。
        self.repo.commit("二", relpath="b.txt")
        self.repo.write("new.txt", "新的\n")

        second = self.state()
        self.assertEqual(1, second["dirty"]["total"], "第二次快照必须看到刚写的文件")
        self.assertNotEqual(first["branch"]["head"], second["branch"]["head"],
                            "短 HEAD 必须跟着新提交变（它也是被缓存的那批事实之一）")

    def test_no_stale_facts_after_the_repo_changes(self):
        """同上，换个朝向：缓存里的「哪些分支已并入基线」也必须跟着变。"""
        self.repo.commit("一")
        self.repo.git("checkout", "-b", "work")
        self.repo.commit("二", relpath="b.txt")
        self.repo.git("checkout", "main")
        merged = {b["name"]: b["merged"] for b in self.state()["branches"]}
        self.assertIs(False, merged["work"])
        self.repo.git("merge", "--no-ff", "-m", "merge: 并入 work", "work")
        merged = {b["name"]: b["merged"] for b in self.state()["branches"]}
        self.assertIs(True, merged["work"], "并入之后不能还报「未并入」")


# ── 批量实现 vs 参考实现 ───────────────────────────────────────────────────
class TestBatchMergedMatchesTheReference(RepoCase):
    """`for-each-ref --merged=<基线>` 是批量实现，`merge-base --is-ancestor` 是参考实现。

    换实现最怕「结论悄悄变了」，所以拿参考实现逐分支比一遍 —— 只要有一个分支答案
    不同，这条就失败。（本仓用过同样的做法：给快路径加精确否定，语义一字不变。）
    """

    def merged_by_reference(self, name: str, baseline: str) -> bool:
        return subprocess.run(
            ["git", "-C", self.repo.path, "merge-base", "--is-ancestor", name, baseline],
            capture_output=True, text=True).returncode == 0

    def test_same_answer_for_every_branch(self):
        self.repo.commit("一")
        self.repo.git("branch", "merged-a")
        self.repo.git("branch", "merged-b")
        self.repo.git("checkout", "-b", "side")
        self.repo.commit("二", relpath="b.txt")
        self.repo.git("checkout", "main")
        self.repo.git("branch", "from-side", "side")     # 指向未并入的提交
        for name in ("main", "merged-a", "merged-b", "side", "from-side"):
            self.assertEqual(self.merged_by_reference(name, "main"),
                             STATE.merged_into(self.repo.path, name, "main"),
                             f"{name}：批量实现和参考实现结论不一致")

    def test_missing_baseline_is_still_none(self):
        """基线不存在时必须是 None（不是 False）—— 这个约定不能因为换实现丢掉。"""
        self.repo.commit("一")
        self.assertIsNone(STATE.merged_into(self.repo.path, "main", "并没有这个基线"))
        self.assertIsNone(STATE.merged_into(self.repo.path, "main", ""))


# ── 子进程预算 ─────────────────────────────────────────────────────────────
class TestSnapshotBudget(RepoCase):
    """一次快照的子进程数不许涨回去。

    实测（4 分支的仓库）：优化前 46 次 / 492ms，优化后 20 次 / ~300ms。
    卡在 26：如果以后又往判断路径里加「每个分支问一次」「每个 worktree 问一次」
    这种调用，这条会先失败 —— 而不是等使用者发现它变慢了。
    """

    def test_snapshot_stays_within_budget(self):
        self.repo.commit("一")
        for name in ("dev", "feat/x", "feat/y"):
            self.repo.git("branch", name)
        calls: list[list[str]] = []
        real = STATE.subprocess.run

        def counting(*args, **kwargs):
            calls.append(list(args[0]))
            return real(*args, **kwargs)

        STATE.subprocess.run = counting
        try:
            STATE.snapshot(self.repo.path)
        finally:
            STATE.subprocess.run = real
        summary = "\n".join("  " + " ".join(call[:5]) for call in calls)
        self.assertLessEqual(len(calls), 26,
                             f"一次快照发了 {len(calls)} 次 git 子进程：\n{summary}")


# ── 边界：--at 指到仓库里 / 子模块在不在范围内 ────────────────────────────
class TestWorktreeAtInRepo(WorktreeCase):
    def test_target_inside_this_repo_is_refused(self):
        """回归：`--at <本仓库>/sub` 曾被放行，输出还写着「这个目录在仓库之外」。

        落在本仓库工作树里的话，`git status` 会把它当成未跟踪内容收进来、
        `clean -fd` 也会去删它 —— 正是「放仓库同级」要避开的事。
        当时只检查了「落在**别的**仓库里」，同仓库这一支被 `not same_path` 漏掉了。
        """
        self.repo.commit("一")
        inside = os.path.join(self.repo.path, "sub")
        code, output = self.wt("create", "feat/inside", "--at", inside)
        self.assertEqual(1, code, output)
        self.assertIn("本仓库的工作树", output)
        self.assertFalse(os.path.isdir(inside), "被拒绝了就不该留下目录")

    def test_target_inside_git_dir_is_refused(self):
        self.repo.commit("一")
        code, output = self.wt("create", "feat/gitdir", "--at",
                               os.path.join(self.repo.path, ".git", "wt"))
        self.assertEqual(1, code, output)

    def test_default_sibling_still_says_where_it_is(self):
        """默认位置建好之后，报告要说清「在仓库之外」和「这是默认位置」。"""
        self.repo.commit("一")
        target = self.beside("feat/beside")
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        code, output = self.wt("create", "feat/beside")
        self.assertEqual(0, code, output)
        self.assertIn("在仓库之外", output)
        self.assertIn("默认位置", output)


class TestSubmoduleScope(RepoCase):
    def test_submodule_changes_are_out_of_scope_and_said_so(self):
        """子模块里的未提交改动不在这个动作的范围里 —— 报告必须说明。

        不然「丢弃工作区改动」会被读成「顺手也把子模块清了」，而它其实没清。
        """
        source = tempfile.mkdtemp(prefix="gitdev-submodule-")
        self.addCleanup(shutil.rmtree, source, ignore_errors=True)
        subprocess.run(["git", "init", "-b", "main", source],
                       capture_output=True, text=True, check=True)
        with open(os.path.join(source, "lib.txt"), "w", encoding="utf-8") as handle:
            handle.write("库\n")
        for args in (("add", "-A"), ("commit", "-m", "feat: 库的起点")):
            subprocess.run(["git", *args], cwd=source, capture_output=True, check=True)

        self.repo.commit("一")
        added = subprocess.run(
            ["git", "-C", self.repo.path, "-c", "protocol.file.allow=always",
             "submodule", "add", source, "vendor/lib"],
            capture_output=True, text=True)
        if added.returncode != 0:
            self.skipTest(f"这个环境的 git 不允许本地子模块：{added.stderr.strip()[:80]}")

        code, output = self.cli(GUARD, "discard-worktree", "--repo", self.repo.path)
        self.assertIn("子模块", output, f"没说清子模块在不在范围里：{output}")
        self.assertIn("不在它的范围里", output)

