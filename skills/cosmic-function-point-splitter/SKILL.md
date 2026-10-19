---
name: cosmic-function-point-splitter
description: >-
  Use when 按 COSMIC 度量软件功能规模、把需求/接口清单/页面或代码转成有来源依据的功能过程与
  E/R/W/X 拆分表、核对接口与页面覆盖，或核查与改写已有 COSMIC 表。中文触发：COSMIC、CFP 估算、
  功能点拆分、功能点清单、拆分表、接口清单、送审自检、规模度量。Do NOT use for: IFPUG/NESMA、
  金额报价或工时评估、普通需求与测试文档。
---

# COSMIC 功能点拆分

从功能用户需求识别功能过程，再按真实数据移动计算 CFP。接口、页面和数据表是证据，
不是固定换算单位。先读 [拆分原则](references/splitting-rules.md)；边界或规则疑问查
[标准与参考来源](references/measurement-sources.md)；送审表的句式、命名与排序见
[命名与写法](references/naming-and-style.md)。

## 范围与证据

从材料确定目的、范围、软件边界、层和功能用户；缺少会改变结果的信息再问用户。
区分已实现功能、已确认的待开发需求与未经确认的候选，不能混为已确认规模。

- 材料可以是需求、接口文档、后端路由、前端代码、可读源码的 HTML 原型、截图或 DDL。
  取证方式与常见遗漏见 [材料提取](references/extraction.md)。
- 截图里看不见的入参/出参标 `unverified`；页面可见字段可以直接作为属性来源。
- 从代码取证保留文件位置与接口；从需求取证保留章节或需求编号。
- 允许从需求直接开始，不强制先造接口清单；已有表直接 audit。

**不得编造**接口、功能过程、数据属性或提效数据。无法实证的条目保留并标待核实，
不用经验补字段、不用目标规模反推功能。

## 工作流

| 步骤 | 产物 | 判断方式 |
| --- | --- | --- |
| 1 范围与素材 | measurement、接口/页面清单 | 边界、层、功能用户清楚；素材覆盖可核对 |
| 2 功能过程 | 功能清单 | 按触发事件与完整业务响应划分，不按接口或表的数量划分 |
| 3 数据移动 | 规格 `spec.json` | 明确 E/R/W/X、兴趣对象、数据组、真实属性与依据 |
| 4 核对与交付 | xlsx + 自检/来源报告 | 结构通过；覆盖与提示逐项处理；人工核对来源与过程划分 |

用户已授权完整交付且材料充足时直接生成，不增加清单审批关口。
无法确认的过程标 `unverified`，分别报告候选规模与已确认标记规模。

有接口或页面素材时，先枚举页面并建清单，再在规格里用 `evidence` 认领接口：

```sh
python3 <skill路径>/scripts/cosmic.py coverage spec.json inventory.json
```

未覆盖接口、悬空证据、空页面会逐项列出；低于 90% 的页面覆盖提示「素材可能不完整」。
覆盖核对不自动认领接口，也不证明清单完整。

## 命令

```sh
python3 <skill路径>/scripts/cosmic.py init spec.json
python3 <skill路径>/scripts/cosmic.py check spec.json --inventory inventory.json
python3 <skill路径>/scripts/cosmic.py build spec.json -o 拆分表.xlsx --template 模板.xlsx
python3 <skill路径>/scripts/cosmic.py audit 已有表.xlsx
python3 <skill路径>/scripts/cosmic.py report spec.json -o 自检清单.md
python3 <skill路径>/scripts/cosmic.py inspect 模板.xlsx
python3 <skill路径>/scripts/cosmic.py coverage spec.json inventory.json --json
python3 <skill路径>/scripts/cosmic.py normalize 已有表.xlsx -o 新表.xlsx --write --glossary
```

- `check` 只校验与预估；`build` 默认检查失败不写表，`--force` 仅保留有问题的草稿。
- `build` 每次同时写自检与逐项来源报告（默认输出文件名加 `.selfcheck.md`）。
- 结构问题阻塞；一致性提示与覆盖缺口默认不阻塞，`--strict` 时一并阻塞。
- `--order crud` 只在模块内按送审增删改查惯例重排过程块；`--user-format dual` 写
  「发起者/接收者」两行；`--require-confirmed` 有未确认过程就不写表。
- `normalize` 默认干跑，只改子过程描述措辞；`--glossary` 同时清理数据组与属性的英文。
  它复制原表后改单元格，保留合并与其他工作表，不覆盖输入。

## 计量约束

- 每个过程使用稳定 id，记录触发事件与功能用户；每项移动明示类型、兴趣对象和属性。
- 同一过程可有多个 E；按过程编号分组，不能遇到 E 就另起过程。
- 同一过程同一兴趣对象同类移动再次出现时，填写有需求支持的 `repeat_reason`。
  工具只检查理由存在，合理性需人工核对；重复执行次数或数据条数不能直接增加 CFP。
- 字段原样保留，不截断、轮转或补造。相同数据组与属性可以跨行使用。
  超出 Excel 单元格限制时明确报错；公式样式的业务文字按文本保存。
- 错误提示、成功确认与结果回执属于 X；翻页与取消等控制命令不计。
  变更度量按受影响的数据移动计数，不与新建立量混用；LocalFP 单独在表外计量。
- `op` 是分类标签，不是定额：写了「新增」也可以有 R 与 X。声明 op 却偏离默认序列时，
  写 `op_note` 说明依据；工具不改数、不自动补齐。
- 不把固定中文句式、全表文字唯一、至少三个字段或零英文当成 COSMIC 规则。
  项目格式要求不得改变真实字段、功能过程或计量结果。
- 目标 CFP 只用于比较范围差距；需求不变时，改变目标不能改变拆分和计量。

## 交付与限制

- 交付范围、候选 CFP、已确认标记/待核实 CFP 与过程数、逐项来源、接口证据和人工待核实项。
- 已确认只是规格作者的标记，工具不验证来源内容；结构通过不等于可以送审。
- audit 保留非法行与原表 CFP；缺失值、非法值和未求值公式均报告。
  支持按过程合并计数或逐行计数求和；新过程不借用上一过程的用户或触发事件。
- 表中没有过程编号时按模块与过程名切块；同名相邻过程无法可靠区分，需补编号。
- 输出是新工作簿，不保留模板辅助 sheet、原始标题内容和复杂格式；
  模板差异见 [模板行为](references/templates.md)。
- 只做 COSMIC，不混用其他功能点方法，不计算金额或工时。

## 按需阅读

- [材料提取](references/extraction.md)：五类素材、页面枚举、清单格式与反向覆盖。
- [拆分原则](references/splitting-rules.md)：过程与数据移动的判据、反例与范围差距。
- [操作类型词表](references/operation-types.md)：op、默认句式与常见偏离。
- [命名与写法](references/naming-and-style.md)：E/F/G/H/J/K 惯例、排序与明确拒绝的规则。
- [术语表](references/glossary-en-zh.md)：英文保留词、替换边界与系统字段。
- [常见坑](references/pitfalls.md)：真实返工点，区分方法问题与格式问题。
- [规格格式](references/spec-format.md)：version 3 字段、示例与计数口径。
- [模板行为](references/templates.md)：探测、缺列、写出与安全改写。
- [标准与参考来源](references/measurement-sources.md)：官方手册、国标与本地惯例边界。

依赖与维护入口见 [README.md](README.md)。
