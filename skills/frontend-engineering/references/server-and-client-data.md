# 服务端渲染与客户端数据流性能（Server & Client Data）

> **综合影响等级：HIGH（服务端）/ MEDIUM-HIGH（客户端）**  
> 本参考覆盖 10 条服务端 / RSC 性能与安全边界规则（3.1–3.10）和 4 条客户端数据拉取与本地存储规则（4.1–4.4）。

---

## 第一部分：服务端与 RSC 性能（HIGH）

### 3.1 像保护公开 API 一样鉴权 Server Actions

**影响等级：CRITICAL**（防止未授权数据篡改）

带 `'use server'` 的 Server Action 本质上是公开可直调的 HTTP 端点。**绝不能**只依赖 Middleware、Layout 或页面级守卫，必须在每个 Server Action 内部完成**输入校验 → 身份认证 → 权限授权**闭环。

#### ❌ 反例：依赖外层页面隐藏按钮，Action 内无鉴权

```typescript
'use server'

export async function deleteUser(userId: string) {
  // 任何人都能直接 POST 调用该端点！
  await db.user.delete({ where: { id: userId } })
  return { success: true }
}
```

#### ✅ 正例：Action 内部完成完整校验、认证与授权

```typescript
'use server'

import { z } from 'zod'
import { verifySession } from '@/lib/auth'

const updateProfileSchema = z.object({
  userId: z.string().uuid(),
  name: z.string().min(1).max(100),
  email: z.string().email(),
})

export async function updateProfile(data: unknown) {
  // 1. 先校验输入结构
  const validated = updateProfileSchema.parse(data)

  // 2. 验证登录态
  const session = await verifySession()
  if (!session) {
    throw new Error('Unauthorized')
  }

  // 3. 验证资源级权限
  if (session.user.role !== 'admin' && session.user.id !== validated.userId) {
    throw new Error('Forbidden: can only update own profile')
  }

  // 4. 执行变更
  await db.user.update({
    where: { id: validated.userId },
    data: { name: validated.name, email: validated.email },
  })

  return { success: true }
}
```

---

### 3.2 避免 RSC Props 中的重复序列化

**影响等级：LOW–HIGH**（依数据类型而定：基础类型数组为 HIGH，对象数组为 LOW）

RSC → Client 边界的序列化按**对象引用**去重，而非按值去重。同一引用只序列化一次；一旦在服务端调用 `.toSorted()`、`.filter()`、`.map()`、`.slice()`、`[...arr]`、`{...obj}`、`structuredClone()` 产生新引用，就会被重复序列化并翻倍传输。

#### ❌ 反例：服务端派生的数组在边界上被发送两份

```tsx
// RSC：发送 6 个字符串（2 份数组 × 3 项）
<ClientList usernames={usernames} usernamesOrdered={usernames.toSorted()} />
<ClientUsers users={users} active={users.filter((u) => u.active)} />
<ClientProduct product={product} productName={product.name} />
```

#### ✅ 正例：只传原始引用，排序与筛选放到客户端做

```tsx
// RSC：只传输 1 份原始数组
<ClientList usernames={usernames} />

// Client Component
'use client'
function ClientList({ usernames }: { usernames: string[] }) {
  const sorted = useMemo(() => usernames.toSorted(), [usernames])
  // ...
}
```

**嵌套去重差异**：
- `string[]` / `number[]` / `boolean[]`：数组与全部原始值都会完整翻倍（**HIGH 影响**）。
- `object[]`：数组结构翻倍，但内部同一引用的对象会被递归去重（**LOW 影响**）。
- **例外**：当客户端根本不需要原始数据，或转换计算非常昂贵只适合在服务端做时，只传转换后的派生结果即可（但不要同时传原始和派生两份）。

---

### 3.3 禁止用模块级可变状态存放请求级数据

**影响等级：HIGH**（防止并发竞态与跨用户数据泄露）

