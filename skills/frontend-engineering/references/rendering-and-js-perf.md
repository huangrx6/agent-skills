# 浏览器渲染与 JavaScript 热点性能（Rendering & JS Performance）

> **综合影响等级：MEDIUM（渲染性能）/ LOW-MEDIUM（JS 热点微优化）**  
> 本文件无损覆盖 11 条浏览器渲染性能规则（6.1–6.11）与 14 条 JavaScript 热点路径规则（7.1–7.14）。

---

## 第一部分：渲染性能（Rendering Performance）

### 6.1 给 SVG 的外层 `<div>` 加动画，而非直接给 `<svg>` 加动画

**影响等级：LOW**（启用 GPU 合成层硬件加速）

不少浏览器对直接作用在 `<svg>` 上的 CSS 变换（`transform`、`opacity`、`rotate`、`scale`、`translate`）不启用硬件加速。套一层 `<div>` 再做动画可稳定走 GPU 合成层。

```tsx
// ❌ 反例：直接动画 SVG
<svg className="animate-spin" width="24" height="24" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="10" stroke="currentColor" />
</svg>

// ✅ 正例：动画加在包装 div 上
<div className="animate-spin">
  <svg width="24" height="24" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="10" stroke="currentColor" />
  </svg>
</div>
```

---

### 6.2 长列表使用 CSS `content-visibility: auto`

**影响等级：HIGH**（跳过视口外项的布局与绘制，千条列表首绘提速可达 ~10×）

```css
.message-item {
  content-visibility: auto;
  contain-intrinsic-size: 0 80px; /* 给出合理估算高度，避免滚动条剧烈跳动 */
}
```

```tsx
function MessageList({ messages }: { messages: Message[] }) {
  return (
    <div className="message-scroll-container">
      {messages.map((msg) => (
        <div key={msg.id} className="message-item">
          <Avatar user={msg.author} />
          <div>{msg.content}</div>
        </div>
      ))}
    </div>
  )
}
```

---

### 6.3 静态 JSX 节点提升到组件外部

**影响等级：LOW**（避免每次渲染重复创建相同的 React 元素对象，尤其适用于大型静态 SVG）

```tsx
// ❌ 反例：每次渲染都重新构造静态骨架元素
function Container({ loading }: { loading: boolean }) {
  return <div>{loading ? <div className="skeleton-box" /> : null}</div>
}

// ✅ 正例：模块级复用同一静态 JSX 引用（启用 React Compiler 时编译器可自动提升）
const LOADING_SKELETON = <div className="skeleton-box" />

function Container({ loading }: { loading: boolean }) {
  return <div>{loading ? LOADING_SKELETON : null}</div>
}
```

---

### 6.4 精简 SVG 路径坐标精度

**影响等级：LOW**（明显缩小内联 SVG 与图标文件体积）

```xml
<!-- ❌ 反例：6 位冗余小数 -->
<path d="M 10.293847 20.847362 L 30.938472 40.192837" />

<!-- ✅ 正例：根据 viewBox 尺寸收敛到 1 位小数 -->
<path d="M 10.3 20.8 L 30.9 40.2" />
```

批处理命令：`npx svgo --precision=1 --multipass icon.svg`

---

### 6.5 无闪烁、无水合错误地读取客户端存储（如主题）

**影响等级：MEDIUM**（同时消除 SSR 报错、水合警告与首屏闪白）

在渲染期直接读 `localStorage` 会导致 SSR 崩溃；放到 `useEffect` 里读取又会导致首屏先闪默认主题再跳变。对主题/偏好类名，在水合前注入一段极短同步内联脚本预先同步 DOM。

```tsx
// ❌ 反例 1：SSR 阶段 localStorage 未定义直接报错
const theme = localStorage.getItem('theme') || 'light'

// ❌ 反例 2：useEffect 在水合后才改主题，首屏必闪白
useEffect(() => {
  const stored = localStorage.getItem('theme')
  if (stored) setTheme(stored)
}, [])

// ✅ 正例：水合前同步脚本设置 DOM 类名，零闪烁、零水合错配
function ThemeWrapper({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div id="theme-wrapper">{children}</div>
      <script
        dangerouslySetInnerHTML={{
          __html: `
            (function() {
              try {
                var theme = localStorage.getItem('theme') || 'light';
                var el = document.getElementById('theme-wrapper');
                if (el) el.className = theme;
              } catch (e) {}
            })();
          `,
        }}
      />
    </>
  )
}
```

