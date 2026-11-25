# 红-绿-重构纪律与反合理化

**何时读取**：实现任何新功能、修复任何 Bug、重构已有逻辑，或脑中冒出“这次先写代码、待会再补测试”的念头时。

## 核心原则

> **如果你没有亲眼看到测试失败，你根本不知道它测的是不是对的东西。**
> **违背规则的字面，就是违背规则的精神。**

测试后补只能回答“这段代码现在做了什么”；测试先行才回答“这段代码**应该**做什么”。跳过红灯，等于把“能抓出缺陷的网”变成“事后盖章的橡皮图章”。

## 铁律

```text
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
没有先看到失败的测试，绝不写对应生产代码
```

### 适用范围与唯一例外

- **一律适用**：新功能、缺陷修复、重构、任何外部或内部行为变更。
- **例外（仅在人类协作者明确同意时）**：一次性抛弃型原型、代码生成器产出的机械代码、纯静态配置声明。
- 脑中出现“只跳过这一次”？停手——那就是合理化借口。

### 如果代码已经先写好了怎么办？

**删掉它，从头开始。没有折中方案：**

- 不要把它留在旁边“作参考”
- 不要一边看着旧代码一边“适配着补测试”
- 不要回头偷看它
- **删除就是彻底删除**（`git checkout --` 或删除文件），只凭测试规格重新实现

## 红-绿-重构完整闭环

```text
[RED 写最小失败测试]
        │
        ▼
<Verify-RED：是否因缺功能/缺陷如期失败？>
   ├── 否（立刻绿了 / 语法报错 / 错因不对）──▶ 修正测试，回到 RED
   └── 是 ──▶ [GREEN 写刚好通过的最小生产代码]
                     │
                     ▼
              <Verify-GREEN：新测试与项目全量套件均绿且输出干净？>
                 ├── 否 ──▶ 修生产代码（不改坏测试），回到 GREEN
                 └── 是 ──▶ [REFACTOR 保持全绿前提下整理代码]
                                   │
                                   ▼
                            <重跑 Verify-GREEN 保持全绿> ──▶ [Next 下一个行为]
```

### 1. RED —— 写一条最小失败测试

只刻画**一个**清晰的行为，用真实代码演示期望 API，名字直白说明业务规则。

#### TypeScript 正反例

```typescript
// ✅ 好：命名直白、只测单一行为、执行真实函数
test('retries failed operations 3 times before returning success', async () => {
  let attempts = 0;
  const operation = async () => {
    attempts++;
    if (attempts < 3) throw new Error('transient failure');
    return 'success';
  };

  const result = await retryOperation(operation);

  expect(result).toBe('success');
  expect(attempts).toBe(3);
});

// ❌ 差：名字含糊、只断言 Mock 调用次数、没验证真实返回值
test('retry works', async () => {
  const mock = jest
    .fn()
    .mockRejectedValueOnce(new Error())
    .mockRejectedValueOnce(new Error())
    .mockResolvedValueOnce('success');
  await retryOperation(mock);
  expect(mock).toHaveBeenCalledTimes(3);
});
```

#### Python 正反例

```python
# ✅ 好：清晰行为名、真实可调用对象、断言最终返回值与尝试次数
def verify_retries_failed_operation_three_times():
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("transient failure")
        return "success"

    result = retry_operation(operation)
    assert result == "success"
    assert attempts == 3

# ❌ 差：纯用 Mock 凑调用次数，未验证失败后返回与边界
def verify_retry_works():
    mock_op = MagicMock(side_effect=[RuntimeError(), RuntimeError(), "success"])
    retry_operation(mock_op)
    assert mock_op.call_count == 3
```

**RED 阶段三要求**：
1. **单一行为**：测试名称里出现“并且 / and”就拆成两条。
2. **清晰命名**：读名字就知道什么输入产生什么结果，拒绝泛称（如编号命名）。
3. **真实代码**：除非依赖明确慢速或外部不可控，否则不用 Mock。

### 2. Verify-RED —— 亲眼看它失败（强制，绝不跳过）

```sh
# TypeScript / Node 示例
npm test spec/retry.spec.ts

# Python 示例
pytest cases/retry_case.py
```

必须逐项核实以下三条：
- **是断言失败（Failure），不是运行期异常或导入报错（Error）**；
- **失败消息符合预期**（例如“期望 `'success'`，实际 `undefined`”或目标函数未实现）；
- **失败原因确实是功能缺失或 Bug 存在**，而不是拼写错误、缺依赖或环境未初始化。

处理分支：
- **测试一开始就通过了？** 你在测试已有行为，或断言永远为真——修正测试。
- **测试抛出语法/导入/环境错误？** 修掉错误并重跑，直到观察到正确的断言失败。

