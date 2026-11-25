# 自动化验收脚本模式库

以下 4 套 Python Playwright 实战脚本模式均遵循「黑盒、同步、先侦察后操作、全链路监听、安全回收资源」工程纪律。运行时优先通过 `scripts/with_server.py` 托管本地服务生命周期，将临时截图与日志写入隔离的临时目录（如 `/tmp/qa-artifacts/`），绝不污染业务源码树。

---

## 模式 1：Console / PageError / Network 全链路监听采集器

一切动态页面黑盒验收的标配基座：在首次 `page.goto()` 之前绑定 `console`、`pageerror`、`response` 与 `requestfailed`，把运行时噪音与报错完整落盘，杜绝口头宣称「控制台没报错」。

```python
# 保存示例：/tmp/qa_console_net.py
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:5173"
OUT_DIR = Path("/tmp/qa-artifacts")
OUT_DIR.mkdir(parents=True, exist_ok=True)

console_records: list[str] = []
console_errors: list[str] = []
page_errors: list[str] = []
failed_responses: list[str] = []
request_failures: list[str] = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    try:
        # 1) 导航前先挂载四类监听通道
        def on_console(msg):
            line = f"[{msg.type}] {msg.text}"
            console_records.append(line)
            if msg.type == "error":
                console_errors.append(line)

        def on_pageerror(err):
            page_errors.append(str(err))

        def on_response(resp):
            if resp.status >= 400:
                failed_responses.append(f"{resp.request.method} {resp.url} -> {resp.status}")

        def on_requestfailed(req):
            failure = req.failure or "unknown"
            request_failures.append(f"{req.method} {req.url} -> FAILED ({failure})")

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)
        page.on("response", on_response)
        page.on("requestfailed", on_requestfailed)

        # 2) 打开页面并等待渲染稳定
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        # 3) 执行真实用户交互（替换为实际语义定位器）
        dashboard_btn = page.get_by_role("link", name="Dashboard")
        if dashboard_btn.count() > 0 and dashboard_btn.first.is_visible():
            dashboard_btn.first.click()
            page.wait_for_load_state("networkidle")

        page.screenshot(path=str(OUT_DIR / "after-nav.png"), full_page=True)
    finally:
        context.close()
        browser.close()

# 4) 落盘原始日志并输出结构化摘要
(OUT_DIR / "console.log").write_text("\n".join(console_records), encoding="utf-8")
print(f"Console 总计: {len(console_records)} | Error: {len(console_errors)}")
print(f"PageError: {len(page_errors)} | HTTP>=400: {len(failed_responses)} | RequestFailed: {len(request_failures)}")
for item in console_errors + page_errors + failed_responses + request_failures:
    print("  [ALERT]", item)
```

---

## 模式 2：页面元素与交互控件自动侦察脚本

严格执行「先侦察，再操作」：在编写任何业务流程断言前，先等待动态渲染稳定，自动扫描当前页面上的真实可见按钮、链接、表单输入、标题层级与缺失可访问名称的控件，并导出基线全页截图。

