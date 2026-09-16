#!/usr/bin/env python3
"""用 **Excalidraw 官方导出 API** 把 `.excalidraw` 渲染成 PNG / SVG。

## 为什么需要这个工具（PIL 预览的边界）

`dev-tools/preview.py` 是我们自己的布局模型画出来的**近似图** —— 它看不见渲染器差异，
手绘质感、字体、箭头样式都是假的。这个工具走的是**官方路线**：

    场景 JSON → 官方 @excalidraw/utils（UMD）→ exportToBlob / exportToSvg → PNG / SVG

`@excalidraw/utils` 是 Excalidraw 官方发布的包（0.1.4 起只发 ESM）；官方没有 CLI，
浏览器外能拿到的"官方导出"就是它暴露的 `exportToBlob` / `exportToSvg` / `exportToCanvas`。
本工具生成一个自包含 HTML（内嵌场景），用**系统 Chrome 无头模式**把官方 ESM
动态 import 进来跑一遍导出，再把 PNG 的 base64 与 SVG 从 DOM 里回收 —— 零 npm
依赖，只需要机器上有 Chrome（Chromium / Edge / Brave 也可以）。

## 环境要求（这是 dev-tools，不在核心链路的零依赖承诺内）

- Chrome / Chromium / Edge / Brave 之一（自动探测，或 `--browser` / 环境变量
  `EXCALIDRAW_EXPORT_BROWSER` 指定）；首次使用需要**联网**拉取官方 UMD 包。
- 导出用的字体由 Excalidraw 官方包自带并嵌入产物，本机不需要装字体。

## 实测到的官方 API 形状（0.1.5）

```js
const utils = await import("https://cdn.jsdelivr.net/npm/@excalidraw/utils@0.1.5/+esm");
await utils.exportToBlob({ data: { elements, appState, files }, config: { mimeType: "image/png", scale: 2, padding: 32 } });
await utils.exportToSvg ({ data: { elements, appState, files }, config: { padding: 32 } });
```

- **不是** `exportToBlob({elements, appState, ...})`（那是 `@excalidraw/excalidraw` 里
  React 那套签名的样子）；0.1.5 一律是 `{ data, config }` 两段式。传错会得到
  `Cannot read properties of undefined (reading 'elements')`。
- 0.1.4 起**只发 ESM、没有 UMD**（老的 `unpkg .../excalidraw-utils.min.js` 早已 404）。
- **倍率两条路不一样**（都实测过）：PNG 走 `config.scale`；SVG 走
  `appState.exportScale`（PNG 传 `appState.exportScale` 会被忽略 —— 出来的是 1 倍图）。
- 留白**两条路都走 `config.padding`**（实测 2026-09-17，0.1.5）。
  `appState.exportPadding` **被忽略** —— 设 32 与不设，PNG 都是 3282×1895；
  换成 `config.padding: 32` 才是 3410×2023（正好多 2×32 图内单位）。而两个官方默认
  不一样：**PNG 默认 0（贴边）、SVG 默认 10**，所以不显式传就会贴着边框。
  本工具**默认给 32**：图内节点自己的内边距是 22~24，外面比里面还紧就显局促。
  `export_drawio.py` 的目标与它一致（最紧一边 ≈32 图内单位），但数值取 48 —— 官方
  那边分得不均（实测右/下只拿到 0.69×B），那是它的事，不是这里的。
  背景由 `appState.viewBackgroundColor` 决定。
- 0.1.5 的导出里**没有** `restoreElements`，只有 `exportToBlob/exportToSvg/
  exportToCanvas/exportToClipboard/getCommonBounds/MIME_TYPES`。

## 用法

    python3 dev-tools/export_excalidraw.py x.excalidraw -o x.png
    python3 dev-tools/export_excalidraw.py x.excalidraw -o x.png --svg x.svg --scale 2
    python3 dev-tools/export_excalidraw.py x.excalidraw --stdout-status --json

退出码：0 = 成功；1 = 官方导出在页面里失败（详见 --json 的 message）；
2 = 环境 不满足（找不到浏览器 / 场景读不了）。
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# 与三档声明对齐：官方渲染是第二档（真实渲染）的证据来源；
# 第三档（感知审查）仍然只能由人或图像模型做。
# 官方 @excalidraw/utils 自 0.1.4 起只发 ESM（无 UMD），用 jsdelivr 的 +esm 入口；
# 它会把依赖一起打包好，浏览器里直接 import 即可。实测版本与可用导出见文件头注释。
CDN = "https://cdn.jsdelivr.net/npm/@excalidraw/utils@0.1.5/+esm"
VIRTUAL_TIME_BUDGET_MS = 20000   # 页面里导出是异步的；给 Chrome 足够的虚拟时间
# 默认留白（场景单位，会随 --scale 一起放大）。官方默认 10 —— 导出来内容紧贴边框、
# 像被框卡住；图内节点自己的内边距是 22~24，外面比里面还紧就不自然。
# export_drawio.py 的默认留白取同一个数，两个后端的产物观感一致。
DEFAULT_PADDING = 32


# ── 浏览器探测 ─────────────────────────────────────────────
_MAC_GLOBS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Arc.app/Contents/MacOS/Arc",
]
_POSIX_NAMES = ["chromium", "chromium-browser", "google-chrome", "chrome",
                "microsoft-edge", "brave-browser"]


def find_browser(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.exists(explicit) else shutil.which(explicit)
    env = os.environ.get("EXCALIDRAW_EXPORT_BROWSER", "").strip()
    if env:
        got = env if os.path.exists(env) else shutil.which(env)
        if got:
            return got
    for pattern in _MAC_GLOBS:
        for hit in glob.glob(pattern):
            if os.path.exists(hit):
                return hit
    for name in _POSIX_NAMES:
        got = shutil.which(name)
        if got:
            return got
    return None


# ── 导出页面（模板；场景在运行时注入）──────────────────────
# 页面做的事：读内嵌场景 → （有 restoreElements 就先 restore 规范化）→
# exportToBlob 出 PNG（base64 进 DOM）→ exportToSvg 出 SVG（base64 进 DOM）。
# 全部完成后把 #status 标成 ok；Chrome 的 --dump-dom 会把最终 DOM 吐回来。
PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script type="application/json" id="excalidraw-scene">__SCENE_JSON__</script>
</head>
<body>
<pre id="status" data-state="running">running</pre>
<pre id="out-png" style="display:none"></pre>
<pre id="out-svg" style="display:none"></pre>
<script type="module">
(async function () {
  var status = document.getElementById("status");
  function fail(message) {
    status.textContent = message;
    status.setAttribute("data-state", "error");
  }
  try {
    var utils = await import("__CDN__");
    if (typeof utils.exportToBlob !== "function") {
      fail("官方包加载了但没有 exportToBlob；检查 " + "__CDN__");
      return;
    }
    var scene = JSON.parse(document.getElementById("excalidraw-scene").textContent);
    var elements = scene.elements || [];
    var appState = Object.assign({}, scene.appState || {});
    appState.exportBackground = true;
    appState.exportScale = __SCALE__;
    try { if (document.fonts && document.fonts.ready) { await document.fonts.ready; } } catch (e) {}
    // 不去写 appState.exportPadding：官方包忽略它，写了就是个哑参数（见文件头实测）。
    var data = { elements: elements, appState: appState, files: scene.files || {} };
    var pngB64 = await utils.exportToBlob({
      data: data,
      // PNG 的倍率在 config.scale（实测：appState.exportScale 对 PNG 无效、
      // 对 SVG 有效；config.exportScale / getDimensions 都不行）。
      // 留白同样在 config.padding —— appState.exportPadding 被官方包忽略（实测），
      // 只设 appState 的话留白是个哑参数，出来的图会贴边。
      config: { mimeType: "image/png", scale: __SCALE__, padding: __PADDING__ },
    }).then(function (blob) {
      return new Promise(function (resolve) {
        var reader = new FileReader();
        reader.onload = function () { resolve(String(reader.result).split(",")[1]); };
        reader.readAsDataURL(blob);
      });
    });
    document.getElementById("out-png").textContent = pngB64;
    var svg = await utils.exportToSvg({
      data: data,
      config: { padding: __PADDING__ },
    });
    var svgText = new XMLSerializer().serializeToString(svg);
    document.getElementById("out-svg").textContent = btoa(unescape(encodeURIComponent(svgText)));
    status.textContent = "ok";
    status.setAttribute("data-state", "ok");
  } catch (err) {
    fail("导出异常: " + (err && err.message ? err.message : String(err)));
  }
})();
</script>
</body>
</html>
"""


