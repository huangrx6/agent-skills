# 测试隔离、资源清理与污染排查

**何时读取**：编写涉及文件系统、数据库、环境变量、子进程或本地端口的测试；排查“单跑全绿、一起跑随机失败”；或测试结束后工作树/家目录冒出多余文件时。

## 核心原则

> **任何测试结束后，机器磁盘、环境变量、端口与仓库工作树必须与运行前完全一致。**
> **任何测试单跑、倒序跑、乱序跑、并行跑，结果必须完全一致。**

## 1. 独立临时目录与零污染边界

- **严禁读写真实路径**：绝不触碰 `$HOME` 下的真实用户配置、真实数据库目录、系统全局缓存或当前 Git 仓库工作树。
- **每用例 / 每套件独占临时根目录**：在系统临时目录下创建唯一目录（`fs.mkdtempSync` / `tempfile.TemporaryDirectory`），把数据根目录、工作区目录、SQLite 文件与日志路径全部收口到该临时目录内。

### TypeScript 隔离夹具示例

```typescript
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export interface IsolatedEnv {
  rootDir: string;
  dataDir: string;
  cleanup: () => Promise<void>;
}

export function createIsolatedEnv(prefix = 'app-spec-'): IsolatedEnv {
  const rootDir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  const dataDir = path.join(rootDir, 'data');
  fs.mkdirSync(dataDir, { recursive: true });

  const prevDataDir = process.env.APP_DATA_DIR;
  const prevCwd = process.cwd();
  process.env.APP_DATA_DIR = dataDir;

  return {
    rootDir,
    dataDir,
    async cleanup() {
      process.chdir(prevCwd);
      if (prevDataDir === undefined) {
        delete process.env.APP_DATA_DIR;
      } else {
        process.env.APP_DATA_DIR = prevDataDir;
      }
      fs.rmSync(rootDir, { recursive: true, force: true });
    },
  };
}
```

### Python 隔离夹具示例

```python
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def isolated_env():
    prev_cwd = os.getcwd()
    prev_data = os.environ.get("APP_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="app-spec-") as tmp:
        root = Path(tmp)
        data_dir = root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["APP_DATA_DIR"] = str(data_dir)
        try:
            yield root, data_dir
        finally:
            os.chdir(prev_cwd)
            if prev_data is None:
                os.environ.pop("APP_DATA_DIR", None)
            else:
                os.environ["APP_DATA_DIR"] = prev_data
```

## 2. 环境变量、端口与全局状态隔离

| 共享资源 | 常见污染手法（❌） | 正确隔离做法（✅） |
| --- | --- | --- |
| **环境变量** | 直接改 `process.env.X = '...'` 忘了还原 | 保存旧值，在 `finally` / `afterEach` 区分 `undefined`（`delete`）与原值精确还原 |
| **进程工作目录** | `process.chdir(tmp)` 后因断言失败提前退出 | `chdir` 必配 `try/finally` 切回原 `cwd` |
| **本地监听端口** | 硬编码 `:8080` / `:3000` 导致并行冲突 | 绑定端口 `0` 让操作系统分配空闲端口，从 `server.address().port` 读取实际端口 |
| **模块级单例/缓存** | 依赖全局可变 `Map` 或模块级 DB 连接 | 通过工厂函数/构造函数注入新实例，避免跨用例共享可变状态 |
| **时钟与随机源** | 依赖当前墙钟日期或全局随机种子 | 将 `now()` / 随机数生成器作为可选依赖注入 |

## 3. 资源关闭与清理顺序（防句柄泄漏与删目录失败）

清理顺序错了，轻则进程退出挂起（未关闭 timer/socket），重则在句柄仍占用时删除临时目录报错。必须严格遵守**由外到内、先停活动再删磁盘**的 5 步顺序：

```text
1. 取消定时器与后台任务（clearInterval / AbortController.abort）
2. 停止本地 HTTP/RPC 服务并等待子进程退出（server.close / proc.wait）
3. 关闭数据库连接与文件流（db.close / stream.close，确保 WAL 刷盘释放）
4. 恢复环境变量与当前工作目录（env / chdir）
5. 递归删除临时目录（fs.rmSync(..., { recursive: true, force: true })）
```

### TypeScript 逆序释放栈模式

```typescript
export class CleanupStack {
  private readonly steps: Array<() => Promise<void> | void> = [];

  defer(fn: () => Promise<void> | void) {
    this.steps.push(fn);
  }

  async flush() {
    const errors: unknown[] = [];
    while (this.steps.length > 0) {
      const fn = this.steps.pop()!;
      try {
        await fn();
      } catch (err) {
        errors.push(err);
      }
    }
    if (errors.length > 0) {
      throw new AggregateError(errors, '清理阶段发生资源释放错误');
    }
  }
}
```

按创建顺序 `defer`（先建临时目录 → 开 DB → 启服务），`flush()` 按 LIFO 逆序自动保证“先停服务 → 关 DB → 删目录”，即使前面某一步清理抛错也会把剩余清理全部跑完。

## 4. 零执行顺序依赖

禁止出现“第 1 条用例创建用户、第 2 条用例查询该用户”的隐式串联。自检方式：
- **单条运行**：只执行任意一条用例也能独立通过；
- **倒序/乱序运行**：反转文件或用例顺序（如 `pytest --random-order` 或倒排文件列表）依然全绿；
- **重复运行**：同一用例连续跑 3 遍结果一致且不残留脏数据。

