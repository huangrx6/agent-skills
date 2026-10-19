#!/usr/bin/env python3
"""Compile authored HTML slides into a standalone player with deterministic exports.

The source owns content, project styling and assets. This compiler validates slide,
reveal and optional raster-media contracts, then embeds the player and opt-in
normal-flow layout CSS. It does not split content or fit text automatically.
Keep source and output in one directory so relative asset URLs retain their meaning.
"""
from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ASSETS = Path(__file__).resolve().parents[1] / "assets"
VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
MARKER = 'name="deck-web-runtime"'


class SourceError(ValueError):
    """The authored HTML does not meet the small presentation contract."""


def svg_url(value: str) -> bool:
    """Recognize explicit SVG URLs; this is a media check, not a URL sandbox."""
    value = value.strip()
    if re.match(r"data\s*:\s*image/svg\+xml(?:\s*[;,]|\s*$)", unquote(value), re.I):
        return True
    try:
        return unquote(urlsplit(value).path).lower().endswith(".svg")
    except ValueError:
        # URL syntax/availability is checked by the browser, not this compiler.
        return False


def css_unescape(value: str) -> str:
    """Decode CSS escapes in resource tokens before checking their media type."""
    value = re.sub(r"\\(?:\r\n|[\r\n\f])", "", value)

    def replace(match):
        if match[1]:
            point = int(match[1], 16)
            return chr(point) if 0 < point <= 0x10FFFF else "\ufffd"
        return match[2]

    return re.sub(r"\\(?:([0-9a-fA-F]{1,6})\s?|([^\r\n\f]))", replace, value)


def check_raster_css(css: str) -> None:
    # Static inline CSS only. Linked stylesheets and script-created images need
    # --check's rendered-DOM inspection; do not advertise this as sanitization.
    css = css_unescape(re.sub(r"/\*.*?\*/", "", css, flags=re.S))
    resources = [match[2] for match in re.finditer(
        r"\burl\(\s*(['\"]?)(.*?)\1\s*\)", css, flags=re.I | re.S)]
    for match in re.finditer(r"(?:-webkit-)?image-set\((.*?)\)", css, flags=re.I | re.S):
        resources.extend(item[2] for item in re.finditer(r"(['\"])(.*?)\1", match[1], flags=re.S))
    if any(svg_url(value) for value in resources):
        raise SourceError("Raster-only decks cannot use SVG in CSS; use PNG, JPEG or WebP assets allowed by the project")


def seconds(value: str | None, default: float, label: str, *, zero=False) -> float:
    try:
        number = float(default if value is None else value)
    except (ValueError, TypeError) as exc:
        raise SourceError(f"{label} must be a finite number of seconds") from exc
    if not math.isfinite(number) or number < 0 or (number == 0 and not zero):
        raise SourceError(f"{label} must be finite and {'nonnegative' if zero else 'positive'}")
    return number


