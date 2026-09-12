#!/usr/bin/env python3
"""不可逆动作预检 —— 把「会丢什么」变成一次必跑的计算，把「确定要做」变成第二步。

## 为什么要有它

`reset --hard`、`clean -fd`、`branch -D`、`push --force` 这类命令的共同点是：
**执行完就没有第二遍**。而 agent 最容易在两种时刻动手：一是被要求「清理一下」，
二是自己觉得「这个没用了吧」。两种时刻的判断依据都不可靠。

所以这里不劝人小心（劝了没用），而是把动作变成一次**有固定判据的计算**：
输入是动作，输出是「按判据，会丢这些；结论是 SAFE / WARN / BLOCK」。

## 三条设计约束

1. **判据必须在代码里**，不在文档里 —— 文档里的「小心」会被忽略，代码里的判据不会。
2. **复用 `git_state.py` 的采集器**：什么叫「未推送」「已并入」「目录不存在」只能有一份实现。
   两份实现必然漂移，而漂移的那一份会让你在错误的一侧得到安全感。
3. **拿不到信息时按最坏处理**（fail-closed）：远端状态问不到就当「可能丢东西」，
   而不是当「没事」。宁可多问一句，不可少拦一次。

## 退出码

- `0` SAFE
- `3` WARN（可以做，但先把下面这些看清楚）
- `4` BLOCK（默认不做；要做得先解决列出来的原因）

## 用法

    python3 scripts/git_guard.py delete-branch feat/x
    python3 scripts/git_guard.py discard-worktree --repo /path
    python3 scripts/git_guard.py rewrite-history --shared
    python3 scripts/git_guard.py force-push --branch dev
    python3 scripts/git_guard.py --list
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys

SAFE, WARN, BLOCK = 0, 3, 4
LEVEL_NAME = {SAFE: "SAFE", WARN: "WARN", BLOCK: "BLOCK"}

# patch-id 比对的有界范围：只在最近这么多条提交里找「同样的改动」。
# 有界是有意的 —— 全历史扫描在真仓库上要几十秒，而这里要回答的是
# 「我这条 stash 是不是已经落进某条提交了」，近期范围足够，且会如实标注。
PATCH_ID_SCAN = 300


def _load_sibling(name: str):
    """按显式文件路径加载同目录模块。

    必须先注册进 sys.modules 再 exec —— 模块里若有 `@dataclass`，解析注解时会查
    `sys.modules.get(cls.__module__)`，没注册就拿到 None 然后炸。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_gitdev_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


S = _load_sibling("git_state")


# ── 结论对象 ──────────────────────────────────────────────────────────────
class Verdict:
    def __init__(self, action: str, level: int, reasons: list[str],
                 evidence: list[str], command: str = "", caveat: str = ""):
        self.action = action
        self.level = level
        self.reasons = reasons
        self.evidence = evidence
        self.command = command
        self.caveat = caveat

    def json(self) -> dict:
        return {"action": self.action, "level": LEVEL_NAME[self.level],
                "reasons": self.reasons, "evidence": self.evidence,
                "command": self.command, "caveat": self.caveat}


def level_from(reasons_blocking: list[str], reasons_warning: list[str]) -> int:
    if reasons_blocking:
        return BLOCK
    if reasons_warning:
        return WARN
    return SAFE


def render(verdict: Verdict) -> str:
    """四段：动作 / 会丢什么 / 结论 / 确定则执行这一条。

    「执行这一条」那一段是**故意**的：让继续动作用户/上层可以直接复制的一行，
    而不是让 agent 自己再拼一次命令 —— 拼出来的那一条没经过这里的判据。
    """
    lines = [f"动作     {verdict.action}"]
    lines.append("会丢什么")
    lines.extend(f"         - {item}" for item in verdict.evidence)
    if not verdict.evidence:
        lines.append("         -（按判据没有可丢的东西）")
    lines.append(f"结论     {LEVEL_NAME[verdict.level]}")
    lines.extend(f"         原因：{reason}" for reason in verdict.reasons)
    if verdict.caveat:
        lines.append(f"         注意：{verdict.caveat}")
    if verdict.command and verdict.level != BLOCK:
        lines.append("确认要这么做的话，执行这一条")
        lines.append(f"         {verdict.command}")
    elif verdict.command:
        lines.append("（被拦时不给命令 —— 给了就等于在暗示它可以做。"
                     "先把上面的原因解决掉，再重新跑一次这个判据。）")
    return "\n".join(lines)


