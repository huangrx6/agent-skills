# CSS 作用域工程化与交互健壮性（CSS & Interaction Craft）

> 再干净的 React 状态流，一旦遭遇全局 CSS 选择器碰撞、Flex 溢出撑破布局、焦点击穿或异步响应乱序覆盖，用户仍会看到错位、截断和脏状态。

---

## 1. CSS 作用域防碰撞与 Design Tokens 铁律

1. **功能级唯一前缀**：禁止不同模块共用宽泛类名（如 `.picker-icon`、`.panel-header`、`.card-item`、`.dialog-body`）。统一采用明确的功能域前缀（如 `.ext-install-dialog-icon` vs `.ext-picker-row-icon`）。
2. **修改或新增类名前先全局搜索**：动任何样式前，先在全仓样式与组件目录检索该类名是否已被使用，防止后加载的 CSS 静默覆盖先加载的页面。
3. **禁止用 `!important` 掩盖层叠事故**：只要发现“不加 `!important` 不生效”，99% 说明存在同名选择器碰撞、样式加载顺序失控或特异性设计错误——必须回冲突源头拆清前缀，严禁堆 `!important`。
4. **单点消费设计变量（Design Tokens）**：颜色、字号、圆角、阴影、间距、z-index 层级与动效曲线全部通过既有 CSS 自定义属性引用；禁止在局部样式里硬编码 `#1e1e1e`、`#fff` 或 `rgba(0,0,0,0.4)` 导致浅色/暗色主题割裂。

```css
/* ❌ 反例：宽泛类名易碰撞 + 硬编码主题色 + !important 补丁 */
.picker-icon {
  width: 18px !important;
  color: #333333;
  background: #f5f5f5;
}

/* ✅ 正例：功能域唯一前缀 + 主题 Token */
.ext-picker-row-icon {
  width: 18px;
  height: 18px;
  color: var(--color-text-secondary);
  background: var(--color-surface-subtle);
  border-radius: var(--radius-sm);
}
```

---

## 2. 高数量与窄窗防撑破布局模板

### A. Flex / Grid 行内省略与防挤扁模板

在 Flex/Grid 布局中，Flex 子项默认 `min-width: auto`，导致长文本会拒绝收缩并把右侧按钮挤出容器。**必须在每一层承载收缩的父容器和主列显式设置 `min-width: 0`**。

```css
.list-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0; /* 允许行自身在更外层 Flex/Grid 中收缩 */
}

.list-row-main {
  flex: 1 1 auto;
  min-width: 0; /* 关键：缺这行，内部 text-overflow: ellipsis 完全失效 */
}

.list-row-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.list-row-actions {
  flex: 0 0 auto; /* 锁住右侧按钮宽度，不被超长标题挤扁 */
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
```

### B. 弹层/选择器「粘性搜索 + 独立滚动主体 + 粘性底栏」模板

数据超过 10–20 条或窗口较矮时，禁止让整张弹层被撑出视口。将头部搜索与底部操作栏设为不收缩，让中间主体区独立滚动：

```css
.popover-shell {
  display: flex;
  flex-direction: column;
  max-height: min(440px, calc(100vh - 96px));
  overflow: hidden;
  background: var(--color-surface-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-popover);
}

.popover-search,
.popover-footer {
  flex: 0 0 auto;
}

.popover-body {
  flex: 1 1 auto;
  min-height: 0; /* 关键：Flex 列容器内缺这行会导致主体撑爆而非滚动 */
  overflow-y: auto;
  overscroll-behavior: contain; /* 防止滚到顶/底后穿透带动背后页面滚动 */
}
```

### C. `grid-template-rows` 无高度硬编码手风琴模板

不要用 `max-height: 9999px`（动画时间失真且内容超限时被裁切）或 JS 测高度；用 CSS Grid `0fr → 1fr` 实现平滑过渡：

```css
.accordion-panel {
  display: grid;
  grid-template-rows: 0fr;
  opacity: 0;
  transition:
    grid-template-rows 200ms var(--ease-out),
    opacity 160ms var(--ease-out);
}

.accordion-panel[data-open="true"] {
  grid-template-rows: 1fr;
  opacity: 1;
}

.accordion-panel-inner {
  overflow: hidden;
  min-height: 0;
}
```

