---
name: obsidian-personal-knowledge-base
description: >-
  操作 Huangrx6 的 Obsidian 知识库 /Users/huangrx6/obsidian。用于在库内创建、更新、移动、重命名、审阅、整理笔记；在 Inbox、Projects、Areas、Resources、Archive、Assets、System 之间判断内容归属；维护 MOC、索引、模板、周计划、周报、项目主页、领域主页、学习笔记和技术资源笔记。使用目录专属规则：Areas/Projects 使用轻量工作管理规则，Resources 才使用深度研究和学习笔记规则。
  处理 Resources 技术学习笔记时，尤其要保证 API 入口、依赖安装、参数说明、可运行示例、轻量 MOC、独立正文、配图清单和表达风格都能直接用于长期复用。
  本 skill 绑定特定 vault 路径 /Users/huangrx6/obsidian，**跨机复用性低**——换电脑或换 vault 路径需要重新校准 references/vault-map.md。
---

# Obsidian 个人知识库

在 `/Users/huangrx6/obsidian` 这个正在演进的 PARA + MOC 知识库里工作。行动前先查看当前文件，目录可能已经被用户重置或重组。

## Prerequisites（机器绑定）

本 skill 绑定 Huangrx6 的本机 Obsidian vault：

- vault 路径必须是 `/Users/huangrx6/obsidian`
- `references/vault-map.md` 描述的是这个 vault 的 PARA + MOC 结构；用户调整过目录结构后需要**同步更新** `references/vault-map.md`，否则起手流程会基于过期信息做判断
- **跨机复用性低**：换电脑或换 vault 路径都需要重新校准

参考本 skill 依赖的 5 个 references：`vault-map.md` / `resource-notes.md` / `work-management.md` / `writing-conventions.md` / `research-and-synthesis.md`。

## 起手流程

1. 读取 `references/vault-map.md`，确认当前目录结构和归位边界。
2. 按目标目录和任务行为分类，不只按关键词判断。
3. 只加载当前任务需要的引用文件。
4. 编辑前打开最近的索引、MOC、模板或主笔记。
5. 编辑后更新最近的索引/MOC，并检查明显的失效链接。

如果用户说某个区域被删除、重置或重建，以真实文件系统为准，不要凭旧链接或记忆恢复已删除结构，除非用户明确要求恢复。

## 任务分流

| 目标/任务 | 加载这些引用 | 工作姿态 |
| --- | --- | --- |
| 归位、重命名、移动、MOC/索引维护 | `vault-map.md`、`writing-conventions.md` | 结构准确、导航轻量。 |
| `01 Projects`、`02 Areas`、周计划、周报、工作日志、交付记录 | `vault-map.md`、`writing-conventions.md`、`work-management.md` | 行动导向，短、清楚、看状态。 |
| `03 Resources`、学习笔记、技术概念、研究综合 | `vault-map.md`、`writing-conventions.md`、`resource-notes.md`；需要研究时再读 `research-and-synthesis.md` | 使用深度学习笔记质量标准。 |
| 审阅已有笔记 | `writing-conventions.md` 加上对应目录的专属引用 | 按笔记所在目录审阅，不套一套全局写法。 |
| 归属不清的临时内容 | `vault-map.md`、`writing-conventions.md` | 放入 `00 Inbox`；只有归位风险较高时再问。 |

资源区规则不会自动套用到领域区或项目区。不要强迫项目计划、领域 MOC、周计划、工作日志解释基础概念、添加配图提示词，或满足学习笔记深度，除非用户明确要求写成学习笔记。

## Resources 技术学习笔记规则

处理 `03 Resources` 下的技术课程、框架教程、SDK/API 笔记时，按长期可复用材料来写。正文只写技术事实、判断依据、操作方式和排错路径；不要出现写给作者自己的后台话术，例如“课程说明”“读者复制代码”“给别人用”“后续补充”“这里要提醒读者”。

### 技术准确性

- 涉及现代框架、SDK、包名、import 路径、参数、迁移和 warning 时，先查当前官方文档、API reference、实际代码或本地报错；不要凭记忆或包名猜测。
- 区分“当前可用写法”“旧教程还能跑但会 warning”“未来可能迁移方向”。不要把趋势写成已经完成的事实。
- 包拆分场景要同步写清安装包、import 路径和适用边界。若目标包中对象不存在，明确写当前不可用，不要给出推荐示例。
- 对 LangChain、LangGraph、Deep Agents、OpenAI-compatible provider 等更新较快的主题，优先使用当前文档或本地验证结果。

### 示例代码

- 示例应尽量完整、可复制运行，并包含必要 import、安装依赖、环境变量加载和最小输入数据。
- 对 LangChain/OpenAI-compatible 模型示例，默认使用 `load_dotenv(dotenv_path=".env")` 和 `init_chat_model(model="Qwen/Qwen2.5-14B-Instruct", model_provider="openai")`，除非笔记主题需要别的 provider。
- Notebook/交互式异步示例优先使用 `await main()`；只有明确说明是独立脚本时才使用 `asyncio.run(main())`。
- 示例要能看出当前章节要观察的效果：打印关键输出、metadata、tool_calls、stream chunk、retriever 命中来源、config trace 标记或错误表现。不要只给“能运行但看不出差异”的代码。
- 代码块改完后做 Python 语法检查；有 top-level `await` 时使用允许 top-level await 的编译方式。

### 参数和接口说明

