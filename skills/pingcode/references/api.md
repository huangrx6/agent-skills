# 端点表：为什么路径不交给调用方，以及怎么加一个新接口

## 三层结构

```text
open.pingcode.com/api_data.json        ← 官方机读文档（594 条，含参数表 + 响应示例 + scope）
        │  dev-tools/gen_endpoints.py（联网，只在这一步需要网络）
        ▼
scripts/endpoints.py                   ← 生成物：470 条接口 + 来源 URL + 抓取时间 + 内容指纹
        │  scripts/api_index.py（手写：require / build / find / scopes）
        ▼
scripts/pingcode.py                    ← 类型化子命令；所有路径都过 require()
```

**数据与查询分开**：`endpoints.py` 会被整份重写，所以手写函数放不进去（会被冲掉，
而且「生成物里混着手写代码」最容易被误改）。

## 为什么值得这么做

参考实现（第三方那个 pingcode skill）把 `--path` 暴露给调用方，自己写死了
`/v1/project/work_items`、`/v1/project/work_item/types` 这类路径 —— 官方当前文档里
**根本不存在**（PJM 的前缀是 `/v1/pjm/`，而且 `workitems` 没有下划线）。它测试全绿的
原因是 mock 了 `urllib.request.urlopen`：路径错了也照样过一个假的 200。

所以这里：

- 路径来自生成表，`require()` 在**发送前**就报错，并给最接近的候选；
- `build()` 在占位符没填全、或参数名拼错时当场报错（不会拼出一个注定 404 的 URL）；
- `tests/test_endpoints.py` 里有两条契约测试：**本 skill 用到的每个端点必须在表里**，
  以及**上面那几条过期路径必须不存在**（把那次调研的结论钉成回归）。

## 自己查

```sh
python3 scripts/api_index.py --groups               # 有哪些分组、各多少个
python3 scripts/api_index.py --scopes               # 官方 54 个 scope
python3 scripts/api_index.py --list 工作项           # 按分组/名称/路径模糊找
python3 scripts/api_index.py --show GET /v1/pjm/workitems
python3 scripts/pingcode.py api --list 需求          # 同样的能力，从 CLI 里走
```

## 加一个类型化命令的步骤

1. 在生成表里找到端点：`api --list 关键词` 或 `api --show METHOD PATH`，记下分组与 scope。
2. 在 `scripts/pingcode.py` 里写处理函数，路径用 `_api.require(...)` 取、用 `_api.build(...)` 拼，
   **不要写字面路径**。
3. 需要「名字 → ID」就加进 `scripts/resolve.py` 的 `SOURCES` 表（那是字典类型的唯一一处定义）。
4. 在 `tests/test_endpoints.py` 的 `USED` 里加上这个端点（契约测试会守住它真实存在）。
5. 在 `tests/test_cli.py` 里加一条用例：**至少要断言 dry-run 不发请求**，以及 body 里的 id 是解析后的真 id。

## 文档漂移怎么发现

```sh
python3 dev-tools/gen_endpoints.py --check    # 有漂移退出 1，并逐条列出 增 / 删 / 改
python3 dev-tools/gen_endpoints.py            # 重新生成（联网）
python3 dev-tools/gen_endpoints.py --input 本地快照.json   # 离线也能跑
```

判据是**整份生成文件是否一致**（不是只比端点集合）—— 只比集合的话，改了表头、注释或
元信息会因为「端点没变」永远不落地，`--check` 也就发现不了。

官方文档改过的迹象：`SOURCE_SHA256` 变了。抓取时间与指纹都写在生成文件头部，
所以「这份表是什么时候、从哪来的」是可追溯的。

## 逃生口

剩下 ~460 个接口（测试管理 / 需求 / 工单 / 知识库 / DevOps / 交付 / 组织……）没有类型化命令，
用 `api` 走：

```sh
pingcode.py api --method GET --path /v1/pjm/workitem_priorities --param project_id=xxx
pingcode.py api --method POST --path /v1/comments --data '{...}'
```

路径不在官方表里会被拦下并给候选；确认要用加 `--force`。**逃生口不猜参数名**——
它只校验路径；参数写错由服务端返回 400，CLI 会把 `{code, message}` 翻出来。

## 已知边界

- 生成表只收「接口」条目：官方 JSON 里那 124 条纯文档页（没有 method/url）不进表。
- **生成表不带请求体 schema**：`normalize()` 只取 `type/url/scopes/permission/group/name`，
  把 `header` 与 `parameter` 两节整块丢了。后果不是“没信息”，而是**误判成“没信息”** ——
  曾经据此把附件上传写成「multipart 字段名没法从文档确认」，而官方文档里一直写着。
  要字段名时直接查快照的 `parameter.fields`（分「查询参数」「请求参数」「请求参数 form-data」）。
- 同一路径不同变体的接口（`/v1/auth/token` 的三个 `grant_type`）靠 `query=` 消歧，
  `require` 在没给 query 时会报歧义并列出变体。
- 官方文档**不保证**等于线上行为。文档里有示例的字段以示例为准；没有示例的一律当未实测，
  真实调用前不要当成已知（见 README 的「已知限制」）。

## 附件上传的契约（从官方文档抄出来的，不是猜的）

两个端点名字很像，但**一个是 multipart、一个是 JSON**：

| | `POST /v1/attachments`（代码段） | `POST /v1/attachments?principal_type=&principal_id=[&comment_id=]`（文件） |
| --- | --- | --- |
| Content-Type | `application/json` | **`multipart/form-data`**（文档写成必填 header） |
| 正文 | `principal_type` `principal_id` `title` `format` `content`（均必填）+ `comment_id`（选） | **form-data：`title` + `file`**（均必填） |
| `principal_type` 取值 | `workitem` / `workitem_review` / `workitem_deliverable` / `testcase` / `testcase_review` / `testrun` / `idea` / `idea_review` / `ticket` / `page` | 同左 |
| 作用域 | 随主体（如 `workitem` 要 `pcp:write:pjm:workitem`） | 同左 |

响应两边一样：`{id, url, title, size, type, file_type, ext, download_url, created_at, created_by}`。
往某条评论的附件上传时多传一个 `comment_id`（两种都适用）。