def _inject_scene(page: str, scene: dict, scale: float, padding: int) -> str:
    scene_json = json.dumps(scene, ensure_ascii=False)
    scene_json = scene_json.replace("</", "<\\/")   # 防止 </script> 提前闭合
    # scale/padding 在 export() 里已经转换并守卫过，这里只做字符串替换（不抛异常）
    return (page
            .replace("__CDN__", CDN)
            .replace("__SCENE_JSON__", scene_json)
            .replace("__SCALE__", repr(scale))
            .replace("__PADDING__", repr(padding)))


def _dump_dom(browser: str, html_path: str) -> str:
    cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           f"--virtual-time-budget={VIRTUAL_TIME_BUDGET_MS}",
           "--dump-dom", html_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 and not proc.stdout:
        raise RuntimeError(f"浏览器退出码 {proc.returncode}：{proc.stderr[-400:]}")
    return proc.stdout


def export(scene_path: str, png_path: str | None, svg_path: str | None,
           browser: str | None = None, scale: float = 2.0,
           padding: int = DEFAULT_PADDING) -> dict:
    """跑一次官方导出。返回机器可读回执；不抛业务异常（结果都在回执里）。"""
    try:
        scale = float(scale)
        padding = int(padding)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "stage": "input", "message": f"scale/padding 不合法：{exc}"}
    try:
        with open(scene_path, encoding="utf-8") as fh:
            scene = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "stage": "input", "message": f"场景读不了：{exc}"}

    exe = find_browser(browser)
    if not exe:
        return {"ok": False, "stage": "environment",
                "message": "找不到 Chrome/Chromium/Edge/Brave；用 --browser 指定路径，"
                           "或设置环境变量 EXCALIDRAW_EXPORT_BROWSER"}

    with tempfile.TemporaryDirectory(prefix="excalidraw-export-") as td:
        html_path = os.path.join(td, "export.html")
        try:
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(_inject_scene(PAGE_TEMPLATE, scene, scale, padding))
        except OSError as exc:
            return {"ok": False, "stage": "output",
                    "message": f"写不了临时导出页：{exc}"}
        try:
            dom = _dump_dom(exe, html_path)
        except (subprocess.TimeoutExpired, RuntimeError) as exc:
            return {"ok": False, "stage": "browser", "message": str(exc),
                    "browser": exe}

    status = re.search(r'<pre id="status"[^>]*data-state="([^"]*)"[^>]*>(.*?)</pre>',
                       dom, re.S)
    state = status.group(1) if status else "missing"
    message = status.group(2) if status else "页面里找不到状态节点"
    if state != "ok":
        return {"ok": False, "stage": "page", "message": message, "browser": exe}

    outputs = {}
    if png_path:
        m = re.search(r'<pre id="out-png"[^>]*>([A-Za-z0-9+/=]+)</pre>', dom)
        if not m:
            return {"ok": False, "stage": "page",
                    "message": "PNG 数据缺失：" + message, "browser": exe}
        try:
            with open(png_path, "wb") as fh:
                fh.write(base64.b64decode(m.group(1)))
        except OSError as exc:
            return {"ok": False, "stage": "output",
                    "message": f"写不了 {png_path}：{exc}"}
        outputs["png"] = os.path.abspath(png_path)
    if svg_path:
        m = re.search(r'<pre id="out-svg"[^>]*>([A-Za-z0-9+/=]+)</pre>', dom)
        if not m:
            return {"ok": False, "stage": "page",
                    "message": "SVG 数据缺失：" + message, "browser": exe}
        try:
            with open(svg_path, "wb") as fh:
                fh.write(base64.b64decode(m.group(1)))
        except OSError as exc:
            return {"ok": False, "stage": "output",
                    "message": f"写不了 {svg_path}：{exc}"}
        outputs["svg"] = os.path.abspath(svg_path)

    return {"ok": True, "outputs": outputs, "browser": exe,
            "engine": "official @excalidraw/utils exportToBlob/exportToSvg"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Excalidraw 官方导出（真实渲染 PNG/SVG）")
    ap.add_argument("scene", help="*.excalidraw 场景文件")
    ap.add_argument("-o", "--out", help="PNG 输出路径（默认与场景同名 .png）")
    ap.add_argument("--svg", help="同时导出 SVG 到这个路径")
    ap.add_argument("--scale", type=float, default=2.0, help="导出倍率（默认 2）")
    ap.add_argument("--padding", type=int, default=DEFAULT_PADDING,
                    help=f"内容四周留白，场景单位（默认 {DEFAULT_PADDING}；官方默认 10 = 贴边）")
    ap.add_argument("--browser", help="浏览器可执行文件路径（默认自动探测）")
    ap.add_argument("--json", action="store_true", help="输出机器可读回执")
    args = ap.parse_args(argv)

    out = args.out or os.path.splitext(args.scene)[0] + ".png"
    receipt = export(args.scene, out, args.svg, browser=args.browser,
                     scale=args.scale, padding=args.padding)
    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if not receipt["ok"]:
        print(f"✗ 官方导出失败（{receipt.get('stage')}）：{receipt.get('message')}",
              file=sys.stderr)
        return 2 if receipt.get("stage") == "environment" or receipt.get("stage") == "input" else 1
    files = " + ".join(receipt["outputs"].keys())
    print(f"✓ 官方渲染完成（{files}，scale {args.scale:g}）：")
    for path in receipt["outputs"].values():
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
