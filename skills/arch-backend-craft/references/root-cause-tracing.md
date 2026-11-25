# 调用链逆向溯源（Root Cause Tracing）

复杂后端与主进程 Bug 往往在调用栈最深处才引爆——例如在源码根目录建出 `.git`、文件落盘到错误路径、数据库以空字符串打开、序列化阶段抛出类型错误。人的本能是在报错那一行加一个 `if (!dir) return`，但那只是**捂住症状，把明确报错伪装成静默数据损坏**。

**核心原则：沿着调用链逐层逆向回溯，直到找到最初注入非法值或坏状态的原始触发点，从源头修复，再叠加纵深防御。**

---

## 1. 何时必须逆向溯源（决策流程图）

```text
[发现故障位于调用栈深处]
          │
          ▼
    能否向上回溯一层？
     ├── 否（已是系统最外层入口或外部不可控边界）──▶ 在边界强拒非法输入（仍不得静默吞错）
     └── 是
          │
          ▼
  沿着调用链向上追问：谁传了这个坏值？
          │
          ▼
    这一层是坏值的最初诞生点吗？
     ├── 否 ──▶ 继续向上回溯（人工读代码或插入前置栈追踪探针）
     └── 是
          │
          ▼
  [在最初源头修复根因] ──▶ [在各必经层叠加四层纵深防御] ──▶ [同类故障结构性不可能复发]
```

**典型适用信号**：
- 异常发生在底层工具函数、文件系统、数据库驱动或子进程封装内部（而非 API / CLI 入口）；
- 错误堆栈跨越 3 层以上函数调用；
- 肉眼看不出非法值（空字符串、越界路径、`undefined`、脏上下文）究竟是在哪一步混进来的；
- 自动化套件运行后工作目录或共享状态被莫名污染，不知道是哪条用例干的。

---

## 2. 五步逆向调用链溯源法

下面用真实故障链路完整演示 5 个标准步骤：

### Step 1：完整观察症状（Observe the Symptom）
不截断错误、不靠转述，先记录完整报错与副作用现场：
```text
Error: git init 在 ~/project/packages/core（源码目录）中被触发，污染了仓库工作树
```

### Step 2：定位直接触发代码（Find Immediate Cause）
找到直接产生该报错或危险副作用的那一行：
```ts
// packages/core/worktree-manager.ts
await execFileAsync('git', ['init'], { cwd: projectDir });
```

### Step 3：追问“谁调用了这里”（Ask: What Called This?）
从直接触发点逐层向上展开调用链：
```text
WorktreeManager.createSessionWorktree(projectDir, sessionId)
  ▲ 调用者：Session.initializeWorkspace()
  ▲ 调用者：Session.create()
  ▲ 调用者：验证套件 spec/project-lifecycle.spec.ts 中的 Project.create()
```

### Step 4：核实每一层传递的真实值（Keep Tracing Up）
不要猜参数是什么，打印或核实每一层传下来的**实际运行时值**：
- 发现 `projectDir === ''`（空字符串！）；
- Node.js 的 `execFile` 在 `cwd: ''` 时会自动退化为 `process.cwd()`；
- 而 `process.cwd()` 正是源码目录 `~/project/packages/core`！

### Step 5：找到最初诞生坏值的触发源（Find Original Trigger）
继续往上查这个空字符串是在哪一行代码里诞生的：
```ts
// spec/project-lifecycle.spec.ts
const context = setupCoreHarness(); // 顶层初始化返回占位对象 { tempDir: '' }
// 在 describe 顶层就读取了 context.tempDir——此时 beforeEach 还没运行！
Project.create('demo-project', context.tempDir);
```
到这里才算真正追到源头：**问题既不在 `gitInit`，也不在 `WorktreeManager`，而在 `setupCoreHarness()` 允许调用方在生命周期就绪前静默读到一个空字符串 `''`**。

---

## 3. 操作前栈追踪插桩技术（Stack Trace Instrumentation）

当调用路径很多、动态回调或异步事件导致无法纯靠肉眼向上追踪时，**在危险操作执行之前**插入栈追踪探针。

### 标准前置插桩代码模板

```ts
async function gitInit(directory: string): Promise<void> {
  // 关键：必须在危险操作执行【之前】捕获，而不是等它失败或污染完再记录
  const stack = new Error('TRACE_GIT_INIT_CALLSITE').stack;
  console.error('[DEBUG gitInit]', {
    directory,
    cwd: process.cwd(),
    nodeEnv: process.env.NODE_ENV,
    timestamp: new Date().toISOString(),
    stack,
  });

  await execFileAsync('git', ['init'], { cwd: directory });
}
```

### 插桩四条铁律

1. **在操作之前打印**：危险动作（写盘、删目录、`git init`、改表）一旦触发就可能破坏现场或吞掉上下文，必须先打堆栈再执行。
2. **排查期优先用 `console.error()` 而非业务 Logger**：在测试或最小复现脚本里，结构化 Logger 经常被级别过滤、异步缓冲或直接静默，导致什么都看不到。
3. **带足环境上下文**：除了 `new Error().stack`，必须一并打印目标参数、当前 `cwd`、关键环境变量（注意先对敏感字段脱敏）和时间戳。
4. **抓完证据立即定向过滤，并在修复后彻底删除探针**：

