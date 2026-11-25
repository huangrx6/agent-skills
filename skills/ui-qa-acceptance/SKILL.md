---
name: ui-qa-acceptance
description: >-
  Use this skill to run black-box interactive UI acceptance testing on live web apps, SPAs, or
  desktop Electron/WebView apps: launching local servers via with_server.py, reconnaissance before
  clicking, verifying state resets across navigation and modal close, stress-testing item counts,
  long text, narrow/short viewports, keyboard focus, interrupted gestures, and console/network
  cleanliness, and delivering evidence-backed QA reports.
  触发：真实页面黑盒交互验收、发版前复测、切页与关闭复位、高数量与窄窗压测、键盘焦点与报错核查、Electron CDP 实测、带证据验收报告。
  Do NOT use for: unit testing or TDD (tdd-testing), static visual critiques (ui-design-craft),
  fixing frontend code (frontend-engineering), or drafting product ACs (product-spec).
  不适用于单元测试与 TDD、纯静态视觉评审、直接修改前端源码、产品 AC 起草。
compatibility: Requires Python 3.10+ for scripts/with_server.py; live UI automation uses Playwright or available browser/CDP DevTools tooling.
---

# 黑盒交互验收与 UI 质检

像挑剔的真实用户一样，在**真实渲染出来的 Web、SPA 或桌面应用界面**上走通完整路径，用新鲜、可复现的客观证据判定改动是否达到发布标准。没有新鲜验证证据，就不宣称任何项已通过。

## 1. 黑盒验收四条铁律

1. **禁止看代码脑补验收（证据先于结论）**：绝不因为「源码写了逻辑」「单测过了」「上次跑通了」就判通过。任何结论前必须过四步验证门控：
   - **识别（IDENTIFY）**：确定哪项真实操作、DOM 数值或日志能证明当前断言；
   - **执行（RUN）**：在真实渲染页面上新鲜、完整地执行验证（不复用改前旧结果）；
   - **阅读（READ）**：读取完整退出码、全部 Console/PageError/Network 输出与几何返回值；
   - **核对（VERIFY）**：证据与断言完全匹配才判通过，否则按事实报失败或未验证。
   - **红旗停手词**：出现「应该没问题」「大概率好了」「看起来正常」「逻辑已覆盖」时立即停手并实测。
2. **先侦察，再操作（Reconnaissance-Then-Action）**：进入动态页先等加载与渲染稳定并挂好 `console` / `pageerror` / `response` 监听，先探测真实可见控件与初始基线，再用语义定位器执行操作，绝不盲猜选择器。
3. **只报事实与证据，不顺手魔改业务源码**：验收角色负责暴露缺陷、收缩最小复现、量化几何与运行时证据并分级定性，绝不私自修改业务代码掩盖现场。
4. **零猜测与未验证透明披露**：凡因环境、账号、令牌、外网、平台无 CDP（如 macOS WKWebView / Linux WebKitGTK）或手势无法真机合成而未测到的 AC 与场景，必须显式标为「未验证（原因）」，绝不混进「已通过」。

## 2. 环境启动决策树

动手前先判断待测形态，避免重复占端口或污染本机真实数据：

```text
待测目标是什么？
├─ 静态 HTML 文件
│   ├─ 无 ES Module / fetch / CORS → 直接用 file:// 绝对路径打开并侦察
│   └─ 含 ES Module / fetch / 路由 → 用 scripts/with_server.py 起本地静态 HTTP 服务
├─ 动态 Web / SPA 应用
│   ├─ 目标服务已在运行 → 直接连接目标 URL，严禁重复拉起冲突端口
│   └─ 服务未启动 → 先跑 scripts/with_server.py --help，再用它托管单/多服务启停
└─ 桌面应用（Electron / NW.js / CEF / WebView2）
    ├─ 强制使用隔离临时 USER_DATA 数据目录（绝不读写用户真实配置/数据库）
    ├─ 仅在 127.0.0.1 开启 --remote-debugging-port=9222 且保持窗口屏幕上可见
    └─ 无 CDP 暴露平台 → 如实声明「未运行真实渲染态检查」
```

- **隔离与可见性**：桌面或本地持久化应用验收一律指向独立临时 `USER_DATA` 目录，测后清理；CDP 仅限 `127.0.0.1`，窗口须保持屏幕可见且测完还原。
- **水合与主题切换**：SPA 需等事件水合与骨架屏消失后再点击；弹窗关闭后核查透明遮罩/滚动锁残留；必做明暗双主题往返切换对比度与硬编码色核查。

详细启停策略与桌面/SPA 陷阱见 [环境启停与先侦察后操作](references/server-and-reconnaissance.md) 与 [桌面 Electron 与 SPA 专项验收](references/electron-and-spa-qa.md)。

## 3. 服务托管命令表（`scripts/with_server.py`）

