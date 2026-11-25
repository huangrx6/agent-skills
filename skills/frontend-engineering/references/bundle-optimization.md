# 包体大小与按需加载优化（Bundle Size Optimization）

> **综合影响等级：CRITICAL**  
> 首屏 JavaScript 体积直接决定下载、解析、编译与水合耗时，是影响 TTI（可交互时间）与 LCP（最大内容绘制）的核心瓶颈。

---

## 规则总览

| 编号 | 规则 | 影响等级 | 核心动作 |
| --- | --- | --- | --- |
| 2.1 | 避免 Barrel File（桶文件）全量导入 | CRITICAL | 消除 200–800ms 冷启动与千级模块加载 |
| 2.2 | 按功能激活状态条件懒加载大模块 | HIGH | 特性未开启时不加载大数据/重模块，且防 SSR 误打包 |
| 2.3 | 延后加载非关键第三方库 | MEDIUM | 统计、日志、监控在水合后再加载 |
| 2.4 | 重型组件采用动态导入 | CRITICAL | 富文本/代码编辑器/图表库移出主包 |
| 2.5 | 保持动态导入与文件路径可静态分析 | HIGH | 用显式映射表与字面量路径，防止打包器兜底全量打入 |
| 2.6 | 基于用户意图预加载重模块 | MEDIUM | `hover` / `focus` / 特性开关触发静默预取 |

---

## 2.1 避免 Barrel File（桶文件）全量导入

**影响等级：CRITICAL**（每次冷启动 200–800ms 导入损耗，开发构建慢数秒）

**Barrel file** 指把海量模块统一 `export * from './...'` 再导出的入口文件（如 `index.js`）。热门图标库与组件库的入口文件常包含上万条重导出，直接导入会迫使运行时或开发服务器解析数千个未使用的文件。

**为什么 Tree-shaking 救不了你**：
- 当依赖被标记为 external（不打包，如 SSR/Node 环境）时，构建工具根本无法做 tree-shaking，运行时会真实加载整个入口图；
- 即便全量打包以启用 tree-shaking，构建工具也必须解析整棵模块依赖图，导致 dev 启动、HMR 和 CI 构建显著变慢。

### ❌ 反例：触发整库桶文件解析

```tsx
import { Check, X, Menu } from 'lucide-react'
// 未优化时加载 1,583 个模块，dev 启动多耗 ~2.8s，每次冷启动多耗 200–800ms

import { Button, TextField } from '@mui/material'
// 未优化时加载 2,225 个模块，dev 启动多耗 ~4.2s
```

### ✅ 正例 A：Next.js 13.5+ 使用 `optimizePackageImports`（推荐）

```js
// next.config.mjs
export default {
  experimental: {
    optimizePackageImports: ['lucide-react', '@mui/material', 'date-fns'],
  },
}
```

```tsx
// 保持标准命名导入，Next.js 在编译期自动改写为直达源文件的导入
// 完整保留 TypeScript 类型提示与编辑器自动补全
import { Check, X, Menu } from 'lucide-react'
```

### ✅ 正例 B：非 Next.js 项目（如 Vite / Webpack）直接导入子路径

```tsx
import Button from '@mui/material/Button'
import TextField from '@mui/material/TextField'
// 只加载实际用到的 2 个模块
```

> **TypeScript 类型警告**：部分库（特别是 `lucide-react`）的深层子路径并未附带 `.d.ts` 声明，直接写 `lucide-react/dist/esm/icons/check` 在 `strict` / `noImplicitAny` 下会退化为隐式 `any`。优先使用框架内置的 `optimizePackageImports`，或先确认目标子路径导出了完整类型定义。

**高频受影响包清单**：`lucide-react`、`@mui/material`、`@mui/icons-material`、`@tabler/icons-react`、`react-icons`、`@headlessui/react`、`@radix-ui/react-*`、`lodash`、`ramda`、`date-fns`、`rxjs`、`react-use`。  
**实测收益区间**：开发启动快 15–70%、生产构建快约 28%、无服务器冷启动快约 40%。

---

## 2.2 按功能激活状态条件懒加载大模块

**影响等级：HIGH**（仅在特性开启时拉取大数据或重型逻辑）

体积庞大的静态数据表、动画帧序列、编解码器或可选功能模块，不要在顶层静态 `import`，而是在功能真正激活时动态 `import()`。

### ✅ 正例：特性开启时在浏览器端按需加载

```tsx
function AnimationPlayer({
  enabled,
  setEnabled,
}: {
  enabled: boolean
  setEnabled: React.Dispatch<React.SetStateAction<boolean>>
}) {
  const [frames, setFrames] = useState<Frame[] | null>(null)

  useEffect(() => {
    if (enabled && !frames && typeof window !== 'undefined') {
      import('./animation-frames.js')
        .then((mod) => setFrames(mod.frames))
        .catch(() => setEnabled(false))
    }
  }, [enabled, frames, setEnabled])

  if (!frames) return <Skeleton />
  return <Canvas frames={frames} />
}
```

**关键细节**：`typeof window !== 'undefined'` 守卫能让打包器在 SSR 构建阶段裁剪掉该动态导入，避免把它打进服务端 bundle 拖慢构建与冷启动。

---

## 2.3 延后加载非关键第三方库

**影响等级：MEDIUM**（水合后再加载，不阻塞首屏交互）