> **动效可访问性**：配合 `@media (prefers-reduced-motion: reduce)` 将过渡时长降为 `0ms` 或极短淡变。

---

## 3. 键盘、焦点闭环与外部点击交互

### 焦点闭环（打开聚焦 → Esc 关闭 → 归还焦点）

```tsx
function usePopoverFocus({
  open,
  onClose,
  containerRef,
  initialFocusRef,
}: {
  open: boolean
  onClose: () => void
  containerRef: React.RefObject<HTMLElement | null>
  initialFocusRef: React.RefObject<HTMLElement | null>
}) {
  const triggerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return

    // 1. 记录打开前焦点元素
    triggerRef.current = document.activeElement as HTMLElement | null
    initialFocusRef.current?.focus()

    // 2. Esc 键关闭
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }

    // 3. 外部点击关闭（使用 pointerdown，避免内部拖拽选中文本到外部松手误关）
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node | null
      if (target && containerRef.current && !containerRef.current.contains(target)) {
        onClose()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown)

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown)
      // 4. 关闭后若触发按钮仍在文档中，把焦点归还给它，避免焦点掉回 body
      if (triggerRef.current?.isConnected) {
        triggerRef.current.focus()
      }
    }
  }, [open, onClose, containerRef, initialFocusRef])
}
```

### 原生语义控件纪律
- 可点击操作使用 `<button type="button">`（表单内忘记写 `type="button"` 会意外触发 submit）；
- 路由/外链导航使用 `<a href="...">`；
- 表单输入绑定 `<label htmlFor="...">` 或包裹关系；
- 严禁用 `<div onClick={...}>` 充当按钮（会丢失键盘 `Tab` 聚焦、`Enter/Space` 触发与屏幕阅读器角色）。

---

## 4. 异步竞态守卫、防双击提交与副作用成对清理

### A. `AbortController` + 递增序号双重竞态守卫

即使下游调用不支持 `AbortSignal`（如部分 IPC 或 SDK 调用），递增序号 `requestId` 也能 100% 保证过期响应不会覆盖最新输入结果：

```tsx
function useSearchResults(query: string) {
  const [results, setResults] = useState<Item[]>([])
  const [error, setError] = useState<Error | null>(null)
  const latestRequestRef = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    const requestId = ++latestRequestRef.current

    fetchResults(query, { signal: controller.signal })
      .then((data) => {
        if (latestRequestRef.current === requestId) {
          setResults(data)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        const isAbort = err instanceof DOMException && err.name === 'AbortError'
        if (!isAbort && latestRequestRef.current === requestId) {
          setError(err instanceof Error ? err : new Error(String(err)))
        }
      })

    return () => {
      controller.abort()
    }
  }, [query])

  return { results, error }
}
```

### B. 同步锁 `inFlightRef` 防同一帧双击重复提交

仅靠 React 状态 `isSubmitting` 无法拦截同一渲染帧内的极速连点（`setIsSubmitting(true)` 是异步批处理）。用同步 `useRef` 锁配合 UI 禁用态，并在 `finally` 中安全释放：

```tsx
function SubmitAction({ onSubmit }: { onSubmit: () => Promise<void> }) {
  const [submitting, setSubmitting] = useState(false)
  const inFlightRef = useRef(false)

  async function handleClick() {
    if (inFlightRef.current) return
    inFlightRef.current = true
    setSubmitting(true)
    try {
      await onSubmit()
    } finally {
      inFlightRef.current = false
      setSubmitting(false)
    }
  }

  return (
    <button type="button" disabled={submitting} onClick={handleClick}>
      {submitting ? '提交中...' : '确认提交'}
    </button>
  )
}
```

### C. 副作用资源成对清理清单
以下资源在 `useEffect` 创建后，**必须在 cleanup 返回函数中成对销毁**：
- `addEventListener` ↔ `removeEventListener`
- `ResizeObserver` / `IntersectionObserver` / `MutationObserver` ↔ `.disconnect()`
- `setTimeout` / `setInterval` / `requestAnimationFrame` ↔ `clearTimeout` / `clearInterval` / `cancelAnimationFrame`
- `AbortController` ↔ `.abort()`
- 订阅 / WebSocket / IPC 监听 ↔ `unsubscribe()` / `.close()`
