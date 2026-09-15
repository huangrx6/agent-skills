#!/usr/bin/env python3
"""交付演练 —— 一条命令把整条链跑完，并把"打开看"变成一张对比图 + 一组可判事实。

## 为什么需要它

单件都有测试，**但"串起来"是另一回事**。2026-09-15 那次演练用九条命令手工跑完整条链，
抓到的三个真 bug 全部只在"把产物打开看"时才露出来：

  · 原生 PPTX 没写 `<a:ea>`（东亚字体）→ 汉字全由宿主软件自选，等于整个风格被换掉
  · 标题字重写死成 bold → 两套 400 字重的风格在设计上被抹掉
  · 原生图表跟着宿主模板画 → 多了网格线、柱子上没有数值（和我们的设计正好相反）

三条的共性是**最毒的那种**：文件生成成功、页数正确、文本数正确 —— 机器能判的全是绿的。
所以这个工具做两件机器做不了的事：把四个版本并排摆出来，**并且**量一下它们差多少。

## 它做什么

1. 跑完整条链（渲染 → 校验 → PDF → 逐页 PNG → 两种 PPTX →（可选）视频）
2. 对指定的几页，把 **HTML / PDF / 原生 PPTX** 三个版本各渲一张图，拼成对比表
3. 把每个版本与 HTML **逐像素比**，报差异百分比
   （PDF 应当几乎一致 —— 同一个 DOM，只有打印 CSS 的差异；原生 PPTX 是**重画**的，
   差异天然大，所以它只报数不判失败）
4. 汇总每件产物的事实（页数 / 尺寸 / 位图 / 字体 / 文本数）

## 为什么"渲第 N 页"要造一份单页 deck

`sips` 与 `qlmanage` 都只能给 PDF 的**第一页**，Chrome headless 又不带 PDF 阅读器
（实测：截出来是一片空白）。所以取某一页的办法是**造一份只含那一页的 deck**再导。
这对本项目成立：每页都是独立的 `<section>`，打印 CSS 也是逐页生效的。

跑法：
    python3 scripts/deliver.py your.spec.json --out /tmp/deliver --pages 1,9,12
    python3 scripts/deliver.py your.spec.json --video        # 连视频一起（慢，几分钟）
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
SCRIPTS = HERE

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SOFFICE = shutil.which("soffice") or "/opt/homebrew/bin/soffice"
SIPS = "/usr/bin/sips"

# 与 HTML 逐像素比的容忍线。
#
# 为什么 PDF 可以卡得很紧：它和 HTML 是**同一个 DOM** 出的，差异只有打印 CSS 那几处
# （颗粒关掉、页尺寸换成 1200×675pt），加上抗锯齿。实测值见 README 那张表——
# 阈值是量出来之后定的，不是先拍一个。
PDF_TOLERANCE = 8.0        # 平均绝对差（%）。超了说明打印路径真的改了版面
PPTX_NATIVE_TOLERANCE = 40.0   # 原生版是重画的，只用来抓"整体崩了"（少了一半内容之类）


def _load(name: str):
    path = os.path.join(SCRIPTS, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"_deck_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载不了同目录模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


deckio = _load("deckio")
render = _load("render")


def run_step(label: str, argv: list[str], cwd: str) -> tuple[int, str]:
    """跑一步流水线，把它的输出原样带回来（不吞掉 —— 那些输出里就是事实）。"""
    print(f"\n──── {label}")
    proc = subprocess.run([sys.executable] + argv, capture_output=True, text=True, cwd=cwd)
    out = (proc.stdout + proc.stderr).strip()
    if out:
        print(out)
    return proc.returncode, out


def one_page_spec(spec: dict, page: int, tmp: str) -> str:
    """造一份只含第 N 页的 deck（给"取某一页的画面"用）。

    为什么不直接切 PDF：`sips`/`qlmanage` 都只给第一页，Chrome headless 不带 PDF
    阅读器（实测截出来一片空白）。而每页本来就是独立的 `<section>`，
    打印 CSS 也逐页生效 —— 所以"单页 deck"与"整份的第 N 页"在版面上一回事。
    """
    out_spec = copy.deepcopy(spec)
    slides = out_spec["deck"]["slides"]
    if not 1 <= page <= len(slides):
        raise SystemExit(f"✗ --pages {page} 越界：这份 deck 只有 {len(slides)} 页")
    out_spec["deck"]["slides"] = [slides[page - 1]]
    path = os.path.join(tmp, f"page{page}.spec.json")
    deckio.write_text(path, __import__("json").dumps(out_spec, ensure_ascii=False, indent=2))
    return path


def ensure_images(spec: dict, tmp: str, allow_placeholder: bool = False) -> None:
    """缺必需图 = **ERROR**（required asset missing），不再默认造合成测试卡。

    规则口径（总编排 §14/§15）：缺图联网找图禁止、静默造占位同样禁止 ——
    "占位图滑进最终交付"是迟早的事。补图三选一：真照片放进产物目录 /
    `image_source.py` 按槽位出图合同再生成 / 演练空跑显式 `--allow-placeholder`
    （造出来的测试卡仍会大声提醒"这不是内容"）。
    """
    needed = {s.get("image") for s in spec["deck"].get("slides", []) if s.get("image")}
    missing = sorted(str(n) for n in needed
                     if not os.path.isfile(os.path.join(tmp, str(n))))
    if missing and not allow_placeholder:
        raise SystemExit(
            "✗ 缺必需图片（required asset missing = ERROR，不造占位）：\n"
            + "".join(f"    · {n}\n" for n in missing)
            + "  补图：真照片放进产物目录，或 image_source.py 按槽位出图合同生成；\n"
            + "  交付演练要空跑流程，显式加 --allow-placeholder（合成测试卡会大声提醒）")
    for name in missing:
        target = os.path.join(tmp, str(name))
        print(f"\n──── 造图（占位）：{name}")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "plate.py"), "--sample", "-o", target],
            capture_output=True, text=True)
        print((proc.stdout + proc.stderr).strip())
        if proc.returncode != 0:
            print(f"  ✗ 造图失败：{name} 会是一张裂图")
        else:
            print(f"  ⚠️ 这是**合成测试卡**，不是内容 —— 真交付要用真照片替掉它"
                  f"（`image_source.py` 或直接换文件）")


def render_variants(page: int, spec: dict, html: str, tmp: str, shots_png: str) -> dict:
    """一页的三个版本：HTML（现成的截图）/ 打印 PDF / 原生 PPTX。

    · 打印 PDF：从**整份** HTML 里只打印第 N 页（页码保持原样，见 `_print_one`）
    · 原生 PPTX：只能造一份**单页 deck**（导出器按整份产物一次成型），
      所以那一栏的页脚与巨号页码会是 `01` —— 这是**取材方式的产物**，不是缺陷，
      对比图上会标注。
    """
    variants = {"html": shots_png}
    print_path = os.path.join(tmp, f"page{page}-print.png")
    _print_one(html, page, print_path, tmp)
    if os.path.isfile(print_path):
        variants["pdf"] = print_path

    one_spec = one_page_spec(spec, page, tmp)
    one_html = os.path.join(tmp, f"page{page}.html")
    code, _ = run_step(f"第 {page} 页：渲染单页产物（给原生 PPTX 用）",
                       [os.path.join(SCRIPTS, "render.py"), one_spec, "-o", one_html], tmp)
    if code != 0:
        return variants
    native_png = os.path.join(tmp, f"page{page}-native.png")
    _native_one(one_html, page, native_png, tmp)
    if os.path.isfile(native_png):
        variants["native"] = native_png
    return variants


def _print_one(html: str, page: int, out_png: str, tmp: str) -> None:
    """**整份 HTML** 里只打印第 N 页 → PDF → PNG。

    为什么不是"造一份单页 deck 再打印"：那样第 N 页会变成第 1 页，于是页脚与右脚那个
    巨号页码都成了 `01` —— 对照图里就出现"HTML 写着 03、PDF 写着 01"的假差异
    （实测踩过：对比图一眼就看出来了，而逐像素差只有 0.3% 没报警）。

    做法是往产物副本里加一段**只在打印时生效**的 CSS：藏掉其余页、只留
    `[data-slide="N"]`。这样页码、编号这些**由页面序号派生的东西**全部保持原样，
    打出来又确实只有一页。顺便把 `page-break-after` 关掉，免得尾巴多出一张空页。
    """
    page_html = os.path.join(tmp, f"only-{page}.html")
    override = (
        "<style>@media print{"
        ".slide{display:none !important}"
        f'.slide[data-slide="{page}"]{{display:block !important;'
        "page-break-after:auto !important;break-after:auto !important}"
        "}</style>")
    text = deckio.read_text(html)
    deckio.write_text(page_html, text.replace("</head>", override + "</head>", 1))
    pdf = out_png.replace(".png", ".pdf")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", f"file://{os.path.abspath(page_html)}"],
                   capture_output=True, check=False, timeout=120)
    if not os.path.isfile(pdf):
        return
    subprocess.run([SIPS, "-s", "format", "png", pdf, "--out", out_png],
                   capture_output=True, check=False, timeout=60)


def _native_one(html: str, page: int, out_png: str, tmp: str) -> None:
    """单页 HTML → 原生 PPTX →（LibreOffice）PDF → PNG。

    soffice 不在就**跳过并说明** —— 它是"能不能看图"的依赖，不是流水线的依赖，
    缺了不该让整次演练失败。
    """
    if not os.path.isfile(SOFFICE):
        print(f"  · 没有 LibreOffice（{SOFFICE}）→ 跳过原生 PPTX 的画面比对"
              f"（文件仍然生成了，只是这一栏看不到）")
        return
    pptx = os.path.join(tmp, f"page{page}-native.pptx")
    code, _ = run_step(f"第 {page} 页：原生 PPTX",
                       [os.path.join(SCRIPTS, "pptx_native.py"), html, "-o", pptx], tmp)
    if code != 0:
        return
    outdir = os.path.join(tmp, f"lo{page}")
    subprocess.run([SOFFICE, "--headless",
                    f"-env:UserInstallation=file://{os.path.join(tmp, f'profile{page}')}",
                    "--convert-to", "pdf", "--outdir", outdir, pptx],
                   capture_output=True, check=False, timeout=180)
    made = os.path.join(outdir, os.path.basename(pptx).replace(".pptx", ".pdf"))
    if os.path.isfile(made):
        subprocess.run([SIPS, "-s", "format", "png", made, "--out", out_png],
                       capture_output=True, check=False, timeout=60)


def fidelity(a: str, b: str, size: tuple[int, int] = (800, 450)) -> float:
    """两个版本的平均绝对差（%）。0 = 逐像素一致。

    比之前**都缩到同一尺寸**：HTML 截图是 2x（3200×1800），PDF 出来是 1200×675，
    不归一化就没法比。缩放的抗锯齿本身会带来一点差，所以容忍线不是 0（见常量注释）。

    差异用**直方图**算而不是 `getdata()` 逐像素求和：后者在 PIL 的类型标注里是
    `float | tuple | None` 的联合，静态层面过不去；而直方图是 256 个整数桶，
    求和快得多，结果一样（先转 L 取亮度）。
    """
    from PIL import Image, ImageChops   # noqa: PLC0415

    with Image.open(a) as ia, Image.open(b) as ib:
        pa = ia.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        pb = ib.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        diff = ImageChops.difference(pa, pb).convert("L")
        hist = diff.histogram()          # 256 个桶
    pixels = sum(hist)
    if not pixels:
        return 0.0
    total = sum(level * count for level, count in enumerate(hist))
    return total / (pixels * 255) * 100.0


def contact_sheet(path: str, rows: list[tuple[str, dict]]) -> str:
    """每页一行：HTML / 打印 PDF / 原生 PPTX 三栏并排。"""
    from PIL import Image, ImageDraw   # noqa: PLC0415

    tw, th, pad, head = 620, 349, 14, 30
    cols = 3
    width = pad * 2 + tw * cols + 12 * (cols - 1)
    height = pad + (head + th + 16) * len(rows)
    board = Image.new("RGB", (width, height), (20, 20, 22))
    draw = ImageDraw.Draw(board)
    labels = (("HTML（屏幕，基准）", "html"), ("打印 PDF（第 N 页）", "pdf"),
              ("原生 PPTX（单页版 → 页码显示 01）", "native"))
    for i, (title, variants) in enumerate(rows):
        y = pad + i * (head + th + 16)
        draw.text((pad, y + 8), title, fill=(235, 235, 235))
        for k, (label, key) in enumerate(labels):
            x = pad + k * (tw + 12)
            draw.text((x, y + 8 + head - 14), label, fill=(150, 150, 155))
            src = variants.get(key)
            if not src or not os.path.isfile(src):
                continue
            with Image.open(src) as im:
                board.paste(im.convert("RGB").resize((tw, th), Image.Resampling.LANCZOS),
                            (x, y + head + 14))
    board.save(path)
    return path


def parse_pages(text: str) -> list[int]:
    """`1,9,12` → [1, 9, 12]。写错就报清楚，不甩 traceback。"""
    out: list[int] = []
    for raw in re.split(r"[,\s]+", text.strip()):
        if not raw:
            continue
        try:
            out.append(int(raw))
        except ValueError as exc:
            raise SystemExit(f"✗ --pages 要是逗号分隔的页号：{raw!r} 不是数字") from exc
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="交付演练：整条链跑一遍 + 画面与像素比对")
    ap.add_argument("spec")
    ap.add_argument("--out", default=None, help="产物目录（缺省：系统临时目录）")
    ap.add_argument("--pages", default="1", help="要比对画面的页，逗号分隔（缺省 1）")
    ap.add_argument("--video", action="store_true", help="连 MP4 一起出（慢，几分钟）")
    ap.add_argument("--json", action="store_true", help="末尾输出机读小结")
    ap.add_argument("--allow-placeholder", action="store_true",
                    help="缺图时造合成测试卡继续演练（默认：缺图 = ERROR —— "
                         "占位图滑进交付是迟早的事，要空跑就显式选入）")
    args = ap.parse_args(argv[1:])

    spec = deckio.read_json(args.spec)
    tmp = args.out or tempfile.mkdtemp(prefix="deck-deliver-")
    deckio.ensure_dir(tmp)
    print(f"交付演练 · 产物目录 {tmp}")

    facts: dict[str, str] = {}
    failures: list[str] = []

    # ── 1. 走完流水线（命令与文档里的"交付演练"一节逐字一致）───────────────
    code, _ = run_step("规格", [os.path.join(SCRIPTS, "validate_spec.py"), args.spec], tmp)
    if code != 0:
        return 1
    html = os.path.join(tmp, "out.html")
    ensure_images(spec, tmp, allow_placeholder=args.allow_placeholder)
    code, _ = run_step("渲染", [os.path.join(SCRIPTS, "render.py"), args.spec, "-o", html], tmp)
    if code != 0:
        return 1
    code, out = run_step("校验", [os.path.join(SCRIPTS, "check.py"), args.spec, html], tmp)
    if code != 0:
        # 校验不过就别导出了 —— 把一份"已知有问题"的 deck 做成五种格式只是把问题复制五份
        print("\n✗ 校验没过，演练中止（先把 check 的问题修掉，再来看导出）")
        return 1

    total = len(spec["deck"]["slides"])
    code, out = run_step("矢量 PDF", [os.path.join(SCRIPTS, "pdf.py"), html,
                                    "-o", os.path.join(tmp, "deck.pdf")], tmp)
    facts["pdf"] = " / ".join(out.split("\n")[1:3]) if code == 0 else "✗ 失败"
    if code != 0:
        failures.append("矢量 PDF 导出失败")

    code, out = run_step("逐页 PNG", [os.path.join(SCRIPTS, "shots.py"), html,
                                    "--out-dir", os.path.join(tmp, "pages"),
                                    "--count", str(total)], tmp)
    shots_dir = os.path.join(tmp, "pages")
    code, out = run_step("贴图版 PPTX", [os.path.join(SCRIPTS, "make_pptx.py"),
                                      "--png-dir", shots_dir,
                                      "-o", os.path.join(tmp, "deck.pptx")], tmp)
    facts["pptx(贴图)"] = out.split("\n")[-1] if code == 0 else "✗ 失败"

    code, out = run_step("原生 PPTX", [os.path.join(SCRIPTS, "pptx_native.py"), html,
                                     "-o", os.path.join(tmp, "deck-editable.pptx")], tmp)
    facts["pptx(原生)"] = " / ".join(out.split("\n")[-3:-1]) if code == 0 else "✗ 失败"
    if code != 0:
        failures.append("原生 PPTX 导出失败")

    if args.video:
        code, out = run_step("视频 MP4", [os.path.join(SCRIPTS, "animate.py"), html,
                                        "-o", os.path.join(tmp, "deck.mp4")], tmp)
        facts["mp4"] = " / ".join(out.strip().split("\n")[-2:]) if code == 0 else "✗ 失败"

    # ── 2. 画面比对 + 逐像素差 ────────────────────────────────────────────
    pages = parse_pages(args.pages)
    rows: list[tuple[str, dict]] = []
    diffs: dict[str, list[tuple[int, float]]] = {"pdf": [], "native": []}
    for page in pages:
        shots_png = os.path.join(shots_dir, f"page-{page:02d}.png")
        if not os.path.isfile(shots_png):
            print(f"  · 第 {page} 页的截图不在（{shots_png}）→ 跳过")
            continue
        variants = render_variants(page, spec, html, tmp, shots_png)
        for key in ("pdf", "native"):
            if key in variants:
                d = fidelity(shots_png, variants[key])
                diffs[key].append((page, d))
        rows.append((f"第 {page} 页 · {spec['deck']['slides'][page - 1].get('title', '')}",
                     variants))

    print("\n──── 与 HTML 的逐像素差（平均绝对差 %，越小越一致）")
    for key, label, tol in (("pdf", "打印 PDF", PDF_TOLERANCE),
                            ("native", "原生 PPTX", PPTX_NATIVE_TOLERANCE)):
        if not diffs[key]:
            continue
        for page, d in diffs[key]:
            mark = "✓" if d <= tol else ("✗" if key == "pdf" else "⚠")
            print(f"  {mark} 第 {page:>2} 页 {label:<10} {d:5.1f}%")
        worst = max(d for _p, d in diffs[key])
        if key == "pdf" and worst > tol:
            failures.append(f"打印 PDF 与屏幕差 {worst:.1f}%（容忍 {tol}%）—— 打印路径改了版面")

    if rows:
        sheet = contact_sheet(os.path.join(tmp, "compare.png"), rows)
        print(f"\n✓ 对比图 → {sheet}")

    print("\n──── 产物")
    for name, desc in facts.items():
        print(f"  {name:<12}{desc}")

    if args.json:
        import json   # noqa: PLC0415

        print(json.dumps({"out": tmp, "facts": facts, "failures": failures,
                          "diffs": {k: [[p, round(d, 2)] for p, d in v]
                                    for k, v in diffs.items()}},
                         ensure_ascii=False, indent=2))
    if failures:
        print("\n✗ " + "；".join(failures))
        return 1
    print("\n✓ 演练通过（校验 / 五种产物 / 画面与像素比对）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