---

### 6.6 仅为「预期差异」使用 `suppressHydrationWarning`

**影响等级：LOW-MEDIUM**（消除本地时间/时区/随机 ID 等合理水合噪音）

仅能用于服务端与客户端**有意不同**的动态文本节点，严禁用它掩盖真实的水合逻辑 Bug。

```tsx
// ❌ 反例：服务端与浏览器时区/语言不同，产生水合警告
function Timestamp() {
  return <span>{new Date().toLocaleString()}</span>
}

// ✅ 正例：精确收敛在动态文本叶子节点
function Timestamp() {
  return <span suppressHydrationWarning>{new Date().toLocaleString()}</span>
}
```

---

### 6.7 高频显隐的重型组件使用 React `<Activity>`

**影响等级：MEDIUM**（保留组件状态与 DOM，免去反复卸载重建开销）

```tsx
import { Activity } from 'react'

function Dropdown({ isOpen }: { isOpen: boolean }) {
  return (
    <Activity mode={isOpen ? 'visible' : 'hidden'}>
      <ExpensiveMenu />
    </Activity>
  )
}
```

---

### 6.8 外链 `<script>` 务必配置 `defer` 或 `async`

**影响等级：HIGH**（消除 HTML 解析阻塞，改善 FCP / TTI）

- `defer`：并行下载、HTML 解析完成后按顺序执行（依赖 DOM 或其他脚本时用）；
- `async`：并行下载、就绪即执行、不保证顺序（独立统计脚本用）；
- Next.js 项目优先使用 `next/script` 并指定 `strategy`（如 `afterInteractive` / `beforeInteractive`）。

```tsx
// ❌ 反例：阻塞 HTML 解析
<script src="https://example.com/analytics.js" />
<script src="/scripts/utils.js" />

// ✅ 正例（Next.js）
import Script from 'next/script'
<Script src="https://example.com/analytics.js" strategy="afterInteractive" />
<Script src="/scripts/utils.js" strategy="beforeInteractive" />
```

---

### 6.9 条件渲染优先显式三元，警惕 `&&` 误渲染 `0` / `NaN`

**影响等级：LOW**（杜绝页面莫名冒出孤零零的 `"0"`）

```tsx
// ❌ 反例：count === 0 时实际渲染出 <div>0</div>
function Badge({ count }: { count: number }) {
  return <div>{count && <span className="badge">{count}</span>}</div>
}

// ✅ 正例：显式布尔条件 + 三元返回 null
function Badge({ count }: { count: number }) {
  return <div>{count > 0 ? <span className="badge">{count}</span> : null}</div>
}
```

---

### 6.10 使用 React DOM 资源提示 API 提前预热关键资源

**影响等级：HIGH**（在浏览器收到完整 HTML 前启动 DNS/建连/字体与样式拉取）

| API（来自 `react-dom`） | 用途 |
| --- | --- |
| `prefetchDNS(href)` | 预解析稍后会访问的第三方域名 DNS |
| `preconnect(href)` | 立即要请求的 API / CDN，预先完成 DNS + TCP + TLS |
| `preload(href, opts)` | 预拉取当前页关键资源（字体、样式、图片、脚本） |
| `preloadModule(href, opts)` | 预拉取高概率跳转路由的 ES 模块 |
| `preinit(href, opts)` | 尽早拉取并执行关键样式表或脚本 |
| `preinitModule(href)` | 尽早拉取并执行 ES 模块 |

```tsx
import { preconnect, prefetchDNS, preload, preinit } from 'react-dom'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  prefetchDNS('https://analytics.example.com')
  preconnect('https://api.example.com')
  preload('/fonts/inter.woff2', {
    as: 'font',
    type: 'font/woff2',
    crossOrigin: 'anonymous',
  })
  preinit('/styles/critical.css', { as: 'style' })

  return (
    <html>
      <body>{children}</body>
    </html>
  )
}
```

---

### 6.11 用 `useTransition` 替代手工 `isLoading` 状态

