#!/usr/bin/env python3
"""从官方 api_data.json 生成 scripts/endpoints.py。

为什么要有这个生成器
--------------------
参考实现（第三方那个 pingcode skill）里写死了 `/v1/project/work_items`、
`/v1/project/projects` 这类路径，而官方当前文档里**根本不存在**：PJM 的前缀是
`/v1/pjm/`，且是 `workitems`（没有下划线）。它的测试 mock 了 `urllib.request.urlopen`，
所以路径写错照样全绿 —— 手抄端点的风险就是这样被掩盖的。

这里的做法：端点表**全部由官方文档生成**，生成文件里记下来源 URL、抓取时间和内容
指纹；`tests/test_endpoints.py` 拿这份表做契约测试（代码里用到的每个端点都必须先在
表里存在）。文档改了 → `--check` 报漂移 → 重新生成。

跑法
----
    python3 dev-tools/gen_endpoints.py                  # 联网抓官方文档并生成
    python3 dev-tools/gen_endpoints.py --input x.json   # 用本地快照（离线可跑）
    python3 dev-tools/gen_endpoints.py --check          # 只比对不写（漂移检测）

退出码：0 成功或无漂移 / 1 漂移或抓取失败 / 2 用法错误
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SOURCE_URL = "https://open.pingcode.com/api_data.json"
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(SKILL_ROOT, "scripts", "endpoints.py")

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

HEADER = '''#!/usr/bin/env python3
"""{doc}

**这个文件由 dev-tools/gen_endpoints.py 生成，不要手改。**
查询函数在 scripts/api_index.py（手写），它读这里的 ENTRIES。

来源      {source}
抓取时间  {fetched_at}
内容指纹  {digest}
条目      {total} 条原始条目 → {endpoints} 条接口 + {docpages} 条纯文档页

