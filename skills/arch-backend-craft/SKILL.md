---
name: arch-backend-craft
description: >-
  Use this skill for language-agnostic system architecture design, cross-module boundaries,
  backend APIs (Python, Java/Spring, Node/TS, Electron main process), JSON/DTO contracts,
  database schema migrations (SQLite/Alembic/Flyway), atomic persistence, path/archive/credential
  security, systematic debugging, root-cause tracing with defense-in-depth, and code reviews.
  中文：系统架构设计、模块边界与数据归属、Python/Java/Node 后端与主进程接口实现、数据库迁移与事务回滚、安全防线、四阶段故障排查与调用链溯源、纵深防御、代码评审。
  Do NOT use for: React UI component or CSS styling (→ frontend-engineering / ui-design-craft),
  product scope/AC discovery alone (→ product-spec), standalone test suites (→ tdd-testing),
  or local Git ops (→ git-dev-workflow).
  不适用于前端组件与样式、纯产品需求梳理、独立测试编写、本地 Git 操作。
compatibility: Requires target project runtime (Python, Java/JVM, Node.js, or database tools) when implementing or verifying backend changes.
---

# 架构设计、后端工程与代码评审规范

面向跨语言（Python / Java / Node.js 等）系统架构、后端服务与桌面主进程工程实现、版本化持久化与原子恢复、四阶段深层故障溯源以及双侧代码评审。

**总纲**：事实源唯一、边界清晰、契约纯净、失败可恢复、排查追源头、评审重事实、交付凭实测。

---

## 1. 架构与后端六大铁律

1. **单源事实（SSOT）**：核心业务状态只允许有唯一权威存储或运行时事实源；投影表、缓存、前端状态一律单向派生，严禁双写或双向同步制造脑裂。
2. **显式所有权与无环依赖**：按业务职责纵向拆分而非机械按技术层切碎；每个模块只暴露唯一公共入口（如 `index.ts` / `__init__.py` / Java `public` Facade + package-private 实现），禁止跨模块深插私有实现，优先显式静态注册，不为已删除旧模块保留僵尸兼容壳。
3. **单向作用域优先级**：多层配置（`全局 → 用户 → 工作区 → 项目 → 会话`）显式声明覆盖规则，严格区分「未设置（继承上层）」与「显式清空（阻断继承）」；**严禁从较窄作用域反推或回写较宽作用域**。
4. **纯净可序列化跨边界契约**：HTTP / RPC / IPC 载荷必须是白名单投影的纯 DTO / JSON；严禁透传 ORM 实体、运行时句柄、内部存储路径、可执行代码或明文凭据；外部输入必做结构、范围、上限与非法键校验。
5. **路径、归档、凭据与诚实安全边界**：外部路径一律规范化并解析真实路径（`realpath` / `Path.resolve().is_relative_to` / `Path.toRealPath().startsWith`）防 `..` 与符号链接逃逸；归档流式限字节防 Zip Slip 与压缩炸弹；凭据只在受信任服务端/主进程加密驻留且零明文入日志/URL；绝不把哈希校验或静态扫描夸大为 OS 级沙箱。
6. **版本化迁移与原子持久化**：Schema 演进走线性版本工具（Alembic / Flyway / Liquibase / SQLite `user_version`）并单事务保护存量，服务端滚动发布采用扩张-收缩；重要文件同目录临时写盘原子重命名，目录级升级走 5 步原子替换与回滚；并发写用乐观锁/版本号，网络/子进程配齐超时、限流与进程组回收。

### 高频工程反模式与标准修法速查