在 RSC 和 SSR 环境中，同一进程可能并发渲染多个用户请求。模块顶层的可变变量是**进程级共享内存**，绝不是请求级隔离状态。

#### ❌ 反例：并发请求互相覆盖，A 用户看到 B 用户信息

```tsx
let currentUser: User | null = null

export default async function Page() {
  currentUser = await auth()
  return <Dashboard />
}

async function Dashboard() {
  return <div>{currentUser?.name}</div>
}
```

#### ✅ 正例：把请求数据留在渲染树参数（或请求级 `React.cache`）内

```tsx
export default async function Page() {
  const user = await auth()
  return <Dashboard user={user} />
}

function Dashboard({ user }: { user: User | null }) {
  return <div>{user?.name}</div>
}
```

**允许放模块顶层的安全例外**：
- 只读的静态资源或启动时加载一次的不可变配置；
- 显式按完整 key 隔离并带容量/过期策略的跨请求缓存；
- 不持有任何请求/用户可变状态的进程级单例客户端（如 DB 连接池）。

---

### 3.4 跨请求内存 LRU 缓存

**影响等级：HIGH**（消除连续请求间的重复 DB/上游查询）

`React.cache()` 仅在单次请求生命周期内有效。若用户在几秒内连续触发多个接口读取同一热点对象，在常驻进程或共享实例的无服务器环境（如 Fluid Compute）下可用 LRU 缓存跨请求复用。

```typescript
import { LRUCache } from 'lru-cache'

const userCache = new LRUCache<string, User | null>({
  max: 1000,
  ttl: 5 * 60 * 1000, // 5 分钟
})

export async function getUser(id: string) {
  if (userCache.has(id)) {
    return userCache.get(id)!
  }
  const user = await db.user.findUnique({ where: { id } })
  userCache.set(id, user)
  return user
}
```

**部署环境注意**：
- 常驻 Node / Fluid Compute 环境下多并发请求共享实例内存，无需引入外部 Redis 即可命中；
- 传统完全隔离的无服务器冷启动环境或多副本强一致失效场景，应使用 Redis 等集中式缓存。

---

### 3.5 将静态 I/O 提升到模块顶层

**影响等级：HIGH**（避免每次请求重复读磁盘或拉取静态资源）

路由处理器或 OG 图像生成中用到的字体、Logo、静态模板、不可变配置，应提升到模块顶层在首次加载时读取一次，而非在每次 `GET` 中重复读取。

#### ❌ 反例：每次请求都重新读取字体和模板文件

```typescript
export async function GET() {
  const fontData = await fetch(new URL('./fonts/Inter.ttf', import.meta.url))
    .then((res) => res.arrayBuffer())
  const logoData = await fetch(new URL('./images/logo.png', import.meta.url))
    .then((res) => res.arrayBuffer())
  return buildOgImage(fontData, logoData)
}
```

#### ✅ 正例 A：模块顶层启动异步 Promise，请求内 `await` 已完成的 Promise

```typescript
import fs from 'node:fs/promises'

const fontDataPromise = fetch(new URL('./fonts/Inter.ttf', import.meta.url))
  .then((res) => res.arrayBuffer())
const templatePromise = fs.readFile('./template.html', 'utf-8')

export async function GET() {
  const [fontData, template] = await Promise.all([fontDataPromise, templatePromise])
  return renderResponse(fontData, template)
}
```

#### ✅ 正例 B：模块顶层同步读取静态小文件

```typescript
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

// 仅在模块首次初始化时阻塞一次
const fontData = readFileSync(join(process.cwd(), 'public/fonts/Inter.ttf'))
const logoData = readFileSync(join(process.cwd(), 'public/images/logo.png'))
```

**何时不要提升**：因请求/用户而异的文件、运行期可能热更新的文件（改用带 TTL 缓存）、会长期占满内存的超大文件、不宜常驻内存的敏感凭据。

---

### 3.6 最小化 RSC 边界序列化体积

**影响等级：HIGH**（直接减小首屏 HTML 体积与 RSC Payload 传输时间）

