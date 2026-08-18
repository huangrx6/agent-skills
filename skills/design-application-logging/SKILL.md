---
name: design-application-logging
description: "设计、审查或完善生产级应用日志规范，包括日志事件选择、日志级别、单点记录边界、结构化字段、时间戳与编码格式、JSON Lines、双流输出、上下文注入、stdout/stderr 与文件输出、trace/correlation 关联、异常日志、安全脱敏、日志注入防护、日志滚动切分、定期压缩归档、保留与自动清理、磁盘水位保护、审计日志分离、采样限频、动态调级、日志测试和成本控制。用于编写日志规范、评审日志实现、设计日志字段与存储策略、治理重复日志与敏感数据，为容器 / Kubernetes / Serverless 及各类后端语言环境提供落地要求。业务错误码定义、统一 API 错误响应、异常传播与重试策略参考独立规范。"
---

# 应用日志设计

## 目标

产出简洁、可执行、可治理的应用日志规范或实现方案，使日志能够支持诊断、关联、监控和审计，同时避免重复、泄密、注入、格式漂移、文件无限增长、磁盘耗尽和成本失控。

## 职责边界

本技能负责：

- 应记录与不应记录的事件；
- DEBUG、INFO、WARN、ERROR 的使用；
- 单点记录责任边界；
- 结构化字段、字段类型与命名；
- 时间戳、编码、单行格式和消息长度；
- stdout/stderr、文件、Syslog、OTLP 等输出方式；
- trace、span 和 correlation 关联；
- 异常日志字段；
- 敏感数据与日志注入防护；
- 文件滚动、定期切分、压缩归档、保留与清理；
- 磁盘容量保护和日志平台故障降级；
- 审计日志分离；
- 采样、限频和成本治理；
- 日志测试、评审和验收。

本技能不负责错误码、API 错误响应、异常传播、超时或重试策略。需要这些内容时，参考独立规范。

衔接说明：日志中的 `error.code` 应复用 错误码注册表的值（同一稳定错误码贯穿错误响应与日志）；`error.type` 表达运行期错误分类（validation/dependency/timeout 等），可与错误码注册表的 category 对应但不必强制同构。

## 工作流

1. 识别日志用途：诊断、业务运营、安全审计、合规证据或告警输入。
2. 识别运行环境：进程、虚拟机、容器、Kubernetes、Serverless 或托管平台。
3. 识别输出链路：标准输出、文件、Syslog、Agent、Collector、OTLP 或集中日志平台。
4. 先定义事件目录和责任边界，再决定级别、格式与字段。
5. 明确日志文件生命周期的唯一责任方、滚动条件、压缩、保留、清理和磁盘保护。
6. 区分诊断日志、审计日志、指标和链路，避免用日志替代所有可观测性信号。
7. 只读取当前任务需要的参考文件。
8. 使用验收规则检查重复、敏感数据、格式一致性、容量上限、清理行为和可关联性。

## 核心规则

- 只记录具有诊断、运营、安全或审计价值的事件。
- 同一失败通常只在承担最终结果责任的边界记录一次。
- 日志级别必须反映运行影响，而不是代码是否进入 `catch`。
- 优先使用结构化日志；默认推荐 UTF-8 编码的 JSON Lines，一条事件对应一行。
- 允许"人读流 + 机器读流"并存：控制台文本供人排查，结构化流（JSON/OTLP）是唯一机器契约，两流字段语义必须一致，不得把同一事件复制到同一形态的多个流。
- 时间戳必须包含时区；跨系统集中采集时应统一使用 UTC 和稳定的 RFC 3339 表示。
- 字段名称、类型、单位和含义必须稳定，不得在不同服务中任意漂移。事件目录引用的每个字段必须在格式目录或事件字段目录有登记。
- 关键上下文必须放入结构化字段，不得只拼接进自然语言消息。
- 入口统一注入 trace/request 与业务上下文，请求结束清理；异步执行必须显式传播，不得依赖线程上下文残留。
- 容器环境通常写入 stdout/stderr，由运行时或平台负责采集与轮转；不得同时由应用和平台重复轮转同一日志流。
- 文件日志必须设置时间或大小滚动条件，并设置文件数、保留天数或总容量上限。
- 归档文件只在关闭后压缩；不得压缩、删除或改写当前活动日志文件。
- 清理策略必须确定、幂等并以最旧的合格归档优先；审计或法律保留数据不得被普通清理策略删除。
- 日志磁盘使用必须设置告警水位和硬上限；不得无限缓冲直至耗尽磁盘或内存。
- 未知异常的内部日志应保留异常类型、消息、调用栈和因果链（用标准异常字段名）；预期业务失败通常不记录完整堆栈。
- 禁止记录密码、令牌、Cookie、私钥、完整支付数据和不必要的个人信息。
- 用户可控文本写入日志前必须限制长度并处理换行与控制字符。
- 诊断日志与审计日志必须分离管理；审计通道降级必须可观测并告警，不得静默丢失。
- 高频成功路径优先使用指标、聚合、采样或限频，不逐条输出 INFO。
- 生产动态调级必须有回退机制、有效期和审计记录，防止误开 DEBUG 导致容量爆掉。
- 日志平台故障原则上不得导致核心业务失败；必须定义有界缓冲、丢弃优先级与告警。
- 日志格式、脱敏、轮转、压缩、保留、清理和磁盘保护必须通过测试或配置校验验证。

