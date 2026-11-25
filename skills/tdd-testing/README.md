# tdd-testing · TDD 与高质量自动化测试

> 严格红-绿-重构 TDD 纪律、真实行为测试设计与突变自检、条件轮询等待、严格隔离与污染定位、按改动分层测试模板、完成前验证门控，附带零依赖跨平台污染定位脚本。

| 适合 | 产物 | 依赖 |
| --- | --- | --- |
| 单元/集成测试编写、Bug 回归测试、测试质量审查、偶发 `sleep` 与污染排查、交付前门控 | 自动化测试 · 污染定位结论 · 全量验证证据报告 | Python 3.10+（仅 `scripts/find_polluter.py` 需要）；执行测试依赖目标项目测试器 |

Agent 的执行铁律、门控表与参考路由见 [SKILL.md](SKILL.md)，细则与正反代码例按需从对应参考手册加载。

## 快速使用

在目标仓库根目录运行测试污染定位脚本（先清理已有残留产物；`{file}` 为单文件占位符）：

```sh
python3 skills/tdd-testing/scripts/find_polluter.py \
  --artifact .unexpected-cache \
  --cmd "python3 -m unittest {file}" \
  --json \
  cases/case_a.py cases/case_b.py
```

典型对话请求：
- “按 TDD 红绿重构方式给这个解析与迁移模块补齐单元测试和边界用例。”
- “先写一条能复现这个 Bug 的失败回归测试，再最小修复并做全量回归验证。”
- “审查一下这组新增测试有没有镜像断言、改动探测、过度 Mock 或脆弱 `sleep`。”
- “测试套件一起跑时会在工作区留下脏目录，帮我定位污染源并彻底隔离。”

## 目录结构

- [SKILL.md](SKILL.md)：四条铁律、红-绿-重构门控表、好测试速查、工具入口、完成前验证红线与一层参考索引
- [references/tdd-cycle-and-discipline.md](references/tdd-cycle-and-discipline.md)：红-绿-重构五关细则、代码先写重来规则、缺陷修复闭环、卡壳应对、12 条借口反驳与红旗清单
- [references/writing-good-tests.md](references/writing-good-tests.md)：好测试双铁律与门控函数、TS/Python 正反例、Mock 分层策略、突变自检与 11 条警报信号
- [references/condition-based-waiting.md](references/condition-based-waiting.md)：通用 `waitFor`、领域等待助手完整 TypeScript 实现、常见错误与允许固定等待的三条件
- [references/isolation-and-polluters.md](references/isolation-and-polluters.md)：临时目录与环境变量隔离、逆序释放栈、零顺序依赖、`scripts/find_polluter.py` 实战与多文件组合污染二分排查法
- [references/verification-gate.md](references/verification-gate.md)：证据先于声明铁律、五步门控、宣称 vs 证明对照、伪完成借口反驳与严禁弱化/删用例/跳过规范
- [references/test-strategy-by-layer.md](references/test-strategy-by-layer.md)：按改动类型选测试层级（L1–L4）决策表及可复用 TypeScript/Python 测试模板
- `scripts/find_polluter.py`：跨平台测试污染顺序定位脚本（仅依赖 Python 3.10+ 标准库）
- `evals/triggers.json` 与 `evals/evals.json`：触发边界与行为评判样例

## 边界

- 负责自动化测试设计与工程验证门控；真实页面黑盒交互验收归 `ui-qa-acceptance`，系统架构与纯代码评审归 `arch-backend-craft`，仓库 CI 与 lint 基线初始化归 `repo-baseline`。
- `scripts/find_polluter.py` 按传入顺序逐个执行并在找到首个污染源后立刻早停，要求目标污染产物在开始前不存在（否则以退出码 `2` 拒绝执行）；若仅在多文件组合或并发执行时才出现污染，结合 [测试隔离、资源清理与污染排查](references/isolation-and-polluters.md) 的二分分组排查法定位。

## 来源与整合说明

- **主要引用来源**：核心纪律借鉴自 [`obra/superpowers`](https://github.com/obra/superpowers)（MIT License）的 `test-driven-development`（RED → GREEN → REFACTOR 循环与良好测试编写规范）、`systematic-debugging` 中的条件等待及轮询定位污染文件思路，以及 `verification-before-completion` 的实证要求。
- **整合与调整要点**：
  1. **用跨平台 Python 脚本重写污染源定位器**：原仓库的 `find-polluter.sh` 依赖 bash 环境且扩展性有限；本 skill 使用仅依赖 Python 3.10+ 标准库自研实现了 `scripts/find_polluter.py`，增加基线清理检查、目录存在性预检、`--json` 输出、早停控制并附带完整单元测试（`tests/tdd-testing/`）。
  2. **建立分层测试路由矩阵**：新增 `references/test-strategy-by-layer.md`，区分 `L1–L4`（纯函数 / 状态边界 / 持久化与集成 / 端到端与视觉）选型原则，提供 TypeScript 与 Python 用例模板，减少过度 mock 或全链路滥用。
  3. **补全 LIFO 清理与变异检验要求**：在 `references/isolation-and-polluters.md` 与 `references/writing-good-tests.md` 中加入 LIFO 资源清理栈、多文件组合污染二分排查及「破坏实现验证测试必红」的反镜像断言要求。

## 维护与验证

从本仓库根目录运行全部三项校验（须全部退出码 `0`、0 失败、0 警告）：

```sh
python3 tools/skill-builder/scripts/validate_skill.py skills/tdd-testing
python3 tools/skill-builder/scripts/check_pointers.py --root . skills/tdd-testing
python3 -m unittest discover -s tests/tdd-testing -v
```
