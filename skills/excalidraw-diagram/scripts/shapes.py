#!/usr/bin/env python3
"""节点形状 —— 形状与语义的映射，以及**形状对可用面积的影响**。

## 为什么形状要与 kind 分开（而不是塞进同一个枚举）

`kind` 是**语义角色**（这是服务、这是数据、这是外部系统），形状是**画法**。
两者正交：流程图里一个「判断」节点在语义上仍属于 `service`，
但形状必须是菱形。

把它们塞进同一个枚举会逼着人做选择：这个判断到底算 kind=diamond 还是 kind=service？
答案是不用选 —— **形状有自己的封闭枚举，默认值由 kind 推出来，需要时可以显式覆盖。**

## ⚠ 形状会改变"能放多少文字"—— 这不是审美，是几何

同一个包围盒里，**菱形能放文字的只有它的内接矩形（面积的一半）**，
椭圆是内接矩形的 √2 倍。不把这个量算进去，文字就会溢出形状 ——
而"文字不溢出"是这个 skill 从第一波就在守的构造性保证。

所以每个形状带一组 `text_fit` 系数：**包围盒 = 文字尺寸 × 系数**。

    rect / round / note   1.0        文字直接填满
    ellipse               √2         内接矩形
    diamond               2.0        内接矩形（半个包围盒）
    capsule               另算       两端是半圆，文字要往里让
    cylinder              另算       顶上多一个椭圆盖

**这仍然是我们自己算出来的尺寸**（不是外部的图标固有宽高），
所以"尺寸只有一个来源"这个前提继续成立 —— 但它从"只有文字测量"
变成了"文字测量 + 形状几何"。`references/validation.md` 第六节要跟着改。
"""

from __future__ import annotations

import math

# ── 形状的封闭枚举 ──────────────────────────────────────────
# 键是规格里能写的取值；改这里要同时改 references/diagram-spec.md。
SHAPES: dict[str, dict] = {
    "rect": {"zh": "矩形", "excalidraw": "rectangle", "roundness": None,
             "text_fit": (1.0, 1.0)},
    "round": {"zh": "圆角矩形", "excalidraw": "rectangle", "roundness": {"type": 3},
              "text_fit": (1.0, 1.0)},
    "capsule": {"zh": "胶囊（消息 / 队列）", "excalidraw": "rectangle",
                "roundness": {"type": 3}, "text_fit": "capsule"},
    "ellipse": {"zh": "椭圆（用户 / 角色）", "excalidraw": "ellipse", "roundness": None,
                "text_fit": (math.sqrt(2), math.sqrt(2))},
    "diamond": {"zh": "菱形（判断）", "excalidraw": "diamond", "roundness": None,
                "text_fit": (2.0, 2.0)},
    "cylinder": {"zh": "圆柱（数据库 / 存储）", "excalidraw": "rectangle",
                 "roundness": {"type": 3}, "text_fit": "cylinder"},
    "note": {"zh": "便签（注释 / 说明）", "excalidraw": "rectangle",
             "roundness": None, "text_fit": (1.0, 1.0), "stroke_style": "dashed"},
}

# kind → 默认形状。显式写了 shape 就以显式为准。
# 依据是"这个语义角色在图上通常长什么样"，不是审美偏好。
DEFAULT_SHAPE_FOR_KIND: dict[str, str] = {
    "client": "ellipse",      # 用户 / 角色 —— 人不是矩形
    "service": "round",       # 服务 / 进程 —— 默认圆角矩形
    "data": "cylinder",       # 数据库 —— 圆柱是通用视觉约定
    "async": "capsule",       # 消息 / 队列 —— 管道感
    "security": "round",      # 鉴权 / 网关 —— 仍是服务，只是语义角色不同
    "external": "note",       # 外部系统 —— 虚线框表示"不受控"
}

# 圆柱顶盖的高度上限：太厚的盖子在小节点上会挤掉文字
CYLINDER_CAP_MAX = 26.0
CYLINDER_CAP_RATIO = 0.24     # 顶盖高度 = 宽度 × 这个比例（受上面的上限约束）
# 胶囊上下各留的呼吸量。按几何算出的侵入量只有 2~3px，这点额外高度是为了
# 文字不贴到弧线上（纯视觉，不影响布局精度）。
CAPSULE_BREATHING = 6.0


