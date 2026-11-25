# React 重渲染治理（Re-render Optimization）

> **综合影响等级：MEDIUM**  
> 消除冗余重渲染、错误 Effect 同步和意外子树重建，能显著降低主线程无效计算，避免输入框丢焦点、画面闪烁与卡顿。本文件无损覆盖全部 15 条重渲染优化规则（5.1–5.15）。

---

## 规则总览

| 编号 | 规则 | 影响等级 | 关键止损点 |
| --- | --- | --- | --- |
| 5.1 | 渲染期直接计算派生状态 | MEDIUM | 消除 `useEffect + setState` 二次渲染与状态漂移 |
| 5.2 | 将状态读取推迟到实际使用点 | MEDIUM | 回调内按需读值，避免无谓订阅重渲染 |
| 5.3 | 简单基础类型表达式不要包 `useMemo` | LOW-MEDIUM | 避免 Hook 比较开销反超计算本身 |
| 5.4 | 严禁在组件内部定义子组件 | HIGH | 杜绝每次父渲染卸载重建子 DOM 与丢焦点 |
| 5.5 | 提炼 `memo` 组件的非原始默认参数为常量 | MEDIUM | 修复内联默认回调/对象/数组击穿 `memo()` |
| 5.6 | 抽离昂贵计算到 `memo` 子组件以支持早退 | MEDIUM | 加载态/早退路径跳过昂贵子计算 |
| 5.7 | 收窄 `useEffect` 依赖到原始值或布尔跳变 | LOW | 避免对象引用或连续数值引发频繁重跑 |
| 5.8 | 将交互触发的副作用放进事件处理器 | MEDIUM | 不把用户点击建模成 state + effect |
| 5.9 | 拆分不同依赖的合并 Hook 计算与副作用 | MEDIUM | 避免无关依赖变动拖累昂贵步骤重算 |
| 5.10 | 订阅派生布尔状态而非连续变化值 | MEDIUM | 例如用 `useMediaQuery` 取代逐像素 `windowWidth` |
| 5.11 | 基于前值更新时使用函数式 `setState` | MEDIUM | 稳定回调引用并彻底杜绝过时闭包 |
| 5.12 | 昂贵初始值使用 `useState` 懒初始化函数 | MEDIUM | 避免每次重渲染都重复算索引或解析存储 |
| 5.13 | 高频非紧急更新包裹 `startTransition` | MEDIUM | 保持滚动、输入等紧急交互顺滑 |
| 5.14 | 昂贵派生渲染使用 `useDeferredValue` | MEDIUM | 输入框零卡顿，重列表在空闲帧追赶 |
| 5.15 | 高频瞬态值放 `useRef` 而非 `useState` | MEDIUM | 鼠标轨迹、定时器、序号不触发 React 重渲染 |

---

## 5.1 渲染期直接计算派生状态

**影响等级：MEDIUM**（消除多余渲染与中间态不一致）

任何能从当前 `props` 或现有 `state` 同步算出的值，都不要另建 `useState` 再靠 `useEffect` 去同步。不要仅为了响应 prop 变化而在 effect 里 `setState`；改用渲染期推导或 `key` 重置。

### ❌ 反例：多一次渲染且存在旧值闪烁

```tsx
function Form() {
  const [firstName, setFirstName] = useState('First')
  const [lastName, setLastName] = useState('Last')
  const [fullName, setFullName] = useState('')

  useEffect(() => {
    setFullName(firstName + ' ' + lastName)
  }, [firstName, lastName])

  return <p>{fullName}</p>
}
```

### ✅ 正例：渲染期直接推导

```tsx
function Form() {
  const [firstName, setFirstName] = useState('First')
  const [lastName, setLastName] = useState('Last')
  const fullName = firstName + ' ' + lastName

  return <p>{fullName}</p>
}
```

---

## 5.2 将状态读取推迟到实际使用点

**影响等级：MEDIUM**（避免组件订阅自己并不展示的动态状态）

如果组件只在点击回调里读取 `searchParams` 或存储值、而渲染结果根本不依赖它，就不要在组件顶层调用订阅型 Hook。

### ❌ 反例：URL 查询参数每变一次，整个按钮都重渲染