# ── 各动作的判据 ──────────────────────────────────────────────────────────
def _non_artifact(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e["kind"] != "artifact"]


def _describe(entries: list[dict], limit: int = 12) -> str:
    kinds = S.by_kind(entries)
    summary = "、".join(f"{k} {v}" for k, v in sorted(kinds.items()))
    names = "、".join(e["path"] for e in entries[:limit])
    if len(entries) > limit:
        names += f" …（还有 {len(entries) - limit} 个）"
    return f"{len(entries)} 项（{summary}）：{names}"


def _tri(value: bool | None) -> str:
    """三态描述：True / False / None。

    **None 有专门的意思 —— 问不出来**，不是「否」。混为一谈会让人以为已经确认过了。
    """
    if value is None:
        return "无法确认（没有基线分支可比）"
    return "是" if value else "否"


def guard_discard_worktree(state: dict) -> Verdict:
    dirty = state["dirty"]
    files = [f for f in dirty["files"] if f["code"] != "!!"]
    blocking_files = _non_artifact(files)
    evidence = []
    if files:
        evidence.append(f"未提交改动：{_describe(files)}")
    if state["dirty"]["counts"]["staged"]:
        evidence.append(f"其中已暂存的 {state['dirty']['counts']['staged']} 项会一起没")
    unprotected = dirty["protected"]
    if unprotected:
        evidence.append("疑似凭据也在里面：" + "、".join(e["path"] for e in unprotected))
    if state.get("submodules", {}).get("present"):
        # 说清范围，不然会被读成「顺手也把子模块清了」：reset --hard 不动子模块工作树，
        # clean -fd 也不会删嵌套的 git 仓库（要 -ff 才行）。
        count = len(state["submodules"].get("items", []))
        evidence.append(f"子模块 {count} 个：这个动作只作用于当前工作树 —— "
                        "reset --hard 与 clean -fd 都不进子模块，"
                        "所以子模块里那些未提交的改动不在它的范围里")
    if not files:
        evidence.append("工作区是干净的")
    blocking: list[str] = []
    warning: list[str] = []
    if blocking_files:
        blocking.append(f"有 {len(blocking_files)} 项不是构建产物 —— 它们是源码/文档/配置，"
                        "丢了要重写")
    elif files:
        warning.append("未提交的都像构建产物：通常能重新生成，但确认一下真的都能")
    if unprotected and not blocking:
        warning.append("里面还夹着疑似凭据（本地才有、不在版本库里的那种）")
    return Verdict("discard-worktree", level_from(blocking, warning),
                   blocking + warning, evidence,
                   command="git reset --hard && git clean -fd",
                   caveat="这条命令会把未跟踪的非产物文件也删掉 —— 上面列的不是产物的那些先处理掉"
                          if any(f["code"] == "??" for f in files) else "")


def guard_clean_untracked(state: dict, include_ignored: bool) -> Verdict:
    files = [f for f in state["dirty"]["files"] if f["code"] == "??"]
    blocking_files = _non_artifact(files)
    ignored = state.get("ignored_count", 0)
    ignored_protected = state.get("ignored_protected", [])
    evidence = []
    if files:
        evidence.append(f"未跟踪文件：{_describe(files)}")
    else:
        evidence.append("没有未跟踪文件")
    if include_ignored and ignored:
        evidence.append(f"被 .gitignore 挡住、但 -x 会连它们一起删的：{ignored} 项"
                        "（.venv / node_modules / 构建缓存通常在里面）")
        for entry in ignored_protected[:8]:
            evidence.append(f"    其中疑似凭据：{entry['path']}")

    blocking: list[str] = []
    warning: list[str] = []
    if blocking_files:
        blocking.append(f"未跟踪里有 {len(blocking_files)} 项不是构建产物 —— "
                        "未跟踪不等于没用（新写的文件就是未跟踪）")
    elif files:
        warning.append("未跟踪的都像构建产物，但 clean 之后要重新生成一遍")
    if include_ignored and ignored:
        warning.append(f"用了 -x：连 .gitignore 挡住的 {ignored} 项也一起删")
    if include_ignored and ignored_protected:
        blocking.append("被挡住的文件里有像凭据的（.env / *.pem 这类）：它们**不在版本库里**，"
                        "删了就真的没了")
    return Verdict("clean-untracked", level_from(blocking, warning),
                   blocking + warning, evidence,
                   command="git clean -fdx" if include_ignored else "git clean -fd")


