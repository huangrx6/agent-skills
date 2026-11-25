# ui-qa-acceptance · 黑盒交互验收与 UI 质检

> 面向 Web、SPA 与桌面 Electron/WebView 渲染页面的旗舰级黑盒交互验收流程：本地多服务安全启停、先侦察后操作、7 维度高压验收矩阵、DOM/几何客观巡检脚本、桌面 CDP 隔离验收与证据化缺陷报告模板。

| 适合 | 产物 | 依赖 |
| --- | --- | --- |
| 发版前黑盒复测、切页与关闭状态复位检查、高数量与窄/矮窗压测、键盘焦点与手势中断检查、Electron CDP 实测、Console/Network 洁净度核查 | 验收总结论 · AC 核对表 · 7 维度压测摘要 · 分级缺陷单与硬证据 · 未验证风险声明 | Python 3.10+（`scripts/with_server.py`）；页面实测依赖 Playwright 或环境可用的浏览器/CDP DevTools 能力 |

Agent 的四条验收铁律、决策树与主流程见 [SKILL.md](SKILL.md)，6 份高密度参考资料按其中的一层直链按需加载。

## 快速使用

在仓库根目录通过 `scripts/with_server.py` 托管本地待测服务并运行黑盒验收脚本（单服务、前后端多服务及 HTTP 健康路径探测均开箱即用）：

```sh
# 1. 查看参数说明
python3 skills/ui-qa-acceptance/scripts/with_server.py --help

# 2. 单服务 + HTTP 就绪探测
python3 skills/ui-qa-acceptance/scripts/with_server.py \
  --server "pnpm run dev" --port 5173 --path / \
  -- python3 path/to/qa_check.py

# 3. 前后端双服务（先后端、后前端，结束自动回收全部进程组）
python3 skills/ui-qa-acceptance/scripts/with_server.py \
  --server "python3 backend/server.py" --port 3000 \
  --server "pnpm --dir web dev" --port 5173 \
  -- python3 path/to/verify_flow.py
```

典型对话请求：
- 「帮我按真实用户路径把刚改好的设置页和扩展选择器黑盒复测一遍，输出带证据的验收报告。」
- 「启动本地前后端服务，重点压测 30+ 列表项、窄/矮窗口、切页返回复位和纯键盘 Esc 焦点归还，并汇总 Console/Network 报错。」
- 「用独立临时用户数据目录拉起 Electron 本地 CDP 端口，核查深浅色切换、弹窗过渡点击和 DOM 几何溢出。」

## 目录结构

- [SKILL.md](SKILL.md)：黑盒验收四条铁律、环境决策树、`scripts/with_server.py` 命令表、先侦察后操作闸门、7 维度摘要与参考直链
- [references/server-and-reconnaissance.md](references/server-and-reconnaissance.md)：环境决策树、`scripts/with_server.py` 单/多服务与 `--path` 探活、动态渲染稳定等待、语义定位器优先级与自动化误判陷阱
- [references/qa-stress-matrix.md](references/qa-stress-matrix.md)：7 维度高压验收详单（每维度含具体测试载荷、操作步骤与量化通过/失败判据）
- [references/dom-and-geometry-checks.md](references/dom-and-geometry-checks.md)：可直接在 DevTools / Playwright `evaluate` 运行的横向溢出、元素裁切、粘性栏遮挡、焦点归还、坏图/字体与 `prefers-reduced-motion`/CLS 扫描脚本
- [references/electron-and-spa-qa.md](references/electron-and-spa-qa.md)：桌面 Electron/WebView 本地 CDP 验收、独立 `USER_DATA` 目录隔离卫生、SPA 水合与弹窗过渡期点击陷阱、明暗双主题切换残留核查
- [references/evidence-and-bug-reporting.md](references/evidence-and-bug-reporting.md)：验证前四步门控与红旗词禁令、硬证据采集标准、Blocker/High/Medium/Low 分级量表、完整验收报告模板与 3 条真实缺陷单示范
- [references/automation-script-patterns.md](references/automation-script-patterns.md)：Console/PageError/Network 监听采集、页面元素自动侦察、静态 HTML 与动态 SPA 自动化验收脚本模板与安全清理
- `scripts/with_server.py`：跨平台单/多服务启停与 TCP/HTTP 就绪检查脚本（零第三方依赖）
- `evals/triggers.json` 与 `evals/evals.json`：触发边界与行为评判样例

## 能力边界

- 本 skill 专注**真实渲染态黑盒交互验收与证据交付**，不替代单元测试与 TDD（归 `tdd-testing`）、纯静态视觉审美评审（归 `ui-design-craft`）、前端业务源码修改（归 `frontend-engineering`）或产品 AC 起草（归 `product-spec`）。
- 无法启动浏览器、缺少账号/外部令牌或目标平台无 CDP 暴露时，必须将对应项如实标为「未验证（原因）」，绝不凭读代码猜测结论。

## 来源与整合说明

- **主要引用来源**：多服务协调与「静默侦察页面状态先于自动化操作」的工作流主要借鉴自 [`anthropics/skills`](https://github.com/anthropics/skills)（按其各技能目录 `LICENSE.txt` 条款）的 `webapp-testing`，审阅与极端情况压测视角借鉴自 [`pbakaus/impeccable`](https://github.com/pbakaus/impeccable)（Apache License 2.0）的极值加固与检查思路，交付实证标准对齐 [`obra/superpowers`](https://github.com/obra/superpowers)（MIT License）的完成前验证规范。
- **整合与调整要点**：
  1. **自研 Python 3.10+ 进程组服务托管器**：用纯标准库实现的 `scripts/with_server.py` 替代示例脚本，支持多前端/后端命令编排、可选 `--path` HTTP 就绪探测（把 `2xx/3xx/4xx` 视为可服务响应）、跨平台进程组退出清理与对应单元测试（`tests/ui-qa-acceptance/`）。
  2. **七维高压测试矩阵与几何级检查**：新增 `references/qa-stress-matrix.md` 与 `references/dom-and-geometry-checks.md`，系统化覆盖超长/多语言文本、并发与弱网、键盘导航、空白与边界态，以及 Playwright/DevTools 的水平溢出与元素遮挡检查代码片段。
  3. **桌面应用与 SPA 水合验收补齐**：新增 `references/electron-and-spa-qa.md` 与 `references/evidence-and-bug-reporting.md`，补充 Electron/WebView 隔离 `USER_DATA` 目录与 CDP 调试、SPA Hydration 前事件丢失排查，以及可复现的 `Blocker / High / Medium / Low` 缺陷报告模板。

## 维护与验证

从本仓库根目录运行以下三条校验命令（须全部退出码 0、0 失败、0 警告）：

```sh
python3 tools/skill-builder/scripts/validate_skill.py skills/ui-qa-acceptance
python3 tools/skill-builder/scripts/check_pointers.py --root . skills/ui-qa-acceptance
python3 -m unittest discover -s tests/ui-qa-acceptance -v
```
