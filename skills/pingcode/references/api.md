# 端点与请求契约

```text
官方 https://open.pingcode.com/api_data.json
  → dev-tools/gen_endpoints.py
  → scripts/endpoints.py（生成数据、来源时间、SHA256）
  → scripts/api_index.py（require/build/find/scopes）
  → scripts/pingcode.py（类型化命令）
```

不要手改生成表。端点是否存在、方法、scope 和令牌要求以快照为准；请求字段需查官方 JSON 的
`parameter.fields`（查询、JSON、form-data），响应参考 `success.examples`。
生成表不保存完整 body schema，也不能替代租户权限、流程及服务端校验。

```sh
python3 scripts/api_index.py --groups
python3 scripts/api_index.py --scopes
python3 scripts/pingcode.py api --list 工作项
python3 scripts/pingcode.py api --show GET /v1/pjm/workitems
python3 dev-tools/gen_endpoints.py --check
python3 dev-tools/gen_endpoints.py --input /path/to/api_data.json
```

这些路径相对本 skill。`--check` 比对完整生成内容，复用已有抓取日期以免每日误报；
无 `--input` 时抓取官方文档，加 `--input` 可离线运行。

新增类型化命令时：查证端点与字段，用 `require()` 取契约、`build()` 填占位符，
需要字典解析时复用 `resolve.py`。补充端点契约测试和行为测试：dry-run 不发写请求、
目标 ID 正确、失败不谎报成功。测试中的 `USED` 清单用于验证已使用的端点。

## 通用 API

```sh
python3 scripts/pingcode.py api --method GET --path /v1/pjm/workitem/priorities --param project_id=xxx
python3 scripts/pingcode.py api --method GET --path '/v1/pjm/workitems/{workitem_id}' --param workitem_id=xxx
```

`--param` 填路径占位符，也可能作为查询参数发送；`--data` 提供 JSON body。
同一路径存在多个变体时按查询参数消歧，例：授权端点的 `grant_type`、附件的主体参数。
`--force` 只绕过“端点不在快照”检查；只有先查证官方契约、且属于已授权任务时才使用。
不要借通用接口扩大到 skill 范围外的管理操作。

## 附件

| 类型 | 端点与内容 |
| --- | --- |
| 文件 | `POST /v1/attachments?principal_type=workitem&principal_id=…`；multipart `title` + `file` |
| 代码段 | `POST /v1/attachments`；JSON `principal_type`、`principal_id`、`title`、`format`、`content`、`comment_id` |
| 删除 | `DELETE /v1/attachments/{attachment_id}`；带主体查询参数，有评论归属时带 `comment_id` |

文件上传到已有评论时也带 `comment_id`。代码段在历史租户验证中缺少该字段会返回
400/code=100039，因此当前 CLI 要求它。不要为了上传代码段擅自发布新评论；应先使用已授权的评论。
上传、删除走类型化命令时会解析主体工作项，并要求删除使用 `--yes`。
