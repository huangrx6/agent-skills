"""角色词表：每页"在干什么"，与"长什么样"分开。

**为什么要有角色**：页型（`type`）只说结构（双栏 / 图页 / 图表），不说这一页在做
什么。于是"有图就摆图、没图就摆卡片"会把不同性质的页渲成同一个样子 —— 两条
`metric` 页、一条 `risks` 页、一条 `actions` 页，全是"标题 + 三条"。加上角色以后：

- 配版式时有依据（`metric` 该给数字/图表，`hero_visual` 该给大图）；
- 门能看出"同一角色的两页结构完全一样"（那是重复，不是风格）；
- 内容规划时先写"这一页在干什么"，再决定用什么结构。

**这套名字与 `references/planning.md` 的页型表同源**（一份词表，两处引用）——
规划阶段判页型、spec 里写 `role`、门按同一份表验收。角色是**语义**不是结构枚举：
同一角色可以落在不同页型上（`comparison` 可以两栏也可以对比图），只有"角色与
页型明显不合"（`trend` 渲成纯文字两栏）才开口 —— 而且只提示不阻塞：编辑上的
例外是真实的（拿两栏对比讲趋势也是合理写法）。

词表是**封闭**的：未知角色由 `validate_spec.py` 拦下（拼错的角色名会让它静默失效，
和拼错 layout 名一个性质）。
"""
from __future__ import annotations

# role → (中文名, 可承载的页型, 一句"什么时候用它")
ROLES: dict[str, dict] = {
    "cover": {"label":  "封面", "visual": ('none',), "types": ("title",),
              "when": "第一页；标题 + 副题 + 一句定位"},
    "transition": {"label":  "章节分隔", "visual": ('none',), "types": ("title",),
                   "when": "换章；只给章节名"},
    "statement": {"label":  "主张 / 金句", "visual": ('none',), "types": ("content-text", "title"),
                  "when": "一个判断，字少、字大"},
    "breakdown": {"label":  "目录 / 结构拆解", "visual": ('none',), "types": ("content-text", "two-column"),
                  "when": "把后面要讲的东西列成几块"},
    "evidence": {"label":  "证据 / 细节", "visual": ('none', 'evidence_image', 'diagram'), "types": ("content-text", "content-image"),
                 "when": "给人读的页；有截图/材料就配图"},
    "metric": {"label":  "核心数字", "visual": ('data', 'none'), "types": ("chart", "content-text"),
               "when": "数字是主角；能画图就画图"},
    "trend": {"label":  "走势 / 时间", "visual": ('data', 'none'), "types": ("chart", "timeline"),
              "when": "随时间变化；折线或横向时间线"},
    "composition": {"label":  "构成 / 占比", "visual": ('data',), "types": ("chart",),
                    "when": "构成与份额"},
    "comparison": {"label":  "对比", "visual": ('none', 'data', 'evidence_image', 'diagram'), "types": ("two-column", "chart", "content-image"),
                   "when": "两边对照；两栏、对比图或文图"},
    "process": {"label":  "流程 / 路径", "visual": ('none', 'evidence_image', 'diagram'), "types": ("timeline", "content-image"),
                "when": "有几步、有先后"},
    "capabilities": {"label":  "能力并列", "visual": ('none',), "types": ("two-column", "content-text"),
                     "when": "几项对等的能力/模块"},
    "architecture": {"label":  "分层架构", "visual": ('evidence_image', 'diagram'), "types": ("content-image",),
                     "when": "层与层的关系；结构图（excalidraw / draw.io）"},
    "flow": {"label":  "流程 / 拓扑图", "visual": ('evidence_image', 'diagram'), "types": ("content-image",),
             "when": "节点与连线；结构图"},
    "topology": {"label":  "拓扑 / 关系", "visual": ('evidence_image', 'diagram'), "types": ("content-image",),
                 "when": "多节点的连接关系；结构图"},
    "hero_visual": {"label":  "大图主角", "visual": ('evidence_image', 'diagram'), "types": ("content-image",),
                    "when": "一张图承担这一页的主要信息"},
    "context_image": {"label":  "配图 / 场景", "visual": ('evidence_image', 'diagram'), "types": ("content-image",),
                      "when": "图说明背景，文字仍是主角"},
    "risks": {"label":  "风险 / 预判", "visual": ('none',), "types": ("content-text", "two-column"),
              "when": "可能出问题的地方"},
    "actions": {"label":  "行动 / 下一步", "visual": ('none',), "types": ("content-text", "two-column"),
                "when": "读完要干什么"},
    "result": {"label":  "结论 / 数字海报", "visual": ('none', 'data'), "types": ("content-text", "chart"),
               "when": "把结论收成一句或几个数"},
    "observation": {"label":  "观点 / 展望", "visual": ('none',), "types": ("content-text", "two-column"),
                    "when": "判断与看法"},
    "team": {"label":  "团队 / 关于", "visual": ('evidence_image', 'diagram', 'none'), "types": ("content-image", "content-text"),
             "when": "谁在做"},
    "closing": {"label":  "收尾", "visual": ('none',), "types": ("end",),
                "when": "最后一页"},
}


def known(role) -> bool:
    return isinstance(role, str) and role in ROLES


def label(role: str) -> str:
    return ROLES.get(role, {}).get("label", role)


def types_for(role: str) -> tuple:
    return tuple(ROLES.get(role, {}).get("types") or ())


def roles_for(page_type: str) -> list:
    """这个页型可以承载哪些角色（写内容时不知道选哪个角色，看这份表）。"""
    return [r for r, spec in ROLES.items() if page_type in spec["types"]]


def mismatch_reason(page_type, role) -> str | None:
    """角色与页型不合 → 一句可操作的理由；合 / 不认识 → None。"""
    if not known(role) or not isinstance(page_type, str):
        return None
    allowed = types_for(role)
    if page_type in allowed:
        return None
    return (f"role={role}（{label(role)}）通常写成 {' / '.join(allowed)}，"
            f"这一页是 {page_type} —— 要么换页型，要么确认这是有意的例外")


def markdown_table() -> str:
    """planning.md 的那张角色表**由这里生成**（文档不再是第二份事实）。

    表里有四列：角色 / 页型（结构）/ 主视觉档 / 什么时候用它。三列来自本模块，
    所以它是生成物 —— `tests/deck-authoring/test_doc_contract.py` 逐字比对，
    改了角色就必然改到文档那一段（或测试当场红）。
    """
    lines = ["| 角色（spec 的 `role`） | 页型（结构） | 主视觉档 | 什么时候用它 |",
             "| --- | --- | --- | --- |"]
    for role, spec in ROLES.items():
        types = " / ".join(spec["types"])
        tiers = " / ".join(f"`{t}`" for t in spec.get("visual", ()))
        lines.append(f"| `{role}` | {types} | {tiers} | {spec['when']} |")
    return "\n".join(lines)


def vocabulary_table() -> list:
    """`[{role, label, types, when}]` —— 文档与 CLI 共用一份（不另拄一份表）。"""
    return [{"role": r, "label": s["label"], "types": list(s["types"]),
             "when": s["when"]} for r, s in ROLES.items()]


__all__ = ["ROLES", "known", "label", "types_for", "roles_for",
           "mismatch_reason", "vocabulary_table", "markdown_table"]