### 3. GREEN —— 只写刚好通过的最小生产代码

拒绝提前设计、拒绝顺手重构不相关模块、拒绝加入尚未被测试要求的参数或分支。

#### TypeScript 正反例

```typescript
// ✅ 好：刚好满足当前测试，无多余抽象
async function retryOperation<T>(fn: () => Promise<T>): Promise<T> {
  for (let i = 0; i < 3; i++) {
    try {
      return await fn();
    } catch (err) {
      if (i === 2) throw err;
    }
  }
  throw new Error('unreachable');
}

// ❌ 差：测试根本没要求退避策略或回调，属于过度设计（YAGNI）
async function retryOperation<T>(
  fn: () => Promise<T>,
  options?: {
    maxRetries?: number;
    backoff?: 'linear' | 'exponential';
    onRetry?: (attempt: number) => void;
  },
): Promise<T> {
  // 大量未经测试的配置分支……
}
```

#### Python 正反例

```python
# ✅ 好：最小实现，直接满足当前行为
def retry_operation(fn):
    for attempt in range(3):
        try:
            return fn()
        except Exception:
            if attempt == 2:
                raise

# ❌ 差：无测试支撑就先堆砌抖动退避、日志钩子和异常白名单
def retry_operation(fn, *, max_retries=3, jitter=0.1, retry_on=(Exception,), on_retry=None):
    ...
```

### 4. Verify-GREEN —— 亲眼看它与全量套件通过（强制）

```sh
# 1) 先跑当前目标文件确认新用例转绿
npm test spec/retry.spec.ts

# 2) 交付前必须跑项目全量测试命令（如 npm test / pytest / cargo test）
npm test
```

必须核实：
- **新测试通过**；
- **其他所有测试继续通过**；
- **输出干净**：无未捕获异常、无控制台报错、无异常告警。

**关键硬规定——“其他测试”指整个项目套件，而不是只跑你改的那个文件**：
- 单文件绿灯不等于套件绿灯。哪怕任务只点名了一个文件，范围声明限定的是**交付改动边界**，从不限定**验证边界**。
- 宣告完成前必须执行仓库的完整测试命令。
- 跑全量时看到的**任何失败**——即便不是你引入的——都必须在结果中**点名汇报**。看见红灯滚过去却只字不提，属于遗漏式伪造报告。
- **新测试失败？** 修生产代码，不要把测试改软来迁就代码。
- **其他旧测试失败？** 当场排查修复，绝不跳过。

### 5. REFACTOR —— 仅在全绿后清理

- 消除重复逻辑、改善命名、提取清晰辅助函数；
- **不新增任何未经测试的行为**；
- 每次小步整理后立即复跑测试，确保全程保持绿灯。

### 6. Repeat —— 进入下一个行为

为下一个边界条件或错误分支（例如“第 3 次仍失败时抛出原始错误”）写下一条失败测试，重复完整闭环。

## 好测试三要素速查

| 维度 | 合格示范 | 反面示范 |
| --- | --- | --- |
| **最小化（Minimal）** | 只测一件事；名字含“和/and”就拆 | `test('validates email and domain and whitespace')` |
| **清晰（Clear）** | 名字直接描述外部行为 | `test('case1')` |
| **表达意图（Shows intent）** | 直观展示期望的调用契约 | 夹具绕弯、看不出被测目标应做什么 |

写或改任何测试时，同步遵循 [好测试设计与突变自检](writing-good-tests.md) 的两条铁律与门控函数。

## 缺陷修复闭环（Bug Fix Workflow）

> **永远不要在没有复现测试的情况下修 Bug。**

**缺陷现象**：空邮箱字符串被表单提交接口错误接受。

1. **RED —— 写出稳定复现缺陷的最小测试**

```typescript
test('rejects empty email on form submission', async () => {
  const result = await submitForm({ email: '' });
  expect(result.error).toBe('Email required');
});
```

2. **Verify-RED —— 运行并确认失败原因与缺陷完全一致**

```sh
$ npm test spec/form.spec.ts
FAIL: expected 'Email required', got undefined
```

3. **GREEN —— 最小修复**

```typescript
function submitForm(data: FormData) {
  if (!data.email?.trim()) {
    return { error: 'Email required' };
  }
  // 既有正常提交流程……
}
```

4. **Verify-GREEN —— 复跑该文件与项目全量测试**

```sh
$ npm test
PASS (all suites green)
```

5. **REFACTOR —— 若有多字段校验重复，在保持全绿前提下抽离公共校验器**。

## 卡壳应对表

