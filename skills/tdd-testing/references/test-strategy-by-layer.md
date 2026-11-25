# 按改动类型分层测试策略与模板

**何时读取**：开始为一个需求或重构规划测试覆盖面、拿不准该写单测还是集成测试，或需要快速起手高信噪比测试骨架时。

## 核心原则

> **把每一类风险放到离它最近、最真实、最快的层级去拦截。**

不要把所有逻辑都写成满屏 Mock 的“假单测”，也不要把每个纯计算分支都塞进重量级端到端流程。按改动性质选对层级，既快又稳。

## 按改动类型选层级决策表

| 改动类型 | 首选测试层级 | 真实组件 vs 替身 | 必测边界与风险点 | 目标速度 |
| --- | --- | --- | --- | --- |
| 纯算法、解析器、格式化、状态归约、权限判定 | **L1 纯函数与领域模型单测** | 100% 真实代码，零 Mock | 空值、零值、极值、非法编码、重复键、顺序不变性 | 毫秒级 |
| 路由/IPC/CLI 处理器、协议编解码、外部 API 适配器 | **L2 边界契约与错误分支测试** | 真实协议/校验层 + 仅替掉慢速/外部 I/O 边界 | 缺字段、类型错、未授权、超时/上游 5xx、错误码契约 | 几十毫秒 |
| SQLite/文件读写、Schema 迁移、缓存持久化、配置合并 | **L3 临时目录真实持久化与迁移集成测试** | 临时目录 + 真实 DB/FS，严禁 Mock 数据层 | 首次初始化、多版本升级幂等、旧数据保留、原子写入与损坏恢复 | 百毫秒级 |
| 队列、锁、异步任务、子进程、重试与取消 | **L4 并发幂等与资源清理测试** | 真实并发原语 + 条件等待 `waitFor`（禁 `sleep`） | 并发写入竞态、重复投递幂等、中途取消、关闭后零句柄/临时文件残留 | 秒级内 |

---

## L1：纯函数与领域模型单测

**要点**：表驱动 + 独立手写字面量预期，一条用例只锁一个行为族，零 Mock。

### TypeScript 模板

```typescript
import { describe, expect, test } from 'vitest';
import { parseDurationMs } from '../src/duration';

describe('parseDurationMs', () => {
  const validCases = [
    { input: '0ms', want: 0 },
    { input: '250ms', want: 250 },
    { input: '2s', want: 2000 },
    { input: '1.5m', want: 90_000 },
    { input: '  3s  ', want: 3000 },
  ];

  for (const { input, want } of validCases) {
    test(`parses "${input}" into ${want}ms`, () => {
      expect(parseDurationMs(input)).toBe(want);
    });
  }

  const invalidCases = ['', '   ', '-5s', '10d', 'abc', 'NaNs'];
  for (const input of invalidCases) {
    test(`rejects invalid duration "${input}"`, () => {
      expect(() => parseDurationMs(input)).toThrow(/invalid duration/i);
    });
  }
});
```

### Python 模板

```python
import pytest
from app.duration import parse_duration_ms


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("0ms", 0),
        ("250ms", 250),
        ("2s", 2000),
        ("1.5m", 90_000),
        ("  3s  ", 3000),
    ],
)
def verify_valid_durations(raw: str, want: int):
    assert parse_duration_ms(raw) == want


@pytest.mark.parametrize("raw", ["", "   ", "-5s", "10d", "abc"])
def verify_invalid_durations_raise(raw: str):
    with pytest.raises(ValueError, match="invalid duration"):
        parse_duration_ms(raw)
```

---

## L2：边界契约与错误分支测试

**要点**：测你的入口校验、序列化/反序列化、传给下游的具体参数、成功/失败/畸形响应各自独立处理路径；只替掉真正外部的网络或远端服务，且替身返回完整真实结构。

### TypeScript 模板

