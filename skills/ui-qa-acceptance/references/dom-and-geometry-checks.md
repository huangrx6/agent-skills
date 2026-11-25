# DOM 与几何客观检查脚本

仅凭肉眼看缩略截图极易漏掉 4px 横向溢出、右侧按钮被轻微裁切、粘性底栏盖住最后一项或焦点掉回 `<body>` 等隐蔽缺陷。以下 JS 检查片段均可直接在 DevTools Console 或 Playwright `page.evaluate(...)` 中执行，返回结构化 JSON，直接作为验收报告的硬证据。

---

## 1. 全页横向溢出与越界元素扫描

同时检测根文档横向溢出、突破视口左右边界的可见元素，以及单行/Flex 容器内部未声明滚动却实际溢出的元素。

```javascript
(() => {
  const vw = window.innerWidth;
  const docOverflow = document.documentElement.scrollWidth - vw;
  const offenders = [];

  const toSelector = (el) => {
    if (el.id) return `#${el.id}`;
    const cls = typeof el.className === 'string'
      ? el.className.trim().split(/\s+/).slice(0, 2).join('.')
      : '';
    return `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''}`;
  };

  for (const el of document.querySelectorAll('body *')) {
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) {
      continue;
    }
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;

    // 1) 超出视口左右边界（跳过刻意设置 overflow-x: auto/scroll 的容器子项）
    if (rect.right > vw + 1 || rect.left < -1) {
      offenders.push({
        kind: 'viewport-overflow',
        selector: toSelector(el),
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        viewportWidth: vw,
        text: (el.innerText || '').trim().slice(0, 40),
      });
    }
    // 2) 非滚动容器自身内容横向溢出
    const allowScrollX = ['auto', 'scroll'].includes(style.overflowX);
    if (!allowScrollX && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 2) {
      if (style.textOverflow !== 'ellipsis') {
        offenders.push({
          kind: 'container-overflow',
          selector: toSelector(el),
          scrollWidth: el.scrollWidth,
          clientWidth: el.clientWidth,
          delta: el.scrollWidth - el.clientWidth,
          text: (el.innerText || '').trim().slice(0, 40),
        });
      }
    }
  }

  return {
    viewportWidth: vw,
    documentScrollWidth: document.documentElement.scrollWidth,
    hasHorizontalOverflow: docOverflow > 1,
    docOverflowPx: docOverflow,
    offenderCount: offenders.length,
    offenders: offenders.slice(0, 20),
  };
})();
```

---

## 2. 元素裁切与粘性顶/底栏遮挡检测

用于核查：**弹窗/卡片内交互按钮是否被父容器裁切出界**、**列表最后一项滚到底后是否被 `sticky`/`fixed` 底栏压住**、**当前聚焦元素是否被粘性栏遮挡**。

```javascript
(() => {
  const vh = window.innerHeight;
  const vw = window.innerWidth;
  const stickyBars = [];
  const clippedControls = [];
  const occludedTargets = [];

  const intersects = (a, b) =>
    !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom);

  // 1) 识别可见的 sticky / fixed 顶栏与底栏
  for (const el of document.querySelectorAll('body *')) {
    const st = getComputedStyle(el);
    if (!['fixed', 'sticky'].includes(st.position) || st.display === 'none' || st.visibility === 'hidden') {
      continue;
    }
    const r = el.getBoundingClientRect();
    if (r.width >= vw * 0.4 && r.height >= 24 && r.height <= vh * 0.45) {
      stickyBars.push({
        el,
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute('role') || '',
        rect: { top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right) },
      });
    }
  }

  // 2) 检查可交互按钮/链接是否被父裁剪容器或视口裁切
  const controls = document.querySelectorAll('button, a[href], input, select, textarea, [role="button"]');
  for (const ctrl of controls) {
    const st = getComputedStyle(ctrl);
    if (st.display === 'none' || st.visibility === 'hidden' || ctrl.offsetParent === null) continue;
    const r = ctrl.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;

    // 是否被裁剪父容器切掉（右边界或底边界超出父容器）
    let parent = ctrl.parentElement;
    while (parent && parent !== document.body) {
      const pst = getComputedStyle(parent);
      if (['hidden', 'clip'].includes(pst.overflowX) || ['hidden', 'clip'].includes(pst.overflowY)) {
        const pr = parent.getBoundingClientRect();
        if (r.right > pr.right + 2 || r.bottom > pr.bottom + 2 || r.left < pr.left - 2 || r.top < pr.top - 2) {
          clippedControls.push({
            text: (ctrl.innerText || ctrl.getAttribute('aria-label') || ctrl.tagName).trim().slice(0, 40),
            controlRect: { l: Math.round(r.left), t: Math.round(r.top), r: Math.round(r.right), b: Math.round(r.bottom) },
            clipParentRect: { l: Math.round(pr.left), t: Math.round(pr.top), r: Math.round(pr.right), b: Math.round(pr.bottom) },
          });
          break;
        }
      }
      parent = parent.parentElement;
    }

    // 检查是否被不相关的 sticky/fixed 栏覆盖中心点
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    if (cx >= 0 && cx <= vw && cy >= 0 && cy <= vh) {
      for (const bar of stickyBars) {
        if (bar.el.contains(ctrl) || ctrl.contains(bar.el)) continue;
        if (intersects(r, bar.rect)) {
          const hit = document.elementFromPoint(cx, cy);
          if (hit && bar.el.contains(hit)) {
            occludedTargets.push({
              control: (ctrl.innerText || ctrl.getAttribute('aria-label') || ctrl.tagName).trim().slice(0, 40),
              occludedBy: `${bar.tag}${bar.role ? `[role=${bar.role}]` : ''}`,
              controlBottom: Math.round(r.bottom),
              barTop: bar.rect.top,
            });
          }
        }
      }
    }
  }

  // 3) 检查当前焦点元素是否被粘性栏遮挡
  const active = document.activeElement;
  let activeOccluded = false;
  if (active && active !== document.body) {
    const ar = active.getBoundingClientRect();
    const hit = document.elementFromPoint(ar.left + ar.width / 2, ar.top + ar.height / 2);
    activeOccluded = Boolean(hit && !active.contains(hit) && !hit.contains(active) && stickyBars.some((b) => b.el.contains(hit)));
  }

  return {
    stickyBarCount: stickyBars.length,
    clippedCount: clippedControls.length,
    clippedControls: clippedControls.slice(0, 15),
    occludedCount: occludedTargets.length,
    occludedTargets: occludedTargets.slice(0, 15),
    activeElementOccluded: activeOccluded,
  };
})();
```

---

## 3. 焦点归还、可见焦点环与可访问性静态/实时巡检

### 3.1 弹层关闭后焦点归还断言（Playwright 侧）

```python
# 在打开弹窗前记录当前触发按钮句柄
trigger = page.get_by_role("button", name="选择扩展")
trigger.focus()
trigger_handle = trigger.element_handle()

