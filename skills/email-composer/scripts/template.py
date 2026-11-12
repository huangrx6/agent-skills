#!/usr/bin/env python3
"""邮件模板库：列出、查看、套用、存为、更新、归档与删除。

用法：
    python3 scripts/template.py list [--type approval] [--query 上线]
    python3 scripts/template.py show approval-release
    python3 scripts/template.py candidates spec.yaml
    python3 scripts/template.py save --spec spec.yaml --id approval-release --name 上线申请 \\
        --var '2026-11-20={{release_date}}'
    python3 scripts/template.py apply approval-release --vars vars.json
    python3 scripts/template.py update --id approval-release --spec spec.yaml --note 补充回滚条件
    python3 scripts/template.py archive approval-release
    python3 scripts/template.py remove approval-release --yes

默认模板库：./email-templates/（可用 --root 或 EMAIL_TEMPLATES_DIR 修改）。
退出码：0 成功，1 套用时校验有阻断项，2 参数、变量或模板错误。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from email_composer.render import parse_formats
from email_composer.spec import SpecError, load_spec
from email_composer.styles import StyleError
from email_composer import templates
from email_composer.templates import TemplateError


def _emit(payload: dict, code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def _fail(message: str, code: int = 2, **extra) -> int:
    return _emit({"ok": False, "error": message, **extra}, code)


def _parse_descriptions(items: list[str] | None) -> dict[str, str]:
    result = {}
    for item in items or []:
        if "=" not in item:
            raise TemplateError(f"--describe 需要「变量名=说明」：{item!r}")
        name, text = item.split("=", 1)
        result[name.strip()] = text.strip()
    return result


def _print_list(rows: list[dict], root: str, include_archived: bool = False) -> None:
    if not rows:
        if not include_archived:
            archived = sum(
                1 for entry in templates.load_index(root)["templates"].values() if entry.get("archived")
            )
            if archived:
                print(f"没有匹配的模板；另有 {archived} 个已归档，用 --all 查看")
                return
        print(f"模板库为空：{root}")
        return
    print(f"模板库：{root}")
    print(f"{'id':<24}{'类型':<12}{'当前':<8}{'更新':<13}名称")
    for row in rows:
        suffix = "（已归档）" if row.get("archived") else ""
        print(
            f"{row['id']:<24}{row.get('type', ''):<12}"
            f"{row.get('current', ''):<8}{row.get('updated', ''):<13}"
            f"{row.get('name', '')}{suffix}"
        )


def _print_candidates(rows: list[dict]) -> None:
    if not rows:
        print("没有识别到可参数化的候选值。")
        return
    print("候选值（由你确认哪些变成变量）：")
    for row in rows:
        value = row["value"]
        if isinstance(value, list):
            value = " / ".join(str(item) for item in value)
        where = ", ".join(row["paths"][:3])
        print(f"[{row['kind']}] {value}  ×{row['count']}  {where}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="template.py", description="邮件模板库操作")
    parser.add_argument("--root", help="模板库目录，默认 ./email-templates")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出模板")
    p_list.add_argument("--type")
    p_list.add_argument("--query")
    p_list.add_argument("--all", action="store_true", help="包含已归档")
    p_list.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", help="查看模板详情")
    p_show.add_argument("id")

    p_candidates = sub.add_parser("candidates", help="列出可参数化的候选值")
    p_candidates.add_argument("spec")
    p_candidates.add_argument("--json", action="store_true")

    def add_save_args(target: argparse.ArgumentParser, require_name: bool) -> None:
        target.add_argument("--spec", required=True)
        target.add_argument("--id", required=True)
        target.add_argument("--name", required=require_name)
        target.add_argument("--scene", default="" if require_name else None)
        target.add_argument("--description", default="" if require_name else None)
        target.add_argument("--var", action="append", default=[], metavar="原值=变量名")
        target.add_argument("--optvar", action="append", default=[], metavar="原值=变量名")
        target.add_argument("--describe", action="append", default=[], metavar="变量名=说明")
        target.add_argument("--note", default="")

    p_save = sub.add_parser("save", help="把规格存为新模板（v1）")
    add_save_args(p_save, require_name=True)

    p_update = sub.add_parser("update", help="生成新版本（v2、v3…）")
    add_save_args(p_update, require_name=False)

    p_apply = sub.add_parser("apply", help="套用模板并渲染")
    p_apply.add_argument("id")
    p_apply.add_argument("--vars", help="变量 JSON，形如 {\"release_date\": \"2026-11-20\"}")
    p_apply.add_argument("--set", action="append", default=[], metavar="变量名=值")
    p_apply.add_argument("--outdir", default="email-out")
    p_apply.add_argument(
        "--formats",
        default=None,
        help="逗号分隔：html,text,md,eml；默认 Spec 模板三格式，HTML 模板 html,text",
    )
    p_apply.add_argument("--version")
    p_apply.add_argument("--date", help="文件名日期，格式 YYYY-MM-DD")
    p_apply.add_argument("--to", help="设置收件人（只写入 .eml 头）")
    p_apply.add_argument("--cc", action="append", default=[])
    p_apply.add_argument("--subject", help="覆盖主题行（HTML 模板默认取 <title>）")

    p_archive = sub.add_parser("archive", help="归档模板（保留文件）")
    p_archive.add_argument("id")

    p_restore = sub.add_parser("restore", help="取消归档")
    p_restore.add_argument("id")

    p_add_html = sub.add_parser("add-html", help="把现成 HTML 加入扩展模板目录")
    p_add_html.add_argument("file")
    p_add_html.add_argument("--id", help="模板 id，默认用文件名")
    p_add_html.add_argument("--force", action="store_true", help="覆盖同名 HTML 文件")

    p_remove = sub.add_parser("remove", help="删除模板及全部版本")
    p_remove.add_argument("id")
    p_remove.add_argument("--yes", action="store_true", help="确认删除，不可恢复")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = templates.root_dir(args.root)

    try:
        if args.command == "list":
            rows = templates.list_templates(root, args.type, args.query, args.all)
            if args.json:
                return _emit({"ok": True, "root": str(root), "templates": rows})
            _print_list(rows, str(root), args.all)
            return 0
        if args.command == "show":
            return _emit(templates.show(root, args.id))
        if args.command == "candidates":
            spec = load_spec(args.spec)
            rows = templates.candidates(spec)
            if args.json:
                return _emit({"ok": True, "candidates": rows})
            _print_candidates(rows)
            return 0
        if args.command == "save":
            result = templates.save(
                args.spec,
                root,
                args.id,
                args.name,
                args.scene,
                args.description,
                templates.parse_assignments(args.var, "--var"),
                templates.parse_assignments(args.optvar, "--optvar"),
                _parse_descriptions(args.describe),
                args.note,
            )
            return _emit(result)
        if args.command == "update":
            result = templates.update(
                args.spec,
                root,
                args.id,
                args.name,
                args.scene,
                args.description,
                templates.parse_assignments(args.var, "--var"),
                templates.parse_assignments(args.optvar, "--optvar"),
                _parse_descriptions(args.describe),
                args.note,
            )
            return _emit(result)
        if args.command == "apply":
            result = templates.apply(
                root,
                args.id,
                args.vars,
                args.set,
                args.outdir,
                parse_formats(args.formats) if args.formats else None,
                args.version,
                args.date,
                args.to,
                args.cc or None,
                args.subject,
            )
            return _emit(result, 0 if result.get("ok") else 1)
        if args.command == "add-html":
            return _emit(templates.add_html(root, args.file, args.id, args.force))
        if args.command == "archive":
            return _emit(templates.archive(root, args.id))
        if args.command == "restore":
            return _emit(templates.restore(root, args.id))
        if args.command == "remove":
            if not args.yes:
                return _fail("删除模板不可恢复，确认后加 --yes")
            return _emit(templates.remove(root, args.id))
        return _fail("未知子命令")
    except TemplateError as exc:
        payload = {"ok": False, "error": str(exc)}
        if getattr(exc, "names", None):
            payload["missing"] = exc.names
        return _emit(payload, 2)
    except (SpecError, StyleError, ValueError, OSError) as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
