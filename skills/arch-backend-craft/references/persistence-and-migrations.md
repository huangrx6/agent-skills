# 持久化、迁移与失败恢复

业务展示层缺陷通常可快速热修，但持久化损坏、迁移丢数据或半截落盘会直接摧毁用户信任。一切数据库演进、磁盘写入与外部资源管理，都必须按**“下一毫秒就会断电、磁盘满、进程被杀或并发重入”**的前提来设计。

## 1. 版本化 Schema 迁移与存量保护

### 迁移铁律

1. **显式线性版本号**：使用 SQLite `PRAGMA user_version` 或独立的 `schema_migrations(version, applied_at, checksum)` 表线性推进；严禁靠 `try { SELECT new_col } catch { ALTER TABLE }` 这类脆弱探测拼凑迁移。
2. **单版本单事务**：每个版本的 DDL 与数据转换包裹在同一事务内；任何一条失败，整体回滚，版本号不前进，绝不留下半截表结构。
3. **幂等与存量无损**：重复启动应用时，已应用版本严格跳过；对存量配置对象演进时，保留未识别的旧字段或显式映射到新结构，不静默清空用户已有数据。

### SQLite 线性版本迁移引擎示例

```ts
export interface Migration {
  readonly version: number;
  readonly name: string;
  up(db: SqliteDatabase): void;
}

export function runMigrations(db: SqliteDatabase, migrations: readonly Migration[]): void {
  // 启动必配：开启外键约束、WAL 并发读写、合理写锁等待超时
  db.pragma('foreign_keys = ON');
  db.pragma('journal_mode = WAL');
  db.pragma('busy_timeout = 5000');

  const sorted = [...migrations].sort((a, b) => a.version - b.version);
  const current = Number(db.pragma('user_version', { simple: true }));

  if (current > (sorted.at(-1)?.version ?? 0)) {
    throw new Error(
      `数据库版本 (${current}) 高于当前应用支持上限，拒绝启动以防损坏数据`,
    );
  }

  for (const m of sorted) {
    if (m.version <= current) continue;
    // 在写事务内关闭外键检查仅用于重建表，并在提交前做外键完整性校验
    db.exec('PRAGMA foreign_keys = OFF');
    try {
      const applyVersion = db.transaction(() => {
        m.up(db);
        const violations = db.pragma('foreign_key_check') as unknown[];
        if (violations.length > 0) {
          throw new Error(`迁移 v${m.version} 破坏外键完整性: ${violations.length} 条冲突`);
        }
        db.pragma(`user_version = ${m.version}`);
      });
      applyVersion();
    } finally {
      db.exec('PRAGMA foreign_keys = ON');
    }
  }
}
```

### 改列约束 / 枚举 / 主键的四步重建法（SQLite）

SQLite 的 `ALTER TABLE` 能力有限，修改列类型、枚举 `CHECK` 约束或主键时，标准做法是**建新表 → 显式字段转换拷贝 → 核对行数 → 删旧表并重命名**：

```sql
-- 在单事务内执行
CREATE TABLE workspaces_v2 (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  trust_level TEXT NOT NULL CHECK (trust_level IN ('untrusted', 'workspace', 'trusted')),
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at INTEGER NOT NULL
);

INSERT INTO workspaces_v2 (id, name, trust_level, revision, updated_at)
SELECT
  id,
  name,
  CASE WHEN is_trusted = 1 THEN 'trusted' ELSE 'untrusted' END,
  1,
  updated_at
FROM workspaces;

DROP TABLE workspaces;
ALTER TABLE workspaces_v2 RENAME TO workspaces;
CREATE INDEX idx_workspaces_updated_at ON workspaces(updated_at DESC);
```

---

## 2. 扩张-收缩（Expand-and-Contract）与可逆迁移

对于需要滚动发布或可能回滚应用版本的服务端数据库，直接 `DROP COLUMN` 或重命名列会导致仍在运行的旧版实例立刻崩溃。必须采用**四阶段扩张-收缩**：

```text
阶段 1 Expand       阶段 2 Backfill       阶段 3 Switch          阶段 4 Contract
新增可空新列/新表  → 离线分批回填存量行  → 新版读新列并双写旧列 → 确认无需回滚后
旧版代码无感知      校验新旧数据 100% 一致   旧版仍可安全回滚      独立迁移删除旧列
```

### 可逆 `down` 迁移约束

- **可逆变更**（加表、加索引、加可空列）：必须配对编写可执行的 `down` 回滚脚本，并在验证环境实测 `up → down → up` 幂等通过。
- **不可逆变更**（删表、合并销毁历史明细）：必须拆到收缩阶段执行，执行前强制完成离线快照备份并记录校验和。

---

## 3. SQLite 与数据库事务原子性守则

