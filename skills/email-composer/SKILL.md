---
name: email-composer
description: >-
  Use when 起草、润色和制作工作邮件（申请、通知、确认、汇报、交付、协调、商务、跟进、邀请、日常），
  输出主题行与正文（HTML、纯文本或 Markdown），并支持保存与复用邮件模板。中文触发：写邮件、发邮件、
  做邮件模板、HTML 邮件。Do NOT use for: 修改单句的聊天回复、整理会议纪要、群发营销邮件、
  直接发送邮件（v1 只输出草稿文件）、复杂网页。
---

# 工作邮件

把一句需求写成可直接用的邮件。先判定类型、补齐关键信息，再写内容 Spec（唯一数据源），
最后按选定的样式渲染并校验。HTML、纯文本、Markdown、.eml 都由同一份 Spec 生成。

运行环境：Python 3.10+，无第三方依赖、网络或邮箱连接；本地解析 YAML/JSON。

## 边界

- 只用用户提供的事实；缺关键事实先问，缺非关键信息写 `【待填：xxx】`。
- v1 不发送、不接邮箱、不做群发营销和复杂网页，只输出草稿文件。
- 不编造数字、日期、人名、链接。用户说「直接生成」时仍要列出假设。
- 视觉验证只到浏览器；Outlook 用 Word 引擎，交付时提醒用户先自测。

## 流程

| 步骤 | 做什么 | 产物 / 门槛 |
| --- | --- | --- |
| 1 接收 | 读需求与材料，判定类型与对象 | 主类型、次类型、期望动作 |
| 2 检查 | 关键事实缺失或矛盾就追问 | C1：一轮 ≤ 4 题；清晰则跳过 |
| 3 设计 | 写内容 Spec，列全 facts | `spec.yaml` / `spec.json` |
| 4 样式 | 普通邮件直接采用预设；复杂版式按需预览 | C2：仅用户要求预览或存在影响结果的版式选择时 |
| 5 渲染 | 生成 HTML / 纯文本 / Markdown / .eml | 输出到 `./email-out/` |
| 6 校验 | 阻断项清零，警告逐条判断 | `validate.py` 的 JSON 报告 |
| 7 交付 | 主题、收件人、文件、待填、假设 | 交付清单 |
| 8 复用 | 结构稳定才问是否存模板 | C3：可选 |

需求清晰时直接出稿，跳过 C1、C2。C3 仅作为交付后的可选建议，不阻塞任务。
用户说「直接生成」时跳过常规确认，内容完整就正常渲染，不加 `--draft`。
仅在正文存在缺失或矛盾事实时保留待填项，用 `--draft` 输出并列明未确认内容；
不自行选定冲突版本，不把默认值当成金额、日期等事实。

## 1 类型与信息检查

十个类型：通知、申请/审批、确认、汇报、交付/验收、协调/故障、商务、跟进、邀请、日常。
主类型由「用途 + 期望动作」决定；一封邮件承担多种用途时写 `secondary`，见
[types.md](references/types.md)。

C1 只问会改变结论的信息：类型、收件人关系、期望动作、时间/金额/范围。
一轮最多 4 题，选择题优先并标推荐项；能从材料推断的直接推断，并在交付清单注明依据。
材料里的日期或数字互相矛盾时先追问；用户明确要求直接生成时保留矛盾待填项。
用户未回答时只对样式与格式采用默认值；事实仍待确认，不能把沉默当作认可。

## 2 内容 Spec

```yaml
type: approval
secondary: [handover]
subject: 【申请】客户门户上线（2026-11-20 20:00）
greeting: 王总，您好
summary: 申请于 2026-11-20 20:00 发布客户门户，请审批。
blocks:
  - {kind: paragraph, text: 本次申请包含发布审批与交付说明。}
  - {kind: table, columns: [项目, 工时（人天）], rows: [[发布, "3.5"], [验证, "1.5"]]}
  - {kind: todo, items: [{text: 确认发布窗口, owner: 李工, due: 2026-11-18 18:00}]}
facts: ["2026-11-20 20:00", "2026-11-18 18:00", "3.5 人天", "1.5 人天"]
```

字段、13 个模块与三种渲染见 [blocks.md](references/blocks.md)；写作规则与中文语气见
[writing.md](references/writing.md)。所有日期与数字必须进 `facts`；金额、工时、比例必须带单位，表格按列头单位检查。
这是声明一致性检查，不证明来源真实；仍须逐项对照用户材料，生成的结构编号不算。
占位统一写 `【待填：xxx】`，不要写进 `to`。

## 3 样式

四套预设：`business`（默认）、`report`、`plain`、`alert`。按类型与场景自动选择；
用户指定品牌色或预设时以用户为准。普通邮件直接渲染；确需 C2 时一次展示：

> 结构：主题 + 摘要 + 范围（3 条）+ 工时表（3 行）+ 待办（2 项）+ 签名。
> 样式：business，强调色 #1F4E79，宽 640px，标题左侧色条。
> 接受 / 调整颜色 / 更简洁 / 更正式 / 换预设？

按用户反馈调整样式令牌，不重写内容，不强制退回默认方案。令牌与覆盖方式见 [styles.md](references/styles.md)。

