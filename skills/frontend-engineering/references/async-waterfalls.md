# 消除异步瀑布（Eliminating Waterfalls）

> **综合影响等级：CRITICAL（最高优先级）**  
> 异步瀑布是前端与全栈 React 应用的第一性能杀手。每一次无依赖的串行 `await` 都会叠加一次完整网络往返延迟（RTT）；消除瀑布往往能带来 2–10× 的端到端响应提速。

---

## 规则总览

| 编号 | 规则 | 影响等级 | 核心动作 |
| --- | --- | --- | --- |
| 1.1 | 先判廉价同步条件，再 `await` 异步标志 | HIGH | 避免冷路径白跑网络/DB/特性开关请求 |
| 1.2 | 将 `await` 下沉到真正使用数据的分支 | HIGH | 提前返回路径不被无关 I/O 阻塞 |
| 1.3 | 基于依赖图的最小等待并行化 | CRITICAL | 部分依赖场景下让各任务在最早时刻启动 |
| 1.4 | 消除 API Route / Server Action 中的瀑布链 | CRITICAL | 先统一启动独立 Promise，按需顺序 `await` |
| 1.5 | 独立异步操作统一 `Promise.all()` | CRITICAL | 将 N 次串行往返压缩为 1 次并行往返 |
| 1.6 | 战略性划分 Suspense 边界流式渲染 | HIGH | 外层壳子立即首绘，慢数据局部流式填充 |

---

## 1.1 先判廉价同步条件，再 `await` 异步标志

**影响等级：HIGH**（同步守卫已不满足时，直接省去全部异步开销）

当分支同时依赖一个**廉价同步条件**（本地 props、请求元数据、已有内存状态）和一个需要 `await` 的异步标志/远程配置时，务必先评估同步条件。否则即便复合条件不可能成立，也会在冷路径白白发起网络、特性开关服务、`React.cache` 或数据库查询。

### ❌ 反例：无论同步条件是否成立都先等待异步标志

```typescript
const someFlag = await getFlag()

if (someFlag && someCondition) {
  // ...
}
```

### ✅ 正例：先短路廉价同步条件，通过后再 `await`

```typescript
if (someCondition) {
  const someFlag = await getFlag()
  if (someFlag) {
    // ...
  }
}
```

### 何时不适用
- `someCondition` 本身计算昂贵，而 `getFlag()` 几乎零成本（如本地内存命中）；
- `someCondition` 的求值依赖 `someFlag` 的返回值；
- 业务要求必须按固定顺序触发副作用（例如埋点、审计或预热）。

---

## 1.2 将 `await` 下沉到真正使用数据的分支

**影响等级：HIGH**（避免阻塞不需要该数据的代码路径）

不要在函数入口急切地 `await` 后续可能用不到的数据；把 `await` 移进实际消费该结果的分支内，让早退路径立刻返回。

### ❌ 反例：跳过分支也被上游 `await` 阻塞

```typescript
async function handleRequest(userId: string, skipProcessing: boolean) {
  const userData = await fetchUserData(userId)

  if (skipProcessing) {
    // 直接返回，却仍白白等待了 userData
    return { skipped: true }
  }

  // 只有这里才真正用到 userData
  return processUserData(userData)
}
```

### ✅ 正例：仅在需要数据的分支中执行 `await`

```typescript
async function handleRequest(userId: string, skipProcessing: boolean) {
  if (skipProcessing) {
    // 零等待直接返回
    return { skipped: true }
  }

  const userData = await fetchUserData(userId)
  return processUserData(userData)
}
```

### 进阶对比：资源存在性校验优先于权限查询

```typescript
// ❌ 反例：资源不存在时仍白查一次权限
async function updateResource(resourceId: string, userId: string) {
  const permissions = await fetchPermissions(userId)
  const resource = await getResource(resourceId)

  if (!resource) {
    return { error: 'Not found' }
  }
  if (!permissions.canEdit) {
    return { error: 'Forbidden' }
  }
  return await updateResourceData(resource, permissions)
}

// ✅ 正例：按命中概率与成本排序，早退不阻塞（若两者都高频命中，则改为并发启动）
async function updateResource(resourceId: string, userId: string) {
  const resource = await getResource(resourceId)

  if (!resource) {
    return { error: 'Not found' }
  }

  const permissions = await fetchPermissions(userId)

  if (!permissions.canEdit) {
    return { error: 'Forbidden' }
  }

  return await updateResourceData(resource, permissions)
}
```

### 适用与权衡
- 当早退分支命中率高，或被延迟的操作代价极高时收益最大。
- 若两个分支几乎总是同时执行（例如 99% 请求都存在资源且需查权限），则应改用 1.4 / 1.5 的并发启动策略而非串行等待。

---

## 1.3 基于依赖图的最小等待并行化

**影响等级：CRITICAL**（2–10× 性能提升）

当一组异步任务存在**部分依赖**（如 `profile` 只依赖 `user`，不依赖 `config`）时，用 `Promise.all([fetchUser(), fetchConfig()])` 再去 `fetchProfile(user.id)` 会让 `profile` 无谓等待较慢的 `config`。应让每个任务在其直接依赖就绪的最早时刻立即启动。

### ❌ 反例：`profile` 被无关的 `config` 拖慢

```typescript
const [user, config] = await Promise.all([
  fetchUser(),
  fetchConfig(),
])
const profile = await fetchProfile(user.id)
```

### ✅ 正例 A：原生 Promise 链编排（零额外依赖）

```typescript
const userPromise = fetchUser()
const profilePromise = userPromise.then((user) => fetchProfile(user.id))

const [user, config, profile] = await Promise.all([
  userPromise,
  fetchConfig(),
  profilePromise,
])
```

