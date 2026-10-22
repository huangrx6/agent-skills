# pingcode

PingCode 项目与工作项 CLI，端点表来自官方 **REST API V2**（2026-10-14 快照）。
Agent 操作规则见 [SKILL.md](SKILL.md)，完整参数见 [命令参考](references/commands.md)。
依赖 Python 3.10+，仅用标准库。

## 配置

按照 [授权与配置](references/auth.md) 设置应用凭据和 scope。
默认配置在 `~/.config/agent-skills/pingcode/`，可用 `PINGCODE_CONFIG_DIR` 单独指定，
或用 `AGENT_SKILLS_CONFIG_DIR` 指定共享配置根。新目录不存在时兼容沿用旧 `~/.config/pingcode/`。
令牌与程序生成的配置采用 0600 原子写；用户手填凭据文件也应设为 0600。

从本仓库根目录运行：

```sh
python3 skills/pingcode/scripts/pingcode.py auth login
python3 skills/pingcode/scripts/pingcode.py auth status
python3 skills/pingcode/scripts/pingcode.py workitem mine --open-only
python3 skills/pingcode/scripts/pingcode.py workitem show SCR-12
python3 skills/pingcode/scripts/pingcode.py workitem create --project X --type bug --title '登录失败' --dry-run
```

环境访问令牌优先于本地缓存令牌；其模式默认未知，可用 `PINGCODE_AUTH_MODE` 显式标记。
`--full` 输出业务响应；诊断凭据仍用状态命令，不要输出 secret/token。

## 验证与维护

```sh
python3 -m unittest discover -s tests/pingcode -v
python3 skills/pingcode/dev-tools/gen_endpoints.py --check
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
- **V2 尚未在真实租户复核**：`identifier` 查询是数字还是完整编号、`with_time` 是否必填、
  `properties.story_points` 是否可写、附件代码段是否仍强制 `comment_id`，都需要在获授权后
  用只读命令和一条可丢弃的测试数据验证。详细清单见 `docs/plans/pingcode-api-v2-migration.md`。

已封装项目、工作项、结构化搜索、树形创建、单字段批量更新、评论与附件。
当前端点表无项目删除接口；成员/权限/部门/CI 管理不在 skill 的操作范围。
状态名、父子类型关系、流程权限与私有部署行为由具体租户决定。
