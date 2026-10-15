# Bases 工作台视图

Bases 是 Obsidian 的核心插件。工作台使用原生表格读取笔记属性；需求、缺陷、任务仍以 Markdown
文件为主档。视图不会自动同步外部平台、分派任务或生成状态事实，也不要求其他 skill。

## 交付资产与范围

- [首页](../assets/workbench/工作台.md)、[使用说明](../assets/workbench/工作台使用说明.md)与[首页样式](../assets/workbench/obsidian-work.css)。
- [工作台.base](../assets/workbench/工作台.base)：8 个原生表格视图，中文列名和一项类型展示公式。
- [需求模板](../assets/workbench/templates/模板%20-%20需求.md)、[缺陷模板](../assets/workbench/templates/模板%20-%20缺陷.md)、
  [任务模板](../assets/workbench/templates/模板%20-%20任务.md)、[日常记录模板](../assets/workbench/templates/模板%20-%20日常记录.md)、
  [外部工作项模板](../assets/workbench/templates/模板%20-%20外部工作项.md)：使用核心 Templates 占位符。

视图匹配全库中明确设置 `work_kind` 的 Markdown 笔记，不要求工作项放在固定目录。
`work_kind` 只接受 `requirement / bug / task / log / release`；目录中出现 `Templates`、`templates`
或 `模板` 的文件，以及 `type: template` 的文件被排除。这里的目录判断匹配完整路径段。
不会凭现有 `status: active`、标题或所在项目目录把旧笔记猜成工作项。

当前资产使用 table，不依赖 Kanban、Cards、Dataview 或 Templater。首页和可选 CSS 属于展示层；
即使不用首页样式，直接打开 `.base` 也可筛选和编辑。

## 手工接入已有知识库

1. 先检查目标文件是否已存在。合并用户已有视图、笔记和模板，不直接覆盖；保留可恢复副本。
2. 将 `assets/workbench/` 中的首页、使用说明和 `.base` 复制到知识库内 `99 System/工作台/`。
   将 `obsidian-work.css` 复制到 `.obsidian/snippets/`，在「设置 → 外观 → CSS 代码片段」刷新并启用。
   样式仅作用于带 `obsidian-work-home` 的首页；在现有首页和系统索引中添加工作台入口。
3. 将 `assets/workbench/templates/` 中的 5 个文件复制到 `99 System/模板/工作台/`。
   目录可以按实际约定调整；修改位置后同步首页链接和模板排除范围。
4. 在 Obsidian「设置 → 核心插件」启用「Bases」。需要用模板时启用「模板 / Templates」，沿用已有
   模板根目录；没有现行设置时可设为 `99 System/模板`。不要为工作台把原有模板根目录缩窄。
5. 打开 `.base` 检查所有视图。首页可使用下列嵌入；同一文件中的其他视图通过顶部菜单切换。

   ```markdown
   ![[99 System/工作台/工作台.base#待推进]]
   ![[99 System/工作台/工作台.base#近期记录]]
   ```

6. 新建笔记后通过核心「插入模板」命令选择相应模板，补已确认信息。核心模板会替换
   `{{title}}` 和 `{{date:YYYY-MM-DD}}`；普通文件复制不会自动替换这些占位符。
7. 需求、缺陷、任务和外部引用页在正式记录前按 [工作项规则](work-items.md) 分配唯一、持久的
   `work_id`。模板故意留空，避免多次使用生成相同编号。日志不强制编号。

新模板的负责人和状态是“待确认”，不代表已有分工或已进入某个执行阶段。只有用户或来源明确
尚无人负责时改为“未分配”。`due` 等日期字段为空，不放“待确认”或提示语；确认日期后再填日期。
`created / updated` 的模板日期表示记录创建时间；后续仅在内容真实改变时更新 `updated`。
核心模板和 Bases 不会自动维护 `updated`。

外部工作项模板不猜对象类型，`work_kind` 初始留空。根据实际来源填写 `requirement / bug / task`
后才进入视图；类型尚不明确的草稿继续在原笔记或项目入口查找，不伪装成已分类事项。

## 各视图的规则

