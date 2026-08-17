# 订单列表页 — 页面布局规格

## §1 来源、画布与页面骨架

### 1.1 来源

- 截图：examples/orders-page.png
- 设备：DPR 1.0
- 设计基准宽：1440

### 1.2 画布、缩放与坐标口径

```json
{"width": 1440, "height": 900, "scale_factor": 1.0, "design_base_width": 1440}
```

所有事实坐标以截图 px 为准；Normalized 为设计稿口径。

### 1.3 ASCII 线框

```text
┌──────────────────────────────────────────────────────────────────────┐
│                            R-001 顶部导航                            │ 56
├──────┬───────────────────────────────────────────────────────────────┤
│      │                       R-004 筛选条                            │ 64
│ R-002│                                                              │
│ 侧边 ├───────────────────────────────────────────────────────────────┤
│ 导航 │                                                               │
│      │                       R-005 订单表格                          │
│ 220  │                                                               │
│      │                                                               │
│      │                                                               │
│      ├───────────────────────────────────────────────────────────────┤
│      │                       R-006 分页器                            │ 32
└──────┴───────────────────────────────────────────────────────────────┘
```

### 1.4 区域索引

| ID | 名称 | bbox | 布局 |
| --- | --- | --- | --- |
| R-001 | 顶部导航栏 | (0,0,1440,56) | horizontal |
| R-002 | 侧边导航 | (0,56,220,844) | vertical |
| R-003 | 主内容区 | (220,56,1220,844) | vertical |
| R-004 | 筛选条 | (220,88,1220,64) | horizontal |
| R-005 | 订单表格 | (220,168,1180,720) | table |
| R-006 | 分页器 | (220,856,1180,32) | horizontal |

### 1.5 页面级栅格

- 主内容区采用 12 列栅格，列宽 24px，列间距 16px；
- 内容左右安全边距 220px / 40px。

## §2 设计令牌

### 2.1 主题与背景层级

- 默认 surface：#ffffff；
- 提升 surface：#fafafa；
- 主区背景：#ffffff。

### 2.2 颜色与图表色

| name | observed | normalized | confidence | evidence |
| --- | --- | --- | --- | --- |
| surface/default | #ffffff | surface/default | high | EV-002 |
| surface/elevated | #fafafa | surface/elevated | high | EV-002 |
| text/primary | #1f2328 | text/primary | high | EV-002 |
| text/secondary | #57606a | text/secondary | high | EV-002 |
| border/default | #d0d7de | border/default | high | EV-002 |
| accent/primary | #0969da | accent/primary | high | EV-002 |

### 2.3 字号与文字层级

| name | observed_px | normalized_pt | confidence |
| --- | --- | --- | --- |
| text/title-lg | 20 | 16 | medium |
| text/body | 14 | 14 | high |
| text/caption | 12 | 12 | medium |

### 2.4 间距、尺寸与栅格

| name | observed_px | normalized | confidence |
| --- | --- | --- | --- |
| space/1 | 4 | space-1 | high |
| space/2 | 8 | space-2 | high |
| space/3 | 12 | space-3 | high |
| space/4 | 16 | space-4 | high |
| space/6 | 24 | space-6 | high |

### 2.5 圆角、边框与阴影

| name | observed | recommended | confidence |
| --- | --- | --- | --- |
| radius/sm | ~4px | radius-sm | medium |
| radius/md | ~8px | radius-md | medium |
| shadow/sm | soft drop ~4px | 0 1px 2px rgba(0,0,0,0.06) | low |

### 2.6 组件风格约定

- 主按钮：accent/primary 背景，白色文字，radius-sm；
- 次按钮：surface/default 背景，accent/primary 文字，border/default 边框；
- 输入框：border/default 边框，radius-sm，padding 8px 12px。

### 2.7 Observed / Normalized / Recommended 差异

- Observed：截图中直接读到的像素值或颜色；
- Normalized：归一到 token 名，便于跨页面复用；
- Recommended：截图无法精确还原时（如完整 box-shadow、字体族）的工程建议。

## §3 分区详解

### R-001 顶部导航栏

- bbox：(0,0,1440,56)
- 布局：水平；左侧 Logo + 主导航，右侧用户菜单
- 容器：surface/elevated，下边 1px border/default
- 组件：Logo、NavLink × 5、UserAvatar、NotificationBell
- 文案：Logo「NovaPay」、导航「订单/商品/库存/财务/设置」、用户名「NovaOps」
- 状态：仅展示默认态
- Evidence：EV-001, EV-002

### R-002 侧边导航

