---
name: design-code-writing-standards
description: "设计、审查或完善团队级代码书写规范，包括命名、格式化、文件与目录组织、导入顺序、文件头与版权元数据、作者/时间/版本信息策略、注释与 API 文档、设计原则与设计模式、函数和类型设计、依赖与配置、安全、并发、性能、测试、版本控制和代码评审。用于编写语言无关的主规范及 Java / Go / Python / JavaScript/TypeScript / C# 等语言实施附录，生成检查清单、模板和自动化规则。异常处理体系、API 错误契约与应用日志生命周期参考独立规范。"
---

# 代码书写规范设计

## 目标

产出简洁、可执行、可自动化的代码书写规范，使代码在命名、格式、结构、文档、设计、测试和维护方式上保持一致，同时避免形式主义、过度设计和依赖人工记忆的规则。

## 职责边界

本技能负责：

- 标识符、文件、包、模块、数据库对象和测试命名；
- 编码、换行、缩进、空白、行宽、导入和格式化；
- 文件与目录组织、模块边界和生成代码管理；
- 文件头、许可证、作者、创建时间、修改时间和版本信息；
- 注释、API 文档、TODO/FIXME、示例和变更说明；
- 函数、类、接口、数据模型和公共 API 设计；
- 设计原则、模式选择和反模式治理；
- 空值、可变性、副作用、并发、资源和依赖管理；
- 安全、性能、配置和可测试性；
- 代码评审、质量门禁和自动化检查。

本技能不负责：

- 异常处理与错误码；
- API 契约设计；
- 数据库对象命名与迁移；
- 日志格式与脱敏。

详细异常处理、API 契约、数据库迁移与日志格式参考独立规范。

注：数据库对象（表/列/索引）命名属数据库层；API 字段命名属 API 契约层；代码标识符命名属本 Skill；代码级线程安全属本 Skill。

## 工作流

1. 识别语言、框架、仓库类型和发布方式。
2. 识别规范层级：组织级主规范、项目级规则或语言实施附录。
3. 优先采用语言官方约定和自动格式化工具，不自行发明冲突规则。
4. 把规则分为：
   - 可由格式化器或静态检查器自动执行；
   - 需要代码评审判断；
   - 仅在法律、合规或生成代码场景适用。
5. 对文件头作者、时间和版本信息先确定唯一事实来源，避免与 Git、构建系统和包清单重复。
6. 对设计模式先验证问题和变化点，再选择最小充分模式。
7. 只读取当前任务需要的参考文件。
8. 使用目录模板和验收清单检查一致性；产出的规范文档用 `standard-completeness-checklist.csv` 自查是否覆盖九段。

## 核心规则

- 清晰和正确优先于简短、技巧性和形式统一。
- 规则应尽量由格式化器、编译器、静态分析或 CI 自动执行。
- 标识符必须表达领域含义，避免无约定缩写、误导性名称和类型前缀。
- 同一概念在代码、API、配置和文档中使用同一术语。
- 布尔命名应表达可判定命题，集合命名应体现复数或容器语义。
- 单位、时区、精度和编码在容易混淆时应体现在类型或名称中。
- 使用仓库统一的格式化器和 `.editorconfig`；不得靠评审讨论机械格式。
- 默认使用 UTF-8、统一换行符、文件末尾换行，并清除无意义尾随空白。
- 导入必须确定、分组且可自动排序；避免通配符导入和隐式副作用导入。
- 文件和模块应高内聚、低耦合，公共 API 最小化，生成代码与手写代码隔离。
- 注释主要解释原因、约束、不变量、风险和非显然决策，不复述代码表面行为。
- 禁止保留注释掉的废弃代码；版本控制系统负责保存历史。
- TODO/FIXME 必须关联可追踪事项，并说明原因或退出条件。
- 默认不在每个源文件手工维护个人作者、创建时间、最后修改时间和文件版本；Git、发布标签、构建元数据和包清单应作为事实来源。
- 法律或许可证信息优先使用 SPDX 标识；确需文件头时只放稳定、可自动维护的字段。
- 公共 API、包和发布物的版本在清单、标签或构建元数据中维护，不在普通源文件中重复。
- 优先简单设计、组合、不可变数据和显式依赖；避免全局可变状态和隐藏副作用。
- 设计模式只在存在真实变化点、边界或协作问题时使用；不得以模式数量衡量设计质量。
- 使用设计模式后，名称、职责、生命周期和失败行为必须清晰，并有测试证明收益。
- 安全验证发生在信任边界；禁止硬编码密钥，数据库访问使用参数化接口。
- 性能优化必须基于测量；先保证算法复杂度、资源上限和正确性。
- 并发代码必须明确所有权、线程安全、取消、超时和资源释放。
- 变更应小而聚焦，测试覆盖行为和边界，评审同时检查设计、复杂度、命名、注释和文档。