| 视图 | 范围与展示 |
| --- | --- |
| 待推进 | 仅显式 `authority: local` 的需求、缺陷、任务；只排除“已完成 / 已取消”，空值和未知状态继续可见 |
| 需求 | 本地需求，含所有状态，按笔记修改时间倒序 |
| 缺陷 | 本地缺陷，含所有状态，保留真实优先级和关联项 |
| 任务分工 | 本地任务，按原始 `assignee` 分组，保留上级工作项与截止日期 |
| 外部跟踪 | 显式 `authority: external` 的需求、缺陷、任务；只展示外部状态与负责人快照，以及两个独立时间字段 |
| 近期记录 | `log / release`，按 `file.mtime` 倒序取最近 30 篇；列名为“笔记修改”，不是事件时间或完成时间 |
| 待整理 | 只检查需求、缺陷、任务；缺编号、主档归属不是 local/external，或本地状态/负责人缺失或待确认时进入 |
| 已完成 | 本地需求、缺陷、任务且原状态明确为“已完成”；笔记修改时间不等于实际完成时间 |

缺 `authority` 的旧笔记不会被默认当作本地主档。日志和发布记录不因缺编号、负责人、状态进入
“待整理”；这三个字段不是普通事件记录的必填项。“未分配”表示已确认无人负责，不当作未知。

当前状态词是工作台的默认约定。项目已有不同用语时，先确认哪些词表示已验收完成或取消，再调整
“待推进”和“已完成”的精确匹配条件；不能简单把不在预设列表的状态当作已完成。任务分工会显示
全部任务，查看当前安排时可在界面中追加状态筛选。

`status`、`assignee` 等原属性保持可编辑。唯一的 `formula.kind_label` 只把 `work_kind` 展示成中文，
不写回原文件。视图编辑原属性会更新对应笔记；编辑外部快照只改变本地记录，不会写入外部系统。
外部字段的语义和更新依据见 [外部协同](external-collaboration.md)。

空属性使用 `isEmpty()` 判断，不用 `!note.status` 等隐式真假值判断，避免缺失字段漏检。
全局过滤器与单视图过滤器按 AND 合并。`order` 指列顺序，`sort` 指行排序，`groupBy` 指分组。
截止日期排序不承诺有日期事项排在空日期之前；空日期表示尚无确认排期，不能隐藏或自动补日期。
首次没有符合条件的笔记时，空表是正常结果；使用真实事项逐项接入，不为展示效果编造工作数据。

## 验证边界

保存前检查 YAML 可解析、公式引用已定义、排序键及列名有效、模板属性无重复键。实际接入后还需
在本机 Obsidian 打开首页和各视图，检查公式、筛选、分组、空值与日期排序，并用可恢复的测试笔记
确认属性编辑回写。检查深浅主题、窄窗口和普通笔记不受首页 CSS 影响。

特别核对：未知状态仍在待推进；缺主档归属只进入待整理；外部快照不进入本地待办；本地任务完成
不改变关联外部缺陷；模板文件不出现；日志不因缺工作项字段而被误报。
YAML 解析成功只证明格式可读取，不证明 Obsidian 公式运行、界面效果或状态事实已验证。

## 官方依据

- [Bases 语法](https://obsidian.md/help/bases/syntax)：过滤器、公式、属性、视图及嵌入上下文。
- [视图与嵌入](https://obsidian.md/help/bases/views)：排序、分组、视图切换及 `base#视图名`。
- [表格视图](https://obsidian.md/help/bases/views/table)：原生表格、属性编辑和汇总。
- [公式函数](https://obsidian.md/help/bases/functions)：列表判断、字符串拆分和 `if`。
- [笔记属性](https://obsidian.md/help/properties)：文本、链接、日期和 `cssclasses`。
- [核心模板](https://obsidian.md/help/plugins/templates)：日期与标题占位符。
- [CSS 片段](https://obsidian.md/help/snippets)：可选首页样式及单篇笔记作用域。
- [官方 API 类型](https://github.com/obsidianmd/obsidian-api/blob/master/obsidian.d.ts)：Bases 的排序配置。
