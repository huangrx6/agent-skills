# Mermaid 后端

用于希望在文档或代码仓库维护文本图的用户；默认交付 `.mmd`，不是图片。
现有 JSON 规格通过 `python3 scripts/emit_mermaid.py` 转换；已有 `.mmd` 可以直接编辑并校验，
目前没有 Mermaid → JSON spec 的反向转换。不要从旧 JSON 重生成后覆盖用户手工编辑而不比对。

## 生成与检查

```sh
python3 scripts/emit_mermaid.py /project/diagrams/orders/.source/orders.diagram.json --colors /project/diagrams/orders/.source/orders.colors.json
python3 scripts/check_mermaid.py /project/diagrams/orders/orders.mmd
python3 dev-tools/sync_exports.py /project/diagrams/orders/orders.mmd
```

`--colors` 可省略，支持与其他后端相同的自由配色输入、节点重点和 `by_group` 浅底色。
不需要另选固定配色方案。生成器只使用 Python 标准库及 skill 内脚本，不启动浏览器。
官方语法检查使用本机 Chrome/Chromium 和固定版本 Mermaid 11.12.0；只调用 `parse()`，不渲染、不落图片。
首次使用/缓存缺失时需要访问 jsDelivr 加载官方 ESM；图内容在本机浏览器处理，不提交在线渲染服务。
离线或浏览器不可用时，保留源文件并说明“官方语法尚未验证”，不能用字符串检查冒充通过。
用 `--browser` 或 `MERMAID_EXPORT_BROWSER` 指定浏览器。

## 支持范围

| spec 类型 | Mermaid 语法 | 边界 |
| --- | --- | --- |
| architecture / dependency / flow | flowchart LR/TB | 保留节点、关系、循环、平行边、显式标签、说明卡和分组 |
| state | stateDiagram-v2 | 普通状态、同步转移、循环、转移标签；不自动添加初始/终止状态 |
| mindmap / network | 暂未支持自动转换 | 不把径向/力导向图悄悄改成流程图 |

- ID 映射为稳定的安全标识符；中文、保留词、标签中的引号与语法符号会转义。
- flowchart 的椭圆映射为 stadium，便签映射为虚线矩形；这两项是外观近似，其他基础形状对应原生 Mermaid 形状。
- state 模式拒绝分组、卡片、特殊形状、非同步边。普通区域不等于复合状态，不能无依据转换。
- `icon`、`rank`、`pin` 明确拒绝，不丢弃约束后假装等价。图标或精细布线需求使用 Excalidraw/draw.io。
- `detail` 沿用既有信息量规则；线条虚实来自边 kind。手绘粗糙度、纹理和角样式不映射，采用 Mermaid 原生样式。
- Mermaid 自己计算坐标和路由，不复用本 skill 的几何布局、避让、预设字号验收，也不承诺无交叉。
  默认增大层间距和节点间距；真实效果仍需编辑器预览或用户需要的导出图核对。
  子图与外部节点相连时，其内部方向可能服从整体方向，不能把分组声明当作精确布局锁定。
- 已有手写 `.mmd` 由官方解析器检查；它能接受的图型不等于结构规格生成器支持的图型。

## 长文本排版

节点标题与 detail 使用不同的中文/拉丁加权行宽，显式换行；保留完整文字，避免宿主默认窄框把句子挤成竖条。
说明卡采用更宽的正文行宽、左对齐和段落空行。空行含零宽占位，兼容原生 SVG 标签忽略空行的行为；
样式同时覆盖宿主 HTML 标签与原生 SVG 文本。宿主禁用 frontmatter/CSS 时可能不能保持相同外观，须在目标宿主核对。

有说明卡时，主图和说明区使用两个透明容器，外层 TB，并通过 `~~~` 不可见布局线把说明区放在主图之后。
主图保留原方向；这条线连接容器，不是新增业务关系。没有说明卡时不增加容器或布局线。
说明区内按宿主布局排列，不能承诺每次都横向并排；不为横排而添加虚构业务箭头。
复杂长图在“整图适应窗口”时仍会变小，局部框更宽不等于适合一页展示。需要拆图或精简内容时先确认。

## 按需导出与更新

```sh
# 只有明确需要时新增 SVG，已有 PNG 也会一并刷新：
python3 dev-tools/sync_exports.py /project/diagrams/orders/orders.mmd --format svg
# 外边距需要更大时：
python3 dev-tools/sync_exports.py /project/diagrams/orders/orders.mmd --padding 100
```

导出器使用原生 SVG 文本便于光栅化；对锁定版本遗留的单层 HTML 转义只在 SVG 文本节点解码一次，
不把解码内容作为 HTML 插入。源 `.mmd` 保留宿主默认标签方式。
支持 PNG/SVG，默认留白 80 图内单位，PNG 默认倍率 2。SVG 保持矢量自然尺寸，倍率不改变其尺寸。
同步工具保存并沿用 scale/padding；没有任何已有导出时不启动浏览器、不写导出参数文件。
不支持固定宽高/PDF；不把不支持的参数静默忽略。导出失败保留旧文件并明确提示它可能过期。
`.mmd`、`.drawio`、`.excalidraw` 如果同目录同名，会争用图片名，需先区分主题名或后端目录。

官方依据：[流程图](https://mermaid.js.org/syntax/flowchart.html)、[状态图](https://mermaid.js.org/syntax/stateDiagram.html)、
[API](https://mermaid.js.org/config/usage.html)。文档站当前版本可能高于锁定的运行时，新增语法需实测后再启用。
