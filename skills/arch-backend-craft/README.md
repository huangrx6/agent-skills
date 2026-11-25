# arch-backend-craft · 架构设计、后端工程与代码评审

> 跨语言（Python / Java / Node.js 等）系统架构与模块边界设计、跨边界 DTO 契约与安全防线、版本化迁移与原子持久化、四阶段调用链溯源及双侧严谨代码评审协议。

| 适合 | 产物 | 依赖 |
| --- | --- | --- |
| 跨模块架构方案、Python/Java/Node 后端与主进程 API、数据库迁移、故障溯源与纵深防御、发起与接收代码评审 | ADR 架构决策 · 契约与迁移实现 · 根因溯源与纵深防御 · 分级评审报告 | 目标项目运行环境（Python / Java / Node.js / 数据库等） |

Agent 的核心铁律、任务分流表与交付门禁见 [SKILL.md](SKILL.md)，专项规范、完整代码示例与模板按其中的参考链接一层直读。

## 快速使用

- “跨模块重构这块状态管理，帮我梳理单源事实、依赖方向和无损迁移路径。”
- “实现这组 FastAPI / SQLAlchemy 接口，确保 Pydantic 校验、不阻塞 asyncio 事件循环和事务边界干净。”
- “排查一下 Spring Boot 服务里的 `@Transactional` 失效、连接池打满和 JPA N+1 问题。”
- “线上出现深层数据污染或路径越界 Bug，按四阶段调试与调用链逆向溯源定位源头并加上四层纵深防御。”
- “对这组后端提交做一次只读代码评审，按 Critical/Important/Minor 分级并给出合并结论。”

## 目录结构

- [SKILL.md](SKILL.md)：六大铁律、反模式速查、任务分流路由表、四阶段调试与三连败停手闸门、评审纪律、参考索引与新鲜验证门禁
- [references/architecture-and-boundaries.md](references/architecture-and-boundaries.md)：SSOT 单源事实、唯一公开入口、无环依赖 DAG、按职责拆分、五层作用域优先级与 ADR 权衡模板
- [references/contracts-and-security.md](references/contracts-and-security.md)：跨边界纯 JSON 白名单 DTO 与错误信封、入口强校验、路径 `realpath` 防逃逸、归档安全、凭据加密脱敏与沙箱诚实边界
- [references/persistence-and-migrations.md](references/persistence-and-migrations.md)：版本化 Schema 迁移、扩张-收缩零停机迁移、事务原子性守则、原子写盘与目录级 5 步原子替换+回滚、并发乐观锁与资源防泄漏
- [references/python-backend-craft.md](references/python-backend-craft.md)：FastAPI/Django 模块封装、Pydantic v2 校验、`asyncio` 防阻塞与并发、SQLAlchemy 2.x/Alembic 纪律、`pathlib`/`zipfile`/`subprocess` 安全
- [references/java-backend-craft.md](references/java-backend-craft.md)：Spring Boot 构造器注入与单例无状态、`@Transactional` 四大陷阱与 HikariCP、关 OSIV 与 JPA/MyBatis 防 N+1/注入、Flyway 不可变迁移、NIO 路径与 Zip 安全
- [references/systematic-debugging.md](references/systematic-debugging.md)：调试与新鲜验证双铁律、四阶段完整排查与边界插桩、单假设验证、三连败停手质疑架构与反合理化对照表
- [references/root-cause-tracing.md](references/root-cause-tracing.md)：五步调用链逆向溯源法、操作前栈追踪插桩、状态污染源二分定位与真实 5 层溯源案例
- [references/defense-in-depth.md](references/defense-in-depth.md)：入口校验 / 业务不变量 / 环境守卫 / 前置诊断四层纵深防御模板与逐层绕过验证协议
- [references/code-review-giving.md](references/code-review-giving.md)：只读评审纪律、规格是愿景原则、`Declined to judge`、六维度核查、严重度校准与完整报告模板
- [references/code-review-receiving.md](references/code-review-receiving.md)：六步响应流程、禁表演式赞同、先全澄清再动工、YAGNI 核验、理性反驳与优雅纠错示范
- `evals/triggers.json` 与 `evals/evals.json`：触发边界与行为评判样例

## 边界

- 覆盖 Python、Java、Node.js/TypeScript 等通用后端架构、持久化、安全与评审；前端 React 组件与 CSS 归 `frontend-engineering` / `ui-design-craft`，产品需求澄清归 `product-spec`，独立测试套件编写归 `tdd-testing`，Git 分支提交归 `git-dev-workflow`。
- 评审模式默认 100% 只读，不改动工作树、暂存区或分支指针。

## 验证

本 skill 无可执行脚本，结构与引用校验在仓库根目录运行：

```sh
python3 tools/skill-builder/scripts/validate_skill.py skills/arch-backend-craft
python3 tools/skill-builder/scripts/check_pointers.py --root . skills/arch-backend-craft
```