trigger.press("Enter")
dialog = page.get_by_role("dialog")
dialog.wait_for(state="visible")

# 断言焦点进入弹层内部
focus_in_dialog = page.evaluate(
    "(dlg) => dlg.contains(document.activeElement)", dialog.element_handle()
)
assert focus_in_dialog, "弹窗打开后焦点未移入弹层内"

# 按 Esc 关闭并断言焦点归还到原触发按钮（非 document.body）
page.keyboard.press("Escape")
dialog.wait_for(state="hidden")
focus_restored = page.evaluate(
    """(btn) => ({
      restored: document.activeElement === btn,
      activeTag: document.activeElement ? document.activeElement.tagName : null,
      activeText: document.activeElement ? (document.activeElement.innerText || '').trim().slice(0, 40) : ''
    })""",
    trigger_handle,
)
assert focus_restored["restored"], f"Esc 关闭后焦点未归还原触发按钮：{focus_restored}"
```

### 3.2 可访问名称、反模式点击元素与焦点环样式扫描

```javascript
(() => {
  const missingButtonLabels = [];
  const unlabeledInputs = [];
  const clickableNonSemantic = [];

  for (const btn of document.querySelectorAll('button, [role="button"]')) {
    const st = getComputedStyle(btn);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    const name = (
      btn.getAttribute('aria-label') ||
      btn.getAttribute('title') ||
      btn.innerText ||
      ''
    ).trim();
    if (!name) {
      missingButtonLabels.push(btn.outerHTML.slice(0, 120));
    }
  }

  for (const input of document.querySelectorAll('input:not([type="hidden"]), select, textarea')) {
    const st = getComputedStyle(input);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    const hasLabel = Boolean(
      input.getAttribute('aria-label') ||
      input.getAttribute('aria-labelledby') ||
      input.closest('label') ||
      (input.id && document.querySelector(`label[for="${CSS.escape(input.id)}"]`))
    );
    if (!hasLabel) {
      unlabeledInputs.push({
        tag: input.tagName.toLowerCase(),
        type: input.getAttribute('type') || '',
        name: input.getAttribute('name') || '',
        placeholder: input.getAttribute('placeholder') || '',
      });
    }
  }

  for (const el of document.querySelectorAll('div[onclick], span[onclick], div.cursor-pointer, span.cursor-pointer')) {
    if (!el.getAttribute('role') && el.tabIndex < 0) {
      clickableNonSemantic.push((el.innerText || el.outerHTML).trim().slice(0, 80));
    }
  }

  const active = document.activeElement;
  let activeFocusStyle = null;
  if (active && active !== document.body) {
    const ast = getComputedStyle(active);
    activeFocusStyle = {
      tag: active.tagName.toLowerCase(),
      outlineStyle: ast.outlineStyle,
      outlineWidth: ast.outlineWidth,
      boxShadow: ast.boxShadow,
      hasVisibleIndicator:
        (ast.outlineStyle !== 'none' && parseFloat(ast.outlineWidth) > 0) ||
        ast.boxShadow !== 'none',
    };
  }

  return {
    missingButtonLabelCount: missingButtonLabels.length,
    missingButtonLabels: missingButtonLabels.slice(0, 10),
    unlabeledInputCount: unlabeledInputs.length,
    unlabeledInputs: unlabeledInputs.slice(0, 10),
    clickableNonSemanticCount: clickableNonSemantic.length,
    clickableNonSemantic: clickableNonSemantic.slice(0, 10),
    activeFocusStyle,
  };
})();
```

---

## 4. 坏图、缺失尺寸、字体加载与触控热区扫描

核查 `naturalWidth === 0` 坏图、缺少显式宽高易致 CLS 的图片、`document.fonts` 加载状态以及小于 `24×24px`（WCAG 2.5.8 底线）或 `44×44px`（移动端推荐）的交互目标。

```javascript
(async () => {
  const brokenImages = [];
  const unsizedImages = [];
  const missingAltImages = [];

  for (const img of document.querySelectorAll('img')) {
    const st = getComputedStyle(img);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    const src = img.currentSrc || img.getAttribute('src') || '(empty)';
    if (img.complete && img.naturalWidth === 0) {
      brokenImages.push({ src, alt: img.getAttribute('alt') });
    }
    if (!img.hasAttribute('width') && !img.hasAttribute('height') && st.aspectRatio === 'auto') {
      unsizedImages.push({ src });
    }
    if (img.getAttribute('alt') === null && img.getAttribute('aria-hidden') !== 'true') {
      missingAltImages.push({ src });
    }
  }

  // 字体状态
  const fontsSummary = { status: document.fonts ? document.fonts.status : 'unsupported', failed: [], loadedCount: 0 };
  if (document.fonts) {
    for (const f of document.fonts) {
      if (f.status === 'loaded') fontsSummary.loadedCount += 1;
      if (f.status === 'error') fontsSummary.failed.push(`${f.family} (${f.weight})`);
    }
  }

  // 交互目标热区扫描（区分 <24px 违规 与 24-43px 偏小）
  const undersizedTargets = [];
  for (const el of document.querySelectorAll('button, a[href], [role="button"], input[type="checkbox"], input[type="radio"]')) {
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || el.offsetParent === null) continue;
    if (st.display === 'inline') continue; // 行内文本链接属于 WCAG 例外
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.width < 24 || r.height < 24) {
      undersizedTargets.push({
        level: 'below-24px-wcag',
        text: (el.innerText || el.getAttribute('aria-label') || el.tagName).trim().slice(0, 30),
        w: Math.round(r.width),
        h: Math.round(r.height),
      });
    } else if (r.width < 44 || r.height < 44) {
      undersizedTargets.push({
        level: 'below-44px-touch',
        text: (el.innerText || el.getAttribute('aria-label') || el.tagName).trim().slice(0, 30),
        w: Math.round(r.width),
        h: Math.round(r.height),
      });
    }
  }

  return {
    brokenImageCount: brokenImages.length,
    brokenImages,
    unsizedImageCount: unsizedImages.length,
    missingAltCount: missingAltImages.length,
    fonts: fontsSummary,
    below24pxCount: undersizedTargets.filter((t) => t.level === 'below-24px-wcag').length,
    below44pxCount: undersizedTargets.filter((t) => t.level === 'below-44px-touch').length,
    undersizedSamples: undersizedTargets.slice(0, 15),
  };
})();
```

---

## 5. `prefers-reduced-motion`、动效残留与 CLS 采集

### 5.1 导航前注入 CLS 观察器（通过 `page.add_init_script(...)`）

```javascript
(() => {
  window.__qaCls = { total: 0, entries: [] };
  if (!('PerformanceObserver' in window)) return;
  try {
    const obs = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) {
          window.__qaCls.total += entry.value;
          window.__qaCls.entries.push({
            value: Number(entry.value.toFixed(4)),
            startTime: Math.round(entry.startTime),
          });
        }
      }
    });
    obs.observe({ type: 'layout-shift', buffered: true });
  } catch (_) {}
})();
```

### 5.2 动效完成态、`transition: all` 与减少动态偏好检查

```javascript
(() => {
  const reducedMotionMatched = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const runningAnimations = document.getAnimations
    ? document.getAnimations().map((a) => ({
        playState: a.playState,
        effect: a.effect && a.effect.getTiming ? a.effect.getTiming().iterations : null,
        target: a.effect && a.effect.target ? a.effect.target.tagName.toLowerCase() : null,
      }))
    : [];

  const transitionAllHits = [];
  const staleWillChangeHits = [];

  for (const el of document.querySelectorAll('body *')) {
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    if (st.transitionProperty.split(',').some((p) => p.trim() === 'all') && st.transitionDuration !== '0s') {
      transitionAllHits.push(el.tagName.toLowerCase() + (el.id ? `#${el.id}` : ''));
    }
    if (st.willChange && st.willChange !== 'auto') {
      staleWillChangeHits.push({ tag: el.tagName.toLowerCase(), willChange: st.willChange });
    }
  }

  return {
    reducedMotionMatched,
    activeAnimationCount: runningAnimations.filter((a) => a.playState === 'running').length,
    infiniteAnimations: runningAnimations.filter((a) => a.effect === Infinity),
    transitionAllCount: transitionAllHits.length,
    staleWillChangeCount: staleWillChangeHits.length,
    cls: window.__qaCls || null,
  };
})();
```

> **使用提示**：在 `reduced_motion="reduce"` 模式下，`infiniteAnimations` 应当清零（装饰性无限循环必须停止），同时验证关键状态切换（如 Tab 选中、错误提示、弹窗显隐）依然有清晰视觉变化而非被暴力 `0.01ms` 全局覆盖毁掉反馈。