class SourceParser(HTMLParser):
    def __init__(self, source: str, *, raster_only=False):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.lines = [0]
        for line in source.splitlines(keepends=True):
            self.lines.append(self.lines[-1] + len(line))
        self.stack: list[str] = []
        self.counts = {"html": 0, "head": 0, "body": 0}
        self.timeline: list[dict] = []
        self.current: dict | None = None
        self.replacements: list[tuple[int, int, str]] = []
        self.head_end = self.body_end = None
        self.raster_only = raster_only
        self.coverage: list[dict] = []

    def source_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        keys = [name for name, _ in attrs]
        if len(keys) != len(set(keys)):
            raise SourceError(f"Duplicate attribute on <{tag}>")
        data = dict(attrs)
        if self.raster_only:
            if tag.split(":")[-1] == "svg":
                raise SourceError("Raster-only decks cannot contain inline SVG; use PNG, JPEG or WebP assets allowed by the project")
            if tag == "meta" and (data.get("name") or "").lower() == "deck-media-policy":
                raise SourceError("deck-media-policy is compiler-owned; use --raster-only instead")
            for key in ("src", "href", "xlink:href", "data", "poster", "background"):
                if data.get(key) and svg_url(data[key]):
                    raise SourceError(f"Raster-only decks cannot use SVG in <{tag}> {key}")
            for key in ("srcset", "imagesrcset"):
                if any(svg_url(value) for value in re.split(r"[\s,]+", data.get(key) or "")):
                    raise SourceError(f"Raster-only decks cannot use SVG in <{tag}> {key}")
            if (data.get("type") or "").split(";", 1)[0].strip().lower() == "image/svg+xml":
                raise SourceError(f"Raster-only decks cannot use SVG MIME types in <{tag}>")
            check_raster_css(data.get("style") or "")
        if tag == "base":
            raise SourceError("<base> is unsupported; keep asset paths relative to the source")
        if data.get("name") == "deck-web-runtime":
            raise SourceError("This is already compiled; edit and compile the original source HTML")
        if tag in self.counts:
            self.counts[tag] += 1
            expected = [] if tag == "html" else ["html"]
            if self.stack != expected or self.counts[tag] != 1:
                raise SourceError(f"Expected one explicit <{tag}> in a complete HTML document")
            if tag == "body" and self.head_end is None:
                raise SourceError("Close <head> before opening <body>")
        is_slide = "slide" in (data.get("class") or "").split()
        if is_slide:
            if tag != "section" or data.get("class") != "slide":
                raise SourceError('Slides must be <section class="slide">; style with IDs or data attributes')
            if self.stack != ["html", "body"]:
                raise SourceError("Slide sections must be direct children of <body>")
            index = len(self.timeline) + 1
            if data.get("data-slide") != str(index):
                raise SourceError(f"Expected consecutive data-slide=\"{index}\"")
            if not (data.get("data-title") or "").strip():
                raise SourceError(f"Slide {index} needs a nonempty data-title")
            enter = seconds(data.get("data-enter"), .9, f"Slide {index} data-enter")
            hold = seconds(data.get("data-hold"), 3, f"Slide {index} data-hold")
            previous = self.timeline[-1] if self.timeline else None
            start = previous["start"] + previous["enter"] + previous["hold"] if previous else 0
            if not math.isfinite(start + enter + hold):
                raise SourceError("Total deck duration must be finite")
            self.current = {"slide": index, "start": start, "enter": enter, "hold": hold}
            self.timeline.append(self.current)
            self.coverage.append({"slide": index, "title": data["data-title"],
                                  "images": 0, "inlineSvg": 0, "reveals": 0})
            # Canonicalize the slide opener while preserving authored attributes.
            canonical = '<section class="slide"' + "".join(
                f' {name}' + (f'="{html.escape(value, quote=True)}"' if value is not None else "")
                for name, value in attrs if name != "class") + ">"
            pos = self.source_offset()
            self.replacements.append((pos, pos + len(self.get_starttag_text()), canonical))
        elif "data-slide" in data:
            raise SourceError('data-slide belongs only on <section class="slide">')
        if self.current is not None:
            if tag == "img":
                self.coverage[-1]["images"] += 1
            if tag == "svg":
                self.coverage[-1]["inlineSvg"] += 1
            if "data-reveal" in data:
                self.coverage[-1]["reveals"] += 1
        if any(key in data for key in ("data-reveal", "data-at", "data-duration")):
            if self.current is None:
                raise SourceError("Reveal attributes must be inside a slide")
            if data.get("data-reveal") not in {"fade", "rise", "wipe"}:
                raise SourceError("data-reveal must be fade, rise or wipe")
            at = seconds(data.get("data-at"), 0, "data-at", zero=True)
            duration = seconds(data.get("data-duration"), .6, "data-duration")
            if at + duration > self.current["enter"] + 1e-9:
                raise SourceError(f"Slide {self.current['slide']}: reveal must finish within data-enter")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_data(self, data):
        if self.raster_only and self.stack and self.stack[-1] == "style":
            check_raster_css(data)

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID and tag != "svg" and "svg" not in self.stack:
            raise SourceError(f"Use an explicit closing tag for <{tag}>; self-closing syntax is only for SVG or void elements")
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            raise SourceError(f"Unbalanced </{tag}>; use explicit closing tags")
        if tag == "head":
            self.head_end = self.source_offset()
        if tag == "body":
            self.body_end = self.source_offset()
        if tag == "section" and self.stack == ["html", "body", "section"]:
            self.current = None
        self.stack.pop()

    def validate(self):
        self.feed(self.source)
        self.close()
        if self.stack or any(n != 1 for n in self.counts.values()) or self.head_end is None or self.body_end is None:
            raise SourceError("Use a complete HTML document with explicitly closed html, head and body")
        if not self.timeline:
            raise SourceError("The source has no slide sections")


def compile_html(source: str, *, raster_only=False) -> str:
    """Compile slides; raster_only rejects explicit SVG, not asset provenance.

    Generated-image provenance needs the image plan, prompts and human review.
    External stylesheets and dynamic resources require the runtime media check.
    """
    parser = SourceParser(source, raster_only=raster_only)
    parser.validate()
    css = (ASSETS / "web-base.css").read_text(encoding="utf-8")
    layouts = (ASSETS / "web-layouts.css").read_text(encoding="utf-8")
    runtime = (ASSETS / "web-runtime.js").read_text(encoding="utf-8")
    timeline = json.dumps(parser.timeline, separators=(",", ":"), allow_nan=False)
    head = f'\n<meta {MARKER} content="1">\n<style id="__deck_web_base">\n{css}\n</style>\n'
    head += f'<style id="__deck_web_layouts">\n{layouts}\n</style>\n'
    if raster_only:
        head += '<meta name="deck-media-policy" content="generated-raster">\n'
    boot = ("\n<script>window.__deck_timeline=" + timeline + ";</script>\n"
            + '<script id="__deck_web_runtime">\n' + runtime + "\n</script>\n")
    replacements = parser.replacements + [(parser.head_end, parser.head_end, head),
                                           (parser.body_end, parser.body_end, boot)]
    for start, end, text in sorted(replacements, reverse=True):
        source = source[:start] + text + source[end:]
    return source


