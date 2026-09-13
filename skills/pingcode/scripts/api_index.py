#!/usr/bin/env python3
"""端点表的查询门：把生成好的 ENTRIES 变成可查询、可拼装的能力。

为什么单独一个文件（而不是把函数写进 `endpoints.py`）
------------------------------------------------------
`endpoints.py` 是**生成物**，重新生成时整份重写。手写函数放进去会被冲掉，而且
"生成物里混着手写代码"是最容易被误改的形态。所以：数据一处（生成）、查询一处（手写）。

这个模块存在的理由
------------------
让"端点写错"变成**机械错误**，而不是静默失败。第三方的那个 pingcode 实现里写死了
`/v1/project/work_items` —— 官方当前文档里根本不存在（PJM 前缀是 `/v1/pjm/`，且是
`workitems` 带下划线）。它的测试 mock 了 `urllib.request.urlopen`，所以错路径照样全绿。

`require()` 会在**发送请求之前**报错，并给出最接近的候选；`build()` 会在参数名拼错时
当场报错，而不是拼出一个注定 404 的路径。

跑法（自查用）
--------------
    python3 scripts/api_index.py --groups
    python3 scripts/api_index.py --list 工作项
    python3 scripts/api_index.py --show GET /v1/pjm/workitems

退出码：0 正常 / 1 查询无结果或用法错误
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import os
import re
import sys
import urllib.parse
from typing import NamedTuple


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。

    **同一个模块只加载一次**：这个函数会被好几个模块各自调用，如果每次都新建一个模块
    对象，就会出现两份互不相干的模块状态 —— 连异常类都不是同一个，`except` 会静默抓不到。
    所以先查 `sys.modules`。
    """
    key = f"_pingcode_{name}"
    loaded = sys.modules.get(key)
    if loaded is not None:
        return loaded
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


endpoints = _load_sibling("endpoints")

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class Entry(NamedTuple):
    method: str
    url: str          # 官方原始形态，含 {占位符} 与查询模板
    scopes: tuple[str, ...]
    perms: tuple[str, ...]   # 令牌要求：企业令牌 / 用户令牌
    group: str
    title: str

    @property
    def path(self) -> str:
        return self.url.partition("?")[0]

    @property
    def query_template(self) -> tuple[tuple[str, str], ...]:
        _path, _, query = self.url.partition("?")
        return tuple(urllib.parse.parse_qsl(query, keep_blank_values=True))

    @property
    def needs_user_token(self) -> bool:
        """只有用户令牌能用（`/v1/myself` 这类）。企业令牌拿不到。"""
        return self.perms == ("用户令牌",)

    @property
    def needs_enterprise_token(self) -> bool:
        return self.perms == ("企业令牌",)


ENTRIES: tuple[Entry, ...] = tuple(Entry(*row) for row in endpoints.ENTRIES)

# 认哪些 HTTP 方法：定义在生成物里（由官方文档的 method 取值推出），这里只转发。
METHODS: tuple[str, ...] = tuple(endpoints.METHODS)


class EndpointError(Exception):
    """端点查询/拼装失败。"""


class UnknownEndpoint(EndpointError):
    """官方文档里没有这个端点。"""


class AmbiguousEndpoint(EndpointError):
    """同一 (method, path) 有多个接口，需要补 query 才能确定。"""


class PathParamError(EndpointError):
    """路径/查询占位符没填全，或者填了文档里没有的名字。"""


def path_of(url: str) -> str:
    return url.partition("?")[0]


def placeholders(url: str) -> tuple[str, ...]:
    """url 模板里所有 `{name}`（路径段与查询值都算）。"""
    return tuple(dict.fromkeys(_PLACEHOLDER.findall(url)))


def path_placeholders(url: str) -> tuple[str, ...]:
    """只在路径部分出现的 `{name}`。"""
    return tuple(dict.fromkeys(_PLACEHOLDER.findall(path_of(url))))


def find(method: str | None = None, path: str | None = None,
         path_prefix: str | None = None, group: str | None = None,
         contains: str | None = None) -> list[Entry]:
    """按条件筛端点（宽松匹配，用于探索与报错时给候选）。"""
    want_method = method.upper() if method else None
    out: list[Entry] = []
    for e in ENTRIES:
        if want_method and e.method != want_method:
            continue
        if path and e.path != path:
            continue
        if path_prefix and not e.path.startswith(path_prefix):
            continue
        if group and group not in e.group:
            continue
        if contains and contains not in e.url and contains not in e.title:
            continue
        out.append(e)
    return out


