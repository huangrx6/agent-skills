# 组件组合模式、依赖注入与状态架构（Composition & State）

> **综合影响等级：HIGH（架构与可维护性）**  
> 本文件无损融合全部 7 条组件组合与状态架构规则（消除布尔 Prop 爆炸、复合组件、UI 与状态解耦、`state/actions/meta` 泛型 Context 依赖注入、状态提升到 Provider、显式变体、`children` 优于 render props），并补齐纯函数模型抽离与切页/关闭状态复位工程实践。

---

## 1. 消除布尔 Prop 爆炸

**影响等级：CRITICAL**（防止组件变体组合指数腐烂）

绝不要不断往单个通用组件上堆叠 `isThread`、`isEditing`、`isDMThread`、`isForwarding`、`isCompact`、`hideFooter` 等模式开关。每多 1 个布尔 prop，合法与非法状态组合数就翻倍，很快演变成不可维护的三元嵌套泥潭。

### ❌ 反例：布尔开关导致指数级条件分支

```tsx
function Composer({
  onSubmit,
  isThread,
  channelId,
  isDMThread,
  dmId,
  isEditing,
  isForwarding,
}: Props) {
  return (
    <form>
      <Header />
      <Input />
      {isDMThread ? (
        <AlsoSendToDMField id={dmId} />
      ) : isThread ? (
        <AlsoSendToChannelField id={channelId} />
      ) : null}
      {isEditing ? (
        <EditActions />
      ) : isForwarding ? (
        <ForwardActions />
      ) : (
        <DefaultActions />
      )}
      <Footer onSubmit={onSubmit} />
    </form>
  )
}
```

### ✅ 正例：用显式组合消除内部条件判断

```tsx
function ChannelComposer() {
  return (
    <Composer.Frame>
      <Composer.Header />
      <Composer.Input />
      <Composer.Footer>
        <Composer.Attachments />
        <Composer.Formatting />
        <Composer.Emojis />
        <Composer.Submit />
      </Composer.Footer>
    </Composer.Frame>
  )
}

function ThreadComposer({ channelId }: { channelId: string }) {
  return (
    <Composer.Frame>
      <Composer.Header />
      <Composer.Input />
      <AlsoSendToChannelField id={channelId} />
      <Composer.Footer>
        <Composer.Formatting />
        <Composer.Emojis />
        <Composer.Submit />
      </Composer.Footer>
    </Composer.Frame>
  )
}

function EditComposer() {
  return (
    <Composer.Frame>
      <Composer.Input />
      <Composer.Footer>
        <Composer.Formatting />
        <Composer.Emojis />
        <Composer.CancelEdit />
        <Composer.SaveEdit />
      </Composer.Footer>
    </Composer.Frame>
  )
}
```

---

## 2. 使用复合组件（Compound Components）

**影响等级：HIGH**（灵活拼装子部件，零层层 prop 透传）

将复杂交互模块拆成共享同一 Context 的一组命名子组件，由调用方显式拼装所需部件。

### ❌ 反例：巨型单体组件 + 满屏 `renderX` 与 `showX`

```tsx
function Composer({
  renderHeader,
  renderFooter,
  renderActions,
  showAttachments,
  showFormatting,
  showEmojis,
}: Props) {
  return (
    <form>
      {renderHeader?.()}
      <Input />
      {showAttachments && <Attachments />}
      {renderFooter ? (
        renderFooter()
      ) : (
        <Footer>
          {showFormatting && <Formatting />}
          {showEmojis && <Emojis />}
          {renderActions?.()}
        </Footer>
      )}
    </form>
  )
}
```

### ✅ 正例：共享 Context 的复合组件命名空间