1. **写事务显式使用 `BEGIN IMMEDIATE`**：避免两个并发连接同时以 `DEFERRED` 启动后升级为写锁时立即抛出 `SQLITE_BUSY` 死锁。
2. **事务内零外部 I/O**：绝对不要在数据库事务开启期间发起 HTTP 请求、执行子进程或等待用户输入——这会长时间锁死写通道并拖垮整个服务。
3. **局部可恢复分支用 `SAVEPOINT`**：当批处理中单条记录失败允许局部跳过而不推翻整批时，使用 `SAVEPOINT sp_item` / `ROLLBACK TO sp_item` / `RELEASE sp_item`。
4. **验证事务失败路径**：每次涉及多表写入，必须至少有一个验证用例模拟第二步抛错，断言第一步写入已完整回滚。

---

## 4. 原子写盘与目录级 5 步原子替换

### 单文件原子写入（防半写 0 字节损坏）

禁止直接 `fs.writeFileSync(target, data)` 覆盖关键配置或状态文件。写到一半崩溃会留下截断文件。

```ts
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export function writeFileAtomic(targetPath: string, content: string | Buffer): void {
  const dir = path.dirname(targetPath);
  fs.mkdirSync(dir, { recursive: true });

  // 必须放在同一目录（同一文件系统），否则 fs.renameSync 会因跨挂载点报 EXDEV
  const tempPath = path.join(dir, `.${path.basename(targetPath)}.${crypto.randomUUID()}.tmp`);
  let fd: number | null = null;
  try {
    fd = fs.openSync(tempPath, 'wx', 0o600);
    fs.writeFileSync(fd, content);
    fs.fsyncSync(fd); // 刷入存储介质，降低断电丢失风险
    fs.closeSync(fd);
    fd = null;
    fs.renameSync(tempPath, targetPath); // POSIX 原子替换
  } catch (err) {
    if (fd !== null) {
      try { fs.closeSync(fd); } catch { /* ignore */ }
    }
    try { fs.rmSync(tempPath, { force: true }); } catch { /* ignore */ }
    throw err;
  }
}
```

### 目录级 5 步原子替换 + 双阶段回滚（包安装 / 资源升级）

安装或升级整个目录（例如扩展包、模型快照、静态资产）且需同步落库时，遵循严格的 **5 步状态机**：

```text
[1 隔离暂存与校验] ──失败──▶ 清理 stage，原目录零触碰
        │ 通过
        ▼
[2 备份旧目录] rename(target → backup)
        │
        ▼
[3 原子切换]   rename(stage → target) ──失败──▶ rename(backup → target) 恢复
        │ 成功
        ▼
[4 事务落库]   DB COMMIT              ──失败──▶ rm(target) + rename(backup → target) 恢复
        │ 成功
        ▼
[5 提交后清理] rm(backup, stage)      ──失败──▶ 记录待回收告警，不推翻已成功安装
```

```ts
export async function installDirectoryAtomic(params: {
  stageDir: string;
  targetDir: string;
  verifyStage: (dir: string) => Promise<void>;
  commitMetadata: () => void; // 同步 DB 事务
  onCleanupWarning: (path: string, err: unknown) => void;
}): Promise<void> {
  const { stageDir, targetDir, verifyStage, commitMetadata, onCleanupWarning } = params;
  const parentDir = path.dirname(targetDir);
  const backupDir = path.join(parentDir, `.${path.basename(targetDir)}.${crypto.randomUUID()}.bak`);
  let backedUp = false;
  let swapped = false;

  try {
    // 1. 隔离区完成清单、哈希与安全边界校验
    await verifyStage(stageDir);

    // 2. 若旧目录存在，原子移至同目录备份位
    if (fs.existsSync(targetDir)) {
      fs.renameSync(targetDir, backupDir);
      backedUp = true;
    }

    // 3. 原子切换到正式目录
    fs.renameSync(stageDir, targetDir);
    swapped = true;

    // 4. 在数据库事务中提交元数据记录
    commitMetadata();
  } catch (err) {
    // 双阶段回滚：任何一步失败都恢复到变更前状态
    if (swapped) {
      try { fs.rmSync(targetDir, { recursive: true, force: true }); } catch { /* ignore */ }
    }
    if (backedUp && fs.existsSync(backupDir)) {
      fs.renameSync(backupDir, targetDir);
    }
    try { fs.rmSync(stageDir, { recursive: true, force: true }); } catch { /* ignore */ }
    throw err;
  }

  // 5. 提交后清理：清理失败只记录待回收，绝不把已成功安装误判为失败
  for (const leftover of [backupDir, stageDir]) {
    if (!fs.existsSync(leftover)) continue;
    try {
      fs.rmSync(leftover, { recursive: true, force: true });
    } catch (cleanupErr) {
      onCleanupWarning(leftover, cleanupErr);
    }
  }
}
```

---

## 5. 乐观修订号并发控制与幂等重入

### 乐观锁（Compare-and-Set Revision）

防止两个窗口或两次并发请求互相静默覆盖配置，所有写接口携带 `expectedRevision`：

