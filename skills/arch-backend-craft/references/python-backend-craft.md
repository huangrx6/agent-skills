# Python 后端专项规范

面向 Python 3.10+ 后端服务（FastAPI / Starlette / Django / SQLAlchemy 2.x / Alembic / `asyncio`）的高频生产工程规范与深坑防线。通用架构、调试与评审纪律仍以核心参考为准，本手册补充 Python 运行时与生态特有的关键陷阱。

## 1. 模块边界、配置与可变状态陷阱

### 公开入口与配置单源化
- 每个业务包通过 `__init__.py`（配合 `__all__`）暴露唯一公共接口，外部模块禁止深插内部 `_repo.py` / `_internal.py`。
- 应用配置统一通过 `pydantic-settings`（或显式 dataclass 加载器）在启动期解析并校验完毕，**严禁在业务函数里散落 `os.environ.get(...)`**；凭据使用 `SecretStr` 承载，防止意外被 `repr()` / 日志打成明文。

### 避开 Python 经典状态与默认参数陷阱
- **禁止可变默认参数**：`def add(items: list[str] = [])` 会在进程内跨请求共享同一个列表，改为 `items: Sequence[str] | None = None`。
- **禁止模块级全局连接/请求态对象**：不要把当前用户、租户或 DB Session 存在模块全局变量里；跨协程上下文使用 `contextvars.ContextVar`（并成对 `reset(token)`）。

---

## 2. 边界契约与 Pydantic v2 强校验

API 请求体、响应体与内部 ORM 模型必须分离，严禁直接把 SQLAlchemy / Django Model 原样序列化返回：

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class CreateWorkspaceReq(BaseModel):
    # extra="forbid" 防止未知字段悄悄穿透或触发质量赋值风险
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128)
    trust_level: Literal["untrusted", "workspace", "trusted"] = "untrusted"
    max_items: int = Field(default=50, ge=1, le=500)

class WorkspaceDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    trust_level: str
    has_token: bool
    revision: int
    updated_at: datetime
```

### 统一脱敏异常映射
- 在应用根注册全局异常处理器，把领域异常映射为稳定错误信封（`code` / `message` / `request_id`）；
- 未捕获异常返回通用 `INTERNAL_ERROR`，详细 traceback 仅打入后端结构化日志（且经脱敏处理器过滤 `authorization`、`token`、`password` 字段）。

---

## 3. `asyncio` 并发与防阻塞铁律

Python 异步服务最常见的线上雪崩，是在 `async def` 里误调阻塞 I/O 或同步重计算，瞬间卡死整个事件循环。

| 场景 | ❌ 危险写法（阻塞全局事件循环） | ✅ 正确做法 |
| --- | --- | --- |
| HTTP 请求 | 在 `async def` 里用 `requests.get()` | 复用应用级 `httpx.AsyncClient(timeout=...)` |
| 文件/加密/压缩 | 直接调用阻塞库解压大 ZIP 或同步读大文件 | 用 `await asyncio.to_thread(...)` 下放线程池并限制并发 |
| 并发发多个独立请求 | 串行 `await a(); await b()` | `asyncio.gather(...)` 或 Python 3.11+ `async with asyncio.TaskGroup()` |
| 后台任务 | `asyncio.create_task(job())` 不保留引用 | 保存任务集合并绑定 `done_callback` 记录异常，停机时优雅取消 |
| 超时控制 | 无超时 `await client.get(url)` | 必配 `asyncio.timeout(10)`（3.11+）或客户端级 `Timeout` |
| 限流保护 | 对外部接口无上限 `gather(*1000_tasks)` | 用 `asyncio.Semaphore(N)` 限制最大并发度 |

> **FastAPI 常见误区**：`def` 同步路由会被框架自动扔进有限线程池，而 `async def` 路由直接在主事件循环执行——**只要路由标了 `async def`，内部就绝不能调用同步 DB 驱动（如 `psycopg2` / 同步 `pymysql`）或 `time.sleep()`**。

---

## 4. SQLAlchemy 2.x 与 Alembic 持久化纪律

### Session 生命周期与并发红线
- **一请求一 Session，禁止跨协程共享 `AsyncSession`**：在 `asyncio.gather` 中让两个协程共用同一个 `AsyncSession` 会直接触发协议错乱与连接损坏。
- **关闭隐式延迟加载陷阱**：异步环境下给 `async_sessionmaker` 设 `expire_on_commit=False`，关系字段显式使用 `selectinload` / `joinedload` 预加载，避免触发 `MissingGreenlet` 或隐蔽 N+1 查询。
- **事务边界在 Service / Use Case 层**：不要在每个小 Repository 方法里各自 `commit()`（会破坏多步操作的原子性）；在业务用例边界统一 `async with session.begin():` 提交或回滚，**事务块内严禁发 HTTP / RPC 调用**。
- **连接池与断线恢复**：配置 `pool_pre_ping=True`、`pool_recycle` 与明确 `pool_size` / `max_overflow`，防数据库重启或空闲断连引发大面积 500。

### Alembic 迁移规范
- `alembic revision --autogenerate` 生成的脚本**必须人工逐行复核**（autogenerate 容易把重命名列识别成“删列再加列”，直接清空线上数据！）。
- 已合入主干并部署过的迁移版本禁止原地改写；滚发兼容变更遵循扩张-收缩，可逆变更补齐真实可用的 `downgrade()`。
- **严禁裸拼接 SQL**：动态参数一律使用绑定参数（`text("... WHERE id = :id").bindparams(id=...)`），动态表名/排序列走显式白名单字典映射。

---

## 5. 路径安全、归档安全、原子写盘与子进程

### 路径防逃逸（Python 3.9+）
```python
from pathlib import Path

def resolve_contained_path(base_dir: Path, untrusted_rel: str) -> Path:
    if not untrusted_rel or "\x00" in untrusted_rel:
        raise ValueError("路径非法")
    base_real = base_dir.resolve(strict=True)
    candidate = (base_real / untrusted_rel).resolve(strict=False)
    if not candidate.is_relative_to(base_real):
        raise PermissionError(f"路径越出允许目录: {untrusted_rel}")
    return candidate
```

### 归档防 Zip Slip 与 Zip Bomb
- **禁止直接调用 `zipfile.ZipFile.extractall(dest)` 处理不可信压缩包**（旧行为及符号链接/超大解压体积均存在风险）。
- 必须逐条遍历 `zf.infolist()`：校验文件名非绝对路径、不含 `..`、拒绝符号链接（`(info.external_attr >> 16) & 0o170000 == 0o120000`）、校验文件数上限，并**按块流式读取同时累计真实解压字节数**（不轻信 header 里可伪造的 `file_size`），超限立即中断并清理暂存目录。

### 同目录原子写盘
```python
import os
import tempfile
from pathlib import Path

def atomic_write_text(target: Path, content: str, encoding: str = "utf-8") -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, target)  # POSIX 与 Windows 均原子覆盖
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
```

### 子进程与外部命令安全
- 始终传参列表 + `shell=False`（绝不把用户输入拼进 `shell=True` 字符串）；
- 必设 `timeout`，需要杀死可能派生子孙进程树的长命令时使用 `start_new_session=True` 并在超时/退出分支用 `os.killpg(proc.pid, signal.SIGTERM)` → `SIGKILL` 彻底回收；
- 所有外部客户端（`httpx.AsyncClient`、DB Engine、线程池）通过应用 `lifespan` 上下文管理器成对初始化与关闭，避免连接与句柄泄漏。