`scripts/with_server.py` 仅依赖 Python 3.10+ 标准库，作为黑盒工具直接调用；首次先运行 `--help` 确认参数，无需读源码污染上下文。无论验收命令通过、失败还是超时，退出前都会按进程组逆序安全回收全部服务。

| 场景 | 推荐命令（`<S>` 为本 skill 下 `scripts/` 绝对路径） |
| --- | --- |
| 查看帮助 | `python3 <S>/with_server.py --help` |
| 单服务 + HTTP 探活 | `python3 <S>/with_server.py --server "pnpm run dev" --port 5173 --path / -- python3 qa_check.py` |
| 前后端多服务 | `python3 <S>/with_server.py --server "python3 backend/server.py" --port 3000 --server "pnpm --dir web dev" --port 5173 -- python3 qa_check.py` |
| 静态站点 HTTP 托管 | `python3 <S>/with_server.py --server "python3 -m http.server 4173 --bind 127.0.0.1" --port 4173 --path / -- python3 verify_flow.py` |
| 自定义主机与超时 | `python3 <S>/with_server.py --host 127.0.0.1 --timeout 45 --server "npm run preview" --port 4173 --path /health -- python3 verify_flow.py` |

- 多服务按**先后端、后前端**顺序成对传入 `--server` 与 `--port`；数量不一致直接退出 `2`。
- 传入 `--path` 后在 TCP 连通之上继续轮询 HTTP 响应直至非 `5xx`（`2xx`/`3xx`/`4xx` 视为已响应）。

## 4. 先侦察后操作闸门

严禁未看真实渲染态就盲写一长串点击脚本，必须按 4 步顺序过关：

1. **先挂监听，再进页面**：首次导航前即绑定 `console`、`pageerror`、`response`（记录 `status >= 400`）与 `requestfailed`，防止漏掉首屏报错。
2. **等待真实就绪**：动态页先等 `networkidle` 与核心交互控件 `visible` 且 `enabled`；存在 SSE / WebSocket 长连接时，改等首屏骨架屏消失且核心业务节点可见，绝不靠盲目固定等待。
3. **采集页面侦察基线**：枚举当前可见按钮、链接、输入控件与 `role` / `aria-label` / 标题层级，并保存基线截图至临时目录；若首屏已是白屏、Error Boundary 或登录拦截态，立即取证止步。
4. **语义定位器驱动 + DOM 几何巡检**：
   - 定位优先级：`get_by_role(role, name=...)` → `get_by_label(...)` → `get_by_placeholder` / `get_by_text` → 稳定 `data-testid` → 语义属性；禁止脆弱深层 `nth-child` 样式链；
   - 每次关键状态切换、弹窗开关或视口缩放后，配合 DOM 几何脚本检测微溢出、元素裁切与粘性底栏遮挡，不靠肉眼小图漏检。

完整脚本模板与客观 JS 检查片段见 [自动化验收脚本模式库](references/automation-script-patterns.md) 与 [DOM 与几何客观检查脚本](references/dom-and-geometry-checks.md)。

## 5. 7 维度高压复测摘要

除逐条验证需求编号 AC 外，凡涉及页面、弹窗、列表、表单、设置或导航改动，一律加测以下 7 维度（每维度的具体载荷、操作步骤与量化通过/失败判据见 [7 维度高压验收矩阵](references/qa-stress-matrix.md)）：

| # | 高压维度 | 必测动作与关键失败信号 |
| --- | --- | --- |
| 1 | **主路径与持久化闭环** | 走通增删改查后**硬刷新或重启应用**复核落盘；破坏性操作需二次确认或撤销；URL 状态同步与未保存离开提示有效 |
| 2 | **切页/关闭/重开复位** | 注入搜索词、切子页、滚列表后，分别经关闭按钮 / `Esc` / 点外部 / 切主导航返回，核对临时词、旧空态、子视图干净复位且无滚动穿透 |
| 3 | **极端数据量（0/1/30/100+）** | 0 条空态有引导、搜索无结果可一键清空；30+/100+ 项时搜索吸顶、列表独立滚动、滚到底部最后一项不被粘性底栏遮挡 |
| 4 | **超长文本与多视口/缩放** | 注入 60+ 字中英混排、无空格长 URL、Emoji 及窄窗/矮窗/200% 缩放；`scrollWidth <= innerWidth`，右侧按钮不挤出，弹层限高可滚 |
| 5 | **键盘导航与焦点闭环** | 脱鼠标走通 `Tab`/`Shift+Tab`/`Enter`/`Space`/`Esc`；有清晰 `:focus-visible`，粘性栏不遮挡焦点，关弹层后焦点归还原触发按钮 |
| 6 | **非法输入、5 连击与手势中断** | 空串/重名/非法格式内联报错且保留输入；提交快速 5 连击防重；拖拽/滑块遇 `pointercancel`/切窗失焦/第二指中断后可恢复；报错不卡加载态 |
| 7 | **运行时洁净度与动效稳定** | 全程 0 未捕获 Console Error 与非预期 4xx/5xx；0 坏图（`naturalWidth === 0`）、无明显 CLS、`prefers-reduced-motion` 有意降级、快速 5 连开合不卡半态 |