```tsx
const ComposerContext = createContext<ComposerContextValue | null>(null)

function useComposerContext() {
  const ctx = useContext(ComposerContext) // React 19+ 可改用 use(ComposerContext)
  if (!ctx) throw new Error('Composer subcomponents must be used within Composer.Provider')
  return ctx
}

function ComposerProvider({ children, state, actions, meta }: ProviderProps) {
  return (
    <ComposerContext.Provider value={{ state, actions, meta }}>
      {children}
    </ComposerContext.Provider>
  )
}

function ComposerFrame({ children }: { children: React.ReactNode }) {
  return <form>{children}</form>
}

function ComposerInput() {
  const {
    state,
    actions: { update },
    meta: { inputRef },
  } = useComposerContext()

  return (
    <input
      ref={inputRef}
      value={state.input}
      onChange={(e) => update((s) => ({ ...s, input: e.target.value }))}
    />
  )
}

function ComposerSubmit() {
  const {
    actions: { submit },
  } = useComposerContext()
  return <button type="button" onClick={submit}>发送</button>
}

export const Composer = {
  Provider: ComposerProvider,
  Context: ComposerContext,
  Frame: ComposerFrame,
  Header: ComposerHeader,
  Input: ComposerInput,
  Footer: ComposerFooter,
  Attachments: ComposerAttachments,
  Formatting: ComposerFormatting,
  Emojis: ComposerEmojis,
  Submit: ComposerSubmit,
}
```

---

## 3. 将状态管理实现与 UI 彻底解耦

**影响等级：MEDIUM**（替换底层状态库/同步机制时零修改 UI 组件）

**只有 Provider 知道状态从哪来、怎么存**（本地 `useState`、Zustand、服务端实时同步或 IPC 持久化）。UI 子组件只消费 Context 接口，不直接 import 具体 store hook。

### ❌ 反例：UI 组件硬编码绑定全局同步 Hook

```tsx
function ChannelComposer({ channelId }: { channelId: string }) {
  const state = useGlobalChannelState(channelId)
  const sync = useChannelSync(channelId)

  return (
    <Composer.Frame>
      <Composer.Input value={state.input} onChange={(text) => sync.updateInput(text)} />
      <Composer.Submit onClick={() => sync.submit()} />
    </Composer.Frame>
  )
}
```

### ✅ 正例：不同场景换 Provider，UI 部件 100% 复用

```tsx
// 场景 A：临时弹窗表单使用本地 useState
function ForwardMessageProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState(initialState)
  const inputRef = useRef<HTMLInputElement>(null)
  const forwardMessage = useForwardMessage()

  return (
    <Composer.Provider
      state={state}
      actions={{ update: setState, submit: forwardMessage }}
      meta={{ inputRef }}
    >
      {children}
    </Composer.Provider>
  )
}

// 场景 B：频道聊天框使用全局同步状态
function ChannelProvider({
  channelId,
  children,
}: {
  channelId: string
  children: React.ReactNode
}) {
  const { state, update, submit } = useGlobalChannel(channelId)
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <Composer.Provider
      state={state}
      actions={{ update, submit }}
      meta={{ inputRef }}
    >
      {children}
    </Composer.Provider>
  )
}
```

---

## 4. 定义 `state / actions / meta` 泛型 Context 契约实现依赖注入

**影响等级：HIGH**（跨场景复用 UI 且支持框架外兄弟节点联动）

**核心原则**：状态提升、内部组合、依赖注入。所有复杂复合组件的 Context 契约统一划分为三段：

```tsx
interface ComposerState {
  input: string
  attachments: Attachment[]
  isSubmitting: boolean
}

interface ComposerActions {
  update: (updater: (state: ComposerState) => ComposerState) => void
  submit: () => void
}

interface ComposerMeta {
  inputRef: React.RefObject<HTMLInputElement | null>
}

interface ComposerContextValue {
  state: ComposerState
  actions: ComposerActions
  meta: ComposerMeta
}
```

**关键洞察**：共享状态取决于 **Provider 边界**，而非视觉嵌套边界。位于 `Composer.Frame` 视觉框之外、但仍在同一个 Provider 之内的 `<MessagePreview />` 与 `<ForwardButton />`，同样可以直接读取 `state` 并触发 `actions.submit`：

```tsx
function ForwardMessageDialog() {
  return (
    <ForwardMessageProvider>
      <Dialog>
        <Composer.Frame>
          <Composer.Input placeholder="补充一条转发留言..." />
          <Composer.Footer>
            <Composer.Formatting />
            <Composer.Emojis />
          </Composer.Footer>
        </Composer.Frame>

        {/* 视觉上在输入框外部，但在同一 Provider 内部 */}
        <MessagePreview />

        <DialogActions>
          <CancelButton />
          <ForwardButton />
        </DialogActions>
      </Dialog>
    </ForwardMessageProvider>
  )
}
```

