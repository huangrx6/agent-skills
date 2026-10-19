#!/usr/bin/env python3
"""Hand off external image generation without depending on a deck renderer.

The plan's directory is the project root. No images are generated or replaced.
Example plan (the prompt must be an authored, complete instruction):
  {"schemaVersion": 1, "project": "Demo", "images": [{
    "id": "cover", "pages": [1], "file": "assets/images/cover.png",
    "role": "concept illustration", "purpose": "Introduce the central idea",
    "target_px": [1600, 900], "aspect": "16:9", "fit": "cover",
    "focal": [65, 50], "prompt": "Complete subject, composition, style and lighting…",
    "negative": ["No text, logos or watermark"], "alt": "Description of the image"
  }]}

--brief validates the plan, then exclusively creates image-brief.md. --check
inspects actual files and returns JSON; pending/invalid assets exit nonzero.
--handoff validates the generated Markdown and HTML bindings before manual
generation; missing generated assets remain explicitly pending, not complete.
"""
from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys
import warnings
from urllib.parse import quote, unquote, urlsplit

from PIL import Image, ImageOps, UnidentifiedImageError


class PlanError(ValueError):
    """An unsafe or incomplete image plan."""


FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}
PLACEHOLDER = re.compile(
    r"〈[^〉]*〉|<[^<>]*>|\{\{.*?\}\}|\$\{[^}]*\}|\b(?:TODO|TBD)\b|"
    r"待填写|待补充|请填写|\[(?:填入|填写|insert\b|placeholder\b)[^\]]*\]",
    re.IGNORECASE | re.DOTALL,
)


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{label} 必须是非空文本")
    if "\x00" in value:
        raise PlanError(f"{label} 不能包含空字符")
    return value.strip()