```typescript
import { describe, expect, test, vi } from 'vitest';
import { createOrderHandler } from '../src/order-handler';

describe('createOrderHandler contract', () => {
  test('rejects missing items before calling payment gateway', async () => {
    const gateway = { charge: vi.fn() };
    const handler = createOrderHandler({ gateway });

    const res = await handler({ userId: 'u-1', items: [] });

    expect(res).toEqual({ status: 400, code: 'EMPTY_ITEMS', message: 'At least one item is required' });
    expect(gateway.charge).not.toHaveBeenCalled();
  });

  test('maps gateway timeout into retryable 503 contract', async () => {
    const gateway = {
      charge: vi.fn().mockRejectedValue(Object.assign(new Error('timed out'), { code: 'ETIMEDOUT' })),
    };
    const handler = createOrderHandler({ gateway });

    const res = await handler({ userId: 'u-1', items: [{ sku: 'A1', qty: 2, unitCents: 500 }] });

    expect(gateway.charge).toHaveBeenCalledWith({ userId: 'u-1', amountCents: 1000, currency: 'USD' });
    expect(res).toEqual({ status: 503, code: 'PAYMENT_TIMEOUT', retryable: true });
  });
});
```

### Python 模板

```python
class RecordingGateway:
    def __init__(self, *, error: Exception | None = None):
        self.calls: list[dict] = []
        self._error = error

    def charge(self, *, user_id: str, amount_cents: int, currency: str) -> dict:
        self.calls.append(
            {"user_id": user_id, "amount_cents": amount_cents, "currency": currency}
        )
        if self._error is not None:
            raise self._error
        return {
            "status": "captured",
            "transaction_id": "tx-001",
            "amount_cents": amount_cents,
            "currency": currency,
        }


def verify_handler_maps_timeout_and_passes_exact_amount():
    gw = RecordingGateway(error=TimeoutError("gateway timeout"))
    res = handle_create_order(
        {"user_id": "u-1", "items": [{"sku": "A1", "qty": 2, "unit_cents": 500}]},
        gateway=gw,
    )
    assert gw.calls == [{"user_id": "u-1", "amount_cents": 1000, "currency": "USD"}]
    assert res == {"status": 503, "code": "PAYMENT_TIMEOUT", "retryable": True}
```

---

## L3：临时目录真实持久化与迁移集成测试

**要点**：绝不 Mock 数据库或文件系统。使用独立临时目录运行真实 SQLite / 文件存储，重点验证：**旧版 schema 升级不丢数据、重复执行迁移幂等、跨重启可完整读回、受损文件有明确报错或安全恢复**。

### TypeScript 模板

```typescript
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, test } from 'vitest';
import { openStore } from '../src/store';

const tmpDirs: string[] = [];

afterEach(() => {
  while (tmpDirs.length > 0) {
    fs.rmSync(tmpDirs.pop()!, { recursive: true, force: true });
  }
});

describe('store persistence & migration', () => {
  test('migrates v1 database to v2 idempotently while preserving rows', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'store-mig-'));
    tmpDirs.push(dir);
    const dbPath = path.join(dir, 'app.sqlite');

    // 1. 写入 v1 真实数据并关闭
    const v1 = openStore(dbPath, { targetVersion: 1 });
    v1.insertLegacyNote({ id: 'n1', body: 'keep me' });
    v1.close();

    // 2. 升级到 v2 并验证旧记录完整保留且默认值生效
    const v2 = openStore(dbPath);
    expect(v2.schemaVersion()).toBe(2);
    expect(v2.getNote('n1')).toEqual({ id: 'n1', body: 'keep me', archived: false });
    v2.close();

    // 3. 再次打开验证迁移幂等、无重复表/索引错误
    const reopened = openStore(dbPath);
    expect(reopened.schemaVersion()).toBe(2);
    expect(reopened.getNote('n1')).toEqual({ id: 'n1', body: 'keep me', archived: false });
    reopened.close();
  });
});
```

### Python 模板

