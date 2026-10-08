# 图标

图标只帮助辨识真实角色。相同角色尽量使用相同图标；不要给每个节点加装饰，
也不要用特定厂商 logo 表示与该厂商无关的系统。

当前只有 Excalidraw 后端支持 `icon`；draw.io 会明确拒绝。

## 选取与使用

内置 sigil 无需外部库，覆盖 user/api/database/queue/shield/cloud/external/plain 等常见语义：

```sh
python3 scripts/sigils.py
python3 scripts/sigils.py --name database
```

节点可写 `"icon": "database"`。内置名称优先于同名外部库项。
需要更丰富或真实品牌图标时，先查目录，不猜项名：

```sh
python3 scripts/icons_fetch.py --search 数据库
python3 scripts/icons_fetch.py --get "IT icons"
python3 scripts/icons.py --library it-icons --grep database
python3 scripts/emit_excalidraw.py system.diagram.json --library it-icons
```

查询/下载使用官方社区素材目录，需要网络。缓存默认在
`~/.cache/diagram-authoring/libraries/`，旁边元数据记录作者和来源。
目录中的作品不等于已获任意用途许可；按具体库许可使用，不把下载缓存写入 skill。

本地库选择顺序：`--library` 路径或缓存库名 → `EXCALIDRAW_LIBRARY` →
`~/.config/excalidraw-library-path`。`icons.py --size <项名>` 可检查尺寸。
未知项名会报错并列出可用项，不能静默换成另一个图标。

支持 `.excalidrawlib` v1 与 v2：v2 有名称；v1 没有名称，只能按 `#序号` 引用。
生成文件直接含素材元素，不必先在用户的编辑器中安装库。

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