```python
# 保存示例：/tmp/qa_recon.py
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:5173"
OUT_DIR = Path("/tmp/qa-artifacts")
OUT_DIR.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    try:
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        print(f"Title: {page.title()} | URL: {page.url}")

        # 1) 侦察标题层级
        headings = page.locator("h1, h2, h3").all()
        print(f"\nFound {len(headings)} headings:")
        for h in headings[:15]:
            if h.is_visible():
                tag = h.evaluate("el => el.tagName.toLowerCase()")
                print(f"  <{tag}> {h.inner_text().strip()}")

        # 2) 侦察所有按钮（区分可见 / 隐藏，顺带暴露无文本且无 aria-label 的图标按钮）
        buttons = page.locator("button, [role='button']").all()
        print(f"\nFound {len(buttons)} buttons:")
        for idx, btn in enumerate(buttons):
            if not btn.is_visible():
                continue
            text = btn.inner_text().strip().replace("\n", " ")
            aria = btn.get_attribute("aria-label") or ""
            label = text or (f"[aria:{aria}]" if aria else "[MISSING_LABEL]")
            disabled = " (disabled)" if not btn.is_enabled() else ""
            print(f"  [{idx}] {label}{disabled}")

        # 3) 侦察链接
        links = page.locator("a[href]").all()
        print(f"\nFound {len(links)} links (showing visible up to 15):")
        shown = 0
        for link in links:
            if not link.is_visible():
                continue
            print(f"  - {link.inner_text().strip() or '[icon-link]'} -> {link.get_attribute('href')}")
            shown += 1
            if shown >= 15:
                break

        # 4) 侦察表单输入控件
        inputs = page.locator("input:not([type='hidden']), textarea, select").all()
        print(f"\nFound {len(inputs)} form controls:")
        for elem in inputs:
            if not elem.is_visible():
                continue
            name = elem.get_attribute("name") or elem.get_attribute("id") or "[unnamed]"
            ctrl_type = elem.get_attribute("type") or elem.evaluate("el => el.tagName.toLowerCase()")
            placeholder = elem.get_attribute("placeholder") or ""
            aria = elem.get_attribute("aria-label") or ""
            print(f"  - {name} ({ctrl_type}) placeholder={placeholder!r} aria-label={aria!r}")

        # 5) 导出基线全页截图供目检
        shot = OUT_DIR / "recon-baseline.png"
        page.screenshot(path=str(shot), full_page=True)
        print(f"\nBaseline screenshot saved: {shot}")
    finally:
        context.close()
        browser.close()
```

---

## 模式 3：静态 HTML 本地页自动化验收模板

适用于纯静态页面、文档页或本地生成产物。使用 `Path(...).resolve().as_uri()` 安全生成跨平台 `file://` 地址；若页面含 ES Module（`<script type="module">`）、相对根路径 `/assets/...` 或 `fetch()` 请求，则改用 `scripts/with_server.py` 配合 `python3 -m http.server` 启动本地 HTTP 服务再跑验收。

```python
# 保存示例：/tmp/qa_static_html.py
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML_PATH = Path("path/to/your/index.html").resolve()
OUT_DIR = Path("/tmp/qa-artifacts/static")
OUT_DIR.mkdir(parents=True, exist_ok=True)

console_errors: list[str] = []
page_errors: list[str] = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    try:
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        page.goto(HTML_PATH.as_uri(), wait_until="load")
        page.screenshot(path=str(OUT_DIR / "before-submit.png"), full_page=True)

        # 基于语义定位器执行交互与表单提交
        page.get_by_label("姓名").fill("张三 Enterprise_QA_User")
        page.get_by_label("邮箱").fill("qa@example.com")
        page.get_by_role("button", name="提交").click()

        # 等待结果节点稳定而非盲目 sleep
        page.get_by_role("status").wait_for(state="visible", timeout=5000)
        page.screenshot(path=str(OUT_DIR / "after-submit.png"), full_page=True)

        # 核对无横向溢出与无坏图
        overflow = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
        broken_imgs = page.evaluate(
            "() => Array.from(document.images).filter(i => i.complete && i.naturalWidth === 0).length"
        )
        assert not overflow, "静态页出现横向溢出"
        assert broken_imgs == 0, f"发现 {broken_imgs} 张坏图"
        assert not console_errors and not page_errors, f"运行时报错: {console_errors + page_errors}"
        print("Static HTML QA passed.")
    finally:
        context.close()
        browser.close()
```

---

## 模式 4：动态 SPA 多视口、状态复位与并发 5 连击验收骨架

配合 `scripts/with_server.py` 一起执行，示范如何把「多视口几何扫描 + 切页/关闭状态复位 + 并发 5 连击防重」收敛到一份干净可复现的验收脚本中：