| 危险反模式 | 后果 | 必须采用的工程修法 |
| --- | --- | --- |
| 缓存与主库双写、前端拼装回写 | 并发竞态、重启脑裂 | 所有写入走单一权威事务，派生视图单向刷新 |
| 读取窄作用域配置顺手回写全局默认 | 跨项目污染、不可预测覆盖 | 纯函数单向合并，区分未设置继承与显式清空 |
| 直接返回 ORM 实体（JPA / SQLAlchemy / 原生行） | 泄漏密文/内部字段、触发延迟加载或 N+1 | 显式白名单 DTO / Pydantic Schema 投影 + 脱敏错误信封 |
| 仅用字符串判 `..` 检查路径 | 被前缀碰撞与符号链接绕过 | 规范化真实路径再做目录归属判定 |
| 事务内发 HTTP/RPC 或篡改已发布迁移脚本 | 拖爆数据库连接池、生产校验失败无法回滚 | 事务只包纯 DB 操作；迁移只追加新版本，滚发走扩张-收缩 |
| 直接覆盖核心配置文件或忽略子进程超时 | 崩溃留下 0 字节损坏文件或僵尸进程 | 同目录 `.tmp` + 落盘刷盘 + 原子重命名；超时必回收进程组 |

---

## 2. 按任务分流路由表

动工前先判定当前任务类型与技术栈，**先读对应专项手册再执行**：

| 任务类型 | 核心产出与目标 | 必须遵守的硬性闸门 | 必读专项手册 |
| --- | --- | --- | --- |
| **架构设计** | ADR 方案对比、SSOT 归属、依赖图、模块职责与任务边界 | 先定唯一事实源与公开入口；列出 5 类隐含失效模式（Review Focus） | [系统架构与模块边界](references/architecture-and-boundaries.md) |
| **跨边界接口与安全** | HTTP / RPC / IPC 路由、入口校验、DTO 投影、路径/归档/凭据防线 | 白名单纯 DTO、真实路径防逃逸、脱敏错误信封 | [跨边界契约与安全防线](references/contracts-and-security.md) |
| **持久化与数据迁移** | 版本化 Schema 迁移、扩张-收缩、原子写盘/替换、乐观锁与资源清理 | 单版本单事务保护存量、失败完整回滚、超时与限流 | [持久化、迁移与失败恢复](references/persistence-and-migrations.md) |
| **Python 后端工程** | FastAPI / Django / Pydantic / SQLAlchemy / Alembic / `asyncio` 实现 | 禁阻塞事件循环、会话不跨协程、Pydantic 边界校验、`shell=False` | [Python 后端专项规范](references/python-backend-craft.md) |
| **Java 后端工程** | Spring Boot / JPA / MyBatis / Flyway / Bean Validation 实现 | 防 `@Transactional` 失效与事务内 I/O、关 OSIV 用 DTO、单例无状态 | [Java 后端专项规范](references/java-backend-craft.md) |
| **深层故障排查与加固** | 根因定位报告、最小复现用例、源头修复与四层纵深防御 | 未查明根因禁止提修复；三连败强制停手质疑架构；先红后绿新鲜验证 | [系统化调试](references/systematic-debugging.md) · [调用链逆向溯源](references/root-cause-tracing.md) · [四层纵深防御](references/defense-in-depth.md) |
| **执行 / 发起代码评审** | 只读审查报告（Strengths / 分级 Issues / Declined to judge / 结论） | 100% 只读；规格是愿景而非豁免牌；基于真实源码并附精确文件行号 | [发起与执行代码评审](references/code-review-giving.md) |
| **接收与响应评审意见** | 澄清清单、源码与 YAGNI 核验回复、逐项修复与回归证明 | 禁表演式赞同；任一项不清先全澄清再改；逐条修复逐条验证 | [接收与响应代码评审](references/code-review-receiving.md) |

---

## 3. 四阶段调试与三连败停手闸门

排查任何后端、主进程、持久化或集成故障时，严禁凭直觉盲改或在报错点加空值判断遮盖症状：

- **调试铁律**：`NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST`（未完成 Phase 1 根因调查，禁止提出或实施任何修复）。

