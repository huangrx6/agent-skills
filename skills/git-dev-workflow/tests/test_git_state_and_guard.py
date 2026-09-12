#!/usr/bin/env python3
"""`git_state.py` / `git_guard.py` 的回归测试。

## 夹具为什么是"真建一个仓库"

这两个脚本的输入就是**仓库的真实状态**：脏工作区、只在本地存在的提交、已并入/未并入
的分支、detached HEAD、merge 中间态、目录被删掉的 worktree。用假的 JSON 去喂它们，
测的就不是它们了。

所以每个用例在 `tempfile` 里 `git init` 一个真仓库，用真的 `git` 造出那个状态。
慢一点（每个用例几十毫秒），但这是唯一能验到判据的办法。

## 环境是干净的

`GIT_CONFIG_GLOBAL` / `GIT_CONFIG_SYSTEM` 都指向 `/dev/null`：本机全局配置
（比如 `core.hooksPath`、`filter.lfs.required`）不会渗进夹具，不然用例会随机器而变。

`GIT_*` 开头的环境变量全部先清掉：钩子在 `git commit` 期间跑测试时会带进来
`GIT_DIR` / `GIT_INDEX_FILE` 这类变量，它们会让夹具里的 git 命令操作到**外层仓库**。
症状很典型：**手动跑全过、在钩子里挂几个**。统一清掉才叫隔离。
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
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


STATE = _load("git_state", os.path.join(SCRIPTS, "git_state.py"))
GUARD = _load("git_guard", os.path.join(SCRIPTS, "git_guard.py"))


# ── 夹具 ──────────────────────────────────────────────────────────────────
class Repo:
    """一个临时建出来的真仓库。"""

    def __init__(self, path: str):
        self.path = path

    def git(self, *args: str) -> str:
        proc = subprocess.run(["git", "-C", self.path, *args],
                              capture_output=True, text=True, check=False)
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
    """建/拆一个仓库，并把全局 git 配置隔离掉。"""

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
        os.environ.clear()
        os.environ.update(self._saved_env)

    def state(self) -> dict:
        return STATE.snapshot(self.repo.path)

    def guard(self, action: str, *extra: str) -> tuple[int, dict]:
        """跑一次 guard，返回 (退出码, JSON 结论)。"""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = GUARD.main([action, *extra, "--repo", self.repo.path, "--json"])
        return code, json.loads(buffer.getvalue())


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


if __name__ == "__main__":
    unittest.main()