```python
# 运行示例：
# python3 skills/ui-qa-acceptance/scripts/with_server.py \
#   --server "pnpm run dev -- --port 5173" --port 5173 --path / \
#   -- python3 /tmp/qa_spa_stress.py

from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:5173"
OUT_DIR = Path("/tmp/qa-artifacts/spa")
OUT_DIR.mkdir(parents=True, exist_ok=True)
VIEWPORTS = [
    ("desktop", {"width": 1440, "height": 900}),
    ("narrow", {"width": 900, "height": 620}),
    ("short", {"width": 1280, "height": 560}),
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport=VIEWPORTS[0][1])
    page = context.new_page()

    errors: list[str] = []
    post_count = 0

    try:
        page.on("console", lambda m: errors.append(f"console:{m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror:{e}"))
        page.on("response", lambda r: errors.append(f"http:{r.status}:{r.url}") if r.status >= 400 else None)

        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        # 1) 多视口横向溢出巡检
        for label, vp in VIEWPORTS:
            page.set_viewport_size(vp)
            overflow_px = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            page.screenshot(path=str(OUT_DIR / f"viewport-{label}.png"))
            assert overflow_px <= 1, f"[{label}] 横向溢出 {overflow_px}px"

        # 2) 弹窗状态复位与 Esc 焦点归还
        page.set_viewport_size(VIEWPORTS[0][1])
        trigger = page.get_by_role("button", name="选择扩展")
        if trigger.count() > 0:
            trigger.focus()
            trigger_handle = trigger.element_handle()
            trigger.press("Enter")
            dialog = page.get_by_role("dialog")
            dialog.wait_for(state="visible")

            search = dialog.get_by_role("searchbox")
            if search.count() > 0:
                search.fill("not-exist-qa-999")
            page.keyboard.press("Escape")
            dialog.wait_for(state="hidden")

            restored = page.evaluate("(el) => document.activeElement === el", trigger_handle)
            assert restored, "Esc 关闭后焦点未归还触发按钮"

            # 再次打开核对搜索词是否干净复位
            trigger.click()
            dialog.wait_for(state="visible")
            if search.count() > 0:
                assert search.input_value() == "", f"重开后残留搜索词: {search.input_value()!r}"
            page.keyboard.press("Escape")
            dialog.wait_for(state="hidden")

        # 3) 写操作并发 5 连击防重计数（按实际写接口路径调整匹配模式）
        def count_writes(route):
            nonlocal post_count
            if route.request.method == "POST":
                post_count += 1
            route.continue_()

        page.route("**/api/**", count_writes)
        save_btn = page.get_by_role("button", name="保存")
        if save_btn.count() > 0 and save_btn.first.is_enabled():
            for _ in range(5):
                if save_btn.first.is_enabled():
                    save_btn.first.click(no_wait_after=True)
            page.wait_for_load_state("networkidle")
            assert post_count <= 1, f"5 连击触发了 {post_count} 次重复 POST 请求"

        assert not errors, f"运行时存在异常: {errors}"
        print("SPA stress QA passed.")
    finally:
        context.close()
        browser.close()
```

---

## 5. Playwright 编写纪律与安全清理清单

- **同步优先、默认无头**：优先使用 `sync_playwright()` 与 `headless=True`（需要目视调试或桌面 CDP 时再切换有头或附着）。
- **必然回收资源**：`context.close()` 与 `browser.close()` 永远放在 `try ... finally` 中；本地服务始终交给 `scripts/with_server.py` 托管进程组清理。
- **隔离临时产物**：截图、HAR、控制台日志统一写入 `/tmp/qa-artifacts/` 或项目忽略提交的临时目录，绝不留在业务源码目录中。
- **不伪造通过**：脚本断言失败时，让其原样失败并输出客观数值与现场截图，绝不靠加 `try/except pass` 或调宽断言阈值掩盖缺陷。
