# email-composer

> 把一句需求变成可直接用的邮件：判定类型、补齐信息、写内容 Spec，渲染为 HTML / 纯文本 /
> Markdown / .eml，并在交付前做兼容与声明一致性校验。

| 适合 | 产物 | 依赖 |
| --- | --- | --- |
| 工作邮件起草与润色 · HTML 邮件 · 邮件模板复用 | `.html` · `.txt` · `.md` · `.eml` · 模板库 | Python 3.10+；无第三方包、无网络、不接邮箱 |

## 快速开始

命令均从仓库根目录执行，`<skill路径>` 指本目录。

```sh
# 1. 按 Spec 渲染三格式
python3 <skill路径>/scripts/render.py spec.yaml --outdir ./email-out

# 2. 校验（阻断项非零时退出码 1）
python3 <skill路径>/scripts/validate.py spec.yaml --report report.json

# 3. 需要 .eml 时
python3 <skill路径>/scripts/render.py spec.yaml --formats all
```

脚本也接受 `.json` 规格。YAML 由内置子集解析器读取，不依赖 PyYAML；具体支持的写法见
[references/blocks.md](references/blocks.md#yaml-子集)。

## 输入

一份内容 Spec（YAML 或 JSON）是唯一数据源：

```yaml
type: approval
subject: 【申请】客户门户上线（2026-11-20 20:00）
greeting: 王总，您好
summary: 申请于 2026-11-20 20:00 发布客户门户，请审批。
blocks:
  - {kind: paragraph, text: 本次申请包含发布审批与交付说明。}
  - {kind: table, columns: [项目, 工时（人天）], rows: [[发布, "3.5"], [验证, "1.5"]]}
facts: ["2026-11-20 20:00", "3.5 人天", "1.5 人天"]
```

完整字段、13 个模块与三种渲染见
[references/blocks.md](references/blocks.md)；示例见
[examples/approval-release.yaml](examples/approval-release.yaml)。

## 输出

默认写到 `./email-out/`，文件名为 `<主题简称>_<日期>.<扩展名>`：

| 格式 | 说明 |
| --- | --- |
| `.html` | 内联样式、表格布局，宽度 ≤ 640px，兼容 Outlook / 主流邮箱 |
| `.txt` | 标题用【】、表格转字段列表、链接单独成行 |
| `.md` | 保留结构，方便二次编辑 |
| `.eml` | `multipart/alternative`；本地图片以 cid 内嵌，可由 Outlook / Foxmail 打开 |

## 校验

渲染与套用默认先校验，有阻断项返回 1 且不写文件。明确要不完整草稿时，
`render.py spec.yaml --draft` 输出 `DRAFT_` 文件并保留报告，未通过仍返回 1；
禁用 HTML 构造不可绕过。普通邮件直接出稿，复杂版式或用户要求预览时才确认。

`validate.py` 输出 JSON 报告，分 `blocking` / `warnings` / `skipped` / `stats`。

阻断项：主题缺失、收件人占位、正文占位或未填变量、HTML 宽度 > 640、flex/grid/script/form/
position、图片缺 alt、数字声明不匹配、HTML 与纯文本数字不一致。

警告项：图片过大或本地路径、正文 > 800 字、按类型缺少期望动作或时限、段落 > 4 行、感叹号/emoji。

数值与单位的一致性以 Spec 的 `facts` 为依据；日期分量不能支持费用等普通数字。
该检查不证明来源真实性，仍须对照用户材料。生成的结构编号不参与。远程图片大小无法测量，
会在 `skipped` 里注明，而不是当作通过。

## 模板库

模板是独立数据目录，可随时增删。默认根目录按以下顺序解析：

1. `--root`
2. `EMAIL_TEMPLATES_DIR`
3. 当前目录 `email-templates/`（项目专用）
4. 本 skill 的 `templates/`（个人常用）

两种模板：

| 类型 | 位置 | 输出 |
| --- | --- | --- |
| Spec 模板 | `<root>/<id>/v1/{template.yaml,vars.json,style.json,sample.html}` | HTML / 文本 / Markdown / .eml |
| HTML 模板 | `<root>/html/<name>.html` + 可选 `<name>.vars.json` | HTML / 文本 / .eml |

```sh
python3 <skill路径>/scripts/template.py list
python3 <skill路径>/scripts/template.py candidates spec.yaml
python3 <skill路径>/scripts/template.py save --spec spec.yaml --id <id> --name <名称> \
  --var '原值={{变量}}'
python3 <skill路径>/scripts/template.py apply <id> --vars vars.json

python3 <skill路径>/scripts/template.py add-html path/to/mail.html --id <name>
python3 <skill路径>/scripts/template.py apply html/<name> --set 'key=value'
```

- Spec 模板：缺必填变量直接报错，不默认填充；真实邮箱/电话与具体日期不允许入库。
- HTML 模板：入库及套用前同样检查固定日期/时间与邮箱/电话；放入文件即出现在 `list`；变量按纯文本做 HTML 转义；不输出 Markdown，
  不做数字声明一致性检查；宽度/alt/禁用构造仍会校验。
- 模板名称只存在于模板库，不写进 SKILL.md、references、脚本或测试。

详细规则见 [references/templates.md](references/templates.md)。

## 样式

四套预设：`business`、`report`、`plain`、`alert`，令牌在
[assets/styles/](assets/styles/)。可用 Spec 的 `style` 或 `--style-file` 覆盖颜色、宽度、
表格样式；调整只改令牌，不改内容。说明见 [references/styles.md](references/styles.md)。

## 目录

```text
email-composer/
├── SKILL.md
├── references/            # 类型、追问、写作、模块、样式、兼容、模板
├── assets/
│   ├── base.html
│   └── styles/            # 四套预设令牌
├── scripts/
│   ├── render.py          # Spec → HTML / 文本 / Markdown / .eml
│   ├── validate.py        # 兼容与声明一致性校验
│   ├── template.py        # 模板库 CLI
│   └── email_composer/    # 实现包
├── examples/              # 示例 Spec
└── templates/             # 个人模板库（可增删）
    └── html/              # 现成 HTML 扩展模板
```

## 验证

仓库内回归与结构检查：

```sh
python3 -m unittest discover -s tests/email-composer -v
python3 tools/skill-builder/scripts/validate_skill.py skills/email-composer
```

回归覆盖 YAML 子集、渲染、校验阻断项、模板入库门槛、HTML 模板与 CLI 退出码。
它不验证视觉呈现，也不代替 Outlook 实机预览。

## 限制

- 不发送邮件、不连接邮箱、不做群发营销或复杂网页。
- 远程图片大小与可访问性无法测量；本地图片在纯 HTML 中只能是路径引用。
- 原始 HTML 模板不做数字声明一致性检查，纯文本由 HTML 自动提取，结构保真度低于 Spec 模板。
- 校验只证明结构与规则，不证明内容正确；Outlook 用 Word 引擎，交付前需用户自测。
- 模板变量是字面值替换；同一原值出现多次会共用一个变量，需要区分时选更长的原值。
