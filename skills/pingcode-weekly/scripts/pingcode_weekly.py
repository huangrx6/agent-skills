#!/usr/bin/env python3
"""PingCode 需求/缺陷周报 CLI。

只读 PingCode。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import output_paths
from _pingcode import auth, client, config
from collect import (
    CollectError,
    assignee_names,
    build_check,
    collect_workspace,
    filter_payload,
    load_workspace,
    parse_window,
    single_project_workspace,
    week_label,
)
from pingcode_read import PingCodeError, current_user, list_projects, open_client
from weekly import TemplateError, render_weekly


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pingcode_weekly.py", description="PingCode 需求/缺陷周报")
    sub = parser.add_subparsers(dest="command", required=True)
    _add_auth(sub)
    _add_check(sub)
    _add_collect(sub)
    _add_weekly(sub)
    _add_render(sub)
    _add_projects(sub)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (PingCodeError, CollectError, TemplateError, config.ConfigError,
            config.TokenError, client.ApiError) as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 2


def _add_auth(sub: argparse._SubParsersAction) -> None:
    auth_parser = sub.add_parser("auth", help="PingCode 授权与令牌状态")
    auth_sub = auth_parser.add_subparsers(dest="auth_command", required=True)
    status = auth_sub.add_parser("status", help="查看令牌状态")
    status.set_defaults(func=_auth_status)
    login = auth_sub.add_parser("login", help="授权（企业模式或用户 OAuth）")
    login.add_argument("--mode", choices=("user", "enterprise"), default="user")
    login.add_argument("--code", help="用户 OAuth 回调里的 code；给了就直接换取令牌")
    login.set_defaults(func=_auth_login)
    logout = auth_sub.add_parser("logout", help="删除本地令牌缓存")
    logout.set_defaults(func=_auth_logout)


def _add_check(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("check", help="检查 PingCode 数据是否足够生成周报")
    _add_source_args(p)
    _add_window_args(p)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--strict", action="store_true", help="任一项目失败即返回 2")
    _add_scope_args(p)
    p.set_defaults(func=_check)


def _add_collect(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("collect", help="采集 PingCode 需求/缺陷证据 JSON")
    _add_source_args(p)
    _add_window_args(p)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--strict", action="store_true", help="任一项目失败即退出 2")
    _add_scope_args(p)
    _add_output_args(p, "JSON")
    p.set_defaults(func=_collect)


def _add_weekly(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("weekly", help="采集并生成周报 Markdown")
    _add_source_args(p)
    _add_window_args(p)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--strict", action="store_true", help="任一项目失败即退出 2")
    p.add_argument("--template", help="自定义模板 TOML")
    p.add_argument("--allow-empty", action="store_true",
                   help="PingCode 没有记录时也生成空周报")
    p.add_argument("--per-assignee", action="store_true",
                   help="按负责人分别输出文件；不能用 --stdout/--out")
    _add_scope_args(p)
    _add_output_args(p, "Markdown")
    p.set_defaults(func=_weekly)


def _add_render(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("render", help="从已有证据 JSON 渲染周报")
    p.add_argument("--input", required=True, help="collect 生成的 evidence JSON")
    p.add_argument("--template", help="自定义模板 TOML")
    _add_output_args(p, "Markdown")
    p.set_defaults(func=_render)


def _add_projects(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("projects", help="列出当前令牌可见的 PingCode 项目")
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(func=_projects)


def _add_output_args(parser: argparse.ArgumentParser, kind: str) -> None:
    parser.add_argument("--output-dir",
                        help="输出目录；默认 ~/Downloads/pingcode-weekly（Windows 为 Downloads\\pingcode-weekly）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--out", help=f"指定完整输出路径，覆盖默认目录；输出 {kind}")
    group.add_argument("--stdout", action="store_true",
                       help=f"写到标准输出，不落盘（输出 {kind}）")


def _add_source_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project", help="PingCode 项目名称、标识或 ID")
    group.add_argument("--workspace", help="多项目工作区 TOML")


def _add_window_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--week", help="ISO 周，例如 2026-W43")
    parser.add_argument("--month", help="自然月，例如 2026-10")
    parser.add_argument("--since", help="窗口起点，YYYY-MM-DD 或 ISO 日期时间")
    parser.add_argument("--until", help="窗口终点，YYYY-MM-DD 或 ISO 日期时间")


def _add_scope_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mine", action="store_true", help="只总结当前登录人的工作项")
    group.add_argument("--assignee", action="append",
                       help="只总结指定负责人；可重复，也可用 @me")


def _auth_status(_args: argparse.Namespace) -> int:
    data = auth.status()
    print(f"模式：{data.get('mode') or '未知'}")
    print(f"主机：{data.get('host') or '未知'}")
    print(f"配置目录：{data.get('config_dir') or '未知'}")
    print(f"access_token：{'有' if data.get('has_access_token') else '无'}")
    print(f"refresh_token：{'有' if data.get('has_refresh_token') else '无'}")
    print(f"已过期：{'是' if data.get('expired') else '否'}")
    if data.get("expires_at"):
        print(f"到期时间戳：{data['expires_at']}")
    return 0


def _auth_login(args: argparse.Namespace) -> int:
    if args.mode == "enterprise":
        auth.login_enterprise()
        print("企业令牌已保存。")
        return 0
    if args.code:
        auth.exchange_code(args.code)
        print("用户令牌已保存。")
        return 0
    print("在浏览器打开下面的地址完成授权：")
    print(auth.authorize_url())
    print("回调地址打不开时，把地址栏里的 code 复制出来，再运行：")
    print("  python3 scripts/pingcode_weekly.py auth login --code <code>")
    return 0


def _auth_logout(_args: argparse.Namespace) -> int:
    removed = config.clear_token()
    print("已删除本地令牌。" if removed else "本地没有令牌。")
    return 0


def _check(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    since, until = parse_window(week=args.week, month=args.month, since=args.since, until=args.until)
    payload = collect_workspace(projects=_projects_of(workspace),
                                since=since, until=until, limit=args.limit,
                                allow_partial=not args.strict)
    payload = _apply_scope(args, payload)
    ok, lines = build_check(payload)
    print(f"窗口：{week_label(since, until)}")
    for line in lines:
        print(line)
    return 0 if ok else 2


def _collect(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    since, until = parse_window(week=args.week, month=args.month, since=args.since, until=args.until)
    payload = collect_workspace(projects=_projects_of(workspace),
                                since=since, until=until, limit=args.limit,
                                allow_partial=not args.strict)
    payload = _apply_scope(args, payload)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.stdout:
        print(text, end="")
        return 0
    target = _output_path(args, workspace, _label(args, payload), since, until, "evidence.json")
    _write(target, text)
    quality = payload.get("quality") or {}
    print(f"已写出 {target}", file=sys.stderr)
    print(f"项目 {quality.get('projects', 0)} 个；需求 {quality.get('requirements', 0)} 条；"
          f"缺陷 {quality.get('bugs', 0)} 条", file=sys.stderr)
    for error in quality.get("errors") or []:
        print(f"注意：{error}", file=sys.stderr)
    _print_quality_warnings(payload)
    return 0


def _weekly(args: argparse.Namespace) -> int:
    workspace = _workspace(args)
    since, until = parse_window(week=args.week, month=args.month, since=args.since, until=args.until)
    payload = collect_workspace(projects=_projects_of(workspace),
                                since=since, until=until, limit=args.limit,
                                allow_partial=not args.strict)
    payload = _apply_scope(args, payload)
    if args.per_assignee:
        return _weekly_per_assignee(args, workspace, payload, since, until)
    _ok, lines = build_check(payload)
    has_data = any(
        not project.get("error")
        and bool(project.get("requirements") or project.get("bugs"))
        for project in payload.get("projects") or []
    )
    if not has_data and not args.allow_empty:
        print("PingCode 数据不足，未生成周报：", file=sys.stderr)
        for line in lines:
            print(line, file=sys.stderr)
        if _scope_excluded_unassigned(payload):
            print("窗口内有工作项因未分配负责人被按人过滤排除；"
                  "先在 PingCode 补负责人，或去掉 --mine/--assignee 生成全量周报。",
                  file=sys.stderr)
        else:
            print("先在 PingCode 录入需求和缺陷，或加 --allow-empty 生成空周报。", file=sys.stderr)
        return 2
    text = render_weekly(payload, template_path=_template(args, workspace))
    _print_quality_warnings(payload)
    if args.stdout:
        print(text, end="")
        return 0
    target = _output_path(args, workspace, _label(args, payload), since, until, "weekly.md")
    _write(target, text)
    print(f"已写出 {target}")
    return 0


def _render(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectError(f"读不了证据文件 {args.input}：{exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise CollectError("证据文件不是 version 1 的 PingCode 周报 JSON")
    text = render_weekly(payload, template_path=args.template)
    if args.stdout:
        print(text, end="")
        return 0
    target = _render_output_path(args)
    _write(target, text)
    print(f"已写出 {target}")
    return 0


def _scope_values(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    me = None
    if getattr(args, "mine", False):
        me = current_user(open_client())
        # id 和姓名都作为匹配键；显示时只留人名
        if me.get("id"):
            values.append(str(me["id"]))
        if me.get("name"):
            values.append(str(me["name"]))
        if not values:
            raise CollectError("拿不到当前登录人信息；请用 --assignee 指定负责人")
        return values
    for raw in getattr(args, "assignee", None) or []:
        for part in str(raw).split(","):
            part = part.strip()
            if part.casefold() in ("@me", "me", "我"):
                if me is None:
                    me = current_user(open_client())
                if me.get("id"):
                    values.append(str(me["id"]))
                if me.get("name"):
                    values.append(str(me["name"]))
            elif part:
                values.append(part)
    return values


def _apply_scope(args: argparse.Namespace, payload: dict) -> dict:
    wanted = _scope_values(args)
    return filter_payload(payload, wanted) if wanted else payload


def _scope_excluded_unassigned(payload: dict) -> bool:
    return any((project.get("scope") or {}).get("excluded_unassigned")
               for project in payload.get("projects") or [])


def _print_quality_warnings(payload: dict) -> None:
    for project in payload.get("projects") or []:
        for warning in (project.get("quality") or {}).get("warnings") or []:
            print(f"注意：{warning}", file=sys.stderr)


def _weekly_per_assignee(args: argparse.Namespace, workspace: dict, payload: dict,
                         since, until) -> int:
    if args.stdout or args.out:
        raise CollectError("--per-assignee 不能用 --stdout 或 --out；用 --output-dir 指定目录")
    names = assignee_names(payload)
    if not names:
        raise CollectError("没有可拆分的负责人；先用 --assignee 指定，或补齐工作项负责人")
    base = _label(args, payload)
    written = 0
    for name in names:
        part = filter_payload(payload, [name])
        if not any(project.get("requirements") or project.get("bugs")
                   for project in part.get("projects") or [] if not project.get("error")):
            continue
        text = render_weekly(part, template_path=_template(args, workspace))
        directory = _output_dir(args, workspace)
        window = output_paths.window_slug(since, until, week=getattr(args, "week", None),
                                          month=getattr(args, "month", None))
        target = directory / output_paths.build_filename(
            base, window, f"{output_paths.safe_name(name)}-weekly.md"
        )
        _write(target, text)
        print(f"已写出 {target}")
        _print_quality_warnings(part)
        written += 1
    if not written:
        raise CollectError("按负责人拆分后没有可输出的工作项")
    return 0


def _projects(args: argparse.Namespace) -> int:
    api = open_client()
    rows = list_projects(api, limit=args.limit)
    if not rows:
        print("当前令牌看不到项目。")
        return 0
    print(f"{'标识':<12} {'名称':<30} ID")
    for row in rows:
        print(f"{str(row.get('identifier') or ''):<12} "
              f"{str(row.get('name') or ''):<30} {row.get('id') or ''}")
    return 0


def _workspace(args: argparse.Namespace) -> dict:
    if args.workspace:
        return load_workspace(args.workspace)
    return single_project_workspace(args.project)


def _label(args: argparse.Namespace, payload: dict | None = None) -> str:
    if getattr(args, "workspace", None):
        return Path(args.workspace).stem
    if getattr(args, "project", None):
        if payload:
            rows = [row for row in payload.get("projects") or [] if not row.get("error")]
            if len(rows) == 1 and rows[0].get("identifier"):
                return str(rows[0]["identifier"])
        return str(args.project)
    return "pingcode"


def _output_dir(args: argparse.Namespace, workspace: dict | None = None) -> Path:
    if getattr(args, "output_dir", None):
        return output_paths.resolve_output_dir(args.output_dir)
    section = (workspace or {}).get("workspace") or {}
    if isinstance(section, dict) and section.get("output_dir"):
        return output_paths.resolve_output_dir(str(section["output_dir"]))
    return output_paths.default_output_dir()


def _output_path(args: argparse.Namespace, workspace: dict, label: str,
                 since, until, suffix: str) -> Path:
    if getattr(args, "out", None):
        return Path(args.out)
    directory = _output_dir(args, workspace)
    name = output_paths.build_filename(
        label,
        output_paths.window_slug(since, until, week=getattr(args, "week", None),
                                 month=getattr(args, "month", None)),
        suffix,
    )
    return directory / name


def _render_output_path(args: argparse.Namespace) -> Path:
    if getattr(args, "out", None):
        return Path(args.out)
    return _output_dir(args) / output_paths.render_filename(Path(args.input).stem)


def _projects_of(workspace: dict) -> list[dict]:
    projects = workspace.get("projects")
    if not isinstance(projects, list) or not projects:
        raise CollectError("没有配置任何项目")
    return projects


def _template(args: argparse.Namespace, workspace: dict) -> str | None:
    if args.template:
        return args.template
    section = workspace.get("workspace") or {}
    template = section.get("template") if isinstance(section, dict) else None
    if not template:
        return None
    if args.workspace:
        return str(Path(args.workspace).resolve().parent / str(template))
    return str(template)


def _write(path: str | Path, text: str) -> None:
    try:
        output_paths.atomic_write_text(path, text)
    except OSError as exc:
        raise CollectError(f"写不出 {path}：{exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
