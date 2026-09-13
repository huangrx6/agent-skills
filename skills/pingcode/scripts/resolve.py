#!/usr/bin/env python3
"""字典缓存 + 「名字 → ID」解析。

两件事放一个文件，因为它们互为前提：解析需要把字典拉下来，而字典拉下来就是为了解析。

**只有字典类数据进缓存。** 项目 / 迭代 / 工作项类型 / 状态 / 优先级 / 标签 / 成员 ——
这些"配好了就不怎么变"的东西。工作项列表**绝不缓存**：那是业务数据，缓存它只会得到
一个看着像真的、其实过期的答案。（参考实现把「当前用户的工作项列表」也缓存了。）

解析规则（顺序固定，先严后宽）：

1. ID 精确匹配 → 命中
2. 名字/标识精确匹配（忽略大小写）→ 命中
3. 唯一的子串匹配 → 命中
4. 多个候选 → `Ambiguous`，**列出候选让人选**，不自动取第一个
5. 没有 → `NotFound`，列出可用的名字

第 4 条是刻意的：两个叫"支付"的迭代里选错一个，比报错更糟 —— 报错只多花一步，
选错会静默改错东西。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from typing import Any

CACHE_TTL = 6 * 3600      # 字典默认 6 小时
CACHE_FORMAT = 1


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


_config = _load_sibling("config")
_api = _load_sibling("api_index")

# kind → 端点模板、名字、需要哪些上下文参数。
# 这张表是**唯一一处**定义"字典类数据有哪些"，加一种只改这里。
SOURCES: dict[str, dict[str, Any]] = {
    "projects": {
        "label": "项目",
        "url": "/v1/pjm/projects",
        "needs": (),
        "scopes": ("pcp:read:pjm:project",),
    },
    "sprints": {
        "label": "迭代",
        "url": "/v1/pjm/projects/{project_id}/sprints",
        "needs": ("project_id",),
        "scopes": ("pcp:read:pjm:sprint",),
    },
    "types": {
        "label": "工作项类型",
        "url": "/v1/pjm/workitem/types?project_id={project_id}",
        "needs": ("project_id",),
        "scopes": ("pcp:read:pjm:workitem",),
    },
    "states": {
        "label": "工作项状态",
        "url": "/v1/pjm/workitem/states?project_id={project_id}&workitem_type_id={workitem_type_id}",
        "needs": ("project_id", "workitem_type_id"),
        "scopes": ("pcp:read:pjm:workitem",),
    },
    "priorities": {
        "label": "优先级",
        "url": "/v1/pjm/workitem/priorities?project_id={project_id}",
        "needs": ("project_id",),
        "scopes": ("pcp:read:pjm:configuration",),
    },
    "tags": {
        "label": "工作项标签",
        "url": "/v1/pjm/workitem/tags?project_id={project_id}",
        "needs": ("project_id",),
        "scopes": ("pcp:read:pjm:workitem",),
    },
    "users": {
        "label": "企业成员",
        "url": "/v1/directory/users",
        "needs": (),
        "scopes": ("pcp:read:global:team",),
    },
    "project_states": {
        "label": "项目状态",
        "url": "/v1/pjm/project/states?project_id={project_id}",
        "needs": ("project_id",),
        "scopes": ("pcp:read:pjm:project",),
    },
    "processes": {
        "label": "项目流程",
        "url": "/v1/pjm/processes",
        "needs": (),
        "scopes": ("pcp:read:pjm:configuration",),
    },
}

# 系统类型的固定枚举（官方文档：9 种系统类型）。类型列表接口返回的 id 就是这些，
# 所以 `--type bug` 与 `--type 缺陷` 都能用，不依赖中文名匹配。
SYSTEM_TYPES = {
    "epic": "史诗", "feature": "特性", "story": "用户故事", "stage": "阶段",
    "milestone": "里程碑", "requirement": "需求", "task": "任务", "bug": "缺陷", "issue": "事务",
}

ME_ALIASES = ("@me", "@我", "me", "我", "自己", "myself")


class NotFound(Exception):
    """没找到。消息里带可选项，避免调用方对着"找不到"发呆。"""


class Ambiguous(Exception):
    """匹配到多个。列出候选，让调用方选 —— 不自动取第一个。"""


def _as_float(value: object, default: float = 0.0) -> float:
    """宽松取浮点：缓存文件是本地状态，一个字段坏了不该让解析整个失败。"""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _fingerprint(kind: str, keys: dict[str, Any]) -> str:
    parts = [f"{k}={keys[k]}" for k in sorted(keys)]
    return kind + ("|" + "&".join(parts) if parts else "")


def _read_cache() -> dict[str, Any]:
    data = _config.load_cache()
    if data.get("format") != CACHE_FORMAT:
        return {}
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return {}
    return dict(entries)


def cached(kind: str, keys: dict[str, Any]) -> list[dict[str, Any]] | None:
    entry = _read_cache().get(_fingerprint(kind, keys))
    if not isinstance(entry, dict):
        return None
    if time.time() - _as_float(entry.get("at")) > CACHE_TTL:
        return None
    values = entry.get("values")
    return list(values) if isinstance(values, list) else None


def store(kind: str, keys: dict[str, Any], values: list[dict[str, Any]]) -> None:
    entries = _read_cache()
    entries[_fingerprint(kind, keys)] = {"at": time.time(), "values": values}
    _config.save_cache({"format": CACHE_FORMAT, "entries": entries})


def clear() -> None:
    _config.save_cache({"format": CACHE_FORMAT, "entries": {}})


def invalidate(kind: str) -> None:
    """丢掉某类字典的**全部**缓存。新建 / 改名之后必须调。

    实测踩到：刚建完项目，紧接着建工作项就报「没有叫 X 的项目」——
    `projects` 缓存还是 6 小时前那份，里面根本没有新项目。
    新建 / 改名会让整张字典失效，所以是整类清，而不是只清某一条。
    """
    entries = _read_cache()
    prefix = kind + "|"
    kept = {key: value for key, value in entries.items()
            if key != kind and not key.startswith(prefix)}
    if len(kept) != len(entries):
        _config.save_cache({"format": CACHE_FORMAT, "entries": kept})


def items(kind: str, client: Any, force: bool = False, **keys: Any) -> list[dict[str, Any]]:
    """拉一种字典（默认先读缓存）。`force=True` 跳过缓存。"""
    spec = SOURCES.get(kind)
    if spec is None:
        raise NotFound(f"未知的字典类型 {kind!r}；可用：{'、'.join(sorted(SOURCES))}")
    missing = [n for n in spec["needs"] if not keys.get(n)]
    if missing:
        raise NotFound(f"{spec['label']} 需要这些上下文参数：{'、'.join(missing)}")

    if not force:
        hit = cached(kind, keys)
        if hit is not None:
            return hit

    url = _api.build(spec["url"], **{k: keys[k] for k in spec["needs"]})
    # 上下文参数已经填进 url 模板了，**不要再传给 paginate** —— 否则会拼出
    # `?project_id=pj1&…&project_id=pj1` 这种重复参数（真发出去服务端行为未知）。
    values = client.paginate(url)
    # dry-run 下不能写缓存：那种“空结果”不是真实数据，存进去会把后面的命令也带歪
    # （实测撞到过：dry-run 建工作项后，优先级缓存被写成空表，之后一直说“没有可选项”）。
    if not getattr(client, "dry_run", False):
        store(kind, keys, values)
    return values


def _aliases(item: dict[str, Any]) -> list[str]:
    """一条记录上所有可用来匹配的写法。

    实测：PingCode 成员的 `name` 是**手机号**，真名在 `display_name`；只匹配 name 的话，
    用户写「黄任翔」会被告诉「没有这个成员」。邮箱/手机号也一并收进来，方便按邮箱指派。
    """
    return [str(item.get(key) or "") for key in
            ("name", "display_name", "identifier", "email", "mobile")]


def _name_of(item: dict[str, Any], kind: str) -> str:
    if kind == "projects":
        ident = str(item.get("identifier", "") or "")
        name = str(item.get("name", "") or "")
        return f"{name}（{ident}）" if ident else name
    if kind == "users":
        # 优先给人看得懂的那一个（display_name 才是真名）
        return str(item.get("display_name") or item.get("name") or "")
    return str(item.get("name", "") or "")


def labels(kind: str, values: list[dict[str, Any]]) -> list[str]:
    return [_name_of(v, kind) for v in values]


def find(kind: str, client: Any, text: str, force: bool = False,
         **keys: Any) -> dict[str, Any]:
    """把用户写的名字/标识/ID 解析成一个字典项。"""
    query = str(text or "").strip()
    if not query:
        raise NotFound(f"没给{SOURCES.get(kind, {}).get('label', kind)}")
    values = items(kind, client, force=force, **keys)
    if not values:
        raise NotFound(f"这个范围里没有{SOURCES[kind]['label']}可选项")

    want = query.lower()
    for item in values:                       # 1. ID
        if str(item.get("id", "")).lower() == want:
            return item
    for item in values:                       # 2. 名字 / 标识 / 真名 / 邮箱 / 手机
        if any(alias.lower() == want for alias in _aliases(item)):
            return item
    if kind == "types" and want in SYSTEM_TYPES:   # 系统类型枚举别名
        for item in values:
            if str(item.get("id", "")).lower() == want:
                return item
    for item in values:                       # 3. 中文名匹配系统类型枚举
        if kind == "types" and SYSTEM_TYPES.get(want) == str(item.get("name", "")):
            return item

    hits = [i for i in values
            if any(want in alias.lower() for alias in _aliases(i))]
    if len(hits) == 1:                        # 4. 唯一子串
        return hits[0]
    if len(hits) > 1:
        shown = "、".join(_name_of(i, kind) for i in hits[:12])
        raise Ambiguous(
            f"{query!r} 匹配到 {len(hits)} 个{SOURCES[kind]['label']}，请写全：{shown}"
        )
    shown = "、".join(_name_of(i, kind) for i in values[:12])
    more = "" if len(values) <= 12 else f" …（共 {len(values)} 个）"
    raise NotFound(f"没有叫 {query!r} 的{SOURCES[kind]['label']}。可选项：{shown}{more}")


def project_id(client: Any, project: str, force: bool = False) -> tuple[str, str]:
    """解析项目 → (id, 展示名)。"""
    item = find("projects", client, project, force=force)
    return str(item.get("id", "")), _name_of(item, "projects")


def type_id(client: Any, project: str, workitem_type: str, force: bool = False) -> str:
    """解析工作项类型 → type_id（系统类型是 `bug` 这样的枚举）。"""
    item = find("types", client, workitem_type, force=force, project_id=project)
    return str(item.get("id", ""))


def state_id_for(client: Any, project: str, workitem_type_id: str, state: str,
                 force: bool = False) -> str:
    """解析状态 → state_id。**必须先按项目 + 类型取状态**，不同类型的状态表不一样。"""
    item = find("states", client, state, force=force,
                project_id=project, workitem_type_id=workitem_type_id)
    return str(item.get("id", ""))


def user_id(client: Any, who: str, force: bool = False) -> str:
    """解析成员 → user_id。`@me`/`我` 需要用户令牌（走 /v1/myself）。"""
    text = str(who or "").strip()
    if text.lower() in ME_ALIASES:
        auth = _load_sibling("auth")
        me = auth.whoami(client)
        got = str(me.get("id", "") or "")
        if not got:
            raise NotFound("/v1/myself 没返回 id，无法识别「我」")
        return got
    item = find("users", client, text, force=force)
    return str(item.get("id", ""))