## 5. 用 `scripts/find_polluter.py` 定位单文件污染源

当整套测试跑完后，工作区或指定路径冒出了不该出现的残留文件/目录（如误建的 `.git`、未隔离的缓存目录、意外落盘的 sqlite 文件），但不知道是哪个测试文件干的，直接使用本 skill 附带的零依赖跨平台脚本 `scripts/find_polluter.py`。

### 基本用法（从目标仓库根目录执行）

```sh
# 1. 先手动清理已存在的残留产物（脚本开始前会核查，若已存在会以退出码 2 拒绝执行）
rm -rf .unexpected-cache

# 2. 按文件逐个执行并实时检测谁制造了该产物
python3 <S>/find_polluter.py \
  --artifact .unexpected-cache \
  --cmd "node --test {file}" \
  --cwd /path/to/target-repo \
  spec/alpha.spec.mjs spec/beta.spec.mjs spec/gamma.spec.mjs
```

> `<S>` 为本 skill 目录下的 `scripts/` 绝对路径；`--cmd` 模板中必须包含 `{file}` 占位符。

### 关键参数与退出码语义

| 参数 / 退出码 | 说明 |
| --- | --- |
| `--artifact <路径>` | 必填。不该出现的污染文件或目录路径（相对 `--cwd` 或绝对路径） |
| `--cmd <模板>` | 必填。单文件测试命令模板，必须含 `{file}`，如 `"python3 -m unittest {file}"` |
| `--cwd <目录>` | 执行测试的工作目录（默认当前目录） |
| `--timeout <秒>` | 单个文件的超时上限（可选），防异常用例卡死排查 |
| `--json` | 输出结构化 JSON（含 `found`、`polluter`、`artifact`、`returncode`、`checked`） |
| 退出码 `0` | 全部文件跑完均未产生目标污染产物 |
| 退出码 `1` | 找到**首个**制造污染的文件并立即早停，避免后续文件继续弄脏环境 |
| 退出码 `2` | 参数错误（如缺 `{file}`）、工作目录不存在、超时，或开始前污染产物已存在 |

### 典型 Python / Vitest / Jest 模板示例

```sh
# Python unittest（--json 便于程序化汇总）
python3 <S>/find_polluter.py \
  --artifact .tmp-leak \
  --cmd "python3 -m unittest {file}" \
  --json \
  cases/storage_case.py cases/migration_case.py

# Vitest 单文件执行
python3 <S>/find_polluter.py \
  --artifact .cache-dir \
  --cmd "npx vitest run {file}" \
  spec/auth.spec.ts spec/session.spec.ts
```

## 6. 多文件组合污染二分排查法

如果 `scripts/find_polluter.py` 逐个单跑返回退出码 `0`（每个文件单跑都干净），但整套一起跑时依然出现污染或随机失败，说明属于**跨文件组合污染**（常见原因：A 文件修改了共享环境变量/模块缓存且未复原，导致 B 文件把数据写到了默认路径；或并行竞态争抢同一固定临时路径）。

### 6.1 顺序敏感型组合污染：固定受害者 + 二分前半区

假设已知文件 `V` 单跑通过，但整套跑到 `V` 时失败或产脏：

1. 取位于 `V` 之前的全部文件列表 `P = [F1, F2, ..., Fn]`；
2. 清理残留产物，将 `P` 对半拆分为 `P_left` 与 `P_right`；
3. 运行 `P_left + [V]`：
   - 若复现污染/失败：污染源在 `P_left` 内，令 `P = P_left` 继续二分；
   - 若干净通过：再测 `P_right + [V]`；若复现则令 `P = P_right` 继续二分；
   - 若两半各自加 `V` 都干净（三文件以上联合触发）：改为删减二分（delta debugging），把 `P` 拆成 4 份，每次去掉 1 份测试其余组合。
4. 在 $\lceil \log_2 n \rceil$ 轮内即可将数百个测试文件收敛到最小污染对 `(A, V)`；
5. 随后对比 `A` 执行前后 `process.env`、`process.cwd()`、全局单例与磁盘目录快照，一眼锁定未复原的状态。

### 6.2 并发竞态型污染排查

若仅在并发执行（如多 worker）时出现污染或偶发失败，而加单进程串行参数（如 `--runInBand` / `-n 0` / `--test-concurrency=1`）立刻消失：
- 搜索所有测试代码中**固定命名的临时路径**（如 `/tmp/app-fixed`）、**固定端口**（如 `3000`、`8080`）或**共享 SQLite 文件名**；
- 全部替换为每次调用唯一生成的临时目录（`mkdtemp`）与动态端口 `0`；
- 修复后连续并发跑 5–10 轮确认零失败、零残留。

## 隔离交付检查清单

- [ ] 无任何测试读写真实 `$HOME`、真实生产/用户配置目录或仓库工作树
- [ ] 所有环境变量与 `cwd` 修改均在 `finally` / `afterEach` 精确恢复
- [ ] 资源严格按“停定时/任务 → 停服务/子进程 → 关 DB/流 → 复原 env → 删临时目录”释放
- [ ] 任意单文件、单用例及乱序执行结果完全一致
- [ ] 若排查过污染源，已修复根因并复跑整套测试确认 `git status` 与工作区零新增脏文件
