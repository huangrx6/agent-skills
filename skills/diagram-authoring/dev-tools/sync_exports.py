#!/usr/bin/env python3
"""Refresh existing exports; create new formats only when explicitly requested.

Emitters stay local and dependency-free. Authors run this after changing a native
diagram. With no sibling exports and no --format, no renderer or file is created.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile

FORMATS = {"excalidraw": ("png", "svg"), "drawio": ("png", "svg", "pdf", "jpg"), "mermaid": ("png", "svg")}
SUFFIXES = {".excalidraw": "excalidraw", ".drawio": "drawio", ".mmd": "mermaid"}
OPTIONS = {
    "mermaid": {"scale", "padding"},
    "excalidraw": {"scale", "padding", "width", "height", "aspect"},
    "drawio": {"scale", "border", "width", "height", "page_index"},
}


def load_exporter(backend):
    spec = importlib.util.spec_from_file_location(
        f"_sync_export_{backend}", Path(__file__).with_name(f"export_{backend}.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 export_{backend}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_options(path, backend, overrides):
    options = {}
    if path.exists():
        recipe = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(recipe, dict) or recipe.get("version") != 1
                or recipe.get("backend") != backend or set(recipe) != {"version", "backend", "options"}):
            raise ValueError("导出配置需要 version=1、匹配的 backend 和 options")
        options = recipe["options"]
        if not isinstance(options, dict):
            raise ValueError("导出 options 必须为对象")
    options = {**options, **overrides}
    if set(options) - OPTIONS[backend]:
        raise ValueError(f"{backend} 不支持导出参数：{sorted(set(options) - OPTIONS[backend])}")
    for key, value in options.items():
        if key == "aspect":
            if not isinstance(value, str):
                raise ValueError("aspect 必须为宽:高字符串")
        elif type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{key} 必须为有限非负数")
        elif key in ("scale", "width", "height", "page_index") and value == 0:
            raise ValueError(f"{key} 必须大于 0")
    return options


def render(source, staged, options):
    engine = load_exporter(SUFFIXES[source.suffix])
    if source.suffix == ".excalidraw":
        result = engine.export(str(source),
                               str(staged["png"]) if "png" in staged else None,
                               str(staged["svg"]) if "svg" in staged else None, **options)
        if not result["ok"]:
            raise RuntimeError(result.get("message", "官方导出失败"))
    else:
        for fmt, path in staged.items():
            result = engine.export(str(source), str(path), fmt=fmt, **options)
            if not result["ok"]:
                raise RuntimeError(f"{fmt}：{result.get('message', '官方导出失败')}")
    for fmt, path in staged.items():
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError(f"导出器未产生有效的 {fmt} 文件")


def publish(staged, before):
    """Publish complete files. Roll back ordinary write failures, not OS crashes."""
    committed = []
    try:
        for target, temp in staged.items():
            os.replace(temp, target)
            committed.append(target)
    except OSError as error:
        failures = []
        for target in reversed(committed):
            try:
                if before[target] is None:
                    target.unlink()
                else:
                    restore = staged[target]
                    restore.write_bytes(before[target])
                    os.replace(restore, target)
            except OSError as rollback_error:
                failures.append(f"{target}: {rollback_error}")
        if failures:
            raise OSError(f"发布失败且部分回滚失败：{failures}；原错误：{error}") from error
        raise


def sync(source, formats=(), **overrides):
    source = Path(source).absolute()
    try:
        backend = SUFFIXES.get(source.suffix)
        if backend not in FORMATS or not source.is_file():
            raise ValueError("需要存在的 .excalidraw、.drawio 或 .mmd 文件")
        if set(formats) - set(FORMATS[backend]):
            raise ValueError(f"{backend} 仅支持 {', '.join(FORMATS[backend])}")
        selected = [fmt for fmt in FORMATS[backend]
                    if fmt in formats or source.with_suffix('.' + fmt).is_file()]
        if not selected:
            return {"ok": True, "status": "not-requested", "outputs": [],
                    "message": "没有已存在的导出，未生成图片；需要时用 --format 指定。"}
        # A shared basename with two native backends has ambiguous ownership.
        others = [source.with_suffix(suffix) for suffix in SUFFIXES if suffix != source.suffix]
        if any(other.exists() for other in others):
            raise ValueError("同名的多种可编辑文件共用导出名，请先区分文件名再同步")
        recipe = source.parent / ".source" / (source.stem + ".exports.json")
        known_recipe = recipe.exists()
        options = read_options(recipe, backend, overrides)
        engine = load_exporter(backend)
        defaults = {"scale": 2.0}
        defaults.update({"padding": engine.DEFAULT_PADDING} if backend in ("excalidraw", "mermaid")
                        else {"border": engine.DEFAULT_BORDER})
        options = {**defaults, **options}
        targets = {fmt: source.with_suffix('.' + fmt) for fmt in selected}
        all_targets = [*targets.values(), recipe]
        if any(p.is_symlink() for p in all_targets):
            raise ValueError("导出目标或配置是符号链接，请明确实际文件路径后同步")
        before = {p: p.read_bytes() if p.exists() else None for p in all_targets}
        digest = hashlib.sha256(source.read_bytes()).digest()
        # Same filesystem permits atomic per-file replacement. The directory is
        # temporary and removed on both success and failure.
        with tempfile.TemporaryDirectory(prefix=".exports-", dir=source.parent) as td:
            folder = Path(td)
            staged = {fmt: folder / target.name for fmt, target in targets.items()}
            render(source, staged, options)
            if hashlib.sha256(source.read_bytes()).digest() != digest:
                raise RuntimeError("导出期间原生图发生变化，未覆盖已有图片；请重新同步")
            for path, previous in before.items():
                if (path.read_bytes() if path.exists() else None) != previous:
                    raise RuntimeError(f"导出期间目标被修改，未覆盖：{path}")
            recipe_temp = folder / "exports.json"
            recipe_temp.write_text(json.dumps({"version": 1, "backend": backend,
                                               "options": options}, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
            created_dir = not recipe.parent.exists()
            recipe.parent.mkdir(exist_ok=True)
            try:
                publish({**{targets[fmt]: path for fmt, path in staged.items()}, recipe: recipe_temp}, before)
            finally:
                if created_dir and not any(recipe.parent.iterdir()):
                    recipe.parent.rmdir()
        result = {"ok": True, "status": "exported", "outputs": [str(p) for p in targets.values()],
                  "options": options, "recipe": str(recipe)}
        if not known_recipe and any(before[p] is not None for p in targets.values()):
            result["note"] = "旧导出参数无记录；本次使用显示的默认值/显式参数，后续沿用保存的配置。"
        return result
    except (ValueError, OSError, RuntimeError) as error:
        return {"ok": False, "status": "failed", "message": str(error),
                "note": "同步未完成；已有预览可能落后于可编辑图，不能作为最新结果交付。"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--format", dest="formats", action="append", default=[],
                        choices=sorted({fmt for values in FORMATS.values() for fmt in values}),
                        help="显式新增的格式；未指定时只刷新已存在格式，可重复")
    parser.add_argument("--page-index", type=int, help="draw.io 页码，从 1 开始")
    parser.add_argument("--scale", type=float)
    parser.add_argument("--padding", type=int, help="Excalidraw/Mermaid 外边距")
    parser.add_argument("--border", type=float, help="draw.io 外边距")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--aspect")
    args = parser.parse_args(argv)
    overrides = {key: value for key, value in vars(args).items()
                 if key not in ("source", "formats") and value is not None}
    result = sync(args.source, args.formats, **overrides)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