```python
import sqlite3
import tempfile
from pathlib import Path
from app.storage import open_store


def verify_v1_to_v2_migration_preserves_rows_and_is_idempotent():
    with tempfile.TemporaryDirectory(prefix="store-mig-") as tmp:
        db_path = Path(tmp) / "app.sqlite"

        # 1. 构造真实 v1 库与既有记录
        raw = sqlite3.connect(db_path)
        raw.execute("PRAGMA user_version = 1")
        raw.execute("CREATE TABLE notes (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        raw.execute("INSERT INTO notes (id, body) VALUES ('n1', 'keep me')")
        raw.commit()
        raw.close()

        # 2. 首次打开升级到 v2
        store = open_store(db_path)
        try:
            assert store.schema_version() == 2
            assert store.get_note("n1") == {"id": "n1", "body": "keep me", "archived": False}
        finally:
            store.close()

        # 3. 重复打开确认迁移幂等
        reopened = open_store(db_path)
        try:
            assert reopened.schema_version() == 2
            assert reopened.get_note("n1") == {"id": "n1", "body": "keep me", "archived": False}
        finally:
            reopened.close()
```

---

## L4：并发幂等与资源清理测试

**要点**：验证并发争用、重复提交幂等性、中途取消与优雅停机；异步同步一律用 [条件等待](condition-based-waiting.md) 的 `waitFor`，严禁硬编码 `sleep`；关闭后断言临时目录/句柄/后台任务已清零。

### TypeScript 模板

```typescript
import { describe, expect, test } from 'vitest';
import { TaskQueue } from '../src/task-queue';
import { waitFor } from './helpers/wait-for';

describe('TaskQueue concurrency & idempotency', () => {
  test('deduplicates concurrent submissions with same idempotencyKey and cleans up on close', async () => {
    let executions = 0;
    const queue = new TaskQueue({
      concurrency: 2,
      handler: async (payload: { value: number }) => {
        executions++;
        return payload.value * 2;
      },
    });

    try {
      const results = await Promise.all([
        queue.enqueue({ idempotencyKey: 'job-1', value: 21 }),
        queue.enqueue({ idempotencyKey: 'job-1', value: 21 }),
        queue.enqueue({ idempotencyKey: 'job-1', value: 21 }),
      ]);

      expect(results).toEqual([42, 42, 42]);
      expect(executions).toBe(1);
    } finally {
      await queue.close();
      await waitFor(() => queue.activeWorkerCount() === 0, '所有 worker 彻底退出');
    }
  });
});
```

### Python 模板

```python
from concurrent.futures import ThreadPoolExecutor
from app.idempotent_store import IdempotentRunner


def verify_concurrent_same_key_executes_once_and_releases_locks(tmp_path):
    executions = 0

    def work(value: int) -> int:
        nonlocal executions
        executions += 1
        return value * 2

    runner = IdempotentRunner(db_path=tmp_path / "jobs.sqlite")
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = [pool.submit(runner.run_once, "job-1", work, 21) for _ in range(4)]
            results = [f.result(timeout=5) for f in futs]

        assert results == [42, 42, 42, 42]
        assert executions == 1
    finally:
        runner.close()
        assert runner.active_locks() == 0
```

## 层级选型反模式检查表

- [ ] **避免“L3 降级成假 L1”**：改了 SQL 查询或迁移脚本，却把数据库连接 Mock 掉——永远抓不住 SQL 语法、唯一约束与事务锁故障。
- [ ] **避免“L1 升级成重 L3”**：只测一个纯字符串解析规则，却每次都起整套 HTTP 服务和数据库——慢且噪音大。
- [ ] **避免“只测快乐路径”**：L2/L3 必须覆盖至少一条畸形输入、一条下游失败和一条幂等/重复调用路径。
- [ ] **避免“Mock 链超过真实边界”**：只要发现要连续 Mock 3 个以上内部协作者，立刻改用临时目录真实组件跑 L3 集成测试。
