# 四层纵深防御（Defense-in-Depth）

查明根因并在源头修好后，只在一个地方加一条 `if` 校验看起来似乎足够了。但在真实工程里，**单点校验必然会在未来被另一条调用路径、后台任务、代码重构或单元测试 Mock 绕过**。

- **单点校验**：“我们修好了这个 Bug。”
- **四层纵深防御**：“我们让这类 Bug 在结构上不可能发生。”

**核心原则：在数据流经的每一层关键边界都建立独立防线，彼此互不假设上游已经帮自己校验过。**

---

## 1. 四层纵深防御架构总览

```text
外部输入 / 调用方
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: 入口边界校验（Entry Point Validation）             │ 拦截显而易见的空值、类型错误、不存在路径
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: 业务逻辑不变量校验（Business Logic Validation）    │ 即使绕过入口直调领域服务，仍守住业务前置条件
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: 环境与危险原语守卫（Environment Guards）           │ 在写盘/删目录/执行命令处按上下文强拒越界破坏
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: 前置诊断插桩（Debug Instrumentation）              │ 执行高危动作前留存堆栈与脱敏上下文，便于事后取证
└─────────────────────────────────────────────────────────────┘
```

| 层级 | 防线位置 | 核心职责 | 兜住其他层漏掉的场景 |
| --- | --- | --- | --- |
| **Layer 1** | API / IPC / CLI / 公开入口 | 在系统边界即刻拒绝非法、空值、越界输入 | 挡住 90% 的外部错误调用与畸形载荷 |
| **Layer 2** | 领域服务 / 用例核心方法 | 断言当前操作必需的业务不变量 | 挡住内部旁路调用、定时任务、重构后的新调用入口 |
| **Layer 3** | 危险底层原语（FS / Git / DB / Shell） | 按运行环境强拒破坏性越界动作 | 挡住 Mock 绕过上层、跨平台路径差异、测试污染源码 |
| **Layer 4** | 高危原语执行前一刻 | 记录结构化操作摘要与脱敏调用栈 | 当出现未知新误用路径时，第一时间给出精确取证线索 |

---

## 2. 四层完整 TypeScript 代码模板

下面以“创建项目 → 初始化工作区 → 执行 `git init`”为例，展示四层防线的完整生产级写法。

### Layer 1：入口边界校验（Entry Point Validation）

**目标**：在公开入口第一时间拒绝空字符串、空白符、不存在路径或非目录路径。

```ts
import fs from 'node:fs';
import path from 'node:path';

export function createProject(name: string, workingDirectory: string): ProjectRecord {
  if (!name || name.trim() === '') {
    throw new Error('项目名称不能为空');
  }
  if (!workingDirectory || workingDirectory.trim() === '') {
    throw new Error('workingDirectory 不能为空');
  }
  const resolved = path.resolve(workingDirectory);
  if (!fs.existsSync(resolved)) {
    throw new Error(`workingDirectory 不存在: ${resolved}`);
  }
  if (!fs.statSync(resolved).isDirectory()) {
    throw new Error(`workingDirectory 不是有效目录: ${resolved}`);
  }
  return workspaceManager.initializeWorkspace(resolved, name.trim());
}
```

### Layer 2：业务逻辑不变量校验（Business Logic Validation）

**目标**：绝不假设所有调用者都走过 `createProject`；领域服务自己守住前置不变量。

```ts
export function initializeWorkspace(projectDir: string, sessionId: string): ProjectRecord {
  if (!projectDir || !path.isAbsolute(projectDir)) {
    throw new Error(`初始化工作区需要合法的绝对路径 projectDir，实际收到: ${JSON.stringify(projectDir)}`);
  }
  if (!sessionId || sessionId.trim() === '') {
    throw new Error('初始化工作区必须提供非空 sessionId');
  }
  // 业务状态约束：禁止在受保护系统根路径上初始化
  if (projectDir === path.parse(projectDir).root) {
    throw new Error('禁止将文件系统根目录作为项目工作区');
  }
  return worktreeManager.createSessionWorktree(projectDir, sessionId);
}
```

### Layer 3：环境与危险原语守卫（Environment Guards）

**目标**：在最靠近破坏性系统调用的底层原语里，根据运行环境建立最后一道硬闸门。注意使用 `path.relative` + `realpathSync` 避免 `/tmp-evil` 这样的 `startsWith` 前缀碰撞漏洞！

```ts
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

function isWithinDirectory(baseDir: string, targetDir: string): boolean {
  const realBase = fs.realpathSync(path.resolve(baseDir));
  const realTarget = fs.existsSync(targetDir)
    ? fs.realpathSync(path.resolve(targetDir))
    : path.resolve(targetDir);
  const rel = path.relative(realBase, realTarget);
  return rel !== '..' && !rel.startsWith(`..${path.sep}`) && !path.isAbsolute(rel);
}

export async function gitInit(directory: string): Promise<void> {
  if (!directory || directory.trim() === '') {
    throw new Error('gitInit 拒绝空目录参数（防止退化到 process.cwd()）');
  }

  // 环境守卫：测试环境下严禁在系统临时目录之外执行 git init
  if (process.env.NODE_ENV === 'test') {
    const allowedTmpRoot = os.tmpdir();
    if (!isWithinDirectory(allowedTmpRoot, directory)) {
      throw new Error(
        `测试环境守卫：拒绝在临时目录 (${allowedTmpRoot}) 之外执行 git init: ${directory}`,
      );
    }
  }

  await runGitInitWithInstrumentation(directory);
}
```