## 4 渲染与校验

```sh
python3 <skill路径>/scripts/render.py spec.yaml --outdir ./email-out
python3 <skill路径>/scripts/render.py spec.yaml --formats html,text,md,eml --preset report
python3 <skill路径>/scripts/validate.py spec.yaml --report report.json
```

默认输出 HTML + 纯文本 + Markdown；`.eml` 用 `--formats all` 或显式追加。
校验阻断项必须清零：主题缺失、收件人占位、正文占位/未填变量、HTML 宽度超 640、
flex/grid/script/form/position、图片缺 alt、数字声明不匹配、HTML 与纯文本数字不一致。
警告项逐条判断：图片过大/本地路径、正文过长、段落过长、感叹号/emoji。
申请、确认、协调、商务、跟进、邀请、交付检查动作及时限；日常、通知、汇报不强制。
默认渲染与套用均先校验，有阻断项不写文件，返回 1。明确要求草稿时，使用
`render.py spec.yaml --draft`，输出文件加 `DRAFT_`，报告保留阻断项，有阻断时仍返回 1；
HTML 禁用构造不能用草稿模式绕过。交付清单首行标注未清零项。

HTML 兼容、纯文本与 .eml 规则见 [html-compat.md](references/html-compat.md)。

## 5 模板

模板库是独立数据目录，可随时增删；**具体模板名称只存在于模板库，不写进 SKILL.md、
references、脚本或测试**。默认优先当前目录 `email-templates/`，否则用 skill 自带的
`templates/`；`--root` 或 `EMAIL_TEMPLATES_DIR` 可覆盖。

```sh
python3 <skill路径>/scripts/template.py list [--type <类型>] [--query <关键词>]
python3 <skill路径>/scripts/template.py show <id>
python3 <skill路径>/scripts/template.py candidates spec.yaml
python3 <skill路径>/scripts/template.py save --spec spec.yaml --id <id> --name <名称> \
  --var '原值={{变量}}'
python3 <skill路径>/scripts/template.py apply <id> --vars vars.json --outdir ./email-out
python3 <skill路径>/scripts/template.py update --id <id> --spec spec.yaml --note <说明>
python3 <skill路径>/scripts/template.py add-html path/to/mail.html --id <name>
python3 <skill路径>/scripts/template.py apply html/<name> --set 'key=value'
```

- Spec 模板：先 `candidates`，将明确变化的值参数化后 `save`；仅歧义项需确认；缺变量报错，不默认填充。
  存模板前把日期、时间、金额、人名、项目名参数化；真实邮箱/电话不允许入库。
- HTML 模板：把 `.html` 放进 `<root>/html/` 即出现在 `list`；`{{name}}` 是变量，
  可选 sidecar `<name>.vars.json` 提供说明与默认值。入库及套用前与 Spec 模板同样
  检查固定日期/时间及邮箱/电话；直接放入目录也不能绕过。默认输出 HTML + 纯文本，不输出 Markdown，
  不做数字声明一致性检查。
- 套用前校验未通过时，不写文件；退出码 1 表示阻断，2 表示参数/变量错误。

目录、变量、入库门槛与限制见 [templates.md](references/templates.md)。

## 6 交付清单

1. 主题行：主选一个，备选一个。
2. 收件人与抄送建议；未确认地址就写「待确认」，不要编造。
3. 输出文件路径（HTML / 纯文本 / Markdown / .eml）。
4. 附件清单与缺失附件。
5. 待填项清单（`【待填】` 与 `placeholders`）。
6. 校验摘要：报告实际阻断数量，草稿明确标注未通过；警告与跳过的检查也要写。
7. 假设清单：本次采用的默认值、推断依据、未确认的信息。

## 默认值

- 收件环境：通用兼容，覆盖 Outlook 与主流邮箱。
- 输出格式：HTML + 纯文本 + Markdown；需要时加 `.eml`。
- 图片：图床 URL 占位，由用户替换；本地图片在 `.eml` 中内嵌。
- 邮箱连接器：不接，只输出文件。
- 语言：中文，专业术语保留英文。

## 兼容与限制

- 宽度 ≤ 640、单列、表格布局、内联样式；不用 flex/grid/position/script/form。
- 远程图片大小无法测量；本地图片按路径引用时只能在作者机器上预览。
- 原始 HTML 模板保留自带版式，不做数字声明一致性检查，不输出 Markdown。
- 校验只证明结构与规则，不证明内容正确；Outlook 必须由用户自测。

## 按需阅读

- [类型与槽位](references/types.md)：十个类型、必填信息、复合规则、预设对应。
- [追问话术](references/questions.md)：C1 四题、占位边界、C2/C3 话术。
- [写作规则](references/writing.md)：主题、开头、段落、称呼、禁用词与语气示例。
- [内容 Spec 与模块](references/blocks.md)：字段、13 个模块、facts、YAML 子集。
- [样式预设](references/styles.md)：四套预设、令牌结构、覆盖与 C2。
- [HTML 兼容](references/html-compat.md)：布局、图片、纯文本、.eml 与 Outlook 边界。
- [模板库](references/templates.md)：Spec 模板、HTML 扩展、变量、版本与门槛。
