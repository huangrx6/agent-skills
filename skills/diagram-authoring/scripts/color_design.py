#!/usr/bin/env python3
"""Project-owned color designs, not a closed catalogue of named palettes.

Colors and their application are separate from the diagram's factual spec.
This module only reads data; source URLs are provenance, never fetched/executed.
"""
from __future__ import annotations

import argparse
import colorsys
from copy import deepcopy
import json
import math
from pathlib import Path
import re

HEX = re.compile(r"#[0-9a-fA-F]{6}\Z")
FIELDS = {"version", "name", "source", "rationale", "canvas", "ink", "accent",
          "critical", "swatches", "by_kind", "by_node", "by_group", "strength"}
DEFAULT_STRENGTH = {"normal": .12, "primary": .30, "critical": .18, "surface": .035}


def read(value):
    if isinstance(value, (str, Path)):
        value = json.loads(Path(value).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("配色文件必须是 JSON 对象")
    return deepcopy(value)


def resolve(value, p):
    """Resolve all actual color pairs and record contrast; do not mutate input."""
    raw = read(value)
    if set(raw) - FIELDS:
        raise ValueError(f"未知配色字段：{sorted(set(raw) - FIELDS)}")
    if type(raw.get("version")) is not int or raw["version"] != 1:
        raise ValueError("配色 version 必须为 1")
    for key in ("name", "source", "rationale"):
        if key in raw and not isinstance(raw[key], str):
            raise ValueError(f"{key} 必须为字符串")
    for key in ("canvas", "ink", "accent", "critical"):
        if not isinstance(raw.get(key), str) or not HEX.fullmatch(raw[key]):
            raise ValueError(f"{key} 必须为 #RRGGBB")
    canvas, ink = raw["canvas"], raw["ink"]
    if p.contrast(ink, canvas) < 4.5:
        raise ValueError("文字 ink 与画布 canvas 对比度不足 4.5；请调整其中一个，原色未被修改")
    swatches = raw.get("swatches", {})
    if not isinstance(swatches, dict):
        raise ValueError("swatches 必须是名称到 HEX 的对象")
    for name, color in swatches.items():
        if not isinstance(name, str) or not name or name in {"accent", "critical"}:
            raise ValueError("色名非空，且不能覆盖 accent / critical")
        if not isinstance(color, str) or not HEX.fullmatch(color):
            raise ValueError(f"swatches.{name} 必须为 #RRGGBB")
    swatches = {**swatches, "accent": raw["accent"], "critical": raw["critical"]}
    assignments = {}
    for key in ("by_kind", "by_node"):
        mapping = raw.get(key, {})
        if not isinstance(mapping, dict):
            raise ValueError(f"{key} 必须是对象")
        for target, name in mapping.items():
            if not isinstance(target, str) or not target:
                raise ValueError(f"{key} 的目标必须是非空字符串")
            if key == "by_kind" and target not in p.DEFAULT_KIND_LEVELS:
                raise ValueError(f"未知节点角色：{target}")
            if not isinstance(name, str) or name not in swatches:
                raise ValueError(f"{key}.{target} 引用了不存在的色名：{name!r}")
        assignments[key] = dict(mapping)
    strength = raw.get("strength", {})
    if not isinstance(strength, dict) or set(strength) - set(DEFAULT_STRENGTH):
        raise ValueError("strength 只支持 normal / primary / critical / surface")
    strength = {**DEFAULT_STRENGTH, **strength}
    for key, value in strength.items():
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"strength.{key} 必须在 0–1 之间")
    group_designs = raw.get("by_group", {})
    if not isinstance(group_designs, dict):
        raise ValueError("by_group 必须是分组 ID 到 {color, strength} 的对象")
    group_fills = {}
    for group_id, entry in group_designs.items():
        if not isinstance(group_id, str) or not group_id or not isinstance(entry, dict):
            raise ValueError("by_group 的分组 ID 非空，值必须为对象")
        if (set(entry) - {"color", "strength"} or not isinstance(entry.get("color"), str)
                or entry["color"] not in swatches):
            raise ValueError(f"by_group.{group_id} 需要已有色名 color，可选 strength")
        ratio = entry.get("strength", strength["normal"])
        if type(ratio) not in (float, int) or not math.isfinite(ratio) or not 0 <= ratio <= 1:
            raise ValueError(f"by_group.{group_id}.strength 必须在 0–1 之间")
        group_fills[group_id] = p._mix(canvas, swatches[entry["color"]], ratio)
    checks, adjustments = [], []

    def check(subject, foreground, background, minimum):
        ratio = p.contrast(foreground, background)
        checks.append(dict(subject=subject, foreground=foreground, background=background,
                           minimum=minimum, ratio=round(ratio, 3), passed=ratio >= minimum))
        if ratio < minimum:
            raise ValueError(f"{subject} 对比度不足 {minimum}: {ratio:.2f}")

    def text_on(background):
        if p.contrast(ink, background) >= 4.5:
            return ink
        return max(("#000000", "#FFFFFF"), key=lambda c: p.contrast(c, background))

    # Ordinary groups and notes are supporting surfaces, not primary accents.
    # Explicit group level=accent still exists when emphasis is intentional.
    surface = p._mix(canvas, ink, strength["surface"])
    surrounds = (canvas, surface, *group_fills.values())

    def boundary(color, fill, subject):
        # A boundary may touch the canvas or a group surface. Keep the input
        # swatch intact; only derive a usable line color, recorded below.
        backgrounds = (*surrounds, fill)
        for target in (ink, "#000000", "#FFFFFF"):
            for step in range(21):
                candidate = p._mix(color, target, step / 20)
                if all(p.contrast(candidate, bg) >= 3 for bg in backgrounds):
                    if candidate.upper() != color.upper():
                        adjustments.append(dict(subject=subject, source=color, derived=candidate))
                    return candidate
        raise ValueError(f"{subject} 无法同时区分填充和背景；请调整 strength 或画布")

    def pair(color, ratio, subject):
        fill = p._mix(canvas, color, ratio)
        stroke, text = boundary(color, fill, subject), text_on(fill)
        check(subject + ":text", text, fill, 4.5)
        for index, background in enumerate((*surrounds, fill)):
            check(subject + f":boundary-{index}", stroke, background, 3)
        return {"fill": fill, "stroke": stroke, "text": text}

    levels = {"neutral": pair(p._mix(canvas, ink, .48), 0, "neutral"),
              "tint": pair(p._mix(canvas, ink, .48), 0, "surface-boundary"),
              "accent": pair(raw["accent"], strength["primary"], "primary"),
              "critical": pair(raw["critical"], strength["critical"], "critical")}
    levels["tint"]["fill"] = surface
    levels["tint"]["text"] = text_on(surface)
    check("surface:text", levels["tint"]["text"], surface, 4.5)
    check("surface:boundary", levels["tint"]["stroke"], surface, 3)
    groups = {}
    for group_id, fill in group_fills.items():
        subject = "group:" + group_id
        groups[group_id] = {"fill": fill, "stroke": levels["tint"]["stroke"], "text": text_on(fill)}
        check(subject + ":text", groups[group_id]["text"], fill, 4.5)
        check(subject + ":boundary", groups[group_id]["stroke"], fill, 3)
    colors = {name: pair(color, strength["normal"], name) for name, color in swatches.items()}
    primary = {name: pair(color, strength["primary"], name + ":primary")
               for name, color in swatches.items()}
    edge = boundary(p._mix(canvas, ink, .60), canvas, "edge")
    for background in surrounds:
        check("edge", edge, background, 3)
    check("canvas:text", ink, canvas, 4.5)
    return dict(raw=raw, canvas=canvas, ink=ink, levels=levels, colors=colors,
                primary=primary, edge=edge, groups=groups, **assignments,
                report=dict(status="pass", basis="resolved-solid-color-pairs",
                            checks=checks, adjustments=adjustments,
                            limits=["不检查透明度、图标像素、纹理或色觉缺陷；不代表审美或完整无障碍验收"]))