```tsx
function ShareButton({ chatId }: { chatId: string }) {
  const searchParams = useSearchParams()

  const handleShare = () => {
    const ref = searchParams.get('ref')
    shareChat(chatId, { ref })
  }

  return <button type="button" onClick={handleShare}>分享</button>
}
```

### ✅ 正例：点击时按需读取，零订阅开销

```tsx
function ShareButton({ chatId }: { chatId: string }) {
  const handleShare = () => {
    const params = new URLSearchParams(window.location.search)
    const ref = params.get('ref')
    shareChat(chatId, { ref })
  }

  return <button type="button" onClick={handleShare}>分享</button>
}
```

---

## 5.3 简单基础类型表达式不要包 `useMemo`

**影响等级：LOW-MEDIUM**（避免 Hook 调度与依赖比对开销大于表达式本身）

只有少数逻辑/算术运算、且返回原始值（`boolean` / `number` / `string`）的表达式，直接计算即可。

### ❌ 反例：为一次布尔或运算维护 Hook 闭包与依赖数组

```tsx
function Header({ user, notifications }: Props) {
  const isLoading = useMemo(() => {
    return user.isLoading || notifications.isLoading
  }, [user.isLoading, notifications.isLoading])

  if (isLoading) return <Skeleton />
  return <header>...</header>
}
```

### ✅ 正例：直接求值

```tsx
function Header({ user, notifications }: Props) {
  const isLoading = user.isLoading || notifications.isLoading

  if (isLoading) return <Skeleton />
  return <header>...</header>
}
```

---

## 5.4 严禁在组件内部定义子组件

**影响等级：HIGH**（避免每次渲染整棵子树卸载重建）

在组件函数体内声明子组件，会导致每次父组件渲染都生成全新的函数引用。React 会将其识别为不同组件类型，强制卸载旧实例并重新挂载新实例。

**典型症状**：输入框每打一个字就丢焦点、CSS 动画反复重播、`useEffect` 每次渲染都销毁重跑、内部滚动条位置归零。

### ❌ 反例：每次渲染都重建 `Avatar` 与 `Stats`

```tsx
function UserProfile({ user, theme }: Props) {
  // ❌ 每次渲染都是新的组件类型
  const Avatar = () => (
    <img
      src={user.avatarUrl}
      className={theme === 'dark' ? 'avatar-dark' : 'avatar-light'}
    />
  )

  const Stats = () => (
    <div>
      <span>{user.followers} followers</span>
      <span>{user.posts} posts</span>
    </div>
  )

  return (
    <div>
      <Avatar />
      <Stats />
    </div>
  )
}
```

### ✅ 正例：提到模块顶层，通过 props 传值

```tsx
function Avatar({ src, theme }: { src: string; theme: string }) {
  return (
    <img
      src={src}
      className={theme === 'dark' ? 'avatar-dark' : 'avatar-light'}
    />
  )
}

function Stats({ followers, posts }: { followers: number; posts: number }) {
  return (
    <div>
      <span>{followers} followers</span>
      <span>{posts} posts</span>
    </div>
  )
}

function UserProfile({ user, theme }: Props) {
  return (
    <div>
      <Avatar src={user.avatarUrl} theme={theme} />
      <Stats followers={user.followers} posts={user.posts} />
    </div>
  )
}
```

---

## 5.5 提炼 `memo` 组件的非原始默认参数为常量

**影响等级：MEDIUM**（防止默认函数/对象/数组击穿 `memo()` 浅比较）

当 `memo()` 包裹的组件对可选的函数、数组或对象参数写了内联默认值（如 `onClick = () => {}`、`items = []`）且调用方未传该 prop 时，每次父重渲染都会新建默认值引用，导致 `memo()` 彻底失效。

### ❌ 反例：内联空函数每次渲染都是新引用

```tsx
const UserAvatar = memo(function UserAvatar({
  onClick = () => {},
}: {
  onClick?: () => void
}) {
  // ...
})

// 调用方未传 onClick 时，memo 优化完全失效
<UserAvatar />
```

### ✅ 正例：把非原始默认值提到模块级常量

```tsx
const NOOP = () => {}

const UserAvatar = memo(function UserAvatar({
  onClick = NOOP,
}: {
  onClick?: () => void
}) {
  // ...
})

<UserAvatar />
```

---

## 5.6 抽离昂贵计算到 `memo` 子组件以支持早退

