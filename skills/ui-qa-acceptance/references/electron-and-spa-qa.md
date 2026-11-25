# 桌面 Electron 与 SPA 专项验收

桌面应用（Electron / NW.js / CEF / WebView2）与现代单页应用（React / Vue / Next.js）具有不同于普通静态网页的运行边界：本地调试端口安全、用户数据目录隔离、客户端水合延迟、弹层过渡期点击截获以及明暗双主题动态切换残留。

---

## 1. 桌面应用本地 CDP 验收模式

### 启用本地 DevTools 协议（仅限回环地址）
- **Electron / NW.js / CEF**：启动被测应用时附加 `--remote-debugging-port=9222`（或指定空闲端口），确保仅监听 `127.0.0.1`，**严禁绑定 `0.0.0.0` 或暴露到局域网/公网**。
- **Windows WebView2**：通过环境变量开启：`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222`。
- **窗口可见性硬要求**：验收期间必须保持应用主窗口在屏幕上**可见且未最小化**；隐藏或最小化的窗口会跳过部分渲染管线与像素对比度读取，导致截图发黑或颜色读取失真。验收完成后，应将窗口恢复至原有大小与状态。

### 通过 Playwright 附着 CDP 定位目标渲染页

Electron 往往同时存在主渲染窗口、菜单栏小窗、隐藏预加载页或 DevTools 窗口，连接后必须按 URL 或标题精准筛选目标 `page`，不可盲取 `pages[0]`：

```python
from playwright.sync_api import sync_playwright

CDP_ENDPOINT = "http://127.0.0.1:9222"
TARGET_MATCH = "localhost:5173"  # 或主窗口标题/路由片段

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
    target_page = None
    for ctx in browser.contexts:
        for pg in ctx.pages:
            url = pg.url or ""
            title = pg.title() if not pg.is_closed() else ""
            if url.startswith("devtools://"):
                continue
            if TARGET_MATCH in url or TARGET_MATCH in title:
                target_page = pg
                break
        if target_page:
            break

    if target_page is None:
        raise RuntimeError(f"未在 CDP 端口找到匹配 '{TARGET_MATCH}' 的可见渲染页")

    # 挂载监听并执行先侦察后操作（注意：connect_over_cdp 断开连接不强制杀掉宿主进程）
    target_page.on("pageerror", lambda err: print(f"[PAGEERROR] {err}"))
    print("Connected to:", target_page.url, "|", target_page.title())
    browser.close()
```

### 无 CDP 暴露平台的透明声明规则
- **Tauri on macOS（WKWebView）与 Linux（WebKitGTK）** 不暴露 Chromium CDP 端口；无法运行远程 CDP 渲染态脚本。
- 遇到此类环境时，严禁假装完成了渲染态实测：可结合静态检查或人工/系统辅助工具能覆盖的部分记录实测结果，并在验收报告的「未覆盖范围与风险提示」中明确声明：**「目标平台不暴露 CDP，本次未运行自动化渲染态检查」**。

---

## 2. 独立 `USER_DATA` 数据目录隔离卫生

本地桌面应用和带 SQLite / IndexedDB / LocalStorage 持久化的应用，绝不能直接对着开发者的真实个人数据目录做高压压测（造 100 条测试数据、触发破坏性删除、改坏主题与凭据）。

### 隔离验收四步规范
1. **每次验收建独立临时根目录**：优先使用应用支持的隔离环境变量（如 `PI_STUDIO_USER_DATA=/tmp/qa-run-<ts>`、`ELECTRON_USER_DATA` 或 Chromium `--user-data-dir=/tmp/qa-profile-<ts>`）。
2. **分场景造数，互不污染**：
   - 空白临时目录 → 测「0 条空态 + 首次冷启动引导」；
   - 预置标准数据集 → 测「核心主路径 + 持久化重启闭环」；
   - 预置 30+/100+ 与超长文案数据集 → 测「高数量滚动、吸顶搜索、粘性底栏与窄/矮窗」。
3. **重启持久化核验**：杀掉并重启桌面应用时**继续指向同一个临时 `USER_DATA` 目录**，核对写盘结果真实保留而非只存在于关闭前的进程内存。
4. **验收后彻底清理**：脚本在 `finally` 或人工收尾阶段删除临时用户数据目录与临时截图目录，确保不把任何临时文件或测试快照带入业务 Git 工作区。

---

## 3. SPA 水合（Hydration）与过渡期点击陷阱

### 3.1 首屏 SSR 壳已渲染但事件未水合
- **症状**：静态 HTML 按钮肉眼可见、`locator.is_visible()` 为真，但点击后毫无反应或表单输入被框架覆盖回空值。
- **验收排查**：
  1. 在 `console` 监听中重点检索 `Hydration failed`、`Text content does not match`、`did not match`、`Minified React error #418/#423/#425`；
  2. 核对时间/日期/随机数渲染是否引发服务端与客户端水合不一致；
  3. 等待策略不要停在 `domcontentloaded`：应等 `networkidle`（或首个业务接口返回）+ 核心控件 `enabled` + 框架就绪信号再点击。

