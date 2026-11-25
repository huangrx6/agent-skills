# 图标

图标只帮助辨识真实角色。相同角色尽量使用相同图标；不要给每个节点加装饰，
也不要用特定厂商 logo 表示与该厂商无关的系统。

**Excalidraw 与 draw.io 均支持同一套 `.excalidrawlib` 素材库**（draw.io 自动将素材矢量元素转为内联 SVG 嵌入，离线可编辑）；Mermaid 生成器仍会明确拒绝 `icon`。

在内容与配色确认后执行 [图标确认](decision-gates.md)：提交是否使用、实际素材来源/库名、节点覆盖清单、
是否使用无框 `shape: "icon"`（拓扑/设备图优先）以及颜色处理，停止等待用户回复。允许明确选择无图标；
不要把“未提图标”理解为已确认无图标。

## 选取与使用（优先外部 `.excalidrawlib` 素材库）

推荐直接使用社区 `.excalidrawlib` 素材库，先查本地缓存再查官方目录，不猜项名：

```sh
python3 scripts/icons_fetch.py --cached                  # 离线列出本地已缓存的全部素材库
python3 scripts/icons_fetch.py --find 防火墙              # 优先离线搜本地缓存，未命中再查官方目录
python3 scripts/icons_fetch.py --get "IT icons"          # 下载到本地缓存
python3 scripts/emit_excalidraw.py system.diagram.json   # 自动扫描全部本地缓存库，无需每次传 --library
python3 scripts/emit_drawio.py system.diagram.json       # draw.io 同样自动扫描并转内联 SVG
```

- **自动跨库发现**：不传 `--library` 时，生成器会自动扫描本地缓存目录内的全部 `*.excalidrawlib`；支持忽略大小写与连字符/空格差异的唯一匹配。
- **跨库混用语法**：同一张图需混用多个库（或重名消歧）时，直接写 `"icon": "库名:图标名"`（例如 `"it-icons:Firewall"`），无需受限于单一 `--library`。
- **无框图标节点**：网络/系统拓扑、安全域/设备图优先给设备节点设 `"shape": "icon"`（图标居中放大至约 48 图内单位、标签居中在下方、无外框），外层仅用 `groups` 画安全域/网段边界，画面更通透。
- 旧内置 sigil（`scripts/sigils.py`）仅作无库离线兼容保留；写 `"库名:图标名"` 时始终走外部 `.excalidrawlib`。

查询/下载使用官方社区素材目录，需要网络。缓存默认在
`~/.agent-skills/data/diagram-authoring/libraries/`，旁边元数据记录作者和来源。
目录中的作品不等于已获任意用途许可；按具体库许可使用，不把下载缓存写入 skill。

显式覆盖顺序：`库名:图标名` → `--library` 路径或缓存库名 → `EXCALIDRAW_LIBRARY` →
`~/.agent-skills/config/excalidraw-library-path` → 自动扫描本地全部缓存库。
未知或重名歧义项会报错并列出候选项，绝不静默错换。

支持 `.excalidrawlib` v1 与 v2：v2 有名称；v1 没有名称，只能按 `#序号` 引用。
生成文件直接含素材矢量元素（Excalidraw）或内联 SVG（draw.io），不必先在用户的编辑器中安装库。

## 视觉与颜色

外部素材可能是一整张带字示意图，缩小后文字不可读。用作角标时优先选纯图形；
不要为了装下库项而把全图图标放大。图标尺寸进入节点尺寸计算，节点会为图形与标签留空间。

| `style.icons` | 颜色处理 |
| --- | --- |
| `auto`（默认） | 单色转节点墨色；多色保留色相，但会调整低对比颜色 |
| `ink` | 统一为节点墨色 |
| `native` | 保留素材颜色 |

描边、粗糙度和大面积填充仍可能被统一；`native` 只控制颜色，**不是完整品牌原貌保证**。
品牌要求不能改形或改色时，先核对导出结果；工具无法满足时用适合原样资产的工作流，
不要把被改造的图标称为官方原版。

带图标的节点使用自由文字与分组，生成时图标和标签整体居中。
后续在编辑器改字不会自动重新排版，修改后要检查与框的关系。
