# 条件等待与异步稳定性

**何时读取**：测试中出现 `setTimeout` / `sleep` / `time.sleep`、异步测试本地绿但 CI 偶发红、并行跑测试偶发超时，或需要等待事件/状态/文件落地时。

## 核心原则

> **等待你真正关心的条件成立，而不是猜测它大概需要多少毫秒。**

靠硬编码延迟猜耗时，必然制造竞态：在空闲开发机上勉强通过，一旦遇到 CI 高负载或并发执行就会随机失败。

## 决策流：该用条件等待还是固定等待？

```text
测试里出现了 setTimeout / sleep？
  ├── 否 ──▶ 保持同步确定性断言
  └── 是 ──▶ 被测对象本身是在验证“真实时间窗口行为”（如防抖/节流/周期 tick）吗？
                ├── 否 ──▶ 一律改用条件轮询等待（waitFor / 领域等待助手）
                └── 是 ──▶ 1) 先用条件等待锚定起始事件
                           2) 再按已知精确周期等待
                           3) 写明注释解释 WHY 需要该时长
```

### 适用与不适用

- **必须使用条件等待**：测试里有任意 `setTimeout` / `sleep`、测试偶发失败、并行执行超时、等待后台异步任务/事件流/文件落盘完成。
- **可谨慎使用固定等待**：仅当被测需求本身是时间窗口语义（如防抖间隔、节流窗口、周期性心跳输出），且必须满足文末三项硬性要求。

## 核心改造模式

### TypeScript 正反例

```typescript
// ❌ 改造前：靠猜 50ms，高负载下必抖
await new Promise((r) => setTimeout(r, 50));
const result = getResult();
expect(result).toBeDefined();

// ✅ 改造后：条件一成立立刻继续，超时给出清晰诊断
const result = await waitFor(() => getResult(), '异步计算产出非空结果');
expect(result).toBeDefined();
```

### Python 正反例

```python
# ❌ 改造前：硬等 0.5 秒，既拖慢测试又在慢机器上偶发失败
time.sleep(0.5)
assert worker.status == "ready"

# ✅ 改造后：每 10ms 重读最新状态，成立即返回
wait_for(lambda: worker.status == "ready", "worker 进入 ready 状态", timeout_sec=5.0)
assert worker.status == "ready"
```

## 五类常见场景速查

| 场景 | 条件等待写法 |
| --- | --- |
| 等待特定事件出现 | `waitFor(() => events.find((e) => e.type === 'DONE'), 'DONE 事件')` |
| 等待状态机就绪 | `waitFor(() => machine.state === 'ready', '状态机进入 ready')` |
| 等待累计数量达标 | `waitFor(() => items.length >= 5, '收集满 5 条记录')` |
| 等待文件落盘 | `waitFor(() => fs.existsSync(targetPath), '导出文件落盘')` |
| 等待复合条件 | `waitFor(() => obj.ready && obj.value > 10, '对象就绪且值大于 10')` |

## 通用轮询函数实现

### TypeScript 通用 `waitFor`（同步与异步条件均适用）

```typescript
export async function waitFor<T>(
  condition: () => T | Promise<T | undefined | null | false> | undefined | null | false,
  description: string,
  timeoutMs = 5000,
  pollIntervalMs = 10,
): Promise<T> {
  const startTime = Date.now();

  while (true) {
    const result = await condition();
    if (result) return result;

    if (Date.now() - startTime > timeoutMs) {
      throw new Error(`Timeout waiting for ${description} after ${timeoutMs}ms`);
    }

    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }
}
```

### Python 通用 `wait_for`

```python
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def wait_for(
    condition: Callable[[], T | None | bool],
    description: str,
    *,
    timeout_sec: float = 5.0,
    poll_interval_sec: float = 0.01,
) -> T:
    deadline = time.monotonic() + timeout_sec
    while True:
        result = condition()
        if result:
            return result  # type: ignore[return-value]
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timeout waiting for {description} after {timeout_sec:.2f}s"
            )
        time.sleep(poll_interval_sec)
```

## 领域专用等待助手（完整 TypeScript 实现）

当同一套事件源在多个测试中被反复等待时，封装领域语义明确的等待助手，把**清晰报错信息**（如“期望 2 条，实际收到 1 条”）沉淀在测试工具层：

