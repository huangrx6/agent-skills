# pingcode

PingCode 项目与工作项 CLI，端点表来自官方 **REST API V2**（2026-10-14 快照）。
Agent 操作规则见 [SKILL.md](SKILL.md)，完整参数见 [命令参考](references/commands.md)，
需求拆分、描述模板和截图附件流程见 [需求录入](references/workitem-authoring.md)。
依赖 Python 3.10+，仅用标准库。

## 配置

按照 [授权与配置](references/auth.md) 设置应用凭据和 scope。
默认配置在 `~/.agent-skills/config/pingcode/`，可用 `PINGCODE_CONFIG_DIR` 单独指定，
或用 `AGENT_SKILLS_CONFIG_DIR` 指定共享配置根。新目录不存在时兼容沿用旧 `~/.config/pingcode/`。
令牌与程序生成的配置采用 0600 原子写；用户手填凭据文件也应设为 0600。

从本仓库根目录运行：

```sh
python3 skills/pingcode/scripts/pingcode.py auth login
python3 skills/pingcode/scripts/pingcode.py auth status
python3 skills/pingcode/scripts/pingcode.py workitem mine --open-only
python3 skills/pingcode/scripts/pingcode.py workitem show SCR-12
python3 skills/pingcode/scripts/pingcode.py workitem history SCR-12
python3 skills/pingcode/scripts/pingcode.py workitem relations SCR-12
python3 skills/pingcode/scripts/pingcode.py workitem participants SCR-12
python3 skills/pingcode/scripts/pingcode.py project members --project X
python3 skills/pingcode/scripts/pingcode.py list boards --project X
python3 skills/pingcode/scripts/pingcode.py board create --project X --name 测试看板 --dry-run
python3 skills/pingcode/scripts/pingcode.py workitem tags SCR-12
python3 skills/pingcode/scripts/pingcode.py tag create --project X --name 后端 --dry-run
python3 skills/pingcode/scripts/pingcode.py worklog list SCR-12
python3 skills/pingcode/scripts/pingcode.py worklog update <id> --duration 3
python3 skills/pingcode/scripts/pingcode.py sprint create --project X --name 'Sprint 13' --start 2026-09-01 --end 2026-09-14 --dry-run
python3 skills/pingcode/scripts/pingcode.py workitem create --project X --type bug --title '登录失败' --dry-run
python3 skills/pingcode/scripts/pingcode.py workitem fill-dates --project X
python3 skills/pingcode/scripts/pingcode.py workitem create --project X --type task \
  --title '待分配任务' --unassigned --dry-run
```

环境访问令牌优先于本地缓存令牌；其模式默认未知，可用 `PINGCODE_AUTH_MODE` 显式标记。
`--full` 输出业务响应；诊断凭据仍用状态命令，不要输出 secret/token。

## 验证与维护

```sh
python3 -m unittest discover -s tests/pingcode -v
python3 skills/pingcode/dev-tools/gen_endpoints.py --check
python3 skills/pingcode/dev-tools/run_evals.py --check
python3 skills/pingcode/dev-tools/run_evals.py --dry-run --agent-cmd 'pi -p {prompt}'
# 有官方 JSON 快照时可离线比对
python3 skills/pingcode/dev-tools/gen_endpoints.py --check --input /path/to/api_data.json
```

单元测试使用临时配置与模拟传输，不访问真实租户。生成器的无 `--input` 模式访问官方公开文档，
`--check` 只比对、不改文件。端点表记录来源与快照指纹，不证明当前服务端接受每个参数；
新增接口应对照官方请求参数表，并在获授权后做实际验证。

## 验证状态

- 2026-09-13 在真实租户（企业令牌）跑过 V1 只读 + 写全链路：项目/字典/进度、建树、建缺陷、
  改描述与截止、改状态、评论、附件、删除。
- 2026-10-22 按官方 **V2** 文档重新生成端点表并迁移字段；单元测试覆盖 V2 编号、日期、
  `properties`、批量接口与项目 `template_type`。
- 2026-10-22 在真实租户跑过 V2 核心链路：令牌刷新 / `whoami`、项目列表/详情/进度、
  字典、工作项 list/show/mine/search、创建任务与用户故事、更新故事点、改状态、
  批量改标题、附件上传/列表/删除、删除与软删除确认。两条一次性测试数据已删除。
- 实测发现：**任务类型没有 `story_points` 属性**，V2 更新会返回 400 `code=100355`。
  CLI 现在先查 `workitem_properties`，不支持的属性当场拒绝，不再发必 400 的请求。
- 尚未实测：项目创建/更新的真实写（只做过 dry-run）、代码段附件（需要先有评论）、
  批量改状态的实写（只做过 dry-run）、评论创建（避免未经要求的外发）、
  `mine --type` 有匹配数据的本地过滤、私有部署。
- 详细清单见 `docs/plans/pingcode-api-v2-migration.md`。

已封装项目、工作项、结构化搜索、树形创建、单字段批量更新、评论与附件。
当前端点表无项目删除接口；成员/权限/部门/CI 管理不在 skill 的操作范围。
状态名、父子类型关系、流程权限与私有部署行为由具体租户决定。