**影响等级：MEDIUM**（让 loading / 空态早退彻底跳过昂贵计算）

Hook 必须无条件在组件顶部调用，因此无法写在 `if (loading) return` 之后。把昂贵计算装进子组件，父组件早退时子组件根本不会执行。

### ❌ 反例：处于 `loading` 时仍然先算了一遍 `computeAvatarId`

```tsx
function Profile({ user, loading }: Props) {
  const avatar = useMemo(() => {
    const id = computeAvatarId(user)
    return <Avatar id={id} />
  }, [user])

  if (loading) return <Skeleton />
  return <div>{avatar}</div>
}
```

### ✅ 正例：早退在父组件，昂贵计算留在子组件

```tsx
const UserAvatar = memo(function UserAvatar({ user }: { user: User }) {
  const id = useMemo(() => computeAvatarId(user), [user])
  return <Avatar id={id} />
})

function Profile({ user, loading }: Props) {
  if (loading) return <Skeleton />
  return (
    <div>
      <UserAvatar user={user} />
    </div>
  )
}
```

> **React Compiler 说明**：若项目已启用 React Compiler，手写 `memo()` 与 `useMemo()` 通常可省去，但将昂贵计算下沉到早退分支之后的组件拆分依然有价值。

---

## 5.7 收窄 `useEffect` 依赖到原始值或布尔跳变

**影响等级：LOW**（显著减少无关重跑）

不要把整块对象或连续变化的数字直接塞进依赖数组；提取实际用到的原始字段，或在渲染期先归约为布尔状态。

### ❌ 反例：依赖整个对象或连续像素值

```tsx
// 任一无关字段变动或新对象引用都会重跑
useEffect(() => {
  console.log(user.id)
}, [user])

// width = 767, 766, 765... 每变 1px 就重跑一次
useEffect(() => {
  if (width < 768) enableMobileMode()
}, [width])
```

### ✅ 正例：只依赖原始 ID 或布尔阈值跳变

```tsx
useEffect(() => {
  console.log(user.id)
}, [user.id])

const isMobile = width < 768
useEffect(() => {
  if (isMobile) enableMobileMode()
}, [isMobile])
```

---

## 5.8 将交互触发的副作用放进事件处理器

**影响等级：MEDIUM**（防止无关依赖变化重复触发提交/请求）

只要副作用是由明确的用户交互（点击、提交、拖拽）触发的，就直接写在事件处理函数里，绝不要通过 `setFlag(true)` 再在 `useEffect` 里监听执行。

### ❌ 反例：把提交动作建模成 state + effect（切主题竟会重复提交！）

```tsx
function Form() {
  const [submitted, setSubmitted] = useState(false)
  const theme = useContext(ThemeContext)

  useEffect(() => {
    if (submitted) {
      post('/api/register')
      showToast('Registered', theme)
    }
  }, [submitted, theme])

  return <button type="button" onClick={() => setSubmitted(true)}>提交</button>
}
```

### ✅ 正例：直接在点击事件中执行副作用

```tsx
function Form() {
  const theme = useContext(ThemeContext)

  function handleSubmit() {
    post('/api/register')
    showToast('Registered', theme)
  }

  return <button type="button" onClick={handleSubmit}>提交</button>
}
```

---

## 5.9 拆分不同依赖的合并 Hook 计算与副作用

**影响等级：MEDIUM**（避免局部依赖变化牵连重算所有步骤）

一个 `useMemo` 或 `useEffect` 里混放多个依赖不同的独立任务时，任一依赖变化都会迫使全部任务重跑。

### ❌ 反例：只切排序方向却重跑全量过滤；只改标题却重发页面埋点

```tsx
const sortedProducts = useMemo(() => {
  const filtered = products.filter((p) => p.category === category)
  return filtered.toSorted((a, b) =>
    sortOrder === 'asc' ? a.price - b.price : b.price - a.price
  )
}, [products, category, sortOrder])

useEffect(() => {
  analytics.trackPageView(pathname)
  document.title = `${pageTitle} | My App`
}, [pathname, pageTitle])
```

### ✅ 正例：按独立依赖拆分粒度

