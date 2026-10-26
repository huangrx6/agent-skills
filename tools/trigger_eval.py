#!/usr/bin/env python3
"""触发出评测：把「这条请求该不该唤醒 skill」变成可测量的数字。

为什么需要它
------------
描述写得像不像样，读一遍是看不出来的：同一个 skill 的 description 在真实请求上
可能过宽（把邻近任务也吸进来）也可能过窄（用户换个说法就不触发）。官方建议的做法是
**每条请求跑多次、看 skill 有没有被加载**，再算触发率：

    正例通过 = 触发率 ≥ 阈值（默认 0.5）
    反例通过 = 触发率 < 阈值

这个脚本不负责任何一次真实运行（那需要干净的上下文和真实模型），它只做两件事：
生成结果模板，算分。跑与不跑、跑几次，由人或调度器决定。

用法：
    python3 tools/trigger_eval.py --list
    python3 tools/trigger_eval.py --template results.json --runs 3
    python3 tools/trigger_eval.py --score results.json
    python3 tools/trigger_eval.py --score results.json --json

结果文件格式（--template 生成的就是它）：
    [{"skill": "obsidian-wiki", "id": 1, "runs": 3, "triggered": 2}, ...]

退出码：0 全部通过，1 有没过的用例，2 输入不可用。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)
DEFAULT_THRESHOLD = 0.5


class InputError(Exception):
    """结果文件或仓库结构不可用：这是输入问题，不是评测失败。"""


def skills_with_triggers(root: str) -> dict[str, dict[str, Any]]:
    """{skill 名: triggers.json 内容}。没有该文件的 skill 直接跳过。"""
    found: dict[str, dict[str, Any]] = {}
    skills_dir = os.path.join(root, "skills")
    if not os.path.isdir(skills_dir):
        raise InputError(f"找不到 skills 目录：{skills_dir}")
    try:
        entries = sorted(os.listdir(skills_dir))
    except OSError as exc:
        raise InputError(f"读不了 {skills_dir}：{exc}") from exc
    for name in entries:
        path = os.path.join(skills_dir, name, "evals", "triggers.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as exc:
            raise InputError(f"读不了 {path}：{exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("triggers"), list):
            raise InputError(f"{path} 不是触发评测集（缺 triggers 列表）")
        found[name] = payload
    if not found:
        raise InputError(f"{skills_dir} 下没有任何 evals/triggers.json")
    return found


def _cases(root: str) -> list[dict[str, Any]]:
    """把所有 skill 的用例摊平，带上 skill 名。"""
    flat: list[dict[str, Any]] = []
    for skill, payload in skills_with_triggers(root).items():
        for case in payload["triggers"]:
            flat.append({"skill": skill, **case})
    return flat


def cmd_list(root: str) -> int:
    sets = skills_with_triggers(root)
    for skill, payload in sets.items():
        cases = payload["triggers"]
        positive = sum(1 for c in cases if c.get("should_trigger"))
        print(f"{skill}: {len(cases)} 条（正例 {positive} / 反例 {len(cases) - positive}）")
        for case in cases:
            mark = "应触发  " if case.get("should_trigger") else "不应触发"
            note = f"  ← {case['note']}" if case.get("note") else ""
            print(f"  [{case.get('id')}] {mark} {case.get('query')}{note}")
    return 0


def cmd_template(root: str, out: str, runs: int) -> int:
    if runs < 1:
        raise InputError("--runs 至少是 1")
    payload = [{"skill": case["skill"], "id": case["id"],
                "runs": runs, "triggered": 0} for case in _cases(root)]
    _write(out, payload)
    print(f"已写出 {len(payload)} 条待记录用例：{out}")
    print("每条跑 --runs 次，填 triggered = 唤醒 skill 的次数，再 --score。")
    return 0


def _count(item: dict[str, Any], field: str, where: str) -> int:
    """取一个非负整数字段。单独成函数是为了让类型窄化一次到位。"""
    value = item.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InputError(f"{where}的 {field} 必须是非负整数")
    return value


def _load_results(path: str) -> dict[tuple[str, Any], dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise InputError(f"读不了 {path}：{exc}") from exc
    except ValueError as exc:
        raise InputError(f"{path} 不是合法 JSON：{exc}") from exc
    if not isinstance(data, list):
        raise InputError(f"{path} 顶层应是列表")

    indexed: dict[tuple[str, Any], dict[str, Any]] = {}
    for position, item in enumerate(data, start=1):
        where = f"结果第 {position} 条"
        if not isinstance(item, dict):
            raise InputError(f"{where}不是对象")
        skill, case_id = item.get("skill"), item.get("id")
        if not isinstance(skill, str) or not skill:
            raise InputError(f"{where}缺 skill")
        if not isinstance(case_id, (str, int)) or isinstance(case_id, bool):
            raise InputError(f"{where}的 id 必须是字符串或整数")
        runs = _count(item, "runs", where)
        triggered = _count(item, "triggered", where)
        if runs == 0:
            raise InputError(f"{where}的 runs 是 0：没跑过不能算触发率")
        if triggered > runs:
            raise InputError(f"{where}的 triggered ({triggered}) 大于 runs ({runs})")
        key = (skill, case_id)
        if key in indexed:
            raise InputError(f"结果里 {skill}#{case_id} 出现了两次")
        indexed[key] = {"skill": skill, "id": case_id,
                        "runs": runs, "triggered": triggered}
    return indexed


def score(root: str, results: dict[tuple[str, Any], dict[str, Any]],
          threshold: float) -> dict[str, Any]:
    cases = _cases(root)
    per_skill: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    missing: list[str] = []

    for case in cases:
        skill, case_id = case["skill"], case.get("id")
        bucket = per_skill.setdefault(skill, {"total": 0, "passed": 0, "failures": 0})
        bucket["total"] += 1
        record = results.get((skill, case_id))
        if record is None:
            missing.append(f"{skill}#{case_id}")
            bucket["failures"] += 1
            continue
        rate = record["triggered"] / record["runs"]
        expected = bool(case.get("should_trigger"))
        passed = rate >= threshold if expected else rate < threshold
        if passed:
            bucket["passed"] += 1
            continue
        bucket["failures"] += 1
        failures.append({
            "skill": skill,
            "id": case_id,
            "expected": expected,
            "rate": round(rate, 3),
            "runs": record["runs"],
            "triggered": record["triggered"],
            "query": case.get("query", ""),
        })

    return {
        "threshold": threshold,
        "total": len(cases),
        "passed": len(cases) - len(failures) - len(missing),
        "failures": failures,
        "missing": missing,
        "per_skill": per_skill,
    }


def render(report: dict[str, Any]) -> str:
    lines = [f"触发评测（阈值 {report['threshold']}）", ""]
    lines.append(f"{'skill':<18}{'用例':>6}{'通过':>6}{'未过':>6}")
    lines.append("-" * 40)
    for skill, bucket in report["per_skill"].items():
        lines.append(f"{skill:<18}{bucket['total']:>6}{bucket['passed']:>6}"
                     f"{bucket['failures']:>6}")
    lines.append("")
    lines.append(f"合计 {report['total']} 条，通过 {report['passed']}，"
                 f"未过 {len(report['failures'])}，未记录 {len(report['missing'])}")
    for item in report["failures"]:
        want = "应触发" if item["expected"] else "不应触发"
        lines.append(f"  ✗ [{item['skill']}#{item['id']}] {want}，实际 {item['triggered']}"
                     f"/{item['runs']}：{item['query']}")
    if report["missing"]:
        lines.append("  未记录的用例：" + "，".join(report["missing"][:8])
                     + ("…" if len(report["missing"]) > 8 else ""))
    return "\n".join(lines)


def _write(path: str, payload: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise InputError(f"写不出 {path}：{exc}") from exc


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="触发评测：生成模板与算分")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="仓库根（默认本仓库）")
    parser.add_argument("--list", action="store_true", help="列出全部触发用例")
    parser.add_argument("--template", metavar="OUT", help="写出待记录的结果模板")
    parser.add_argument("--score", metavar="RESULTS", help="给结果文件算分")
    parser.add_argument("--runs", type=int, default=3, help="--template 时每条跑几次（默认 3）")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"触发率阈值（默认 {DEFAULT_THRESHOLD}）")
    parser.add_argument("--json", action="store_true", help="--score 时输出 JSON")
    args = parser.parse_args(argv)

    modes = [bool(args.list), bool(args.template), bool(args.score)]
    if sum(modes) != 1:
        parser.print_help()
        return 2
    try:
        if args.list:
            return cmd_list(args.root)
        if args.template:
            return cmd_template(args.root, args.template, args.runs)
        results = _load_results(args.score)
        report = score(args.root, results, args.threshold)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(render(report))
        return 0 if not report["failures"] and not report["missing"] else 1
    except InputError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