def safe_path(root: Path, value, label: str = "file") -> Path:
    """Reject traversal, Windows/URL paths and symlink escapes before any IO."""
    name = _text(value, label)
    if (name != value or any(ord(char) < 32 for char in name)
            or any(char in name for char in '\\:*?"<>|`')
            or PurePosixPath(name).is_absolute()
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise PlanError(f"{label} 必须是项目目录内的相对路径，不能含绝对路径、.. 或特殊路径字符：{name}")
    try:
        target = (root / name).resolve()
    except (OSError, RuntimeError) as exc:
        raise PlanError(f"{label} 路径无法解析：{name}") from exc
    if not target.is_relative_to(root.resolve()):
        raise PlanError(f"{label} 通过符号链接逃逸项目目录：{name}")
    return target


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def load_plan(path: Path | str) -> dict:
    path = Path(path).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlanError(f"无法读取 image plan：{exc}") from exc
    if not isinstance(data, dict) or type(data.get("schemaVersion")) is not int or data["schemaVersion"] != 1:
        raise PlanError("image plan 必须为 schemaVersion: 1 的对象")
    assets = data.get("images")
    if not isinstance(assets, list) or not assets:
        raise PlanError("images 必须是非空数组；完整新稿不能用空计划免除配图交接")
    root = path.parent
    seen_ids, seen_files = set(), set()
    normalized = []
    for index, raw in enumerate(assets, 1):
        label = f"images[{index}]"
        if not isinstance(raw, dict):
            raise PlanError(f"{label} 必须是对象")
        identifier = _text(raw.get("id"), f"{label}.id")
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", identifier) or identifier in seen_ids:
            raise PlanError(f"{label}.id 必须是唯一的小写字母开头标识符")
        seen_ids.add(identifier)
        file = raw.get("file")
        target = safe_path(root, file, f"{identifier}.file")
        # casefold also protects a shared plan when later used on a case-insensitive disk.
        key = str(target).casefold()
        if key in seen_files or target == path:
            raise PlanError(f"{identifier}.file 重复或指向 plan 本身")
        seen_files.add(key)
        if Path(file).suffix.lower() not in FORMATS:
            raise PlanError(f"{identifier}.file 仅支持 .png / .jpg / .jpeg / .webp")
        pages = raw.get("pages")
        if (not isinstance(pages, list) or not pages
                or any(type(page) is not int or page < 1 for page in pages)
                or len(pages) != len(set(pages))):
            raise PlanError(f"{identifier}.pages 必须是互不重复的正整数页码数组")
        size = raw.get("target_px")
        if (not isinstance(size, list) or len(size) != 2
                or any(type(n) is not int or n <= 0 for n in size)):
            raise PlanError(f"{identifier}.target_px 必须为 [正整数宽, 正整数高]")
        ratio = size[0] / size[1]
        aspect = raw.get("aspect")
        if aspect is None:
            divisor = math.gcd(*size)
            aspect = f"{size[0] // divisor}:{size[1] // divisor}"
        if not isinstance(aspect, str) or not re.fullmatch(r"\d+(?:\.\d+)?:\d+(?:\.\d+)?", aspect):
            raise PlanError(f"{identifier}.aspect 应写成 16:9 等宽高比")
        left, right = map(float, aspect.split(":"))
        if not left or not right or not math.isfinite(left / right) or abs(left / right / ratio - 1) > .02:
            raise PlanError(f"{identifier}.aspect 与 target_px 不一致")
        fit = raw.get("fit", "cover")
        if fit not in ("cover", "contain"):
            raise PlanError(f"{identifier}.fit 只能为 cover 或 contain")
        focal = raw.get("focal", [50, 50])
        if (not isinstance(focal, list) or len(focal) != 2
                or any(not _number(n) or not 0 <= n <= 100 for n in focal)):
            raise PlanError(f"{identifier}.focal 应为 0–100 的 [水平百分比, 垂直百分比]")
        source = raw.get("source", "generated")
        if source not in ("generated", "provided"):
            raise PlanError(f"{identifier}.source 只能为 generated 或 provided")
        source_note = _text(raw.get("source_note"), f"{identifier}.source_note") if source == "provided" else ""
        prompt = _text(raw.get("prompt"), f"{identifier}.prompt") if source == "generated" else ""
        if source == "generated" and (PLACEHOLDER.search(prompt) or prompt.lower() in ("placeholder", "待定", "…", "...")):
            raise PlanError(f"{identifier}.prompt 仍有占位符，请写完整主体、构图、风格与光线")
        # A short Chinese prompt can be complete. Length is not a quality test.
        negative = raw.get("negative", [])
        if not isinstance(negative, list):
            raise PlanError(f"{identifier}.negative 必须是约束文本数组")
        negative = [_text(item, f"{identifier}.negative") for item in negative]
        if any(PLACEHOLDER.search(item) for item in negative):
            raise PlanError(f"{identifier}.negative 仍有占位符")
        optional = {}
        if "transparent" in raw:
            if type(raw["transparent"]) is not bool:
                raise PlanError(f"{identifier}.transparent 必须是布尔值")
            if raw["transparent"] and Path(file).suffix.lower() in (".jpg", ".jpeg"):
                raise PlanError(f"{identifier}.transparent 需要 PNG 或 WebP，JPEG 不支持透明通道")
            optional["transparent"] = raw["transparent"]
        if "negativeSpace" in raw:
            optional["negativeSpace"] = _text(raw["negativeSpace"], f"{identifier}.negativeSpace")
        normalized.append({
            "id": identifier, "pages": pages, "file": file,
            "role": _text(raw.get("role"), f"{identifier}.role"),
            "purpose": _text(raw.get("purpose"), f"{identifier}.purpose"),
            "target_px": size, "aspect": aspect, "fit": fit, "focal": focal,
            "prompt": prompt, "negative": negative,
            "source": source, "source_note": source_note,
            "alt": _text(raw.get("alt"), f"{identifier}.alt"), **optional,
        })
    return {"schemaVersion": 1, "project": _text(data.get("project", path.stem), "project"),
            "images": normalized, "root": root, "path": path}


def check_images(plan: dict) -> dict:
    """Only factual file validation. Passing never substitutes for visual review."""
    results = []
    for asset in plan["images"]:
        result = {"id": asset["id"], "file": asset["file"], "status": "pending", "errors": [], "warnings": []}
        target = safe_path(plan["root"], asset["file"])
        if not target.exists():
            result["errors"].append("文件缺失；按提示词生成后放入此路径")
            results.append(result)
            continue
        result["status"] = "invalid"
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(target) as probe:
                    actual_format = probe.format
                    expected = FORMATS[Path(asset["file"]).suffix.lower()]
                    if actual_format != expected:
                        result["format"] = actual_format
                        result["errors"].append(
                            f"后缀要求 {expected}，真实内容为 {actual_format}；请导出正确格式，不要只改后缀")
                        results.append(result)
                        continue
                    probe.verify()
                with Image.open(target) as probe:
                    probe.load()
                    if getattr(probe, "n_frames", 1) != 1:
                        result["errors"].append("请提供单帧静态图，避免展示与导出取帧不一致")
                    width, height = ImageOps.exif_transpose(probe).size
                    alpha_range = probe.convert("RGBA").getchannel("A").getextrema()
                    result["has_transparency"] = alpha_range[0] < 255
                    if alpha_range[1] == 0:
                        result["errors"].append("图片完全透明，没有可见内容")
                    if asset.get("transparent") is True and alpha_range[0] == 255:
                        result["errors"].append("要求透明背景，但文件没有实际透明像素")
                    if asset.get("transparent") is False and alpha_range[0] < 255:
                        result["errors"].append("要求不透明背景，但文件含有透明像素")
        except (OSError, ValueError, SyntaxError, UnidentifiedImageError,
                Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            result["errors"].append(f"文件不能安全解码为图片：{exc}")
            results.append(result)
            continue
        result.update({"format": actual_format, "actual_px": [width, height]})
        tw, th = asset["target_px"]
        scale = (max if asset["fit"] == "cover" else min)(tw / width, th / height)
        if scale > 1.01:
            result["errors"].append(f"清晰度不足：按 {asset['fit']} 放入 {tw}×{th} 图位需放大 {scale:.2f} 倍")
        visible_fraction = min((width / height) / (tw / th), (tw / th) / (width / height))
        if visible_fraction < .97:
            percent = (1 - visible_fraction) * 100
            if asset["fit"] == "cover":
                result["warnings"].append(
                    f"cover 约裁掉 {percent:.1f}% 图像面积；需核对焦点 {asset['focal']}% 和主体安全区")
            else:
                result["warnings"].append(f"contain 约有 {percent:.1f}% 图位留边；需检查背景衔接")
        if not result["errors"]:
            result["status"] = "ready"
        results.append(result)
    return {"ready": all(item["status"] == "ready" for item in results), "assets": results,
            "review_required": "ready 仅表示文件与采样检查通过；仍需在实际页面检查主体、事实、裁切、文字避让和整体风格。"}


def _fence(text: str) -> str:
    longest = max((len(match[0]) for match in re.finditer(r"`+", text)), default=0)
    marker = "`" * max(3, longest + 1)
    return f"{marker}text\n{text}\n{marker}"


def image_markup(asset: dict) -> str:
    """A resource hookup, not a page template. The author owns its layout."""
    w, h = asset["target_px"]
    src = html.escape(quote(asset["file"], safe="/"), quote=True)
    alt = html.escape(asset["alt"], quote=True)
    x, y = asset["focal"]
    return (f'<img data-image-id="{asset["id"]}" src="{src}" alt="{alt}" '
            f'width="{w}" height="{h}" '
            f'style="display:block;width:100%;height:auto;aspect-ratio:{w}/{h};'
            f'object-fit:{asset["fit"]};object-position:{x}% {y}%">')


def check_bindings(plan: dict, path: Path) -> dict:
    """Verify static img references on declared slides; no browser/visual claims.

    CSS backgrounds, lazy JS and srcset need another explicit contract; they
    cannot silently count as a working manual drop-in img connection here.
    """
    path = path.resolve()
    if not path.is_relative_to(plan["root"]):
        raise PlanError("--html 必须位于 plan 的项目目录内")
    expected = {item["id"]: item for item in plan["images"]}
    targets = {safe_path(plan["root"], item["file"]): item["id"] for item in plan["images"]}
    found = {key: set() for key in expected}
    errors, pages = [], set()

    class Bindings(HTMLParser):
        def __init__(self):
            super().__init__()
            self.sections = []
            self.in_picture = 0

        def handle_starttag(self, tag, attrs):
            data = dict(attrs)
            if tag == "base":
                errors.append("不支持 base URL；使用项目相对路径")
            if tag == "picture":
                self.in_picture += 1
            if tag == "section":
                page = None
                if "slide" in (data.get("class") or "").split():
                    raw = data.get("data-slide", "") or ""
                    if not re.fullmatch(r"[1-9][0-9]*", raw) or int(raw) in pages:
                        errors.append("slide 需要唯一正整数 data-slide 页码")
                    else:
                        page = int(raw)
                        pages.add(page)
                self.sections.append(page)
            if tag != "img":
                return
            identifier = data.get("data-image-id")
            try:
                src = urlsplit(data.get("src") or "")
                target = (path.parent / unquote(src.path)).resolve() if not src.scheme and not src.netloc and src.path else None
            except (ValueError, OSError, RuntimeError):
                target = None
            matched = targets.get(target)
            if identifier is None and matched is None:
                return
            if identifier is None:
                identifier = matched
            if identifier not in expected:
                errors.append(f"未知 data-image-id：{identifier}")
                return
            if len(attrs) != len(data) or self.in_picture or "srcset" in data:
                errors.append(f"{identifier}：重复属性或 picture/srcset 会改变实际图片，使用直接 img src")
            if matched != identifier:
                errors.append(f"{identifier}：src 没有指向计划中的文件")
                return
            page = next((p for p in reversed(self.sections) if p is not None), None)
            if page is None:
                errors.append(f"{identifier}：图片不在带 data-slide 的 slide 内")
            else:
                found[identifier].add(page)

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            if tag != "img":
                self.handle_endtag(tag)

        def handle_endtag(self, tag):
            if tag == "section" and self.sections:
                self.sections.pop()
            if tag == "picture":
                self.in_picture = max(0, self.in_picture - 1)

    parser = Bindings()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    for identifier, asset in expected.items():
        wanted = set(asset["pages"])
        missing, extra = wanted - found[identifier], found[identifier] - wanted
        if missing:
            errors.append(f"{identifier}：计划第 {sorted(missing)} 页未接入图片")
        if extra:
            errors.append(f"{identifier}：第 {sorted(extra)} 页引用未登记在计划中")
    return {"ready": not errors, "html": str(path), "errors": errors,
            "pages": {key: sorted(value) for key, value in found.items()},
            "scope": "只验证静态 img 路径和页码；加载、CSS 隐藏、裁切与美感须浏览器复核"}


def plan_digest(plan: dict) -> str:
    contract = {key: plan[key] for key in ("schemaVersion", "project", "images")}
    return hashlib.sha256(json.dumps(contract, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def check_handoff(plan: dict, html_path: Path, document: str = "image-brief.md") -> dict:
    """Check a usable manual handoff, independently of generated asset readiness."""
    path = safe_path(plan["root"], document, "document")
    errors = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        text = ""
        errors.append(f"配图 Markdown 缺失或不可读：{path}")
    if text:
        marker = f"<!-- deck-image-plan-sha256:{plan_digest(plan)} -->"
        if marker not in text:
            errors.append("配图 Markdown 与当前计划不一致；对齐修改并用 --brief --out 生成有效版本")
        for asset in plan["images"]:
            required = [asset["file"], asset["prompt"] if asset["source"] == "generated" else asset["source_note"]]
            if any(value not in text for value in required):
                errors.append(f"{asset['id']}：Markdown 缺少对应文件路径或完整提示词/复用来源")
    elif not errors:
        errors.append("配图 Markdown 为空")
    bindings = check_bindings(plan, html_path)
    errors.extend(bindings["errors"])
    files = check_images(plan)
    provided = {item["id"] for item in plan["images"] if item["source"] == "provided"}
    for asset in files["assets"]:
        # A supplied asset has no pending generation step that could repair it.
        if asset["id"] in provided and asset["status"] != "ready":
            errors.append(f"{asset['id']}：登记复用的图片尚未就绪")
    return {"ready": not errors, "stage": "handoff", "document": str(path), "errors": errors,
            "bindings": bindings, "files_ready": files["ready"],
            "pending_images": [item["id"] for item in files["assets"] if item["status"] != "ready"],
            "scope": "仅核对交接文件和静态路径；功能图覆盖、背景设计、可见性与最终画面仍须审阅"}


def write_brief(plan: dict, out: str = "image-brief.md", html_path: Path | None = None) -> Path:
    destination = safe_path(plan["root"], out, "--out")
    if html_path and destination == html_path.resolve():
        raise PlanError("提示词文档不能覆盖待检查的 HTML")
    if destination == plan["path"] or any(destination == safe_path(plan["root"], item["file"]) for item in plan["images"]):
        raise PlanError("提示词文档不能覆盖 plan 或图片目标")
    checked = {item["id"]: item for item in check_images(plan)["assets"]}
    bindings = check_bindings(plan, html_path) if html_path else None
    chunks = [f"# {plan['project']} — 图片生成交接\n",
              f"<!-- deck-image-plan-sha256:{plan_digest(plan)} -->\n",
              "这是交接文档，不代表素材齐备。标为生成的项目按完整提示词出图，标为复用的项目直接使用已登记文件。\n",
              f"项目目录：`{plan['root']}`。下方文件路径均相对此目录。\n",
              "1. 生成项按要求生成单张静态图片，复用项使用已登记文件；页面正文默认保留为可编辑文字。\n"
              "2. 按指定格式导出，创建目标子目录并使用完全相同的文件名。不要只修改扩展名。\n"
              "3. 回填后运行 `image_handoff.py --check` 并传入本 plan；重新预览每个使用页面。\n"
              "4. 状态是文档生成时的快照；文件检查通过仍需目检，不能据此宣称配图或页面已完成。\n",
              "机械校验不评估提示词创意质量；提交生图前确认提示词包含本图必要的主体、处理方式和构图约束。\n"]
    if bindings:
        chunks.append("页面接入：" + ("静态路径与页码已核对；回填后仍需刷新预览。" if bindings["ready"]
                       else "尚未接好，不能承诺放入目录即可显示。\n" + "\n".join(bindings["errors"])) + "\n")
    else:
        chunks.append("页面接入：未核对。作者须将下方 img 接入声明页面，运行 --check PLAN --html HTML 后再承诺自动回填。\n")
    for asset in plan["images"]:
        check = checked[asset["id"]]
        w, h = asset["target_px"]
        instructions = (["### 复用来源（无需生成）\n", asset["source_note"] + "\n"]
                        if asset["source"] == "provided" else [
                            "### 可直接复制的完整提示词\n", _fence("\n".join(filter(None, [
                                asset["prompt"],
                                "文字安全区：" + asset["negativeSpace"] if asset.get("negativeSpace") else "",
                                "输出真实透明背景，保留 alpha 通道。" if asset.get("transparent") else "",
                            ]))) + "\n",
                            "### 负面约束\n", (_fence("\n".join(asset["negative"])) if asset["negative"] else "未另设约束。") + "\n"])
        chunks += [f"## {asset['id']} · 第 {', '.join(map(str, asset['pages']))} 页\n",
                   f"- 文件：`{asset['file']}`\n- 当前状态：**{check['status']}**\n"
                   f"- 角色：{asset['role']}\n- 页面目的：{asset['purpose']}\n"
                   f"- 目标图位：{w} × {h} px；比例 {asset['aspect']}；格式 {FORMATS[Path(asset['file']).suffix.lower()]}\n"
                   f"- 放置方式：`object-fit: {asset['fit']}`；`object-position: {asset['focal'][0]}% {asset['focal'][1]}%`\n"
                   f"- 替代文本：{asset['alt']}\n",
                   *instructions,
                   "### 作者接入片段\n",
                   "源 HTML 与 plan 同目录时可使用；放入本页的自定图位，按布局调整实际宽高，保留比例或明确裁切。\n",
                   "```html\n" + image_markup(asset) + "\n```\n",
                   "### 回填验收\n",
                   "- 检查文件名、格式、分辨率与比例。\n"
                   "- 检查主体是否准确，是否有水印、乱码、多余标志或生成瑕疵。\n"
                   "- 在所有使用页面复查裁切、焦点、正文避让；图文重叠不能靠裁掉关键信息解决。\n"]
        for warning in check["errors"] + check["warnings"]:
            chunks.append(f"- 当前检查：{warning}\n")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("x", encoding="utf-8") as output:
            output.write("\n".join(chunks))
    except FileExistsError as exc:
        raise PlanError(f"文档已存在，保留原文不覆盖：{destination}；使用 --out 指定新文件名") from exc
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--brief", type=Path, metavar="PLAN", help="校验计划并创建人工生图交接文档")
    action.add_argument("--check", type=Path, metavar="PLAN", help="验收真实回填文件，缺失或无效返回非零")
    action.add_argument("--handoff", type=Path, metavar="PLAN", help="验收配图 Markdown 与 HTML 图位；允许生成图片待回填")
    parser.add_argument("--out", default=None, help="相对 plan 目录的文档路径；默认 image-brief.md；不覆盖")
    parser.add_argument("--document", default=None, help="--handoff 使用的 Markdown，相对 plan 目录；默认 image-brief.md")
    parser.add_argument("--html", type=Path, help="同时核对 HTML 中的静态图片引用与声明页码")
    args = parser.parse_args(argv)
    if not args.brief and args.out is not None:
        parser.error("--out 只适用于 --brief")
    if args.document is not None and not args.handoff:
        parser.error("--document 只适用于 --handoff")
    if args.handoff and not args.html:
        parser.error("--handoff 必须提供 --html 以核对真实图位")
    try:
        plan = load_plan(args.brief or args.check or args.handoff)
        if args.brief:
            destination = write_brief(plan, args.out or "image-brief.md", args.html)
            print(f"交接文档已创建：{destination}\n尚未生成或改写任何图片。")
            return 0
        if args.handoff:
            report = check_handoff(plan, args.html, args.document or "image-brief.md")
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ready"] else 1
        report = check_images(plan)
        report["files_ready"] = report["ready"]
        report["bindings"] = check_bindings(plan, args.html) if args.html else None
        if args.html:
            report["ready"] = report["files_ready"] and report["bindings"]["ready"]
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ready"] else 1
    except (PlanError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