### Layer 4：前置诊断插桩（Debug Instrumentation）

**目标**：在执行危险动作前记录足够用于事后取证的结构化上下文（严禁记录任何凭据明文）。

```ts
async function runGitInitWithInstrumentation(directory: string): Promise<void> {
  const stack = new Error('gitInit callsite').stack;
  logger.debug('准备执行 git init', {
    directory,
    cwd: process.cwd(),
    nodeEnv: process.env.NODE_ENV,
    // 仅截取有意义的调用帧，避免日志爆炸；绝不打印环境变量全量（可能含 Token）
    callsite: stack?.split('\n').slice(1, 8).join('\n'),
  });

  await execFileAsync('git', ['init'], { cwd: directory });
}
```

---

## 3. 落地四步法与“逐层绕过验证”协议

每次修复由非法数据、越界路径或脏状态引发的高危缺陷后，按以下 4 步落地纵深防御：

1. **绘制坏值数据流**：标出非法值从诞生、传递、转换到最终触发危险操作的完整链路。
2. **列出全部必经检查点**：识别入口层、领域层、底层危险原语与观测日志位置。
3. **逐层实现独立防线**：每层只依赖自己的参数和环境事实，不依赖上层标记位。
4. **执行逐层绕过验证（Layer-Bypass Verification）**：如果只测入口，你根本不知道 Layer 2 和 Layer 3 是否真的生效！必须编写独立用例**故意绕过上一层**来验证下一层是否能稳稳接住。

### 逐层绕过验证用例骨架（`spec/workspace-defense.spec.ts`）

```ts
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';

describe('工作区路径四层纵深防御验证', () => {
  it('Layer 1：入口 createProject 拦截空串与不存在目录', () => {
    expect(() => createProject('demo', '')).toThrow(/workingDirectory 不能为空/);
    expect(() => createProject('demo', '/path/definitely/missing')).toThrow(/不存在/);
  });

  it('Layer 2：绕过 Layer 1 直接调用 initializeWorkspace，仍拦截相对路径与根目录', () => {
    expect(() => initializeWorkspace('./relative', 'sess-1')).toThrow(/绝对路径/);
    expect(() => initializeWorkspace(path.parse(process.cwd()).root, 'sess-1')).toThrow(/根目录/);
  });

  it('Layer 3：绕过前两层直调 gitInit，测试环境守卫拒绝 tmpdir 外的路径及前缀碰撞', async () => {
    const repoRoot = process.cwd();
    await expect(gitInit(repoRoot)).rejects.toThrow(/测试环境守卫/);

    // 额外验证前缀碰撞：例如 /var/folders/...-evil 不应被误判在 tmpdir 内
    const fakeSibling = `${os.tmpdir()}-evil-sibling`;
    await expect(gitInit(fakeSibling)).rejects.toThrow(/测试环境守卫/);
  });

  it('Layer 4：合法路径执行前稳定输出可定位调用栈且不泄露凭据', async () => {
    const debugSpy = vi.spyOn(logger, 'debug');
    const safeTmp = createTempDir();
    await gitInit(safeTmp);
    expect(debugSpy).toHaveBeenCalledWith(
      '准备执行 git init',
      expect.objectContaining({
        directory: safeTmp,
        callsite: expect.any(String),
      }),
    );
  });
});
```

---

## 4. 真实实战复盘：为什么四层缺一不可

在真实排查“空 `projectDir` 导致源码目录被 `git init` 污染”的工程实践中，四层防线各自拦截到了其他三层漏掉的问题：

| 实际触发场景 | 为什么前面的层没拦住 | 最终由哪一层兜住 |
| --- | --- | --- |
| 新命令行工具直接调领域层建项目 | 没走原 IPC/API 入口 | **Layer 2** 业务逻辑校验拦住 |
| 某条集成验证 Mock 掉了 `WorkspaceManager` | 业务层被替身绕过 | **Layer 3** 环境守卫拒绝在 `tmpdir` 外建仓 |
| 不同操作系统 `tmpdir` 为符号链接（macOS `/var` → `/private/var`） | 简单字符串前缀比对误放行或误拦截 | **Layer 3** `realpathSync + path.relative` 守住 |
| 某后台定时任务在特殊生命周期反复误触发底层调用 | 前三层虽抛错，但异步栈丢失最初入口 | **Layer 4** 前置栈追踪瞬间定位调用者 |

> **收尾纪律**：不要止步于“加了一处校验，原报错消失了”。每遇到一次高危数据/路径/权限故障，就顺手把对应链路的四层防线补全并通过逐层绕过验证，把一次性修补沉淀为永久结构安全。