```tsx
const filteredProducts = useMemo(
  () => products.filter((p) => p.category === category),
  [products, category]
)

const sortedProducts = useMemo(
  () =>
    filteredProducts.toSorted((a, b) =>
      sortOrder === 'asc' ? a.price - b.price : b.price - a.price
    ),
  [filteredProducts, sortOrder]
)

useEffect(() => {
  analytics.trackPageView(pathname)
}, [pathname])

useEffect(() => {
  document.title = `${pageTitle} | My App`
}, [pageTitle])
```

---

## 5.10 订阅派生布尔状态而非连续变化值

**影响等级：MEDIUM**（将高频重渲染降为仅在跨越阈值时渲染）

### ❌ 反例：窗口每拖动 1px 都触发重渲染

```tsx
function Sidebar() {
  const width = useWindowWidth() // 连续变化
  const isMobile = width < 768
  return <nav className={isMobile ? 'mobile' : 'desktop'} />
}
```

### ✅ 正例：只订阅断点布尔值

```tsx
function Sidebar() {
  const isMobile = useMediaQuery('(max-width: 767px)')
  return <nav className={isMobile ? 'mobile' : 'desktop'} />
}
```

---

## 5.11 基于前值更新时使用函数式 `setState`

**影响等级：MEDIUM**（稳定回调引用，彻底避免过时闭包 Bug）

只要新状态依赖当前状态（增删数组项、计数递增、异步回调合并状态），一律写 `setState(curr => ...)`。

### ❌ 反例：要么依赖 state 频繁重建回调，要么漏写依赖拿到旧值

```tsx
function TodoList() {
  const [items, setItems] = useState(initialItems)

  // items 每次变更都重建回调，牵连子组件重渲染
  const addItems = useCallback((newItems: Item[]) => {
    setItems([...items, ...newItems])
  }, [items])

  // 漏写 items 依赖：永远基于初始 items 过滤！
  const removeItem = useCallback((id: string) => {
    setItems(items.filter((item) => item.id !== id))
  }, [])

  return <ItemsEditor items={items} onAdd={addItems} onRemove={removeItem} />
}
```

### ✅ 正例：零 state 依赖，回调永久稳定且永远读取最新值

```tsx
function TodoList() {
  const [items, setItems] = useState(initialItems)

  const addItems = useCallback((newItems: Item[]) => {
    setItems((curr) => [...curr, ...newItems])
  }, [])

  const removeItem = useCallback((id: string) => {
    setItems((curr) => curr.filter((item) => item.id !== id))
  }, [])

  return <ItemsEditor items={items} onAdd={addItems} onRemove={removeItem} />
}
```

**边界**：当直接设为常量（`setCount(0)`）或仅由外部参数决定（`setName(nextName)`）时，无需函数式更新。即使启用了 React Compiler，出于正确性与防闭包缺陷仍推荐使用函数式更新。

---

## 5.12 昂贵初始值使用 `useState` 懒初始化函数

**影响等级：MEDIUM**（消除每次重渲染白跑初始化计算的浪费）

直接给 `useState(expensiveFn())` 传表达式，会在**每一次重渲染**都执行 `expensiveFn()`，只是返回值会被 React 丢弃；传入初始化函数 `useState(() => expensiveFn())` 则只在首次挂载执行一次。

### ❌ 反例：每次输入 query 都会重建搜索索引或重复解析 `localStorage`

```tsx
function FilteredList({ items }: { items: Item[] }) {
  const [searchIndex] = useState(buildSearchIndex(items)) // 每次渲染都重跑
  const [query, setQuery] = useState('')
  return <SearchResults index={searchIndex} query={query} />
}

function UserProfile() {
  const [settings, setSettings] = useState(
    JSON.parse(localStorage.getItem('settings') || '{}') // 每次渲染都读盘解析
  )
  return <SettingsForm settings={settings} onChange={setSettings} />
}
```

### ✅ 正例：传无参初始化函数，仅首次挂载执行一次

```tsx
function FilteredList({ items }: { items: Item[] }) {
  const [searchIndex] = useState(() => buildSearchIndex(items))
  const [query, setQuery] = useState('')
  return <SearchResults index={searchIndex} query={query} />
}

function UserProfile() {
  const [settings, setSettings] = useState(() => {
    try {
      const stored = localStorage.getItem('settings')
      return stored ? JSON.parse(stored) : {}
    } catch {
      return {}
    }
  })
  return <SettingsForm settings={settings} onChange={setSettings} />
}
```

