# product-spec · 产品需求澄清与规格收敛

> 把模糊诉求、用户反馈或零散想法，沿「探索 → 拆期 → 提问 → 方案权衡 → 分段规格 → 自审 → 计划桥接」七关收敛为可复测产品规格与可执行实施交接包。

| 适合 | 产物 | 依赖 |
| --- | --- | --- |
| 需求澄清、多子系统拆期、2–3 方案权衡、可复测 AC、边界矩阵、规格自审与实施计划桥接 | 短规格 / 完整产品规格 · 编号 AC · 边界异常矩阵 · `Global Constraints` · `Review Focus` · 实施计划交接包 | 无外部运行时依赖 |

Agent 的阶段闸门、硬拦截规则、场景判断表与反合理化清单见 [SKILL.md](SKILL.md)，各阶段模板与方法按其中的一层参考链接按需读取。

## 典型用法

直接给出模糊诉求、痛点反馈、待权衡方案或刚对齐待拆解的规格即可触发：

- **零散反馈收敛**：「用户说扩展选择器装了十几个扩展之后很不好用，帮我查一下现有实现，收敛方案、范围边界和可复测 AC。」
- **打包需求拆期**：「我想做一个插件市场、权限管理、自动更新和评价系统，先帮我拆期并定第一期 MVP 规格。」
- **方案对比取舍**：「对比侧栏抽屉、独立弹窗和设置子页三种交互方案，按交互、维护成本和可逆性给推荐。」
- **模糊口径转 AC**：「把『设置页更丝滑、报错更友好、窄窗不乱』改写成测试能直接照步复测的 Given/When/Then 验收标准。」
- **规格自审与研发交接**：「这份规格刚确认完，准备交给前后端并行开发，帮我做构建者视角自审，补齐 Global Constraints、Review Focus 和实施计划交接。」

## 目录结构

- [SKILL.md](SKILL.md)：七关阶段闸门、未确认前禁写代码硬闸门、场景判断表、反合理化清单与一层参考索引
- [references/discovery-and-questioning.md](references/discovery-and-questioning.md)：上下文只读侦察清单、多子系统拆期与体量分级、首轮策略、1–3 关键提问、带推荐项选择题正反例、事实 vs 假设分离与「太简单不用设计」反驳
- [references/options-and-tradeoffs.md](references/options-and-tradeoffs.md)：2–3 方案对比框架、交互/维护成本/演进风险/可逆性权衡矩阵、YAGNI 裁剪五问表与推荐理由论证写法
- [references/spec-structure-and-ac.md](references/spec-structure-and-ac.md)：分段回放节奏、短规格/完整规格模板、Given/When/Then 编号 AC、18 条模糊主观词改写对照、状态生命周期契约与多层作用域 UI 继承/覆盖规范
- [references/edge-and-exception-matrix.md](references/edge-and-exception-matrix.md)：0 项空态、无结果、单条、20+/100+ 高数量、超长混排/URL/Emoji、切页/关闭状态复位、并发竞态、4xx/5xx 保输入恢复、破坏性护栏与存量兼容完整矩阵
- [references/review-focus-and-spec-audit.md](references/review-focus-and-spec-audit.md)：愿景文档原则、`Global Constraints` 提炼、五大隐含失效模式 `Review Focus`、独立构建者视角审查提示词与三堆分拣、6 维规格自审清单
- [references/implementation-plan-bridge.md](references/implementation-plan-bridge.md)：文件归属地图、可独立验证的任务切分、`Consumes / Produces` 接口契约、无歧义步骤粒度与篇幅比例检查、执行方式交接与顺序执行核心纪律
- `evals/triggers.json` 与 `evals/evals.json`：触发正反例与端到端行为评判样例

## 边界

- **只定「做什么、不做什么、怎么验收、如何切分交接」**：不直接编写业务生产代码；不替代视觉样式打磨（归 `ui-design-craft`）、系统架构与表结构设计（归 `arch-backend-craft`）、黑盒 UI 验收执行（归 `ui-qa-acceptance`）或 COSMIC 功能点拆分（归 `cosmic-split`）。
- **硬闸门约束**：规格未获用户明确批准前，不跳进编码、建脚手架或装依赖；一次性探路原型（Spike）须明确标为丢弃物，保留则须重回规格闸门。
- **跨领域协同**：涉及复杂存储迁移、安全边界或跨服务协议时，规格中以约束和契约表达业务要求，技术实现细节交由架构与研发评审确认。

## 来源与整合说明

- **主要引用来源**：方法主干借鉴自 [`obra/superpowers`](https://github.com/obra/superpowers)（MIT License）的 `brainstorming`（探索式澄清、方案对比与独立构建视角审查）与 `writing-plans`（文件结构图、细粒度零占位符步骤拆解）。
- **整合与调整要点**：
  1. **连续七步门控闭环**：将原仓库分离的「构思」与「写计划」两条链路整合为 7 步统一工作流，避免规格刚确认完进入实现拆分时丢失上下文或前提约束。
  2. **双深度路由与硬性禁码闸门**：新增「短规格 vs 全规格」自适应深度，并把「规格未定稿与审查未通过前不得写入任何业务实现或脚手架代码」设为硬门控。
  3. **验收标准改写与边界矩阵补全**：在 `references/spec-structure-and-ac.md` 与 `references/edge-and-exception-matrix.md` 中系统化补充 18 类模糊词改写为 Given/When/Then 可测 AC 的对照表，以及空态、大数据量、CJK/URL/Emoji 溢出、并发竞态、接口错误、破坏性操作保护与旧数据兼容等高频漏项矩阵。
  4. **剥离宿主私有约定**：移除原仓库中依赖特定客户端工作流插件、子智能体命名或固定 `docs/superpowers/...` 输出路径的假设，改为按目标项目实际结构（或 `.specs/`）落盘。

## 校验

本 skill 无可执行脚本，结构、禁词与引用完整性校验在仓库根目录运行：

```sh
python3 tools/skill-builder/scripts/validate_skill.py skills/product-spec
python3 tools/skill-builder/scripts/check_pointers.py --root . skills/product-spec
```
