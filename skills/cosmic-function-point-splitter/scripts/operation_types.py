#!/usr/bin/env python3
"""操作类型词表：给默认提议，不给定额。

同一个操作名在不同需求下可以有不同的数据移动。这里只声明三件事：
  1. 该类操作通常由谁触发（操作员 / 定时任务）；
  2. 在没有相反证据时，子过程描述的默认句式；
  3. 送审表里的排序类别（增删改查→采集→统计→图表→其他）。

**moves 不是计量规则。** 规格里实际写了什么移动就计什么；声明的 op 与移动不一致时，
检查器只提示「偏离词表默认，请写 op_note 说明依据」，不自动改数、不自动补齐。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Op:
    key: str
    label: str            # 功能过程名的动作词，用于句式与提示
    action: str           # H 列句式里的动作词（查询 / 新增 / 导出……）
    category: str         # insert/update/delete/query/metric/send/other
    moves: tuple[str, ...]
    trigger: str = "operator"   # operator | timer
    note: str = ""


OPS: dict[str, Op] = {op.key: op for op in (
    # 基础信息
    Op("query", "查询", "查询", "query", ("E", "R", "X")),
    Op("queryList", "列表查询", "查询", "query", ("E", "R", "X")),
    Op("queryDetail", "详情查询", "查询", "query", ("E", "R", "X")),
    Op("insert", "新增", "新增", "insert", ("E", "W")),
    Op("update", "修改", "修改", "update", ("E", "W")),
    Op("delete", "删除", "删除", "delete", ("E", "W")),
    Op("import", "导入", "导入", "insert", ("E", "W")),
    Op("export", "导出", "导出", "query", ("E", "X")),
    Op("download", "下载", "下载", "query", ("E", "X")),
    Op("enable", "启用", "启用", "update", ("E", "W"), note="对称操作仅在需求与处理相同时合并"),
    Op("publish", "发布", "发布", "insert", ("E", "W"), note="是否与取消发布合并按触发及处理差异判断"),
    Op("up", "上线", "上线", "update", ("E", "W"), note="上线/下线是否合并按触发及处理差异判断"),
    # 审批
    Op("pass", "审批", "审批", "update", ("E", "W"), note="通过/驳回按触发与处理差异判断；意见与历史不自动另拆过程"),
    # 发送
    Op("send", "发送", "发送", "send", ("E", "X"), note="提醒/推送/通知/同步统按发送类"),
    Op("push", "推送", "推送", "send", ("E", "X")),
    # 指标
    Op("collect", "采集", "采集", "metric", ("E", "W"), trigger="timer"),
    Op("stat", "统计", "统计", "metric", ("E", "W"), trigger="timer"),
    Op("chart", "查看图表", "查看", "metric", ("E", "R", "X")),
    Op("report", "报表查询", "查询", "metric", ("E", "R", "X")),
    # 其他
    Op("verify", "验证", "验证", "other", ("E", "W", "X"), note="模拟调用/校验类；序列按真实交互，不套定额"),
    Op("other", "其他", "处理", "other", ()),
)}

# 排序类别：送审表的本地编排惯例，不是 COSMIC 规则。
# 指标三段式的次序固定为 采集 → 统计 → 查看图表/报表查询。
ORDER = {
    "insert": (1, 0), "update": (2, 0), "delete": (3, 0), "query": (4, 0),
    "collect": (5, 0), "stat": (5, 1), "chart": (6, 0), "report": (6, 0),
    "send": (8, 0), "other": (8, 0), "metric": (5, 0),
}

# 名称后缀 → 操作类型。按长度倒序匹配，先长后短（「列表查询」优先于「查询」）。
SUFFIXES: tuple[tuple[str, str], ...] = (
    ("导入确认执行", "insert"),
    ("导入数据预览", "queryList"),
    ("导入文件上传", "import"),
    ("导入模板下载", "export"),
    ("模拟调用验证", "verify"),
    ("报表查询", "report"),
    ("查看图表", "chart"),
    ("列表查询", "queryList"),
    ("详情查询", "queryDetail"),
    ("数据采集", "collect"),
    ("数据统计", "stat"),
    ("查询", "query"),
    ("采集", "collect"),
    ("统计", "stat"),
    ("导出", "export"),
    ("下载", "download"),
    ("导入", "import"),
    ("新增", "insert"),
    ("创建", "insert"),
    ("修改", "update"),
    ("编辑", "update"),
    ("变更", "update"),
    ("删除", "delete"),
    ("移除", "delete"),
    ("启用", "enable"),
    ("停用", "enable"),
    ("发布", "publish"),
    ("上线", "up"),
    ("下线", "up"),
    ("审批通过", "pass"),
    ("审批驳回", "pass"),
    ("审核通过", "pass"),
    ("审核驳回", "pass"),
    ("审批", "pass"),
    ("审核", "pass"),
    ("提醒", "send"),
    ("推送", "push"),
    ("发送", "send"),
    ("通知", "send"),
    ("验证", "verify"),
)

# 三级模块名里不该出现的操作后缀（「模型列表」→「模型」）。
MODULE_SUFFIXES = ("列表查询", "详情查询", "列表", "详情", "查询", "新增", "修改", "编辑",
                   "删除", "导出", "导入", "下载", "管理列表")


def get(key: str) -> Op | None:
    return OPS.get(key)


def infer(name: str) -> str | None:
    """按名称后缀猜一个 op，仅用于提示与排序；不确定时返回 None。"""
    text = name.strip()
    for suffix, key in SUFFIXES:
        if text.endswith(suffix):
            return key
    return None


def op_of(process: dict) -> str | None:
    return process.get("op") or infer(process.get("name", ""))


# 指标三段式在同类里还要再分先后：采集 → 统计 → 查看图表/报表查询。
METRIC_ORDER = {"collect": (5, 0), "stat": (5, 1), "chart": (6, 0), "report": (6, 0)}


def order_key(key: str | None) -> tuple[int, int]:
    if key in METRIC_ORDER:
        return METRIC_ORDER[key]
    op = OPS.get(key or "")
    if not op:
        return (8, 0)
    return ORDER[op.category]


def default_moves(key: str) -> tuple[str, ...]:
    op = OPS.get(key)
    return op.moves if op else ()