def guard_delete_branch(state: dict, name: str) -> Verdict:
    branch = next((b for b in state["branches"] if b["name"] == name), None)
    evidence = []
    if branch is None:
        return Verdict(f"delete-branch {name}", BLOCK,
                       [f"本地没有名为 {name} 的分支"], evidence)
    baseline = state["branch"]["baseline"]
    if branch["current"]:
        evidence.append(f"{name} 就是当前分支")
    if name == baseline:
        evidence.append(f"{name} 就是基线分支本身")
    if branch["merged"] is None:
        evidence.append(f"没有基线分支可比（这个仓库没有 main/dev/master）—— 无法确认它是否已并入")
    else:
        evidence.append(f"是否已并入 {baseline}：{'是' if branch['merged'] else '否'}")
    evidence.append(f"仅存在于本地的提交：{branch['unpushed']} 条")
    for subject in S.unpushed(state["root"], name)["subjects"][:5]:
        evidence.append(f"    {subject}")

    blocking: list[str] = []
    warning: list[str] = []
    if branch["current"]:
        blocking.append("它是当前分支：先切到别的分支（或别的 worktree）上再删")
    if name == baseline:
        # 删基线不是「清理分支」，是换主干：主干上的提交可能只被它指着，
        # 而且删掉它之后这个工具的所有判断都没有参照了。
        blocking.append(f"它是基线分支（{baseline}）：所有判断都以它为准 —— "
                        "这在「清理分支」的范围之外，真要换主干就先做迁移")
    if branch["merged"] is None:
        blocking.append("确认不了它是否已并入别处 —— 拿不到信息时按最坏处理")
    elif not branch["merged"] and branch["unpushed"]:
        blocking.append(f"有 {branch['unpushed']} 条提交只存在于这一条分支上："
                        "删了就要去 reflog 里捞")
    elif not branch["merged"]:
        warning.append("分支未并入基线（提交已在远端，所以只是本地这个指针没了）")
    # 已并入就不再提「未推送」：并入意味着那些提交能从基线走到，删掉分支丢不了东西。
    # 以前这里会再报一条 WARN，于是同一个已并入的分支在「有提交没进远端」时反而更“重”——
    # 那个判断是错的，用例把它抓出来了（没有远端的仓库里首次提交就是这样）。
    return Verdict(f"delete-branch {name}", level_from(blocking, warning),
                   blocking + warning, evidence,
                   command=f"git branch -D {name}",
                   caveat="已并入也只保证「内容在」，指针没了；要恢复得查 reflog")


def guard_delete_worktree(state: dict, path: str) -> Verdict:
    target = os.path.realpath(path)
    item = next((w for w in state["worktrees"] if S.same_path(w["path"], target)), None)
    evidence = []
    if item is None:
        return Verdict(f"delete-worktree {path}", BLOCK,
                       ["worktree 清单里没有这个路径"], evidence)
    evidence.append(f"分支：{item['branch'] or '(detached)'}  HEAD {item['head']}")
    if not item["exists"]:
        evidence.append("目录已经不存在了 —— 这种用 `git worktree prune` 清就行")
        return Verdict(f"delete-worktree {path}", SAFE, [], evidence,
                       command="git worktree prune")
    baseline = state["branch"]["baseline"]
    merged = S.merged_into(state["root"], item["branch"], baseline) if item["branch"] else None
    evidence.append(f"目录存在；未提交 {item['dirty']} 项；仅存在于本地的提交 {item['unpushed']} 条")
    evidence.append(f"是否已并入 {baseline or '(无基线)'}：{_tri(merged)}")

    # 判据只有一条硬的：**那个目录里的未提交改动**。
    #
    # 原设计是「三项前置：已并入 / 无未推送 / 无未提交」。实测（用例断言过）表明
    # `git worktree remove` **不删分支、不删提交** —— 它只拿掉工作目录和记录。
    # 所以「无未推送」不是数据丢失条件：没有远端的仓库里它恒为真，会把回收卡死；
    # 而它想防的「那份工作没人管了」是个提醒，不是损失。判据按事实改：
    # 脏 → BLOCK（真丢），分支未并入 → WARN（不丢，但得确认不是做到一半）。
    blocking: list[str] = []
    warning: list[str] = []
    if item["dirty"]:
        blocking.append(f"那个目录里有 {item['dirty']} 项未提交的改动 —— "
                        "它们只存在于那个目录里，删掉就真没了")
    if merged:
        evidence.append("已并入基线：提交能从基线走到，回收不会丢东西")
    else:
        warning.append("这个 worktree 上的分支还没并进基线 —— 提交不会丢（分支还在），"
                       "但先确认你不是正在做到一半")
    return Verdict(f"delete-worktree {path}", level_from(blocking, warning),
                   blocking + warning, evidence,
                   command=f"git worktree remove {item['path']}",
                   caveat="回收只拿掉目录和记录：分支、提交都还在"
                          + ("；那个目录里的未提交改动才是真会丢的东西" if item["dirty"] else ""))


