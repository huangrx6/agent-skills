#!/usr/bin/env python3
"""文字测量与容器尺寸推导 —— 纯函数，不依赖布局。

## 这个模块存在的理由（前作真正的病灶）

前作 `draw-excalidraw` 的**结构**是对的：

    width = max(每行 units) × fontSize     （CJK 与拉丁分开计）

它依然出现文字溢出，**主因不是精度，是耦合**：`wrapText(maxUnits = 22)` 里的 22 是
写死的，与容器尺寸档位完全无关 —— 22 单位 × 16px = 352px，而容器可能只有 140px 宽。

（“不是精度问题”这句后来被自己的实测**部分推翻**了 —— 见下方“数值来源”。）

**所以本模块把耦合方向反过来：先定断行宽度，容器宽度由它反推。**

    档位 → 断行宽度（单位）→ 容器宽度 = 断行宽度 × 字号 + 2 × 内边距
    实际断行 = wrap(文字, 同一个断行宽度)
    容器高度 = 实际行数 × 字号 × 行高 + 2 × 内边距

这样文字**在构造上**不可能溢出容器：它和容器用的是同一个宽度。于是
`validation.md` 里的"文字溢出"检查不再是"发现溢出"，而是**一致性断言** ——
一旦它报，说明推导和落笔之间有不一致，是脚本 bug，不是内容问题。

> 通用原则：**让错误在结构上不可能发生，比让错误发生了再去检测更可靠。**

## 数值来源：这一处后来被自己的实测推翻了

CJK 的 **1.00 保持不变** —— 用真实字体量过，全角字符的前进宽度精确等于 1.0 em（偏差 0.0%）。

拉丁的 **0.56 不对**，已换成按字符查 `_ADVANCE` 表（Helvetica 实测前进宽度，向上取整）。
0.56 是个“平均字符宽度”式的单值启发式，实测对**最需要准的标签**偏得最厉害：

    MQ -30.5%   CPU/DNS -20.4%   DB -19.4%   SQL -16.0%   HTTPS -14.6%

而这些恰恰是架构图里最常见的缩写。**偏窄的代价是容器比真实文字小** ——
Excalidraw 会自己换行、把容器撑高，整个布局随之偏移。

原则仍然成立，但要说得更细：别人失败经验里的**具体数值**值得复用，
**但要拿实测复核，而不是因为“前作是好的”就照抄** ——
“它没被推翻”当时只是没人去量，不等于它经得起量。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── 字符权重 ────────────────────────────────────────────────
# 0x2E80 起：CJK 部首、假名（0x3040-）、谚文（0xAC00-）、全角形式（0xFF01-）都在其后
WIDE_FROM_CODEPOINT = 0x2E80
# 【已实测】全角字符的前进宽度精确等于 1.0 em。
# 实测方式：拿真实 Excalidraw 渲染 10 个全角字，量得 160px @16px = 10.0 em，偏差 0.0%。
WIDE_WEIGHT = 1.00


def _advance_table(rows: tuple[tuple[str, float], ...]) -> dict[str, float]:
    out: dict[str, float] = {}
    for chars, width in rows:
        for ch in chars:
            out[ch] = width
    return out


# 【已实测】可打印 ASCII 的真实前进宽度（em）：Helvetica 逐个字符量出后**向上取整到 0.05**。
# 数值被 tests/test_text_metrics.py 锁住 —— 改这张表必须是刻意的。
#
# 为什么不用“拉丁一律 0.56”这种单值启发式：实测下来它对**最需要准的标签**偏得最厉害 ——
#     MQ -30.5%   CPU/DNS -20.4%   DB -19.4%   SQL -16.0%   HTTPS -14.6%
# 而这些恰恰是架构图里最常见的缩写。偏窄的代价是容器比真实文字小，
# Excalidraw 只能自己换行、把容器撑高，整个布局随之偏移。
_ADVANCE = _advance_table((
    ("'", 0.20),
    ("ijl", 0.25),
    ("ftI!,./:;[\\]| ", 0.30),
    ("r()-`{}", 0.35),
    ('"*', 0.40),
    ("cksvxyzJ^", 0.50),
    ("0123456789abdeghnopquL#$+<=>?_~", 0.60),
    ("FTZ", 0.65),
    ("ABEKPSVXY&", 0.70),
    ("wCDHNRU", 0.75),
    ("GOQ", 0.80),
    ("mM", 0.85),
    ("%", 0.90),
    ("W", 0.95),
    ("@", 1.05),
))

# ── 字号：固定 3 档，不给区间 ───────────────────────────────
# 前作给的是区间（28-32 / 18-20 / 16-18 / 12-14）—— 区间就是"让模型自己判断"，
# 而它不该判断这个。
FONT_TITLE = 24.0
FONT_NODE = 16.0
FONT_DETAIL = 12.0

# 行框系数。2026-09-16 由 1.25 提到 1.4：
# 实测反馈是“文字总和框覆盖重叠，而不是在框内部”（用户原话），逐节点量出来的
# 数据是单行节点上下余量只剩 12px、圆柱只剩 9.9px —— 再叠上 Excalidraw 真实字体
# 的墨迹溢出（CJK 字形占满 em，行框外的上伸/下延还有 ~0.1-0.2em）和手绘描边
# ±2-3px 的抖动，视觉余量归零。这个值会写进元素的 lineHeight，Excalidraw 按它
# 排版文字块，而容器尺寸用同一个数反推 —— 两边同源，加大它就是整体加大呼吸，
# 行间空气也从 0.25em 涨到 0.4em（标题与 detail 的分隔感同步变好）。
LINE_HEIGHT = 1.4

# ── 容器内边距 ──────────────────────────────────────────────
# 2026-09-16 两连跳：12 → 16 → 24。第一轮按“不贴边”修（16），用户拿着真实渲染
# 的要点卡片反馈“还是挤得满满的，小家子气，不够大气，框就不能大一些吗”——
# 那就一次到位：对齐同类工具的盒大字小比例（单行节点 44px → 70px 高）。
# 水平方向实测最少余量 44px 本来就不挤，PADDING_X 只跟一小步（16 → 22）
# 保持盒字比例协调。垂直余量 = PADDING_Y，它是手绘抖动与字体溢出的唯一吸收层。
PADDING_X = 22.0
PADDING_Y = 24.0

# ── 断行宽度档位（加权单位）────────────────────────────────
# 注意这里定义的是**断行宽度**，不是容器宽度；容器宽度由它算出来。
# 【待验证】这三个档位是按前作档位与常识设的起点，不是实测出来的。
# 它们等的是 validation.md 里那张校准表（用够 5 张图做一次复盘）。
# 信任状态总表见 references/diagram-spec.md（“数值的信任状态”一节）。
SIZE_CLASSES: tuple[tuple[str, float], ...] = (
    ("S", 10.0),
    ("M", 16.0),
    ("L", 24.0),
)
LARGEST_CLASS = SIZE_CLASSES[-1]


def is_wide(ch: str) -> bool:
    """是否按全角（1.0 em）计宽。"""
    return ord(ch) >= WIDE_FROM_CODEPOINT


def char_weight(ch: str) -> float:
    """单个字符占多少 em。

    - 全角（CJK、全角标点）：恰好 1.00。实测全角字体的前进宽度就是 1.0 em，偏差 0.0%。
    - 可打印 ASCII：查 `_ADVANCE`（Helvetica 实测，向上取整）。
    - 其它（带重音字母、西里尔、emoji……）：按 1.00 估。表里没有的字符一律按最宽的算，
      理由同上：估宽只是多留白，估窄会把布局推偏。
    """
    if is_wide(ch):
        return WIDE_WEIGHT
    return _ADVANCE.get(ch, WIDE_WEIGHT)


def weighted_units(text: str) -> float:
    """一串文字的加权宽度（单位数，与字号无关）。"""
    return sum(char_weight(c) for c in text)


def size_class_for(units: float) -> tuple[str, float]:
    """按加权长度选档位，返回 (档位名, 该档的断行宽度)。

    超过最大档时落到最大档 —— 是否"太长了"由调用方判断（那是内容问题，要报告），
    这里只负责给出能用的宽度。
    """
    for name, cap in SIZE_CLASSES:
        if units <= cap:
            return name, cap
    return LARGEST_CLASS


def _tokens(line: str) -> list[str]:
    """切成断点之间的小块：全角每字一块，拉丁按空白切词（词内不断）。

    拉丁词与全角字符都保留**前导空格**，这样重新拼接时不必特殊处理；
    行首的空格由 `wrap` 去掉。

    全角那一支曾漏掉这个空格：“Web 前端” 里的空格会在词与中文的交界处被吃掉，
    于是出图上的文字和规格里的 label 不一致 —— 而“脚本忠实地把结构画出来”
    正是这个 skill 的前提，静默吞字符不算“忠实”。
    """
    toks: list[str] = []
    buf: list[str] = []
    pending_space = False
    for ch in line:
        if is_wide(ch):
            if buf:
                toks.append("".join(buf))
                buf = []
            toks.append((" " if pending_space else "") + ch)
            pending_space = False
        elif ch.isspace():
            if buf:
                toks.append("".join(buf))
                buf = []
            pending_space = True
        else:
            if pending_space:
                buf.append(" ")
                pending_space = False
            buf.append(ch)
    if buf:
        toks.append("".join(buf))
    return _glue_kinsoku(toks)


# 中文排印的**避头尾**（禁则）：下面两类字符不能出现在行首 / 行尾。
# 不处理的话图里会出现以"；"或"，"开头的行（实测出过），看起来像排错了。
# 做法是与邻字**黏成一块**（不可拆的 token）：断行时拆不开它们，宽度也不变。
_NO_LINE_START = "、。，．；：？！）］｝〉》」』】〕…—～·!?,.;:)]}"
_NO_LINE_END = "（［｛〈《「『【〔([{"


def _glue_kinsoku(toks: list[str]) -> list[str]:
    """把避头尾字符与邻字黏成一块（纯文本拼接，不动字符本身）。"""
    out: list[str] = []
    index = 0
    while index < len(toks):
        tok = toks[index]
        bare = tok.strip()
        if out and bare and all(c in _NO_LINE_START for c in bare):
            out[-1] += tok                   # 行首禁则：黏到前一块尾巴上
            index += 1
            continue
        if (bare and all(c in _NO_LINE_END for c in bare)
                and index + 1 < len(toks)):
            out.append(tok + toks[index + 1])  # 行尾禁则：与后一块一起下移
            index += 2
            continue
        out.append(tok)
        index += 1
    return out


def _force_break(token: str, max_units: float) -> list[str]:
    """单个词放不下时强制切开（URL、长标识符）——切完记录，让报告能提这件事。"""
    pieces: list[str] = []
    cur = ""
    for ch in token.lstrip(" "):
        if cur and weighted_units(cur) + char_weight(ch) > max_units:
            pieces.append(cur)
            cur = ""
        cur += ch
    if cur:
        pieces.append(cur)
    return pieces or [token]


def wrap_balanced(text: str, max_units: float) -> tuple[list[str], list[str]]:
    """同行数前提下挑**最均衡**的一版断行。

    贪心断行会把末行剩一两个字（实测卡片条目把"降级"切成孤字"级"），
    而把断行宽度收窄一档就能断在词的空隙上。行数**必须不变** —— 行数一变，
    容器高度就变，尺寸链两头就对不上了。这与 `layout.region_label_lines`
    里那段均衡搜索是同一件事；那边因为还要返回像素宽度单独实现，
    这边是条目/说明类的通用入口。
    """
    lines, forced = wrap(text, max_units)
    if len(lines) <= 1:
        return lines, forced
    count = len(lines)
    widest = max(weighted_units(line) for line in lines)
    for factor in (0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55, 0.5):
        candidate, candidate_forced = wrap(text, max_units * factor)
        if len(candidate) != count:
            continue
        candidate_widest = max(weighted_units(line) for line in candidate)
        if candidate_widest < widest - 1e-6:
            lines, widest = candidate, candidate_widest
            forced = candidate_forced
    return lines, forced


def wrap(text: str, max_units: float) -> tuple[list[str], list[str]]:
    """按加权单位断行。返回 (行列表, 被强制切开的词列表)。

    显式换行符优先（用户写了 `\\n` 就按它断）。
    """
    lines: list[str] = []
    forced: list[str] = []

    for raw_line in text.split("\n"):
        if not raw_line.strip():
            lines.append("")
            continue
        cur = ""
        cur_units = 0.0
        for tok in _tokens(raw_line):
            tok_units = weighted_units(tok)
            if not cur and tok_units > max_units:
                pieces = _force_break(tok, max_units)
                forced.append(tok.lstrip(" "))
                lines.extend(pieces[:-1])
                cur = pieces[-1]
                cur_units = weighted_units(cur)
                continue
            candidate = cur + tok if cur else tok.lstrip(" ")
            if cur and weighted_units(candidate) > max_units:
                lines.append(cur)
                cur = tok.lstrip(" ")
            else:
                cur = candidate
            cur_units = weighted_units(cur)
        if cur:
            lines.append(cur)
    return lines or [""], forced


@dataclass(frozen=True)
class TextBox:
    """由文字反推出来的容器尺寸。**宽度来自断行宽度，不是反过来。**"""

    size_class: str
    break_units: float            # 该档的断行宽度（单位）
    lines: tuple[str, ...]        # 标题实际断行结果
    detail_lines: tuple[str, ...]  # 次要说明实际断行结果
    width: float
    height: float
    # 这份文字实际用的字号。**由 measure 决定，调用方只读不猜** ——
    # emit 写元素时若自己再算一遍（比如写死 FONT_NODE），重点节点的字就还是小的。
    font_size: float = FONT_NODE
    forced_breaks: tuple[str, ...] = field(default_factory=tuple)

    @property
    def overflowed(self) -> bool:
        """一致性断言：任何一行都不该超过断行宽度。

        按本模块的构造方式这里永远为 False。它为 True 只可能意味着
        `measure` 被改坏了 —— 所以调用方应把它当**脚本 bug**上报，而不是内容问题。
        """
        return any(weighted_units(l) > self.break_units + 1e-6 for l in self.lines)


def measure(label: str, detail: str = "", *, font_size: float = FONT_NODE) -> TextBox:
    """由文字推容器尺寸。

    **档位由标题与说明一起决定**（两者都折算成节点字号的等效长度，取最大值）。
    旧规矩是只看标题（"说明是次要行，不反过来撑大容器"），实测的后果就是用户截图里的
    样子：一个长说明的节点，框停在 S 档的 204px，说明挤成 ~110px 的窄列一直断行，
    长标识符还被拦腰截断。用户原话："如果一个框中文本较多，直接将框设置的稍微宽一些，
    不要一直换行换行的，很难受"。

    **说明的断行宽度按字号比折算**，所以它与标题用**同一条像素宽度** —— 不折算的话
    同一串单位数在 12px 下只画出 16px 的 75%，说明会永久比标题窄一截。

    两个桶都用**均衡**断行（同行数下挑最均匀的那版）：行数一样，但避免末行只剩一两个字。
    """
    label_units = weighted_units(label)
    # 折算到标题字号才能比较"谁更长"：说明是 12px，同样的字符数占的位置更小
    detail_units_as_node = (weighted_units(detail) * FONT_DETAIL / font_size
                            if detail else 0.0)
    class_name, break_units = size_class_for(max(label_units, detail_units_as_node))
    # 用**均衡**断行（不是贪心）：行数一样，但末行不会只剩一两个字。
    # 贪心断行的末行实测出现过单个字符（"…三项都匹配才接" / "受"），
    # 用户截图里那个孤零零的 `.` 也是同一回事。
    lines, forced_label = wrap_balanced(label, break_units)
    # 同一条像素宽度 = break_units × font_size；说明字号小，能放的单位数按比例多
    detail_units = break_units * font_size / FONT_DETAIL
    detail_lines, forced_detail = (wrap_balanced(detail, detail_units)
                                  if detail else ([], []))

    width = break_units * font_size + 2 * PADDING_X
    line_total = len(lines) + (len(detail_lines) if detail_lines else 0)
    height = line_total * font_size * LINE_HEIGHT + 2 * PADDING_Y

    return TextBox(
        size_class=class_name,
        break_units=break_units,
        font_size=font_size,
        lines=tuple(lines),
        detail_lines=tuple(detail_lines),
        width=width,
        height=height,
        forced_breaks=tuple(forced_label + forced_detail),
    )


def too_long_for_largest(label: str) -> bool:
    """标题超过最大档 → 内容问题，该报告建议拆节点或缩短标签。"""
    return weighted_units(label) > LARGEST_CLASS[1]


if __name__ == "__main__":
    import sys

    for s in sys.argv[1:] or ["鉴权服务", "Auth Service", "一个特别长的节点标题用来测试断行行为"]:
        box = measure(s, "detail line")
        print(f"{s!r}")
        print(f"  档位 {box.size_class}  断行宽度 {box.break_units} 单位")
        print(f"  容器 {box.width:.0f} × {box.height:.0f}")
        print(f"  行: {box.lines}   说明: {box.detail_lines}")
        print(f"  溢出(断言, 应恒为 False): {box.overflowed}")