def resolve(node: dict) -> str:
    """这个节点该用哪种形状。未知值抛错 —— 与 kind 同一条原则，不 fallback。

    为什么不能 fallback 到 rect：静默换形状会让“形状必须与语义有关”这条
    变成一句空话 —— 写错的人不会知道，看图的人也看不出本该是别的形状。

    报错要**分清是哪一种失败**（实测踩过：kind 写错时报出的是“未知 shape: None”，
    照着那个修只会越修越偏）：

    - 显式 shape 不认识 → 报 shape 的允许值
    - kind 不认识 → 报“这个 kind 没有默认形状”，并指向 kind 的允许值
    """
    declared = node.get("shape")
    kind = str(node.get("kind") or "")
    if declared:
        shape = str(declared)
        if shape not in SHAPES:
            raise KeyError(f"未知 shape {shape!r}；允许的取值：{sorted(SHAPES)}")
        return shape
    default = DEFAULT_SHAPE_FOR_KIND.get(kind)
    if default is None:
        raise KeyError(
            f"kind {kind!r} 没有对应的默认形状 —— 要么 kind 写错了，"
            f"要么在这个 node 上显式写 shape（允许值：{sorted(SHAPES)}）"
        )
    return default


def stroke_style_for(shape_name: str) -> str:
    return SHAPES[shape_name].get("stroke_style", "solid")


def cylinder_cap(width: float) -> float:
    """圆柱顶盖的高度。文字要放在盖子下面，所以它是纯增加的高度。"""
    return min(CYLINDER_CAP_MAX, width * CYLINDER_CAP_RATIO)


def capsule_intrusion(radius: float, text_height: float) -> float:
    """胶囊两端半圆真正侵占文字的宽度。

    第一版这里写的是“宽度 += 高度”（~46px），是按“半圆各占一个半径”拍的。
    按几何算根本不是：圆心在距边 r 处，文字上下各到 |y| = h/2，
    真正侵入的量只有 r − √(r² − (h/2)²)。

    以 r=23、文字高 20 为例：23 − √(529−100) ≈ **2.3px**，而我当初加了 46px。
    多出来的 44px 不是审美问题 —— 盒子变大就会挤掉布局的余地（实测：
    加完形状后网状图开始出现“连线穿过节点”）。
    """
    half = min(text_height, 2 * radius) / 2.0
    return radius - math.sqrt(max(0.0, radius * radius - half * half))


def box_for(shape_name: str, text_width: float, text_height: float
            ) -> tuple[float, float]:
    """给定文字尺寸，算出**形状包围盒**要多大。

    这是“文字在构造上不可能溢出形状”的实现处：请求的盒子一定把文字装得下，
    因为盒子就是从文字反推出来的。
    """
    fit = SHAPES[shape_name]["text_fit"]
    if fit == "capsule":
        # 上下各留一点，让文字不贴到弧线；左右按几何算出的侵入量让开
        height = text_height + CAPSULE_BREATHING
        intrusion = capsule_intrusion(height / 2.0, text_height)
        return text_width + 2 * intrusion, height
    if fit == "cylinder":
        return text_width, text_height + cylinder_cap(text_width)
    scale_x, scale_y = fit
    return text_width * scale_x, text_height * scale_y


def text_area(shape_name: str, width: float, height: float
              ) -> tuple[float, float]:
    """包围盒里**实际能放文字**的那块区域 —— `box_for` 的逆运算。

    `check_layout` 的一致性断言要用它：落笔尺寸与重新量出来的文字比对时，
    必须把形状带来的那圈余量扣掉，否则会误报“文字溢出”。
    """
    fit = SHAPES[shape_name]["text_fit"]
    if fit == "capsule":
        inner_height = height - CAPSULE_BREATHING
        intrusion = capsule_intrusion(height / 2.0, inner_height)
        return width - 2 * intrusion, inner_height
    if fit == "cylinder":
        return width, height - cylinder_cap(width)
    scale_x, scale_y = fit
    return width / scale_x, height / scale_y


if __name__ == "__main__":
    import sys

    for name, entry in SHAPES.items():
        w, h = box_for(name, 100.0, 40.0)
        tw, th = text_area(name, w, h)
        print(f"{name:<9} {entry['zh']:<20} 文字 100×40 → 盒子 {w:6.1f}×{h:5.1f} "
              f"→ 反算 {tw:6.1f}×{th:5.1f}")
    print()
    for kind, shape in DEFAULT_SHAPE_FOR_KIND.items():
        print(f"  {kind:<10} → {shape}")
    if len(sys.argv) > 1:
        print(f"\n  未知形状会抛错：{resolve({'kind': 'service', 'shape': sys.argv[1]})!r}")
