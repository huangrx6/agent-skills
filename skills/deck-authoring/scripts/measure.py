#!/usr/bin/env python3
"""产物实测层 —— 用**真浏览器**量，不用估算猜。

## 为什么必须有这一层

原先 `check.py` 判断"文字放不放得下"靠一个估算函数：

    text_width(text, size) = (CJK 个数 + ASCII 个数 × 0.55) × size

对同一行 26 个汉字 40px 的标题，它算 **1040px**，浏览器实测 **840px** —— 差 24%。
而"哪一行被裁了"这件事，估算根本看不出来：真实的折行、字体回退、字距、
`white-space` 都是浏览器才知道的事。

huashu-design 在这件事上的判断是对的：它的 `verify.py` 开真 Chromium 抓控制台错误、
截多视口截图。**它不估，它量。** 这一层就是照那个思路补的，但不引入新依赖 ——
`shots.py` 本来就要系统 Chrome，这里复用它。

## 怎么把数据从浏览器里拿出来（零依赖）

Chrome CLI 只能 `--dump-dom`（不能像 CDP 那样取求值结果），所以：

1. 往产物副本里注入一小段探针脚本（`<head>` 之后，先于页面自身脚本）
2. 探针在 `load` + 双 rAF 后量所有 `[data-m]` 元素，把结果 **base64** 塞进
   `<pre id="__probe">`
3. 我们用 `--dump-dom --virtual-time-budget` 跑一次，把那段 base64 取回来解码

base64 是为了绕开转义（JSON 里可能有 `<`、引号、中文）。

副本写在**产物同目录**下 —— 写进临时目录会让相对路径的图片全部裂掉。

## 量什么

| 量 | 用来判 |
|---|---|
| 真实盒模型（x/y/w/h） | 是否越出版面、是否互相压住 |
| **真实文字宽**（离屏 span 量） | 文字溢出 —— 取代估算 |
| `scrollWidth > clientWidth` | **被裁切**（真实发生的裁切，不是推测） |
| `img.naturalWidth` | 图有没有真的加载 |
| 注入的错误监听 | 页面自身脚本报错（白屏类事故） |
| canvas 测宽对比 | **字体回退**：声明的族在不在 |

字体那条是启发式（拿一个一定不存在的族当基准比宽度），所以只作为**提示**，
不判失败 —— 它报错了也可能是衬线撞衬线，得人看一眼。

跑法：
    python3 measure.py out.html                  # 量并写出 out.measured.json
    python3 measure.py out.html --json           # 打到 stdout
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。

    把模块注册进 sys.modules 之后再 exec —— 写法沿用 `check_layout.py`。那一步是为
    `@dataclass` / 自引用 import 准备的；本 skill 的脚本都没有这两样，属防御性写法；
    它**不**负责“同一模块只加载一次”（实测：两次加载是两个对象）。
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py")
    mod_spec = importlib.util.spec_from_file_location(f"_deck_{name}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_spec.name] = module
    mod_spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")   # IO 收口：读不到要报清楚，不甩 traceback

# 实测结果缓存：键 = 产物内容的 sha256。同一份 HTML 同一进程内只量一次。
# 为什么需要：`check()` 每次调用都会量一遍，而测试里同一份基线被查好几次 ——
# 不加缓存实测 36 条测试要 25 秒，全是重复开 Chrome。
_CACHE: dict[str, dict] = {}

# 探针：注入到 <head> 之后。先挂错误监听，再在 load 后量。
PROBE_JS = r"""
(function () {
  var errs = [];
  window.addEventListener('error', function (e) { errs.push('error: ' + (e.message || e.type)); });
  window.addEventListener('unhandledrejection', function (e) { errs.push('rejection: ' + e.reason); });
  var ce = console.error; console.error = function () {
    errs.push('console.error: ' + Array.prototype.join.call(arguments, ' '));
    ce.apply(console, arguments);
  };

  function textWidth(el, cs) {
    // 离屏 span 量真实文字宽（不带容器的 overflow:hidden）
    var s = document.createElement('span');
    s.style.cssText = 'position:absolute;left:-99999px;top:0;visibility:hidden;'
      + 'white-space:nowrap;font:' + cs.font + ';letter-spacing:' + cs.letterSpacing + ';';
    s.textContent = el.textContent;
    document.body.appendChild(s);
    var w = s.getBoundingClientRect().width;
    s.remove();
    return w;
  }

  var GENERIC = {'serif':1,'sans-serif':1,'monospace':1,'cursive':1,'fantasy':1,
                 'system-ui':1,'ui-serif':1,'ui-sans-serif':1,'ui-monospace':1,
                 'ui-rounded':1,'math':1,'emoji':1,'fangsong':1};
  function fontAvailable(fam) {
    // 通用族不是“字体”而是**回退目标**：`font: 40px serif` 和基准的不存在族一样
    // 都落到默认衬线，宽度相等 → 启发式会误报“缺失”。先排掉这一整类。
    if (GENERIC[fam.toLowerCase()]) {
      return { available: true, generic: true, width: null };
    }
    // **像素指纹**：同一字串在"声明的族"与"一定不存在的族"下各画一次，逐像素比。
    // 为什么不是宽度（原来就是这么写的）：CJK 字形全是 1em 等宽 —— 换字体宽度不变，
    // 实测 11 个族（含不存在的族）宽度全等，宽度法对中文**永远判不出**，只会误报。
    // 像素比的是字形形状与覆盖，对 CJK 有效；alpha 通道做指纹。
    var sample = '汉字永宇国术图 AaWM7';
    var cv = document.createElement('canvas');
    cv.width = 300; cv.height = 56;
    var ctx2 = cv.getContext('2d');
    function fingerprint(f) {
      ctx2.clearRect(0, 0, cv.width, cv.height);
      ctx2.font = '32px "' + f + '", __no_such_font_xyz__';
      ctx2.fillStyle = '#000';
      ctx2.textBaseline = 'top';
      ctx2.fillText(sample, 2, 6);
      var d = ctx2.getImageData(0, 0, cv.width, cv.height).data;
      var h = 5381;
      for (var i = 0; i < d.length; i += 4) { h = ((h * 33) ^ d[i + 3]) >>> 0; }
      return h;
    }
    var missing = fingerprint('__no_such_font_xyz__');
    var mine = fingerprint(fam);
    // 与默认渲染一致 = 这个族没带来任何字形差异（不存在，或它就是本机默认族）。
    return { available: mine !== missing, defaultLike: mine === missing, width: null };
  }

  function collect() {
    var out = {
      viewport: { w: window.innerWidth, h: window.innerHeight },
      elements: [], images: [], errors: errs, fonts: {}
    };
    var fams = {};
    var stacks = {};                       // 有文字的元素的字体栈（保留顺序）
    document.querySelectorAll('[data-m]').forEach(function (el) {
      var r = el.getBoundingClientRect();
      var cs = getComputedStyle(el);
      out.elements.push({
        id: el.getAttribute('data-m'),
        x: Math.round(r.x * 10) / 10, y: Math.round(r.y * 10) / 10,
        w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10,
        textW: Math.round(textWidth(el, cs) * 10) / 10,
        scrollW: el.scrollWidth, clientW: el.clientWidth,
        scrollH: el.scrollHeight, clientH: el.clientHeight,
        fontSize: parseFloat(cs.fontSize),
        fontFamily: cs.fontFamily,
        // 字重：导出层要用它，不能按角色写死（有两套风格的标题就是 400 字重）。
        // getComputedStyle 给的是字符串（'400'/'700'），解析不了就按常规 400。
        fontWeight: parseInt(cs.fontWeight, 10) || 400,
        // 图元素的原始像素尺寸：判断“是不是被放大渲染了”（放大 = 糊）。
        // SVG 也报自己的 viewBox 尺寸（但 SVG 放大不糊，所以那边不看这条）。
        //
        // 要往下找一层 `<img>`：`data-m` 有时挂在**包着图的容器**上（内容图的
        // `.imgwrap` 是 `<figure>`，而品牌 logo 的 `data-m` 直接挂在 `<img>` 上）。
        // 只看 el.naturalWidth 的话，内容图永远报 0 —— “图被放大＝糊”那条检查
        // 就永远不会触发（实测：压测里量出来 s12.image 是 0，而 images 数组里是 640）。
        naturalW: el.naturalWidth || (el.querySelector && el.querySelector('img')
                   ? el.querySelector('img').naturalWidth : 0) || 0,
        naturalH: el.naturalHeight || (el.querySelector && el.querySelector('img')
                   ? el.querySelector('img').naturalHeight : 0) || 0,
        color: cs.color,
        overflow: cs.overflow,
        visible: cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0,
        // 图表就绪（v4）：G2 在浏览器里现渲染 —— 容器里有没有 canvas/svg、
        // 有没有报错，**只有真浏览器知道**。静态读 HTML 判断不出来（产物里
        // 只有容器与 spec），所以 readiness 由这里实测并写进结果。
        // 图表就绪（v4）：G2 在浏览器里现渲染，容器是 **.g2 子元素**（挂在
        // chartwrap 上，而 chartwrap 才是带 data-m 的那个）—— 所以在子元素上找。
        // 静态读 HTML 判断不出来（产物里只有容器与 spec），只有真浏览器知道。
        chartReady: (function (g2) {
          if (!g2) return null;
          var err = g2.getAttribute('data-chart-error');
          if (err) return 'error:' + err;
          return g2.querySelector('canvas,svg') ? 'ready' : 'pending';
        })(el.querySelector('.g2[data-g2]')),
        // 标题的**逐行真实矩形**（Range API）：标题装饰（侧条/下划线）锚定的是
        // 真实行几何，不是容器盒 —— 行数/行高变了装饰要跟着走，验证需要它。
        lineRects: (function () {
          var mid = el.getAttribute('data-m') || '';
          if (!/\.title$/.test(mid)) return null;
          var range = document.createRange();
          range.selectNodeContents(el);
          return Array.prototype.map.call(range.getClientRects(), function (r) {
            return { x: Math.round(r.x * 10) / 10, y: Math.round(r.y * 10) / 10,
                     w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10 };
          });
        })()
      });
      // 只统计**自己直接渲染文字**的元素。
      //
      // 判据是「有直接子文本节点」，不是 `textContent`：后者会把**后代的**文字也算进来，
      // 于是 `<figure class="imgwrap"><img><figcaption>图注</figcaption></figure>`
      // 里的 figure 就被当成“有文字”的元素 —— 而它自己一个字形都不渲染，
      // 它的 font-family 只是 Chrome 给 CJK 的 UA 默认值（实测报了 'PingFang SC'，
      // 页面上根本没写这个族）。这类假提示会把人生生练成"忽略字体提示"。
      //
      // 踩过两次：第一次是 figure 里只有 <img>（无 textContent，侥幸躲过）；
      // 加上 <figcaption> 之后 textContent 非空，八套风格全部报了同一条假提示。
      var ownText = '';
      for (var ni = 0; ni < el.childNodes.length; ni++) {
        if (el.childNodes[ni].nodeType === 3) ownText += el.childNodes[ni].nodeValue;
      }
      if (ownText.trim()) {
        stacks[cs.fontFamily] = true;
        cs.fontFamily.split(',').forEach(function (f) {
          f = f.trim().replace(/^["']|["']$/g, '');
          if (f) fams[f] = true;
        });
      }
    });
    Object.keys(fams).forEach(function (f) { out.fonts[f] = fontAvailable(f); });
    // 字体栈**保留顺序**交出去：这样才能说清“首选不可用时谁顶上了”，
    // 而不是只丢一句“某族不可用”（不够可操作）。
    out.stacks = Object.keys(stacks).map(function (s) {
      return s.split(',').map(function (f) { return f.trim().replace(/^["']|["']$/g, ''); })
              .filter(function (f) { return f; });
    });
    document.querySelectorAll('img').forEach(function (im) {
      out.images.push({
        src: im.getAttribute('src'), complete: !!im.complete,
        naturalW: im.naturalWidth, naturalH: im.naturalHeight
      });
    });
    // 装饰墨块（data-zone）：不是内容、不属语义清单，但导出层要把它画成**原生形状**
    // —— 所以也量。它自己不带 id，所在页从 DOM 里找最近的一页。
    out.decor = [];
    var secs = [].slice.call(document.querySelectorAll('section.slide'));
    document.querySelectorAll('[data-zone]').forEach(function (el) {
      var r = el.getBoundingClientRect();
      out.decor.push({
        slide: secs.indexOf(el.closest('section.slide')) + 1,
        kind: el.getAttribute('data-kind'),
        zone: el.getAttribute('data-zone'),
        size: parseFloat(el.getAttribute('data-size')),
        x: Math.round(r.x * 10) / 10, y: Math.round(r.y * 10) / 10,
        w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10
      });
    });
    // 每页版面**各自的盒子**。产物是竖向堆叠的多页，第 2 页的元素 y 本来就在 900 以下；
    // 拿全局页面边界（1600×900）去比多页产物，会把后面每一页都误报成“越界”（实测踩过）。
    out.slides = [];
    document.querySelectorAll('section.slide').forEach(function (s) {
      var r = s.getBoundingClientRect();
      out.slides.push({
        x: Math.round(r.x * 10) / 10, y: Math.round(r.y * 10) / 10,
        w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10
      });
    });
    return out;
  }

  function emit() {
    // **不能靠 rAF 触发**：在 `--virtual-time-budget` 下虚拟时间会直接跳到底，
    // rAF 回调跟预算到期之间存在竞争 —— 实测同一份产物跑三次，两次拿到、一次是空
    // （“探针没跑起来”）。改成 load 后**同步**采集：load 时 CSS 已应用、布局已完成，
    // 量得到的就是终值。
    var pre = document.getElementById('__probe');
    if (!pre) { return; }
    try {
      pre.textContent = btoa(unescape(encodeURIComponent(JSON.stringify(collect()))));
    } catch (e) {
      pre.textContent = btoa('{"fatal":"' + String(e) + '"}');
    }
  }
  if (document.readyState === 'complete') { emit(); }
  else { window.addEventListener('load', emit); }
  // 字体晚到的话再补一次（幂等覆盖）—— 系统字体场景下通常用不上
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () {
      if (document.readyState === 'complete') { emit(); }
    });
  }
})();
"""

PROBE_HTML = '<pre id="__probe" style="display:none"></pre>'


def _inject(html: str) -> str:
    """把探针塞到 <head> 之后（先于页面自身脚本），并把结果容器一并放进去。"""
    at = html.find("<head")
    if at == -1:
        at = html.find("<html")
    close = html.find(">", at)
    if close == -1:
        raise SystemExit("✗ 产物里找不到 <head>，注入不了测量探针")
    return (html[:close + 1] + PROBE_HTML + "<script>" + PROBE_JS + "</script>"
            + html[close + 1:])


def _extract(dumped: str) -> dict:
    m = re.search(r'<pre id="__probe"[^>]*>([^<]*)</pre>', dumped)
    if not m or not m.group(1).strip():
        raise SystemExit("✗ 没拿到测量结果 —— 探针没跑起来（页面有脚本错误？）")
    try:
        return json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SystemExit(f"✗ 测量结果解不开：{exc}") from exc


def read_manifest(html: str) -> list[dict]:
    """取出渲染层嵌进产物的语义清单（身份 / 角色 / 意图字号）。"""
    m = re.search(r'<script type="application/json" id="__deck_manifest">(.*?)</script>',
                  html, re.S)
    if not m:
        return []
    try:
        return json.loads(m.group(1))
    except ValueError:
        return []


# 壳与品牌标记：固定在版面角落，不是“内容”。算内容占位时要把它们排掉 ——
# 不排的话每页都“装满”（因为页脚永远在底部）。
CHROME_ROLES = ("foot", "brandfoot", "logo")


def slide_content_span(measured: dict, slide_no: int) -> tuple[float, float] | None:
    """一页里**内容**的竖向占位（相对该页左上角），返回 (顶, 底)；没内容返回 None。

    必须按**自己那页**归一化：产物是纵向堆叠的，`getBoundingClientRect()` 给的是
    文档坐标（实测踩过：第 2 页之后的元素全都“越出 900px”）。探针把每页的 rect 也
    带回来了，减一下就好。

    为什么单独一个函数：`fit.py`（试排）与 `check.py`（半页死白的提示）要用**同一个**
    口径 —— 两处各算一次的话，“fit 说装得下、check 说太稀”这种矛盾只是时间问题。
    """
    slides = measured.get("slides") or []
    if not 1 <= slide_no <= len(slides):
        return None
    base = slides[slide_no - 1]["y"]
    top: float | None = None
    bottom: float | None = None
    for el in measured.get("elements", []):
        if el.get("slide") != slide_no or el.get("role") in CHROME_ROLES:
            continue
        loc, end = el["y"] - base, el["y"] + el["h"] - base
        top = loc if top is None else (loc if loc < top else top)
        bottom = end if bottom is None else (end if end > bottom else bottom)
    if top is None or bottom is None:
        return None
    return (top, bottom)


def measure(html_path: str, budget_ms: int = 2500, chrome: str = CHROME) -> dict:
    """跑一次真浏览器，返回合并了语义清单的实测结果。

    同一份 HTML（按内容 sha256）在**同一进程内只量一次** —— 否则每个校验调用点
    都会再开一次 Chrome（测试里同一份基线被查好几次，实测 36 条测试从 25 秒降到几秒）。
    """
    if not os.path.isfile(chrome):
        raise SystemExit(f"✗ 找不到 Chrome：{chrome}\n"
                         f"  这一层靠真浏览器度量，估算是替代不了的。")
    html = deckio.read_text(html_path)
    # 缓存键必须**带上产物所在目录**：同一份 HTML 放在不同目录，量出来的结果可能不同
    # （相对路径的图片在不在旁边）。只拿 HTML 内容做键会把 A 目录的结果错给 B 目录 ——
    # 实际上坑过：测试里先量了“图不存在”的目录，缓存在那里，后来把图放好了仍然报缺图。
    directory = os.path.dirname(os.path.abspath(html_path)) or "."
    cache_key = hashlib.sha256((directory + "\x00" + html).encode("utf-8")).hexdigest()
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    manifest = {e["id"]: e for e in read_manifest(html)}

    # 副本必须落在**产物同目录** —— 换目录会让相对路径的图片全部裂掉（实测过）。
    fd, probe_path = tempfile.mkstemp(prefix=".__probe_", suffix=".html", dir=directory)
    os.close(fd)
    try:
        with open(probe_path, "w", encoding="utf-8") as fh:
            fh.write(_inject(html))
        proc = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             f"--virtual-time-budget={budget_ms}", "--dump-dom",
             f"file://{probe_path}"],
            capture_output=True, text=True)
        raw = _extract(proc.stdout)
    finally:
        try:
            os.unlink(probe_path)
        except OSError:
            pass

    # 合并：几何来自测量，角色/意图来自清单。
    for el in raw.get("elements", []):
        meta = manifest.get(el["id"], {})
        el["role"] = meta.get("role")
        el["intendedText"] = meta.get("text")
        el["slide"] = meta.get("slide")
        el["intendedSize"] = meta.get("fontSize")

    # 幻灯片版面（拿 section 的真实盒子，判"页本身有没有超出 1600×900"）
    raw["source"] = os.path.abspath(html_path)
    raw["manifest_count"] = len(manifest)
    raw["measured_count"] = len(raw.get("elements", []))
    _CACHE[cache_key] = raw
    return raw


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="产物实测层：用真浏览器量（不估算）")
    ap.add_argument("html")
    ap.add_argument("-o", "--out", default=None, help="默认写出 <html>.measured.json")
    ap.add_argument("--budget-ms", type=int, default=2500)
    ap.add_argument("--json", action="store_true", help="打到 stdout")
    args = ap.parse_args(argv[1:])

    data = measure(args.html, args.budget_ms)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    out = args.out or (args.html + ".measured.json")
    deckio.write_text(out, json.dumps(data, ensure_ascii=False, indent=2))

    missing = [f for f, v in data["fonts"].items() if not v["available"]]
    broken = [i["src"] for i in data["images"] if not (i["complete"] and i["naturalW"])]
    print(f"✓ 实测 {data['measured_count']} 个元素"
          f"（清单 {data['manifest_count']} 条）→ {out}")
    if data["errors"]:
        print(f"  ✗ 页面报错 {len(data['errors'])} 条：{data['errors'][:3]}")
    if broken:
        print(f"  ✗ 图片没加载：{broken}")
    if missing:
        print(f"  · 字体回退（启发式提示）：{missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
