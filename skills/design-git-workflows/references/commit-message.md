# Conventional Commits 提交信息

## 格式

```text
<type>[可选 scope][可选 !]: <简短描述>

[可选正文]

[可选 footer]
```

示例：

```text
feat(orders): add bulk export endpoint

支持按日期范围批量导出订单为 CSV。导出任务异步执行，
完成后通知用户。

BREAKING CHANGE: 移除了 /api/v1/orders/export（同步），
改用 /api/v2/orders/export（异步任务）。
```

## type 语义

| type | 用途 | SemVer 影响 |
| --- | --- | --- |
| `feat` | 新功能（面向用户的能力） | MINOR |
| `fix` | bug 修复（修正错误行为） | PATCH |
| `docs` | 文档变更 | 无 |
| `style` | 格式/空白/分号（不改逻辑） | 无 |
| `refactor` | 重构（不改外部行为） | 无 |
| `perf` | 性能优化 | PATCH |
| `test` | 测试新增/修改 | 无 |
| `build` | 构建系统/依赖 | 无 |
| `ci` | CI 配置 | 无 |
| `chore` | 杂项（不属上述） | 无 |
| `revert` | 撤销之前的 commit | 依被撤销项 |

- `feat` 仅用于新增面向用户的能力；内部重构不算 feat；
- `fix` 仅用于修正错误行为；新发现的"应该加但没加"不算 fix；
- `BREAKING CHANGE` 或 type 后加 `!` 表示不兼容变更（MAJOR）。

## scope

scope 表示影响的代码区域，可选：

```text
feat(auth): add OAuth2 login
fix(parser): handle empty input
docs(readme): update install steps
```

- 选稳定代码区域名（模块/包/服务名）；
- 不确定的不要硬写 scope；
- scope 用小写连字符（`react-client`、`order-service`）。

## 描述（subject）

- 英文现在时祈使语气：`add`（不是 `added`/`adds`）；
- 首字母小写（除专有名词）；
- 结尾不加句号；
- 不超 50 字符（正文换行说明细节）；
- 不写工单号、作者署名、Agent 行为声明；
- 不写"添加了""我们"，不写未验证成果。

正文：
- 解释"为什么"（what/why），不重复 diff（how）；
- 每行 ≤ 72 字符；
- 说明迁移上下文、非显而易见的后果。

footer：
- `BREAKING CHANGE: <说明 + 迁移路径>`；
- 引用 issue：`Closes #123`、`Refs #456`；
- 只有真实证据时才写 footer。

## 自动归类信号

自动化场景根据变更识别 type：

| 信号 | 推断 type |
| --- | --- |
| 新文件在 `views/components/api/pages/routers` | `feat` |
| diff 含 fix/bug/crash 关键字且非新增 | `fix` |
| 仅 `.md` | `docs` |
| 仅 `*.test.*`/`tests/`/`__tests__/` | `test` |
| 重命名/移动/提取 | `refactor` |
| perf/cache/memoize 关键字 | `perf` |
| `.github/**`/`.gitlab-ci.yml`/`Jenkinsfile` | `ci` |
| 仅格式/注释/lint | `style` |
| 其它 | `chore` |

## 撰写禁忌

- 不夸大：`feat: 完美支持所有场景` → `feat: support CSV export`；
- 不含密钥/内部地址；
- 不把多个无关改动塞进一个 commit；
- 不写无意义 commit：`fix: update`、`wip`、`asdf`；
- 不在共享分支写 "Squash later"。

## 撰写来源

以项目 `CONTRIBUTING.md` / commitlint 配置为优先；本规范是 Conventional Commits 1.0.0 的落地约定，项目可按需收紧。
