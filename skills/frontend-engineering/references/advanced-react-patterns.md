# 高级 React 模式与 React 19 API（Advanced Patterns & React 19）

> **综合影响等级：LOW（高级模式）/ MEDIUM（React 19 API 演进）**  
> 本文件无损覆盖 4 条高级 React 副作用与初始化规则（8.1–8.4），以及 React 19+ 组件定义与 Context 消费 API 变更。

---

## 第一部分：高级副作用与初始化模式（8.1–8.4）

### 8.1 严禁把 `useEffectEvent` 返回的函数放进依赖数组

**影响等级：LOW**（避免每次渲染重跑 Effect 及触发 Hooks Lint 报错）

`useEffectEvent` 返回的 Effect Event 函数**刻意不具备稳定引用**，每次渲染都会变化。绝不能把它放进 `useEffect` 的依赖数组；依赖数组里只保留真正的响应式值（如 `roomId`），在 Effect 主体或订阅回调中直接调用该 Effect Event。

#### ❌ 反例：把 Effect Event 塞进依赖数组，导致每次渲染断开重连

```tsx
import { useEffect, useEffectEvent } from 'react'

function ChatRoom({
  roomId,
  onConnected,
}: {
  roomId: string
  onConnected: () => void
}) {
  const handleConnected = useEffectEvent(onConnected)

  useEffect(() => {
    const connection = createConnection(roomId)
    connection.on('connected', handleConnected)
    connection.connect()

    return () => connection.disconnect()
  }, [roomId, handleConnected]) // ❌ 导致每次渲染重跑并触发 lint 报错
}
```

#### ✅ 正例：只依赖真正的响应式值 `roomId`

```tsx
import { useEffect, useEffectEvent } from 'react'

function ChatRoom({
  roomId,
  onConnected,
}: {
  roomId: string
  onConnected: () => void
}) {
  const handleConnected = useEffectEvent(onConnected)

  useEffect(() => {
    const connection = createConnection(roomId)
    connection.on('connected', handleConnected)
    connection.connect()

    return () => connection.disconnect()
  }, [roomId]) // ✅ 仅在 roomId 变化时重连，但回调永远执行最新 onConnected
}
```

---

### 8.2 应用级一次性初始化不要绑定到组件挂载

**影响等级：LOW-MEDIUM**（消除开发模式 StrictMode 双执行与组件重挂载重复初始化）

必须在整个应用生命周期中**只跑一次**的初始化（读取全局启动存储、校验全局鉴权、注册全局 SDK），不要直接裸写在某个组件的 `useEffect(..., [])` 中。组件可能被卸载重挂载，开发态 StrictMode 也会主动重跑 Effect。应使用模块级幂等守卫，或放到应用入口模块顶层执行。

#### ❌ 反例：开发态跑两次，组件重挂载再跑一次

```tsx
function AppShell() {
  useEffect(() => {
    loadFromStorage()
    checkAuthToken()
  }, [])

  // ...
}
```

#### ✅ 正例：模块级布尔守卫确保整个应用周期只初始化一次

```tsx
let didInit = false

function AppShell() {
  useEffect(() => {
    if (didInit) return
    didInit = true
    loadFromStorage()
    checkAuthToken()
  }, [])

  // ...
}
```

> **SSR 注意**：仅在浏览器端执行的初始化仍须保留在 `useEffect`（或 `typeof window !== 'undefined'`）内，切勿在服务端模块顶层存放用户级状态。

---

### 8.3 事件监听订阅与最新回调解耦（`useEffectEvent` / Ref 托管）

**影响等级：LOW**（避免外层回调变化导致反复解绑与重绑 `window` 监听器）

#### ❌ 反例：调用方传内联函数时，每次渲染都先 `removeEventListener` 再 `addEventListener`

```tsx
function useWindowEvent(event: string, handler: (e: Event) => void) {
  useEffect(() => {
    window.addEventListener(event, handler)
    return () => window.removeEventListener(event, handler)
  }, [event, handler])
}
```

#### ✅ 正例 A（React 19.2+ / 支持 `useEffectEvent`）：零重订阅且永远执行最新 `handler`