### 3.2 弹窗/抽屉过渡动画截获底层点击
- **症状**：关闭弹窗后紧接着点击底层列表项或导航按钮，请求未触发或 Playwright 报「element intercepts pointer events」。
- **专项压测动作**：
  1. 正常操作时：等待弹窗与遮罩层 `wait_for(state="detached")`（或 `state="hidden"` 且 `pointer-events: none`）后再点底层；
  2. **故意高压连点**：在弹窗刚关闭 50ms 内立刻点击底层元素，以及在 500ms 内连续开关同一弹窗/抽屉 5 次；
  3. 检查动画结束后是否残留透明全屏遮罩（`position: fixed; inset: 0`）、`body` 是否遗留 `overflow: hidden` 锁死页面滚动、或 `inert` / `aria-hidden="true"` 未从主内容移除导致全页无法点击和聚焦。

### 3.3 长连接（SSE / WebSocket / 轮询）导致 `networkidle` 超时
- 含实时流式输出或心跳轮询的 SPA，不应死等 `networkidle` 触发 30 秒超时。
- 替代等待策略：
  ```python
  page.goto(url, wait_until="domcontentloaded")
  # 1) 等首屏核心数据接口返回 200
  # 2) 等骨架屏 / Spinner 消失
  page.locator("[data-loading='true'], .skeleton, [aria-busy='true']").wait_for(
      state="hidden", timeout=15000
  )
  # 3) 等主交互入口可见且可点
  page.get_by_role("button", name="新建").wait_for(state="visible", timeout=10000)
  ```

---

## 4. 明暗双主题与系统偏好切换残留核查

许多页面只在开发者常用的单一主题（纯亮色或纯暗色）下目视正常，切换到另一套主题或动态来回切换后立刻暴露硬编码颜色与原生控件割裂。

### 双主题压测步骤
1. 在亮色模式下采集主界面、弹窗、表单、下拉列表、选中态与禁用态基线；
2. 通过应用内置主题开关（以及 Playwright `page.emulate_media(color_scheme="dark")` / `"light"`）切换至暗色模式，再切回亮色、再切回暗色（至少往返 1 次）；
3. 在每个主题下运行以下 DOM 主题一致性核查脚本，并配截图人工复核对比度。

### 主题切换残留快速检查脚本（DevTools / `page.evaluate`）

```javascript
(() => {
  const html = document.documentElement;
  const htmlStyle = getComputedStyle(html);
  const bodyStyle = getComputedStyle(document.body);
  const themeMeta = document.querySelector('meta[name="theme-color"]')?.getAttribute('content') || null;

  // 检查原生 select 在深色模式下是否仍呈刺眼白底或不可读前景
  const selects = Array.from(document.querySelectorAll('select')).map((s) => {
    const st = getComputedStyle(s);
    return {
      name: s.getAttribute('name') || s.id || '(select)',
      bg: st.backgroundColor,
      color: st.color,
    };
  });

  // 粗筛可能的“白底浅字”或“黑底深字”同色不可读文本
  const parseRgb = (c) => {
    const m = c.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
    return m ? { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] } : null;
  };
  const lum = ({ r, g, b }) => {
    const f = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const contrast = (c1, c2) => {
    const l1 = lum(c1);
    const l2 = lum(c2);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  };

  const lowContrastSamples = [];
  for (const el of document.querySelectorAll('button, a, p, span, label, h1, h2, h3, li, td, th')) {
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || !(el.innerText || '').trim()) continue;
    const fg = parseRgb(st.color);
    const bg = parseRgb(st.backgroundColor);
    if (!fg || !bg || bg.a < 0.9) continue; // 仅对自带不透明背景的元素做快速实测
    const ratio = contrast(fg, bg);
    const fontSize = parseFloat(st.fontSize);
    const isLarge = fontSize >= 24 || (fontSize >= 18.66 && Number(st.fontWeight) >= 700);
    const threshold = isLarge ? 3.0 : 4.5;
    if (ratio < threshold) {
      lowContrastSamples.push({
        text: el.innerText.trim().slice(0, 30),
        ratio: Number(ratio.toFixed(2)),
        threshold,
        fg: st.color,
        bg: st.backgroundColor,
      });
    }
  }

  return {
    colorScheme: htmlStyle.colorScheme,
    dataTheme: html.getAttribute('data-theme') || html.className,
    bodyBg: bodyStyle.backgroundColor,
    bodyColor: bodyStyle.color,
    themeMeta,
    selects,
    lowContrastCount: lowContrastSamples.length,
    lowContrastSamples: lowContrastSamples.slice(0, 15),
  };
})();
```

### 重点人工核查项
- `<html>` 在暗色模式下是否声明了 `color-scheme: dark`（直接影响原生滚动条、日期选择器、输入框高亮色）；
- 弹窗、下拉菜单、Tooltip、代码高亮块、SVG 图标与图表坐标轴在切换主题后是否**同步更新**，不残留切换前的旧主题背景或边框；
- 正文对比度 ≥ `4.5:1`，大字号标题与关键控件边框 ≥ `3:1`。
