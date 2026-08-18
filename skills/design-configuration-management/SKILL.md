---
name: design-configuration-management
description: "设计、评审和完善生产级应用配置管理体系，包括配置分类、Schema、类型与默认值、来源与优先级、环境隔离、启动校验、动态配置、热更新、配置中心、缓存与失效、Feature Flag、Secret 分离、变更审计、灰度、回滚、漂移检测、Kubernetes ConfigMap/Secret 使用和配置测试。用于建立项目级配置规范、设计动态配置平台接入、治理配置事故。Secret 安全使用、部署流水线参考独立规范。"
---

# 配置管理设计

## 目标

让每个配置都有明确类型、来源、事实版本、验证方式、生效模型和回滚路径，避免“改一个配置直接生产事故”。

## 工作流

1. 分类为 Code Constant、Deployment Config、Secret、Dynamic Config、Feature Flag。
2. 定义 Schema、类型、单位、默认值、范围、Owner。
3. 定义来源和优先级，消除隐式多源覆盖。
4. 启动时完成完整校验。
5. 动态配置定义刷新、版本、原子应用、失败行为和 rollback。
6. Feature Flag 定义 Owner、targeting、TTL/删除条件。
7. Secret 与普通配置彻底分离。
8. 配置变更执行 Validate → Review → Canary → Observe → Rollback/Promote。
9. 记录 revision，并检测环境漂移。

## 核心规则

- 配置不是无类型字符串集合；必须有 Schema、类型、单位、范围和描述。
- 只有安全、稳定、跨环境合理的值才允许代码默认值。
- 生产关键地址、凭据和关键容量参数不能依赖隐藏默认值。
- 配置来源和优先级必须唯一、显式、可查询。
- 同一 key 不应被 env、文件、参数、配置中心多层覆盖而无人知道最终值。
- Secret 不进入 ConfigMap、普通配置文件、Git、日志或文档。
- 启动校验包括 required、range、enum 和跨字段组合约束。
- 动态配置必须说明何时生效、谁读取、如何失败、如何回滚。
- 多字段相关配置使用原子版本快照，避免读取到半套新值。
- 配置中心故障不应让业务线程同步阻塞；使用 last-known-good 或明确失败策略。
- 刷新失败不能把当前有效配置清空。
- 运行实例应可报告配置 revision/摘要，但不得暴露 Secret。
- 高风险配置必须支持灰度、审计和快速回滚。
- Feature Flag 不是永久配置；必须有 Owner 和删除条件。
- Kubernetes ConfigMap 的 volume 与 environment variable 更新语义不同，不能假设已运行进程都会自动即时生效。
- 配置变化应产生可观测 revision/change event。
- 安全相关配置倾向 fail closed；非安全配置可按风险使用 last-known-good。

## 职责边界

本 Skill 负责：

- 配置分类（Code Constant/Deployment/Secret/Dynamic/Feature Flag）；
- 配置 Schema、类型、默认值与优先级；
- 动态配置、原子生效、last-known-good 与回滚；
- Feature Flag 生命周期与 Secret 分离；
- Kubernetes ConfigMap/Secret 使用；
- 配置变更治理、审计与漂移检测。

本 Skill 不负责：

- Secret 的安全存储与密码学实现：不属本 Skill 范围；
- 部署流水线与发布编排：不属本 Skill 范围；
- 日志与可观测性信号：不属本 Skill 范围。

注：Secret 的“安全使用”（不落日志/不硬编码）是本 Skill 的边界要求，但 Secret 的加密存储与密钥生命周期属安全层；配置变更的灰度与回滚是配置治理的一部分，与发布流水线的整体编排区分。

## 参考文件选择

- 处理配置分类、Schema、默认值与优先级时，读取 [references/config-model.md](references/config-model.md)。
- 处理动态配置、原子生效、last-known-good 与回滚时，读取 [references/dynamic-configuration.md](references/dynamic-configuration.md)。
- 处理 Feature Flag 生命周期与 Secret 分离时，读取 [references/feature-flags-secrets.md](references/feature-flags-secrets.md)。
- 处理 Kubernetes ConfigMap/Secret 使用时，读取 [references/kubernetes-configuration.md](references/kubernetes-configuration.md)。
- 处理配置变更流程、审计与漂移检测时，读取 [references/change-governance.md](references/change-governance.md)。
- 了解 K8s、OWASP、12-Factor、Vault 等权威来源时，读取 [references/standards-sources.md](references/standards-sources.md)。

## 输出结构

完整规范优先采用：

1. 配置分类与范围；
2. 配置 Schema 与校验；
3. 来源与优先级；
4. 动态配置与原子生效；
5. Feature Flag 与 Secret 分离；
6. Kubernetes 配置使用；
7. 变更治理与审计；
8. 漂移检测与验证。

使用“必须、应、可”表达约束强度。配置默认值和优先级是本组织决策，不直接复制他人默认。

## 内置资源

- `assets/config-schema-catalog.csv`：配置 Schema 目录（类型/单位/默认/动态/Secret）。
- `assets/config-source-precedence.csv`：配置来源优先级。
- `assets/dynamic-config-policy.csv`：动态配置策略（reloadMode/fallback/maxStale）。
- `assets/config-review-checklist.csv`：配置评审清单。
- `assets/config-change.template.md`：配置变更模板。
- `examples/` 目录：虚构项目配置管理产出样例。
- `scripts/validate_configuration.py`：校验上述资产与模板。

修改资产后运行：

```bash
uv run scripts/validate_configuration.py --assets assets/
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
uv run scripts/validate_configuration.py --assets assets/
uv run python -m unittest discover -s scripts/tests   # 跑测试
```