def require(method: str, path: str,
            query: dict[str, str] | None = None) -> Entry:
    """取唯一的端点条目；取不到或有歧义都抛错（发送前就拦住）。

    query 用于同名不同变体的接口：`/v1/auth/token` 有三个 grant_type，
    靠 `require("GET", "/v1/auth/token", {"grant_type": "refresh_token"})` 区分。
    """
    want_method = method.upper()
    hits = [e for e in ENTRIES if e.method == want_method and e.path == path]
    if query:
        want = {k: str(v) for k, v in query.items()}
        narrowed = []
        for e in hits:
            template = dict(e.query_template)
            if set(want) <= set(template) and all(template[k] == v for k, v in want.items()):
                narrowed.append(e)
        hits = narrowed
    if not hits:
        known = sorted({e.path for e in ENTRIES if e.method == want_method})
        near = difflib.get_close_matches(path, known, n=5, cutoff=0.6)
        hint = ("最接近的候选：" + "、".join(near)) if near else "该方法下没有相近路径"
        raise UnknownEndpoint(
            f"官方文档里没有 {want_method} {path}（{hint}）。"
            f"确认后重新生成端点表：python3 dev-tools/gen_endpoints.py"
        )
    if len(hits) > 1:
        variants = "、".join(
            ("?" + "&".join(f"{k}={v}" for k, v in e.query_template)) or "(无查询参数)"
            for e in hits
        )
        raise AmbiguousEndpoint(
            f"{want_method} {path} 有 {len(hits)} 个变体，需要 query 指定：{variants}"
        )
    return hits[0]


def build(url: str, **params: object) -> str:
    """把模板里的 `{占位符}` 换成实际值；缺参数或参数名拼错都当场报错。"""
    need = placeholders(url)
    missing = [n for n in need if n not in params]
    extra = [k for k in params if k not in need]
    if missing:
        raise PathParamError(
            f"{url} 缺少占位符：{'、'.join(missing)}（需要：{'、'.join(need) or '无'}）"
        )
    if extra:
        raise PathParamError(
            f"{url} 没有这些占位符：{'、'.join(sorted(extra))}（需要：{'、'.join(need) or '无'}）"
        )
    out = url
    for name in need:
        out = out.replace("{" + name + "}", urllib.parse.quote(str(params[name]), safe=""))
    return out


def scopes() -> tuple[str, ...]:
    """官方全部 scope（给应用配数据范围时照着勾）。"""
    return tuple(sorted({s for e in ENTRIES for s in e.scopes}))


def groups() -> tuple[str, ...]:
    return tuple(sorted({e.group for e in ENTRIES if e.group}))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="查端点表（生成数据见 scripts/endpoints.py）")
    ap.add_argument("--groups", action="store_true", help="列出全部分组")
    ap.add_argument("--scopes", action="store_true", help="列出官方全部 scope")
    ap.add_argument("--list", metavar="关键词", help="按分组/名称/路径模糊列出")
    ap.add_argument("--show", nargs=2, metavar=("METHOD", "PATH"), help="精确查一个端点")
    args = ap.parse_args(argv)

    if args.groups:
        for g in groups():
            print("%-14s %d 个" % (g, len(find(group=g))))
        return 0
    if args.scopes:
        for s in scopes():
            print(s)
        return 0
    if args.show:
        method, path = args.show
        try:
            e = require(method, path)
        except EndpointError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print("%s %s" % (e.method, e.url))
        print("分组   %s" % e.group)
        print("名称   %s" % e.title)
        print("scopes %s" % ("、".join(e.scopes) or "（无）"))
        print("令牌   %s" % ("、".join(e.perms) or "（无）"))
        if e.query_template:
            print("查询模板 %s" % "&".join("%s=%s" % kv for kv in e.query_template))
        return 0
    if args.list:
        hits = find(contains=args.list) or find(group=args.list)
        if not hits:
            print("没有匹配的端点：%s" % args.list, file=sys.stderr)
            return 1
        for e in hits:
            print("%-6s %-72s %s" % (e.method, e.url, e.title))
        print("共 %d 个" % len(hits))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
