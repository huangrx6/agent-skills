#!/usr/bin/env python3
"""校验邮件草稿：阻断项清零才能交付，警告项逐条判断。

用法：
    python3 scripts/validate.py spec.yaml
    python3 scripts/validate.py spec.yaml --report report.json --preset business
退出码：0 无阻断项，1 有阻断项，2 规格或样式错误。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from email_composer.render import render_html, render_markdown, render_text
from email_composer.spec import SpecError, load_spec
from email_composer.styles import StyleError, resolve
from email_composer.validate import report_to_json, validate_spec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate.py", description="校验内容 Spec 与三种渲染结果"
    )
    parser.add_argument("spec", help="内容 Spec（.yaml 或 .json）")
    parser.add_argument("--preset", choices=("business", "report", "plain", "alert"))
    parser.add_argument("--style-file", help="样式令牌 JSON")
    parser.add_argument("--report", help="把 JSON 报告另存到文件")
    parser.add_argument("--quiet", action="store_true", help="只返回退出码，不打印报告")
    args = parser.parse_args(argv)

    try:
        spec = load_spec(args.spec)
        tokens, preset, _ = resolve(spec, args.preset, args.style_file)
        html_body = render_html(spec, tokens)
        text_body = render_text(spec)
        md_body = render_markdown(spec)
        base_dir = os.path.dirname(os.path.abspath(args.spec))
        report = validate_spec(spec, tokens, html_body, text_body, md_body, base_dir)
        report["style"] = {
            "preset": preset,
            "width": tokens["width"],
            "accent": tokens["color"]["accent"],
        }
        text = report_to_json(report)
        if args.report:
            with open(args.report, "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
        if not args.quiet:
            print(text)
        return 0 if report["ok"] else 1
    except (SpecError, StyleError, ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
