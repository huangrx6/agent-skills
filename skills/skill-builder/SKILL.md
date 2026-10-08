---
name: skill-builder
description: >-
  Use when creating a new skill or reviewing whether a skill's trigger description and
  scope are clear. 中文触发：建一个 skill / 要不要包成 skill / 帮我起 SKILL.md /
  这个 skill 老是不触发 / 触发描述太宽或太窄 / 评审 skill 边界。
  Identify the reusable workflow, compare adjacent skills, and write an actionable entry
  with realistic trigger examples. Do NOT use for: ordinary edits to an existing skill's
  body, scripts, references or assets; one-off prompts; running a formal trigger benchmark.
---

# skill-builder

把可复用的工作方法写成容易触发、能执行、能核验的 skill。用户已明确要求创建或调整时，
在授权范围内直接推进；缺少历史使用次数不是拒绝工作的理由。

## 先确定范围

从当前请求和已有材料回答这些问题，不必逐条向用户提问：

1. **解决什么重复问题？** 用户经常给什么输入，想拿到什么产物，哪些步骤需要固定下来？
   尚无使用记录时，用具体预期场景建立初版，说明待验证处；一次性任务通常直接完成即可。
2. **什么时候触发？** 写出用户会实际说的话，包含常用语言和产物名称。
3. **与相邻 skill 怎么分工？** 阅读可能重叠的 description，按输入、动作、产物区分。
   能由现有 skill 完整覆盖时优先复用；有独立流程时再拆分。允许同一任务合理组合多个 skill。
4. **本次做到哪里？** 定义一个可完成的主流程、必要依赖、验证方式和能力边界。
   不为了凑齐目录而新增脚本、素材或参考文件。

只有影响结果、无法从上下文判断的信息才问用户。不要用“过去 30 天用够几次”、固定写作时长
或必须先修改另一个 skill 的描述作为开工门槛。

## 写 description

- 先写用途和具体触发条件，再写最容易混淆的排除项；本仓库以 `Do NOT use for:` 标识边界。
- 使用用户的常用表达；中文工作流应有中文触发语，但不堆砌同义词。
- description 是发现入口，正文是操作流程；不要把完整命令、安装步骤或历史故事塞进入口。
- 对照相邻 skill，确保一般请求不会误触发，也不会把真正属于自己的任务排除出去。
- 不承诺尚未实现或未验证的功能。触发准确度需要独立测试，不能由措辞好看推断。

## 写最小可执行流程

正文保留开始工作必须知道的信息：输入、配置发现、关键步骤、真实工具入口、检查方式和交付。
把按条件才需要的详细格式、后端差异、示例放进 references，并在正文说明何时读取。

- 优先记录本项目特有的知识、可靠脚本和难以猜出的约束，不重复通用助手礼仪。
- 配置、路径、账号和秘密从环境或配置读取；示例使用占位符。
- 脚本是行为的依据，文档说明接口与限制；不要复制一份容易漂移的实现细节。
- 仅在风险和用户授权范围要求时确认。用户已授权的可逆工作不重复设审批门。
- 删除过时流程、无依据的比例/次数、重复叙述；保留影响决策的理由即可。
- 可调用的独立 skill 不应依赖仓库外不可用的文件；必需共享资源要说明安装关系或包含后备方案。

目录与边界见 `references/anatomy-and-scope.md`；精简现有内容时读 `references/slimming.md`。
仓库内为使用者补一份 README，用法见 `references/skill-readme-template.md`。

## 验证与交付

1. 对照脚本 CLI、实际文件和已实现行为，检查每个命令、链接和限制。
2. 运行 `scripts/validate_skill.py <skill目录>`：结构约束以脚本定义为准。
   正文上限是仓库的维护约定，不是模型能力边界；不要为压行数写成电报体。
3. 运行 `scripts/check_pointers.py` 检查目标存在；逐项确认引用内容确实支持正文的说法。
4. 涉及对外文档时运行 `scripts/check_leakage.py`；未配置词表表示扫描未执行，不能称“已排除泄露”。
5. 脚本行为改变时跑对应回归；触发或流程改变时，用真实正例、近似反例和授权边界场景评估。
   独立评估只向执行者提供用户输入和 skill，不提供预期答案；结果再与判据比较。
6. 仓库维护可运行 `scripts/preflight.py` 汇总结构、泄露、指针检查与文件快照。
   它不运行回归测试，不证明产物质量，也不自动证明脚本有无用处。
7. 新增或移除 skill 时更新根索引；改变 SKILL.md 后，用仓库的锁文件工具生成哈希。
   仅当后续方向改变时更新 ROADMAP，不记每次维护流水账。

报告实际改动、检查结果和仍有的限制。失败、跳过、未执行分别说明，不能拿静态检查代替
浏览器渲染、外部 API 或视觉验收。简洁证据写法见 `references/reporting.md`。
