#!/usr/bin/env python3
"""动画层的验证 —— 核心只有一条：**同一个 t 必出同一帧**。

## 为什么这条是核心

它撑着三件事：可回归（不同时间渲的两支能逐帧对齐）、可局部重渲（改一页不用重录整片）、
可复现（别人拿到 spec 能渲出一样的）。这条一破，上面三件全废 —— 而且**不会报错**，
只会让每次导出的视频都略有不同，谁都说不清哪个对。

所以这里钉住三件事：

1. **纯函数性**：同一个 t，两次独立 Chrome 会话取到的帧逐字节一致
2. **渲染路径上没有 CSS transition**：transition 走墙钟，逐帧 seek 下不可复现
   （静态检查，最便宜也最值钱的一条 —— 它是这类 bug 唯一的早期信号）
3. **时间轴本身**：连续、不漏页、同输入同输出

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_animation.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
SCRIPTS = os.path.join(SKILL, "scripts")
DEMO = os.path.join(SKILL, "dev-tools", "demo.spec.json")
STYLES = os.path.join(SKILL, "styles")


def _style_names() -> list[str]:
    """所有风格 —— **读目录，不写死名单**。

    写死名单的代价是实测过的：加了四套新风格之后，那份写死的名单让它们全部逃过了
    运动 / 装饰 / 版式表三条检查 —— 而测试是绿的。目录才是唯一事实来源。
    """
    return sorted(d for d in os.listdir(STYLES) if os.path.isdir(os.path.join(STYLES, d)))


STYLE_NAMES = _style_names()


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = _load("_deck_test_render_anim", os.path.join(SCRIPTS, "render.py"))
animate = _load("_deck_test_animate", os.path.join(SCRIPTS, "animate.py"))


class TestTimeline(unittest.TestCase):
    """时间轴在 Python 里算 —— 所以它的数学是可测的（JS 只负责“给定 t 画成什么样”）。"""

    @classmethod
    def setUpClass(cls) -> None:
        with open(DEMO, encoding="utf-8") as fh:
            cls.spec = json.load(fh)
        cls.style = render.load_style(cls.spec["deck"].get("style", render.DEFAULT_STYLE))
        cls.tokens = cls.style["tokens"]

    def test_timeline_is_deterministic(self) -> None:
        """同一份 spec + 同一个风格，两次算出的时间轴必须一模一样。"""
        a = render.timeline(self.spec["deck"], self.tokens)
        b = render.timeline(copy.deepcopy(self.spec["deck"]), self.tokens)
        self.assertEqual(a, b, "时间轴两次算出来不一样 —— 里面混进了随机性")

    def test_every_slide_gets_a_span_and_they_are_contiguous(self) -> None:
        """每页都要有，且首尾相接 —— 中间留缝就是“空画面”，观众会以为卡了。"""
        spans = render.timeline(self.spec["deck"], self.tokens)
        self.assertEqual(len(spans), len(self.spec["deck"]["slides"]), "有页没拿到时间片")
        for prev, nxt in zip(spans, spans[1:]):
            self.assertAlmostEqual(
                prev["start"] + prev["enter"] + prev["hold"], nxt["start"], places=3,
                msg=f"第 {prev['slide']} 页与第 {nxt['slide']} 页之间有空隙")
        self.assertEqual(spans[0]["start"], 0, "第一页必须从 0 开始")

    def test_reading_time_grows_with_content(self) -> None:
        """条目多的页 hold 要更长 —— “礼让观众”得是可量的，不是口号。"""
        deck = {"slides": [
            {"type": "content-text", "title": "少", "bullets": ["a", "b"]},
            {"type": "content-text", "title": "多", "bullets": ["a", "b", "c", "d", "e", "f"]},
        ]}
        spans = render.timeline(deck, self.tokens)
        self.assertGreater(spans[1]["hold"], spans[0]["hold"],
                           "条目多的页阅读时间没有更长 —— hold 是按常数给的？")

    def test_chart_pages_hold_longer_than_text(self) -> None:
        """§32 阅读时间按复杂度：看懂一组柱比读一句话慢，图表页要多停。"""
        deck = {"slides": [
            {"type": "content-text", "title": "文本页", "bullets": ["a"]},
            {"type": "chart", "title": "图表页", "chart": "bar", "data": [
                {"label": "a", "value": 1}, {"label": "b", "value": 2},
                {"label": "c", "value": 3}, {"label": "d", "value": 4},
                {"label": "e", "value": 5}]},
        ]}
        spans = render.timeline(deck, self.tokens)
        self.assertGreater(spans[1]["hold"], spans[0]["hold"],
                           "图表页没有比同内容重量的文本页多停 —— 复杂度项没生效")

    def test_hold_is_capped_at_seven_seconds(self) -> None:
        """§32 clamp 上限：密页也不许停到观众走神。"""
        deck = {"slides": [
            {"type": "content-text", "title": "密", "bullets": [str(i) for i in range(10)]},
        ]}
        spans = render.timeline(deck, self.tokens)
        self.assertLessEqual(spans[0]["hold"], 7.0 + 1e-9,
                             "hold 超过 7s —— clamp 没生效")

    def test_total_duration_matches_the_product(self) -> None:
        """产物里写进去的时长必须等于 Python 算出来的 —— 两处不一致就是“看到的与录到的不是一回事”。"""
        html = render.render(self.spec, self.style)
        m = re.search(r"window\.__deck_timeline=(\[.*?\]);", html)
        self.assertIsNotNone(m, "产物里没有时间轴 —— 注入漏了")
        spans = json.loads(m.group(1))  # type: ignore[union-attr]
        want = render.total_duration(self.spec["deck"], self.tokens)
        got = spans[-1]["start"] + spans[-1]["enter"] + spans[-1]["hold"]
        self.assertAlmostEqual(got, want, places=3)


class TestMotionTokens(unittest.TestCase):
    def test_every_style_declares_motion(self) -> None:
        """每种风格都必须声明运动参数 —— 运动是风格的一部分，不是全局开关。"""
        for name in STYLE_NAMES:
            with self.subTest(style=name):
                tokens = render.load_style(name)["tokens"]
                self.assertIn("motion", tokens, f"{name} 没声明 motion")
                mo = tokens["motion"]
                for key in ("easing", "cssEase", "enterMs", "staggerMs",
                            "titleHoldMs", "holdMs", "readPerItemMs"):
                    self.assertIn(key, mo, f"{name}.motion 缺 {key}")

    def test_styles_differ_in_motion(self) -> None:
        """不同风格的运动参数**不能完全一样** —— 否则“运动是风格的一部分”是假的。"""
        params = {name: tuple(sorted(render.load_style(name)["tokens"]["motion"].items()))
                  for name in STYLE_NAMES}
        self.assertEqual(len(set(params.values())), len(STYLE_NAMES),
                         "有两套风格的运动参数完全一样 —— 运动层没真的按风格分化")

    def test_no_linear_easing(self) -> None:
        """缓动不能是 linear / ease —— 那是 AI slop 的第一特征（数字元素没有重量）。"""
        for name in STYLE_NAMES:
            with self.subTest(style=name):
                css = render.load_style(name)["tokens"]["motion"]["cssEase"]
                self.assertNotIn(css, ("linear", "ease", "ease-in-out"),
                                 f"{name} 用了 {css} —— 换成 expoOut 那类有阻尼的曲线")


class TestMotionPresets(unittest.TestCase):
    """§19 元素动画按类型设计：角色决定怎么上台，不是所有元素统一 opacity 0→1。"""

    @classmethod
    def setUpClass(cls) -> None:
        with open(DEMO, encoding="utf-8") as fh:
            cls.spec = json.load(fh)
        cls.html = render.render(cls.spec, render.load_style(
            cls.spec["deck"].get("style", render.DEFAULT_STYLE)))
        cls.js = cls.html[cls.html.index("window.__deck_timeline="):]

    def test_title_uses_mask_reveal(self) -> None:
        """标题 = maskRevealY：遮罩从下揭开（clip-path inset），不是纯淡入。"""
        self.assertIn("clipPath='inset('", self.js.replace('\"', "'"),
                      "标题没有遮罩揭示")

    def test_rules_grow_from_left(self) -> None:
        """段式线 = growX：从左**画**出来（scale x + origin left），不是浮出来。"""
        self.assertIn("transformOrigin='left center'", self.js.replace('\"', "'"))

    def test_image_reveals_horizontally(self) -> None:
        """图 = imageReveal：横向揭示（inset 右收）+ 近 1 的落定 scale。"""
        self.assertIn("clipPath='inset(0 '", self.js.replace('\"', "'"))

    def test_chart_bars_grow_from_baseline(self) -> None:
        """图表 = 容器先行 + 柱从基线生长：.bar 拿到 fill-box 原点，横向竖向分开。"""
        self.assertIn("querySelectorAll('.bar')", self.js)
        self.assertIn("transformBox='fill-box'", self.js.replace('\"', "'"))
        self.assertIn("'bottom center'", self.js.replace('\"', "'"))

    def test_chart_lines_draw_along_the_path(self) -> None:
        """折线 = pathDraw：stroke-dasharray/offset 沿线描画。"""
        self.assertIn("strokeDasharray", self.js)
        self.assertIn("strokeDashoffset", self.js)

    def test_clear_paint_restores_everything_it_touches(self) -> None:
        """滚动态要回到 CSS 满态：clearPaint 必须清掉 paint 碰过的每个属性。"""
        for prop in ("clipPath", "transformOrigin", "transformBox",
                     "strokeDashoffset"):
            self.assertIn(f".{prop}=''", self.js.replace('\"', "'"),
                          f"clearPaint 没清 {prop} —— 滚动态会残留入场中间态")


class TestRenderPathIsSeekable(unittest.TestCase):
    """这个类里的两条是**静态检查**：便宜，而且是同类 bug 唯一的早期信号。"""

    @classmethod
    def setUpClass(cls) -> None:
        with open(DEMO, encoding="utf-8") as fh:
            cls.spec = json.load(fh)
        cls.style = render.load_style(cls.spec["deck"].get("style", render.DEFAULT_STYLE))
        cls.html = render.render(cls.spec, cls.style)

    def test_no_css_transition_on_the_content_path(self) -> None:
        """内容元素上不许有 CSS transition。

        这是整个动画层最容易踩、也最难发现的坑：transition 走**墙钟**，逐帧 seek
        渲染时每帧都是独立会话/独立时刻，中间态取决于“截这帧时真实过了多久”——
        不可复现，而且**不会报错**（画面只是慢慢偏掉）。

        壳（页码/快捷键提示）可以有 transition：它们录视频时是隐藏的，不进渲染路径。
        """
        offenders = []
        for m in re.finditer(r"([^{}]+)\{([^{}]*transition[^{}]*)\}", self.html):
            sel, body = m.group(1).strip(), m.group(2)
            if ".hud" in sel or ".hint" in sel:
                continue                      # 壳，不在渲染路径上
            offenders.append(f"{sel} → {' '.join(body.split())[:60]}")
        self.assertEqual(offenders, [],
                         "渲染路径上出现了 CSS transition（seek 渲染下不可复现）：\n  "
                         + "\n  ".join(offenders))

    def test_animation_uses_translate_scale_not_transform(self) -> None:
        """动画要动 `translate`/`scale` 这两个**独立属性**，不是 `transform`。

        理由：skin 自己会用 `transform`（歪一点、倾斜之类）。两边都写 transform
        就会互相覆盖 —— 动画一跑，skin 的那个变换就没了（而且只在动画期间消失，
        最难查的那一类）。
        """
        js = self.html[self.html.index("window.__deck_timeline"):]
        self.assertIn("style.translate", js, "动画没走 translate 独立属性")
        self.assertIn("style.scale", js, "动画没走 scale 独立属性")
        # 禁的是给 `transform` **属性赋值**（会和 skin 自己的变换互相覆盖）。
        # transform-origin / transform-box 是伴生属性，不碰 transform 本身，
        # 且只落在段式线与图表 SVG 内部（skin 不变换这些元素），安全。
        self.assertNotRegex(
            js, r"style\.transform\s*=",
            "动画写了 style.transform —— 会覆盖 skin 自己的变换")

    def test_product_carries_motion_params(self) -> None:
        self.assertIn("window.__deck_motion=", self.html, "产物里没有运动参数")
        self.assertIn("window.__deck_timeline=", self.html, "产物里没有时间轴")
        # 不能直接找 "__deck.seek" —— 产物里是 `window.__deck = {... seek: ...}`
        # 赋值语句里根本没有那个点号路径（调用方 animate.py 才用点号访问）。
        self.assertRegex(
            self.html, r"window\.__deck\s*=\s*\{[^}]*seek\s*:",
            "产物里没有 seek 接口 —— 逐帧录制没法驱动它")

    def test_frame_mode_hides_the_chrome(self) -> None:
        """取帧态必须隐藏壳（页码/提示），否则它们会被录进视频。"""
        self.assertIn('html[data-view="frame"] .hud', self.html,
                      "取帧态没有隐藏页码 —— 录出来的视频会带着页码")


class TestFramesAreReproducible(unittest.TestCase):
    """真开浏览器验纯函数性。这是这个文件里最贵也最重要的两条。"""

    @classmethod
    def setUpClass(cls) -> None:
        with open(DEMO, encoding="utf-8") as fh:
            spec = json.load(fh)
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.html = os.path.join(cls._tmp.name, "out.html")
        with open(cls.html, "w", encoding="utf-8") as fh:
            fh.write(render.render(spec))

    def test_same_t_produces_byte_identical_frames(self) -> None:
        """同一个 t，两次**独立的 Chrome 会话**取到的帧必须逐字节一致。

        独立会话是关键：同一个会话里连取两次，第二次可能读到缓存的合成结果，
        那样测的是“缓存对不对”，不是“渲染纯不纯”。
        """
        times = [0.4, 5.4]
        digs = []
        for round_no in (1, 2):
            d = os.path.join(self._tmp.name, f"r{round_no}")
            os.makedirs(d, exist_ok=True)
            frames = animate._capture(self.html, d, times, 1.0, False)
            import hashlib   # noqa: PLC0415

            digs.append([hashlib.sha256(open(p, "rb").read()).hexdigest() for p in frames])
        for i, t in enumerate(times):
            self.assertEqual(
                digs[0][i], digs[1][i],
                f"t={t}s 两次独立会话取到的帧不一样 —— seek 路径上混进了墙钟/随机性")

    def test_frames_actually_differ_across_time(self) -> None:
        """不同 t 必须出不同的帧 —— 否则动画根本没在动，而上面那条会假绿。"""
        d = os.path.join(self._tmp.name, "diff")
        os.makedirs(d, exist_ok=True)
        frames = animate._capture(self.html, d, [0.05, 1.6], 1.0, False)
        import hashlib   # noqa: PLC0415

        a, b = (hashlib.sha256(open(p, "rb").read()).hexdigest() for p in frames)
        self.assertNotEqual(a, b, "入场前与入场后的帧一样 —— 动画没生效")

    def test_frame_size_is_exactly_one_slide(self) -> None:
        """取帧必须是精确的 1600×900（×DPR）—— 不然视频里会带上下页的边。"""
        from PIL import Image   # noqa: PLC0415

        d = os.path.join(self._tmp.name, "size")
        os.makedirs(d, exist_ok=True)
        frames = animate._capture(self.html, d, [1.6], 1.0, False)
        self.assertEqual(Image.open(frames[0]).size, (1600, 900),
                         "取帧尺寸不是一页 —— 视口没钉准（Emulation.setDeviceMetricsOverride）")


if __name__ == "__main__":
    unittest.main()