def _patch_id(repo: str, args: list[str]) -> str:
    """把某条 diff 算成 patch-id（与提交位置无关的「同一个改动」指纹）。"""
    try:
        diff = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
        if diff.returncode != 0 or not diff.stdout.strip():
            return ""
        pid = subprocess.run(["git", "patch-id", "--stable"], input=diff.stdout,
                             capture_output=True, text=True)
    except OSError:
        return ""
    parts = pid.stdout.split()
    return parts[0] if parts else ""


def _commit_patch_ids(repo: str, limit: int) -> dict[str, str]:
    """最近 limit 条提交的 patch-id → sha。**有界**，并在报告里说明这个界。

    `--exclude=refs/stash` 不能省，且必须写在 `--all` **前面**：`--all` 把
    `refs/stash` 也算进去，于是 stash 的改动会匹配到它自己 —— 那样
    「改动在别处找不到」这条分支永远走不到，drop-stash 对任何非空 stash
    都给 SAFE（实测踩过：整条 WARN 分支成了死代码）。
    """
    try:
        log = subprocess.run(["git", "-C", repo, "log", "--exclude=refs/stash", "--all",
                              "-n", str(limit), "-p"],
                             capture_output=True, text=True)
        if log.returncode != 0:
            return {}
        pid = subprocess.run(["git", "patch-id", "--stable"], input=log.stdout,
                             capture_output=True, text=True)
    except OSError:
        return {}
    found: dict[str, str] = {}
    for line in pid.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            found.setdefault(parts[0], parts[1])
    return found


def guard_drop_stash(state: dict, ref: str) -> Verdict:
    stash = [s for s in state["stash"] if s["ref"] == ref]
    evidence = []
    if not stash:
        return Verdict(f"drop-stash {ref}", BLOCK,
                       [f"stash 列表里没有 {ref}（现有 {len(state['stash'])} 条）"], evidence)
    evidence.append(f"{ref}  {stash[0]['subject']}")
    target = _patch_id(state["root"], ["stash", "show", "-p", ref])
    if not target:
        evidence.append("算不出这条 stash 的 patch-id（可能是空的）")
        return Verdict(f"drop-stash {ref}", WARN,
                       ["拿不到它的指纹，无法确认改动在别处还有"], evidence,
                       command=f"git stash drop {ref}")
    elsewhere = _commit_patch_ids(state["root"], PATCH_ID_SCAN)
    hit = elsewhere.get(target, "")
    if hit:
        evidence.append(f"同样的改动已经在提交 {hit} 里 —— 在最近 {PATCH_ID_SCAN} 条里找到的")
        return Verdict(f"drop-stash {ref}", SAFE, [], evidence,
                       command=f"git stash drop {ref}")
    evidence.append(f"最近 {PATCH_ID_SCAN} 条提交里没有同样的改动（stash 自身不算；"
                    f"比对范围有界，更早的历史没查）")
    return Verdict(f"drop-stash {ref}", WARN,
                   ["这条 stash 的改动在近期历史里找不到对应 —— 丢了就要去 reflog 捞"],
                   evidence, command=f"git stash drop {ref}")


