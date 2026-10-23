# 规格格式（version 3）

`init` 生成唯一规格示例；填写真实项目内容后运行 `check`。示例默认为 `unverified`，不假设已有证据。

## 可运行示例

下例是一个触发下保存主数据和关联数据的过程，3 个移动，候选 3 CFP。
它没有独立维护关联数据的需求，因此不会被拆为两个功能过程。
E 行故意省略 `description`，工具会按 `op` 与移动类型推导。

```json
{
  "version": 3,
  "project": "示例项目",
  "measurement": {
    "purpose": "需求阶段功能规模度量",
    "scope": "订阅申请服务",
    "boundary": "业务用户与申请服务之间，持久存储在边界内",
    "layer": "应用层",
    "functional_users": ["业务用户"],
    "conventions": {"排序": "规格声明顺序", "描述句式": "输入/读取/保存/返回"}
  },
  "modules": [{"l2": "订阅服务", "l3": "申请管理"}],
  "processes": [{
    "id": "FP-001",
    "l3": "申请管理",
    "name": "提交订阅申请",
    "op": "insert",
    "trigger": "业务用户提交申请资料",
    "user": "业务用户",
    "status": "unverified",
    "source": "需求 3.2 订阅申请",
    "evidence": ["api-subscription-create"],
    "op_note": "提交前校验资源可用性，完成后返回受理编号",
    "movements": [
      {"type": "E", "object": "订阅申请", "group": "申请资料", "attributes": ["申请人编码", "申请内容"]},
      {"type": "R", "object": "资源", "group": "资源资料", "attributes": ["资源编码", "可用状态"], "description": "读取资源可用状态"},
      {"type": "W", "object": "订阅申请", "group": "申请资料", "attributes": ["申请人编码", "申请内容"]},
      {"type": "W", "object": "申请关联", "group": "关联资料", "attributes": ["申请编码", "资源编码"], "description": "保存申请与资源的关联"},
      {"type": "X", "object": "受理结果", "group": "处理结果", "attributes": ["受理编号", "结果状态"], "description": "返回受理结果"}
    ]
  }]
}
```

`evidence` 里的 id 来自清单文件（见 [材料提取](extraction.md)），只用于覆盖核对；
自然语言依据仍写在 `source`。

## 字段约定

| 位置 | 字段 | 要求 |
| --- | --- | --- |
| 顶层 | version / project / modules / processes | version 为整数 3；模块与过程列表非空 |
| 顶层 | measurement | purpose、scope、boundary、layer 为非空文字；functional_users 为非空列表 |
| measurement | conventions | 可选对象，记录本项目采用的本地惯例（句式、排序、命名），原样写入自检报告 |
| 模块 | l2 / l3 | 非空名称；l3 全局唯一，重名时加业务限定 |
| 过程 | id / name / l3 | 编号与展示名称全局唯一；l3 引用已声明模块 |
| 过程 | trigger / user | 真实触发事件；user 必须在 functional_users 中声明 |
| 过程 | status | confirmed 或 unverified；不会从名字、接口存在与否自动判定 |
| 过程 | source | 需求编号、章节或代码定位文字；可被每个移动的 source 覆盖 |
| 过程 | op | 可选，取自 [操作类型词表](operation-types.md)；只影响默认描述、提示与排序 |
| 过程 | op_note | 可选；声明了 op 但移动序列偏离词表默认时必须能解释依据 |
| 过程 | evidence | 可选接口 id 数组，引用清单文件；用于双向覆盖核对，不改变计量 |
| 过程 | movements | 至少两项，明示实际数据移动，不从操作名推导 |
| 移动 | type / object / group | E/R/W/X、兴趣对象、数据组；object 与 group 不得含首尾空白 |
| 移动 | description | 可省略；省略时按 op 与移动类型推导简洁句式 |
| 移动 | attributes | 一个或多个实际字段；不含空项、重复项，字段名不得含逗号 |
| 移动 | source | 可选覆盖过程来源；confirmed 的每项移动必须能取得非空来源 |
| 移动 | repeat_reason | 同一过程、同一兴趣对象、同类移动再次出现时必填，并说明需求依据 |

状态按过程设置，不能把未核实移动混入已确认过程。来源内容不会由脚本自动读取或验证。
允许同一数据组、相同属性出现在不同移动或不同过程，不因显示重复而改变事实。

`op` 是分类标签，不是模板：写了 `insert` 也可以有 R 与 X；
计量只看 `movements`。声明 op 却不写 op_note 且与默认序列不同，只会得到提示。

## 计数与交付

候选 CFP 为规格中显式移动数；已确认标记与待核实分别汇总，待核实还会给过程数。
只在结构检查通过后才将该数值用于后续人工核查；`--force` 生成的表必须视为有问题草稿。
目标区间不参与脚本计算。

`build` 默认按声明顺序展开；`--order crud` 只在模块内按送审惯例重排过程块。
`--require-confirmed` 会把未确认过程当作阻塞项。`--user-format dual` 只改变功能用户
单元格写法（发起者/接收者两行），不改变规格数据。

拆分表默认只写标准列；加 `--trace` 时在末尾保留过程编号、核实状态、需求依据、兴趣对象、
重复移动理由，以及 op、op_note 和 evidence；模板已有同名列时复用。
自检报告额外包含接口覆盖、一致性提示与 measurement 上下文；xlsx 本身不完整保存顶层范围说明。

## 格式要求

version 固定为 3，用于识别当前文件结构，不提供版本选择或兼容分支。
旧式属性池、操作模板与 version 2 规格不再支持；输入不符合本格式时直接报错，
按 init 示例重新整理。未知版本、未声明引用和非法字段类型会报错；
`--force` 不绕过规格解析错误。