```text
Phase 1 根因调查（读全报错 → 稳定复现 → 查近期变更 → 跨边界插桩 → 逆向溯源至源头）
   │ 已明确 WHAT 与 WHY
   ▼
Phase 2 模式分析（找同类正常样例 → 逐行读参考实现 → 列举全部差异 → 摸清隐式依赖）
   │ 已定位精确差异
   ▼
Phase 3 单假设最小验证（写下单一假设 → 一次只动一个变量验证 ──无效──▶ 立即回退重立假设）
   │ 假设被证据证实
   ▼
Phase 4 源头修复与纵深加固（先建失败复现用例 → 单一根因修复 → 四层纵深防御 → 新鲜全量验证）
   └── 若修复失败：尝试 < 3 次回 Phase 1；尝试 ≥ 3 次 ──▶【三连败停手闸门】停止补丁、质疑架构！
```

- **高危缺陷必加四层纵深防御**：修完最初源头后，按「入口校验 → 业务不变量 → 环境守卫 → 前置诊断」逐层加固并做逐层绕过验证，让同类故障结构性不可能复发。
- **三连败停手闸门**：连续 3 次修补仍失败，或每次修好一处就在别处引爆新耦合/新回归，**立即停手，严禁发起第 4 次补丁**——先向协作者重审事实源与底层架构。
- **立即停手的红旗念头**：“先快速修一下以后再查”“一次改三个可疑点试试”“跳过复现用例先手动看”“参考太长扫一眼照着改”。

---

## 4. 代码评审双侧纪律与严重度校准

### 发起与执行评审（Giving）
- **独立上下文与 100% 只读**：只提供精炼实现摘要、规格与 `BASE_SHA..HEAD_SHA`，不倾倒完整会话历史；严禁改动工作树、暂存区或 `HEAD`，不派生嵌套子评审员。
- **规格是愿景文档**：规格未明写但违背理性用户合理预期的行为同样是缺陷，按实际用户伤害定级。
- **透明搁置**：结论前单列 `Declined to judge` 说明暂不评判的越界项与理由（无则显式写「无」），禁止静默忽略。

### 接收与响应评审（Receiving）
- **零表演式赞同**：严禁“你说得完全对！”“非常棒的建议！”或空洞致谢；直接复述技术点、澄清疑问、基于事实反驳或改完展示结果。
- **先全澄清再动工**：多条意见中只要有任意一条模糊，先全部问清再改第一行代码。
- **差异化核验与 YAGNI**：外部评审意见必过五问核验（技术正确、无回归、历史动因、全平台兼容、上下文完整）；对建议扩充未用功能的意见先全库 grep 调用方，无调用方提议按 YAGNI 移除。
- **单步落地与优雅纠错**：按「阻塞 → 简单 → 复杂」顺序逐项修改并单步验证；若反驳后发现自己判断有误，简短陈述事实并立即修正，不写长篇道歉。

| 严重度 / 类别 | 判定标准 | 评审侧要求 | 接收侧处理顺序 |
| --- | --- | --- | --- |
| **Critical** | 数据丢失、安全漏洞、契约破坏、并发竞态、功能阻断 | 必附 `文件:行号` 与修法，阻断合并 | 最高优阻塞项，核验属实后立刻首位修复 |
| **Important** | 架构漂移、错误处理缺口、合理预期缺失、关键边界未测 | 明确影响与建议，修复后推进 | 次优处理，若涉历史兼容或 YAGNI 用事实讨论 |
| **Minor** | 命名、魔法数字、局部可读性、文档润色 | 不得升级为 Critical | 简单修正随手落地，不夹带大重构 |
| **Declined to judge** | 超出本次变更/规格范围但值得记录的疑点 | 逐条写清搁置理由，交决策者拍板 | 确认是否另开任务跟进，不静默遗忘 |

---

## 5. 专项参考索引（按需一层直读）