def propose(seed, *, canvas="#FCFCFA", ink="#20252B", offsets=(40, 180)):
    """Any seed and any hue offsets; a reproducible starting point, not taste QA."""
    if not isinstance(seed, str) or not HEX.fullmatch(seed):
        raise ValueError("seed 必须为 #RRGGBB")
    offsets = tuple(offsets)
    if any(not math.isfinite(x) for x in offsets):
        raise ValueError("色相偏移必须为有限数字")
    rgb = tuple(int(seed[i:i+2], 16) / 255 for i in (1, 3, 5))
    h, light, sat = colorsys.rgb_to_hls(*rgb)
    swatches = {}
    for index, offset in enumerate(offsets, 1):
        color = colorsys.hls_to_rgb((h + offset / 360) % 1, light, sat)
        swatches[f"companion-{index}"] = "#{:02X}{:02X}{:02X}".format(*(round(x*255) for x in color))
    return dict(version=1, name="主色派生候选", source=f"seed {seed}; hue offsets {list(offsets)}",
                rationale="色相偏移仅生成候选；用真实图调整明暗、面积和角色分配。",
                canvas=canvas, ink=ink, accent=seed, critical="#C44343", swatches=swatches,
                by_kind={}, by_node={}, strength=dict(DEFAULT_STRENGTH))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design", nargs="?", help="检查项目配色 JSON")
    parser.add_argument("--seed", help="任意 #RRGGBB 主色，生成候选 JSON")
    parser.add_argument("--offsets", default="40,180", help="任意逗号分隔色相角度；负值用 --offsets=-30,30")
    parser.add_argument("--canvas", default="#FCFCFA")
    parser.add_argument("--ink", default="#20252B")
    parser.add_argument("-o", "--out", type=Path)
    args = parser.parse_args(argv)
    import palette
    try:
        if bool(args.seed) == bool(args.design):
            raise ValueError("提供配色文件或 --seed，二者选一")
        if args.seed:
            result = propose(args.seed, canvas=args.canvas, ink=args.ink,
                             offsets=[float(x) for x in args.offsets.split(",") if x.strip()])
            resolve(result, palette)
        else:
            result = resolve(args.design, palette)["report"]
        payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            args.out.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        return 0
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