**影响等级：LOW**（减少额外状态与重渲染，异常时自动复位，新过渡自动覆盖旧过渡）

```tsx
// ❌ 反例：手写 isLoading 容易忘在 catch/finally 复位，且易出竞态
const [isLoading, setIsLoading] = useState(false)
const handleSearch = async (value: string) => {
  setIsLoading(true)
  setQuery(value)
  const data = await fetchResults(value)
  setResults(data)
  setIsLoading(false)
}

// ✅ 正例：useTransition 内置 isPending 与错误弹性（React 19 支持 async action）
import { useState, useTransition } from 'react'

function SearchResults() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Result[]>([])
  const [isPending, startTransition] = useTransition()

  const handleSearch = (value: string) => {
    setQuery(value) // 输入立即更新
    startTransition(async () => {
      const data = await fetchResults(value)
      setResults(data)
    })
  }

  return (
    <>
      <input value={query} onChange={(e) => handleSearch(e.target.value)} />
      {isPending ? <Spinner /> : null}
      <ResultsList results={results} />
    </>
  )
}
```

---

## 第二部分：JavaScript 热点性能（JS Performance）

### 7.1 避免布局抖动（Layout Thrashing）

**影响等级：MEDIUM**（消除强制同步回流）

不要在连续修改样式之间穿插读取布局几何属性（`offsetWidth`、`offsetHeight`、`getBoundingClientRect()`、`getComputedStyle()`）。优先切换 CSS class；若必须操作行内样式，先批量写、再统一读（或先批量读、再统一写）。

```typescript
// ❌ 反例：读写交替触发 2 次强制同步回流
element.style.width = '100px'
const width = element.offsetWidth
element.style.height = '200px'
const height = element.offsetHeight

// ✅ 正例：批量写完后再读一次（更佳做法：直接切换 CSS className）
element.style.width = '100px'
element.style.height = '200px'
element.style.backgroundColor = 'blue'
const { width, height } = element.getBoundingClientRect()
```

---

### 7.2 重复查找场景先建 `Map` 索引

**影响等级：LOW-MEDIUM**（千×千级关联从 100 万次降至 2 千次操作）

```typescript
// ❌ 反例：O(N × M)
function processOrders(orders: Order[], users: User[]) {
  return orders.map((order) => ({
    ...order,
    user: users.find((u) => u.id === order.userId),
  }))
}

// ✅ 正例：一次 O(M) 建索引 + O(1) 查询
function processOrders(orders: Order[], users: User[]) {
  const userById = new Map(users.map((u) => [u.id, u]))
  return orders.map((order) => ({
    ...order,
    user: userById.get(order.userId),
  }))
}
```

---

### 7.3 循环热点中缓存深层属性访问

**影响等级：LOW-MEDIUM**（减少热循环中的重复属性查找）

```typescript
// ❌ 反例：每轮迭代重复解引用 3 层属性
for (let i = 0; i < arr.length; i++) {
  process(obj.config.settings.value)
}

// ✅ 正例：循环外缓存一次
const value = obj.config.settings.value
const len = arr.length
for (let i = 0; i < len; i++) {
  process(value)
}
```

---

### 7.4 用模块级 `Map` 缓存重复纯函数计算

**影响等级：MEDIUM**（跨渲染、工具函数与事件处理器通用缓存）

```typescript
// ❌ 反例：渲染列表中对相同名称重复调用 slugify()
const slug = slugify(project.name)

// ✅ 正例：模块级 Map 缓存（比 Hook 适用范围更广，需按场景控制边界/清理）
const slugifyCache = new Map<string, string>()

function cachedSlugify(text: string): string {
  const hit = slugifyCache.get(text)
  if (hit !== undefined) return hit
  const result = slugify(text)
  slugifyCache.set(text, result)
  return result
}
```

单值缓存同理（如鉴权 cookie 检查），在状态变更回调里将缓存置空失效即可。

---

### 7.5 内存缓存同步 Storage / Cookie 读取

**影响等级：LOW-MEDIUM**（消除反复同步读取 `localStorage` / `sessionStorage` / `document.cookie` 的 I/O 阻塞）

