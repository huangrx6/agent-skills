#!/usr/bin/env python3
"""风格层工具 —— 列表 / 契约体检 / 摘要 / 联系表。

## 为什么需要一个（而不是"多个目录自己管自己"）

风格是**加一个目录就算加一套**（`styles/<name>/{style.json,skin.css}`，不碰任何 .py）。
这让扩展很便宜，代价是**契约是隐式的**：少一个字号档、少一个 motion 键、色板过不了
对比度门槛 —— 渲染器都不会报错，skin 里 `var(--t-missing)` 只会静默地退回默认值，
那一页看着"就是有点怪"，查起来极贵。

所以这个工具干三件事：

1. **体检**（`--check`）：每套风格对着契约过一遍，**缺什么当场指名报出**。
2. **摘要**（`style.py <名字>`）：一眼看全这套风格的取值，不用翻 style.json。
3. **联系表**（`--sheet`）：**所有风格 × 同一份 demo** 拼成一张图。
   「先出三个方向让人选」那个流程要的是画面，不是风格名 —— 一张图比三段描述管用。

跑法：
    python3 scripts/style.py                  # 列出所有风格 + 契约状态
    python3 scripts/style.py swiss-grid       # 一套风格的摘要
    python3 scripts/style.py --check          # 只体检，有问题退出 1
    python3 scripts/style.py --sheet -o /tmp/styles.png
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
STYLES_DIR = os.path.join(SKILL_DIR, "styles")
DEMO = os.path.join(SKILL_DIR, "dev-tools", "demo.spec.json")


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
ink = _load_sibling("ink")
shots = _load_sibling("shots")

# 一套风格必须提供的顶层键。少一个 → 渲染器或校验层会踩空。
REQUIRED_KEYS = ("version", "label", "temperature", "reference", "note", "colorSets",
                 "ink", "contrast", "type", "fonts", "texture", "decor",
                 "misregistration", "viewerBackground", "motion")
# motion 里的键：时间轴与 JS 引擎都直接取，少一个就是运行时塌掉。
REQUIRED_MOTION = ("easing", "cssEase", "enterMs", "staggerMs", "titleHoldMs",
                   "holdMs", "readPerItemMs")
# 每套色板必须有的四个颜色（缺一个 ink.py 推导文字色时就没得算）
REQUIRED_COLORS = ("primary", "secondary", "background")

VALID_EASING = ("expoOut", "overshoot")


def available() -> list[str]:
    return render.style_names()          # 双根：用户 styles/ + 开发夹具


def load(name: str) -> dict:
    """读一套风格（返回渲染器用的那个形状：`tokens` + `skin`）。"""
    if name not in available():
        raise SystemExit(f"✗ 没有风格 {name!r}（现有：{available()}）")
    return render.load_style(name)


def audit(name: str) -> list[str]:
    """对一套风格做契约体检，返回问题清单（空的 = 合格）。

    只报**客观缺失/越界**：少键、少档位、色板不达门槛、缓动是 slop。
    至于"好不好看"不在这里 —— 那个只能看联系表。
    """
    problems: list[str] = []
    folder = render.style_folder(name)
    if folder is None:
        return [f"没有风格 {name!r}（现有：{available()}）"]
    raw = deckio.read_json(os.path.join(folder, "style.json"))
    tokens = raw
    for key in REQUIRED_KEYS:
        if key not in raw:
            problems.append(f"{name}/style.json 缺顶层键 {key!r}")
    if problems:
        return problems                     # 连键都不齐，后面的检查没有意义

    missing_tiers = sorted(render.REQUIRED_TYPE_TIERS - set(raw["type"]))
    if missing_tiers:
        problems.append(f"{name} 的 type 级数少了 {missing_tiers} —— skin 里 "
                        f"var(--t-…) 拿不到值会静默退回默认字号，最难看的那种 bug")

    # 阶梯的「同级碰撞」与倒挂（实测：4 套风格 subtitle 与 bullet 同字号 ——
    # 两级之间没有层级可言；那正是「中段挤成一团」的来源）。
    tiers = raw["type"]
    if tiers.get("subtitle") == tiers.get("bullet"):
        problems.append(f"{name} 的 subtitle({tiers.get('subtitle')}) == "
                        f"bullet({tiers.get('bullet')}) —— 同级碰撞，抬 subtitle 一档")
    if tiers.get("bulletSmall", 0) >= tiers.get("bullet", 1):
        problems.append(f"{name} 的 bulletSmall({tiers.get('bulletSmall')}) ≥ "
                        f"bullet({tiers.get('bullet')}) —— 倒挂")
    if tiers.get("bullet", 0) >= tiers.get("bulletLarge", 1):
        problems.append(f"{name} 的 bullet({tiers.get('bullet')}) ≥ "
                        f"bulletLarge({tiers.get('bulletLarge')}) —— 倒挂")

    for key in REQUIRED_MOTION:
        if key not in raw["motion"]:
            problems.append(f"{name} 的 motion 缺 {key!r}")
    easing = raw["motion"].get("easing")
    if easing not in VALID_EASING:
        problems.append(f"{name} 的 motion.easing={easing!r} 不认识（只有 {VALID_EASING}）")
    css_ease = raw["motion"].get("cssEase", "")
    # `linear` / `ease` 是 AI slop 的第一特征：所有元素同速，数字元素没有重量感。
    if css_ease in ("linear", "ease", "ease-in-out"):
        problems.append(f"{name} 的 motion.cssEase={css_ease!r} 是匀速系 —— "
                        f"换成 expoOut 那类有阻尼的曲线")

    limits = raw["contrast"]
    for cs_name, cs in raw["colorSets"].items():
        for key in REQUIRED_COLORS:
            if key not in cs:
                problems.append(f"{name} 色板 {cs_name!r} 缺 {key!r}")
        if any(key not in cs for key in REQUIRED_COLORS):
            continue
        # 文字色与 ink.py **同一处**推导（declared 就用声明的，否则走叠印）——
        # 这里不重抄那套数学，只是拿来判门槛。
        ratio = ink.contrast(ink.text_color(cs), cs["background"])
        if ratio < limits["minBody"]:
            problems.append(f"{name} 色板 {cs_name!r} 的文字色对比度 {ratio:.2f} < "
                            f"{limits['minBody']} —— 换色板，不要放宽门槛")

    # decor 声明与落点要一致：声明了类型却没有 zones，装饰就没有地方放。
    decor = raw["decor"]
    if decor.get("types") and not decor.get("zones"):
        problems.append(f"{name} 声明了 decor.types={decor['types']} 但 decor.zones 是空的")
    if decor.get("zones") and not decor.get("types"):
        problems.append(f"{name} 声明了 decor.zones 但 decor.types 是空的")
    return problems


def summarize(name: str) -> str:
    raw = deckio.read_json(os.path.join(render.style_folder(name),
                                         "style.json"))
    tokens = raw
    mo = raw["motion"]
    type_bits = " ".join(f"{k}={v}" for k, v in raw["type"].items()
                         if isinstance(v, (int, float)) and not isinstance(v, bool))
    out = [
        f"风格 {name}",
        f"  名字      {raw['label']}（{raw['temperature']}）",
        f"  参考      {raw['reference']}",
        f"  字体      display={raw['fonts']['display'].split(',')[0]}"
        f"  body={raw['fonts']['body'].split(',')[0]}",
        f"  字号      {type_bits}",
        f"  运动      {mo['easing']} enter={mo['enterMs']}ms stagger={mo['staggerMs']}ms "
        f"titleHold={mo['titleHoldMs']}ms hold={mo['holdMs']}ms",
        f"  装饰      types={raw['decor'].get('types')} zones={raw['decor'].get('zones')}",
        f"  底色      {raw['viewerBackground']}",
        "",
        "  色板（文字色对比度）",
    ]
    limits = raw["contrast"]
    for cs_name, cs in raw["colorSets"].items():
        ratio = ink.contrast(ink.text_color(cs), cs["background"])
        ok = "✓" if ratio >= limits["minBody"] else "✗"
        out.append(f"    {ok} {cs_name:<12}{cs['background']}  文字 {ratio:5.2f}  "
                   f"主 {cs['primary']} / 副 {cs['secondary']}")
    return "\n".join(out)


def sheet(path: str, styles: list[str] | None = None, scale_pct: int = 42,
          spec_path: str | None = None, pages: list[int] | None = None) -> str:
    """所有风格 × 同一份内容 → 一张联系表。

    - 缺省用 `dev-tools/demo.spec.json` 的**封面 + 第 2 页**（选风格看这两页最有效）。
    - 传 `spec_path` / `pages` 就变成**矩阵**：某一份 deck 的第 N 页在全部风格下的样子。
      压测就是用这个看 8 风格 × 各版式（`--spec dev-tools/stress.spec.json --pages 9,14`）。

    `scale_pct` 是**整数百分比**而不是浮点缩放：尺寸用整数算术算出来，
    不必再调 `int()` 转一道（那只是多一个抛异常的地方）。
    """
    from PIL import Image, ImageDraw   # noqa: PLC0415

    names = styles or available()
    if not names:
        raise SystemExit("✗ 一套风格都没有")
    spec = deckio.read_json(spec_path or DEMO)
    tiles: list[tuple[str, list[str]]] = []
    tmp = tempfile.mkdtemp(prefix="deck-sheet-")
    for name in names:
        raw = deckio.read_json(os.path.join(render.style_folder(name),
                                             "style.json"))
        probe = copy.deepcopy(spec)                 # 深拷（不用 JSON 绕一圈）
        probe["deck"]["style"] = name
        probe["deck"]["colorSet"] = next(iter(raw["colorSets"]))
        html_path = os.path.join(tmp, f"{name}.html")
        deckio.write_text(html_path, render.render(probe))
        count = max(pages) if pages else 6
        rendered = shots.shoot(html_path, os.path.join(tmp, name), render.SLIDE_W,
                               render.SLIDE_H, count)
        want = [p - 1 for p in pages] if pages else [0, 1]
        picked = [rendered[k] for k in want if 0 <= k < len(rendered)]
        if not picked:
            raise SystemExit(f"✗ --pages 越界：这份 deck 只有 {len(rendered)} 页")
        tiles.append((f"{name}（{raw['temperature']}）", picked))

    tw = render.SLIDE_W * scale_pct // 100
    th = render.SLIDE_H * scale_pct // 100
    pad, head = 14, 30
    width = pad * 2 + tw * 2 + 8
    height = pad + (head + th + 10) * len(tiles)
    board = Image.new("RGB", (width, height), (20, 20, 22))
    draw = ImageDraw.Draw(board)
    for i, (label, imgs) in enumerate(tiles):
        y = pad + i * (head + th + 10)
        draw.text((pad, y + 8), label, fill=(232, 232, 232))
        for k, page in enumerate(imgs):
            with Image.open(page) as im:
                board.paste(im.convert("RGB").resize((tw, th), Image.Resampling.LANCZOS),
                            (pad + k * (tw + 8), y + head))
    board.save(path)
    return path


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="风格层：列表 / 体检 / 摘要 / 联系表")
    ap.add_argument("name", nargs="?", default=None, help="看某套风格的摘要")
    ap.add_argument("--check", action="store_true", help="只做契约体检（有问题退出 1）")
    ap.add_argument("--sheet", default=None, metavar="PNG",
                    help="所有风格 × 同一份内容拼成一张联系表（缺省用 demo 的封面 + 第 2 页）")
    ap.add_argument("--spec", default=None, help="配合 --sheet：换一份 deck")
    ap.add_argument("--pages", default=None,
                    help="配合 --sheet：取哪几页，逗号分隔（如 9,14）")
    ap.add_argument("--json", action="store_true", help="机读输出")
    args = ap.parse_args(argv[1:])

    if args.sheet:
        picked = None
        if args.pages:
            try:
                picked = [int(x) for x in args.pages.split(",") if x.strip()]
            except ValueError as exc:
                raise SystemExit(f"✗ --pages 要是逗号分隔的页号：{exc}") from exc
        path = sheet(args.sheet, spec_path=args.spec, pages=picked)
        print(f"✓ 联系表 → {path}")
        return 0

    if args.name:
        print(summarize(args.name) if not args.json
              else json.dumps(deckio.read_json(
                  os.path.join(render.style_folder(args.name),
                               "style.json")),
                  ensure_ascii=False, indent=2))
        return 0

    names = available()
    if not names:
        raise SystemExit("✗ 一套风格都没有 —— styles/（用户）与 "
                         "dev-tools/style-fixture/（夹具）都是空的")
    reports = {n: audit(n) for n in names}
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return 1 if any(reports.values()) else 0
    if args.check:
        for n, problems in reports.items():
            if problems:
                print(f"✗ {n}")
                for p in problems:
                    print(f"    · {p}")
        bad = [n for n, p in reports.items() if p]
        if bad:
            print(f"\n✗ {len(bad)}/{len(names)} 套风格未过契约：{bad}")
            return 1
        print(f"✓ {len(names)} 套风格全部过契约（顶层键 / 字号档 / 运动 / 色板门槛 / "
              f"装饰声明一致）")
        return 0
    for n in names:
        raw = deckio.read_json(os.path.join(render.style_folder(n),
                                             "style.json"))
        problems = reports[n]
        mark = "✓" if not problems else "✗"
        print(f"  {mark} {n:<16}{raw['temperature']:<4}"
              f"{len(raw['colorSets'])} 色板  {raw['label']}")
        for p in problems:
            print(f"      · {p}")
    print(f"\n共 {len(names)} 套。看一套：style.py {names[0]}；"
          f"拼联系表：style.py --sheet -o /tmp/styles.png")
    return 1 if any(reports.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