```typescript
export interface ThreadEvent {
  type: string;
  data: Record<string, unknown>;
}

export interface ThreadEventSource {
  getEvents(threadId: string): ThreadEvent[];
}

/**
 * 等待指定类型的首个事件出现
 */
export function waitForEvent(
  threadManager: ThreadEventSource,
  threadId: string,
  eventType: string,
  timeoutMs = 5000,
): Promise<ThreadEvent> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();

    const check = () => {
      const events = threadManager.getEvents(threadId);
      const event = events.find((e) => e.type === eventType);

      if (event) {
        resolve(event);
      } else if (Date.now() - startTime > timeoutMs) {
        reject(new Error(`Timeout waiting for ${eventType} event after ${timeoutMs}ms`));
      } else {
        setTimeout(check, 10); // 每 10ms 轮询一次，兼顾响应与 CPU 占用
      }
    };

    check();
  });
}

/**
 * 等待指定类型的事件达到目标数量，超时时报告当前已收到的数量
 */
export function waitForEventCount(
  threadManager: ThreadEventSource,
  threadId: string,
  eventType: string,
  count: number,
  timeoutMs = 5000,
): Promise<ThreadEvent[]> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();

    const check = () => {
      const events = threadManager.getEvents(threadId);
      const matchingEvents = events.filter((e) => e.type === eventType);

      if (matchingEvents.length >= count) {
        resolve(matchingEvents);
      } else if (Date.now() - startTime > timeoutMs) {
        reject(
          new Error(
            `Timeout waiting for ${count} ${eventType} events after ${timeoutMs}ms (got ${matchingEvents.length})`,
          ),
        );
      } else {
        setTimeout(check, 10);
      }
    };

    check();
  });
}

/**
 * 等待满足自定义谓词的事件（需要检查事件载荷字段而不仅是类型时使用）
 */
export function waitForEventMatch(
  threadManager: ThreadEventSource,
  threadId: string,
  predicate: (event: ThreadEvent) => boolean,
  description: string,
  timeoutMs = 5000,
): Promise<ThreadEvent> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();

    const check = () => {
      const events = threadManager.getEvents(threadId);
      const event = events.find(predicate);

      if (event) {
        resolve(event);
      } else if (Date.now() - startTime > timeoutMs) {
        reject(new Error(`Timeout waiting for ${description} after ${timeoutMs}ms`));
      } else {
        setTimeout(check, 10);
      }
    };

    check();
  });
}
```

### 真实排障改造对比（并发工具调用中止场景）

```typescript
// ❌ 改造前（60% 通过率，频繁随机失败）
const messagePromise = agent.sendMessage('Execute tools');
await new Promise((r) => setTimeout(r, 300)); // 赌 300ms 内工具已启动
agent.abort();
await messagePromise;
await new Promise((r) => setTimeout(r, 50));  // 赌 50ms 内结果都已回写
expect(getToolResults().length).toBe(2);      // 随机失败

// ✅ 改造后（100% 通过率，且总执行耗时缩短约 40%）
const messagePromise = agent.sendMessage('Execute tools');
await waitForEventCount(threadManager, threadId, 'TOOL_CALL', 2); // 确认 2 个工具均已启动
agent.abort();
await messagePromise;
const results = await waitForEventCount(threadManager, threadId, 'TOOL_RESULT', 2);
expect(results).toHaveLength(2);
```

使用带谓词的 `waitForEventMatch` 定位特定调用结果：

```typescript
const resultEvent = await waitForEventMatch(
  threadManager,
  threadId,
  (e) => e.type === 'TOOL_RESULT' && e.data.id === 'call_123',
  'TOOL_RESULT with id=call_123',
);
expect(resultEvent.data.status).toBe('ok');
```

## 常见错误与修复

| 常见错误 | 后果 | 正确修复 |
| --- | --- | --- |
| **轮询过快**：`setTimeout(check, 1)` 或无休眠忙等 | 空转烧满 CPU，反而拖慢并行测试 | 轮询间隔固定在 **10–25ms**（默认 `10ms`） |
| **无超时上限**：`while (!ready()) await sleep(10)` | 条件永不成立时挂死整个 CI 任务 | 必带 `timeoutMs`（如 5000ms），超时抛出包含期望描述与当前观测值的错误 |
| **循环外缓存过期状态**：先取 `const list = store.items` 再在循环里判 `list.length` | 状态早已更新，循环却永远盯着旧快照直到超时 | 每次轮询都在条件函数内部重新调用 getter 读取最新状态 |
| **用大 `sleep` 掩盖并发竞态** | 套件越跑越慢，遇到负载抖动照样红 | 暴露可观察事件/状态或注入可控时钟，用条件等待精准同步 |

```typescript
// ❌ 过期快照：循环外只读了一次 events，永远看不到新事件
const snapshot = threadManager.getEvents(threadId);
await waitFor(() => snapshot.some((e) => e.type === 'DONE'), 'DONE');

// ✅ 每次轮询重新查询最新状态
await waitFor(
  () => threadManager.getEvents(threadId).some((e) => e.type === 'DONE'),
  'DONE event',
);
```

## 何时才允许固定等待（及三项硬性要求）

只有当测试目标**本身就是时间流逝带来的行为**（例如：每 100ms 输出一次心跳、200ms 防抖窗口、500ms 令牌过期），且无法或不适合替换虚拟时钟时，才允许固定等待：

```typescript
// 工具每 100ms 触发一次 tick，验证需要观察到 2 次局部输出
await waitForEvent(threadManager, threadId, 'TOOL_STARTED'); // 1. 先用条件等待锚定起点
await new Promise((r) => setTimeout(r, 200));                 // 2. 再等待已知精确窗口
// 3. 注释说明 WHY：200ms = 2 个 100ms tick 周期，非猜测耗时
```

**必须同时满足三项要求**：
1. **先等触发条件**：用条件等待确认计时起点已经真正发生，绝不在未就绪时开表；
2. **基于已知周期**：时长必须由被测规格里的明确周期推算，而非凭感觉拍脑袋；
3. **注释写明 WHY**：紧邻代码说明为什么必须是这个毫秒数，防止后人误删或误判为脆弱 `sleep`。
