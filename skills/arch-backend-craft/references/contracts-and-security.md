# 跨边界契约与安全防线

任何跨进程（IPC / Worker）、跨网络（HTTP / RPC）或跨信任边界（用户输入、外部压缩包、第三方扩展）的数据流，都必须默认**不可信**。本手册提供跨边界纯 JSON 契约、入口强校验、路径防逃逸、归档防炸弹、凭据加密脱敏以及安全边界诚实声明的工程标准。

## 1. 纯净 JSON 序列化契约

跨进程或跨服务传输的所有请求、响应与事件载荷，必须是**可安全 JSON 序列化的纯数据对象（Plain JSON）**。

### 严禁跨边界泄漏的 6 类对象

| 禁止项 | 风险后果 | 正确替代 |
| --- | --- | --- |
| 运行时句柄 / Socket / Stream / Promise | 序列化崩溃或跨进程泄漏内部状态 | 仅传稳定 ID 与状态枚举 |
| 类实例 / 原型方法 / 闭包函数 | 丢失原型或暴露私有内部字段 | 显式白名单映射为普通 DTO 对象 |
| 数据库连接 / Statement / 任务句柄 | 耦合底层实现，破坏分层 | 映射为只读领域视图字段 |
| 宿主内部存储绝对路径 | 暴露操作系统目录结构，诱导前端拼路径 | 传逻辑 ID 或相对展示名 |
| 原始扩展模块实例 / 可执行 HTML/JS/CSS | 触发渲染进程代码执行（XSS / RCE） | 仅传声明式 UI 数据结构 |
| 明文凭据（Token / API Key / Password） | 被渲染层、扩展或前端日志窃取 | 只传 `hasCredential: true` 与脱敏尾号 |

### 白名单 DTO 投影模式（正反例）

```ts
// ❌ 反例：直接把 ORM 行对象或内部实体抛给前端/调用方
ipcMain.handle('account:get', async (_event, id: string) => {
  return accountService.getEntity(id); // 意外带出 encryptedSecret、dbPath、内部类方法
});

// ✅ 正例：显式白名单投影 + 统一结构化错误信封
export interface AccountSummaryDTO {
  readonly id: string;
  readonly displayName: string;
  readonly provider: 'github' | 'gitlab' | 'local';
  readonly hasToken: boolean;
  readonly tokenHint: string | null; // 例如 "****8f2a"
  readonly revision: number;
}

export function toAccountSummaryDTO(entity: AccountEntity): AccountSummaryDTO {
  return {
    id: entity.id,
    displayName: entity.displayName,
    provider: entity.provider,
    hasToken: Boolean(entity.encryptedToken),
    tokenHint: entity.tokenLast4 ? `****${entity.tokenLast4}` : null,
    revision: entity.revision,
  };
}
```

### 结构化错误信封

不要直接把底层驱动或文件系统原始堆栈透传给外部调用方；在边界转换为稳定的错误码 + 面向动作的安全文案，详细堆栈仅写入受控后端日志（且先脱敏）：

```ts
export interface ApiErrorEnvelope {
  readonly ok: false;
  readonly code:
    | 'INVALID_INPUT'
    | 'PATH_OUT_OF_BOUNDS'
    | 'ARCHIVE_UNSAFE'
    | 'CONFLICT'
    | 'NOT_FOUND'
    | 'INTERNAL_ERROR';
  readonly message: string; // 可安全展示给用户的行动导向文案
  readonly requestId: string;
}
```

---

## 2. 入口强校验与原型污染防护

在数据进入业务逻辑之前，必须完成三项检查：**结构类型、数量与长度上限、原型污染键过滤**。

### 原型污染防护与安全字典解析

外部 JSON 对象可能携带 `__proto__`、`constructor`、`prototype` 键；直接用 `Object.assign` 或递归深合并会污染全局 `Object.prototype`。

```ts
const FORBIDDEN_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

export function assertSafePlainObject(
  input: unknown,
  label: string,
  maxKeys = 100,
): Record<string, unknown> {
  if (typeof input !== 'object' || input === null || Array.isArray(input)) {
    throw new BoundaryError('INVALID_INPUT', `${label} 必须是普通对象`);
  }
  const keys = Object.keys(input);
  if (keys.length > maxKeys) {
    throw new BoundaryError('INVALID_INPUT', `${label} 字段数量超出上限 (${maxKeys})`);
  }
  // 使用无原型对象承载外部键值映射，彻底隔离原型链
  const safe: Record<string, unknown> = Object.create(null);
  for (const key of keys) {
    if (FORBIDDEN_KEYS.has(key)) {
      throw new BoundaryError('INVALID_INPUT', `${label} 包含非法保留键: ${key}`);
    }
    safe[key] = (input as Record<string, unknown>)[key];
  }
  return safe;
}
```

### 入口校验必备清单

