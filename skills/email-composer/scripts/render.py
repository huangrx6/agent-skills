#!/usr/bin/env python3
"""把内容 Spec 渲染成 HTML / 纯文本 / Markdown / .eml。

用法：
    python3 scripts/render.py spec.yaml --outdir ./email-out
    python3 scripts/render.py spec.yaml --formats html,text,md,eml --preset report
退出码：0 校验通过并写出，1 有阻断项（--draft 可输出草稿），2 参数错误。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from email_composer.render import build_outputs, parse_formats, style_summary
from email_composer.validate import validate_spec
from email_composer.render import render_html, render_text, render_markdown
from email_composer.spec import SpecError, load_spec
from email_composer.styles import StyleError, resolve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="render.py", description="把内容 Spec 渲染成邮件草稿文件"
    )
    parser.add_argument("spec", help="内容 Spec（.yaml 或 .json）")
    parser.add_argument("--outdir", default="email-out", help="输出目录（默认 ./email-out）")
    parser.add_argument(
        "--formats", default="html,text,md", help="逗号分隔：html,text,md,eml 或 all"
    )
    parser.add_argument("--preset", choices=("business", "report", "plain", "alert"))
    parser.add_argument("--style-file", help="样式令牌 JSON（预设 + overrides）")
    parser.add_argument("--name", help="文件名主干；默认由主题与日期生成")
    parser.add_argument("--date", help="文件名日期，默认今天，格式 YYYY-MM-DD")
    parser.add_argument("--draft", action="store_true", help="允许未填项的草稿输出；有阻断时仍返回 1，禁止绕过 HTML 安全检查")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    args = parser.parse_args(argv)

    try:
        spec = load_spec(args.spec)
        tokens, preset, reason = resolve(spec, args.preset, args.style_file)
        formats = parse_formats(args.formats)
        day = date.fromisoformat(args.date) if args.date else None
        report = validate_spec(spec, tokens, render_html(spec, tokens), render_text(spec),
                               render_markdown(spec), os.path.dirname(os.path.abspath(args.spec)))
        unsafe = any(item["code"] == "html_forbidden" for item in report["blocking"])
        if not report["ok"] and (not args.draft or unsafe):
            print(json.dumps({"ok": False, "files": {}, "report": report}, ensure_ascii=False, indent=2))
            return 1
        draft = args.draft
        output_name = args.name
        if draft:
            from email_composer.spec import filename_base
            output_name = "DRAFT_" + filename_base(spec["subject"], day, args.name)
        outputs, notes = build_outputs(
            spec,
            tokens,
            os.path.dirname(os.path.abspath(args.spec)),
            formats=formats,
            day=day,
            name=output_name,
        )
        outdir = os.path.abspath(args.outdir)
        os.makedirs(outdir, exist_ok=True)
        files: dict[str, str] = {}
        for fmt, (filename, content) in outputs.items():
            path = os.path.join(outdir, filename)
            if isinstance(content, bytes):
                with open(path, "wb") as handle:
                    handle.write(content)
            else:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(content)
            files[fmt] = path
        payload = {
            "ok": report["ok"],
            "draft": draft,
            "report": report,
            "subject": spec["subject"],
            "preset": preset,
            "preset_reason": reason,
            "style": style_summary(tokens),
            "files": files,
            "notes": notes,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            if draft:
                print("草稿：请检查报告中的未填项；不代表已通过交付检查。")
            print(f"样式：{payload['style']}（{reason}）")
            for fmt in formats:
                print(f"{fmt}: {files[fmt]}")
            for note in notes:
                print(f"提示：{note}")
        if not report["ok"] and not args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    except (SpecError, StyleError, ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
