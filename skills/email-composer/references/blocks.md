# 内容 Spec 与模块

Spec 是唯一数据源。HTML、纯文本、Markdown、.eml 都由它渲染，不分别维护三份内容。
`facts` 用于检查数字声明是否一致；`blocks` 决定结构与顺序。

## 完整示例

```yaml
type: approval
secondary: [handover, confirm]
audience: 上级（内部）
tone: 正式、简洁
to: 王总 <wang@example.com>          # 可选；没有就留空，交付时给建议
cc: [李工 <li@example.com>]          # 可选
subject: 【申请】客户门户上线（2026-11-20 20:00）
greeting: 王总，您好
summary: 申请于 2026-11-20 20:00 发布客户门户，请审批。发布窗口 2 小时。
urgent: false                        # 可选；true 时用 alert
style: business                      # 可选；字符串或 {preset, overrides}
blocks:
  - kind: paragraph
    text: 本次申请包含发布审批、交付说明与工时确认。
  - kind: heading
    text: 发布范围
  - kind: bullets
    items: [首页改版, 审批流并行会签, 移动端适配]
  - kind: images
    items:
      - src: https://example.com/home.png
        alt: 改版后的首页
        caption: 首页改版效果
  - kind: table
    columns: [项目, 工时（人天）, 说明]
    rows:
      - [发布执行, "3.5", 含窗口值守]
      - [功能验证, "1.5", 覆盖三条主流程]
  - kind: steps
    items:
      - {title: 冻结变更, time: "20:00", text: 停止合入，确认版本一致}
      - {title: 灰度发布, time: "20:30", text: 先放量一成}
  - kind: callout
    tone: warn
    title: 回滚条件
    text: 发布后 30 分钟内错误率超过 1%，立即回滚。
  - kind: todo
    items:
      - {text: 确认发布窗口, owner: 李工, due: 2026-11-18 18:00}
  - kind: signature
    name: 张明
    title: 平台组
    contact: [内线 8001]
facts:
  - 2026-11-20 20:00
  - 2026-11-18 18:00
  - "2 小时"
  - "30 分钟"
  - "1%"
  - "20:00"
  - "20:30"
  - "3.5 人天"
  - "1.5 人天"
  - "8001"
placeholders: []                     # 可选的待补说明，不渲染
```

## 顶层字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `type` | 是 | 十个类型之一；可写中文，脚本归一化 |
| `secondary` | 否 | 次类型列表，只追加模块 |
| `audience` | 否 | 收件对象；含「外部/客户」时倾向 plain |
| `tone` | 否 | 语气说明，供写作参考，不参与渲染 |
| `to` / `cc` | 否 | 收件人与抄送；只写入 .eml 头，不渲染进正文 |
| `subject` | 是 | 主题行；缺失会阻断 |
| `greeting` | 否 | 称呼，例如「王总，您好」 |
| `summary` | 否 | 置顶结论，渲染为摘要卡（plain 预设为普通段落） |
| `urgent` | 否 | true 时选 alert 预设，并显示警示色带 |
| `style` | 否 | 预设名，或 `{preset, overrides}`；覆盖见 styles.md |
| `blocks` | 否 | 模块列表，按顺序渲染 |
| `facts` | 是 | 正文全部日期与数字的来源；见下文 |
| `placeholders` | 否 | 已知待补信息，交付清单会列出 |

## 模块