- **字符串**：非空检查、长度上限（如名称 ≤ 128 字符、备注 ≤ 4 KB）、禁止控制字符/空字节 `\0`。
- **数值**：必须 `Number.isFinite(n)`（防 `NaN` / `Infinity`）、明确上下界（如分页 `limit` 限制在 `1..200`）。
- **枚举**：使用 `Set` 或字面量白名单校验，绝不把外部枚举字符串直接拼进 SQL、Shell 命令或文件名。
- **数组**：校验最大长度，逐项校验元素合法性，防超大数组耗尽内存。

---

## 3. 路径规范化与 `realpath` 防逃逸

只检查 `!userPath.includes('..')` 是极其脆弱的：攻击者可通过编码、反斜杠、前缀碰撞（`/base-evil` 匹配 `/base`）或目录内**符号链接（Symlink）**轻松绕过。

### 完整安全路径解析实现（覆盖已存在与待创建目标）

```ts
import fs from 'node:fs';
import path from 'node:path';

export function resolveSafePath(rootDir: string, untrustedRelative: string): string {
  if (!untrustedRelative || untrustedRelative.includes('\0')) {
    throw new BoundaryError('PATH_OUT_OF_BOUNDS', '路径为空或包含非法空字节');
  }

  const realRoot = fs.realpathSync(path.resolve(rootDir));
  const candidate = path.resolve(realRoot, untrustedRelative);

  // 1. 词法边界检查：防 .. 穿越、绝对路径覆盖、前缀碰撞（/root-evil）
  assertWithinRoot(realRoot, candidate);

  // 2. 真实文件系统边界检查：防符号链接逃逸
  if (fs.existsSync(candidate)) {
    const realTarget = fs.realpathSync(candidate);
    assertWithinRoot(realRoot, realTarget);
    return realTarget;
  }

  // 3. 目标尚不存在时，向上找到最近存在的祖先目录做 realpath 校验
  let cursor = path.dirname(candidate);
  while (!fs.existsSync(cursor)) {
    const parent = path.dirname(cursor);
    if (parent === cursor) break;
    cursor = parent;
  }
  const realAncestor = fs.realpathSync(cursor);
  assertWithinRoot(realRoot, realAncestor);
  return candidate;
}

function assertWithinRoot(realRoot: string, target: string): void {
  const rel = path.relative(realRoot, target);
  // rel === '' 表示根目录本身；以 '..' 开头或仍是绝对路径（如 Windows 跨盘符）即越界
  if (rel === '..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel)) {
    throw new BoundaryError('PATH_OUT_OF_BOUNDS', '目标路径超出允许根目录范围');
  }
}
```

> **注意 TOCTOU（检查时间到使用时间窗口）**：在多进程共享目录场景中，校验后到实际打开之间目录可能被替换为符号链接。高危写操作优先在独立私有的隔离目录内完成，或结合 `O_NOFOLLOW` / `lstat` 拒绝符号链接。

---

## 4. 归档（ZIP / Tar）安全边界与防压缩炸弹

解压任何来自用户、插件市场或网络下载的压缩包时，必须同时防御 **5 类攻击面**：

1. **Zip Slip 路径穿越**：条目名含 `../`、`..\` 或空字节。
2. **绝对路径条目**：条目名以 `/`、`\` 或盘符 `C:` 开头。
3. **符号链接 / 硬链接越界**：归档内包含指向根目录外部的 Symlink 或设备文件。
4. **压缩炸弹（Zip Bomb）**：100 KB 压缩包解压出 10 GB 全零文件（**绝不能轻信 ZIP 头部声称的 `uncompressedSize`**，必须在流式写出时实时计数）。
5. **条目数与深度炸弹**：数万个空文件耗尽 inode 或 100 层嵌套目录触发栈溢出。

### 流式受限解压校验骨架

```ts
export interface ArchiveLimits {
  maxEntries: number;       // 例如 2_000
  maxTotalBytes: number;    // 例如 100 * 1024 * 1024 (100 MB)
  maxSingleFileBytes: number; // 例如 25 * 1024 * 1024 (25 MB)
  maxDepth: number;         // 例如 16
  maxCompressionRatio: number; // 例如 100（仅对较大条目生效）
}

export function validateArchiveEntryPath(rawEntryName: string, limits: ArchiveLimits): string {
  const normalized = rawEntryName.replace(/\\/g, '/');
  if (!normalized || normalized.includes('\0') || normalized.startsWith('/')) {
    throw new BoundaryError('ARCHIVE_UNSAFE', `拒绝绝对路径或非法条目: ${rawEntryName}`);
  }
  if (/^[a-zA-Z]:/.test(normalized)) {
    throw new BoundaryError('ARCHIVE_UNSAFE', `拒绝含盘符条目: ${rawEntryName}`);
  }
  const segments = normalized.split('/').filter(Boolean);
  if (segments.some((seg) => seg === '..' || seg === '.')) {
    throw new BoundaryError('ARCHIVE_UNSAFE', `拒绝路径穿越条目: ${rawEntryName}`);
  }
  if (segments.length > limits.maxDepth) {
    throw new BoundaryError('ARCHIVE_UNSAFE', `归档目录层级超过上限 (${limits.maxDepth})`);
  }
  return segments.join('/');
}

