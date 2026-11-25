# 好测试设计与突变自检

**何时读取**：编写或修改任何自动化测试、准备引入 Mock/Stub/Spy、或考虑给生产类新增清理/辅助方法时。

## 核心总览

自动化测试存在的唯一理由，是**拦截特定的生产故障**。一切判断收束到两条铁律：

```text
1. 每条测试必须说出它拦截什么生产故障（Name the Break）
2. 每条测试必须运行真实代码（Exercise the Real Thing）
```

严格执行红-绿-重构会自然带来这两条：先写测试并亲眼看它在真实代码上失败，就已经证明了它具备抓错能力；只有当真实依赖确实慢速或位于外部边界时，替身才配登场。

---

## 原则一：说出它拦截什么生产故障

写测试体之前，必须先回答清楚：**“生产代码发生什么改动会让这条测试挂掉？这个改动是 Bug，还是有意的设计决策？”**

有价值的测试拦截的是：错误的条件分支、缺失的副作用、传错的参数、边界条件遗漏或被破坏的对外契约。

### 1.1 独立推导预期值（严禁镜像断言）

预期值必须使用**手算字面量**或**人工核对过的静态夹具**；多分支逻辑优先采用**表驱动测试 + 字面量 `want`**。只要预期值由被测函数或其内部 helper 算出来，无论生产代码算错成什么样，等式两边永远相等。

#### TypeScript 正反例

```typescript
// ❌ 镜像断言：同一个构建器算两边，生产代码返回空串它也能通过
test('builds urgent tag query', () => {
  const expected = buildSearchQuery({ tag: 'urgent' });
  expect(buildSearchQuery({ tag: 'urgent' })).toBe(expected);
});

// ✅ 独立手写字面量预期（表驱动）
const cases = [
  { input: { tag: 'urgent' }, want: 'tag:"urgent"' },
  { input: { tag: 'ops', owner: 'lin' }, want: 'tag:"ops" owner:"lin"' },
  { input: { tag: '' }, want: '' },
];

for (const { input, want } of cases) {
  test(`formats query for ${JSON.stringify(input)}`, () => {
    expect(buildSearchQuery(input)).toBe(want);
  });
}
```

#### Python 正反例

```python
# ❌ 镜像断言：复用了生产代码同款归一化 helper 算预期
def verify_slug_generation():
    raw = "Hello, World!"
    assert to_slug(raw) == normalize_tokens(raw).replace(" ", "-")

# ✅ 独立手算字面量，直接锚定契约
@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("Hello, World!", "hello-world"),
        ("  multi   spaces  ", "multi-spaces"),
        ("---", ""),
    ],
)
def verify_slug_generation(raw: str, want: str):
    assert to_slug(raw) == want
```

### 1.2 拒绝改动探测（No Change Detectors）

如果只有“有意的设计调整”（例如调一个常量值、润色提示文案、改私有字段名）才会让测试失败，而真正的逻辑故障却能一路绿灯，这条测试就是**改动探测器**：重构必响、出 Bug 装睡。

**做法**：测试依赖该决策的**可观察行为**，而不是把内部常量或字面文案钉死。

```typescript
// ❌ 改动探测：只锁死了常量值，哪怕重试循环删光了它也全绿
test('max retries constant is 5', () => {
  expect(MAX_RETRIES).toBe(5);
});

// ✅ 测行为：确认失败调用确实尝试 5 次，且绝不发生第 6 次
test('stops retrying after 5 failed attempts and surfaces last error', async () => {
  let attempts = 0;
  await expect(
    runWithRetry(async () => {
      attempts++;
      throw new Error(`boom-${attempts}`);
    }),
  ).rejects.toThrow('boom-5');
  expect(attempts).toBe(5);
});
```

```python
# ❌ 改动探测：锁死私有字段名或精确中文措辞
def verify_error_message_wording():
    err = validate_port(-1)
    assert err == "端口号必须位于 1 到 65535 之间，请重新输入！"

# ✅ 测行为契约：断言错误类别/错误码与合法边界行为
def verify_port_bounds():
    assert validate_port(1).ok is True
    assert validate_port(65535).ok is True
    assert validate_port(0).code == "INVALID_PORT"
    assert validate_port(65536).code == "INVALID_PORT"
```

