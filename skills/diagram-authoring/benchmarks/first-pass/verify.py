#!/usr/bin/env python3
"""first-pass 基准的验证器 —— 三门：语义 / 确定性校验 / 人审。

## 它量什么

「普通模型第一次生成的规格，不经人工修补能不能用」。这是一道**交付门**，
不是模型排行榜：一个 run 记 `first_pass_usable = true` 当且仅当三门全过：

1. **语义门**：清单里的每个必须节点恰好绑到一个节点（别名匹配，大小写不敏感），
   每条必须边按声明的方向存在。词汇别名永远不替代拓扑 —— 节点绑定错了就是失败。
2. **校验门**：`validate_spec` 无 error，`layout_with_retry` + `promote("showcase")`
   无阻塞项。**用 showcase 档**：基准测的是交付质量，不是草稿质量。
3. **人审门**：`run.json` 里记录 `visual_review.status`（passed/failed/skipped）。
   `skipped` 永远不能产出 `first_pass_usable = true` —— 与三档声明同一条规矩：
   自动化证据不冒充感知审查。

## 它不量什么

- 不启动模型：候选由外部 runner 生成后冻结，本脚本只验**第一次的产物**；
- 不做感知判断：渲染好不好看只能人/图像模型审，这里只收结论。

用法：
    python3 benchmarks/first-pass/verify.py \\
        --case benchmarks/first-pass/manifest.json#release-flow \\
        --candidate /path/to/candidate.diagram.json \\
        --run /path/to/run.json --json

退出码：0 = first-pass usable，1 = 有门没过，2 = 输入本身不合法。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "scripts")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_bench_{name}",
                                                 os.path.join(SCRIPTS, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


validate_spec = _load("validate_spec")
layout = _load("layout")
check_layout = _load("check_layout")


def _norm(text: str) -> str:
    """小写 + NFKC + 去空白 —— 让「Order 服务」能对上「order服务」。"""
    return "".join(unicodedata.normalize("NFKC", text).lower().split())


def bind_nodes(candidate: dict, required: list[dict]) -> tuple[dict, list[str]]:
    """把清单里的别名绑到候选节点上。返回 (别名→node_id 映射, 未绑出的说明)。"""
    nodes = candidate.get("nodes") or []
    pool = [(_norm(str(n.get("label", ""))), _norm(str(n.get("id", ""))), n)
            for n in nodes]
    binding: dict[str, str] = {}
    missing: list[str] = []
    for req in required:
        hit = None
        for alias in req["aliases"]:
            key = _norm(alias)
            for label, nid, node in pool:
                if key == label or key == nid or key in label:
                    hit = (alias, node)
                    break
            if hit:
                break
        if hit is None:
            missing.append("/".join(req["aliases"][:3]))
        else:
            binding[hit[0]] = hit[1]["id"]
    return binding, missing


def gate_semantic(case: dict, candidate: dict) -> tuple[bool, list[str]]:
    problems: list[str] = []
    binding, missing = bind_nodes(candidate, case.get("required_nodes", []))
    for name in missing:
        problems.append(f"必须节点没找到：{name}")
    # 清单声明了 kind 时连语义角色一起验 —— 词汇别名不替代角色：
    # 把「数据库」绑到一个 service 节点上，拓扑对、语义错，同样是失败。
    kinds = _load("palette").KINDS
    by_id = {str(n.get("id")): n for n in candidate.get("nodes") or []}
    for req in case.get("required_nodes", []):
        want = req.get("kind")
        if not want or want not in kinds:
            continue
        for alias, nid in binding.items():
            if _norm(alias) in {_norm(a) for a in req["aliases"]}:
                got = by_id.get(nid, {}).get("kind")
                if got != want:
                    problems.append(f"节点 {nid!r} 的 kind 是 {got!r}，清单要求 {want!r}")
    edges = candidate.get("edges") or []
    for req in case.get("required_edges", []):
        src = binding.get(req["from"])
        dst = binding.get(req["to"])
        if not src or not dst:
            continue                       # 端点缺失已报过，不重复计
        ok = any(e.get("from") == src and e.get("to") == dst for e in edges)
        if not ok:
            problems.append(f"必须边缺失或方向反了：{req['from']} → {req['to']}")
    return not problems, problems


def gate_validation(candidate: dict) -> tuple[bool, list[str], dict]:
    problems: list[str] = []
    report = validate_spec.validate(candidate)
    for item in report.errors:
        problems.append(f"规格错误 [{item['code']}] {item['where']}: {item['message']}")
    receipt: dict = {}
    if not report.errors:
        boxes = layout.boxes_from_spec(candidate)
        result, outcome, attempts = check_layout.layout_with_retry(candidate, boxes)
        outcome = outcome.promote("showcase")
        receipt = check_layout.build_receipt(candidate, result, attempts,
                                             outcome, "showcase")
        for issue in outcome.blocking:
            problems.append(f"showcase 阻塞 [{issue.check}] {issue.where}: {issue.detail}")
    return not problems, problems, receipt


def gate_review(run: dict | None) -> tuple[bool, list[str], str]:
    if not isinstance(run, dict):
        return False, ["没有 run.json —— 人审结论缺失"], "not_run"
    review = run.get("visual_review") or {}
    status = str(review.get("status", "not_run"))
    if status == "passed":
        return True, [], status
    if status == "failed":
        defects = review.get("defects") or []
        return False, [f"人审发现缺陷：{', '.join(map(str, defects)) or '未记录'}"], status
    return False, ["人审未执行（skipped）—— skipped 永远不能算 usable"], status


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="first-pass 三门验证器")
    ap.add_argument("--case", required=True,
                    help="manifest.json#case_id（或单独的 case JSON 路径）")
    ap.add_argument("--candidate", required=True, help="候选 *.diagram.json（必须是第一次的冻结产物）")
    ap.add_argument("--run", help="run 元数据（含 visual_review 结论）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    # 读 case
    try:
        if "#" in args.case:
            manifest_path, case_id = args.case.split("#", 1)
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            case = next((c for c in manifest["cases"] if c["id"] == case_id), None)
            if case is None:
                print(f"manifest 里没有 case {case_id!r}", file=sys.stderr)
                return 2
        else:
            with open(args.case, encoding="utf-8") as fh:
                case = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"case 读不了：{exc}", file=sys.stderr)
        return 2

    try:
        with open(args.candidate, encoding="utf-8") as fh:
            candidate = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"first_pass_usable": False,
                          "gates": {"semantic": "not_run", "validation": "not_run"},
                          "problems": [f"候选读不了：{exc}"]}, ensure_ascii=False))
        return 1

    run = None
    if args.run:
        try:
            with open(args.run, encoding="utf-8") as fh:
                run = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"run.json 读不了：{exc}", file=sys.stderr)
            return 2

    sem_ok, sem_problems = gate_semantic(case, candidate)
    val_ok, val_problems, receipt = gate_validation(candidate)
    rev_ok, rev_problems, rev_status = gate_review(run)

    usable = sem_ok and val_ok and rev_ok
    result = {
        "case_id": case["id"],
        "first_pass_usable": usable,
        "gates": {
            "semantic": "pass" if sem_ok else "fail",
            "validation": "pass" if val_ok else "fail",
            "visual_review": rev_status,
        },
        "problems": [*sem_problems, *val_problems, *rev_problems],
        "validation_receipt": receipt or None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if usable else 1


if __name__ == "__main__":
    sys.exit(main())
