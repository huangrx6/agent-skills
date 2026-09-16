"""Repair Loop：实测硬问题 → 修复梯 → 补丁（只动 spec 可表达的字段）。

**主权规则（不可违反）**：

- 只修改 spec **能表达**的字段（`bulletTier` / `titleTier` / `layout`）——
  每一步都落在补丁清单里，产出 `*.repaired.spec.json` 可复现、可采纳、可拒绝。
  不改 CSS、不改风格、不写运行期魔法变量（那种修复无法复现）。
- **作者声明过的字段一律不碰**：slide 里显式写了 `bulletTier` / `titleTier` /
  `layout`，修复只把它记进诊断（"声明过，不自动改"），决定权在作者。
- **缩字号是最后手段**：竖向溢出的梯子只有"条目档降一档"，且降到最小档
  就停 —— 再装不下是内容问题（拆页 / 收短文案），不是字号问题。

流程（render --repair 内部）：

```text
渲 → 实测 → signals() → plan() → apply() → 再渲 ……（≤4 轮）
                        └→ 梯子走完仍有问题 → diagnostics（可解释：差多少、建议什么）
```
"""
from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _up(name: str):
    """加载上一级目录的模块（scripts/ 不是包，同 _load_sibling 机制）。"""
    path = os.path.join(os.path.dirname(HERE), f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_deck_layout_up_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


grid = _up("grid")

# 不参与溢出判定的角色：页脚行钉在底部（bottom:52），封面/封底天然稀疏
CHROME = frozenset({"foot", "brandfoot", "logo"})
SPARSE_PAGES = frozenset({"title", "end"})

# 条目档的降序链（降一档 = 换到右边那一个；到头 = 梯子走完）
TIER_DOWN = {"bulletLarge": "bullet", "bullet": "bulletSmall"}
TITLE_DOWN = {"cover": "compact", "compact": "small"}


def signals(measured: dict) -> list:
    """实测 → 每页硬问题。两种：

    - ``v_overflow``：内容底超过正文带底（grid.CONTENT_BOTTOM，含 2px 容差）
    - ``h_overflow``：标题横向溢出（nowrap 皮肤下长标题写出列）
    """
    rects = measured.get("slides") or []
    out = []
    for el in measured.get("elements", []):
        role, slide_no = el.get("role"), el.get("slide")
        x, y, w, h = el.get("x"), el.get("y"), el.get("w"), el.get("h")
        if (role in CHROME or not isinstance(slide_no, int)
                or not all(isinstance(v, (int, float)) for v in (x, y, w, h))):
            continue
        if 1 <= slide_no <= len(rects):
            top = rects[slide_no - 1].get("y", 0)
            over = (y + h - top) - grid.CONTENT_BOTTOM
            if over > 2:
                out.append({"slide": slide_no, "kind": "v_overflow",
                            "el": str(el.get("id", "")), "over": round(over, 1)})
        scroll_w, client_w = el.get("scrollW"), el.get("clientW")
        if (role == "title" and isinstance(slide_no, int)
                and isinstance(scroll_w, (int, float))
                and isinstance(client_w, (int, float))
                and scroll_w > client_w + 2):
            out.append({"slide": slide_no, "kind": "h_overflow",
                        "el": str(el.get("id", "")), "over": round(scroll_w - client_w, 1)})
    return out


def _effective(resolved: dict, slide_no: int) -> dict:
    """该页当前生效的档位（compile 算好的 tTier/bTier）。"""
    slides = resolved.get("slides") or []
    if 1 <= slide_no <= len(slides):
        return slides[slide_no - 1]
    return {}


def plan(spec: dict, resolved: dict, issues: list) -> tuple:
    """问题 →（补丁清单, 诊断清单）。只动 spec 可表达且**未被作者声明**的字段。"""
    slides = spec.get("deck", {}).get("slides", [])
    actions, diagnostics = [], []
    by_slide: dict[int, list] = {}
    for it in issues:
        by_slide.setdefault(it["slide"], []).append(it)
    for slide_no, items in sorted(by_slide.items()):
        if not (1 <= slide_no <= len(slides)):
            continue
        slide = slides[slide_no - 1]
        eff = _effective(resolved, slide_no)
        kinds = {it["kind"] for it in items}
        if "v_overflow" in kinds:
            worst = max(it["over"] for it in items if it["kind"] == "v_overflow")
            cur = eff.get("bTier") or "bullet"
            if slide.get("type") in SPARSE_PAGES:
                continue        # 封面/封底不判溢出（signals 已滤 chrome，双保险）
            if "bulletTier" in slide:
                diagnostics.append({
                    "slide": slide_no, "issue": "v_overflow", "over": worst,
                    "why": f"作者已声明 bulletTier={slide['bulletTier']!r}，不自动改",
                    "suggest": "拆页 / 收短文案 / 换更饱满版式"})
                continue
            nxt = TIER_DOWN.get(cur)
            if nxt is None:
                diagnostics.append({
                    "slide": slide_no, "issue": "v_overflow", "over": worst,
                    "why": f"条目档已到最小（{cur}）—— 再装不下是内容问题",
                    "suggest": "拆页 / 收短文案（缩字号不是答案）"})
            else:
                actions.append({"slide": slide_no, "field": "bulletTier",
                                "from": cur, "to": nxt,
                                "why": f"内容底超出正文带 {worst:.0f}px"})
        if "h_overflow" in kinds:
            worst = max(it["over"] for it in items if it["kind"] == "h_overflow")
            cur = eff.get("tTier") or "compact"
            if "titleTier" in slide:
                diagnostics.append({
                    "slide": slide_no, "issue": "h_overflow", "over": worst,
                    "why": f"作者已声明 titleTier={slide['titleTier']!r}，不自动改",
                    "suggest": "收短标题 / 去掉皮肤的 nowrap"})
                continue
            nxt = TITLE_DOWN.get(cur)
            if nxt is None:
                diagnostics.append({
                    "slide": slide_no, "issue": "h_overflow", "over": worst,
                    "why": f"标题档已到最小（{cur}）仍写出列",
                    "suggest": "收短标题 / 去掉皮肤的 nowrap（换行由标题块内高兜）"})
            else:
                actions.append({"slide": slide_no, "field": "titleTier",
                                "from": cur, "to": nxt,
                                "why": f"标题写出列 {worst:.0f}px"})
    return actions, diagnostics


def apply(spec: dict, actions: list) -> None:
    """把补丁写回 spec（就地）。"""
    slides = spec["deck"]["slides"]
    for act in actions:
        slides[act["slide"] - 1][act["field"]] = act["to"]


__all__ = ["signals", "plan", "apply", "TIER_DOWN", "TITLE_DOWN"]
