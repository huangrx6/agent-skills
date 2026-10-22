#!/usr/bin/env python3
"""轻量 evals 执行器：把 prompts 交给可配置的 agent，可选 judge 命令。

不内置模型、不读密钥：agent/judge 都由命令行或环境变量提供，便于在本地或 CI 里
换成不同的执行器。默认只做结构校验；真正执行要显式给 --agent-cmd。

用法：
    python3 run_evals.py --check
    python3 run_evals.py --dry-run --agent-cmd 'pi -p {prompt}'
    python3 run_evals.py --agent-cmd 'pi -p {prompt}' --judge-cmd './judge.sh'
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVALS = SKILL_ROOT / "evals" / "evals.json"
DEFAULT_TIMEOUT = 300


def load_evals(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"读不到 evals 文件 {path}：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} 不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("evals"), list):
        raise ValueError("evals 文件顶层要包含 evals 数组")
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, item in enumerate(data["evals"]):
        where = f"evals[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{where} 不是对象")
        for key in ("id", "prompt", "expected_output"):
            if key not in item:
                raise ValueError(f"{where} 缺 {key}")
        if not isinstance(item["id"], int) or item["id"] in seen:
            raise ValueError(f"{where}.id 要是唯一的整数")
        seen.add(item["id"])
        for key in ("prompt", "expected_output"):
            if not isinstance(item[key], str) or not item[key].strip():
                raise ValueError(f"{where}.{key} 不能为空")
        files = item.get("files", [])
        if not isinstance(files, list):
            raise ValueError(f"{where}.files 要是数组")
        out.append(item)
    if not out:
        raise ValueError("evals 不能为空")
    return out


def render_command(template: str, values: dict[str, str], append: str | None = None) -> list[str]:
    """模板按 shell 分词；占位符替换后仍是一个 argv 元素，避免 prompt 被再拆开。"""
    parts = shlex.split(template)
    rendered = [part.replace("{prompt}", values.get("prompt", ""))
                .replace("{expected}", values.get("expected", ""))
                .replace("{actual}", values.get("actual", ""))
                for part in parts]
    if append is not None and "{prompt}" not in template:
        rendered.append(append)
    return rendered


def run_command(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout)


def write_transcript(path: Path, eval_item: dict[str, Any], agent: subprocess.CompletedProcess[str],
                     judge: subprocess.CompletedProcess[str] | None, status: str) -> None:
    lines = [
        f"# eval {eval_item['id']}",
        "",
        "## prompt",
        "",
        eval_item["prompt"],
        "",
        "## expected",
        "",
        eval_item["expected_output"],
        "",
        "## agent",
        "",
        f"exit={agent.returncode}",
        "",
        "```text",
        agent.stdout.rstrip(),
        "```",
    ]
    if agent.stderr.strip():
        lines += ["", "stderr:", "", "```text", agent.stderr.rstrip(), "```"]
    if judge is not None:
        lines += ["", "## judge", "", f"exit={judge.returncode}", "",
                  "```text", (judge.stdout + judge.stderr).rstrip(), "```"]
    lines += ["", f"## status: {status}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="运行 pingcode evals（agent/judge 可配置）")
    parser.add_argument("--evals", default=str(DEFAULT_EVALS), help="evals.json 路径")
    parser.add_argument("--check", action="store_true", help="只校验结构，不执行")
    parser.add_argument("--dry-run", action="store_true", help="打印将要执行的命令，不执行")
    parser.add_argument("--id", type=int, action="append", help="只跑指定 id，可重复")
    parser.add_argument("--limit", type=int, help="最多跑多少条")
    parser.add_argument("--agent-cmd", default=os.environ.get("PINGCODE_EVAL_AGENT"),
                        help="agent 命令模板；用 {prompt} 占位，未写占位则 prompt 追加为最后一个参数")
    parser.add_argument("--judge-cmd", default=os.environ.get("PINGCODE_EVAL_JUDGE"),
                        help="可选 judge 命令模板；支持 {prompt}/{expected}/{actual}，退出 0 为通过")
    parser.add_argument("--require-judge", action="store_true", help="没有 judge 时视为失败")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--output-dir", help="运行记录目录（默认 evals/runs/<时间>）")
    args = parser.parse_args(argv)

    try:
        evals = load_evals(Path(args.evals))
    except ValueError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    selected = [e for e in evals if not args.id or e["id"] in set(args.id)]
    if args.limit is not None:
        selected = selected[:max(0, args.limit)]
    if not selected:
        print("没有匹配的 eval", file=sys.stderr)
        return 2
    if args.check:
        print(f"✓ {len(selected)} 条 eval 结构有效")
        return 0
    if not args.agent_cmd:
        print("✗ 执行 evals 需要 --agent-cmd 或 PINGCODE_EVAL_AGENT", file=sys.stderr)
        return 2
    if args.judge_cmd and "{actual}" not in args.judge_cmd:
        print("✗ judge 命令要包含 {actual} 占位符", file=sys.stderr)
        return 2

    if args.dry_run:
        for item in selected:
            cmd = render_command(args.agent_cmd, {"prompt": item["prompt"]}, append=item["prompt"])
            print(f"[{item['id']}] {shlex.join(cmd)}")
            if args.judge_cmd:
                print("    judge: " + shlex.join(render_command(
                    args.judge_cmd, {"prompt": item["prompt"],
                                     "expected": item["expected_output"], "actual": "<agent output>"})))
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else SKILL_ROOT / "evals" / "runs" / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    failed = 0
    for item in selected:
        cmd = render_command(args.agent_cmd, {"prompt": item["prompt"]}, append=item["prompt"])
        try:
            agent = run_command(cmd, args.timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"✗ eval {item['id']} agent 启动失败：{exc}", file=sys.stderr)
            results.append({"id": item["id"], "status": "error", "error": str(exc)})
            failed += 1
            continue
        judge: subprocess.CompletedProcess[str] | None = None
        status = "recorded"
        if args.judge_cmd:
            judge_cmd = render_command(args.judge_cmd, {
                "prompt": item["prompt"], "expected": item["expected_output"],
                "actual": agent.stdout,
            })
            try:
                judge = run_command(judge_cmd, args.timeout)
            except (OSError, subprocess.TimeoutExpired) as exc:
                status = "error"
                print(f"✗ eval {item['id']} judge 启动失败：{exc}", file=sys.stderr)
            else:
                status = "pass" if judge.returncode == 0 else "fail"
        elif args.require_judge:
            status = "fail"
        if agent.returncode != 0 and status == "recorded":
            status = "agent-error"
        if status not in ("pass", "recorded"):
            failed += 1
        path = output_dir / f"{item['id']:02d}.md"
        write_transcript(path, item, agent, judge, status)
        results.append({"id": item["id"], "status": status, "agent_exit": agent.returncode,
                        "transcript": str(path)})
        print(f"{'✓' if status == 'pass' else '·'} {item['id']:02d} {status} → {path}")

    (output_dir / "results.json").write_text(
        json.dumps({"status": "fail" if failed else "ok", "results": results},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(selected) - failed}/{len(selected)} 通过；记录在 {output_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