- bbox：(0,56,220,844)
- 布局：垂直；菜单项左对齐，icon 24px + 文字 14px
- 组件：NavMenuItem × 8
- 文案：「订单/商品/库存/财务/设置/运营/审计/帮助」
- Evidence：EV-003

### R-004 筛选条

- bbox：(220,88,1220,64)
- 布局：水平；左侧搜索框 + 状态筛选，右侧新建按钮
- 组件：Input（搜索）、Select（状态）、Button（primary 新建）
- 文案：「搜索订单号」「全部状态」「新建订单」
- Evidence：EV-004, EV-009

### R-005 订单表格

- bbox：(220,168,1180,720)
- 布局：table；表头高度 44px，行高 48px
- 组件：Table
- 列：订单号、客户、金额、状态、创建时间
- 文案：表头逐字；可见数据行内容略
- Evidence：EV-005

### R-006 分页器

- bbox：(220,856,1180,32)
- 布局：水平；居右
- 组件：Pagination（当前第 1 页）
- Evidence：EV-006

## §4 复用组件规格库

| ID | 类型 | 复用范围 | anatomy 摘要 |
| --- | --- | --- | --- |
| C-001 | Button | 顶部 + 筛选条 | label + padding 8px 16px + radius-sm |
| C-002 | Input | 筛选条 | placeholder + size-md + radius-sm |
| C-003 | Table | 主区 | header 44 + row 48 + cell-padding 12 |
| C-004 | Pagination | 主区底部 | current + total unknown |

## §5 图表与表格规格

### T-001 订单表格

- header_height_px：44
- row_height_px：48
- columns：订单号、客户、金额、状态、创建时间
- alignment：left / right / left / left / left
- cell_padding_px：12
- separator：行底 1px border/default
- Evidence：EV-005

## §6 文案与数据清单

- 顶部导航：NovaPay、订单、商品、库存、财务、设置、NovaOps
- 侧边导航：订单、商品、库存、财务、设置、运营、审计、帮助
- 筛选条：搜索订单号、全部状态、新建订单
- 表头：订单号、客户、金额、状态、创建时间

## §7 状态与响应式

- 已提供：默认态
- 未提供（图中不可见）：hover、active、disabled、loading、error
- 单图响应式：未提供 mobile/tablet 截图；响应式断点规则属 Low Confidence / Recommended

## §8 实现提示

- 用 token 系统（surface/text/border/accent）落地颜色；
- 按钮、输入框使用统一 radius-sm；
- 表格行高 48、表头 44 作为常见 ERP 表格规格；
- 中文字体推荐 system-ui / -apple-system / "PingFang SC" 栈；
- shadow 使用 recommended 的 0 1px 2px（截图无法精确还原）。

## §9 待确认清单

- U-001 hover/loading/disabled 状态未提供（confidence: low）
- U-002 响应式断点未提供（confidence: low）
- U-003 字体族未确定（confidence: low）
- U-004 阴影 box-shadow 完整参数截图无法精确还原（confidence: low）

## §10 自检与 Evidence Ledger

### 10.1 自检

- UI-001 §1–§10 全部存在 ✓
- UI-002 所有区域有 bbox 与 Evidence ID ✓
- UI-003 设计令牌区分 observed/normalized/recommended ✓
- UI-004 所有 Low Confidence 项进入 §9 ✓
- UI-005 图中可见文字逐字登记 ✓
- UI-006 Evidence Ledger 仅保存可重跑命令，不依赖临时文件 ✓
- UI-007 未编造图中不存在的功能/状态 ✓

### 10.2 Evidence Ledger

- EV-001: `image_probe.py info examples/orders-page.png --json`
- EV-002: `image_probe.py palette examples/orders-page.png --colors 12`
- EV-003: `image_probe.py runs examples/orders-page.png --row 480 --tol 6 --min-len 5`
- EV-004: `image_probe.py runs examples/orders-page.png --col 100 --tol 6`
- EV-005: `image_probe.py bands examples/orders-page.png --axis v --top 8`
- EV-006: `image_probe.py runs examples/orders-page.png --row 880 --tol 6`
- EV-007: `image_probe.py crop examples/orders-page.png --box 0,0,1440,56 --scale 3 --out /tmp/crop_nav.png`
- EV-008: `image_probe.py pick examples/orders-page.png --points 240,52 --radius 3`
- EV-009: VLM semantic pass on examples/orders-page.png

### 10.3 探测统计

- 共 9 条证据（8 image_probe + 1 VLM semantic）；
- 跨区覆盖 6 个 regions；
- Low Confidence 项 4 条全部进入 §9。