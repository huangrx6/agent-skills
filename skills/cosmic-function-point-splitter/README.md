# cosmic-function-point-splitter

> 按需求、接口、页面或代码识别 COSMIC 数据移动，生成可核对、可审计的功能点拆分表。

| 适合 | 产物 | 依赖 |
| --- | --- | --- |
| 需求 / 接口 / 页面 / 代码 → COSMIC 拆分 | xlsx 拆分表 · Markdown 自检 · 覆盖清单 | Python 3.10+；xlsx 需 openpyxl |

规则见 [SKILL.md](SKILL.md)，字段见 [规格格式](references/spec-format.md)。

## 快速开始

```sh
python3 -m pip install openpyxl
python3 skills/cosmic-function-point-splitter/scripts/cosmic.py init spec.json
python3 skills/cosmic-function-point-splitter/scripts/cosmic.py check spec.json
python3 skills/cosmic-function-point-splitter/scripts/cosmic.py build spec.json -o 拆分表.xlsx --template 模板.xlsx
```

`check` / `report` / `coverage` 只用标准库。模板可省略，工作表自动探测，可用 `--sheet` 指定。
`build` 自动生成 `.selfcheck.md` 来源报告，可用 `--selfcheck` 改路径。`init` 示例默认为待核实，
需填写真实项目依据。表格与报告须使用不同路径，不能覆盖输入规格、模板、接口清单或自定义术语表；
已有输出可正常重新生成。

<details>
<summary><strong>全部命令</strong></summary>

```sh
python3 skills/cosmic-function-point-splitter/scripts/cosmic.py inspect 模板.xlsx
python3 skills/cosmic-function-point-splitter/scripts/cosmic.py audit 拆分表.xlsx
python3 skills/cosmic-function-point-splitter/scripts/cosmic.py report spec.json -o 自检.md
python3 skills/cosmic-function-point-splitter/scripts/cosmic.py coverage spec.json inventory.json
python3 skills/cosmic-function-point-splitter/scripts/cosmic.py normalize 已有表.xlsx -o 新表.xlsx --write
```

</details>

## 关键行为

- CFP 按显式移动计算，支持同一过程多个输入；目标点数不参与计算。
- 字段完整保留，不自动补造；允许跨行重复属性和单字段数据组。
  公式样式的业务文字保存为文本，超出 Excel 文本限制时报错，不静默截断。
- 已确认标记与待核实规模分别报告；来源真实性需人工核对。
- 结构错误默认不写表；`--force` 可写问题草稿，问题仍保留在报告中。
- 一致性提示（op 偏离、排序、旧句式、英文残留、描述重复）默认只提示；
  `--strict` 时与结构错误一样阻塞，check/report/build/audit 行为一致。
- `--inventory` 把接口/页面清单接入 check/build/report：未覆盖接口、悬空证据、
  空页面与页面覆盖率写入输出与自检报告；`coverage` 单独运行并支持 `--json`。
- `--order crud` 只重排模块内的过程块；`--user-format dual` 写发起者/接收者两行；
  `--require-confirmed` 把未确认过程当阻塞项。
- audit 对比原表声明 CFP 与移动数，保留非法移动及缺损非空行，报告核心列缺失。
  新过程不继承上一过程的名称、用户或触发事件；公式不自动求值。
- normalize 只改子过程描述（`--glossary` 时也改数据组/属性），复制原表后改单元格，
  保留合并与其他工作表；默认干跑，`--write` 需另给 `-o`，不会覆盖原表。
- 表内保留操作类型、操作依据与接口证据，生成和回读审计使用同一份依据。
- 表格没有过程编号时按模块与名称分组，同名相邻过程无法可靠区分。
- 模板只复用基础布局与样式，新建单 sheet；不复制标题内容、辅助表和复杂格式。
  详见 [模板行为](references/templates.md)。

只做 COSMIC 功能规模，不计算金额或工时。结构检查通过不等于标准认证或可送审。

## 代码结构

| 文件 | 职责 |
| --- | --- |
| scripts/cosmic.py | 命令、表格回读、自检与覆盖报告、安全改写 |
| scripts/spec.py | version 3 规格、引用、来源、op 与 evidence 校验 |
| scripts/builder.py | 原样展开移动、保留过程边界、可选 CRUD 排序 |
| scripts/checks.py | 结构硬错误与一致性提示 |
| scripts/operation_types.py | 操作类型词表、默认序列、排序类别 |
| scripts/style.py | 默认句式、旧句式改写、命名与英文残留提示 |
| scripts/glossary.json | 英文保留词与中英映射 |
| scripts/inventory.py | 接口/页面清单、双向覆盖与报告 |
| scripts/sheet.py | 模板探测、表格与追溯列、功能用户写法 |

## 验证

```sh
python3 -m unittest discover -s tests/cosmic-function-point-splitter -v
python3 tools/skill-builder/scripts/validate_skill.py skills/cosmic-function-point-splitter
python3 tools/skill-builder/scripts/check_pointers.py skills/cosmic-function-point-splitter --root skills/cosmic-function-point-splitter
```

测试覆盖字段保真、来源、多输入过程、计数篡改、审计缺损行、输出覆盖保护、模板与命令流程、
操作词表偏离、覆盖缺口、严格模式、排序与安全改写。
evals/evals.json 是行为评估案例，不等于已经执行的模型评测。
