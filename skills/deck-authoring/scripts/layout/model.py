"""几何模型：矩形、内缩、安全盒扩张、相交判定。

纯函数、零依赖（只用标准库）—— render / check / 测试三方共用同一份数学。
所有数值单位是 px，坐标是产物坐标系（多页竖向堆叠，y 随页递增）。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


@dataclass(frozen=True)
class Insets:
    """四向外扩量（安全盒 = 实际边界向外扩这么多的「视觉安全范围」）。"""

    top: float = 0
    right: float = 0
    bottom: float = 0
    left: float = 0


def expand_rect(rect: Rect, inset: Insets) -> Rect:
    """实际边界 + 外扩量 = 安全盒。

    例：正文盒 (84, 280, 600, 300)，外扩 top16/right32/bottom24/left0
    → 安全盒 (84, 264, 632, 340)。
    """
    return Rect(
        x=rect.x - inset.left,
        y=rect.y - inset.top,
        width=rect.width + inset.left + inset.right,
        height=rect.height + inset.top + inset.bottom,
    )


def intersects(a: Rect, b: Rect) -> bool:
    """两盒是否相交（共享面积 > 0 才算；边贴边不算）。"""
    return not (
        a.right <= b.x
        or b.right <= a.x
        or a.bottom <= b.y
        or b.bottom <= a.y
    )


def gap_between(a: Rect, b: Rect) -> float:
    """两盒的净距：相交返回 0；否则取两个方向上较大的隔离距离。

    诊断用 —— 碰撞报告要写「需要 32，实际 18」，而不是只说「撞了」。
    """
    dx = max(b.x - a.right, a.x - b.right)
    dy = max(b.y - a.bottom, a.y - b.bottom)
    return max(0.0, max(dx, dy))


@dataclass(frozen=True)
class Box:
    """一个参与碰撞检测的元素：实际边界 + 安全盒外扩量 + 政策。"""

    id: str
    role: str
    slide: int
    rect: Rect
    clearance: Insets = field(default_factory=Insets)
    policy: str = "deny"          # deny | decorative | intentional

    @property
    def safe(self) -> Rect:
        return expand_rect(self.rect, self.clearance)


def _vertical_pair(a: Box, b: Box) -> bool:
    """两盒主要是上下关系还是左右关系（决定取哪对 clearance 之和）。"""
    dx = max(b.rect.x - a.rect.right, a.rect.x - b.rect.right)
    dy = max(b.rect.y - a.rect.bottom, a.rect.y - b.rect.bottom)
    return dy >= dx


def required_gap(a: Box, b: Box) -> float:
    """这一对的最小需要间距：取主导方向上两侧外扩量之和。"""
    if _vertical_pair(a, b):
        if b.rect.y >= a.rect.bottom:        # b 在 a 下方
            return a.clearance.bottom + b.clearance.top
        return b.clearance.bottom + a.clearance.top
    if b.rect.x >= a.rect.right:             # b 在 a 右侧
        return a.clearance.right + b.clearance.left
    return b.clearance.right + a.clearance.left


def boxes_touch(a: Box, b: Box) -> tuple[bool, float, float]:
    """两个盒子是否构成一次「安全盒碰撞」。

    返回 (是否违规, 需要间距, 实际间距)。只算数、不看政策 ——
    deny×deny 才算违规，豁免（decorative / intentional）由调用方定。
    """
    hit = intersects(a.safe, b.safe)
    return hit, required_gap(a, b), gap_between(a.rect, b.rect)


__all__ = ["Rect", "Insets", "Box", "expand_rect", "intersects",
           "gap_between", "required_gap", "boxes_touch", "replace"]