跨越 Server → Client 边界传入的 props 会被全量序列化并内嵌进 HTML 及后续 RSC 载荷。只传客户端组件真正用到的字段，切忌把 50 个字段的整条 ORM 记录透传下去（还容易误泄隐私字段）。

#### ❌ 反例：整条 50 字段的用户对象全量序列化到浏览器

```tsx
async function Page() {
  const user = await fetchUser() // 包含 50 个字段
  return <Profile user={user} />
}

'use client'
function Profile({ user }: { user: User }) {
  return <div>{user.name}</div> // 实际只用了 1 个字段
}
```

#### ✅ 正例：只传客户端实际消费的 1 个字段

```tsx
async function Page() {
  const user = await fetchUser()
  return <Profile name={user.name} />
}

'use client'
function Profile({ name }: { name: string }) {
  return <div>{name}</div>
}
```

---

### 3.7 用组件组合并行化 RSC 数据拉取

**影响等级：CRITICAL**（消除服务端组件树串行瀑布）

父级 async RSC 在 `await` 完成之前，React 不会开始渲染其 JSX 里的子级 async RSC。通过把独立拉取拆成兄弟组件（或利用 `children` 插槽），让 React 并发执行它们的数据请求。

#### ❌ 反例：`Sidebar` 被迫等 `Page` 的 `fetchHeader()` 完成才开始拉取

```tsx
export default async function Page() {
  const header = await fetchHeader()
  return (
    <div>
      <div>{header}</div>
      <Sidebar />
    </div>
  )
}

async function Sidebar() {
  const items = await fetchSidebarItems()
  return <nav>{items.map(renderItem)}</nav>
}
```

#### ✅ 正例：兄弟组件并发拉取（也可用 `<Layout><Sidebar /></Layout>` 组合）

```tsx
async function Header() {
  const data = await fetchHeader()
  return <div>{data}</div>
}

async function Sidebar() {
  const items = await fetchSidebarItems()
  return <nav>{items.map(renderItem)}</nav>
}

export default function Page() {
  return (
    <div>
      <Header />
      <Sidebar />
    </div>
  )
}
```

---

### 3.8 嵌套数据拉取按项流水线并行

**影响等级：CRITICAL**（防止单个慢请求拖死整批二阶段查询）

存在两层依赖（先查列表项，再查每项关联详情）时，不要把两层拆成两个全局 `Promise.all` 栅栏；把二阶段查询直接链在每个元素的 Promise 上。

#### ❌ 反例：100 条会话里 1 条极慢，其余 99 条作者全被挡住

```tsx
const chats = await Promise.all(chatIds.map((id) => getChat(id)))
const chatAuthors = await Promise.all(chats.map((chat) => getUser(chat.author)))
```

#### ✅ 正例：每条记录独立流水线推进 `getChat → getUser`

```tsx
const chatAuthors = await Promise.all(
  chatIds.map((id) => getChat(id).then((chat) => getUser(chat.author)))
)
```

---

### 3.9 使用 `React.cache()` 做单请求内去重

**影响等级：MEDIUM**（跨多层组件树复用同一次鉴权与 DB 查询）

在 Next.js 中 `fetch()` 已自动按请求去重，但 Prisma/Drizzle 数据库查询、鉴权检查、文件系统读取与重计算仍需 `React.cache()` 去重。

```typescript
import { cache } from 'react'

export const getCurrentUser = cache(async () => {
  const session = await auth()
  if (!session?.user?.id) return null
  return db.user.findUnique({ where: { id: session.user.id } })
})
```

#### ⚠️ 严防陷阱：不要传内联对象字面量作为 `React.cache()` 参数
`React.cache()` 按浅比较（`Object.is`）判断是否命中缓存，内联对象每次都是新引用，命中率永远为 0%：

