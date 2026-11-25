---
name: frontend-engineering
description: >-
  Use this skill to build or refactor React/TypeScript UI components, design compound component
  composition and state ownership, eliminate async waterfalls, optimize bundle size, RSC/client
  data fetching, re-renders, rendering and JS hot paths, engineer scoped CSS with design tokens,
  and systematically debug frontend bugs.
  触发：前端 React/TypeScript 组件开发与重构、复合组件与状态架构、异步瀑布与包体优化、RSC/SWR 性能治理、重渲染与 JS 热点优化、CSS 作用域防冲突、前端 Bug 根因调试。
  Do NOT use for: visual/aesthetic direction alone (→ ui-design-craft),
  backend/main-process/DB architecture (→ arch-backend-craft),
  standalone TDD workflow (→ tdd-testing), black-box browser QA sign-off (→ ui-qa-acceptance),
  or repo lint/CI baseline setup (→ repo-baseline).
  不适用于纯视觉审美评审、后端与数据库架构设计、黑盒浏览器验收或仓库基线初始化。
compatibility: Requires project frontend toolchain (Node.js/TypeScript/React/bundler) when building, testing, or verifying changes.
---

# 前端工程实现、性能优化与根因调试

面向 React / TypeScript / Next.js / Vite 前端工程的旗舰级实战规范，完整融合**异步瀑布消除、包体拆分、服务端与客户端数据流、重渲染治理、渲染与 JS 热点、高级模式与 React 19、复合组件架构、作用域 CSS 与交互健壮性、以及四阶段根因调试**。

核心目标：**对齐既有体系、按影响级别治本、组合代替开关泥潭、证据驱动根因修复。**

---

## 一、开工前工作闸门（不可跳过）

动手修改任何前端代码前，先完成四项对齐检查：

1. **检索既有资产**：先在目标仓库查找已有共享组件、hooks、纯函数模型与 Design Tokens；同类模式直接复用或抽象，禁止复制第二套近似组件或样式。
2. **确认运行环境与版本**：核对 React 版本（是否 React 19+，决定是否用 `ref` 普通 prop、`use()`、`useEffectEvent`）、是否启用 React Compiler、是否使用 Next.js App Router / RSC 或 Vite SPA。
3. **划清目录与 CSS 边界**：UI 组件、自定义 hooks、纯 TypeScript 模型与局部 CSS 各归其位；新增或修改任何 CSS 类名前，先全仓检索同名选择器，防后加载覆盖。
4. **锁定验证入口**：明确项目的受影响前端单测（如 `*.spec.ts` / `*.spec.mjs`）、类型检查与构建命令，所有改动必须经其验证。

---

## 二、性能优化优先级闸门（先大后小）

做性能治理时严格按影响级别自上而下排查，**禁止跳过高优先级瓶颈去抠低收益微优化**：

1. **CRITICAL — 消除异步瀑布与缩减首屏包体**：并行化无依赖 `await`、把重型组件移出主包、消灭 Barrel File 全量导入（单次即可省去数百毫秒至数秒）。
2. **HIGH — 服务端/RSC 边界与安全**：Server Action 内部鉴权、最小化 RSC 序列化体积、兄弟组件并行拉取、提升静态 I/O、长列表 `content-visibility: auto`。
3. **MEDIUM-HIGH / MEDIUM — 客户端数据与重渲染治理**：SWR 请求去重、被动滚动监听、消除 `useEffect` 同步派生、避免组件内嵌套定义子组件、`useDeferredValue` / `startTransition` / `useRef` 托管瞬态值。
4. **LOW-MEDIUM / LOW — 渲染细节与 JS 热点**：防布局抖动、`Map`/`Set` O(1) 查找、单遍 `flatMap`/极值循环、`.toSorted()` 不可变排序、`useEffectEvent` 稳定订阅。

---

## 三、组件架构与工程铁律

