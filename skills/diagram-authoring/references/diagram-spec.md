# 结构规格契约

`*.diagram.json` 是闭合字段集。`scripts/validate_spec.py` 拒绝未知键；
布局参数、坐标、宽高、色值和像素字号不属于 spec。输出路径、后端和 draw.io 配色用 CLI 控制。

## 可运行示例

以下 JSON 可保存为 `system.diagram.json`，两个后端均可生成：

```json
{
  "type": "architecture",
  "title": "订单服务的请求与存储",
  "direction": "LR",
  "detail": "standard",
  "visual": "auto",
  "groups": [{"id": "core", "label": "服务边界", "level": "tint"}],
  "nodes": [
    {"id": "client", "label": "客户端", "kind": "client"},
    {"id": "orders", "label": "订单服务", "kind": "service", "group": "core", "emphasis": "primary"},
    {"id": "db", "label": "订单库", "kind": "data", "group": "core"}
  ],
  "edges": [
    {"from": "client", "to": "orders", "label": "提交订单"},
    {"from": "orders", "to": "db", "kind": "data", "label": "保存"}
  ],
  "cards": [{"title": "边界说明", "items": ["本图只表达请求与持久化关系"]}]
}
```

## 顶层字段

| 字段 | 含义 |
| --- | --- |
| `type`（必填） | `architecture` / `dependency` / `flow` / `state` / `mindmap` / `network` |
| `nodes`（必填） | 非空节点数组 |
| `title` | 图标题，字符串 |
| `edges` | 边数组；省略表示无边 |
| `groups` | 区域声明，节点用 `group` 引用 |
| `cards` | 图下结论卡，每卡包含 `title` 和非空字符串数组 `items` |
| `direction` | 分层图的 `LR` / `TB`；径向与力导向不靠此字段排列 |
| `detail` | `executive` / `standard`（默认）/ `diagnostic` |
| `visual` | Excalidraw 视觉方向，见下表；省略或 `auto` 按图型、mood 选择 |
| `mood` | 用户的视觉意图短句，辅助自动选方向/方案 |
| `style` | 样式轴对象，见下表 |

`architecture` / `dependency` 默认 LR；`flow` / `state` 默认 TB。
`mindmap` 用径向布局，`network` 用力导向布局。不能把算法名写成 type。

## 节点、边和分组

节点必填 `id`、`label`、`kind`。ID 为非空字符串且图内唯一，标签为非空字符串。

| 节点可选字段 | 取值与作用 |
| --- | --- |
| `kind`（必填） | `client` / `service` / `data` / `async` / `security` / `external` / `plain` |
| `shape` | `rect` / `round` / `capsule` / `ellipse` / `diamond` / `cylinder` / `note` |
| `emphasis` | `muted` / `normal`（默认）/ `primary` / `critical` |
| `detail` | 次级说明字符串；不是顶层的信息量档位 |
| `group` | 已声明区域的 ID |
| `icon` | 内置或已确认的库项名称；仅 Excalidraw，见 [图标](icons.md) |
| `rank` | 非负整数，分层图的明确层级约束；不是坐标 |
| `pin` | `left` / `right` / `top` / `bottom`，分层图方向约束 |

缺省形状按角色选：client→ellipse、data→cylinder、async→capsule、external→note，
其余→round。用 diamond 表示实际判断点，不能仅为装饰而换形状。
`kind` 不决定重要性；默认节点均为中性，重点由 emphasis 决定。

边必填 `from` / `to`，必须指向存在的节点，不接受自环；可选 `id`、`label`、`kind`。
边 kind：`sync`（默认同步实线）、`data`（数据实线）、`async` / `optional`（虚线）。
循环流程使用不同节点间的回边，不用自己连自己的节点。

分组必填 `id`，可选 `label`、`description`、`level`、`style`。
level 为 `neutral` / `tint` / `accent` / `critical`；至少一个节点引用该组。
区域从成员位置包围而成，声明 group **不会把成员自动聚到一起**。
部分重叠、夹入非成员会阻塞；需要时改真实分组或分层，不能靠缩区域掩盖问题。
区域标题应短，超过两行会报错。

`rank` 与边方向冲突会失败；主轴 pin 不能把有前驱的节点强行放到起点。
这些约束不表达精确角落或像素位置；需要任意手工摆放时，生成后在编辑器里调整。

## 信息量和样式

| `detail` | 可见内容 |
| --- | --- |
| `executive` | 隐藏部分次要节点说明与用户边标签；使用前确认不损失本次必须表达的事实 |
| `standard` | 节点说明和显式边标签 |
| `diagnostic` | 在 standard 基础上，为未标注的非默认边型补语义标签 |

`cards` 可容纳支撑性说明，不能靠隐藏关键边标签或把全部事实塞进卡片解决拥挤。

Excalidraw 的五个方向是 `botanical`、`editorial`、`fresh`、`coastal`、`night`；
颜色种子与推导规则只在 `scripts/palette.py` 维护。`auto` 不是第六套配色。
draw.io 使用独立的 `--scheme`，见 [后端说明](drawio-backend.md)。

| `style` 键 | 档位 | 缺省 |
| --- | --- | --- |
| `fill` | `hachure` / `cross-hatch` / `solid` | `hachure` |
| `stroke` | `shape` / `solid` / `dashed` / `dotted` | `shape` |
| `corners` | `shape` / `sharp` / `round` | `shape` |
| `line` | `straight` / `sketch` / `rough` | `sketch` |
| `icons` | `auto` / `ink` / `native` | `auto` |

`shape` 表示沿用形状本身的边角/描边；stroke 只管节点与区域，边虚实由边 kind 控制。
区域 style 覆盖顶层对应轴。draw.io 不支持 Excalidraw 的纹理填充，输出为实心；
不要把选项存在理解为两个后端画法完全相同。

## 修改与检查

```sh
python3 scripts/validate_spec.py system.diagram.json --json
python3 scripts/check_layout.py system.diagram.json --quality showcase --json
```

校验只查本契约与布局模型；源材料真实性、图是否讲清楚及应用重排后的效果还需复核。
字段与默认值以 `validate_spec.py`、`palette.py`、`shapes.py`、`layout.py` 为准。