```typescript
const storageCache = new Map<string, string | null>()

function getLocalStorage(key: string): string | null {
  if (!storageCache.has(key)) {
    try {
      storageCache.set(key, localStorage.getItem(key))
    } catch {
      return null
    }
  }
  return storageCache.get(key) ?? null
}

function setLocalStorage(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // 忽略存储异常
  }
  storageCache.set(key, value)
}

// 关键：监听跨标签页变更与页面切回前台，防止缓存过期
window.addEventListener('storage', (e) => {
  if (e.key) storageCache.delete(e.key)
  else storageCache.clear()
})

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') storageCache.clear()
})
```

---

### 7.6 合并对同一数组的多次遍历

**影响等级：LOW-MEDIUM**（3 次遍历合并为 1 次）

```typescript
// ❌ 反例：遍历 3 遍
const admins = users.filter((u) => u.isAdmin)
const testers = users.filter((u) => u.isTester)
const inactive = users.filter((u) => !u.isActive)

// ✅ 正例：单遍分组
const admins: User[] = []
const testers: User[] = []
const inactive: User[] = []

for (const user of users) {
  if (user.isAdmin) admins.push(user)
  if (user.isTester) testers.push(user)
  if (!user.isActive) inactive.push(user)
}
```

---

### 7.7 用 `requestIdleCallback` 延后非关键后台工作

**影响等级：MEDIUM**（交互帧零阻塞，大任务按帧分片）

```typescript
const scheduleIdleWork =
  typeof window !== 'undefined' && 'requestIdleCallback' in window
    ? window.requestIdleCallback.bind(window)
    : (cb: () => void) => window.setTimeout(cb, 1)

function handleSearch(query: string) {
  const results = searchItems(query)
  setResults(results)

  // 非关键副作用放到浏览器空闲期
  scheduleIdleWork(() => analytics.track('search', { query }), { timeout: 2000 })
  scheduleIdleWork(() => saveToRecentSearches(query))
  scheduleIdleWork(() => prefetchTopResults(results.slice(0, 3)))
}

// 大批量后台任务分片（每片 < 50ms）
function processLargeDataset(items: Item[]) {
  let index = 0
  function processChunk(deadline: IdleDeadline) {
    while (index < items.length && deadline.timeRemaining() > 0) {
      processItem(items[index])
      index++
    }
    if (index < items.length) {
      requestIdleCallback(processChunk)
    }
  }
  requestIdleCallback(processChunk)
}
```

**不要用于**：需要立刻给用户反馈的操作、用户正在等待的渲染更新、强时效任务。

---

### 7.8 昂贵数组对比前先做 O(1) 长度检查

**影响等级：MEDIUM-HIGH**（长度不同直接短路，省去排序与序列化）

```typescript
// ❌ 反例：哪怕长度 5 vs 100 也要做两次 O(n log n) 排序并原地修改原数组
function hasChanges(current: string[], original: string[]) {
  return current.sort().join() !== original.sort().join()
}

// ✅ 正例：先 O(1) 判长度，再不可变排序并遇首处差异早退
function hasChanges(current: string[], original: string[]) {
  if (current.length !== original.length) return true
  const currentSorted = current.toSorted()
  const originalSorted = original.toSorted()
  for (let i = 0; i < currentSorted.length; i++) {
    if (currentSorted[i] !== originalSorted[i]) return true
  }
  return false
}
```

---

### 7.9 结果已确定时立即提前返回（Early Return）

**影响等级：LOW-MEDIUM**（跳过剩余无效迭代）

```typescript
// ❌ 反例：发现错误仍遍历完所有用户
function validateUsers(users: User[]) {
  let hasError = false
  let errorMessage = ''
  for (const user of users) {
    if (!user.email) { hasError = true; errorMessage = 'Email required' }
    if (!user.name) { hasError = true; errorMessage = 'Name required' }
  }
  return hasError ? { valid: false, error: errorMessage } : { valid: true }
}

// ✅ 正例：遇到首处非法输入立刻返回
function validateUsers(users: User[]) {
  for (const user of users) {
    if (!user.email) return { valid: false, error: 'Email required' }
    if (!user.name) return { valid: false, error: 'Name required' }
  }
  return { valid: true }
}
```

---

### 7.10 提升或记忆化 `RegExp` 创建

**影响等级：LOW-MEDIUM**（避免每次渲染重复编译正则）

