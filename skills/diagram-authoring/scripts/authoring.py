"""Authoring vocabulary shared by routing, validation and semantic review.

Patterns guide content; they do not add layout algorithms or silently edit facts.
Display presets are review targets; generation typography lives in presentation.py.
"""

AUDIENCES = {
    "engineer": "保留组件名、接口和条件；将实现细节放 detail 或附图。",
    "mixed": "首次解释缩写，主标签写职责，技术标识放 detail。",
    "executive": "突出影响、责任和关键决策；仍保留本次结论依赖的条件与异常。",
}

PATTERNS = {
    "capacity": {
        "type": "architecture", "name": "容量与等待",
        "signals": ["瓶颈", "积压", "排队", "backpressure", "bottleneck", "queue depth"],
        "question": "工作为什么等待，处理能力限制在哪里？",
        "required": ["输入来源", "队列与容量或速率（注明单位和来源，未知就写未知）",
                     "受限处理点", "处理与等待/拒绝路径"],
        "avoid": "不要用同宽流水线掩盖竞争，也不要从框大小推断容量。",
    },
    "lifecycle": {
        "type": "state", "name": "对象生命周期",
        "signals": ["生命周期", "lifecycle", "终态", "等待恢复"],
        "question": "同一个对象怎样进入、等待、恢复和结束？",
        "required": ["状态名称", "主阶段", "适用的等待/恢复状态", "终态与带触发条件的转移"],
        "avoid": "取消和失败含义不同时分别保留；当前自环尚不支持，不能伪造新状态绕过。",
    },
    "recovery": {
        "type": "flow", "name": "主流程与恢复",
        "signals": ["回滚", "回退", "补偿", "rollback", "compensation"],
        "question": "正常路径如何完成，失败后如何恢复？",
        "required": ["正常完成路径", "判断条件", "失败后动作", "有依据的恢复入口或终止结果"],
        "avoid": "不要省略失败分支，也不要把执行动作画成状态。",
    },
    "boundary": {
        "type": "architecture", "name": "边界与访问",
        "signals": ["信任边界", "权限边界", "trust boundary", "隔离区", "跨网访问"],
        "question": "谁可以跨越哪条边界，通过什么入口？",
        "required": ["参与者", "真实区域归属", "允许的跨界路径及条件", "禁止路径的文字说明"],
        "avoid": "现有 groups 是平面分组；嵌套网络范围须拆图，禁止路径不要画成正常可达边。",
    },
    "decomposition": {
        "type": "mindmap", "name": "主题分解",
        "signals": ["主题分解", "知识分解", "概念分解", "topic decomposition"],
        "question": "一个主题由哪些子主题构成？",
        "required": ["唯一根主题", "可辨识的父子关系", "同层级概念", "稳定节点 ID"],
        "avoid": "多父关系与横向依赖需要 dependency；不要为画成树而删边。",
    },
    "dependency-impact": {
        "type": "dependency", "name": "依赖与影响",
        "signals": ["循环依赖", "影响范围", "变更影响", "dependency cycle", "blast radius"],
        "question": "谁依赖谁，修改后可能影响哪些对象？",
        "required": ["依赖方向约定", "焦点模块", "直接依赖", "真实循环或跨层依赖"],
        "avoid": "依赖与运行时调用不可混用；存在依赖不等于必然造成故障。",
    },
}

# Logical viewing pixels, independent of raster export density. Floors are initial
# project defaults for review, not a visual-acuity guarantee or a WCAG assertion.
PRESETS = {
    "doc-inline": {"width": 960, "height": None, "min_text": 10, "padding": 32},
    "doc-wide": {"width": 1280, "height": None, "min_text": 10, "padding": 32},
    "slide-16x9": {"width": 1280, "height": 720, "min_text": 16, "padding": 40},
    "print-a4-landscape": {"width": 1120, "height": 792, "min_text": 12, "padding": 40},
    "fit": {"width": None, "height": None, "min_text": None, "padding": 32},
}