def guard_rewrite_history(state: dict, shared: bool) -> Verdict:
    evidence = []
    if state["mid_operation"]:
        return Verdict("rewrite-history", BLOCK,
                       [f"正处于 {' / '.join(state['mid_operation'])}：先结束或中止它"],
                       evidence)
    head = S.git_text(state["root"], "rev-parse", "HEAD")
    on_remote = S.git_lines(state["root"], "branch", "-r", "--contains",
                            state["branch"]["head"] or "HEAD")
    evidence.append(f"当前 HEAD {state['branch']['head']}，未提交 {state['dirty']['total']} 项")
    if on_remote:
        evidence.append("这个提交已经在远端：" + "、".join(r.strip() for r in on_remote[:5]))
    else:
        evidence.append("没有任何远端分支包含这个提交（或这个仓库没有远端）")

    blocking: list[str] = []
    warning: list[str] = []
    if on_remote and not shared:
        blocking.append("要重写的提交已经在远端了 —— 改写它等于改写别人的历史，"
                        "而别的 clone 不会自己知道")
    if state["dirty"]["total"] and not state["dirty"]["counts"]["conflicted"]:
        warning.append(f"工作区不干净（{state['dirty']['total']} 项）：改写历史前先处理掉，"
                       "否则它们会被卷进冲突")
    caveat = ""
    if shared and on_remote:
        warning.append("这是共享历史改写：别的 clone 不会自己知道，得你去通知（或接受它们出问题）")
        caveat = ("你已用 --shared 显式声明「我知道这是共享历史」—— 报告里要写明这一点，"
                  "别把它当成普通的本地清理")
    return Verdict("rewrite-history", level_from(blocking, warning),
                   blocking + warning, evidence,
                   command="git commit --amend --no-edit" if not state["dirty"]["total"] else "",
                   caveat=caveat)


def guard_force_push(state: dict, branch: str, remote: str) -> Verdict:
    name = branch or state["branch"]["branch"]
    evidence = []
    if not name:
        return Verdict("force-push", BLOCK, ["当前是 detached HEAD，且没指定 --branch"], evidence)
    baseline = state["branch"]["baseline"]
    if name in (baseline, "main", "master", "dev"):
        evidence.append(f"{name} 是基线分支之一")
        return Verdict(f"force-push {remote}/{name}", BLOCK,
                       [f"不许强推基线分支 {name} —— 那是所有人的共同参照"],
                       evidence, command="")
    upstream = state["upstream"]
    evidence.append(f"本地 {name}@{state['branch']['head']}")
    if upstream["upstream"]:
        evidence.append(f"上游 {upstream['upstream']}  领先 {upstream['ahead']} / 落后 {upstream['behind']}")
    else:
        evidence.append("没有上游，拿不到远端位置")

    remote_ref = f"{remote}/{name}"
    has_remote_ref = bool(S.git_text(state["root"], "rev-parse", "--verify", "--quiet",
                                     f"refs/remotes/{remote_ref}"))
    reasons = []
    if not has_remote_ref:
        reasons.append(f"本地没有 {remote_ref} 这个远端跟踪引用 —— "
                       "拿不到远端现在在哪，按最坏处理（先 fetch 一次）")
        return Verdict(f"force-push {remote_ref}", BLOCK, reasons, evidence,
                       command=f"git fetch {remote} && git status -sb")
    # 变量名按**方向**取，不按“谁的”——上一版把两个名字写反了（逻辑对、名字反），
    # 读代码的人会以为 `remote_ref..HEAD` 是“远端的”。方向按 `A..B` 读就是 B 独有。
    local_only = S.as_int(S.git_text(state["root"], "rev-list", "--count",
                                     f"{remote_ref}..HEAD"))
    remote_only = S.as_int(S.git_text(state["root"], "rev-list", "--count",
                                      f"HEAD..{remote_ref}"))
    evidence.append(f"远端有而本地没有：{remote_only} 条；本地有而远端没有：{local_only} 条")
    if remote_only:
        reasons.append(f"远端有 {remote_only} 条本地没有的提交 —— 强推会把它们从远端抹掉")
        return Verdict(f"force-push {remote_ref}", BLOCK, reasons, evidence, command="")
    if not local_only:
        reasons.append("本地并不领先 —— 这条强推没有内容可推，普通 push 就够")
        return Verdict(f"force-push {remote_ref}", WARN, reasons, evidence,
                       command=f"git push {remote}")
    return Verdict(f"force-push {remote_ref}", WARN,
                   ["本地领先但这是强推：远端那一刻的提交会被替换掉"],
                   evidence, command=f"git push --force-with-lease {remote} {name}",
                   caveat="用 --force-with-lease 而不是 --force：远端若在你之后动过，它会被挡下")