---

## 5. 将状态提升到 Provider（杜绝三大同步反模式）

**影响等级：HIGH**（根治兄弟组件互访状态时的同步地狱）

当弹窗底部确认按钮、外侧预览区与内部表单需要共享同一份状态时，绝不要使用以下三种反模式：

### ❌ 三大反模式
1. **状态困死在子组件内部**：外层兄弟 `<MessagePreview />` 与 `<ForwardButton />` 根本拿不到状态和提交动作；
2. **用 `useEffect` 向上同步状态**：子组件每次输入再 `useEffect(() => onInputChange(state.input), [state.input])`，制造双份真相源与帧延迟；
3. **传 `stateRef` 给子组件在提交时偷读**：绕过 React 数据流，外层按钮禁用态/预览区完全无法响应变化。

### ✅ 正例：状态放进外层 `ForwardMessageProvider`
如上节所示，把状态留在共同祖先 Provider 内，`<ForwardMessageComposer />`、`<MessagePreview />` 与 `<ForwardButton />` 都直接从同一个 Context 读取唯一事实源。

---

## 6. 创建显式语义变体组件

**影响等级：MEDIUM**（代码自解释，消灭不可能状态）

调用点应该一眼看出渲染了什么，而不是靠阅读 6 个布尔参数去猜组件内部逻辑：

```tsx
// ❌ 反例：调用方和阅读者根本看不出最终长什么样
<Composer
  isThread
  isEditing={false}
  channelId="abc"
  showAttachments
  showFormatting={false}
/>

// ✅ 正例：语义清晰、自包含、底层复用同一套复合部件与对应 Provider
<ThreadComposer channelId="abc" />
<EditMessageComposer messageId="xyz" />
<ForwardMessageComposer messageId="123" />
```

---

## 7. 结构组合优先用 `children`，仅数据回传时用 Render Props

**影响等级：MEDIUM**（更自然的 JSX 结构与可读性）

- **组合静态/布局结构**（Header、Footer、Toolbar、Actions）：一律用复合组件 + `children`，不要写 `renderHeader={() => ...}`、`renderFooter={() => ...}`。
- **何时适合 Render Props**：只有当父组件需要把内部迭代/计算产生的数据回传给子渲染函数时，才使用 render prop：

```tsx
// ✅ Render prop 的合理场景：父组件回传 item / index
<VirtualList
  data={items}
  renderItem={({ item, index }) => <ItemRow item={item} index={index} />}
/>
```

---

## 8. 纯函数模型抽离与视图解耦

将**过滤、排序、分组、显隐阈值、摘要裁剪、边界态推导、状态复位判定**全部抽离到零 React 依赖的纯 `.ts` 模型模块（如 `picker-model.ts`）：
- 输入为只读数组与普通配置对象，输出为视图直接消费的结构化结果；
- 边界条件（0 项、搜索阈值、大小写与拼音/多关键字匹配、超长文本）可直接用 `picker-model.spec.ts` 在毫秒级完成自动化回归，无需挂载整棵 DOM。

---

## 9. 状态生命周期显式化与切页/关闭复位

在设计组件状态前，必须显式区分两类状态的生命周期：

| 状态类型 | 典型例子 | 生命周期与存储位置 |
| --- | --- | --- |
| **持久偏好** | 主题、侧栏宽度、默认排序方式 | 版本化持久化存储，切页与重启保留 |
| **临时界面态** | 弹窗搜索词、设置二级子视图、折叠展开项、未保存表单草稿、高亮索引 | 随弹窗关闭、切页或切换目标对象**干净复位** |

**两种可靠的复位写法**：
1. **切换目标实体时用 `key={targetId}`**：例如 `<SettingsDetail key={activeTargetId} target={target} />`，让 React 自动丢弃旧子树内部全部临时状态，禁止靠手写 `useEffect` 逐个 `setState` 清空；
2. **弹窗/切页显式重置函数**：在关闭事件回调（`handleClose`）或导航离开事件中调用 `actions.reset()`，把搜索词、二级子页和错误提示归零，不靠延迟 `setTimeout` 清空。