- 对带参数的方法、类和配置项，写清关键参数、默认心智、取值范围、影响、常见误用和适用场景。
- 不只解释“怎么调用”，还要说明输入、输出、状态变化、副作用、失败路径和如何验证。
- 对成组概念要给选择规则，例如 Basic Chain / RAG Chain / Agent Chain，LangChain / LangGraph / LlamaIndex / Semantic Kernel，VectorStore / Retriever，`stream` / `astream` / `astream_events`。

### 正文表达

- MOC 只做轻量导航：一句范围说明 + 子笔记链接 + 每篇一句范围说明。不要在 MOC 里写长篇概念解释、复杂大图、学习目标大表、判断能力清单或正文内容。
- 不要用“模块总览”代替正文。用户已经有 MOC 时，编号 `01` 应该是实质性基础篇，而不是重复路线的总览页。
- 每篇正文只展开本篇知识。避免出现“本模块学习路线”“与后续模块的关系”“延伸阅读”这类路线型章节；路线、跨模块跳转和目录关系交给 MOC 维护。
- 章节编号要连续、稳定。删除“模块总览”或重排章节时，重命名文件、更新 H1、同步 MOC 和全库 wikilink。
- 每个重要小节先说明它解决什么问题、处于哪一层、什么时候用、什么时候不用，再给代码。
- 避免一句话简介式堆标题；如果一个标题下只有泛泛一句话，要补充具体机制、例子、参数或错误场景。
- 正文面向未来检索和复用，少写教学旁白，多写稳定事实和可验证判断。
- 如果用户指出某段“看不出效果”“太简单”“不具体”，优先补对比示例、运行输出、边界条件和错误表现。

### 图示和截图

- 图示数量不设固定上下限。判断标准不是“多”或“少”，而是这张图是否解决了文字难以快速讲清的问题。复杂机制可以有多张图；短小概念可以没有图。
- `## 建议配图与截图清单` 只列必要或高价值图示，不为每个小节凑图，不把正文已经讲清的概念重复画一遍。
- 每张图都要说明“画什么、解决什么理解障碍、放在哪里”。不能说清价值的图，删掉。
- 配图清单优先分层：`核心必画` 放没有图会明显难懂的图；`可选截图` 放真实配置、运行结果、trace、模型报告截图；`不建议画` 可用于明确哪些内容文字足够、不需要配图。
- 已经嵌入正文的图片要定期审查。若图片只是装饰、重复正文、过时、与当前位置不匹配或降低阅读节奏，应删除正文引用，并同步删除未被其他笔记引用的源文件，避免占用空间。
- 需要降低理解成本时优先使用 Excalidraw 手绘风格、白底、浅灰网格、浅色系；技术截图应来自真实配置、运行输出、trace 或模型报告，而不是为了“看起来丰富”而放。
- MOC 一般不放配图清单；配图清单放在具体正文笔记里。只有用户明确要求模块级视觉总览时，才在 MOC 中保留少量导航型图示建议。

### 自测问题

- 正文末尾的自测题要给参考答案。标题优先使用 `## 自测问题与参考答案`。
- 答案要简短但完整，直接回答问题，不只写“见上文”。答案可以复述正文关键判断，方便复习时独立查看。
- 如果问题用于开放判断，答案要给判断维度、边界条件和常见误区，而不是唯一死答案。

### 维护和验收

- 编辑已有笔记时保留 frontmatter，并按实际修改更新 `updated`。
- 批量重命名或重编号后，同步更新 MOC、附近索引和 wikilink，检查旧标题、旧编号和临时文件残留。
- 完成后至少检查：关键旧 import / 旧写法残留、Python 代码块语法、明显失效链接、表格列是否被代码里的 `|` 破坏、尾随空格。

## 目录判断

- `01 Projects`：有明确结果、能完成或关闭的工作。
- `02 Areas`：长期责任、持续维护事项。
- `03 Resources`：可复用知识、学习材料、资料、技术笔记。
- `00 Inbox`：归属不清的捕获和临时笔记。
- `04 Archive`：已不活跃但需要保留的历史内容。
- `90 Assets`：附件、图片、绘图。
- `99 System`：模板、规范、工作流、首页。

如果一个内容看起来可以放多处，只选一个最稳定的主家，再从其他地方链接过去。

## 通用流程

1. 用 `rg --files` 或 `find` 查看现状。
2. 读取父级索引/MOC 和相关模板。
3. 编辑或创建最小但有用的笔记。
4. 编辑已有笔记时保留原前置属性。
5. 只在有助于检索时更新导航。
6. 重命名或移动后，检查附近索引/MOC 是否还有失效链接。

## 引用文件

- `references/vault-map.md`：当前目录地图、活跃结构、归位规则。
- `references/writing-conventions.md`：全库通用命名、前置属性、链接、MOC、排版、重命名规则。
- `references/work-management.md`：Areas、Projects、周计划、周报、工作日志、交付记录。
- `references/resource-notes.md`：仅适用于 Resources 的写作标准、学习笔记审阅、技术示例、配图规则。
- `references/research-and-synthesis.md`：仅适用于 Resources 的研究流程和深度综合规则。

## 安装

通过仓库根的 `npx skills add huangrx6/agent-skills` 安装（详见仓库根 [README.md](../../README.md)）。安装后：

1. 验证本机 vault 路径是否与 `references/vault-map.md` 描述一致
2. Agent 第一次触发本 skill 时会自动读取 `references/vault-map.md` 确认结构