**边界**：原始值（`useState(0)`）、直接引用（`useState(props.value)`）或廉价空字面量（`useState({})`）无需懒初始化。

---

## 5.13 高频非紧急更新包裹 `startTransition`

**影响等级：MEDIUM**（保障滚动、打字等高优先级交互响应）

将高频但允许短暂延后的状态更新标记为过渡更新，让 React 优先响应用户输入。

### ❌ 反例：每次滚动都触发同步高优先级重渲染

```tsx
function ScrollTracker() {
  const [scrollY, setScrollY] = useState(0)
  useEffect(() => {
    const handler = () => setScrollY(window.scrollY)
    window.addEventListener('scroll', handler, { passive: true })
    return () => window.removeEventListener('scroll', handler)
  }, [])
}
```

### ✅ 正例：使用 `startTransition` 降级为可中断更新

```tsx
import { startTransition, useEffect, useState } from 'react'

function ScrollTracker() {
  const [scrollY, setScrollY] = useState(0)
  useEffect(() => {
    const handler = () => {
      startTransition(() => setScrollY(window.scrollY))
    }
    window.addEventListener('scroll', handler, { passive: true })
    return () => window.removeEventListener('scroll', handler)
  }, [])
}
```

---

## 5.14 昂贵派生渲染使用 `useDeferredValue`

**影响等级：MEDIUM**（大列表模糊搜索、重图表联动时输入框不掉帧）

当用户输入驱动昂贵的列表筛选或图表重绘时，用 `useDeferredValue` 把输入态与昂贵派生渲染解耦，并配合 `useMemo` 让昂贵计算仅依赖延后值。

### ❌ 反例：每次击键同步跑全量 `fuzzyMatch`，输入框明显卡顿

```tsx
function Search({ items }: { items: Item[] }) {
  const [query, setQuery] = useState('')
  const filtered = items.filter((item) => fuzzyMatch(item, query))

  return (
    <>
      <input value={query} onChange={(e) => setQuery(e.target.value)} />
      <ResultsList results={filtered} />
    </>
  )
}
```

### ✅ 正例：输入立即响应，昂贵列表延后渲染并给温和过期态提示

```tsx
function Search({ items }: { items: Item[] }) {
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query)
  const filtered = useMemo(
    () => items.filter((item) => fuzzyMatch(item, deferredQuery)),
    [items, deferredQuery]
  )
  const isStale = query !== deferredQuery

  return (
    <>
      <input value={query} onChange={(e) => setQuery(e.target.value)} />
      <div style={{ opacity: isStale ? 0.7 : 1 }}>
        <ResultsList results={filtered} />
      </div>
    </>
  )
}
```

**关键注意**：必须把昂贵过滤/计算包在依赖 `deferredQuery` 的 `useMemo`（或已 `memo` 的子组件）中；否则输入触发渲染时，昂贵计算仍会同步执行一次。

---

## 5.15 高频瞬态值放 `useRef` 而非 `useState`

**影响等级：MEDIUM**（高频事件零 React 重渲染）

鼠标坐标、拖拽偏移、定时器句柄、最新请求序号等高频瞬态值，若不需要驱动整棵组件树重新 Diff，应保存在 `useRef` 中，必要时直接更新单个 DOM 节点的合成层样式（如 `transform`）。

### ❌ 反例：鼠标每移动 1 像素就触发整组件重渲染

```tsx
function Tracker() {
  const [lastX, setLastX] = useState(0)

  useEffect(() => {
    const onMove = (e: MouseEvent) => setLastX(e.clientX)
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  return (
    <div style={{ position: 'fixed', top: 0, left: lastX, width: 8, height: 8 }} />
  )
}
```

### ✅ 正例：`useRef` 跟踪 + 直接操作合成属性 `transform`

```tsx
function Tracker() {
  const lastXRef = useRef(0)
  const dotRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      lastXRef.current = e.clientX
      const node = dotRef.current
      if (node) {
        node.style.transform = `translateX(${e.clientX}px)`
      }
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])

  return (
    <div
      ref={dotRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: 8,
        height: 8,
        transform: 'translateX(0px)',
      }}
    />
  )
}
```