def guard_bypass_hooks(state: dict) -> Verdict:
    hooks = state["hooks"]
    evidence = [f"钩子来源：{hooks['source']}（{hooks['path']}）"]
    if hooks["enabled"]:
        evidence.append("已启用：" + " ".join(hooks["enabled"]))
        return Verdict("bypass-hooks", BLOCK,
                       ["这个仓库装了钩子 —— 绕过它等于跳过别人（或你自己）设的检查"],
                       evidence, command="")
    evidence.append("没有启用的钩子")
    return Verdict("bypass-hooks", SAFE, [], evidence)


ACTIONS = {
    "discard-worktree": "丢弃工作区改动（reset --hard / checkout -- .）",
    "clean-untracked": "删除未跟踪文件（git clean）",
    "delete-branch": "删除本地分支（git branch -D）",
    "delete-worktree": "移除 worktree（git worktree remove）",
    "drop-stash": "丢弃一条 stash（git stash drop）",
    "rewrite-history": "改写历史（amend / rebase / filter-branch）",
    "force-push": "强推（git push --force）",
    "bypass-hooks": "绕过钩子（--no-verify）",
}


def evaluate(action: str, state: dict, args) -> Verdict:
    # 先清一次去重缓存。**这行是双保险，不是承重的**：判档读的都是传进来的 state，
    # 每次 snapshot() 开头已经清过了（承重的是那一句 —— 用例盯着它）。这里清一次是防
    # 「直接调 evaluate、state 是别处取的」那条路径（worktree.py 就是这么调的）下，
    # 证据文本里重问 git 时拿到更早一次读取的旧事实。别把它当成判档的保障。
    S.clear_cache()
    if action not in ACTIONS:
        return Verdict(action, BLOCK, [f"不认识的动作；可用：{'、'.join(ACTIONS)}"], [])
    # 中间态下一律先拦：rebase/merge 没结束时，这些命令的含义和平时不一样
    if action != "bypass-hooks" and state["mid_operation"]:
        return Verdict(action, BLOCK,
                       [f"正处于 {' / '.join(state['mid_operation'])}："
                        "先结束或中止它，再评估这个动作"],
                       [])
    if action == "discard-worktree":
        return guard_discard_worktree(state)
    if action == "clean-untracked":
        return guard_clean_untracked(state, args.include_ignored)
    if action == "delete-branch":
        return guard_delete_branch(state, args.name or "")
    if action == "delete-worktree":
        return guard_delete_worktree(state, args.name or "")
    if action == "drop-stash":
        return guard_drop_stash(state, args.name or "")
    if action == "rewrite-history":
        return guard_rewrite_history(state, args.shared)
    if action == "force-push":
        return guard_force_push(state, args.branch or "", args.remote)
    return guard_bypass_hooks(state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="不可逆 git 动作的预检（SAFE / WARN / BLOCK）",
        epilog="；".join(f"{k}：{v}" for k, v in ACTIONS.items()))
    parser.add_argument("action", nargs="?", help="要评估的动作")
    parser.add_argument("name", nargs="?", help="分支名 / worktree 路径 / stash ref")
    parser.add_argument("--repo", default=".", help="仓库路径（默认当前目录）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--shared", action="store_true",
                        help="rewrite-history 的逃生阀：显式声明「我知道这是共享历史」")
    parser.add_argument("--include-ignored", action="store_true",
                        help="clean-untracked：连 .gitignore 挡住的也删（-x）")
    parser.add_argument("--branch", default="", help="force-push：要推的分支")
    parser.add_argument("--remote", default="origin", help="force-push：远端名")
    parser.add_argument("--list", action="store_true", help="列出所有动作")
    args = parser.parse_args(argv)

    if args.list or not args.action:
        for name, desc in ACTIONS.items():
            print(f"  {name:<18} {desc}")
        return SAFE

    state = S.snapshot(args.repo)
    if not state.get("is_repo"):
        print(f"不是一个 git 仓库：{os.path.abspath(args.repo)}", file=sys.stderr)
        return 1

    verdict = evaluate(args.action, state, args)
    if args.json:
        print(json.dumps(verdict.json(), ensure_ascii=False, indent=2))
    else:
        print(render(verdict))
    return verdict.level


if __name__ == "__main__":
    sys.exit(main())