```tsx
// 静态正则直接提至模块顶层
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

// 动态模式配合转义与 useMemo
function Highlighter({ text, query }: { text: string; query: string }) {
  const regex = useMemo(
    () => new RegExp(`(${escapeRegex(query)})`, 'gi'),
    [query]
  )
  const parts = text.split(regex)
  return <>{parts.map((part, i) => <span key={i}>{part}</span>)}</>
}
```

> **全局正则陷阱**：带 `/g` 标志的正则持有可变状态 `lastIndex`——`const re = /foo/g; re.test('foo')` 第一次返回 `true`（`lastIndex = 3`），第二次返回 `false`（`lastIndex = 0`）。提升为模块常量时，若用 `.test()` / `.exec()` 请勿加 `/g`，或每次重置 `lastIndex = 0`。

---

### 7.11 用 `flatMap` 单遍完成映射与过滤

**影响等级：LOW-MEDIUM**（消除 `.map().filter(Boolean)` 的中间数组与二次遍历）

```typescript
// ❌ 反例：两次遍历 + 分配中间数组
const userNames = users
  .map((user) => (user.isActive ? user.name : null))
  .filter(Boolean)

// ✅ 正例：单遍完成转换与过滤，且 TypeScript 类型自动收窄为 string[]
const userNames = users.flatMap((user) => (user.isActive ? [user.name] : []))

// 解析并跳过非法数字
const numbers = strings.flatMap((s) => {
  const n = parseInt(s, 10)
  return Number.isNaN(n) ? [] : [n]
})
```

---

### 7.12 求极值用 O(n) 单遍循环，不要先排序

**影响等级：LOW**（O(n) 替代 O(n log n)，零数组拷贝）

```typescript
// ❌ 反例：仅为找最新一条就把全表排序
function getLatestProject(projects: Project[]) {
  const sorted = [...projects].sort((a, b) => b.updatedAt - a.updatedAt)
  return sorted[0]
}

// ✅ 正例：单遍扫描同时拿到最小/最大
function getOldestAndNewest(projects: Project[]) {
  if (projects.length === 0) return { oldest: null, newest: null }
  let oldest = projects[0]
  let newest = projects[0]
  for (let i = 1; i < projects.length; i++) {
    if (projects[i].updatedAt < oldest.updatedAt) oldest = projects[i]
    if (projects[i].updatedAt > newest.updatedAt) newest = projects[i]
  }
  return { oldest, newest }
}
```

> **为什么不用 `Math.max(...largeArray)`**：展开运算符受引擎参数栈上限限制（约 10 万级元素即会抛 `RangeError: Maximum call stack size exceeded`），循环方案对任意规模稳定可靠。

---

### 7.13 重复成员判断改用 `Set` / `Map` 实现 O(1) 查找

**影响等级：LOW-MEDIUM**（把嵌套 `.includes()` 的 O(n) 降为 O(1)）

```typescript
// ❌ 反例：每次 filter 都线性扫描 allowedIds
const allowedIds = ['a', 'b', 'c']
items.filter((item) => allowedIds.includes(item.id))

// ✅ 正例：Set.has 为 O(1)
const allowedIds = new Set(['a', 'b', 'c'])
items.filter((item) => allowedIds.has(item.id))
```

---

### 7.14 使用 `.toSorted()` 替代 `.sort()` 保证不可变性

**影响等级：MEDIUM-HIGH**（杜绝原地修改 props/state 破坏 React 不可变契约与闭包Bug）

```tsx
// ❌ 反例：原地篡改父组件传入的 users 数组
const sorted = useMemo(
  () => users.sort((a, b) => a.name.localeCompare(b.name)),
  [users]
)

// ✅ 正例：返回新排序数组，原数组保持只读
const sorted = useMemo(
  () => users.toSorted((a, b) => a.name.localeCompare(b.name)),
  [users]
)
```

**兼容与同族不可变方法**：
- `.toSorted()` 支持 Chrome 110+ / Safari 16+ / Firefox 115+ / Node 20+；更旧运行环境用 `[...items].sort(...)` 兜底。
- 同族不可变数组 API：`.toSorted()`、`.toReversed()`、`.toSpliced()`、`.with()`。