| kind | 必填字段 | HTML | 纯文本 | Markdown |
| --- | --- | --- | --- | --- |
| `summary` | text | 摘要卡（或普通段落） | 原文 | `>` 引用 |
| `paragraph` | text | 段落，`\n` 转 `<br>` | 原文 | 原文 |
| `heading` | text | h2，强调色 | 原文 | `##` |
| `bullets` | items | 无序列表 | `- ` 列表 | `- ` 列表 |
| `table` | columns, rows | 数据表格，可斑马纹 | 首列 + 「字段：值」 | 管道表格 |
| `todo` | items | 事项/负责人/截止时间表格 | 分项 + 字段 | 三列表格 |
| `images` | items | 图片 + 图注 | `[图片]` + 图注 + URL | `![alt](src)` |
| `steps` | items | 编号步骤 | `1.` + 时间 + 说明 | 编号 + 加粗标题 |
| `callout` | text | 左侧色条提示框 | `【说明/注意/风险】` | 引用块 |
| `attachments` | items | 附件列表 | `附件：名称（说明）` | 列表 |
| `cta` | text, url | 按钮 + 完整 URL | 文字 + 独立 URL | 链接 |
| `signature` | name | 分隔线 + 姓名/职务/联系方式 | 多行 | `--` + 姓名 |
| `note` | text | 小字说明 | 原文 | 斜体 |

### 各模块细节

- `bullets.items` 可以是字符串，也可以是 `{text: ...}`。
- `table.rows` 每行列数必须等于 `columns`，否则 Spec 结构错误，渲染直接失败。
- `todo` 的 `owner` / `due` 可以留空，但校验会给警告；交付前补齐。
- `images.items` 的 `width` 可选；不写时按版心宽度输出，写大了会按版心截断并警告。
- `images.alt` 必须非空；空 alt 是阻断项。
- `steps.items` 的 `time` 可选；`text` 可选。
- `callout.tone` 只支持 `info` / `warn` / `risk`。
- `attachments.items` 需要 `name`，`note` 可选；附件名未定时写 `【待填：附件名】`。
- `cta` 只放一个主操作；多个链接会分散注意力。
- `signature.contact` 是列表；每行一个联系方式。

## facts 与声明一致性校验

`facts` 写用户提供的全部事实。校验会从以下字段提取日期、时间、数字，逐项到 `facts` 里找：

- `subject`、`greeting`、`summary`
- 各模块的可见文本：段落、标题、列表、表格表头与单元格、待办事项/负责人/截止时间、
  图片图注、步骤标题/时间/说明、提示框标题/正文、附件名/说明、CTA 文字、签名、小字
- 不包含：图片 `src`、`alt`、CTA `url`、`to`/`cc`、`facts` 自身、`placeholders`

规则：

- 正文出现但 `facts` 没有的日期或数字 → 阻断。日期或时间的分量不能支持普通数字。
- 金额、工时、比例按数值与单位共同匹配；`5 元` 不能支持 `5 万元`，不自动换算。
- 表头为 `工时（人天）` 等括号单位时，数值单元格继承该单位。
- 单位仅支持脚本列出的常见单位；其他单位与字段归属需人工核对。
- 这是 Spec 内部一致性检查，不能证明原始材料真实，也不能识别不同业务字段互换。
- `facts` 有但正文未使用的值 → 不报错。
- 生成的序号（步骤 1/2/3、列表编号）不计入。
- 日期写全年月日；时间写 24 小时制。`2026-11-20 20:00` 能覆盖 `2026-11-20` 与 `20:00`。
- 表格里的工时、金额、百分比都要进 `facts`，包括数字字符串。

## 占位与变量

- 占位统一写 `【待填：xxx】`。它不阻塞写作，但会在校验里成为阻断项；交付前处理。
- `{{name}}` 只用于模板变量，不用于普通 Spec；正文出现未填变量也会阻断。
- 收件人未知时把 `to` 留空，交付清单给建议；不要把 `to` 写成占位邮箱。

## YAML 子集

`render.py` 用内置解析器读取本 skill 的 YAML 子集，不依赖第三方库：

- 2 空格缩进；不能用 tab 缩进。
- 支持映射、列表、行内集合 `[a, b]` / `{k: v}`、单双引号、`|` / `>-` 块标量。
- 中文折行不插空格：`第一句\n第二句` 折叠为 `第一句第二句`。
- 不支持锚点、别名、合并键、多文档；遇到会报错并给行号。
- 复杂内容可以改用 `.json`，脚本会优先按 JSON 解析。
