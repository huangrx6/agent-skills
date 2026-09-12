#!/usr/bin/env python3
"""把生成的图在**真实 Excalidraw** 里打开，好接着手改。

纯 stdlib，不引入任何依赖。

## 为什么需要这个小服务

Excalidraw 支持从外部 JSON 地址导入场景：`https://excalidraw.com/#url=<URL>`
（excalidraw 的 PR #2726，没有官方 UI 入口，但确实可用）。所以把 `.excalidraw`
用 HTTP 喂给 excalidraw.com 就行。

但有两个坑，都是踩过才明白的：

1. **必须是 http(s)，不能是 `file://`。** `file://` 不会被页面 fetch 到。
2. **必须带 CORS 头。** excalidraw.com 是 https 页面去 fetch `http://localhost` ——
   localhost 属于浏览器认可的“可信源”、不受混合内容拦截，**但跨源 fetch 仍要 CORS**。
   Python 自带的 `http.server` 不发这个头，于是 fetch 被浏览器挡掉，
   现象是“打开 excalidraw.com 后一直空白”，原因只在控制台里看得到。

## 为什么不用 `SimpleHTTPRequestHandler`

第一版用了它 + `directory=`，它会：
- 把**整个目录**暴露出去（同目录下别人的文件也能被取到）
- 需要一个宽泛的 `Access-Control-Allow-Origin: *`，于是**你开着这个服务的期间，
  任何网页都能读到你的场景文件**

所以改成只服务**这一个文件**、并且只允许 `EXCALIDRAW_ORIGIN` 这一个源。
自建/内网 Excalidraw 的话改那个常量。

## 它和 Obsidian 插件的关系

在 Obsidian 里用 Excalidraw 插件的话，**根本不需要这个脚本** ——
把 `.excalidraw` 放进 vault 直接双击就行。这个脚本是给“开着 excalidraw.com 官网手改”
这条路径用的。

## 用法

    python3 scripts/open_excalidraw_com.py x.excalidraw
    python3 scripts/open_excalidraw_com.py x.excalidraw --port 8777 --no-open

按 Ctrl-C 结束服务。**页面载入完成后就可以关掉它**。

  ⚠ 浏览器里会先弹一次确认（"加载外部绘图将替换您现有的内容"），点红色那一下
  才会真的载入 —— 这是 excalidraw.com 自己的安全确认，不是本脚本的步骤。
  在此之前"页面打开了"不等于"场景进去了"。
"""

from __future__ import annotations

import argparse
import http.server
import os
import socketserver
import sys
import threading
import webbrowser
from urllib.parse import quote

EXCALIDRAW_ORIGIN = "https://excalidraw.com"
EXCALIDRAW_BASE = EXCALIDRAW_ORIGIN + "/"


def scene_url(scene_path: str, port: int) -> str:
    name = quote(os.path.basename(scene_path), safe="")
    return f"{EXCALIDRAW_BASE}#url={quote(f'http://localhost:{port}/{name}', safe='')}"


def make_handler(filename: str, payload: bytes):
    """造一个只认这一个文件名的请求处理器。"""

    class _SceneHandler(http.server.BaseHTTPRequestHandler):
        server_version = "excalidraw-diagram-scene/1"

        def _end_headers(self) -> None:
            # 只允许 excalidraw.com：别的网站就算猜到地址也读不到这个文件。
            self.send_header("Access-Control-Allow-Origin", EXCALIDRAW_ORIGIN)
            self.send_header("Vary", "Origin")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self) -> None:                       # noqa: N802 (stdlib 命名)
            # 只认这一个文件名，**连 `/` 也不开** —— 否则就说不清“到底暴露了什么”。
            if self.path.split("?", 1)[0] != f"/{filename}":
                self.send_error(404, "only the requested scene is served")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._end_headers()
            self.wfile.write(payload)

        def do_OPTIONS(self) -> None:                   # noqa: N802 (stdlib 命名)
            self.send_response(204)
            self._end_headers()

        def log_message(self, format: str, *args) -> None:   # noqa: A002 (stdlib 参数名)
            pass        # 打开一张图只有一两个请求，默认的逐请求日志纯属噪音

    return _SceneHandler


def serve(filename: str, payload: bytes, port: int) -> socketserver.TCPServer:
    handler = make_handler(filename, payload)
    socketserver.TCPServer.allow_reuse_address = True
    return socketserver.TCPServer(("127.0.0.1", port), handler)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="在 excalidraw.com 里打开场景（本地 CORS 服务）")
    ap.add_argument("scene", help="*.excalidraw")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--no-open", action="store_true", help="只打印链接，不自动打开浏览器")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.scene):
        print(f"找不到场景文件：{args.scene}", file=sys.stderr)
        return 2
    if not args.scene.endswith(".excalidraw"):
        print(f"警告：{args.scene} 不是 .excalidraw（excalidraw.com 只认这个后缀）",
              file=sys.stderr)

    # 先把文件读完再起服务：读失败时直接报错，不用起一个空服务再让页面白屏
    try:
        with open(args.scene, "rb") as fh:
            payload = fh.read()
    except OSError as exc:
        print(f"读不到场景文件：{exc}", file=sys.stderr)
        return 2

    try:
        httpd = serve(os.path.basename(args.scene), payload, args.port)
    except OSError as exc:
        print(f"端口 {args.port} 起不来：{exc}（换一个 --port）", file=sys.stderr)
        return 2

    url = scene_url(args.scene, args.port)
    # flush=True 不是多余：输出重定向到文件/管道时 Python 是块缓冲，
    # 不加的话用户**看不到那句“打开地址”，会以为程序没反应**（实测踩过）。
    print(f"只服务这一个文件：{os.path.basename(args.scene)}", flush=True)
    print(f"打开地址 {url}", flush=True)
    print("（浏览器里会先弹一次确认框：加载外部绘图将替换您现有的内容 —— "
          "点红色那一下才会真的载入；点完就可以 Ctrl-C 停掉这个服务）", flush=True)

    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停。", flush=True)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
