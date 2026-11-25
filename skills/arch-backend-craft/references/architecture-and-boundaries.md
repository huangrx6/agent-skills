# 系统架构与模块边界

好的系统架构不是抽象层级越多越“高级”，而是**事实源唯一、模块所有权一眼看清、依赖方向严格无环、跨层配置优先级单向明确**。架构演进的目标是降低变更半径与认知负担，而不是提前堆砌无人调用的抽象层。

## 1. 单源事实（SSOT）与派生数据规则

任何核心业务状态、配置或执行事实，在全系统中只能有**唯一权威来源（Single Source of Truth）**。

### 判定与分层准则

| 角色 | 典型载体 | 写入权限 | 同步方向 |
| --- | --- | --- | --- |
| **权威事实源（SSOT）** | 运行时引擎状态机、主数据库核心表、受托管主配置 | 唯一拥有写入口的归属模块 | 向下发布变更事件或供查询 |
| **持久化投影（Projection）** | 列表索引表、搜索视图、摘要快照 | 仅由订阅者/同步器单向刷新 | 权威源 → 投影（只读派生） |
| **内存与表现层缓存** | 进程内 LRU、前端 Store、表单草稿 | 仅作临时视图或待提交编辑态 | 权威源 → 缓存；修改必须回流到权威写入口 |

### 反例 vs 正例：防双向写入脑裂

```ts
// ❌ 反例：配置同时写主表和内存缓存，前端还直接拼装覆盖，形成双写脑裂
async function updateProvider(id: string, patch: ProviderPatch) {
  memoryCache.set(id, { ...memoryCache.get(id), ...patch }); // 旁路写入 1
  await db.run('UPDATE providers SET name = ? WHERE id = ?', [patch.name, id]); // 旁路写入 2
  // 若 DB 失败，内存已脏；若另一路径只改 DB，内存永久过期
}

// ✅ 正例：所有写入只走权威存储事务，成功后再单向刷新派生视图与事件
async function updateProvider(id: string, patch: ProviderPatch): Promise<ProviderDTO> {
  const updated = db.transaction(() => {
    const next = providerRepo.applyPatch(id, patch); // 唯一写入口
    return toProviderDTO(next);
  })();
  projectionHub.refreshProvider(updated.id); // 单向派生刷新
  eventBus.emit('provider:updated', { id: updated.id, revision: updated.revision });
  return updated;
}
```

> **核心纪律**：只要出现“A 改完同步 B，B 改完又同步 A”的双向同步回路，就必然在并发、重试或重启瞬间产生脑裂。遇到这种冲动时，立刻停下来重新指认谁是权威源。

---

## 2. 模块所有权与唯一公开入口

### 公开入口封装（Facade / Public Entrypoint）

每个领域或能力模块必须有明确的目录归属与**唯一公共入口**（如 `capabilities/auth/index.ts` 或 `capabilities/auth/index.cjs`）。模块内部的子文件（仓库访问、状态转换、内部工具）一律视为私有实现：

- **允许**：跨模块仅导入 `capabilities/auth/index.ts` 或共享契约目录（如 `core/contracts.ts`）。
- **禁止**：跨模块深插私有路径（如 `import { rawTokenStore } from '../auth/internal/store'`）。

### 显式静态注册 vs 运行时目录扫描

对内置能力、路由表、核心服务等关键清单，优先使用**显式静态注册表**而非启动时动态 `readdir` 扫描：

```ts
// ✅ 正例：显式静态注册表——打包器可见、启动顺序确定、依赖校验在启动前完成
import { authCapability } from '../capabilities/auth/index.ts';
import { workspaceCapability } from '../capabilities/workspace/index.ts';
import { billingCapability } from '../capabilities/billing/index.ts';

export const BUILTIN_CAPABILITIES = [
  authCapability,
  workspaceCapability,
  billingCapability,
] as const;
```

优点：静态分析与打包工具可见、初始化顺序确定、缺失依赖在启动校验阶段立刻暴露，不依赖文件系统遍历顺序。

### 拒绝僵尸兼容层

- 不为已经删除的旧模块、废弃 IPC 通道或全库无调用方的历史接口保留兼容壳。
- 仅在需要**保护真实存量用户持久化数据**（数据库表、磁盘配置文件）时编写带版本号的显式迁移逻辑，并对迁移进行版本化追踪。

