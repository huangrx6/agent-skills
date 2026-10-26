#!/usr/bin/env python3
"""跑触发评测：在干净会话里逐条发请求，记录被测 skill 有没有被加载。

为什么单独一个脚本
------------------
`trigger_eval.py` 只算分，不跑——因为跑一次要真实模型和干净会话，成本高。
成本高就得能**按需缩小范围**：改了一个 skill 的描述，只跑那一个（三分钟出结论）；
发布前才全量。把范围、次数、并发都做成参数，而不是每次手写一次性脚本。

用法：

    python3 tools/trigger_run.py --list                     # 看有哪些用例
    python3 tools/trigger_run.py --skill deck-authoring      # 只跑一个 skill
    python3 tools/trigger_run.py --skill deck-authoring --ids 6,8 --reps 1   # 只验两条边界
    python3 tools/trigger_run.py --out /tmp/results.json     # 全量跑，结果交给 trigger_eval

结果文件与 `trigger_eval.py --score` 兼容，两条命令串起来就是一次完整验证：

    python3 tools/trigger_run.py --skill deck-authoring --out /tmp/r.json
    python3 tools/trigger_eval.py --score /tmp/r.json

退出码：0 全部通过，1 有用例没过，2 参数或环境不可用。
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)
# 与 trigger_eval.py 的默认阈值一致：正例要 > 0.5 才算稳定触发，反例要 < 0.5 才算稳定不触发
DEFAULT_THRESHOLD = 0.5
DEFAULT_REPS = 3
DEFAULT_PARALLEL = 8
DEFAULT_TIMEOUT = 150
SKILL_EVENTS = ("loaded-skill", "inline-skill")


def load_catalog(root: str) -> dict[str, dict[str, Any]]:
    """读所有 skill 的 evals/triggers.json，返回 {skill: payload}。"""
    catalog: dict[str, dict[str, Any]] = {}
    skills_dir = os.path.join(root, "skills")
    try:
        names = sorted(os.listdir(skills_dir))
    except OSError as exc:
        raise SystemExit(f"读不到 skills 目录：{exc}") from None
    for name in names:
        path = os.path.join(skills_dir, name, "evals", "triggers.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"{path} 读不出来：{exc}") from None
        if isinstance(payload.get("triggers"), list):
            payload["skill_name"] = payload.get("skill_name") or name
            catalog[name] = payload
    return catalog


def select_cases(root: str, skills: list[str] | None,
                 ids: set[int] | None) -> list[dict[str, Any]]:
    """挑出要跑的用例：`skills` 为空表示全部；`ids` 为空表示该 skill 的全部用例。"""
    catalog = load_catalog(root)
    chosen: list[dict[str, Any]] = []
    for name in (skills or sorted(catalog)):
        if name not in catalog:
            raise SystemExit(f"没有这个 skill 的评测集：{name}")
        for case in catalog[name]["triggers"]:
            if ids and case.get("id") not in ids:
                continue
            chosen.append({
                "skill": name,
                "id": case.get("id"),
                "query": case.get("query"),
                "expect": bool(case.get("should_trigger")),
            })
    if not chosen:
        raise SystemExit("没有匹配的用例（检查 --skill / --ids）")
    return chosen


def parse_session(session_dir: str) -> list[str]:
    """读会话目录里的 jsonl，返回被加载过的 skill 名（去重）。

    `pi` 把 skill 加载记成 `loaded-skill`（读 SKILL.md）或 `inline-skill`（内联注入）。
    只看这两个事件：工具调用记录里也有 name 字段，混进来会误判。
    """
    names: set[str] = set()
    for base, _dirs, files in os.walk(session_dir):
        for filename in files:
            if not filename.endswith(".jsonl"):
                continue
            path = os.path.join(base, filename)
            try:
                with open(path, encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        try:
                            record = json.loads(line)
                        except ValueError:
                            continue
                        if record.get("customType") not in SKILL_EVENTS:
                            continue
                        name = (record.get("data") or {}).get("name")
                        if name:
                            names.add(name)
            except OSError:
                continue
    return sorted(names)


def run_case(case: dict[str, Any], work: str, timeout: int) -> dict[str, Any]:
    session_dir = os.path.join(work, f"{case['skill']}-{case['id']}")
    try:
        os.makedirs(session_dir, exist_ok=True)
    except OSError as exc:
        raise SystemExit(f"建不了会话目录 {session_dir}：{exc}") from None
    command = ["pi", "-p", str(case["query"]), "--tools", "read",
               "--session-dir", session_dir]
    try:
        subprocess.run(command, cwd=work, timeout=timeout, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {**case, "loaded": [], "timed_out": True}
    except FileNotFoundError:
        raise SystemExit("找不到 pi 命令：触发评测要在装有 pi 的环境里跑") from None
    return {**case, "loaded": parse_session(session_dir), "timed_out": False}


def summarize(cases: list[dict[str, Any]], rows: list[dict[str, Any]],
              threshold: float) -> list[dict[str, Any]]:
    """把多次运行折成每条用例的触发率，并标出是否通过。"""
    report: list[dict[str, Any]] = []
    for case in cases:
        runs = [row for row in rows
                if row["skill"] == case["skill"] and row["id"] == case["id"]]
        hits = sum(1 for row in runs if case["skill"] in row["loaded"])
        rate = hits / len(runs) if runs else 0.0
        passed = rate > threshold if case["expect"] else rate < threshold
        report.append({**case, "runs": len(runs), "hits": hits,
                       "rate": round(rate, 2), "passed": passed,
                       "others": sorted({s for row in runs for s in row["loaded"]
                                         if s != case["skill"]})})
    return report


def render(report: list[dict[str, Any]]) -> str:
    lines = []
    for item in report:
        mark = "✓" if item["passed"] else "✗"
        kind = "应" if item["expect"] else "不应"
        lines.append(f"{mark} [{item['skill']}#{item['id']}] {kind}触发 "
                     f"{item['hits']}/{item['runs']}  {str(item['query'])[:34]}")
        if not item["passed"] and item["others"]:
            lines.append(f"      实际唤醒：{', '.join(item['others'])}")
    failed = [item for item in report if not item["passed"]]
    lines.append("")
    lines.append(f"合计 {len(report)} 条，通过 {len(report) - len(failed)}，未过 {len(failed)}")
    return "\n".join(lines)


def prepare_workdir(work: str) -> None:
    """清空并重建会话目录。

    必须每轮全新：同一目录会累积历史 jsonl，检测时一起读进来，
    等于把上一轮的结果算进这一轮（这个坑踩过一次，同一反例连续三轮都是「命中」）。
    """
    try:
        if os.path.isdir(work):
            shutil.rmtree(work)
        os.makedirs(work, exist_ok=True)
    except OSError as exc:
        raise SystemExit(f"准备不了会话目录 {work}：{exc}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="跑触发评测（结果兼容 trigger_eval --score）")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="仓库根目录")
    parser.add_argument("--skill", action="append", metavar="NAME",
                        help="只跑这个 skill，可重复；不写表示全部")
    parser.add_argument("--ids", default="", help="只跑这些用例编号，逗号分隔")
    parser.add_argument("--reps", type=int, default=DEFAULT_REPS, help="每条用例跑几次（默认 3）")
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL, help="并发会话数")
    parser.add_argument("--work", default=os.path.join(tempfile.gettempdir(), "trigger-run"),
                        help="会话目录，每次运行会清空重建")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单条超时秒数")
    parser.add_argument("--out", help="把结果写成 JSON（供 trigger_eval --score）")
    parser.add_argument("--list", action="store_true", help="只列出选中用例，不跑")
    args = parser.parse_args(argv)

    ids: set[int] = set()
    for part in args.ids.replace(" ", "").split(","):
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            raise SystemExit(f"--ids 里有不是数字的项：{part!r}") from None
    cases = select_cases(args.root, args.skill, ids or None)

    if args.list:
        for case in cases:
            kind = "应触发" if case["expect"] else "不应触发"
            print(f"[{case['skill']}#{case['id']}] {kind} {case['query']}")
        print(f"\n{len(cases)} 条 × {args.reps} 次 = {len(cases) * args.reps} 次会话")
        return 0

    prepare_workdir(args.work)

    jobs = [(case, rep) for case in cases for rep in range(args.reps)]
    rows: list[dict[str, Any]] = []
    print(f"{len(cases)} 条 × {args.reps} 次 = {len(jobs)} 次（并发 {args.parallel}）", flush=True)
    with cf.ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [pool.submit(run_case, case, args.work, args.timeout) for case, _ in jobs]
        for done, future in enumerate(cf.as_completed(futures), start=1):
            rows.append(future.result())
            if done % 20 == 0:
                print(f"  已跑 {done}/{len(jobs)}", flush=True)

    report = summarize(cases, rows, DEFAULT_THRESHOLD)
    print(render(report))

    if args.out:
        payload = [{"skill": item["skill"], "id": item["id"], "runs": item["runs"],
                    "triggered": item["hits"]} for item in report]
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
        except OSError as exc:
            raise SystemExit(f"写不了结果文件 {args.out}：{exc}") from None
        print(f"结果已写 {args.out}")

    return 0 if all(item["passed"] for item in report) else 1


if __name__ == "__main__":
    sys.exit(main())
