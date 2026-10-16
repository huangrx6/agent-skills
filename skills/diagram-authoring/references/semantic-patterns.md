# 表达模式：先决定读者要理解什么

写 spec 前明确一句阅读问题。复杂关系先选主问题，再选图型；没有匹配模式时直接选图型。
模式要求保留关键信息，不授权编造数值或强制删除节点。选错模式时换模式，不改事实配合模板。
脚本模式 ID 和起手清单由 [authoring.py](../scripts/authoring.py) 维护。

| 读者问题 | pattern / 图型 | 必须保留的表达 | 当前限制 |
| --- | --- | --- | --- |
| 为什么排队？ | capacity / architecture | 来源、队列、真实容量或速率、处理/等待结果 | 没有队列专用图元，用明确命名节点和说明；未知容量写未知 |
| 对象如何经历阶段？ | lifecycle / state | 主阶段、适用的等待恢复、终态、触发事件 | 自环尚不支持，不伪造额外状态 |
| 失败后怎么办？ | recovery / flow | 主路径、判断结果、恢复动作、重新进入点 | 恢复必须有来源；不能将失败都改成终止 |
| 谁能跨边界访问？ | boundary / architecture | 真实归属、访问入口、允许条件、禁止项说明 | groups 是平面分组；禁止路径写说明，不伪装成允许连接 |
| 主题由什么构成？ | decomposition / mindmap | 根主题、父子层级、稳定 ID | 多父/环关系改 dependency/network，不能删边成树 |
| 改动影响谁？ | dependency-impact / dependency | 明确依赖方向、焦点模块、跨层和循环 | 不从依赖推断确定故障，影响范围需结合事实解释 |

可用 `guide.py "一句话" --audience mixed --preset doc-inline --json` 辅助；
自动命中多个模式时保留候选，不强制等用户挑。显式 `--pattern` 只覆盖模式选择，
不能使未支持的图型变成已支持。

## 意图记录

可选 `intent.question` 记录本图回答的问题；`intent.audience` 记录读者；`intent.pattern`
记录已选模式。详见 [规格契约](diagram-spec.md)。它们不改布局、不改标签，不增加确认步骤。

- engineer：保留关键接口/条件，避免堆实现细节。
- mixed：主标签写职责，首次解释缩写，技术标识放 detail。
- executive：写清影响、责任、关键决策；结论依赖的条件与异常仍要保留。

受众与 detail 信息量档位独立。选择 executive 受众不会自动隐藏任何信息。