## 参考文件选择

- 处理事件选择、责任边界、日志级别、FATAL 声明、severity 映射和异常日志字段时，读取 [references/logging-model.md](references/logging-model.md)。
- 处理 JSON Lines、双流输出、时间戳、编码、字段类型、stdout/stderr、文件、Syslog/OTLP 和 Serverless 输出时，读取 [references/format-output.md](references/format-output.md)。
- 处理结构化字段、命名、上下文注入、链路关联和事件目录时，读取 [references/structured-fields.md](references/structured-fields.md)。
- 处理文件滚动、定期切分、压缩归档、保留、清理和磁盘保护时，读取 [references/rotation-retention.md](references/rotation-retention.md)。
- 处理敏感数据、脱敏、日志注入、删除权与个人信息和请求内容记录时，读取 [references/sensitive-data.md](references/sensitive-data.md)。
- 处理审计日志、审计降级、采样、限频、动态调级、日志量预算、成本和平台故障时，读取 [references/governance.md](references/governance.md)。
- 处理代码评审、日志测试和发布验收时，读取 [references/testing-review.md](references/testing-review.md)。
- 落地实现（从零开始、入口上下文注入、统一业务事件记录、统一错误出口、双流实现、异步背压、动态调级）时，读取 [references/implementation-patterns.md](references/implementation-patterns.md)。
- 需要完整产出样例时：读取 [examples/README.md](examples/README.md) 下的虚构项目示范。

## 输出结构

完整规范优先采用：

1. 日志目标与适用范围；
2. 事件选择、责任边界与日志级别；
3. 日志格式、字段与输出方式；
4. 链路关联与异常日志；
5. 文件滚动、压缩、保留、清理和磁盘保护；
6. 敏感数据与安全；
7. 审计、采样、限频和成本治理；
8. 测试与验收。

使用"必须、应、可"表达约束强度。不要把日志消息文本当作稳定机器契约；统计、检索和告警应依赖稳定字段、事件名或指标。

### 交付物清单（Definition of Done）

规范交付应包含五件套，缺一不算完成：

1. 事件目录（`assets/log-event-catalog.csv` 对应物）：至少 8-10 个关键事件，字段引用全部有登记；
2. 字段目录（格式目录 + 事件字段目录）：公共字段与事件专属字段命名、类型、索引、分类齐全；
3. 存储策略：输出、轮转、压缩、保留、清理与磁盘保护；
4. 敏感字段策略：禁止记录项、处理动作与验证方式；
5. 测试计划或自动化校验：至少覆盖 JSON 可解析、必填字段、敏感字段不出现、滚动清理行为。

交付前运行资产校验脚本并通过。

## 内置资源

- [assets/log-event-catalog.csv](assets/log-event-catalog.csv)：日志事件目录模板（含启动/请求失败/重试耗尽/降级/认证/致命错误/审计降级/权限变更事件）。
- [assets/log-format-schema.csv](assets/log-format-schema.csv)：公共日志字段与格式模板（含 severity_number、schema.version、correlation_id）。
- [assets/log-event-fields.csv](assets/log-event-fields.csv)：事件专属字段登记模板（事件目录 requiredFields 引用的非公共字段在此登记）。
- [assets/log-storage-policy.csv](assets/log-storage-policy.csv)：输出、轮转、压缩、保留和清理策略模板。
- [assets/sensitive-field-policy.csv](assets/sensitive-field-policy.csv)：敏感字段处理策略模板。
- `scripts/validate_logging_catalog.py`：校验上述目录的格式、枚举、跨表引用一致性和基本语义。
- `scripts/tests/test_validate_logging_catalog.py`：校验脚本的单元测试。

修改目录后运行：

```bash
uv run scripts/validate_logging_catalog.py \
  assets/log-event-catalog.csv \
  --format-schema assets/log-format-schema.csv \
  --event-fields assets/log-event-fields.csv \
  --storage-policy assets/log-storage-policy.csv \
  --sensitive-policy assets/sensitive-field-policy.csv
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
uv run scripts/validate_logging_catalog.py assets/log-event-catalog.csv --format-schema assets/log-format-schema.csv --event-fields assets/log-event-fields.csv --storage-policy assets/log-storage-policy.csv --sensitive-policy assets/sensitive-field-policy.csv
uv run python -m unittest discover -s scripts/tests   # 跑测试
```

