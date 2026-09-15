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
    // 启发式：拿一个一定不存在的族当基准，宽度不同 = 声明的族真的生效了
    var c = document.createElement('canvas').getContext('2d');
    var probe = '汉字宽度测试 Abcdefgh 0123456789 ilWm';
    c.font = '40px "' + fam + '"';              var a = c.measureText(probe).width;
    c.font = '40px "__no_such_font_xyz__"';     var b = c.measureText(probe).width;
    return { available: Math.abs(a - b) > 0.5, width: Math.round(a * 100) / 100 };
  }

  function collect() {
    var out = {
      viewport: { w: window.innerWidth, h: window.innerHeight },
      elements: [], images: [], errors: errs, fonts: {}
    };
    var fams = {};
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
        color: cs.color,
        visible: cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0
      });
      cs.fontFamily.split(',').forEach(function (f) {
        f = f.trim().replace(/^["']|["']$/g, '');
        if (f) fams[f] = true;
      });
    });
    Object.keys(fams).forEach(function (f) { out.fonts[f] = fontAvailable(f); });
    document.querySelectorAll('img').forEach(function (im) {
      out.images.push({
        src: im.getAttribute('src'), complete: !!im.complete,
        naturalW: im.naturalWidth, naturalH: im.naturalHeight
      });
    });
    return out;
  }

  function emit() {
    requestAnimationFrame(function () { requestAnimationFrame(function () {
      var pre = document.getElementById('__probe');
      if (!pre) { return; }
      pre.textContent = btoa(unescape(encodeURIComponent(JSON.stringify(collect()))));
    }); });
  }
  if (document.readyState === 'complete') { emit(); }
  else { window.addEventListener('load', emit); }
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


def measure(html_path: str, budget_ms: int = 2500, chrome: str = CHROME) -> dict:
    """跑一次真浏览器，返回合并了语义清单的实测结果。"""
    if not os.path.isfile(chrome):
        raise SystemExit(f"✗ 找不到 Chrome：{chrome}\n"
                         f"  这一层靠真浏览器度量，估算是替代不了的。")
    html = deckio.read_text(html_path)
    manifest = {e["id"]: e for e in read_manifest(html)}

    # 副本必须落在**产物同目录** —— 换目录会让相对路径的图片全部裂掉（实测过）。
    directory = os.path.dirname(os.path.abspath(html_path)) or "."
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