- [系统架构与模块边界](references/architecture-and-boundaries.md)：SSOT 单源事实、唯一公开入口、无环依赖 DAG、按职责拆分原则、五层作用域优先级实现、ADR 方案权衡与 Review Focus 完整模板。
- [跨边界契约与安全防线](references/contracts-and-security.md)：纯 JSON 白名单 DTO 与错误信封、入口强校验与原型污染防护、`realpath` 路径防逃逸、归档防 Zip Slip 与压缩炸弹、凭据加密与日志/URL 脱敏、受信任代码与 OS 沙箱边界。
- [持久化、迁移与失败恢复](references/persistence-and-migrations.md)：版本化 Schema 迁移与重建表、扩张-收缩零停机迁移、事务原子性守则、单文件原子写盘、目录级 5 步原子替换+回滚、乐观修订号与流式字节限流/进程组回收。
- [Python 后端专项规范](references/python-backend-craft.md)：FastAPI/Django 分层与边界 Pydantic v2 强校验、SQLAlchemy `Session`/`AsyncSession` 生命周期与 N+1 防护、Alembic 迁移纪律、`asyncio` 禁阻塞事件循环与超时并发、`pathlib`/`zipfile`/`subprocess` 安全及资源清理。
- [Java 后端专项规范](references/java-backend-craft.md)：Spring Boot 模块封装与无状态单例 Bean、`@Transactional` 四大失效与连接池陷阱、JPA/MyBatis 关 OSIV 与 DTO/N+1 治理、Flyway/Liquibase 不可变迁移、Bean Validation + `@RestControllerAdvice` 错误信封、`Path.toRealPath()` 与 Zip Slip/Bomb 安全。
- [系统化故障排查与四阶段调试](references/systematic-debugging.md)：调试与新鲜验证双铁律、四阶段完整动作与跨组件诊断插桩、单假设验证、三连败停手质疑架构协议、完整红旗清单与反合理化借口对照表。
- [调用链逆向溯源](references/root-cause-tracing.md)：何时溯源决策图、五步逆向调用链溯源法、操作前栈追踪插桩与污染源二分脚本、真实 5 层溯源案例完整剖析、源头停止判据。
- [四层纵深防御](references/defense-in-depth.md)：入口校验 / 业务不变量 / 环境守卫 / 前置诊断四层完整模板、防前缀碰撞路径守卫、逐层绕过验证协议与实战复盘。
- [发起与执行代码评审](references/code-review-giving.md)：评审触发时机与精准上下文派发、规格是愿景原则、`Declined to judge`、只读纪律、六维度核查清单、严重度校准规则、完整评审报告模板与真实示范。
- [接收与响应代码评审](references/code-review-receiving.md)：六步响应流程、禁表演式赞同清单、不清项先全澄清原则、协作者 vs 外部评审差异化核验、YAGNI grep 核验、落地顺序、理性反驳与优雅纠错示范、GitHub 行内线程回复规范。
- [使用与维护说明](README.md)：目录总览、典型调用场景、能力边界与仓库校验命令。

---

## 6. 交付前新鲜验证门禁（Verification Gate）

`NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE`——未在最终代码状态下全新执行验证命令并亲眼读完输出前，禁止使用“应该好了 / 看起来通过 / 已修复”等任何隐含成功的表述。

| 宣称结论 | 必须具备的新鲜证据 | 不构成证据的偷懒写法 |
| --- | --- | --- |
| 验证全部通过 | 完整验证命令最新输出：退出码 0、0 失败 | 上一轮旧结果、“改得很小应该能过” |
| 缺陷已修复 | 原症状复现用例红→绿通过，且无回归 | 只改了代码未跑复现、仅代码走查 |
| 构建无误 | 实际构建/类型检查命令退出码 0 | 仅 Linter 通过或日志看着正常 |
| 持久化/迁移安全 | 存量升级、事务失败回滚与原子替换实测通过 | 仅空库建表成功 |

- [ ] 架构边界、公开入口、跨边界纯 JSON、路径/归档/凭据安全校验均已核实。
- [ ] Schema 迁移版本化且单事务原子，原子写盘/回滚与资源释放（含清理临时探针）均已完成。
- [ ] 已在最终代码状态运行受影响与全量验证、构建及 `git diff --check`，亲眼确认退出码 0。