---

## 3. 无环依赖方向与解耦手法

全系统保持严格的有向无环依赖（DAG），上层可依赖下层，下层绝不反向导入上层：

```text
表现层 / 外部协议适配（HTTP / IPC / CLI）
        │  仅调用公开入口，传递纯 JSON DTO
        ▼
能力 / 业务编排层（Capabilities / Use Cases）
        │  能力之间不互插私有实现；跨能力协作通过公开接口或事件
        ▼
核心领域与契约层（Core Domain / Contracts / Errors）
        │  纯业务规则与稳定类型，不依赖框架与传输协议
        ▼
基础设施层（SQLite / FS / Crypto / Logger / Clock）
```

### 出现循环依赖时的 3 种标准拆解法

1. **提取共享契约下沉**：若模块 A 和 B 互相导入对方的类型或错误码，把稳定接口与错误类型下沉到 `core/contracts.ts`，A 与 B 单向依赖它。
2. **依赖倒置（注入端口）**：若底层服务需要触发上层能力，在底层定义最小回调接口（Port），由顶层组装入口（如主进程 `index.ts`）注入实现。
3. **事件解耦（单向通知）**：若 A 完成后需要通知 B 做异步衍生工作（如清理缓存、写审计日志），A 只发出领域事件，由 B 订阅，A 对 B 零编译依赖。

---

## 4. 按职责拆分而非按技术层拆分

模块化与规划拆分必须服从**变化聚合律**（一起变更的代码住在一起），而非机械按“controllers / services / utils”横向切碎：

### 文件职责与规划拆分四原则

1. **按业务职责纵向切分**：一个能力目录内聚其入口、校验、领域逻辑与持久化适配，避免改一个字段要同时横跨 6 个技术层目录翻找。
2. **单文件清晰边界与合适体积**：一个文件只承担一项可一眼讲清的职责；工程师和审查者能一次性放进上下文完整推理的文件，改动失误率远低于千行“上帝文件”。
3. **任务与模块右尺寸（Right-Sizing）**：划分实施单元时，把配置、脚手架与文档折入对应交付单元；**只在评审员能够合理打回单元 A 同时批准单元 B 的边界处拆分**。每个单元交付独立可验证的行为与精确接口签名（Consumes / Produces）。
4. **尊重存量代码库惯例**：在已有大型代码库中不擅自发起大规模目录重构；但当你正在修改的单个文件已经膨胀失控、职责混杂时，顺势拆出独立职责模块是合理且必要的。

---

## 5. 多层作用域优先级与禁反向推导

当配置或策略存在多层作用域（例如 `全局 Default → 用户 User → 工作区 Workspace → 项目 Project → 会话 Session`）时，必须遵守两条铁律：

1. **优先级单向显式声明**：窄作用域覆盖宽作用域，必须明确区分 **`undefined`（未设置，继承上层）** 与 **`null` / `""` / `[]`（显式清空，阻断继承）**。
2. **严禁反向推导（No Upward Leakage）**：绝不能从较窄作用域的值反推、回写或猜想较宽作用域的默认配置（例如读取某项目配置时顺手改写用户级默认设置）。

### 标准作用域解析实现

```ts
export type ScopeLevel = 'global' | 'user' | 'workspace' | 'project' | 'session';

export interface ScopedPolicy {
  timeoutMs?: number;
  allowedHosts?: string[]; // [] 表示显式清空，undefined 表示继承上层
  proxyUrl?: string | null; // null 表示显式禁用代理，undefined 表示继承
}

export interface EffectivePolicy {
  timeoutMs: number;
  allowedHosts: string[];
  proxyUrl: string | null;
  sources: Record<'timeoutMs' | 'allowedHosts' | 'proxyUrl', ScopeLevel>;
}

const SCOPE_ORDER: readonly ScopeLevel[] = [
  'global',
  'user',
  'workspace',
  'project',
  'session',
];

export function resolvePolicy(
  layers: Partial<Record<ScopeLevel, ScopedPolicy>>,
  defaults: Required<ScopedPolicy>,
): EffectivePolicy {
  const result: EffectivePolicy = {
    timeoutMs: defaults.timeoutMs,
    allowedHosts: [...defaults.allowedHosts],
    proxyUrl: defaults.proxyUrl,
    sources: {
      timeoutMs: 'global',
      allowedHosts: 'global',
      proxyUrl: 'global',
    },
  };

  for (const level of SCOPE_ORDER) {
    const patch = layers[level];
    if (!patch) continue;

    // 仅当字段显式定义（!== undefined）时覆盖；null / [] 视为合法显式覆盖
    if (patch.timeoutMs !== undefined) {
      result.timeoutMs = patch.timeoutMs;
      result.sources.timeoutMs = level;
    }
    if (patch.allowedHosts !== undefined) {
      result.allowedHosts = [...patch.allowedHosts];
      result.sources.allowedHosts = level;
    }
    if (patch.proxyUrl !== undefined) {
      result.proxyUrl = patch.proxyUrl;
      result.sources.proxyUrl = level;
    }
  }

  return result; // 纯函数，绝不回写任何输入层或宽作用域存储
}
```

