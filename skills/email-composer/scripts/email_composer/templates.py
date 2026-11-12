"""模板库：列出、查看、套用、存为、更新、归档、删除。

模板是「内容 Spec + 变量声明 + 样式引用 + 样例」。变量只做字面值替换，
缺变量就报错，不默认填充；套用后与直接渲染走同一套校验。
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from . import SKILL_ROOT, rawhtml, render, styles, validate, yamlish
from .spec import SpecError, filename_base, iter_images, load_spec, normalize, type_label

__all__ = [
    "TemplateError",
    "root_dir",
    "load_index",
    "list_templates",
    "show",
    "candidates",
    "save",
    "update",
    "apply",
    "archive",
    "restore",
    "remove",
    "apply_vars",
    "parse_assignments",
]

INDEX_NAME = "index.json"
HTML_DIR = "html"
VAR_RE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
EXACT_VAR_RE = re.compile(r"^\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}$")
VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
BRACKET_RE = re.compile(r"【[^】]+】")
DATE_OR_TIME_RE = re.compile(
    r"\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}(?:\s*日)?|\d{1,2}:\d{2}"
)
DATETIME_RE = re.compile(
    r"\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}(?:\s*日)?\s+\d{1,2}:\d{2}"
)


class TemplateError(ValueError):
    """模板操作失败：变量缺失、结构冲突、入库门槛未过。"""


class MissingVars(TemplateError):
    """套用模板时缺少必填变量。"""

    def __init__(self, names: list[str]):
        self.names = names
        super().__init__("缺少必填变量：" + ", ".join(names))


class _Injected(list):
    """整值替换进来的列表，用于在父列表中展开一层。"""


def root_dir(explicit: str | None = None) -> Path:
    """模板库根目录。

    优先级：--root > EMAIL_TEMPLATES_DIR > 当前目录的 email-templates/ > skill 自带 templates/。
    当前目录有项目模板时优先用它；否则用随 skill 安装的个人模板库。
    """
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("EMAIL_TEMPLATES_DIR")
    if env:
        return Path(env).expanduser()
    project = Path.cwd() / "email-templates"
    if project.is_dir():
        return project
    return SKILL_ROOT / "templates"


def load_index(root: Path) -> dict:
    path = root / INDEX_NAME
    if not path.is_file():
        return {"version": 1, "templates": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TemplateError(f"模板索引损坏：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise TemplateError(f"模板索引顶层需要对象：{path}")
    data.setdefault("version", 1)
    data.setdefault("templates", {})
    return data


def _write_index(root: Path, index: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / INDEX_NAME
    path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _entry(root: Path, tid: str) -> dict:
    index = load_index(root)
    entry = index["templates"].get(tid)
    if not entry:
        raise TemplateError(f"模板不存在：{tid}")
    return entry


def _version_number(version: str) -> int:
    match = re.fullmatch(r"v(\d+)", version or "")
    if not match:
        raise TemplateError(f"版本号需要形如 v1：{version!r}")
    return int(match.group(1))


def _version_dir(root: Path, tid: str, version: str | None = None) -> Path:
    entry = _entry(root, tid)
    version = version or entry.get("current") or "v1"
    _version_number(version)
    path = root / tid / version
    if not path.is_dir():
        raise TemplateError(f"模板版本目录不存在：{path}")
    return path


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TemplateError(f"读取失败：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise TemplateError(f"{path} 顶层需要对象")
    return data


def _html_dir(root: Path) -> Path:
    return root / HTML_DIR


def _html_paths(root: Path) -> list[Path]:
    directory = _html_dir(root)
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.glob("*.html") if not path.name.endswith(".sample.html")
    )


def _html_sidecar(path: Path) -> Path:
    return path.with_name(path.stem + ".vars.json")


def _html_name(tid: str) -> str:
    name = tid[len("html/") :] if tid.startswith("html/") else tid
    if name.endswith(".html"):
        name = name[:-5]
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise TemplateError(f"HTML 模板 id 不合法：{tid!r}")
    return name


def _html_path(root: Path, tid: str) -> Path:
    path = _html_dir(root) / f"{_html_name(tid)}.html"
    if not path.is_file():
        raise TemplateError(f"HTML 模板不存在：{path}")
    return path


def _html_meta(path: Path) -> dict:
    sidecar = _html_sidecar(path)
    data = _read_json(sidecar) if sidecar.is_file() else {}
    return {
        "id": f"html/{path.stem}",
        "kind": "html",
        "name": data.get("name") or path.stem,
        "type": data.get("type", ""),
        "scene": data.get("scene", ""),
        "description": data.get("description", ""),
        "current": "file",
        "versions": [],
        "updated": date.fromtimestamp(path.stat().st_mtime).isoformat(),
        "archived": False,
    }


def _html_matches(meta: dict, type_filter: str | None, key: str | None) -> bool:
    if type_filter and meta.get("type") != type_filter:
        return False
    haystack = " ".join(
        str(meta.get(field, "")) for field in ("name", "type", "scene", "description")
    ).lower()
    return not key or key in meta["id"].lower() or key in haystack


def list_templates(
    root: Path, type_filter: str | None = None, query: str | None = None, include_archived: bool = False
) -> list[dict]:
    index = load_index(root)
    key = query.lower() if query else None
    result = []
    for tid, entry in index["templates"].items():
        if entry.get("archived") and not include_archived:
            continue
        if type_filter and entry.get("type") != type_filter:
            continue
        haystack = " ".join(
            str(entry.get(field, "")) for field in ("name", "type", "scene", "description")
        ).lower()
        if key and key not in tid.lower() and key not in haystack:
            continue
        result.append({"id": tid, **entry})
    for path in _html_paths(root):
        meta = _html_meta(path)
        if not _html_matches(meta, type_filter, key):
            continue
        result.append(meta)
    return sorted(result, key=lambda item: (item.get("type", ""), item["id"]))


def _show_html(root: Path, tid: str) -> dict:
    path = _html_path(root, tid)
    meta = _html_meta(path)
    sidecar = _html_sidecar(path)
    if sidecar.is_file():
        variables = _read_json(sidecar).get("vars", {})
    else:
        variables = rawhtml.auto_vars(path.read_text(encoding="utf-8"))
    files = [path.name] + ([sidecar.name] if sidecar.is_file() else [])
    return {**meta, "path": str(path), "vars": variables, "files": files}


def show(root: Path, tid: str) -> dict:
    if tid.startswith("html/") or (_html_dir(root) / f"{tid}.html").is_file():
        return _show_html(root, tid)
    entry = _entry(root, tid)
    current = entry.get("current") or "v1"
    path = root / tid / current
    if not path.is_dir():
        raise TemplateError(f"模板版本目录不存在：{path}")
    vars_path = path / "vars.json"
    variables = _read_json(vars_path).get("vars", {}) if vars_path.is_file() else {}
    return {
        "id": tid,
        **entry,
        "path": str(path),
        "vars": variables,
        "files": sorted(name.name for name in path.iterdir()),
    }


# ── 变量替换 ──────────────────────────────────────────────────────────────
def _count_placeholders(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, str):
        found.update(VAR_RE.findall(node))
    elif isinstance(node, dict):
        for value in node.values():
            found.update(_count_placeholders(value))
    elif isinstance(node, list):
        for value in node:
            found.update(_count_placeholders(value))
    return found


def apply_vars(data: dict, values: dict, var_defs: dict, transform=None) -> dict:
    """把 {{name}} 替换成变量值。缺必填变量直接报错，不用默认值糊过去。"""
    missing = []
    for name, meta in var_defs.items():
        required = meta.get("required", True)
        if required and (name not in values or values[name] in (None, "")):
            missing.append(name)
    if missing:
        raise MissingVars(sorted(missing))
    unknown = sorted(set(values) - set(var_defs))
    if unknown:
        raise TemplateError("模板没有声明这些变量：" + ", ".join(unknown))

    full: dict[str, Any] = {}
    for name, meta in var_defs.items():
        if name in values:
            full[name] = values[name]
        elif not meta.get("required", True):
            full[name] = meta.get("default", "")
        else:
            full[name] = ""

    def walk(node: Any, in_list: bool = False) -> Any:
        if isinstance(node, str):
            exact = EXACT_VAR_RE.match(node)
            if exact and exact.group(1) in full:
                value = full[exact.group(1)]
                if isinstance(value, list) and in_list:
                    return _Injected(value)
                if transform and isinstance(value, str):
                    return transform(value)
                return value
            for name, value in full.items():
                token = "{{" + name + "}}"
                if token in node:
                    if isinstance(value, (list, dict)):
                        raise TemplateError(
                            f"变量 {name} 是列表/对象，只能作为整个字段值使用，不能拼进字符串：{node[:40]!r}"
                        )
                    rendered = "" if value is None else str(value)
                    if transform and isinstance(value, str):
                        rendered = transform(value)
                    node = node.replace(token, rendered)
            return node
        if isinstance(node, list):
            result = []
            for item in node:
                value = walk(item, in_list=True)
                if isinstance(value, _Injected):
                    result.extend(walk(entry, in_list=False) for entry in value)
                else:
                    result.append(value)
            return result
        if isinstance(node, dict):
            return {key: walk(value) for key, value in node.items()}
        return node

    result = walk(data)
    leftover = _count_placeholders(result)
    if leftover:
        raise TemplateError("模板里还有未声明的变量：" + ", ".join(sorted(leftover)))
    return result


# ── 候选变量 ──────────────────────────────────────────────────────────────
def _walk_strings(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _walk_strings(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node, start=1):
            yield from _walk_strings(value, f"{path}[{index}]")


def candidates(spec: dict) -> list[dict]:
    """列出可参数化的候选值：日期、时间、数字、链接、重复文本、表格行。

    只扫描会进入正文的字段，不把 kind/src 这类结构键当成内容。
    这只是给用户确认的候选，不自动决定哪些该变成变量。
    """
    from .spec import iter_text_fields

    seen: dict[tuple, dict] = {}
    counts: dict[tuple, int] = {}

    def add(kind: str, value: Any, where: str) -> None:
        key = (kind, json.dumps(value, ensure_ascii=False, sort_keys=True))
        counts[key] = counts.get(key, 0) + 1
        item = seen.get(key)
        if item is None:
            seen[key] = {"kind": kind, "value": value, "paths": [where]}
        elif len(item["paths"]) < 5 and where not in item["paths"]:
            item["paths"].append(where)

    for where, value in iter_text_fields(spec):
        for match in DATETIME_RE.finditer(value):
            add("datetime", match.group(0), where)
        for token in validate.extract_tokens(value):
            kind = (
                "date"
                if token[0] in validate.DATE_KINDS
                else "time"
                if token[0] == "time"
                else "number"
            )
            add(kind, token[2], where)
        for url in validate.URL_RE.findall(value):
            add("url", url, where)
        if len(value.strip()) >= 2 and not DATE_OR_TIME_RE.search(value):
            add("repeat", value, where)

    if spec.get("greeting"):
        add("greeting", spec["greeting"], "greeting")
    for index, block in enumerate(spec.get("blocks") or [], start=1):
        if block["kind"] == "signature":
            add("person", block["name"], f"blocks[{index}].signature.name")
            if block["title"]:
                add("person", block["title"], f"blocks[{index}].signature.title")
        if block["kind"] == "table":
            for row_index, row in enumerate(block["rows"], start=1):
                add("row", row, f"blocks[{index}].rows[{row_index}]")
        elif block["kind"] == "images":
            for item_index, item in enumerate(block["items"], start=1):
                if not item["src"].startswith("data:"):
                    add("url", item["src"], f"blocks[{index}].items[{item_index}].src")
        elif block["kind"] == "cta":
            add("url", block["url"], f"blocks[{index}].url")

    result = []
    for key, item in seen.items():
        item["count"] = counts[key]
        if item["kind"] == "repeat" and item["count"] < 2:
            continue
        result.append(item)
    order = {
        "datetime": 0,
        "date": 1,
        "time": 2,
        "number": 3,
        "url": 4,
        "greeting": 5,
        "person": 6,
        "repeat": 7,
        "row": 8,
    }
    return sorted(
        result,
        key=lambda item: (
            order.get(item["kind"], 9),
            -item["count"],
            json.dumps(item["value"], ensure_ascii=False),
        ),
    )


# ── 保存与更新 ────────────────────────────────────────────────────────────
def _prune(node: Any) -> Any:
    """去掉模板里的空字段；列表元素保留，表格空单元格不能被删。"""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if value is None or value == "" or value == [] or value == {}:
                continue
            out[key] = _prune(value)
        return out
    if isinstance(node, list):
        return [_prune(value) for value in node]
    return node


def _clean_spec(spec: dict) -> dict:
    data: dict[str, Any] = {
        "type": spec["type"],
        "secondary": spec.get("secondary") or [],
        "audience": spec.get("audience") or "",
        "tone": spec.get("tone") or "",
        "subject": spec.get("subject") or "",
        "greeting": spec.get("greeting") or "",
        "summary": spec.get("summary") or "",
        "urgent": bool(spec.get("urgent")),
        "blocks": spec.get("blocks") or [],
        "facts": spec.get("facts") or [],
        "placeholders": spec.get("placeholders") or [],
    }
    if spec.get("style"):
        data["style"] = spec["style"]
    for key in ("secondary", "audience", "tone", "greeting", "summary", "facts", "placeholders"):
        if not data.get(key):
            data.pop(key, None)
    if not data.get("urgent"):
        data.pop("urgent", None)
    return _prune(data)


def _replace_literals(node: Any, mapping: dict[str, str], counts: dict[str, int]) -> Any:
    if isinstance(node, str):
        for literal, name in mapping.items():
            counts.setdefault(literal, 0)
            counts[literal] += node.count(literal)
        if not mapping:
            return node
        ordered = sorted(mapping, key=len, reverse=True)
        pattern = re.compile("|".join(re.escape(item) for item in ordered))
        return pattern.sub(lambda match: "{{" + mapping[match.group(0)] + "}}", node)
    if isinstance(node, list):
        return [_replace_literals(item, mapping, counts) for item in node]
    if isinstance(node, dict):
        return {key: _replace_literals(value, mapping, counts) for key, value in node.items()}
    return node


def parse_assignments(items: list[str] | None, flag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise TemplateError(f"{flag} 需要「原值=变量名」：{item!r}")
        literal, name = item.rsplit("=", 1)
        literal, name = literal.strip(), name.strip()
        if name.startswith("{{") and name.endswith("}}"):
            name = name[2:-2].strip()
        if not literal:
            raise TemplateError(f"{flag} 的原值不能为空：{item!r}")
        if not VAR_NAME_RE.match(name):
            raise TemplateError(f"{flag} 的变量名不合法：{name!r}（需以字母或下划线开头，只含字母、数字、下划线）")
        if literal in result:
            raise TemplateError(f"{flag} 重复声明同一个原值：{literal!r}")
        result[literal] = name
    return result


def _var_defs(
    required: dict[str, str],
    optional: dict[str, str],
    descriptions: dict[str, str],
) -> dict:
    names = list(required.values()) + list(optional.values())
    if len(names) != len(set(names)):
        raise TemplateError("变量名重复")
    defs = {}
    for literal, name in required.items():
        defs[name] = {
            "required": True,
            "description": descriptions.get(name, ""),
            "example": literal,
        }
    for literal, name in optional.items():
        if name in defs:
            raise TemplateError(f"变量名重复：{name}")
        defs[name] = {
            "required": False,
            "description": descriptions.get(name, ""),
            "example": literal,
            "default": literal,
        }
    return defs


def _style_reference(spec: dict, tokens: dict) -> dict:
    style = spec.get("style")
    overrides = {}
    if isinstance(style, dict) and isinstance(style.get("overrides"), dict):
        overrides = style["overrides"]
    return {"preset": tokens["name"], "overrides": overrides}


def _readme(entry: dict) -> str:
    lines = [
        f"# {entry['name']}",
        "",
        f"- 模板 id：`{entry['id']}`",
        f"- 类型：{entry['type']}",
        f"- 场景：{entry.get('scene') or '未标注'}",
        f"- 当前版本：{entry['current']}",
        f"- 更新：{entry['updated']}",
        "",
        "## 适用场景",
        "",
        entry.get("description") or f"{entry['type']} 类邮件，内容结构固定、只换变量。",
        "",
        "## 使用方法",
        "",
        "```sh",
        f"python3 scripts/template.py apply {entry['id']} --vars vars.json --outdir ./email-out",
        "```",
        "",
        "必填变量缺失时 `apply` 会报错退出，不会默认填充。",
        "",
        "## 变量",
        "",
        "| 变量 | 必填 | 说明 | 示例 |",
        "| --- | --- | --- | --- |",
    ]
    for name, meta in entry["vars"].items():
        lines.append(
            f"| `{name}` | {'是' if meta.get('required', True) else '否'} | "
            f"{meta.get('description') or '—'} | {meta.get('example') or '—'} |"
        )
    lines.extend(["", "## 更新记录", ""])
    for item in entry.get("history") or []:
        lines.append(f"- {item['version']} {item['date']}：{item.get('note') or '更新'}")
    return "\n".join(lines) + "\n"


def _render_sample(data: dict, preset: str, base_dir: str) -> tuple[str, str, dict]:
    spec = normalize(data, source="<sample>")
    tokens, _, _ = styles.resolve(spec, preset=preset)
    html_body = render.render_html(spec, tokens)
    text_body = render.render_text(spec)
    md_body = render.render_markdown(spec)
    report = validate.validate_spec(spec, tokens, html_body, text_body, md_body, base_dir)
    return html_body, preset, report


def _write_template(
    root: Path,
    tid: str,
    version: str,
    data: dict,
    defs: dict,
    style_ref: dict,
    sample_html: str,
    entry: dict,
) -> Path:
    target = root / tid / version
    if target.exists():
        raise TemplateError(f"版本已存在：{target}")
    (root / tid).mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{tid}-{version}-", dir=str(root / tid)))
    try:
        (tmp / "template.yaml").write_text(yamlish.dumps(data), encoding="utf-8")
        (tmp / "vars.json").write_text(
            json.dumps({"version": 1, "vars": defs}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (tmp / "style.json").write_text(
            json.dumps(style_ref, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (tmp / "sample.html").write_text(sample_html, encoding="utf-8")
        (tmp / "README.md").write_text(_readme(entry), encoding="utf-8")
        os.replace(tmp, target)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return target


def _check_sensitive(text: str) -> None:
    emails = sorted(set(EMAIL_RE.findall(text)))
    phones = sorted(set(PHONE_RE.findall(text)))
    if emails or phones:
        raise TemplateError(
            "模板里仍有真实邮箱或电话，请改成变量后再入库："
            + ", ".join(emails + phones)
        )


def _check_template_gate(text: str, defs: dict) -> list[str]:
    warnings = []
    _check_sensitive(text)
    _check_sensitive(json.dumps(defs, ensure_ascii=False))
    dates = sorted(set(DATE_OR_TIME_RE.findall(text)))
    if dates:
        raise TemplateError(
            "模板里仍有具体日期或时间，请改成变量后再入库：" + ", ".join(dates[:5])
        )
    numbers = sorted(
        {
            token[2]
            for token in validate.extract_tokens(text)
            if token[0] == "num" and token[1] != 0
        }
    )
    if numbers:
        warnings.append(
            {
                "code": "template_numbers",
                "message": "模板仍含数字（可能是固定阈值）：" + ", ".join(numbers[:8]),
                "where": "template.yaml",
            }
        )
    return warnings


def _build(
    spec_path: str,
    root: Path,
    tid: str,
    name: str,
    scene: str,
    description: str,
    required: dict[str, str],
    optional: dict[str, str],
    descriptions: dict[str, str],
    note: str,
    today: str,
    version: str,
    history: list[dict],
) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", tid or ""):
        raise TemplateError("模板 id 只能用小写字母、数字和连字符，且以字母或数字开头")
    spec = load_spec(spec_path)
    if not spec["type"]:
        raise TemplateError("规格缺少 type，不能存为模板")
    data = _clean_spec(spec)
    mapping = {**required, **optional}
    counts: dict[str, int] = {}
    data = _replace_literals(data, mapping, counts)
    absent = [literal for literal in mapping if counts.get(literal, 0) == 0]
    if absent:
        raise TemplateError("这些原值在规格里没有出现，无法设为变量：" + ", ".join(repr(x) for x in absent))
    defs = _var_defs(required, optional, descriptions)
    text = yamlish.dumps(data)
    warnings = _check_template_gate(text, defs)

    examples = {key: meta["example"] for key, meta in defs.items()}
    sample_data = apply_vars(data, examples, defs)
    tokens, preset, _ = styles.resolve(spec)
    sample_html, _, report = _render_sample(sample_data, preset, os.path.dirname(spec_path))
    if not report["ok"]:
        first = report["blocking"][0]["message"] if report["blocking"] else "未知阻断项"
        raise TemplateError(f"样例校验未通过，不能入库：{first}")

    entry = {
        "id": tid,
        "name": name,
        "type": spec["type"],
        "scene": scene,
        "description": description,
        "current": version,
        "versions": [item["version"] for item in history],
        "created": (history[0]["date"] if history else today),
        "updated": today,
        "archived": False,
        "history": history,
        "vars": defs,
    }
    style_ref = _style_reference(spec, tokens)
    target = _write_template(root, tid, version, data, defs, style_ref, sample_html, entry)

    index = load_index(root)
    previous = index["templates"].get(tid, {})
    versions = list(previous.get("versions") or [])
    if version not in versions:
        versions.append(version)
    entry["versions"] = sorted(versions, key=_version_number)
    entry.pop("vars", None)
    index["templates"][tid] = entry
    _write_index(root, index)
    return {
        "ok": True,
        "id": tid,
        "version": version,
        "path": str(target),
        "variables": defs,
        "warnings": warnings + report["warnings"],
        "sample_validation": report,
    }


def save(
    spec_path: str,
    root: Path,
    tid: str,
    name: str,
    scene: str = "",
    description: str = "",
    required: dict[str, str] | None = None,
    optional: dict[str, str] | None = None,
    descriptions: dict[str, str] | None = None,
    note: str = "",
    today: str | None = None,
) -> dict:
    index = load_index(root)
    if tid in index["templates"]:
        raise TemplateError(f"模板已存在：{tid}；要改内容请用 update 生成新版本")
    day = today or date.today().isoformat()
    return _build(
        spec_path,
        root,
        tid,
        name,
        scene,
        description,
        required or {},
        optional or {},
        descriptions or {},
        note or "从规格生成",
        day,
        "v1",
        [{"version": "v1", "date": day, "note": note or "从规格生成"}],
    )


def update(
    spec_path: str,
    root: Path,
    tid: str,
    name: str | None = None,
    scene: str | None = None,
    description: str | None = None,
    required: dict[str, str] | None = None,
    optional: dict[str, str] | None = None,
    descriptions: dict[str, str] | None = None,
    note: str = "",
    today: str | None = None,
) -> dict:
    index = load_index(root)
    entry = index["templates"].get(tid)
    if not entry:
        raise TemplateError(f"模板不存在：{tid}")
    day = today or date.today().isoformat()
    version = f"v{max(_version_number(item) for item in entry.get('versions', ['v1'])) + 1}"
    history = list(entry.get("history") or [])
    previous_vars: dict = {}
    previous_dir = root / tid / (entry.get("current") or "v1")
    previous_vars_path = previous_dir / "vars.json"
    if previous_vars_path.is_file():
        previous_vars = _read_json(previous_vars_path).get("vars", {})
    merged_descriptions = {
        name: meta.get("description", "")
        for name, meta in previous_vars.items()
        if meta.get("description")
    }
    merged_descriptions.update(descriptions or {})
    history.append({"version": version, "date": day, "note": note or "更新"})
    result = _build(
        spec_path,
        root,
        tid,
        name or entry["name"],
        scene if scene is not None else entry.get("scene", ""),
        description if description is not None else entry.get("description", ""),
        required or {},
        optional or {},
        merged_descriptions,
        note or "更新",
        day,
        version,
        history,
    )
    return result


# ── 套用 ──────────────────────────────────────────────────────────────────
def _load_values(path: str | None, overrides: list[str] | None) -> dict:
    values: dict[str, Any] = {}
    if path:
        data = _read_json(Path(path))
        values.update(data.get("vars", data) if isinstance(data.get("vars"), dict) else data)
    for item in overrides or []:
        if "=" not in item:
            raise TemplateError(f"--set 需要「变量名=值」：{item!r}")
        name, value = item.split("=", 1)
        values[name.strip()] = value
    return values


def _write_outputs(outputs: dict, outdir: str) -> dict:
    target = Path(outdir).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    files = {}
    for fmt, (filename, content) in outputs.items():
        file_path = target / filename
        if isinstance(content, bytes):
            file_path.write_bytes(content)
        else:
            file_path.write_text(content, encoding="utf-8")
        files[fmt] = str(file_path)
    return files


def apply_html(
    root: Path,
    tid: str,
    values_path: str | None = None,
    overrides: list[str] | None = None,
    outdir: str = "email-out",
    formats: tuple[str, ...] | None = None,
    day: str | None = None,
    to: str | None = None,
    cc: list[str] | None = None,
    subject: str | None = None,
) -> dict:
    """套用原始 HTML 模板：只做字面变量替换、HTML 兼容校验与纯文本提取。"""
    path = _html_path(root, tid)
    text = path.read_text(encoding="utf-8")
    sidecar = _html_sidecar(path)
    detected = rawhtml.auto_vars(text)
    if sidecar.is_file():
        defs = _read_json(sidecar).get("vars", {})
        undeclared = sorted(set(detected) - set(defs))
        if undeclared:
            raise TemplateError(
                "vars.json 未声明这些变量：" + ", ".join(undeclared) + "；先更新 sidecar 再套用"
            )
    else:
        defs = detected
    _check_template_gate(html_lib.unescape(text), defs)
    unused = sorted(set(defs) - set(detected))
    values = _load_values(values_path, overrides)
    data = apply_vars(
        {"html": text},
        values,
        defs,
        transform=lambda value: html_lib.escape(value, quote=True),
    )
    html_body = data["html"]
    subject_value = (subject or rawhtml.extract_title(html_body) or path.stem).strip()
    selected = tuple(formats) if formats else ("html", "text")
    unknown_formats = [fmt for fmt in selected if fmt not in render.ALL_FORMATS]
    if unknown_formats:
        raise TemplateError("未知格式：" + ", ".join(unknown_formats))
    if "md" in selected:
        raise TemplateError("HTML 模板不输出 Markdown；可用 html / text / eml")
    text_body = rawhtml.html_to_text(html_body)
    report = rawhtml.validate_html_template(html_body, text_body, subject_value, to, cc, _html_meta(path).get("type", ""))
    if not report["ok"]:
        return {
            "ok": False,
            "id": f"html/{path.stem}",
            "kind": "html",
            "report": report,
            "note": "校验有阻断项，未写出文件。修好 HTML 或补齐变量后重试。",
        }
    day_value = date.fromisoformat(day) if day else None
    base = filename_base(subject_value, day=day_value)
    outputs: dict[str, tuple[str, str | bytes]] = {}
    if "html" in selected:
        outputs["html"] = (f"{base}.html", html_body)
    if "text" in selected:
        outputs["text"] = (f"{base}.txt", text_body)
    notes: list[str] = []
    if "eml" in selected:
        content, eml_notes = render.build_eml(
            subject_value, html_body, text_body, str(path.parent), to, cc
        )
        outputs["eml"] = (f"{base}.eml", content)
        notes.extend(eml_notes)
    if unused:
        notes.append("vars.json 有未出现在 HTML 中的变量：" + ", ".join(unused))
    files = _write_outputs(outputs, outdir)
    return {
        "ok": True,
        "id": f"html/{path.stem}",
        "kind": "html",
        "subject": subject_value,
        "files": files,
        "notes": notes,
        "report": report,
    }


def apply(
    root: Path,
    tid: str,
    values_path: str | None = None,
    overrides: list[str] | None = None,
    outdir: str = "email-out",
    formats: tuple[str, ...] | None = None,
    version: str | None = None,
    day: str | None = None,
    to: str | None = None,
    cc: list[str] | None = None,
    subject: str | None = None,
) -> dict:
    if tid.startswith("html/") or (_html_dir(root) / f"{tid}.html").is_file():
        return apply_html(
            root, tid, values_path, overrides, outdir, formats, day, to, cc, subject
        )

    entry = _entry(root, tid)
    path = _version_dir(root, tid, version)
    template = yamlish.load_file(str(path / "template.yaml"))
    defs = _read_json(path / "vars.json").get("vars", {})
    style_path = path / "style.json"
    style_file = str(style_path) if style_path.is_file() else None
    values = _load_values(values_path, overrides)
    data = apply_vars(template, values, defs)
    spec = normalize(data, source=str(path / "template.yaml"))
    if subject:
        spec["subject"] = subject
    if to:
        spec["to"] = to
    if cc:
        spec["cc"] = cc
    tokens, preset, reason = styles.resolve(spec, style_file=style_file)
    base_dir = str(path)
    html_body = render.render_html(spec, tokens)
    text_body = render.render_text(spec)
    md_body = render.render_markdown(spec)
    report = validate.validate_spec(spec, tokens, html_body, text_body, md_body, base_dir)
    if not report["ok"]:
        return {
            "ok": False,
            "id": tid,
            "version": entry.get("current"),
            "report": report,
            "preset": preset,
            "style": render.style_summary(tokens),
            "note": "校验有阻断项，未写出文件。补齐变量或修好内容后重试。",
        }
    day_value = date.fromisoformat(day) if day else None
    outputs, notes = render.build_outputs(
        spec, tokens, base_dir, formats=formats or ("html", "text", "md"), day=day_value
    )
    files = _write_outputs(outputs, outdir)
    return {
        "ok": True,
        "id": tid,
        "version": version or entry.get("current"),
        "files": files,
        "preset": preset,
        "preset_reason": reason,
        "style": render.style_summary(tokens),
        "notes": notes,
        "report": report,
    }


def add_html(root: Path, source: str, tid: str | None = None, force: bool = False) -> dict:
    """把现成 HTML 复制到扩展模板目录，并补齐变量声明。"""
    src = Path(source).expanduser()
    if not src.is_file():
        raise TemplateError(f"找不到 HTML 文件：{src}")
    name = _html_name(tid or src.stem)
    dest_dir = _html_dir(root)
    dest = dest_dir / f"{name}.html"
    if dest.exists() and not force:
        raise TemplateError(f"HTML 模板已存在：{dest}；覆盖请加 --force")
    text = src.read_text(encoding="utf-8")
    sidecar = _html_sidecar(dest)
    if sidecar.is_file():
        data = _read_json(sidecar)
    else:
        data = {"version": 1, "name": name, "type": "", "scene": "", "description": "", "vars": {}}
    data.setdefault("vars", {})
    for var_name, meta in rawhtml.auto_vars(text).items():
        data["vars"].setdefault(var_name, meta)
    _check_template_gate(html_lib.unescape(text), data.get("vars", {}))
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    sidecar.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    placeholders = sorted(set(BRACKET_RE.findall(text)))
    html_hits = validate.check_html_body(text)
    warnings = [item["message"] for item in html_hits]
    if placeholders:
        warnings.append(
            f"发现 {len(placeholders)} 个【...】占位，套用前改成 {{{{变量}}}}"
        )
    return {
        "ok": True,
        "id": f"html/{name}",
        "path": str(dest),
        "vars": sorted(rawhtml.auto_vars(text)),
        "placeholders": placeholders,
        "warnings": warnings,
    }

# ── 归档与删除 ────────────────────────────────────────────────────────────
def archive(root: Path, tid: str) -> dict:
    if tid.startswith("html/") or (_html_dir(root) / f"{tid}.html").is_file():
        raise TemplateError("HTML 模板不进入版本索引；归档请直接移出 html/ 目录")
    index = load_index(root)
    entry = index["templates"].get(tid)
    if not entry:
        raise TemplateError(f"模板不存在：{tid}")
    entry["archived"] = True
    entry["updated"] = date.today().isoformat()
    _write_index(root, index)
    return {"ok": True, "id": tid, "archived": True}


def restore(root: Path, tid: str) -> dict:
    if tid.startswith("html/") or (_html_dir(root) / f"{tid}.html").is_file():
        raise TemplateError("HTML 模板不进入版本索引；无需恢复")
    index = load_index(root)
    entry = index["templates"].get(tid)
    if not entry:
        raise TemplateError(f"模板不存在：{tid}")
    entry["archived"] = False
    entry["updated"] = date.today().isoformat()
    _write_index(root, index)
    return {"ok": True, "id": tid, "archived": False}


def remove(root: Path, tid: str) -> dict:
    if tid.startswith("html/") or (_html_dir(root) / f"{tid}.html").is_file():
        path = _html_path(root, tid)
        sidecar = _html_sidecar(path)
        path.unlink()
        if sidecar.is_file():
            sidecar.unlink()
        return {"ok": True, "id": f"html/{path.stem}", "removed": True}
    index = load_index(root)
    if tid not in index["templates"]:
        raise TemplateError(f"模板不存在：{tid}")
    shutil.rmtree(root / tid)
    del index["templates"][tid]
    _write_index(root, index)
    return {"ok": True, "id": tid, "removed": True}