### 1.3 测行为，不测源码文本（Behavior, Not Text）

用正则或字符串查找去断言脚本、配置或文档“包含某一行”，只证明了“源码等于它自己”。

- **脚本与命令行工具**：用受控临时输入真实执行，断言 stdout/stderr、落盘副作用和退出码；
- **面向 Agent 的指令文档**：通过消费它的行为评测验证，不靠 grep 段落文字；
- **纯人类阅读的散文说明**：根本不该为其编写单元测试。

```python
# ❌ 测文本：把源码当字符串搜，改个变量名就挂、逻辑写坏反而不挂
def verify_backup_script_uses_atomic_rename():
    source = Path("scripts/backup_tool.py").read_text(encoding="utf-8")
    assert "os.replace(" in source

# ✅ 测行为：在临时目录真实运行脚本，验证产物内容与退出码
def verify_backup_script_creates_complete_snapshot(tmp_path):
    src = tmp_path / "data.db"
    src.write_text("v1", encoding="utf-8")
    out = tmp_path / "backup.db"
    proc = subprocess.run(
        [sys.executable, "scripts/backup_tool.py", str(src), str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert out.read_text(encoding="utf-8") == "v1"
```

### 1.4 测你的代码契约，不测框架机制（Your Code, Not the Framework）

只测试**你的代码在边界处作出的承诺**——你注册的路由映射、你构造的查询语句、你产出的响应载荷与状态码。上游框架自身的工作机理（例如“路由器收到请求后会调用已注册的 handler”）归框架维护者测试。

- **何时可破例**：当上游依赖的实际行为确实出乎意料并影响你的设计时，写**一条窄特征测试（characterization test）**，明确命名你在依赖的那个假设。
- **内部代码同理**：纯构造器、简单 getter、常量定义与直通转发方法，只有在它们承担**校验、归一化、默认值填充、派生计算、约束强制或副作用**时才值得测；否则直接断言依赖它们的第一个调用方可见结果。

### 原则一门控函数

```text
写测试体之前（BEFORE writing the test body）：
  说出哪一处生产代码改动会让本测试失败。

  说不出来               ──▶ 围绕外部可观察行为重新设计测试
  “源码某行文本改了”      ──▶ 改为真实执行产物并断言输出/副作用/退出码
  只有有意决策才会挂      ──▶ 这是改动探测器；改测依赖该决策的行为

  核对预期值是否在脱离被测代码的前提下独立算出：
  IF 预期值复用了被测逻辑或其内部 helper：
    立刻换成手写字面量或人工核对夹具
```

---

## 原则二：运行真实代码

### 2.1 严禁断言 Mock 本身（The Mock Earns No Assertions）

如果一条断言只在 Mock 存在时通过、撤掉 Mock 就失败，它测试的是你的测试脚手架，对生产代码零覆盖。

#### TypeScript 正反例

```typescript
// ❌ 测的是 Mock 的存在，侧边栏彻底坏了它依然通过
test('renders sidebar', () => {
  render(<AppShell />);
  expect(screen.getByTestId('sidebar-mock')).toBeInTheDocument();
});

// ✅ 测真实组件渲染出的可访问行为
test('renders primary navigation landmark', () => {
  render(<AppShell />);
  expect(screen.getByRole('navigation')).toBeInTheDocument();
});
```

#### Python 正反例

```python
# ❌ 把被测对象本身或核心协作者整个 Mock 掉，再断言它返回了预设值
def verify_invoice_total():
    calc = MagicMock()
    calc.total.return_value = 120
    assert calc.total([100, 20]) == 120

# ✅ 运行真实计费器，验证折扣与税费的真实计算结果
def verify_invoice_total():
    calc = InvoiceCalculator(tax_rate=0.1)
    assert calc.total([100, 20], discount=20) == 110
```