### ✅ 正例 B：复杂依赖图使用 `better-all`

```typescript
import { all } from 'better-all'

const { user, config, profile } = await all({
  async user() {
    return fetchUser()
  },
  async config() {
    return fetchConfig()
  },
  async profile() {
    return fetchProfile((await this.$.user).id)
  },
})
```

### 要点
- 先统一创建所有起始 Promise，依赖项通过 `.then()` 或 `this.$` 接续，最后统一 `Promise.all` 收口。
- 注意给独立启动的 Promise 接上最终 `await`（或统一 `Promise.all`），避免提前 reject 导致 `UnhandledPromiseRejection`。

---

## 1.4 消除 API Route / Server Action 中的瀑布链

**影响等级：CRITICAL**（2–10× 性能提升）

在 API Route、Server Action 或数据加载器中，哪怕某个结果要到后面才用，也要在入口处**立即发起所有无前置依赖的异步请求**，再按依赖顺序依次 `await`。

### ❌ 反例：`config` 等 `auth`，`data` 等两者

```typescript
export async function GET(request: Request) {
  const session = await auth()
  const config = await fetchConfig()
  const data = await fetchData(session.user.id)
  return Response.json({ data, config })
}
```

### ✅ 正例：`auth` 与 `config` 同步起跑，拿到 `session` 后立刻并发 `data`

```typescript
export async function GET(request: Request) {
  const sessionPromise = auth()
  const configPromise = fetchConfig()
  const session = await sessionPromise
  const [config, data] = await Promise.all([
    configPromise,
    fetchData(session.user.id),
  ])
  return Response.json({ data, config })
}
```

### 注意事项
- 如果 `auth()` 失败后会提前返回 401，而 `fetchConfig()` 涉及敏感数据或极高数据库成本，务必先鉴权或给 `configPromise` 挂载 `.catch(() => null)` 避免未捕获拒绝。

---

## 1.5 独立异步操作统一 `Promise.all()`

**影响等级：CRITICAL**（2–10× 性能提升）

彼此没有数据依赖的异步请求绝对不要顺序 `await`，用 `Promise.all()`（或允许局部失败时用 `Promise.allSettled()`）压缩为单次往返。

### ❌ 反例：串行 3 次网络往返

```typescript
const user = await fetchUser()
const posts = await fetchPosts()
const comments = await fetchComments()
```

### ✅ 正例：并行 1 次网络往返

```typescript
const [user, posts, comments] = await Promise.all([
  fetchUser(),
  fetchPosts(),
  fetchComments(),
])
```

### 容错变体
若其中一个非关键模块允许降级而不影响整页渲染，使用 `Promise.allSettled()` 分别处理 `fulfilled` 与 `rejected`，不要因为次要请求报错拖垮主视图。

---

## 1.6 战略性划分 Suspense 边界流式渲染

**影响等级：HIGH**（显著加速首屏绘制与外层交互就绪）

不要在顶层异步页面组件里 `await` 全部数据后才返回 JSX。把页面静态壳子（侧栏、顶栏、底栏）保留在同步渲染树中，用 `<Suspense>` 包裹真正依赖慢数据的子组件，实现流式展示。

### ❌ 反例：整页布局被中部慢数据完全阻塞

```tsx
async function Page() {
  const data = await fetchData() // 阻塞 Sidebar / Header / Footer 渲染

  return (
    <div>
      <div>Sidebar</div>
      <div>Header</div>
      <div>
        <DataDisplay data={data} />
      </div>
      <div>Footer</div>
    </div>
  )
}
```

### ✅ 正例 A：局部异步组件 + `<Suspense>` 边界

```tsx
function Page() {
  return (
    <div>
      <div>Sidebar</div>
      <div>Header</div>
      <div>
        <Suspense fallback={<Skeleton />}>
          <DataDisplay />
        </Suspense>
      </div>
      <div>Footer</div>
    </div>
  )
}

async function DataDisplay() {
  const data = await fetchData() // 只挂起当前子树
  return <div>{data.content}</div>
}
```

### ✅ 正例 B：顶层预发起 Promise，跨组件共享并用 React 19 `use()` 解包

```tsx
import { Suspense, use } from 'react'

function Page() {
  // 立即启动请求，不在 Page 顶部 await
  const dataPromise = fetchData()

  return (
    <div>
      <div>Sidebar</div>
      <div>Header</div>
      <Suspense fallback={<Skeleton />}>
        <DataDisplay dataPromise={dataPromise} />
        <DataSummary dataPromise={dataPromise} />
      </Suspense>
      <div>Footer</div>
    </div>
  )
}

function DataDisplay({ dataPromise }: { dataPromise: Promise<Data> }) {
  const data = use(dataPromise)
  return <div>{data.content}</div>
}

function DataSummary({ dataPromise }: { dataPromise: Promise<Data> }) {
  const data = use(dataPromise) // 复用同一份 Promise，不重复请求
  return <div>{data.summary}</div>
}
```

### 何时不适用 `<Suspense>` 拆分
- **影响主布局决策的关键数据**：例如决定整页结构或重定向的数据；
- **首屏 SEO 关键内容**：需要同步直出在初始 HTML 中的核心文案；
- **极快的小查询**（如 <10ms 的内存/边缘缓存）：拆分 Suspense 的骨架闪烁与调度开销反而不划算；
- **零布局偏移（CLS）优先场景**：骨架屏与真实内容高度差异大、会引起明显跳动且无法预设稳定占位尺寸时。

**权衡原则**：更快的首屏绘制 vs 潜在布局偏移（CLS）。骨架屏必须尽量匹配真实内容的几何尺寸。
