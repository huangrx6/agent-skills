# 初始化与分享知识库

`obsidian-wiki` 的代码和 Obsidian vault 是两件事：

- **skill 仓库**保存规则、脚本、参考资料和角色素材，可以通过 Git、`npx skills add` 或其他安装器分享。
- **vault 仓库**保存个人笔记、附件和 `.obsidian` 配置，由每个使用者自己创建、选择是否用 Git 管理。

不要把真实 vault 路径、`~/.agent-skills/config/obsidian-vault-path` 或个人笔记写进 skill 仓库。

## 从空目录开始

目标路径必须由用户明确给出；skill 不猜测应该在哪个目录创建知识库。

```sh
python3 scripts/init_vault.py "/path/to/学习 Wiki" --git --configure
```

脚本会：

1. 创建缺失的 PARA 目录、各区域入口、系统首页和附件目录；
2. 创建 `AGENTS.md` 作为所有 Agent 的统一规则，`VAULT.md` 记录目录地图和知识生命周期；
3. 创建 vault 自己的 `README.md` 和最小 `.gitignore`；
4. `--git` 只在目标目录没有 Git 仓库、且不在上级仓库内时运行 `git init`；
5. `--configure` 把路径写入当前用户配置。已有其他 vault 配置时会停止并保留原文件；
6. 只写缺失文件。重复运行是安全的，已有笔记和 `.obsidian/` 不会被覆盖。

脚本不安装 Obsidian、不安装插件、不上传笔记、不创建远端、不自动提交或推送。

## 交给别人使用

分享者需要分别分享两部分：

1. **skill**：让对方安装本 skill，例如从 skill 仓库按其 Agent 的安装方式安装；
2. **vault**：把初始化后的 vault 推到对方可访问的 Git 远端，或直接交付一个目录压缩包。

接收者在自己的机器上：

```sh
git clone <vault-repository> "/absolute/path/学习 Wiki"
python3 "/path/to/obsidian-wiki/scripts/init_vault.py" "/absolute/path/学习 Wiki" --configure
```

每个使用者设置自己的路径；配置文件不是共享协议，Git 也不会同步它。

交给别人前运行：

```sh
python3 scripts/health_check.py --vault "/path/to/学习 Wiki" --strict
```

`--strict` 检查初始化结构、失效双链和配置路径，不判断笔记内容是否适合公开。

## 共享边界

笔记和附件是否适合共享由 vault 所有人决定。`.obsidian/workspace*.json`、缓存和系统回收站默认忽略，但插件配置可能包含机器路径或账号信息，提交前应检查。skill 只负责初始化和结构检查，不替用户判断内容是否应公开。