> 关键自问：**“我们现在测的是生产行为，还是 Mock 的行为？”**

### 2.2 在正确层级 Mock（Mock at the Right Level）

替换任何依赖前，先列清真实方法的**全部副作用**；只替掉真正慢速或外部不可控的底层边界，保留测试依赖的中间状态与副作用为真实实现。拿不准时，先跑一遍真实实现，观察实际发生了什么再决定隔离点。

#### TypeScript 正反例

```typescript
// ❌ Mock 层级过高：把 discoverAndCacheTools 整体替掉，
//    连带吞掉了“写入本地配置”的副作用，导致下游重复检测失效
vi.mock('./tool-catalog', () => ({
  discoverAndCacheTools: vi.fn().mockResolvedValue(undefined),
}));

// ✅ Mock 下沉到慢速外部边界：只替掉外部进程启动，本地发现与写配置保持真实
vi.mock('./mcp-server-manager', () => ({
  startServerProcess: vi.fn().mockResolvedValue({ tools: [{ name: 'search', schema: {} }] }),
}));
```

#### Python 正反例

```python
# ❌ 替掉了整个 Repository.save，连同唯一约束与序列化逻辑一起绕过
monkeypatch.setattr(repo, "save", lambda record: True)

# ✅ 使用临时目录中的真实 SQLite 数据库，仅替掉外部 webhook HTTP 发信客户端
class FakeWebhookClient:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    def post(self, url: str, payload: dict) -> int:
        self.sent.append((url, payload))
        return 202
```

### 2.3 让测试替身足够具体（Make Doubles Specific）

当传参、调用次数或调用顺序本身属于外部契约时，替身必须严格校验它们——来者不拒的万能 fake 什么都证明不了。成功、失败、畸形响应等每条分支应拥有各自独立的夹具或 spy，确保走错分支绝不可能侥幸满足断言。

### 2.4 完整镜像真实数据结构（Mirror Real Data Completely）

Mock 返回的响应对象必须包含真实协议的**全部文档化字段**，而不仅是当前测试挑出来读的那一两个字段。局部 Mock 会在下游代码读取缺失字段时静默失真：单测全绿、一集成就炸。

```typescript
// ❌ 局部 Mock：漏掉了真实响应里的 status / headers / meta，下游读 headers 时单测抓不到
const fakeRes = { data: { id: 'u1' } };

// ✅ 完整镜像真实协议结构
const fakeRes: ApiResponse<User> = {
  status: 200,
  headers: { 'x-request-id': 'req-42', 'content-type': 'application/json' },
  data: { id: 'u1', email: 'lin@example.com', role: 'member', active: true },
  meta: { latencyMs: 12 },
};
```

### 2.5 生产类只承载生产方法（No Test-Only Cleanup in Production）

只有测试才会调用的清理或重置方法（例如仅给测试清缓存用的 `destroy()` / `resetForTest()`）严禁塞进生产类。放到测试辅助工具里，或通过显式依赖注入管理生命周期。

做决定前问自己两个问题：
1. 这个方法是否只有测试代码调用？
2. 这个生产类在真实运行时是否本来就拥有该资源的生命周期？

只要第 1 题为“是”或第 2 题为“否”——立刻移出生产类，放进测试辅助模块。

```typescript
// ❌ 污染生产类：生产运行永不调用，只为测试清状态而生
class SessionRegistry {
  clearAllForTesting() {
    this.sessions.clear();
  }
}

// ✅ 生产类接收独立存储/实例，测试每次构造全新隔离实例或通过测试 helper 清理
function createIsolatedRegistry(tmpDir: string): SessionRegistry {
  return new SessionRegistry({ storagePath: path.join(tmpDir, 'sessions.sqlite') });
}
```

### 2.6 宁用真实组件，不用膨胀 Mock

当出现以下任一迹象时，立刻停手并改用真实组件的集成测试：
- Mock 配置代码长度超过测试断言逻辑本身；
- Mock 漏掉了真实组件已经新增或改动的方法；
- 每次微调协作者签名，测试就因 Mock 失真而成片破碎。