埋点分析、错误监控、会话录制、客服浮窗等非核心第三方脚本不需要参与首屏渲染和水合。

### ❌ 反例：同步打入根布局主包

```tsx
import { Analytics } from '@vercel/analytics/react'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html>
      <body>
        {children}
        <Analytics />
      </body>
    </html>
  )
}
```

### ✅ 正例：关闭 SSR 并在水合后懒加载

```tsx
import dynamic from 'next/dynamic'

const Analytics = dynamic(
  () => import('@vercel/analytics/react').then((m) => m.Analytics),
  { ssr: false }
)

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html>
      <body>
        {children}
        <Analytics />
      </body>
    </html>
  )
}
```

> **纯 React / Vite 项目等价写法**：用 `React.lazy(() => import(...))` 配合 `<Suspense fallback={null}>`，或在根组件挂载后通过 `requestIdleCallback` 触发初始化导入。

---

## 2.4 重型组件采用动态导入

**影响等级：CRITICAL**（直接改善 TTI 与 LCP）

首屏立即可见区域之外的重型组件（Monaco 代码编辑器、PDF 阅读器、富文本编辑器、复杂图表、Markdown 渲染引擎）一律拆出主 chunk。

### ❌ 反例：~300KB 的 Monaco 直接打进主包

```tsx
import { MonacoEditor } from './monaco-editor'

function CodePanel({ code }: { code: string }) {
  return <MonacoEditor value={code} />
}
```

### ✅ 正例 A：Next.js 使用 `next/dynamic`

```tsx
import dynamic from 'next/dynamic'

const MonacoEditor = dynamic(
  () => import('./monaco-editor').then((m) => m.MonacoEditor),
  { ssr: false, loading: () => <EditorSkeleton /> }
)

function CodePanel({ code }: { code: string }) {
  return <MonacoEditor value={code} />
}
```

### ✅ 正例 B：Vite / 标准 React 使用 `React.lazy` + `Suspense`

```tsx
import { lazy, Suspense } from 'react'

const MonacoEditor = lazy(() =>
  import('./monaco-editor').then((m) => ({ default: m.MonacoEditor }))
)

function CodePanel({ code }: { code: string }) {
  return (
    <Suspense fallback={<EditorSkeleton />}>
      <MonacoEditor value={code} />
    </Suspense>
  )
}
```

---

## 2.5 保持动态导入与文件路径可静态分析

**影响等级：HIGH**（防止打包器与文件追踪把整个目录误打入产物）

打包工具（Vite、Webpack、esbuild、Rollup、Next.js Output File Tracing）依赖编译期静态分析确定可达文件集合。一旦把路径藏进变量或用字符串拼接动态构造，构建工具要么告警无法分析，要么被迫把整棵目录树打包/追踪进去，造成**服务端包体暴涨、构建变慢、冷启动恶化、内存飙升**。

### ❌ 反例 1：从字符串映射表间接 `import(var)`

```ts
const PAGE_MODULES = {
  home: './pages/home',
  settings: './pages/settings',
} as const

// 打包器无法静态确认 PAGE_MODULES[pageName] 的字面量集合
const Page = await import(PAGE_MODULES[pageName])
```

### ✅ 正例 1：改用显式 loader 函数映射表，每个调用点都是字面量

```ts
const PAGE_MODULES = {
  home: () => import('./pages/home'),
  settings: () => import('./pages/settings'),
} as const

const Page = await PAGE_MODULES[pageName]()
```

### ❌ 反例 2：即便是 2 值枚举拼接也会破坏静态路径追踪

```ts
// Next.js / 打包器文件追踪会把整个 content/ 目录全部纳入输出
const baseDir = path.join(process.cwd(), 'content/' + contentKind)
```

### ✅ 正例 2：在调用点写明每个完整的字面量路径

```ts
const baseDir =
  kind === ContentKind.Blog
    ? path.join(process.cwd(), 'content/blog')
    : path.join(process.cwd(), 'content/docs')
```

---

## 2.6 基于用户意图预加载重模块

**影响等级：MEDIUM**（兼顾小首屏包体与接近零感知的交互延迟）

代码拆分后，首次点击打开编辑器/弹窗可能出现短暂加载等待。利用悬停（`onMouseEnter`）、键盘聚焦（`onFocus`）或特性开关状态提前触发 `import()`，浏览器会把 chunk 提前缓存下来。

### ✅ 正例 A：在按钮悬停与键盘聚焦时预加载

```tsx
function EditorButton({ onClick }: { onClick: () => void }) {
  const preload = () => {
    if (typeof window !== 'undefined') {
      void import('./monaco-editor')
    }
  }

  return (
    <button
      type="button"
      onMouseEnter={preload}
      onFocus={preload}
      onClick={onClick}
    >
      打开编辑器
    </button>
  )
}
```

### ✅ 正例 B：特性开关开启时后台静默预热

```tsx
function FlagsProvider({ children, flags }: Props) {
  useEffect(() => {
    if (flags.editorEnabled && typeof window !== 'undefined') {
      void import('./monaco-editor').then((mod) => mod.init())
    }
  }, [flags.editorEnabled])

  return <FlagsContext value={flags}>{children}</FlagsContext>
}
```

**细节**：始终保留 `typeof window !== 'undefined'` 守卫，防止预加载语句把客户端重型模块牵连进服务端包体。