---

## 6. 架构决策与方案权衡（ADR）完整模板

跨模块重构或引入核心子系统前，先输出精炼的架构决策记录（ADR），锁定边界、契约与隐含风险后再写代码。

### 标准模板

```markdown
# ADR-<编号>：<架构主题>

- **状态**：提议中 / 已采纳 / 已废弃
- **影响范围**：<受影响模块与入口列表>
- **明确不改**：<本轮刻意排除的区域，防范围蔓延>

## 1. 背景与核心问题
用 2–4 句话说明当前痛点、触发契机与硬约束（版本底线、兼容要求、平台限制）。

## 2. 事实源与数据流
- **唯一权威源（SSOT）**：<表/文件/运行时模块>
- **派生视图与刷新路径**：<谁读取、如何单向同步>
- **模块公开入口与依赖方向**：<Consumes / Produces 精确签名>

## 3. 备选方案权衡（2–3 选 1）

| 维度 | 方案 A（推荐） | 方案 B | 方案 C |
| --- | --- | --- | --- |
| 改动半径 | 小（仅 2 个能力模块） | 中（需改公共契约） | 大（重写存储层） |
| 复杂度与维护成本 | 低，职责内聚 | 中，需维护双路径 | 高 |
| 存量兼容与迁移成本 | 版本迁移平滑升级 | 需停机重建 | 需导出导入 |
| 失败回滚难度 | 单步回滚 | 中 | 不可逆 |

**决策结论**：选择方案 A，因为 <一句话说明核心取舍依据>。

## 4. 跨边界契约变更
- **接口/通道名**：`domain:action` 或 `POST /api/v1/...`
- **入参 Schema**：字段、类型、上限、必填项
- **出参 DTO**：纯 JSON 结构，不含内部句柄/路径/凭据
- **错误码**：`INVALID_INPUT` / `CONFLICT` / `FORBIDDEN` 等

## 5. 迁移、并发与回滚策略
- Schema 版本号推进方案、存量数据无损转换、并发修订号校验、失败回滚路径。

## 6. 评审关注点（Review Focus）
列出规格未明写但最可能伤害真实用户的 5 类输入或失效模式，每条对应到归属模块与验收用例：
1. <失效模式 1：输入/条件 → 合理预期行为 → 归属模块>
2. <失效模式 2：...>
3. <失效模式 3：...>
4. <失效模式 4：...>
5. <失效模式 5：...>

## 7. 验证计划
- 单元与边界验证（精确到行为断言与用例文件，如 `spec/policy.spec.ts`）
- 集成与存量迁移验证（旧版本库升级、并发冲突、断电/异常回滚）
```

### 精炼填写示范（片段）

> **示例：桌面应用新增扩展安装能力**
> - **唯一权威源**：SQLite `installed_extensions` 表保存安装态元数据；磁盘受管目录保存包体文件。
> - **方案权衡**：在“先写库后解压”与“隔离暂存校验 → 目录原子替换 → 事务落库 → 失败回滚目录”之间选择后者，避免半解压损坏包污染运行态。
> - **Review Focus 样例**：
>   1. ZIP 内含 `../../.ssh/authorized_keys` 路径穿越 → 暂存阶段即刻拒绝，不写目标目录。
>   2. 升级安装到一半写库抛磁盘满异常 → 自动删新目录并恢复旧备份目录，原扩展可继续使用。
>   3. 同名扩展双击触发并发安装 → 进程内互斥 + 修订号校验拒绝第二次写入并返回 `INSTALL_IN_PROGRESS`。