```tsx
import { useEffect, useEffectEvent } from 'react'

function useWindowEvent(event: string, handler: (e: Event) => void) {
  const onEvent = useEffectEvent(handler)

  useEffect(() => {
    window.addEventListener(event, onEvent)
    return () => window.removeEventListener(event, onEvent)
  }, [event])
}
```

#### ✅ 正例 B（React 18 兼容方案）：用 `useRef` 保存最新回调

```tsx
import { useEffect, useLayoutEffect, useRef } from 'react'

function useWindowEvent(event: string, handler: (e: Event) => void) {
  const handlerRef = useRef(handler)

  useLayoutEffect(() => {
    handlerRef.current = handler
  })

  useEffect(() => {
    const listener = (e: Event) => handlerRef.current(e)
    window.addEventListener(event, listener)
    return () => window.removeEventListener(event, listener)
  }, [event])
}
```

---

### 8.4 防抖与定时器副作用用 `useEffectEvent` 保持稳定触发

**影响等级：LOW**（防止父组件每次重渲染重置防抖计时器）

在防抖搜索、轮询或超时提示中，回调 `onSearch` 往往在父组件渲染时变化；把它放进依赖数组会不断清空并重启 `setTimeout`，不放又会拿不到最新闭包。用 `useEffectEvent` 把「何时重启计时器（`query`）」与「到期执行什么（`onSearch`）」彻底分离。

#### ❌ 反例：父组件重渲染产生新 `onSearch`，导致防抖定时器被反复重置

```tsx
function SearchInput({ onSearch }: { onSearch: (q: string) => void }) {
  const [query, setQuery] = useState('')

  useEffect(() => {
    const timeout = setTimeout(() => onSearch(query), 300)
    return () => clearTimeout(timeout)
  }, [query, onSearch])
}
```

#### ✅ 正例：计时器仅随 `query` 重置，回调永远读取最新 `onSearch`

```tsx
import { useEffect, useEffectEvent, useState } from 'react'

function SearchInput({ onSearch }: { onSearch: (q: string) => void }) {
  const [query, setQuery] = useState('')
  const onSearchEvent = useEffectEvent(onSearch)

  useEffect(() => {
    const timeout = setTimeout(() => onSearchEvent(query), 300)
    return () => clearTimeout(timeout)
  }, [query])
}
```

---

## 第二部分：React 19+ API 变更规范

> **版本门槛**：以下规范仅适用于 **React 19 及以上** 项目；若目标仓库仍在 React 18 及以下，保持 `forwardRef` 与 `useContext` 写法。改动前先确认目标项目的 React 版本。

### 1. `ref` 直接作为普通 Prop 传递（不再使用 `forwardRef`）

**影响等级：MEDIUM**（简化组件签名与泛型类型声明）

#### ❌ 反例（React 19 中多余的 `forwardRef` 样板）

```tsx
const ComposerInput = forwardRef<HTMLInputElement, Props>((props, ref) => {
  return <input ref={ref} {...props} />
})
```

#### ✅ 正例（React 19 直接解构 `ref`）

```tsx
function ComposerInput({
  ref,
  ...props
}: Props & { ref?: React.Ref<HTMLInputElement> }) {
  return <input ref={ref} {...props} />
}
```

---

### 2. 用 `use()` 替代 `useContext()`（且支持条件分支内读取）

**影响等级：MEDIUM**（统一读取 Context 与 Promise，打破条件调用限制）

#### ❌ 反例（React 19 中仍受限于 Hook 顶层调用的 `useContext`）

```tsx
const value = useContext(ComposerContext)
```

#### ✅ 正例（使用 `use()`，可在 `if` 早退之后按需读取）

```tsx
import { use } from 'react'

function ComposerBadge({ show }: { show: boolean }) {
  if (!show) return null
  // 与 useContext 不同，use() 允许在条件分支与早退之后调用
  const ctx = use(ComposerContext)
  return <span>{ctx?.state.attachments.length ?? 0}</span>
}
```

---

### 3. 直接把 Context 对象作为 Provider 渲染

在 React 19 中，不再需要 `<MyContext.Provider value={...}>`，可直接写成 `<MyContext value={...}>`：

```tsx
function ComposerProvider({ children, state, actions, meta }: ProviderProps) {
  return (
    <ComposerContext value={{ state, actions, meta }}>
      {children}
    </ComposerContext>
  )
}
```
