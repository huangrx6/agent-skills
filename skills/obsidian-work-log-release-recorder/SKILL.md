---
name: obsidian-work-log-release-recorder
description: >-
  Use when the user asks to record completed coding, deployment, configuration, database or release work
  in Obsidian: 这次发布记一下、把刚才完成的改动沉淀到知识库、补本周发版文档。
  Capture verified changes, commands, validation and recovery details, updating a weekly release note only for release-relevant work.
  Do NOT use merely because a task finished, for speculative plans, weekly status reports, or editing/moving existing notes without new work facts (use obsidian-personal-knowledge-base).
---

# 已完成工作与发版记录

把有复用价值的已完成事实写成简短记录。记录请求不授权执行发布、SQL、git、插件配置或外部通知。
“已实现”“已验证”“已发布”是不同状态，不能相互替代。

## 准备与落点

依赖同级 `obsidian-personal-knowledge-base`（PKB）：共享路径解析、归位和写作规范，不另存一份 vault 规则。
先读其 [归位规则](../obsidian-personal-knowledge-base/references/vault-map.md) 与
[写作规范](../obsidian-personal-knowledge-base/references/writing-conventions.md)，再探查目标目录及最近的笔记/MOC。
缺少依赖时说明所缺文件；可先整理事实草稿，不猜目录写入 vault。

以下命令相对于本 skill 目录：

```sh
python3 ../obsidian-personal-knowledge-base/scripts/vault_path.py --explain
```

路径按 PKB 配置解析，也可向检查器传 `--vault PATH`。
优先更新拥有该主题的已有笔记；新记录选最窄稳定位置：有交付边界的项目进 Projects，
长期运维责任进 Areas，可复用方法进 Resources，未归类捕获进 Inbox。
不假定运维一定属于 Areas，也不从历史记忆恢复不存在的领域。

用户已指定确切新路径时可直接创建。落点确实不清且会建立新结构时再澄清。
结合当前工作上下文理解“记一下”；没有上下文的“把这周做的事记一下”才需区分周报与发版事实。
同时明确要求记录和整理时完成两者，不重复要求二选一。

## 事实筛选

保留未来执行、验证、回滚或交接真正需要的内容：

- 已改动的模块、接口、脚本、配置项、SQL、产物和版本，以及实际状态。
- 已执行命令的环境、结果和证据；未执行的发布命令单独标为待执行，不能写成执行记录。
- 验证方式、结果、跳过项及原因；已知前提、执行顺序、影响和恢复方法。
- 已确认且影响后续工作的决定；不复制所有改动文件、原始对话或未采纳的猜想。

敏感操作信息只记变量名和凭据位置，不记令牌、密码或连接串中的真实凭据。
用户未提供的发布人、时间、备份或回滚结果标为未知，不根据模板编造。

## 写入与验证

1. 从当前会话、用户材料或可核查产物整理事实，区分实现、验证、发布状态。
2. 更新已有主题笔记。涉及发布准备或发布变更时，查找同系统同 ISO 周的记录，已有就追加或合并，
   不涉及发布的本地实现/测试记录无需另建周发版笔记。
3. 默认名称为 `发版 - <系统或项目名> - YYYY-Www.md`；ISO 周年可能与日期的公历年不同。
   采用用户指定的发布周期；没有指定时用本次记录日期所属周，不推断历史发布日期。
4. 新建周发版笔记按 [模板](references/release-note-template.md)。附近已有稳定格式时沿用本地约定。
   长脚本可在“04 发布依赖清单”章节引用对应文件；这是章节名，不是要求新建目录。
5. 新长期记录补一个有用的父页/MOC 链接，更新 vault 内相关索引；不修改 skill 地图或计数器。
6. 默认模板笔记运行下列检查；本地自定义格式按其约定审阅，不为通过默认模板检查强制改写。

```sh
python3 scripts/check_release_note.py "<笔记路径>" --vault "<vault 路径>"
python3 ../obsidian-personal-knowledge-base/scripts/check_links.py --vault "<vault 路径>" --ignore-template
```

`check_release_note.py` 检查默认命名、真实 ISO 周/日期、H1、模板字段与章节、同目录重复周、
其他笔记中的 wikilink 引用，并提醒明显凭据赋值；不判断事实真实性或发布安全性。
未配置 vault 时会明确跳过引用检查，不能据此宣称完整验证。
链接检查的原有断链单独报告，不扩展任务删除无关链接。

返回实际新增/更新的笔记、记录的事实、周发版记录是否更新，以及验证结果和未提供的信息。
