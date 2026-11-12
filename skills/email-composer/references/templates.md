# 模板库与扩展

模板是可选的复用资产，不属于 skill 的核心代码。目录可以随时增删；**模板名称只存在于
模板库自身**，不写进 SKILL.md、references、脚本或测试。

模板库支持两种类型：

| 类型 | 存放 | 适用 | 输出 |
| --- | --- | --- | --- |
| Spec 模板 | `<root>/<id>/vN/` | 结构固定、需要三格式与数字校验 | HTML / 纯文本 / Markdown / .eml |
| HTML 模板 | `<root>/html/*.html` | 已有设计好的 HTML，只换文字与图片 | HTML / 纯文本 / .eml |

## 目录位置

优先级：

1. `--root <dir>`
2. 环境变量 `EMAIL_TEMPLATES_DIR`
3. 当前工作目录的 `email-templates/`（项目专用模板）
4. skill 自带的 `templates/`（个人常用模板）

默认输出目录是当前工作目录的 `email-out/`，可用 `--outdir` 修改。
`template.py list` 的 JSON 里会返回实际使用的 `root`。

## Spec 模板

### 目录结构

```text
<root>/
├── index.json
└── <id>/
    ├── README.md
    └── v1/
        ├── template.yaml     # 内容 Spec，变量写 {{name}}
        ├── vars.json         # 变量定义
        ├── style.json       # 预设与覆盖
        └── sample.html      # 用示例值渲染的样例
```

`index.json` 记录 `id`、名称、类型、场景、当前版本、历史版本、更新时间与归档状态。
版本只增不改：更新生成 `v2`、`v3`，旧版本保留。

### 变量

`template.yaml` 是完整 Spec，只是把会变的值写成 `{{name}}`：

```yaml
subject: 【申请】{{project}} 上线（{{release_time}}）
facts:
  - "{{release_time}}"
```

`vars.json`：

```json
{
  "version": 1,
  "vars": {
    "project": {"required": true, "description": "项目名", "example": "客户门户"},
    "release_time": {
      "required": false,
      "description": "发布窗口",
      "example": "2026-11-20 20:00",
      "default": "2026-11-20 20:00"
    }
  }
}
```

- `required: true` 缺值直接报错，不默认填充。
- `required: false` 缺值时用 `default`；没有 default 就用空字符串。
- `example` 只用于生成 `sample.html` 与文档，不参与套用。
- 变量名只允许字母、数字、下划线，且以字母或下划线开头。
- 字面替换：同一个原值出现多次会共用一个变量；需要区分时选更长的原值。

### 命令

```sh
# 列出候选变量（日期、时间、数字、链接、重复文本、表格行、称呼、签名）
python3 <skill路径>/scripts/template.py candidates spec.yaml

# 存为新模板；--var 的原值必须真实出现在 Spec 里
python3 <skill路径>/scripts/template.py save --spec spec.yaml \
  --id approval-release --name 上线申请 --scene release \
  --var '2026-11-20 20:00={{release_time}}' \
  --var '客户门户={{project}}'

# 套用
python3 <skill路径>/scripts/template.py apply approval-release \
  --vars vars.json --outdir ./email-out

# 更新为下一个版本
python3 <skill路径>/scripts/template.py update --id approval-release \
  --spec spec.yaml --note 补充回滚条件 --var '...'

# 查看、归档、恢复、删除
python3 <skill路径>/scripts/template.py list --type approval
python3 <skill路径>/scripts/template.py show approval-release
python3 <skill路径>/scripts/template.py archive approval-release
python3 <skill路径>/scripts/template.py restore approval-release
python3 <skill路径>/scripts/template.py remove approval-release --yes
```

`--var` 的变量名可以写 `name` 或 `{{name}}`；`--optvar` 声明选填变量，
其原值作为默认值。`--describe name=说明` 可补充变量说明。

### 入库门槛

- 变量声明齐全，模板正文没有残留的具体日期或时间。
- 真实邮箱、电话必须改成变量；正文、变量示例和默认值存到就拒绝入库。
  先在源 Spec 中脱敏，再存模板，避免变量 example 保留真实联系方式。
- 样例能用示例值渲染，且校验无阻断项。
- 数字仍留在模板里只给警告：固定阈值（如「24 小时」）可能是有意的。
- 收件人 `to` / `cc` 不写入模板；套用时再指定。

### 套用规则