def compile_file(source: Path, output: Path, *, raster_only=False) -> dict:
    source, output = source.resolve(), output.resolve()
    if source == output:
        raise SourceError("Source and output must be different files")
    if source.parent != output.parent:
        raise SourceError("Keep source and output in the same directory to preserve relative asset URLs")
    authored = source.read_text(encoding="utf-8")
    rendered = compile_html(authored, raster_only=raster_only)
    coverage = source_coverage(authored)
    output.write_text(rendered, encoding="utf-8")
    return coverage


def source_coverage(source: str) -> dict:
    """Inventory authored markup, never infer beauty, visibility or live motion."""
    parser = SourceParser(source)
    parser.validate()
    return {
        "scope": "Authored slide markup only; excludes CSS backgrounds, dynamic images, custom animations and player controls. Counts do not verify visibility, assets, motion playback or design quality.",
        "pages": parser.coverage,
        "totals": {key: sum(page[key] for page in parser.coverage)
                   for key in ("images", "inlineSvg", "reveals")},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--out", required=True, type=Path)
    parser.add_argument("--raster-only", action="store_true",
                        help="Reject explicit SVG media; use --check for rendered resources and verify project-required image provenance separately")
    parser.add_argument("--check", action="store_true",
                        help="Inspect the compiled deck in Chrome and save <output>.check.json; unresolved layout findings return nonzero")
    parser.add_argument("--image-plan", type=Path,
                        help="Verify the image Markdown and source hookups before compiling; pending generated images are allowed")
    parser.add_argument("--image-brief", default=None,
                        help="Markdown path relative to image plan; defaults to image-brief.md")
    args = parser.parse_args(argv)
    if args.image_brief is not None and not args.image_plan:
        parser.error("--image-brief requires --image-plan")
    try:
        if args.image_plan:
            module_spec = importlib.util.spec_from_file_location(
                "_deck_image_handoff", Path(__file__).with_name("image_handoff.py"))
            handoff = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(handoff)
            try:
                plan = handoff.load_plan(args.image_plan)
                protected = [plan["path"], handoff.safe_path(plan["root"], args.image_brief or "image-brief.md")]
                protected += [handoff.safe_path(plan["root"], item["file"]) for item in plan["images"]]
                for output in [args.out] + ([args.out.with_suffix(".check.json")] if args.check else []):
                    if any(output.resolve() == path.resolve() or
                           (output.exists() and path.exists() and output.samefile(path)) for path in protected):
                        raise SourceError("Output/report would overwrite the image plan, Markdown or an image")
                result = handoff.check_handoff(plan, args.source, args.image_brief or "image-brief.md")
            except handoff.PlanError as exc:
                raise SourceError(str(exc)) from exc
            if not result["ready"]:
                pending = "、".join(result["pending_images"]) or "（无待生成图）"
                print("Image handoff: 占位待回填：" + pending
                      + "；编译继续，图放进 assets/images/ 后重新编译即可")
                for problem in result["errors"]:
                    print("  · " + problem)
            else:
                print("Image handoff: passed; files present (visual review still required)")
        report_path = args.out.with_suffix(".check.json")
        if args.check:
            protected = (args.source, args.out)
            if report_path.is_symlink() or any(
                report_path.resolve() == path.resolve()
                or (report_path.exists() and path.exists() and report_path.samefile(path))
                for path in protected
            ):
                raise SourceError("The generated check report would overwrite a source or output file")
        coverage = compile_file(args.source, args.out, raster_only=args.raster_only)
        totals = coverage["totals"]
        print(f"Source coverage: {totals['images']} img slots, {totals['inlineSvg']} inline SVG, "
              f"{totals['reveals']} reveal targets")
        print("Design review: confirm imagery/prompt handoff and intended playback separately; "
              "player controls and layout pass do not verify them.")
        if args.check:
            module_spec = importlib.util.spec_from_file_location(
                "_deck_web_check", Path(__file__).with_name("web_check.py"))
            checker = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(checker)
            report = checker.inspect(args.out)
            report["sourceCoverage"] = coverage
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"✓ HTML: {args.out.resolve()}")
            summary = report['summary']
            print(f"Layout: {summary['status']} — {summary['errors']} errors, "
                  f"{summary['warnings']} warnings, {summary['review']} review — {report_path.resolve()}")
            return checker.exit_code(report)
    except (SourceError, OSError, RuntimeError) as exc:
        parser.exit(1, f"✗ {exc}\n")
    print(f"✓ {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