```bash
# 运行复现套件并精确抓取每次危险调用的完整调用栈
pnpm run spec 2>&1 | grep -A 12 '\[DEBUG gitInit\]'
```

分析输出的栈帧时重点看：
- 哪个用例文件或业务入口反复出现在调用链顶端？
- 触发调用的精确行号是什么？
- 每次出问题时传入的参数是否存在固定模式（空串、相对路径、未初始化字段）？

---

## 4. 自动二分定位状态污染源脚本

当运行整套验证后磁盘冒出脏文件（如意外的 `.git` 或残余目录），却不知道是几百条用例中的哪一条造成的，用以下逐文件探测脚本精准锁定第一个污染源：

```bash
#!/usr/bin/env bash
# 用法：bash scripts/find-polluter.sh '.git' 'spec/**/*.spec.ts'
set -euo pipefail

ARTIFACT="$1"
GLOB_PATTERN="$2"

if [ -e "$ARTIFACT" ]; then
  echo "请先清理当前已存在的污染产物: $ARTIFACT" >&2
  exit 2
fi

for file in $(find spec -name '*.spec.ts' | sort); do
  echo ">>> 检查: $file"
  pnpm exec vitest run "$file" >/dev/null 2>&1 || true
  if [ -e "$ARTIFACT" ]; then
    echo "!!! 锁定首个污染源: $file（产生了 $ARTIFACT）"
    exit 1
  fi
done

echo "未在给定文件集中发现产生 $ARTIFACT 的污染源"
```

> 锁定单个文件后，再在该文件内用前置栈追踪插桩或二分用例块，通常 2 分钟内即可定位到精确行号。

---

## 5. 真实 5 层溯源案例完整剖析

| 溯源层级 | 现场观察与真实状态 | 若在此层打补丁的后果 |
| --- | --- | --- |
| **第 1 层（症状点）** | `git init` 在 `process.cwd()` 执行，污染 `packages/core/` | 加 `if (!dir) return` 会让上层以为初始化成功，后续报更诡异的错 |
| **第 2 层** | `WorktreeManager.createSessionWorktree('')` 收到空串 | 仅在此抛错能止损，但调用方仍不知道空串怎么来的 |
| **第 3 层** | `Session.create()` 把空 `projectDir` 透传给工作树管理器 | 仍未修复坏值诞生源 |
| **第 4 层** | `spec/project-lifecycle.spec.ts` 在 `beforeEach` 前访问 `context.tempDir` | 暴露了使用顺序问题，但为什么没在读取瞬间就炸？ |
| **第 5 层（真源头）** | `setupCoreHarness()` 用普通属性 `{ tempDir: '' }` 初始化占位值 | **真根因！** 任何过早读取都会静默拿到空串并向下游扩散 |

### 源头修复 + 四层防御闭环

1. **源头根治**：把 `context.tempDir` 改为 `getter`，在 `beforeEach` 尚未分配真实临时目录前任何访问都**立刻抛出明确异常**，彻底消灭空串诞生路径：
   ```ts
   export function setupCoreHarness() {
     let activeTempDir: string | null = null;
     return {
       setTempDir(dir: string) { activeTempDir = dir; },
       reset() { activeTempDir = null; },
       get tempDir(): string {
         if (!activeTempDir) {
           throw new Error('Harness 尚未初始化：禁止在 beforeEach 之外读取 context.tempDir');
         }
         return activeTempDir;
       },
     };
   }
   ```
2. **同步加固四层纵深防御**：
   - 第 1 层：`Project.create()` 校验目录非空、存在、且确为目录；
   - 第 2 层：`WorkspaceManager` 校验 `projectDir` 非空不变量；
   - 第 3 层：`NODE_ENV === 'test'` 环境守卫拒绝在系统临时目录之外执行 `git init`；
   - 第 4 层：`git init` 执行前记录结构化调试堆栈，留存取证证据。

结果：整套 1847 条验证全部通过，源码目录零污染。

---

## 6. 何时才算真正追到了源头（停止判据）

在准备动手写修复代码前，用以下 4 条判据自检——**有任意一条答不上来，说明还没追到底**：

| 自检问题 | 合格标准 | 不合格信号（继续上溯） |
| --- | --- | --- |
| **1. 精确诞生点** | 能指明“哪一文件哪一行、在什么时机”生成了这个坏值或脏状态 | 只能说“大概是上游传错了” |
| **2. 因果闭环** | 能一步步推演坏值如何从诞生点无阻碍流到报错点 | 中间有断层，靠猜连接 |
| **3. 下游零补丁依赖** | 修完源头后，下游无需靠“猜默认值/静默跳过”也能正常工作 | 必须同时在报错点加兜底吞错才不崩 |
| **4. 解释既往行为** | 能解释为什么以前没暴露、为什么在特定输入或时序下才触发 | 无法解释触发条件，归咎于“玄学偶发” |