## 参考文件选择

- 命名、术语、布尔值、单位、文件和测试名称：读取 [references/naming-and-api.md](references/naming-and-api.md)。
- 格式化、编码、导入、文件与目录组织：读取 [references/formatting-and-files.md](references/formatting-and-files.md)。
- 注释、API 文档、TODO、示例和文档同步：读取 [references/comments-documentation.md](references/comments-documentation.md)。
- 文件头、许可证、作者、日期、版本和生成代码标记：读取 [references/file-metadata-versioning.md](references/file-metadata-versioning.md)。
- SOLID、KISS、YAGNI、设计模式与反模式：读取 [references/design-principles-patterns.md](references/design-principles-patterns.md)。
- 类型、函数、安全、并发、性能、配置和依赖：读取 [references/implementation-quality.md](references/implementation-quality.md)。
- 语言差异和实施附录：读取 [references/language-adaptation.md](references/language-adaptation.md)。
- 测试、代码评审、质量门禁和发布验收：读取 [references/testing-review.md](references/testing-review.md)。
- 需要标准来源时：读取 [references/standards-sources.md](references/standards-sources.md)。
- 多语言仓库的规范组织与目录布局：读取 [references/repository-layout.md](references/repository-layout.md)。
- 需要完整产出样例时：读取 [examples/README.md](examples/README.md) 下的虚构项目示范。

## 输出结构

完整规范优先采用：

1. 目标、适用范围与规范强度；
2. 命名与术语；
3. 格式化、文件和目录；
4. 文件头、许可证和版本信息；
5. 注释与文档；
6. 设计原则与设计模式；
7. 实现质量、安全、并发和性能；
8. 测试、评审和自动化；
9. 语言实施附录。

使用“必须、应、可”表达强度，对应目录中的 `MUST / SHOULD / MAY`（便于机器校验，脚本 `RULE_SEVERITIES = {"MUST", "SHOULD", "MAY"}`）。映射：必须 = MUST（违反即构建失败或评审不通过）；应 = SHOULD（默认遵守，偏离需说明理由）；可 = MAY（推荐，按场景取舍）。不要把个人偏好写成强制规则，也不要用无法自动执行的精确行数、函数长度或模式数量作为通用质量指标。

本 Skill 负责“代码级的命名、格式、结构、注释、设计模式与评审”，不复制上述领域的实施细节。

注：数据库对象（表/列/索引）命名属数据库层；API 字段命名属 API 契约层；代码标识符命名属本 Skill；代码级线程安全属本 Skill。

## 内置资源

- [assets/naming-convention-catalog.csv](assets/naming-convention-catalog.csv)：命名规则目录。
- [assets/file-header-policy.csv](assets/file-header-policy.csv)：文件头与元数据策略。
- [assets/design-pattern-catalog.csv](assets/design-pattern-catalog.csv)：模式适用条件与风险目录。
- [assets/code-review-checklist.csv](assets/code-review-checklist.csv)：代码评审检查清单。
- [assets/standard-completeness-checklist.csv](assets/standard-completeness-checklist.csv)：规范文档完整性自查清单（按九段校验产出是否覆盖）。
- [assets/editorconfig.template](assets/editorconfig.template)：基础 EditorConfig 模板。
- [assets/source-file-header.template.txt](assets/source-file-header.template.txt)：条件式文件头模板。
- `scripts/validate_code_standard.py`：校验上述 CSV 目录。

修改目录后运行：

```bash
uv run scripts/validate_code_standard.py \
  assets/naming-convention-catalog.csv \
  --header-policy assets/file-header-policy.csv \
  --pattern-catalog assets/design-pattern-catalog.csv \
  --review-checklist assets/code-review-checklist.csv \
  --standard-completeness assets/standard-completeness-checklist.csv
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
uv run scripts/validate_code_standard.py assets/naming-convention-catalog.csv --header-policy assets/file-header-policy.csv --pattern-catalog assets/design-pattern-catalog.csv --review-checklist assets/code-review-checklist.csv --standard-completeness assets/standard-completeness-checklist.csv
uv run python -m unittest discover -s scripts/tests   # 跑测试
```