## 6. 证据规范、严重度与未验证声明

| 级别 | 判定标准 | 发布影响 |
| --- | --- | --- |
| **阻断（Blocker / P0）** | 主路径不通、崩溃白屏、数据丢失/写错、核心按钮被遮挡无法点击、权限越界 | 禁止发版，必须修复后新鲜复测 |
| **高（High / P1）** | 状态复位失效、高数量/窄窗严重溢出、键盘主链路断裂、未捕获报错、5 连击重复写入 | 建议发版前修复 |
| **中（Medium / P2）** | 边缘校验提示不清、局部主题色漂移、次要视图轻度错位但有绕行路径 | 排期尽快修复 |
| **低（Low / P3）** | 细微光学对齐、标点、动效微调（保持克制，不淹没核心缺陷） | 随后续迭代打磨 |

- **总结论三档**：`通过`（0 阻断且核心 AC 全实测通过）、`有条件通过`（0 阻断但存在高/中缺陷或已知未验证项且披露风险）、`不通过`（存在任意阻断项或关键 AC 失败）。
- **硬证据与卫生**：每条缺陷附最小复现步骤、实际 vs 预期、DOM/几何数值、Console/Network 原文与临时截图路径（临时截图严禁提交进业务源码库）；手势测试须注明证据来源（模拟视口 / 合成触摸 / 引擎 / 真机）及未测项。完整模板与示范见 [证据规范、严重度与缺陷报告模板](references/evidence-and-bug-reporting.md)。

## 7. 按需参考（一层直链索引）

- [环境启停与先侦察后操作](references/server-and-reconnaissance.md)：静态页/动态页/桌面端决策树、`scripts/with_server.py` 单多服务与 `--path` 探活、渲染稳定等待、语义定位器优先级与自动化误判陷阱。
- [7 维度高压验收矩阵](references/qa-stress-matrix.md)：7 大维度的具体测试数据载荷、可复现步骤与量化通过/失败判据（覆盖表单、键盘、极端数据、RTL/i18n、手势中断与错误恢复）。
- [DOM 与几何客观检查脚本](references/dom-and-geometry-checks.md)：可直接在 DevTools / Playwright `page.evaluate` 运行的 JS 扫描片段（横向溢出、元素裁切与粘性栏遮挡、焦点归还、坏图与字体、`prefers-reduced-motion` 与 CLS）。
- [桌面 Electron 与 SPA 专项验收](references/electron-and-spa-qa.md)：本地 CDP `--remote-debugging-port` 验收、独立 `USER_DATA` 目录隔离卫生、SPA 水合与弹窗过渡期点击陷阱、明暗双主题切换残留核查。
- [证据规范、严重度与缺陷报告模板](references/evidence-and-bug-reporting.md)：验证前门控与红旗词禁令、硬证据清单、严重度分级量表、完整验收报告模板与 3 条真实缺陷单示范。
- [自动化验收脚本模式库](references/automation-script-patterns.md)：Console/PageError/Network 监听采集、页面控件自动侦察、静态 HTML 与动态 SPA 自动化验收脚本模板与安全清理。
- [使用与维护说明](README.md)：仓库内快速命令示例、目录索引与维护者回归验证入口。

## 8. 交付前自检闸门

交付验收报告前，逐条核对以下硬条件（任一未满足即补测或如实降级为「未验证」）：

- **真实渲染验证**：全部标为「通过」的 AC 与高压项均在真实渲染页面完成本轮新鲜操作，无看代码脑补、无沿用改前旧结果、无「应该没问题」类推测语。
- **环境与数据卫生**：本地服务已通过 `scripts/with_server.py` 托管并在结束时回收全部进程组；桌面或持久化应用均在独立临时 `USER_DATA` 目录执行，未污染用户真实配置与数据库，临时截图未落入业务源码目录。
- **运行时与几何证据**：全程已挂载并读取 `console`、`pageerror`、`response`、`requestfailed` 汇总；涉及布局、列表或弹窗的改动均已采集关键 DOM 几何数值（溢出、裁切、粘性栏遮挡、焦点归还）。
- **报告结构完整**：报告已包含明确总结论（`通过 / 有条件通过 / 不通过`）、AC 逐条核对表、7 维度高压抽查摘要、按严重度排序的缺陷单（含最小复现步骤与客观证据），以及透明的「未覆盖范围与风险提示」。
- **职责边界清晰**：未顺手修改业务源码掩盖现场；手势、触摸或无 CDP 平台限制均已明确标注证据来源与未测项。
