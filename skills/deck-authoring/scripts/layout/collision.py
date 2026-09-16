"""安全盒碰撞：政策（谁能贴谁）+ 安全距离表 + 验收。

三条政策（默认 deny）：

- ``deny``        信息元素之间默认禁止安全盒相交 —— 没声明就是禁止，
                  不让 QA 猜「这是 bug 还是设计」。
- ``decorative``  装饰（纸纹 / 色块 / 网点）。测量层根本不把它们收进
                  ``elements``（无 ``data-m``），天然不参与本门。
- ``intentional`` 真正的满版设计。目前只有一种：hero 版式的标题条压图
                  （实心反色条，对比度走 token 保证）。

分组豁免（同一组的成员是一个视觉整体，不互相判撞）：

- title   = 标题块（title + subtitle）
- body    = 正文（bullets / 栏题）
- visual  = 视觉（chart / image / 时间线节点）
- caption = 说明（caption / chartValue / chartLabel —— 图表页的 caption
  登记角色是 ``bullet``，所以分组看 **id 段**（``s3.caption``），不看 role）
- foot    = 页脚行（foot / brandfoot / logo）

安全距离（px，四向外扩；需要间距 = 主导方向两侧外扩量之和）：

===== ======== ====
title bottom    28
subtitle bottom 20
body  top/bottom 20/16
chart 四向      24
image 上16其余24
caption 四向    12
foot  top      24
logo  四向      16
===== ======== ====
"""
from __future__ import annotations

import importlib.util
import os
import sys


def _sibling(name: str):
    """加载同目录模块 —— 同 ``check.py::_load_sibling`` 的机制：scripts/ 不是包。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_deck_layout_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 layout/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


model = _sibling("model")
Box, Insets, Rect = model.Box, model.Insets, model.Rect
boxes_touch = model.boxes_touch


def group_of(el: dict) -> str:
    """id 段 → 视觉组（role 兜底）。图表页 caption 的 role 是 bullet，必须看 id。"""
    eid = str(el.get("id", ""))
    seg = eid.split(".", 1)[1] if "." in eid else ""
    head = seg.split(".")[0]
    if head in ("title", "subtitle"):
        return "title"
    if head == "caption":
        return "caption"
    if head.startswith("bullet"):
        return "body"
    role = str(el.get("role", ""))
    if role in ("chart", "image", "nodeLabel", "nodeNote"):
        return "visual"
    if role in ("chartValue", "chartLabel"):
        return "caption"
    if role in ("foot", "brandfoot", "logo"):
        return "foot"
    if role == "colTitle":
        return "body"
    return "body"


CLEARANCE = {
    "title":    Insets(bottom=28),
    "subtitle": Insets(bottom=20),
    "bullet":   Insets(top=20, bottom=16),
    "colTitle": Insets(top=20, bottom=12),
    "chart":    Insets(top=24, right=24, bottom=24, left=24),
    "image":    Insets(top=16, right=24, bottom=24, left=24),
    "nodeLabel": Insets(top=16),
    "nodeNote": Insets(top=12),
    "caption":  Insets(top=12, right=12, bottom=12, left=12),
    "chartValue": Insets(top=12),
    "chartLabel": Insets(top=12),
    "foot":     Insets(top=24),
    "brandfoot": Insets(top=16),
    "logo":     Insets(top=16, right=16, bottom=16, left=16),
}

# hero 版式：标题条压图是设计本身（实心反色条，对比度由 token 保证）
INTENTIONAL_PAIRS = {frozenset({"title", "visual"})}


def build_boxes(elements: list):
    """实测元素 → 碰撞盒。几何四值缺一 / 非数字的元素不参与（check 从不抛）。"""
    out = []
    for el in elements:
        x, y, w, h = el.get("x"), el.get("y"), el.get("w"), el.get("h")
        slide = el.get("slide")
        if not all(isinstance(v, (int, float)) for v in (x, y, w, h, slide)):
            continue
        role = str(el.get("role", ""))
        eid = str(el.get("id", ""))
        head = eid.split(".", 1)[1].split(".")[0] if "." in eid else ""
        # 图表页的 caption 登记角色是 bullet；安全距离按真实身份（caption）取
        key = "caption" if head == "caption" else role
        out.append(Box(
            id=eid,
            role=role,
            slide=slide,
            rect=Rect(x, y, w, h),
            clearance=CLEARANCE.get(key, Insets()),
        ))
    return out


def _contains(outer, inner) -> bool:
    """outer 是否完全包含 inner（几何包含）。"""
    r, s = outer.rect, inner.rect
    return (r.x <= s.x and r.y <= s.y
            and r.right >= s.right and r.bottom >= s.bottom)


def _figure_internal(a, b) -> bool:
    """figure 内部成员（caption 组被 visual 组包含）豁免。

    只认这一种包含：caption / 图表数值标签是 figure 的组成部分（DOM 上就是
    它的子节点）。**全幅图"包含"标题不算** —— 那是压字，没声明 hero 就是
    违规，不能让包含豁免把真重叠吞了。
    """
    pair = ((a, b), (b, a))
    for outer, inner in pair:
        if (group_of({"id": inner.id, "role": inner.role}) == "caption"
                and group_of({"id": outer.id, "role": outer.role}) == "visual"
                and _contains(outer, inner)):
            return True
    return False


def violations(boxes: list, hero_slides: frozenset) -> list:
    """安全盒碰撞清单。只报 deny×deny：不同组、同页、安全盒相交。

    ``hero_slides``：hero 版式的页码 —— 那些页的 title×visual 是 intentional。

    豁免三件（都是「一个视觉整体」，不是兄弟）：
    - 同组（title 块内 / 列表条目间 / 页脚行内）
    - caption 被 visual 包含（figure 的 DOM 子节点；**全幅图包含标题不在此列**
      —— 那是压字，必须走 hero 声明）
    - 同页 visual×caption —— caption 属于 figure 本身（图内间距由 figure
      的 padding 管：实测画布→说明 48px，是舒服的）
    """
    out: list[dict] = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a.slide != b.slide:
                continue
            ga = group_of({"id": a.id, "role": a.role})
            gb = group_of({"id": b.id, "role": b.role})
            if ga == gb:
                continue
            if _figure_internal(a, b):
                continue
            if {ga, gb} == {"visual", "caption"}:
                continue
            if a.slide in hero_slides and frozenset((ga, gb)) in INTENTIONAL_PAIRS:
                continue
            hit, need, actual = boxes_touch(a, b)
            if hit:
                out.append({
                    "slide": a.slide, "a": a.id, "b": b.id,
                    "group": f"{ga}×{gb}",
                    "required": round(need, 1), "actual": round(actual, 1),
                })
    return out


__all__ = ["CLEARANCE", "INTENTIONAL_PAIRS", "group_of", "build_boxes",
           "violations"]
