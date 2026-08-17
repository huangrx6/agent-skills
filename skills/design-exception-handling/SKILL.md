---
name: design-exception-handling
description: "设计、审查或完善生产级异常处理方案，包括失败分类、异常传播与包装边界、错误码体系、统一 API 错误响应、全局异常处理器、超时、重试、取消、幂等、异步失败处理和失败路径测试。用于编写工程规范、评审后端错误处理设计、制定 HTTP API 错误契约，或为各类后端语言环境提供落地要求。不覆盖日志级别、结构化日志字段、审计日志与日志脱敏规范。"
---

# 异常处理设计

## 目标

产出简洁、可执行、可测试的异常处理规范或实现方案，确保失败语义准确、边界清晰、错误契约稳定、恢复行为有上限，并且不会泄露内部信息。

## 职责边界

本技能负责：

- 失败分类与异常模型；
- 捕获、包装、转换和传播；
- 错误码及统一错误响应；
- 全局异常处理器；
- 超时、重试、取消、幂等和降级；
- 任务、消息和批处理失败；
- 失败路径测试与验收。

本技能不负责制定完整日志规范。需要设计日志级别、结构化字段、敏感数据控制、审计日志或日志成本治理时，参考独立规范。

注：HTTP 幂等键的契约设计（Header、作用域）属 API 契约层；重试时的幂等消费与失败处理属本技能。

## 工作流

1. 识别交付物：团队规范、API 契约、全局处理器、框架实现、代码评审或测试清单。
2. 识别执行边界：HTTP/RPC、后台任务、消息消费者、批处理或命令行。
3. 先分类失败，再决定状态码、错误码、重试和告警行为。
4. 明确领域层、应用层、基础设施层与入口边界的职责。
5. 只读取当前任务所需的参考文件。
6. 使用验收规则检查错误契约、安全性、重试上限和失败路径测试。
7. 交付前运行资产校验脚本，确保错误码注册表与异常映射表一致。

## 核心规则

- 禁止吞掉异常或使用空 `catch/except`。
- 仅在能够恢复、补偿、转换、补充有效上下文、释放资源或承担最终处理责任时捕获异常。
- 包装异常必须保留原始 `cause`、调用栈和因果链。
- 不得把程序缺陷或依赖故障伪装成用户输入错误。
- 不得通过解析异常消息文本判断异常类型。
- 预期失败必须使用稳定的机器错误码。
- 废弃错误码必须保留且不得重新分配，语义变更必须发布新错误码。
- 错误响应必须携带 `traceId`/`correlationId` 以便与日志和链路关联。
- HTTP 状态码表达协议语义，业务错误码表达具体失败原因；不得使用 HTTP 200 包装失败。
- 未知异常对外统一返回安全的内部错误，对内保留完整诊断信息。
- 所有外部调用必须设置超时或截止时间。
- 只重试临时性失败，并确保操作幂等或具备幂等保护。
- 重试必须限制次数和总耗时，并采用有上限的指数退避和随机抖动。
- 上游取消信号和剩余截止时间必须向下游传播。
- 非幂等写操作在无法确认结果时不得直接重复提交。
- 失败路径必须覆盖映射、超时、重试耗尽、取消、回滚、清理和脱敏测试。

## 参考文件选择

- 处理失败分类、捕获、包装、分层职责和全局异常处理时，读取 [references/failure-model.md](references/failure-model.md)。
- 处理错误码、HTTP 状态码、RFC 9457 响应和兼容性时，读取 [references/api-error-contract.md](references/api-error-contract.md)。
- 处理超时、重试、取消、幂等、熔断和降级时，读取 [references/resilience.md](references/resilience.md)。
- 处理定时任务、消息消费者和批处理失败时，读取 [references/async-failures.md](references/async-failures.md)。
- 处理代码评审、失败路径测试和发布验收时，读取 [references/testing-review.md](references/testing-review.md)。
- 需要完整产出样例时：读取 [examples/README.md](examples/README.md) 下的虚构项目示范。

## 输出结构

完整规范优先采用：

1. 核心原则与失败分类；
2. 异常边界与分层职责；
3. 错误码与统一响应；
4. 全局异常处理；
5. 超时、重试、取消与幂等；
6. 异步失败处理；
7. 测试与验收。

使用“必须、应、可”表达约束强度。不要把工程经验表述为适用于所有平台的官方规则；涉及协议要求时注明标准来源。

### 交付物清单（Definition of Done）

规范交付应包含四件套，缺一不算完成：

1. 错误码注册表（`assets/error-code-registry.csv` 对应物）：错误码、状态码、分类、可重试性、责任方、生命周期齐全；
2. 异常映射表（`assets/exception-mapping.csv` 对应物）：内部异常到对外契约的映射，与注册表一致；
3. 全局异常处理器设计：识别、映射、脱敏、traceId 透传、未知兜底的明确流程；
4. 失败路径测试清单：覆盖映射、超时、重试耗尽、取消、回滚、脱敏。

交付前运行资产校验脚本并通过。

## 内置资源

- [assets/error-code-registry.csv](assets/error-code-registry.csv)：错误码注册表模板（含分类、可重试性、生命周期）。
- [assets/exception-mapping.csv](assets/exception-mapping.csv)：内部异常到对外契约的映射模板。
- `scripts/validate_error_catalog.py`：校验两个目录的格式、枚举、跨表一致性和分类↔状态码语义。
- `scripts/tests/test_validate_error_catalog.py`：校验脚本的单元测试。

修改目录后运行：

```bash
uv run scripts/validate_error_catalog.py \
  assets/error-code-registry.csv \
  --mapping assets/exception-mapping.csv
```

运行校验脚本测试：

```bash
uv run python -m unittest discover -s scripts/tests -p 'test_*.py'
```

## 环境与运行

本 Skill 脚本统一通过 **uv** 运行（不使用宿主机的原始 Python，避免环境污染）。

- 所有脚本均为纯标准库，无需安装任何第三方包；uv 仅用于隔离 Python 解释器。
- uv 使用全局缓存（`~/.cache/uv`），**不会在每个 skill 目录创建 .venv**；Python 解释器与依赖在所有 skill 间共享，不重复下载。
- 固定路径约定：
  - uv 二进制：`~/.local/bin/uv`
  - 依赖与 Python 缓存：`~/.cache/uv`（全局共享）
  - Python 解释器：`~/.local/share/uv/python/`
  - 脚本：各 skill 的 `scripts/` 目录

首次使用前确保 uv 可用（不可用则自动安装，无需用户操作）：

```bash
python scripts/ensure_uv.py
# 或手动：curl -LsSf https://astral.sh/uv/install.sh | sh
```

统一运行方式：

```bash
uv run scripts/validate_error_catalog.py assets/error-code-registry.csv --mapping assets/exception-mapping.csv
uv run python -m unittest discover -s scripts/tests   # 跑测试
```

