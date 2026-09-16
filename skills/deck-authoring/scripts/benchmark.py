#!/usr/bin/env python3
"""固定基准（§53/§54）—— 系统升级必跑，指标落盘可对比。

## 为什么需要它

488 条测试证明"没坏"，证明不了"没变差"：测试是阈值的（0 个问题就绿），
基准是**数值的**（密度分布/焦点/层级/版式多样性每次都记下来）。升级前跑
一份、升级后跑一份、`--compare` 对一下 —— "这次改动让图表页更挤了没有"
从感觉变成数字。

## 指标口径（全部实测，不估）

| 指标 | 来源 | §54 对应 |
| --- | --- | --- |
| check_problems / check_notes | check.check（真浏览器） | overflow / overlap / asset failure 的合集 |
| script_errors | measure 的 console 错误 | 页面报错 |
| render_ms | perf_counter（**机器相关，仅参考**） | render time |
| reproducible / deterministic | 渲两次逐字节比 / 编两次全等比 | determinism（§41） |
| densities | hierarchy.density_share 逐页 | layout score 的原始料 |
| focal_issues / budget_issues | hierarchy 三尺 | visual score 的原始料 |
| unique_kinds / max_consecutive | 版式序列 | variant diversity / repetition rate |

不采的（诚实留白）：repair iterations（Repair 引擎未建）、export 回读
（慢，测试套件里有 test_pdf/test_pptx_native 盖着）、human rating（人的事）。

缺图时用 `plate.sample()` 造确定性测试卡 —— 基准量的是**版面几何**不是内容
真伪，测试卡不进交付、只进基准跑（deliver.py 的"缺图=ERROR"管交付那条路）。

跑法：
    python3 scripts/benchmark.py                          # 跑基线，打印
    python3 scripts/benchmark.py --out bench.json         # 落盘
    python3 scripts/benchmark.py --compare bench.json     # 对比基线（回归非零退出）
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name: str):
    path = os.path.join(HERE, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_deck_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")
render = _load_sibling("render")
measure_mod = _load_sibling("measure")
check_mod = _load_sibling("check")
compile_mod = _load_sibling("compile")
hierarchy_mod = _load_sibling("hierarchy")
plate = _load_sibling("plate")

# 固定基线集（§53 已覆盖的）：demo（混排短deck）/ stress（21 页全版式+
# chart-heavy+image-heavy+长中英）/ chart-intents（Chart Resolver v2 展示）。
# Table-heavy / Diagram-heavy：版式本身未建（§20 约定），建了才进基线。
FIXTURES = ("demo", "stress", "chart-intents")

# compare 时"变多就是回归"的指标（越少越好）；render_ms 只报不动。
COUNT_METRICS = ("check_problems", "script_errors", "focal_issues",
                 "budget_issues", "max_consecutive_same_kind")


def _deep_copy(obj: dict) -> dict:
    """惰性深拷贝（json 往返）。刚从磁盘读进来的数据不会坏 —— 但裸 loads
    是可抛调用，给它一个干净的兜底而不是栈。"""
    try:
        return json.loads(json.dumps(obj))
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"✗ fixture 数据无法深拷贝（含不可序列化值？）：{exc}") from exc


def run_fixture(name: str, run_dir: str) -> dict:
    """跑一份 fixture，返回它的指标（不含与其它 fixture 的比较）。"""
    spec_path = os.path.join(HERE, "..", "dev-tools", f"{name}.spec.json")
    spec = deckio.read_json(spec_path)
    # 缺图 → 确定性测试卡（见模块 docstring：量几何不量内容真伪）
    for s in spec["deck"].get("slides", []):
        img = s.get("image")
        if img and not os.path.isfile(os.path.join(run_dir, str(img))):
            plate.sample().save(os.path.join(run_dir, str(img)))

    t0 = time.perf_counter()
    html = render.render(spec)
    render_ms = round((time.perf_counter() - t0) * 1000)
    html_path = os.path.join(run_dir, f"{name}.html")
    deckio.write_text(html_path, html)

    reproducible = render.render(_deep_copy(spec)) == html
    deterministic = (compile_mod.compile_spec(spec)
                     == compile_mod.compile_spec(_deep_copy(spec)))

    measured = measure_mod.measure(html_path)
    problems = check_mod.check(spec, html_path, measured=measured)
    deck = spec["deck"]
    kinds = [s.get("type", "?") for s in deck["slides"]]

    densities = []
    for i in range(1, len(kinds) + 1):
        share = hierarchy_mod.density_share(measured, i)
        if isinstance(share, (int, float)):
            densities.append(round(share, 3))

    max_run = 1
    run = 1
    for a, b in zip(kinds, kinds[1:]):
        run = run + 1 if a == b else 1
        max_run = max(max_run, run)

    return {
        "pages": len(kinds),
        "render_ms": render_ms,              # 机器相关：只参考，不判回归
        "reproducible": reproducible,
        "deterministic": deterministic,
        "check_problems": len(problems),
        "script_errors": len(measured.get("errors") or []),
        "focal_issues": len(hierarchy_mod.focal_issues(measured, deck)),
        "budget_issues": len(hierarchy_mod.budget_issues(deck)),
        "unique_kinds": len(set(kinds)),
        "max_consecutive_same_kind": max_run,
        "densities": densities,
    }


def run_all(run_dir: str) -> dict:
    return {"schemaVersion": 1,
            "fixtures": {name: run_fixture(name, run_dir) for name in FIXTURES}}


def _fmt(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def compare(base: dict, new: dict) -> int:
    """基线对比：计数类指标变多=回归（退出码非零）；耗时只报不判。"""
    regressions = 0
    print(f"{'fixture':<14}{'指标':<26}{'基线':>10}{'本次':>10}   ")
    for name, metrics in new["fixtures"].items():
        b = (base.get("fixtures") or {}).get(name)
        if not b:
            print(f"{name:<14}（基线里没有这份 fixture —— 新增，无对比）")
            continue
        for key in COUNT_METRICS:
            if key not in b or key not in metrics:
                continue
            mark = ""
            if metrics[key] > b[key]:
                mark = " ✗ 回归"
                regressions += 1
            elif metrics[key] < b[key]:
                mark = " ✓ 变好"
            if mark or metrics[key] != b[key]:
                print(f"{name:<14}{key:<26}{b[key]:>10}{metrics[key]:>10}{mark}")
        dt = metrics["render_ms"] - b.get("render_ms", metrics["render_ms"])
        print(f"{name:<14}{'render_ms':<26}{b.get('render_ms', 0):>10}"
              f"{metrics['render_ms']:>10}   （机器相关，仅参考 {dt:+d}ms）")
    print(f"\n{'✗ 有回归' if regressions else '✓ 无回归'}"
          f"（计数类指标：{', '.join(COUNT_METRICS)}）")
    return 1 if regressions else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="固定基准（§53/§54）：升级前后各跑一份，--compare 对数值")
    ap.add_argument("--out", default=None, help="指标落盘路径（benchmark.json）")
    ap.add_argument("--compare", default=None,
                    help="与这份基线对比：计数类指标变多即回归（退出非零）")
    args = ap.parse_args(argv[1:])

    with tempfile.TemporaryDirectory(prefix="deck-bench-") as run_dir:
        result = run_all(run_dir)

    for name, m in result["fixtures"].items():
        print(f"── {name}（{m['pages']} 页 / {m['render_ms']}ms / "
              f"check {m['check_problems']} 问题 / 密度 "
              f"{min(m['densities']):.0%}~{max(m['densities']):.0%} / "
              f"版式 {m['unique_kinds']} 种 / 焦点 issue {m['focal_issues']}）")
    flags = []
    for name, m in result["fixtures"].items():
        if not m["reproducible"]:
            flags.append(f"{name} 渲两次不逐字节相同")
        if not m["deterministic"]:
            flags.append(f"{name} 编两次不相等")
        if m["script_errors"]:
            flags.append(f"{name} 有脚本报错")
    if flags:
        print("✗ " + "；".join(flags))
        return 1

    if args.out:
        deckio.write_json(args.out, result)
        print(f"✓ 已落盘 {args.out}")
    if args.compare:
        try:
            with open(args.compare, encoding="utf-8") as fh:
                base = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"✗ 读不了基线 {args.compare}：{exc}\n"
                             f"  先跑一份：benchmark.py --out {args.compare}") from exc
        return compare(base, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