```ts
export function updateSettingWithRevision(
  db: SqliteDatabase,
  key: string,
  valueJson: string,
  expectedRevision: number,
): { revision: number } {
  const nextRevision = expectedRevision + 1;
  const info = db
    .prepare(
      `UPDATE app_settings
          SET value_json = ?, revision = ?, updated_at = ?
        WHERE key = ? AND revision = ?`,
    )
    .run(valueJson, nextRevision, Date.now(), key, expectedRevision);

  if (info.changes === 0) {
    const current = db.prepare('SELECT revision FROM app_settings WHERE key = ?').get(key) as
      | { revision: number }
      | undefined;
    throw new ConflictError(
      current
        ? `配置已被其他操作更新（当前修订号 ${current.revision}，提交基准 ${expectedRevision}）`
        : `目标配置不存在: ${key}`,
      current?.revision ?? null,
    );
  }
  return { revision: nextRevision };
}
```

### 幂等键与重入互斥

- **幂等写接口**：初始化、安装、支付或后台任务入口接受稳定 `idempotencyKey`；相同键在窗口期内返回同一结果而不重复创建副作用。
- **进程内按资源键串行化**：对同一 `workspaceId` / `packageId` 的并发写操作使用 `Map<string, Promise<unknown>>` 排队或明确返回 `OPERATION_IN_PROGRESS`。

---

## 6. 流式字节限流、超时、进程组回收与资源防泄漏

### 外部 HTTP 请求：超时 + 重定向限制 + 流式字节上限

不要依赖响应头 `Content-Length`（恶意或流式分块服务可省略或伪造它），必须在读取流的过程中实时累加字节数并中止：

```ts
export async function fetchBoundedBuffer(
  url: string,
  opts: { timeoutMs: number; maxBytes: number; maxRedirects?: number },
): Promise<Buffer> {
  const maxRedirects = opts.maxRedirects ?? 3;
  let currentUrl = url;

  for (let hop = 0; hop <= maxRedirects; hop += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(new Error('HTTP_TIMEOUT')), opts.timeoutMs);
    try {
      const res = await fetch(currentUrl, {
        redirect: 'manual',
        signal: controller.signal,
      });

      if (res.status >= 300 && res.status < 400 && res.headers.get('location')) {
        if (hop === maxRedirects) throw new Error('重定向次数超出上限');
        currentUrl = new URL(res.headers.get('location')!, currentUrl).toString();
        continue;
      }
      if (!res.ok) throw new Error(`HTTP 请求失败: ${res.status}`);
      if (!res.body) return Buffer.alloc(0);

      const chunks: Buffer[] = [];
      let total = 0;
      for await (const chunk of res.body as AsyncIterable<Uint8Array>) {
        total += chunk.length;
        if (total > opts.maxBytes) {
          controller.abort(new Error('RESPONSE_TOO_LARGE'));
          throw new Error(`响应体超过最大允许字节数 (${opts.maxBytes})`);
        }
        chunks.push(Buffer.from(chunk));
      }
      return Buffer.concat(chunks, total);
    } finally {
      clearTimeout(timer);
    }
  }
  throw new Error('不可达的重定向分支');
}
```

### 外部子进程超时与进程组可靠回收

只调用 `child.kill()` 往往只杀掉外层 Shell，留下孙进程继续占用端口和 CPU。在 POSIX 平台应启用独立进程组 `detached: true` 并按负 PID 杀整组：

```ts
import { spawn } from 'node:child_process';

export function runCommandBounded(
  cmd: string,
  args: string[],
  opts: { cwd: string; timeoutMs: number; maxOutputBytes: number },
): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, {
      cwd: opts.cwd,
      detached: process.platform !== 'win32',
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let settled = false;
    let outputBytes = 0;
    const outChunks: Buffer[] = [];
    const errChunks: Buffer[] = [];

    const terminateGroup = () => {
      if (!child.pid) return;
      try {
        if (process.platform !== 'win32') {
          process.kill(-child.pid, 'SIGTERM');
          setTimeout(() => {
            try { process.kill(-child.pid!, 'SIGKILL'); } catch { /* already exited */ }
          }, 2_000).unref();
        } else {
          child.kill('SIGTERM');
        }
      } catch {
        /* 进程已退出 */
      }
    };

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      terminateGroup();
      reject(new Error(`子进程执行超时 (${opts.timeoutMs}ms): ${cmd}`));
    }, opts.timeoutMs);

    const onChunk = (target: Buffer[]) => (chunk: Buffer) => {
      outputBytes += chunk.length;
      if (outputBytes > opts.maxOutputBytes) {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          terminateGroup();
          reject(new Error(`子进程输出超过上限 (${opts.maxOutputBytes} bytes)`));
        }
        return;
      }
      target.push(chunk);
    };

    child.stdout.on('data', onChunk(outChunks));
    child.stderr.on('data', onChunk(errChunks));
    child.once('error', (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(err);
    });
    child.once('close', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        code: code ?? -1,
        stdout: Buffer.concat(outChunks).toString('utf8'),
        stderr: Buffer.concat(errChunks).toString('utf8'),
      });
    });
  });
}
```

### 资源释放与优雅退出清单

- 文件句柄、临时目录、定时器、`AbortController`、数据库连接、文件监听器一律配对置于 `try / finally`。
- 进程退出钩子（`before-quit` / `SIGTERM`）逐个关闭子服务时，为每个清理任务套独立超时（如 3 秒）与 `try / catch`，确保**单个服务卡死不会阻塞其余连接关闭与进程退出**。