- **组合优于布尔 Prop 爆炸**：单个组件超过 2–3 个模式开关（`isCompact` / `isDialog` / `showFooter` / `isEditing`）时，立刻拆为复合组件 + 显式语义变体，用 `state / actions / meta` 三段式泛型 Context 做依赖注入，将状态提升至 Provider。
- **能推导的不存 State**：可从 props/state 同步计算的值一律渲染期推导；禁止 `useEffect + setState` 同步派生状态，禁止在组件函数体内定义子组件，禁止把用户交互副作用建模成 state + effect。
- **纯逻辑抽离视图**：过滤、排序、分组、显隐阈值、摘要裁剪与复位判定抽成零 React 依赖的纯 `.ts` 模型，让 `*.spec.ts` 毫秒级覆盖 0 项、阈值边界与超长文本。
- **状态生命周期显式化**：区分「持久偏好」（版本化 `localStorage` + `try/catch` + 最小字段）与「临时界面态」（弹窗搜索词、二级子视图、高亮项）；切页/关闭时显式重置，切换实体时优先用 `key={targetId}` 干净重建子树。
- **异步竞态与防双击兜底**：动态查询配 `AbortController` + 递增序号守卫；提交按钮配同步 `inFlightRef` 锁拦截同一帧连点；监听、Observer 与定时器全部在 cleanup 中成对销毁。
- **严守 Token 与零 `!important`**：所有颜色、圆角、阴影、间距与动效时长消费既有 Design Tokens；Flex/Grid 收缩层必写 `min-width: 0`，弹层滚动体必写 `min-height: 0` + `overscroll-behavior: contain`。

---

## 四、高频反模式红线速查

| 禁止写法 | 直接后果 | 正确替代 |
| --- | --- | --- |
| 入口处顺序 `await` 多个独立请求 | 延迟按 RTT 线性倍增 | `Promise.all` / 入口预发起 Promise |
| 组件函数体内声明 `const Row = () => ...` | 每次父渲染卸载重建 DOM、输入框丢焦点 | 提到模块顶层通过 props 传值 |
| `useEffect` 里 `setFiltered(...)` 同步派生 | 双倍渲染、首帧闪烁、状态短暂失步 | 渲染期同步推导（昂贵时配 `useMemo`） |
| 往单组件继续加第 4 个 `isXxx` 布尔 prop | 状态组合指数膨胀、嵌套三元腐烂 | 复合组件 + 显式变体 + `children` |
| 用 `!important` 压住样式覆盖 | 破坏层叠顺序，后续主题/状态全部失效 | 全局搜撞名选择器并拆清功能域前缀 |
| 原地调用 `props.items.sort(...)` | 篡改只读 props/state，引发隐蔽闭包 Bug | 使用 `.toSorted()` 或 `[...items].sort()` |
| Server Action 只靠外层页面隐藏入口 | 公开 HTTP 端点可被绕过直调篡改数据 | Action 内完成输入校验 + 认证 + 授权 |
| `setTimeout(..., 100)` 兜底聚焦或清状态 | 高负载/不同机器必现偶发闪烁与竞态 | 生命周期钩子、事件回调或状态复位源头 |

---

## 五、按任务场景精准路由（先读再写）

遇到具体任务时，**先打开对应参考文件，对照其中的 ❌/✅ 代码与边界条件落地**：

| 任务场景 / 痛点症状 | 必读参考文件 | 核心覆盖内容 |
| --- | --- | --- |
| 串行 `await`、接口慢、首屏被慢查询阻塞 | [消除异步瀑布](references/async-waterfalls.md) | 廉价守卫前置、`await` 下沉、依赖图并行、`Promise.all`、Suspense 流式边界（6 条） |
| 首屏 JS 过大、冷启动/构建慢、编辑器/图表拖慢 TTI | [包体与按需加载优化](references/bundle-optimization.md) | 规避 Barrel File、条件懒加载、延后非关键三方库、重组件动态导入、静态可分析路径、意图预加载（6 条） |
| Server Action 鉴权、RSC 载荷过大、客户端重复请求/存储报错 | [服务端与客户端数据流](references/server-and-client-data.md) | RSC 安全/去重/静态 I/O 提升/LRU/`React.cache`/`after()`（10 条）+ 全局监听去重/passive/SWR/版本化存储（4 条） |
| 输入卡顿、页面闪烁、丢焦点、Effect 死循环或重复触发 | [React 重渲染治理](references/rerender-optimization.md) | 派生推导、禁组件内建组件、`memo` 常量默认值、收窄依赖、事件放副作用、函数式更新、懒初始化、`useDeferredValue`/`useRef`（15 条） |
| 长列表首绘慢、水合警告/闪白、SVG 动画掉帧、数组/DOM 热点慢 | [渲染与 JS 热点性能](references/rendering-and-js-perf.md) | SVG 包装加速、`content-visibility`、无闪烁主题脚本、`<Activity>`、资源提示、`useTransition`（11 条）+ 防回流、Map 索引、缓存、`flatMap`、`toSorted`（14 条） |
| 稳定订阅不重连、应用单次初始化、React 19 写法迁移 | [高级 React 模式与 React 19](references/advanced-react-patterns.md) | `useEffectEvent` 依赖红线与稳态回调、应用级单次初始化、React 19 无 `forwardRef` 与 `use()`（4 条 + React 19） |
| 组件堆满布尔开关、兄弟组件同步状态困难、切页残留旧状态 | [组件组合与状态架构](references/composition-and-state.md) | 消除布尔爆炸、复合组件、UI/状态解耦、`state/actions/meta` 依赖注入、状态提升、显式变体、`children` 组合、纯函数模型与复位（7 条 + 实践） |
| 样式冲突、长文本挤扁按钮、弹窗撑出视口、键盘焦点迷失、异步竞态 | [CSS 作用域与交互健壮性](references/css-and-interaction-craft.md) | 前缀防撞、Token 约束、`min-width: 0`、粘性头尾独立滚动、`grid-template-rows` 手风琴、焦点闭环、`AbortController` + 同步防双击 |
| 任何样式错位、状态不同步、闪烁或改了两次还没修好的 Bug | [前端根因调试手册](references/frontend-debugging.md) | 四阶段根因调试、CSS/React/多边界采证、三连败架构熔断、常见合理化借口对照表 |