```typescript
const getUserById = cache(async (uid: number) => {
  return db.user.findUnique({ where: { id: uid } })
})

// ❌ 传内联对象：{ uid: 1 } !== { uid: 1 }，每次都未命中
// ✅ 优先传基础类型参数（number / string），或复用同一对象引用
getUserById(1)
getUserById(1) // 命中缓存
```

---

### 3.10 使用 `after()` 执行非阻塞响应后任务

**影响等级：MEDIUM**（立刻返回响应，把日志/埋点/通知移到后台）

在 Route Handler、Server Action 或 Server Component 中，审计日志、埋点上报、发送通知、缓存清理等副作用不应拖慢客户端收到响应的时间。

#### ❌ 反例：写日志阻塞接口响应

```tsx
export async function POST(request: Request) {
  await updateDatabase(request)
  const userAgent = request.headers.get('user-agent') || 'unknown'
  await logUserAction({ userAgent }) // 阻塞响应
  return Response.json({ status: 'success' })
}
```

#### ✅ 正例：用 `after()` 在响应发出后异步执行

```tsx
import { after } from 'next/server'
import { headers, cookies } from 'next/headers'

export async function POST(request: Request) {
  await updateDatabase(request)

  after(async () => {
    const userAgent = (await headers()).get('user-agent') || 'unknown'
    const sessionCookie = (await cookies()).get('session-id')?.value || 'anonymous'
    await logUserAction({ sessionCookie, userAgent })
  })

  return Response.json({ status: 'success' })
}
```

> 即使响应出错或发生重定向，`after()` 注册的回调依然会执行；适用于埋点、审计、通知、失效刷新和清理任务。

---

## 第二部分：客户端数据拉取与本地存储（MEDIUM-HIGH）

### 4.1 去重全局事件监听器

**影响等级：LOW**（N 个组件实例共享 1 个 `window` 监听器）

多个组件实例或自定义 Hook 同时注册 `window.addEventListener('keydown', ...)` 会线性叠加监听器开销。用模块级注册表配合 `useSWRSubscription`（或引用计数单例）合并为单一全局监听。

#### ❌ 反例：N 次调用挂 N 个 `keydown` 监听器

```tsx
function useKeyboardShortcut(key: string, callback: () => void) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.metaKey && e.key === key) callback()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [key, callback])
}
```

#### ✅ 正例：模块级 Map 路由分发 + 单例订阅

```tsx
import useSWRSubscription from 'swr/subscription'

const keyCallbacks = new Map<string, Set<() => void>>()

function useKeyboardShortcut(key: string, callback: () => void) {
  useEffect(() => {
    if (!keyCallbacks.has(key)) keyCallbacks.set(key, new Set())
    keyCallbacks.get(key)!.add(callback)

    return () => {
      const set = keyCallbacks.get(key)
      if (!set) return
      set.delete(callback)
      if (set.size === 0) keyCallbacks.delete(key)
    }
  }, [key, callback])

  useSWRSubscription('global-keydown', () => {
    const handler = (e: KeyboardEvent) => {
      if (e.metaKey && keyCallbacks.has(e.key)) {
        keyCallbacks.get(e.key)!.forEach((cb) => cb())
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  })
}
```

---

### 4.2 滚动与触控事件使用 Passive 监听器

**影响等级：MEDIUM**（消除主线程阻塞导致的滚动延迟）

浏览器默认要等 `touchstart` / `touchmove` / `wheel` 回调执行完毕，确认未调用 `preventDefault()` 后才开始合成线程滚动。只要不拦截默认滚动，务必传 `{ passive: true }`。

#### ❌ 反例：阻塞浏览器立即滚动

```typescript
document.addEventListener('touchstart', handleTouch)
document.addEventListener('wheel', handleWheel)
```

#### ✅ 正例：显式声明被动监听

```typescript
useEffect(() => {
  const handleTouch = (e: TouchEvent) => trackTouch(e.touches[0].clientX)
  const handleWheel = (e: WheelEvent) => trackWheel(e.deltaY)

  document.addEventListener('touchstart', handleTouch, { passive: true })
  document.addEventListener('wheel', handleWheel, { passive: true })

  return () => {
    document.removeEventListener('touchstart', handleTouch)
    document.removeEventListener('wheel', handleWheel)
  }
}, [])
```