重新生成：python3 dev-tools/gen_endpoints.py
漂移检测：python3 dev-tools/gen_endpoints.py --check
"""
'''

TUPLE_DOC = '''
# (method, url 模板, scopes, 令牌要求, 分组, 名称)
#
# url 模板就是官方文档里的原始形态，带 `{占位符}` 与查询模板（如
# `/v1/auth/token?grant_type=client_credentials`），它是条目的**唯一身份** ——
# 同一路径不同 grant_type 的接口靠它区分。路径与查询参数名由 api_index 现算。
#
# 令牌要求：企业令牌 / 用户令牌 / 企业令牌/用户令牌。注意 /v1/myself 只认**用户令牌**。
'''


class SourceError(Exception):
    """抓取或读取官方文档失败。"""


def load_source(input_path: str | None, url: str) -> tuple[bytes, str]:
    """返回 (原始字节, 来源标识)。"""
    if input_path:
        try:
            with open(input_path, "rb") as fh:
                return fh.read(), os.path.abspath(input_path)
        except OSError as exc:
            raise SourceError("读取本地快照 %s 失败：%s" % (input_path, exc)) from exc
    req = urllib.request.Request(url, headers={"User-Agent": "pingcode-skill/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - 固定 https 官方源
            return resp.read(), url
    except (urllib.error.URLError, OSError) as exc:
        raise SourceError("抓取 %s 失败：%s" % (url, exc)) from exc


def split_url(url: str) -> tuple[str, tuple[str, ...]]:
    """把 `/v1/x?page_size={page_size}&page_index={page_index}` 拆成路径与参数名。"""
    path, _, query = url.partition("?")
    keys = tuple(k for k, _v in urllib.parse.parse_qsl(query, keep_blank_values=True))
    return path, keys


def normalize(raw: bytes) -> tuple[list[tuple], int, int]:
    """把官方 JSON 归一化成 ENTRIES（排序后）与两类计数。"""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("api_data.json 解析失败：%s" % exc) from exc
    if not isinstance(data, list):
        raise ValueError("api_data.json 的顶层不是数组，格式变了")

    entries: list[tuple] = []
    docpages = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        method = str(item.get("type") or "").strip().upper()
        url = str(item.get("url") or "").strip()
        if method not in METHODS or not url.startswith("/"):
            docpages += 1
            continue
        path, keys = split_url(url)
        scopes = tuple(sorted({str(s.get("name")) for s in item.get("scopes") or [] if s.get("name")}))
        perms = tuple(sorted({str(p.get("name")) for p in item.get("permission") or [] if p.get("name")}))
        group = str(item.get("group") or "").strip()
        title = str(item.get("name") or item.get("title") or "").strip()
        entries.append((method, url, scopes, perms, group, title))

    entries.sort(key=lambda e: (split_url(e[1])[0], e[0], e[1]))
    return entries, len(data), docpages


def render(entries: list[tuple], total: int, docpages: int, digest: str, fetched_at: str) -> str:
    lines = [HEADER.format(
        doc="PingCode REST 端点表（官方文档生成）。",
        source=SOURCE_URL,
        fetched_at=fetched_at,
        digest=digest,
        total=total,
        endpoints=len(entries),
        docpages=docpages,
    )]
    lines.append("\nSOURCE_URL = %r" % SOURCE_URL)
    lines.append("FETCHED_AT = %r" % fetched_at)
    lines.append("SOURCE_SHA256 = %r" % digest)
    lines.append("TOTAL_ENTRIES = %d" % total)
    lines.append("ENDPOINT_COUNT = %d" % len(entries))
    lines.append("DOC_PAGE_COUNT = %d" % docpages)
    lines.append(TUPLE_DOC.rstrip("\n"))
    lines.append("\nMETHODS: tuple[str, ...] = %r" % (METHODS,))
    lines.append("ENTRIES: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], str, str], ...] = (")
    for e in entries:
        lines.append("    %s," % (repr(e),))
    lines.append(")")
    return "\n".join(lines) + "\n"


def existing_entries(path: str):
    """读回已生成文件里的 ENTRIES（查不到就返回 None）。"""
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("_gen_endpoints_existing", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:  # noqa: BLE001 - 坏文件按"没有"处理，交给调用方重新生成
        return None
    return list(getattr(mod, "ENTRIES", [])), getattr(mod, "SOURCE_SHA256", "")


def diff(old: list[tuple], new: list[tuple]) -> list[str]:
    oldmap = {e[1]: e for e in old}
    newmap = {e[1]: e for e in new}
    out: list[str] = []
    for u in sorted(set(newmap) - set(oldmap)):
        out.append("  + %s %s" % (newmap[u][0], u))
    for u in sorted(set(oldmap) - set(newmap)):
        out.append("  - %s %s" % (oldmap[u][0], u))
    for u in sorted(set(oldmap) & set(newmap)):
        if oldmap[u] != newmap[u]:
            out.append("  ~ %s %s" % (newmap[u][0], u))
            out.append("      旧: %s" % (oldmap[u][2:],))
            out.append("      新: %s" % (newmap[u][2:],))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="从官方 api_data.json 生成 scripts/endpoints.py")
    ap.add_argument("--input", help="本地 api_data.json 快照（不给就联网抓）")
    ap.add_argument("--url", default=SOURCE_URL, help="官方文档地址（默认 %s）" % SOURCE_URL)
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出路径（默认 scripts/endpoints.py）")
    ap.add_argument("--check", action="store_true", help="只比对不写；有漂移退出 1")
    args = ap.parse_args(argv)

    try:
        raw, origin = load_source(args.input, args.url)
    except SourceError as exc:
        print(str(exc), file=sys.stderr)
        print("离线时用 --input 指定本地快照。", file=sys.stderr)
        return 1
    except ValueError as exc:
        print("用法错误：%s" % exc, file=sys.stderr)
        return 2

    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    try:
        entries, total, docpages = normalize(raw)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    fetched_at = datetime.date.today().isoformat()
    text = render(entries, total, docpages, digest, fetched_at)

    old_text = ""
    if os.path.isfile(args.out):
        try:
            with open(args.out, encoding="utf-8") as fh:
                old_text = fh.read()
        except OSError as exc:
            print("读取 %s 失败：%s" % (args.out, exc), file=sys.stderr)
            return 1

    # 判据是**整份文件文本是否一致**，不是只比端点集合 —— 否则改了生成模版
    # （表头、注释、元信息）会因为端点没变而永远不落地。
    if old_text == text:
        print("✓ 无漂移：文件与官方源一致（%d 条接口，%s）" % (len(entries), digest))
        return 0

    existing = existing_entries(args.out)
    changes = diff(existing[0], entries) if existing else []
    old_digest = existing[1] if existing else ""
    if changes:
        print("⚠ 端点漂移：%d 处" % len(changes))
        for line in changes:
            print(line)
    elif old_digest and old_digest != digest:
        print("· 端点集合一致，官方文档内容变了（指纹 %s → %s）" % (old_digest, digest))
    elif old_text:
        print("· 端点与指纹一致，但生成模版或元信息有变化")
    else:
        print("· 生成文件不存在：%s" % args.out)

    if args.check:
        print("  重新生成：python3 dev-tools/gen_endpoints.py")
        return 1

    try:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as exc:
        print("写入 %s 失败：%s" % (args.out, exc), file=sys.stderr)
        return 1
    print("✓ 已写入 %s（%d 条接口，来源 %s）" % (args.out, len(entries), origin))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