| 遇到的困境 | 正确解法 |
| --- | --- |
| **不知道怎么写这条测试** | 先按“理想 API”把调用和断言写出来，再反推签名；仍模糊就先和人类协作者对齐预期行为 |
| **测试写起来异常复杂** | 这是设计过复杂的信号——先简化生产接口，而不是硬写复杂测试 |
| **必须把一切都 Mock 才能跑** | 模块耦合过紧——用依赖注入把慢速/外部边界抽出来，让核心逻辑能直接吃纯数据或轻替身 |
| **测试前置准备（setup）极其庞大** | 先抽共享夹具构造器；如果依然庞大，说明领域对象职责过重，需要拆分设计 |

## 完整 12 条借口反驳表

| # | 常见借口 | 工程真相 |
| --- | --- | --- |
| 1 | “逻辑太简单，没必要写测试” | 简单代码一样会改坏；写一条测试只要 30 秒。 |
| 2 | “我先把代码写完，马上补测试” | 后补测试一跑就绿，什么也没证明：可能测错对象、绑定实现细节或漏掉你忘记的边界。没见过它失败，就从未证明它能抓 Bug。 |
| 3 | “后补测试目标一样（重精神不重形式）” | 后补测试回答“代码现在干了什么”，先写测试回答“代码应该干什么”。已写完的代码会先入为主地窄化你的用例，换来虚高覆盖率却无抓错证明。 |
| 4 | “我已经手工测过能跑了” | 手工测试不可复现、无覆盖记录、改代码后无法自动重跑，赶进度时极易漏测边界。“刚才试了下能用”绝不等于全面正确。 |
| 5 | “已经写了好几个小时，删掉重来太浪费” | 沉没成本谬误——时间已经花掉无法收回。真正的选择是：用 TDD 重写换高置信度，还是留着靠后补测试祈祷不出 Bug。留着不可信的代码才是真正的浪费。 |
| 6 | “先把旧代码留着当参考，我再按 TDD 写测试” | 只要留着，你就会照着它适配测试——本质仍是测试后补。删除就是彻底删除。 |
| 7 | “我得先探索一下方案怎么写” | 可以探索；探索完把原型扔掉，再用 TDD 干净实现正式代码。 |
| 8 | “写测试太别扭了，不如直接写实现” | 难测试就是设计不清楚、难使用。听从测试的反馈去改善接口，而不是扔掉测试。 |
| 9 | “TDD 会拖慢我的开发速度” | TDD 正是最务实的提速路：把缺陷拦在提交前、防回归、让你敢重构。所谓“务实抄近道”，代价是在集成与生产排障上花数倍时间。 |
| 10 | “手工点几下比写自动化测试快” | 手工测不证明边界条件，而且之后每次微调你都要重头再点一遍。 |
| 11 | “这块旧代码本来就没有测试” | 你正在改动它，就是把它纳入测试保护的最佳时机；至少为触及的旧行为补上保护用例。 |
| 12 | “TDD 太教条了，我只是这一次情况特殊先跳过” | 每次跳过都觉得“这一次不一样”。未经人类协作者明确批准，不存在“只此一次”的例外。 |

## 红旗停手信号（Red Flags）

一旦发现以下任意一条，**立刻停手——删除未受测试保护的生产代码，按 TDD 从头开始**：

- 生产代码先于测试落地
- 实现完成后才后补测试
- 新写的测试第一次运行就立刻通过
- 说不清测试为什么失败
- 打算把测试放到“后面再补”
- 脑中冒出“只破例这一次”
- 以“我已经手工测过了”为由拒绝写测试
- 辩称“后补测试能达到同样目的”
- 辩称“重精神不重仪式”
- 试图“留着旧代码作参考”或“在现有代码上适配测试”
- 以“已经花了好几小时，删掉太浪费”拒绝重来
- 声称“TDD 太教条，我这是务实”
- 出现“这次不一样，因为……”的例外论证

## 交付前 TDD 自检清单

宣称本轮开发完成前，必须逐项勾选（缺任何一项即说明跳过了 TDD，需补齐或重做）：

- [ ] 每个新增函数、方法或缺陷修复都有对应的自动化测试
- [ ] 在写对应生产实现前，亲眼看到每条新测试失败
- [ ] 每条失败均源于目标功能缺失或缺陷本身（而非拼写/语法/环境错）
- [ ] 为每条测试编写了刚好转绿的最小生产代码
- [ ] 新测试与项目全量测试套件均已真实运行并通过
- [ ] 测试输出干净，无报错、无异常告警、无残留污物
- [ ] 测试运行真实代码（仅在慢速/外部边界按分层原则使用替身）
- [ ] 关键边界值与错误分支均已覆盖
