#!/usr/bin/env python3
"""out.html → MP4 / GIF。逐帧 seek 渲染，**确定性**。

# 为什么能确定（这套东西的地基）

「同一个 t 必出同一帧」不是锦上添花，它撑着三件事：

1. **可回归**：不同时间、不同机器渲出的同一段视频能逐帧对齐，才谈得上比对
2. **可局部重渲**：改一页不用重录整支，只重渲它那一段
3. **可复现**：别人拿到 spec 能渲出一模一样的东西

做到它要避开三个坑（都踩过 / 都有人踩过）：

- **不用 CSS `transition`** —— transition 走**墙钟**，逐帧截图下每帧都是独立进程/独立
  时刻，中间态取决于「截这帧时真实过了多久」，不可复现（huashu 坑 #18 实测）
- **不用 rAF 驱动** —— 同上。录制走 `__deck.seek(t)` 直接设状态
- **不靠实时录屏** —— 实时录屏会丢帧、随机器负载抖动。逐帧 seek 是「要哪帧给哪帧」

# 为什么用 CDP 而不是一帧开一个 Chrome

实测（同一个 1600×900 的页面，30 帧取平均）：

| 做法 | 单帧耗时 | 360 帧（15 秒 @24fps） |
| --- | --- | --- |
| 一帧一个 `chrome --headless --screenshot` | **2450 ms** | ≈ 15 分钟 |
| 一次启动 + CDP `Page.captureScreenshot` | **48 ms** | ≈ 17 秒 |

51 倍。这不是优化，是「可用」与「不可用」的区别 —— 所以 CDP 是主路径。

依赖：`websockets`（CDP 走 WebSocket）。缺了它会**说清楚**并降到慢路径，不静默变慢。

跑法：
    python3 animate.py out.html -o deck.mp4                  # 默认出 MP4
    python3 animate.py out.html -o deck.gif --width 960
    python3 animate.py out.html -o deck.mp4 --fps 60 --scale 2
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name: str):
    """动态加载同目录脚本（`scripts/` 不是包，同级 import 在静态层面无法解析）。"""
    path = os.path.join(HERE, f"{name}.py")
    mod_spec = importlib.util.spec_from_file_location(f"_deck_{name}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_spec.name] = module
    mod_spec.loader.exec_module(module)
    return module


deckio = _load_sibling("deckio")

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SWIFT_SRC = os.path.join(HERE, "h264_encode.swift")
SLIDE_W, SLIDE_H = 1600, 900


def _ws_connect() -> Any:
    """拿到 CDP 要用的 WebSocket connect。拿不到就返回 None。

    两个路径都试：websockets 13+ 把客户端移到 `websockets.asyncio.client`，
    10.x 在顶层。**只写死一个 = 换个版本就炸**（本机是 10.4，走的是老路径）。

    用 importlib 而不是两个 `import` 语句：哪个路径存在要跑起来才知道，
    静态写死一个会在另一条路上直接报 ImportError。
    """
    import importlib   # noqa: PLC0415

    for mod_name in ("websockets.asyncio.client", "websockets"):
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        fn = getattr(mod, "connect", None)
        if callable(fn):
            return fn
    return None


def _encode_binary() -> str:
    """编译并缓存 H.264 编码器（按源码 mtime 缓存，不是每次都编）。

    为什么要编译而不是每次 `swift h264_encode.swift`：后者是解释执行，
    几百帧的循环会慢一个数量级。编一次缓存在临时目录，之后是原生速度。
    """
    import hashlib   # noqa: PLC0415

    src = deckio.read_text(SWIFT_SRC)
    stamp = hashlib.sha256((src + str(os.path.getmtime(SWIFT_SRC))).encode()).hexdigest()[:16]
    cached = os.path.join(tempfile.gettempdir(), f"deck-h264-{stamp}")
    if os.path.isfile(cached):
        return cached
    if not os.path.isfile(SWIFT_SRC):
        raise SystemExit(f"✗ 找不到编码器源码：{SWIFT_SRC}")
    swiftc = subprocess.run(["which", "swiftc"], capture_output=True, text=True)
    if swiftc.returncode != 0:
        raise SystemExit(
            "✗ 没有 swiftc —— 编不了 H.264 编码器。\n"
            "  两条路：① xcode-select --install（装命令行工具，一次性）\n"
            "           ② 自己装 ffmpeg，然后把 _frames 目录里的 PNG 帧序列\n"
            "              按 --fps 编成 MP4（帧序列就在那儿，不绑编码器）")
    proc = subprocess.run(["swiftc", "-O", SWIFT_SRC, "-o", cached],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.isfile(cached):
        raise SystemExit(f"✗ swiftc 编译失败：\n{proc.stderr.strip()[:600]}")
    return cached


# ── 取帧（CDP）──────────────────────────────────────────────────────────────
async def _capture_async(html: str, out_dir: str, times: list[float], scale: float,
                         progress=None):
    """在**一次** Chrome 会话里，把这些时间点逐帧截下来。

    传时间点列表而不是 (fps, 帧数)：抽帧检查与整片录制走同一条路 ——
    否则“检查时看到的那帧”与“录进视频的那帧”可能不是同一回事。
    """
    ws_connect = _ws_connect()
    if ws_connect is None:
        raise RuntimeError("no-websockets")
    port = 9500 + (os.getpid() % 400)          # 端口跟 PID 走，并行跑不撞
    profile = tempfile.mkdtemp(prefix="deck-cdp-")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    frames: list[str] = []
    try:
        target = None
        deadline = time.time() + 25
        while time.time() < deadline and target is None:
            try:
                data = json.loads(urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json", timeout=2).read())
                for t in data:
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        target = t["webSocketDebuggerUrl"]
                        break
            except (OSError, ValueError):
                # CDP 还没起来（连不上/端口没监听）—— 等一会儿再试，不是错误
                await asyncio.sleep(0.2)
        if target is None:
            raise SystemExit("✗ 25 秒内没拿到 CDP 目标 —— Chrome 起来了吗？")

        seq = [0]

        async def cmd(ws, method: str, params: dict | None = None):
            seq[0] += 1
            mine = seq[0]
            await ws.send(json.dumps({"id": mine, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mine:
                    if "error" in msg:
                        raise SystemExit(f"✗ CDP {method} 报错：{msg['error']}")
                    return msg.get("result", {})

        async with ws_connect(target, max_size=None) as ws:
            await cmd(ws, "Page.enable")
            await cmd(ws, "Runtime.enable")
            # 取帧态要 1:1 不缩放 —— 用 deviceMetrics 把视口钉成正好一页，
            # 这样截图就是精确的 1600×900（×scale），**不需要事后裁剪**。
            await cmd(ws, "Emulation.setDeviceMetricsOverride", {
                "width": SLIDE_W, "height": SLIDE_H,
                "deviceScaleFactor": scale, "mobile": False})
            # ⚠️ __recording 必须在**导航之前**注入：页面 boot 时就要知道自己在录制
            #    （隐藏壳、不循环、首帧就 seek(0)）。晚一步就得靠事后纠正，
            #    而“事后纠正”正是 huashu 坑 #12 里那类起点偏移的来源。
            await cmd(ws, "Page.addScriptToEvaluateOnNewDocument",
                      {"source": "window.__recording = true;"})
            await cmd(ws, "Page.navigate", {"url": f"file://{os.path.abspath(html)}"})

            # 等 load + 字体就绪（字体没就绪就取帧 = 拍到 fallback 字体的排版，
            # 这是 huashu 坑 #6：测早了等于测错）
            for _ in range(200):
                r = await cmd(ws, "Runtime.evaluate", {
                    "expression": "document.readyState === 'complete'",
                    "returnByValue": True})
                if r.get("result", {}).get("value"):
                    break
                await asyncio.sleep(0.1)
            await cmd(ws, "Runtime.evaluate", {
                "expression": "document.fonts ? document.fonts.ready : 1",
                "awaitPromise": True})

            n = len(times)
            for i, t in enumerate(times):
                await cmd(ws, "Runtime.evaluate",
                          {"expression": f"window.__deck.seek({t:.6f})"})
                shot = await cmd(ws, "Page.captureScreenshot",
                                 {"format": "png", "captureBeyondViewport": False})
                path = os.path.join(out_dir, f"f{i:05d}.png")
                deckio.write_bytes(path, base64.b64decode(shot["data"]))
                frames.append(path)
                if progress:
                    progress(i + 1, n)
        return frames
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        import shutil   # noqa: PLC0415
        shutil.rmtree(profile, ignore_errors=True)


def _capture_slow(html: str, out_dir: str, times: list[float], scale: float,
                  progress=None) -> list[str]:
    """慢路径：一帧开一个 Chrome。缺 websockets / CDP 起不来时用。

    保留它的意义不是「一样好」，而是**别把用户堵死** —— 装上 websockets 就快 51 倍，
    但没装也得能出片。所以它会把代价说清楚，不静默地慢。
    """
    frames = []
    for i, t in enumerate(times):
        path = os.path.join(out_dir, f"f{i:05d}.png")
        url = f"file://{os.path.abspath(html)}#deckt={t:.6f}"
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        f"--force-device-scale-factor={scale}",
                        f"--window-size={SLIDE_W},{SLIDE_H}",
                        f"--screenshot={path}", url],
                       check=True, capture_output=True)
        frames.append(path)
        if progress:
            progress(i + 1, len(times))
    return frames


# ── 编码 ────────────────────────────────────────────────────────────────────
def _resize_all(frames: list[str], width: int, height: int) -> list[str]:
    """把帧统一缩到目标宽度（超采样降采样 = 文字更锐）。

    尺寸已经对了就**不碰** —— 降采样是整条链路里最贵的一步（实测 777 帧要两分多钟），
    而 `--scale 1` 时它本来就不需要。
    """
    from PIL import Image   # noqa: PLC0415

    out = []
    for p in frames:
        im = Image.open(p)
        if im.size != (width, height):
            im.convert("RGB").resize((width, height), Image.Resampling.LANCZOS).save(p)
        out.append(p)
    return out


def encode_mp4(frames: list[str], out: str, fps: int) -> None:
    binary = _encode_binary()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(os.path.abspath(p) for p in frames))
        listing = fh.name
    try:
        proc = subprocess.run([binary, os.path.abspath(out), str(fps), listing],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(f"✗ H.264 编码失败：\n{(proc.stderr or proc.stdout).strip()[:600]}")
    finally:
        os.unlink(listing)


def encode_gif(frames: list[str], out: str, fps: int) -> None:
    """GIF：**共享调色板** + 抖动。

    为什么不能每帧各自量化：每帧一张 256 色表，帧间的表不一样 → 播放时整片**闪色**。
    正确做法是先跨帧建一张全局表（从中等间隔采样几帧拼一张图去量化），所有帧都用它。
    这就是「palette 优化」的实际含义，不是加个 optimize=True 就完了。
    """
    from PIL import Image   # noqa: PLC0415

    imgs = [Image.open(p).convert("RGB") for p in frames]
    step = max(1, len(imgs) // 12)
    samples = imgs[::step][:12]
    sw = max(1, samples[0].width // 4)
    sh = max(1, samples[0].height // 4)
    montage = Image.new("RGB", (sw * len(samples), sh))
    for i, im in enumerate(samples):
        montage.paste(im.resize((sw, sh), Image.Resampling.LANCZOS), (i * sw, 0))
    palette = montage.quantize(colors=256, method=Image.Quantize.MEDIANCUT)

    quantized = [im.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG)
                 for im in imgs]
    duration = max(20, round(1000 / fps))       # GIF 的 duration 是毫秒整数
    quantized[0].save(out, save_all=True, append_images=quantized[1:],
                      duration=duration, loop=0, optimize=True,
                      disposal=2)               # disposal=2：每帧前清底，避免残影


def inspect_media(path: str, fps: int) -> dict:
    """验产物 —— 不看命令返回 0，看文件里到底是什么。"""
    size = os.path.getsize(path)
    info: dict = {"bytes": size, "ext": os.path.splitext(path)[1].lower()}
    if info["ext"] == ".mp4":
        raw = deckio.read_bytes(path)
        info["mp4_magic"] = raw[4:8] == b"ftyp"
        # 用 avconvert 读一遍：读得动 = 容器合法（它读不动会退非 0）
        probe_out = os.path.join(tempfile.gettempdir(), f"_probe_{os.getpid()}.mov")
        probe = subprocess.run(["avconvert", "--source", os.path.abspath(path),
                                "--preset", "PresetPassthrough", "--output", probe_out],
                               capture_output=True, text=True)
        info["container_ok"] = probe.returncode == 0
        deckio.remove(probe_out)
    else:
        raw = deckio.read_bytes(path)
        info["gif_magic"] = raw[:6] in (b"GIF87a", b"GIF89a")
        from PIL import Image   # noqa: PLC0415

        with Image.open(path) as im:
            info["gif_size"] = im.size
            # ⚠️ 帧数**不等于**标称帧数：Pillow 会把连续相同的帧合成一帧并延长时长
            # （停顿段帧帧一样，全并了）。实测 777 帧写出 160 帧，而**时长是对的**。
            # 所以真正的检查是**总时长** —— 盯帧数只会得到一个假的失败。
            total_ms = 0
            try:
                for i in range(getattr(im, "n_frames", 1)):
                    im.seek(i)
                    total_ms += im.info.get("duration", 0)
            except EOFError:
                pass
            info["gif_frames"] = getattr(im, "n_frames", 1)
            info["gif_ms"] = total_ms
    return info


def _capture(html: str, work: str, times: list[float], scale: float,
             force_slow: bool, progress=None) -> list[str]:
    """取帧的入口：优先 CDP，不行就降级并**把代价说清楚**。

    降级不是“静默地慢”：先告诉用户慢多少、以及怎么变快（装 websockets）。
    堵死用户的导出比慢一点更不可接受。
    """
    if force_slow:
        print("· 慢路径：一帧一个 Chrome（约 2.4s/帧 —— 排查 CDP 问题时用）")
        return _capture_slow(html, work, times, scale, progress)
    try:
        return asyncio.run(_capture_async(html, work, times, scale, progress))
    except RuntimeError as exc:
        if "no-websockets" not in str(exc):
            raise
        est = len(times) * 2.45 / 60
        print(f"⚠ 没装 websockets，CDP 走不了 → 降级成慢路径（约 {est:.0f} 分钟）。\n"
              f"  装上它快 51 倍：pip install websockets")
        return _capture_slow(html, work, times, scale, progress)


def _parse_times(raw: str) -> list[float]:
    """`0,2.5,10` → [0.0, 2.5, 10.0]。格式不对要说清楚哪里不对。"""
    out = []
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        try:
            out.append(float(part))
        except ValueError as exc:
            raise SystemExit(f"✗ --stills 里有个时间点不是数字：{part!r}") from exc
    if not out:
        raise SystemExit("✗ --stills 是空的（写成如 0,2.5,10）")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="out.html → MP4 / GIF（逐帧 seek 渲染）")
    ap.add_argument("html")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--fps", type=int, default=24,
                    help="帧率（默认 24；60 靠复制帧，兼容性比插帧好）")
    ap.add_argument("--scale", type=float, default=0,
                    help="取帧的像素密度倍率（默认自动 = 输出宽/1600 —— 这样 Chrome "
                         "直接按目标尺寸光栅化，不需要降采样那一道，快很多也够锐）。"
                         "想要超采样（更平滑的边缘）就显式给 2")
    ap.add_argument("--width", type=int, default=0,
                    help="输出宽度（默认 MP4 1920 / GIF 960）。高度按 16:9 算")
    ap.add_argument("--keep-frames", action="store_true",
                    help="保留 PNG 帧序列（不绑编码器 —— 你可以自己拿 ffmpeg 编）")
    ap.add_argument("--slow", action="store_true",
                    help="强制走慢路径（一帧一个 Chrome），用于排查 CDP 问题")
    ap.add_argument("--stills", default="",
                    help="只抽这几个时间点（逗号分隔的秒）存 PNG 不编码 —— "
                         "交付前用它抽第 0 帧/末帧/每个切点验一遍")
    args = ap.parse_args(argv[1:])

    is_gif = args.out.lower().endswith(".gif")
    width = args.width or (960 if is_gif else 1920)
    width -= width % 2                       # H.264 要偶数
    height = round(width * SLIDE_H / SLIDE_W / 2) * 2
    fps = 24 if is_gif else args.fps
    # 默认让 Chrome 直接按输出尺寸光栅化（DPR = 输出宽/1600），而不是 2x 取完再降采样。
    # 实测 777 帧下，降采样那一道要两分多钟；而 DPR 直接到目标尺寸时文字是
    # **按最终尺寸重新光栅化**的（不是把位图放大），所以既快又不糊。
    scale = args.scale or (width / SLIDE_W)

    render = _load_sibling("render")
    spec = None
    for candidate in (args.html + ".spec.json",):
        if os.path.isfile(candidate):
            spec = deckio.read_json(candidate)
    if spec is None:
        # 时间轴在渲染期就写进产物了，直接从产物里读 —— 不要求用户再给一份 spec
        html_text = deckio.read_text(args.html)
        marker = "window.__deck_timeline="
        m = html_text.find(marker)
        if m < 0:
            raise SystemExit("✗ 产物里没有时间轴 —— 这是新版 render.py 出的 HTML 吗？")
        tail = html_text[m + len(marker):]
        try:
            spans = json.loads(tail[:tail.index(";")])
        except (ValueError, json.JSONDecodeError) as exc:
            raise SystemExit(f"✗ 产物里的时间轴读不出来（产物损坏？）：{exc}") from exc
        total = spans[-1]["start"] + spans[-1]["enter"] + spans[-1]["hold"]
    else:
        style = render.load_style(spec["deck"].get("style", render.DEFAULT_STYLE))
        total = render.total_duration(spec["deck"], style["tokens"])

    print(f"· 时间轴总长 {total:.2f}s @ {fps}fps → {max(2, round(total * fps))} 帧"
          f"（{SLIDE_W}×{SLIDE_H} × DPR {scale:g} → {width}×{height}）")

    work = tempfile.mkdtemp(prefix="deck-frames-")
    started = time.time()

    def progress(done: int, n: int) -> None:
        if done % 24 == 0 or done == n:
            el = time.time() - started
            eta = (el / done) * (n - done) if done else 0
            print(f"  取帧 {done}/{n}（{el:.0f}s，剩 ~{eta:.0f}s）", flush=True)

    try:
        if args.stills:
            # 抽帧检查：走**同一条**取帧路径（所以“看到的”就是“录进去的”），
            # 只是不编码。huashu 的交付清单就要求抽第 0 帧 + 末帧验证。
            stills_dir = args.out + ".stills"
            deckio.ensure_dir(stills_dir)
            times = _parse_times(args.stills)
            frames = _capture(args.html, work, times, scale, args.slow, progress)
            saved = []
            for t, p in zip(times, frames):
                dst = os.path.join(stills_dir, f"t{t:07.2f}.png")
                deckio.copy(p, dst)
                saved.append(dst)
            print(f"✓ 抽出 {len(saved)} 帧 → {stills_dir}")
            for dst in saved:
                print("   ", dst)
            return 0
        times = [i / fps for i in range(max(2, round(total * fps)))]
        frames = _capture(args.html, work, times, scale, args.slow, progress)
        frames = _resize_all(frames, width, height)
        if is_gif:
            encode_gif(frames, args.out, fps)
        else:
            encode_mp4(frames, args.out, fps)
    finally:
        if not args.keep_frames:
            import shutil   # noqa: PLC0415
            shutil.rmtree(work, ignore_errors=True)

    info = inspect_media(args.out, fps)
    ok = (info.get("mp4_magic") or info.get("gif_magic")) and info["bytes"] > 4096
    print(f"{'✓' if ok else '✗'} {args.out}")
    print(f"  {width}×{height} / {fps}fps / {info['bytes'] / 1048576:.2f}MB / "
          f"{time.time() - started:.0f}s")
    if is_gif:
        want_ms = round(total * 1000)
        got_ms = info.get("gif_ms", 0)
        drift = abs(got_ms - want_ms)
        print(f"  GIF {info.get('gif_frames', 0)} 帧 / 时长 {got_ms / 1000:.2f}s"
              f"（应 {total:.2f}s，差 {drift / 1000:.2f}s）"
              f"{'  ✓' if drift <= 200 else '  ✗ 时长不对'}")
        ok = ok and drift <= 200
    else:
        print(f"  容器校验：{'✓ 通过' if info.get('container_ok') else '✗ 读不动'}"
              f"（用系统 avconvert 回读一遍，不是只看命令返回 0）")
    if args.keep_frames:
        print(f"  PNG 帧序列保留在：{work}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