- 缺必填变量 → 退出码 2，列出缺失项，不写文件。
- 变量未声明 / 多传变量 → 退出码 2。
- 渲染后校验有阻断项 → 退出码 1，不写文件。
- 通过后输出 HTML、纯文本、Markdown（可加 `.eml`），并返回校验报告。

## HTML 模板（扩展）

现成 HTML 模板放在 `<root>/html/`，不需要改索引；放入文件即出现在 `list` 里，
删除文件即移除。适合保留已有版式的邮件，只替换文字与图片。

### 目录结构

```text
<root>/html/
├── <name>.html        # 模板，变量写 {{name}}
└── <name>.vars.json   # 可选：名称、类型、说明、变量定义
```

- 文件名去掉 `.html` 就是模板 id，命令里写 `html/<name>`。
- `name` 可以重命名文件来改；不需要修改任何 skill 文件。
- sidecar 的 `name` 字段是展示名，`type` / `scene` 用于筛选，`description` 用于说明。
- 没有 sidecar 时，脚本按 HTML 里的 `{{name}}` 自动声明必填变量。

### 变量与 sidecar

```json
{
  "version": 1,
  "name": "排班通知",
  "type": "notice",
  "scene": "support",
  "description": "发布窗口值守安排",
  "vars": {
    "owner": {"required": true, "description": "负责人", "example": "张工"},
    "period": {"required": false, "description": "时段", "example": "20:00–22:00", "default": "20:00–22:00"}
  }
}
```

- 变量值按纯文本处理，会做 HTML 转义；需要插入 HTML 片段时直接改模板。
- 变量名只允许字母、数字、下划线，且以字母或下划线开头。
- 模板里的 `【待填：xxx】` 不是变量，套用时会被当作未处理占位阻断；其他 `【...】` 会给警告，提示可能还有未转换的字段。
- 新增或修改占位符后，要同步 sidecar；脚本发现 HTML 有未声明变量会报错。

### 命令

```sh
# 把现成 HTML 复制进模板库；自动扫描 {{变量}}，生成或补齐 sidecar
python3 <skill路径>/scripts/template.py add-html path/to/mail.html --id support-plan

# 列出与查看
python3 <skill路径>/scripts/template.py list
python3 <skill路径>/scripts/template.py show html/support-plan

# 套用：HTML 模板默认输出 html + text；需要 .eml 时显式加
python3 <skill路径>/scripts/template.py apply html/support-plan \
  --vars vars.json --outdir ./email-out

# 删除（HTML 与 sidecar 一起删除，不可恢复）
python3 <skill路径>/scripts/template.py remove html/support-plan --yes
```

- `add-html` 在写入前检查固定日期/时间及邮箱/电话，未参数化则拒绝；
  `apply` 对源模板重新检查，直接复制入库也不能绕过。sidecar 不得含真实邮箱/电话。
- `add-html` 不改写 HTML 内容；`--force` 覆盖同名 HTML，保留已有 sidecar。
- `apply` 的默认输出是 HTML + 纯文本；加 `--formats html,text,eml` 可生成 `.eml`。
- HTML 模板不支持 Markdown（没有结构化内容模型）；显式要求会报错。
- `archive` / `restore` 只适用于 Spec 模板；HTML 模板直接移出目录或 `remove`。
- `--subject` 可覆盖主题；不指定时取 HTML 的 `<title>`，再退回文件名。

### 校验范围

- HTML 宽度 ≤ 640、禁用构造、图片 alt、未填占位/变量：阻断。
- 正文长度、期望动作、时限、感叹号/emoji：警告。
- **不做数字声明一致性检查**：HTML 模板没有 `facts` 模型，报告里会标「未测量」。
- 不做 HTML 与纯文本的一致性对比；纯文本由 HTML 自动提取，仅作阅读备份。

### 兼容要求

HTML 模板必须满足 [html-compat.md](html-compat.md) 的规则：内联样式、表格布局、
不用 flex/grid/position/script/form、显式背景色、图片带 alt。`add-html` 会报告
宽度超限、缺 alt 与禁用构造；套用时这些是阻断项。

## 模板的取舍

- 结构会变、需要 Markdown 源稿或数值与单位的一致性检查 → 用 Spec 模板。
- 版式已定、只想换文字/图片、来源是现成 HTML → 用 HTML 模板。
- 两者都不把模板名称写进 skill 的文档或代码；模板库是独立的数据目录。
- 模板里的示例人名、日期、图片地址应是占位示例，不放真实个人信息。