export async function pipeWithByteLimit(
  source: AsyncIterable<Buffer>,
  dest: NodeJS.WritableStream,
  state: { totalBytes: number },
  limits: ArchiveLimits,
): Promise<number> {
  let fileBytes = 0;
  for await (const chunk of source) {
    fileBytes += chunk.length;
    state.totalBytes += chunk.length;
    if (fileBytes > limits.maxSingleFileBytes || state.totalBytes > limits.maxTotalBytes) {
      dest.destroy();
      throw new BoundaryError('ARCHIVE_UNSAFE', '归档解压体积超出安全上限（疑似压缩炸弹）');
    }
    if (!dest.write(chunk)) {
      await new Promise<void>((resolve) => dest.once('drain', resolve));
    }
  }
  return fileBytes;
}
```

对于归档中的 `symlink` / `link` / `character-device` / `fifo` 类型条目：**默认直接拒绝并中断解压**，不要静默跳过后继续安装半残包。

---

## 5. 凭据加密与日志 / URL 脱敏

### 凭据驻留边界

- **唯一存放地**：凭据（API Key、OAuth Refresh Token、数据库密码、私钥）只能驻留在受信任的服务端或桌面应用主进程，落盘必须经由系统安全存储（如 Electron `safeStorage`、macOS Keychain、KMS/Envelope Encryption）加密。
- **零明文出境**：绝不把明文凭据发给渲染进程、浏览器本地存储、扩展回调、崩溃报告或错误提示。
- **诊断可排查性**：需要让用户核对配置时，只返回是否已设置、脱敏后 4 位、过期时间与校验状态。

### 通用 URL 与结构化日志脱敏器

```ts
const SENSITIVE_KEY_RE =
  /^(?:authorization|cookie|set-cookie|token|access_token|refresh_token|api[-_]?key|secret|password|passwd|private[-_]?key)$/i;

export function redactUrl(rawUrl: string): string {
  try {
    const parsed = new URL(rawUrl);
    if (parsed.username) parsed.username = '***';
    if (parsed.password) parsed.password = '***';
    for (const [key] of parsed.searchParams) {
      if (SENSITIVE_KEY_RE.test(key)) {
        parsed.searchParams.set(key, '[REDACTED]');
      }
    }
    return parsed.toString();
  } catch {
    // 即使不是合法 URL，也兜底脱敏常见 query 参数与 Bearer Token
    return rawUrl
      .replace(/(Bearer\s+)[A-Za-z0-9._~+/=-]+/gi, '$1[REDACTED]')
      .replace(/([?&](?:token|key|api_key|password|secret)=)[^&\s]+/gi, '$1[REDACTED]');
  }
}

export function redactRecord(value: unknown, depth = 0): unknown {
  if (depth > 6 || value === null || value === undefined) return value;
  if (typeof value === 'string') return redactUrl(value);
  if (Array.isArray(value)) return value.map((item) => redactRecord(item, depth + 1));
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = SENSITIVE_KEY_RE.test(k) ? '[REDACTED]' : redactRecord(v, depth + 1);
    }
    return out;
  }
  return value;
}
```

---

## 6. 受信任代码与 OS 沙箱的诚实界定

在架构设计、文档说明与代码评审中，必须对安全边界保持**绝对技术诚实**，严禁把“防误操作守卫”包装成“操作系统级安全沙箱”。

| 安全机制 | 实际能提供的保障 | 绝对不能宣称的能力 |
| --- | --- | --- |
| **完整性哈希 / 签名校验** | 发现文件在传输或存放后是否被篡改，锁定受信任来源 | 不能阻止已签名代码在主进程内读写宿主文件或访问网络 |
| **静态命令 / AST 扫描** | 拦截低级显式危险调用，作为纵深防线的一环 | 不能构成沙箱（动态拼接、反射、原生模块可轻易绕过） |
| **声明式 UI 协议** | 渲染层只渲染受控组件数据，避免扩展注入任意 HTML/JS/CSS | 不能替代扩展后端代码本身在主进程执行的信任模型 |
| **OS 级沙箱（容器 / Seatbelt / seccomp / 独立低权用户）** | 由内核强制限制文件系统、网络、系统调用与资源配额 | 仅当真正启用内核隔离机制并经实测验证时才可声明 |

> **工程准则**：如果插件/扩展是以 Node.js / Python 代码直接在主进程执行的，必须在信任确认提示与文档中如实说明“该扩展以受信任代码运行”，并把安全重点放在**显式用户授权、来源完整性校验、最小化凭据暴露与清晰的数据边界**上。