---

## 六、前端四阶段根因调试与三连败熔断

> **铁律：未完成第一阶段根因采证，严禁提议或写入任何修复代码。**

| 阶段 | 强制动作 | 阶段产出 |
| --- | --- | --- |
| **1. 复现与采证** | 拿到最小稳定复现、读完整首次报错栈、检查 `getComputedStyle`/选择器碰撞或状态/异步时序快照 | 可核验事实与真实故障层 |
| **2. 对照正常路径** | 找同仓库正常工作的同类组件，逐项比对 DOM 层级、CSS 前缀与加载序、Provider 边界与复位时机 | 完整差异清单 |
| **3. 单假设最小验证** | 写下“根因是 X，因为证据 Y”，只改单变量验证；假设被证伪立刻撤销，绝不叠残余补丁 | 经证实的单一根因 |
| **4. 源头修复 + 回归** | 先立必败复现用例，从源头单点修复，跑单测、类型检查与构建验证 | 无回归的干净修复 |

> **三连败熔断**：针对同一前端缺陷连续 **3 次** 尝试未根治，或每次修好 A 立刻弄坏 B，**立刻停手，禁止第 4 次补丁**。退一步重审状态归属层级、组件组合边界或 CSS 层叠结构，先对齐结构方案再动代码。详见 [前端根因调试手册](references/frontend-debugging.md)。

---

## 七、全部参考文档索引（一层直链）

- [references/async-waterfalls.md](references/async-waterfalls.md) — 消除异步瀑布（6 条，CRITICAL）
- [references/bundle-optimization.md](references/bundle-optimization.md) — 包体大小与按需加载优化（6 条，CRITICAL）
- [references/server-and-client-data.md](references/server-and-client-data.md) — 服务端 / RSC 性能（10 条，HIGH）与客户端数据流（4 条，MEDIUM-HIGH）
- [references/rerender-optimization.md](references/rerender-optimization.md) — React 重渲染治理（15 条，MEDIUM）
- [references/rendering-and-js-perf.md](references/rendering-and-js-perf.md) — 浏览器渲染性能（11 条，MEDIUM）与 JS 热点性能（14 条，LOW-MEDIUM）
- [references/advanced-react-patterns.md](references/advanced-react-patterns.md) — 高级 React 副作用/初始化模式（4 条）与 React 19 API 变更
- [references/composition-and-state.md](references/composition-and-state.md) — 复合组件架构、`state/actions/meta` 依赖注入、纯函数模型与状态复位（7 条 + 实践）
- [references/css-and-interaction-craft.md](references/css-and-interaction-craft.md) — 作用域 CSS、Token、高数量/窄窗模板、焦点闭环与竞态/防连点守卫
- [references/frontend-debugging.md](references/frontend-debugging.md) — 前端四阶段系统化根因调试、三连败熔断与反合理化对照表
- [README.md](README.md) — 适用范围、快速使用样例与边界说明

---

## 八、交付前验收清单

- [ ] 已复用仓库既有组件、hooks 与 Design Tokens；无同名 CSS 碰撞，无 `!important` 临时补丁。
- [ ] 无无依赖串行 `await` 瀑布、无未鉴权 Server Action、无不必要的大包同步导入。
- [ ] 无 `useEffect` 同步派生状态、无组件内定义子组件、无原地 `.sort()` 修改 props/state、无未清理的监听/定时器/请求竞态。
- [ ] 极端数据（0 项、高数量滚动、超长文本、窄窗）与键盘焦点闭环（打开聚焦、`Esc` 关闭归还焦点）均已处理。
- [ ] 已运行目标项目的受影响单测、类型检查与构建命令并确认全部通过。