- **应该用 passive**：埋点统计、滚动位置读取、日志记录等不调用 `preventDefault()` 的监听；
- **不要用 passive**：自定义手势缩放、自定义横向滑动拦截等确实需要 `preventDefault()` 的交互。

---

### 4.3 使用 SWR / Query 层自动请求去重与缓存

**影响等级：MEDIUM-HIGH**（消除多组件重复拉取与手工竞态）

手写 `useEffect + fetch` 既不会在多实例间去重，也缺少缓存、失焦重验、错误重试与过时请求丢弃。

#### ❌ 反例：每个挂载实例各自发一次请求

```tsx
function UserList() {
  const [users, setUsers] = useState<User[]>([])
  useEffect(() => {
    fetch('/api/users')
      .then((r) => r.json())
      .then(setUsers)
  }, [])
}
```

#### ✅ 正例：SWR 自动跨组件共享请求、缓存与变更触发

```tsx
import useSWR from 'swr'
import useSWRImmutable from 'swr/immutable'
import useSWRMutation from 'swr/mutation'

// 普通列表：多实例共享同一份请求
function UserList() {
  const { data: users } = useSWR('/api/users', fetcher)
  // ...
}

// 静态配置：禁用自动重验
function StaticConfig() {
  const { data } = useSWRImmutable('/api/config', fetcher)
  // ...
}

// 写操作：显式触发变更
function UpdateButton() {
  const { trigger, isMutating } = useSWRMutation('/api/user', updateUser)
  return (
    <button type="button" disabled={isMutating} onClick={() => trigger()}>
      更新
    </button>
  )
}
```

---

### 4.4 给 `localStorage` 数据加版本号、最小化字段与异常保护

**影响等级：MEDIUM**（防数据结构升级崩坏、防存储超限、防误存敏感信息）

无痕模式（Safari/Firefox）、配额已满或浏览器禁用存储时，`localStorage.getItem/setItem` 会直接抛出异常。必须同时做到：**键名带版本后缀 + 只存必要最小字段 + 全部 `try/catch` + 明确迁移路径**。

#### ❌ 反例：无版本、全量写入、无异常保护

```typescript
localStorage.setItem('userConfig', JSON.stringify(fullUserObject))
const data = localStorage.getItem('userConfig')
```

#### ✅ 正例：版本化键名 + 最小化字段 + 迁移 + `try/catch`

```typescript
const CONFIG_VERSION = 'v2'
const CONFIG_KEY = `userConfig:${CONFIG_VERSION}`

interface UserConfig {
  theme: 'light' | 'dark'
  language: string
}

function saveConfig(config: UserConfig) {
  try {
    localStorage.setItem(CONFIG_KEY, JSON.stringify(config))
  } catch {
    // 兼容无痕模式、存储配额耗尽或被策略禁用
  }
}

function loadConfig(): UserConfig | null {
  try {
    const raw = localStorage.getItem(CONFIG_KEY)
    return raw ? (JSON.parse(raw) as UserConfig) : null
  } catch {
    return null
  }
}

function migrateConfigV1ToV2() {
  try {
    const v1 = localStorage.getItem('userConfig:v1')
    if (!v1) return
    const old = JSON.parse(v1)
    saveConfig({
      theme: old.darkMode ? 'dark' : 'light',
      language: old.lang ?? 'zh-CN',
    })
    localStorage.removeItem('userConfig:v1')
  } catch {
    // 忽略损坏的旧数据，按默认值恢复
  }
}
```

**只存最小必要字段**：服务端返回 20+ 字段的用户对象时，仅挑选界面真正需要的 2–3 个偏好项（如 `theme`、`notifications`），严禁把 Token、PII 或内部标志整包塞进 `localStorage`。