> 关键自问：**“这里真的非用 Mock 不可吗？”**

### 原则二门控函数

```text
引入任何 Mock 或测试辅助方法之前（BEFORE adding a mock or test helper）：
  1. 列出真实方法的全部副作用；
     保留本测试依赖的副作用为真实实现，只 Mock 它们下方的慢速/外部层级。
  2. 核对 Mock 响应是否完整镜像真实数据结构（含全部文档化字段）。
  3. 仅测试调用的清理/重置方法一律放在测试工具中，绝不放进生产类。
  4. 准备对 Mock 本身写断言？
     ──▶ 立刻取消 Mock 测真实组件，或删除这条断言。
```

---

## 测试随实现一起交付

红-绿-重构闭环本身就是“完成”的定义。只交付行为真正需要的测试：纯直通代码与人类散文不写无意义测试，因为每一条为应付流程而写的空洞测试，都会永久增加团队维护税。

## 突变自检清单（The Mutation Check）

收尾前，对刚改过的生产代码做一次**心智突变**：假设有人把生产代码按以下 5 类方式改坏，至少应有一条测试必然失败。

- [ ] **改错常量或参数**：如把重试上限 `3` 改成 `2`，把超时或页大小传错；
- [ ] **走错分支处理**：如反转 `if` 条件、调换两个 `case` 的处理函数；
- [ ] **删掉状态变更或副作用**：如删掉写库、发事件、更新标记位或释放锁；
- [ ] **返回空值或默认值**：如把函数体直接改成 `return null` / `return []` / `return 0`；
- [ ] **删掉边界校验**：如去掉对 `0`、空字符串、`null`/`None`、未授权或畸形输入的拦截。

如果某一种现实突变改完后整套测试依然全绿，说明该行为处于裸奔状态——或者对应测试是同义反复。

## 速查对照表

| 当你准备…… | 正确做法 |
| --- | --- |
| 写任何一条新测试 | 先说出它拦截哪个生产 Bug，而不是哪个设计决策 |
| 构造预期值 | 独立手算字面量或静态夹具；绝不用被测代码算预期 |
| 测试脚本或指令文档 | 真实运行看输出与副作用 / 压测消费行为；绝不 grep 源码文本 |
| 测试第三方依赖交互 | 只测自己的边界契约，不替框架测它的公开机制 |
| 对 Mock 元素写断言 | 取消 Mock 测真实组件，或直接删掉该断言 |
| Mock 某个方法 | 先列清它的全部副作用，把 Mock 下沉到慢速/外部层级 |
| 编写 Mock 返回值 | 完整镜像真实数据结构的所有文档化字段 |
| 添加仅测试用的清理逻辑 | 放入测试辅助工具，不污染生产类 |
| 发现 Mock 配置不断膨胀 | 改写为使用真实组件的集成测试 |
| 完成一个测试文件 | 逐项执行 5 类心智突变自检 |

## 11 条警报信号（Warning Signs）

评审自己或他人测试时，命中任何一条立即返工：

1. 前置准备（setup）与断言共享同一个对象引用，天然保证相等；
2. 这条测试只有在程序崩溃、抛异常或找不到选择器时才会失败；
3. 每次有意的正常重构都会挂掉，但逻辑改错时却从不报错；
4. 预期值藏在循环、复杂 builder 或复用生产逻辑的 helper 后面；
5. 测试在 grep 源码文本，或断言某个已删除的符号“保持不存在”；
6. 把业务代码全挖空、只留框架骨架时，这条测试依然能通过；
7. 测试纯粹为了拉高覆盖率而写，未检验任何外部结果或副作用；
8. 断言检查了 `*-mock` 测试 ID，或一移除 Mock 断言就失效；
9. 生产代码里存在只在测试文件中被调用的方法；
10. Mock 配置占了整个测试一半以上篇幅，或说不清为什么需要这个 Mock；
11. 理由是“为了保险起见先 Mock 一下”。
