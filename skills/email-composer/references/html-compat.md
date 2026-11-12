# HTML 兼容与交付格式

邮件客户端不是浏览器。Outlook 桌面端用 Word 渲染引擎，Gmail 会重写部分样式。
规则只有一条：用最保守的 HTML，让内容在所有客户端都能读。

## 布局

- 宽度 600–640px；`business` / `report` / `alert` 用 640，`plain` 用 600。
- 单列。不用多列分栏、不用浮动、不用响应式断点。
- 外层布局用 `<table role="presentation">`，`cellpadding="0" cellspacing="0" border="0"`。
- 数据表格不用 `role="presentation"`，保留表头语义。
- 内容区宽度 = 总宽 − 左右内边距；图片按内容区宽度输出。

## 样式

- 所有样式内联；不使用 `<style>` 块、CSS 变量、外部样式表。
- 禁用：`flex`、`grid`、`position`、`float`、`<script>`、`<form>`、`javascript:` 链接。
- 字号 14px，行高 1.7；标题 20px，小节标题 16px；表格 13px。
- 字体回退链：`"Microsoft YaHei", "微软雅黑", "PingFang SC", Arial, sans-serif`。
- 按钮用带背景色的单元格 + 链接实现，不用 `<button>`。
- 链接写完整 URL；`href` 与可见文字都要可读。
- 显式设置背景色（页面、卡片、表格、按钮），避免深色模式反转后文字不可读。

## 图片

- 每张图必须有 `width` 与 `alt`；`alt` 为空是阻断项。
- 图片总大小超过 1 MB 给警告；远程图片大小无法测量，报告里会标「未测量」。
- HTML 里引用本地路径只在作者机器上有效；发送前要上传，或改用 `.eml` 内嵌。
- `.eml` 会把本地图片转成 `cid:` 内嵌，远程图片保持原 URL。

## 纯文本版

- 主题用 `【主题】` 开头。
- 标题用【】或序号；表格转成「首列 + 字段：值」，待办转成「事项 + 负责人 + 截止」。
- 链接单独成行，不嵌在句子中间。
- 不输出 HTML 标签；图片用 `[图片] 图注` + URL。

## Markdown 版

- 保留结构：`#` 主题、`##` 小节、管道表格、`-` 列表、`![alt](src)` 图片。
- 用于二次编辑与版本管理，不要求像素还原。
- 摘要用 `>` 引用；签名用 `--` 分隔。

## .eml

- 结构：有本地图片时 `multipart/related`，否则 `multipart/alternative`。
- 正文同时包含 `text/plain` 与 `text/html`；Outlook / Foxmail 可直接打开。
- 本地图片按 `cid:imgN@email-composer` 内嵌，带 `Content-ID` 与 `inline` 文件名。
- 头信息包含 `Subject`、`To`、`Cc`、`Date`、`MIME-Version`；中文头由标准库编码。
- 不写 `From`；由邮件客户端补。
- `.eml` 只作为草稿，不代替真实发送测试。

## 兼容边界

沙箱或浏览器里的预览不能代表 Outlook。Outlook 使用 Word 引擎，可能：

- 忽略 `border-radius`、`max-width`；
- 对表格单元格的内边距处理不同；
- 对深色模式与图片做额外处理；
- 把过宽的表格撑出阅读区。

交付时提醒用户：先给自己发一封测试邮件，在 Outlook 里看一眼，再发给收件人。
这一步不能由静态校验代替。

## 校验对应

| 规则 | 阻断/警告 |
| --- | --- |
| 宽度 > 640 | 阻断 `html_width` |
| flex / grid / script / form / position / javascript: | 阻断 `html_forbidden` |
| 图片缺 alt | 阻断 `image_alt` |
| 正文仍有 `【待填】` | 阻断 `placeholder` |
| 正文仍有 `{{变量}}` | 阻断 `unfilled_variable` |
| 图片总大小 > 1 MB | 警告 `image_size` |
| 本地图片按路径引用 | 警告 `image_local_path` |
| 正文 > 800 字 | 警告 `body_long` |
| 需要对方行动的类型缺动作 / 时限 | 警告 `no_action` / `no_deadline` |
| 段落 > 4 行 | 警告 `long_paragraph` |
| 感叹号 / emoji | 警告 `exclamation` / `emoji` |

原始 HTML 模板同样受这些 HTML 规则约束；它不做数字声明一致性检查，也不输出 Markdown。
