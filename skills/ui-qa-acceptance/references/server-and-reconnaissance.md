# 环境启停与先侦察后操作

高质量黑盒验收建立在两个工程前提上：**受控且可自动回收的运行环境**，以及**基于真实渲染 DOM 而非源码猜测的操作链路**。

## 1. 环境启动决策树

收到验收任务后，先按以下决策树确定入口方式，绝不盲目拉起冲突端口或在未就绪页面硬点：

```text
用户验收任务
├─ 1. 目标是静态 HTML 文件？
│   ├─ 是（纯本地 DOM/样式/表单，无 ES Module、fetch 或绝对路径资源）
│   │   ├─ 先读 HTML 确认基础结构，并用 file://<绝对路径> 打开验证
│   │   └─ 若页面存在动态脚本、ES Module、CORS 或路由回退 → 转入「本地服务模式」
│   └─ 否（动态 Web / SPA / 前后端联调 / 桌面渲染页）
│       ├─ 2. 目标服务是否已在运行？
│       │   ├─ 是 → 直接连接已运行地址（如 http://127.0.0.1:5173），不重复启动
│       │   └─ 否 → 先运行 `python3 <S>/with_server.py --help` 确认用法
│       │            再通过 `scripts/with_server.py` 托管单/多服务启停
│       └─ 3. 是否为 Electron / WebView 桌面应用？
│           └─ 是 → 使用隔离临时 USER_DATA 目录 + 127.0.0.1 本地 CDP 端口
│                   （详见 electron-and-spa-qa.md）
└─ 进入「先侦察，后操作（Reconnaissance-Then-Action）」
    1. 导航前先绑定 Console / PageError / Network 监听
    2. 导航并等待渲染稳定（networkidle + 关键业务节点可见可用）
    3. 截图并侦察真实 DOM 控件与初始基线
    4. 使用侦察到的语义定位器执行 AC 与 7 维度高压操作
```

## 2. 使用 `scripts/with_server.py` 管理服务生命周期

### 黑盒脚本使用纪律
- 首次使用时先运行 `python3 <S>/with_server.py --help` 查看完整参数，把随附脚本视为**黑盒可靠工具**直接调用，不必把脚本源码全文塞进上下文。
- 验收脚本本身只写 Playwright / 浏览器交互逻辑，服务启动、就绪探测与退出回收全部交给 `scripts/with_server.py`。

### 参数与行为速查

| 参数 | 说明 | 默认值 / 约束 |
| --- | --- | --- |
| `--server "<cmd>"` | 服务启动命令，可重复传入多个 | 必填，按传入顺序依次启动 |
| `--port <int>` | 对应服务监听端口，可重复传入多个 | 必填，数量必须与 `--server` 严格一致（否则退出码 `2`） |
| `--host <addr>` | 端口与 HTTP 探测主机地址 | 默认 `127.0.0.1` |
| `--path <route>` | 可选 HTTP 就绪路径（如 `/`、`/health`） | 留空仅做 TCP 探测；填写后等待 HTTP 状态 `< 500` |
| `--timeout <sec>` | 单个服务等待就绪的最大秒数 | 默认 `30.0` 秒 |
| `-- <command...>` | 全部服务就绪后执行的验收命令 | 必填（缺省时退出码 `2`）；建议放在 `--` 之后 |

### 常用调用示例

```bash
# 1) 单前端开发服务器 + HTTP 根路径探活
python3 skills/ui-qa-acceptance/scripts/with_server.py \
  --server "pnpm run dev -- --host 127.0.0.1 --port 5173" --port 5173 --path / \
  -- python3 /tmp/qa_verify.py

# 2) 前后端双服务（先启后端，再启前端；分别校验端口）
python3 skills/ui-qa-acceptance/scripts/with_server.py \
  --server "cd backend && python3 server.py" --port 3000 \
  --server "cd frontend && npm run dev -- --port 5173" --port 5173 \
  --timeout 45 \
  -- python3 /tmp/qa_e2e_flow.py

# 3) 静态站点含 ES Module / fetch，用 Python 内置 HTTP 服务托管
python3 skills/ui-qa-acceptance/scripts/with_server.py \
  --server "python3 -m http.server 4173 --bind 127.0.0.1 --directory website" \
  --port 4173 --path / \
  -- python3 /tmp/qa_website.py
```

### 进程组清理与退出码契约
- **安全清理**：在 POSIX 系统下以独立会话（`start_new_session=True`）启动每个服务，无论验收脚本成功、抛异常还是超时，`finally` 都会按**逆序**对整个进程组发送 `SIGTERM`，最多等待 5 秒后兜底 `SIGKILL`，杜绝 `npm` / `vite` 子进程泄漏占端口。
- **提前退出诊断**：若服务在端口就绪前意外退出，脚本会立即中止并打印其退出码与 `stderr`，不会白等完整超时时间。
- **退出码**：透传验收命令真实退出码；参数错误返回 `2`；服务启动失败或超时返回 `1`。

> **多服务与 `--path` 注意**：`--path` 会应用于本次启动的每一个服务。若后端是 `/health` 而前端是 `/`，推荐不传统一 `--path`（由 TCP 端口放行），而在验收脚本开头用 `page.goto()` 配合元素就绪等待完成应用层校验，或分别给两个服务提供相同的 `/` 可达响应。

## 3. 先侦察，后操作（Reconnaissance-Then-Action）

动态应用的最终 DOM 由运行时数据、权限、特征开关和客户端状态共同决定。严格按 4 阶段推进：

### 阶段 A：导航前先挂监听通道
必须在首次 `page.goto()` 之前绑定 `console`、`pageerror`、`response`（记录 `status >= 400`）与 `requestfailed`。否则首屏初始化阶段的报错、资源 404 和水合异常会被彻底漏掉。

### 阶段 B：等待动态渲染真正稳定
- **常规动态页**：先 `page.wait_for_load_state("networkidle")`，再等待首屏核心业务容器或主按钮 `wait_for(state="visible")` 且 `is_enabled()`。
- **存在长连接的页面（SSE / WebSocket / 高频轮询）**：`networkidle` 可能永不满足。改为：
  1. `page.wait_for_load_state("domcontentloaded")`；
  2. 等待首屏骨架屏 / Loading 指示器消失（`state="hidden"` 或 `"detached"`）；
  3. 等待核心业务列表项或主交互按钮 `state="visible"` 且可用。

### 阶段 C：探测真实界面基线
执行任何业务操作前，先采集一次完整侦察快照：
1. 保存全页或首屏基线截图到临时目录（如 `/tmp/qa-baseline.png`）；
2. 枚举可见按钮（含文本与 `aria-label`）、链接、表单输入（`name` / `type` / `placeholder` / 关联 `label`）、标题层级（`h1`–`h3`）与弹窗/抽屉节点；
3. 检查是否处于白屏、错误边界（Error Boundary）、空配置引导或登录拦截态——若是，立刻记录截图和 Console/Network 证据并定性，不要强行执行后续点击。

### 阶段 D：基于实测定位器执行与逐帧核对
- 每次触发写操作、切页或弹窗开关后，验证**三个信号**：预期 DOM 变更已生效、无新增 Console Error / 非预期 4xx/5xx、关键容器几何无溢出或遮挡。

## 4. 语义定位器优先级

定位器决定黑盒脚本是“模拟真实用户”还是“耦合脆弱内部实现”。优先使用面向用户可见语义的定位方式：

| 优先级 | Playwright 定位器 | 适用场景 | 稳定性与验收价值 |
| --- | --- | --- | --- |
| 1（首选） | `page.get_by_role("button", name="保存")` | 按钮、链接、对话框、开关、标签页、输入框 | 最高；同时顺带验证无障碍角色与可访问名称是否存在 |
| 2 | `page.get_by_label("API 密钥")` | 带 `<label>` 或 `aria-label` 的表单控件 | 极高；若定位不到，本身就暴露了表单缺少标签的 A11y 缺陷 |
| 3 | `page.get_by_placeholder("搜索扩展…")` / `get_by_text(...)` | 搜索框、提示条、空态文案、列表项内容 | 高；需配合 `exact=True` 或父容器作用域避免重名误点 |
| 4 | `page.get_by_test_id("extension-picker")` | 复杂画布、无文本自定义组件、高重复卡片 | 中高；不暴露用户感知问题，仅作语义不足时的补充 |
| 5（兜底） | 语义属性选择器（如 `input[name="email"]`、`[aria-expanded="true"]`） | 原生属性明确但缺少角色名的控件 | 中；避免绑定样式类名 |
| 禁止 | 深层位置链（`div > div:nth-child(3) > span.text-sm`） | Tailwind 工具类或易变 DOM 层级 | 极脆；微小重构即误报，且无法反映真实用户可见性 |

## 5. 常见自动化误判陷阱与防呆对策

| 常见陷阱 | 表现症状 | 正确对策 |
| --- | --- | --- |
| 未等 `networkidle` / 水合完成即查 DOM | 侦察结果为空、点击按钮毫无反应（事件尚未绑定） | 等待 `networkidle` + 目标控件 `visible` & `enabled` + 骨架屏消失 |
| 靠 `wait_for_timeout(1000)` 盲等 | CI 或慢机上偶发失败，快机上拖慢全流程 | 用条件等待：`locator.wait_for()`、`expect_response()`、`wait_for_function()`；仅在验证“状态稳定后未回弹”或“防抖窗口”时做短时辅助观察 |
| 弹窗关闭动画未结束即点底层 | Playwright 报元素被遮罩拦截，或点击被过渡中的透明层吃掉 | 等待弹窗/遮罩 `wait_for(state="detached")` 或 `state="hidden"` 后再操作底层 |
| 只看 `locator.count() > 0` 不看可见性 | 隐藏 DOM 或 `opacity: 0` 元素被误判为「页面正常显示」 | 校验 `is_visible()` 并结合 `getBoundingClientRect()` 确认宽高 > 0 且在可视区 |
| 只看缩略截图不测 DOM 几何 | 4px 横向溢出、按钮被右边界裁切、最后一项被底栏压住半截被肉眼放过 | 每次关键视图变更都运行 DOM 几何溢出与遮挡检查脚本 |
| 复用有脏数据的共享环境 | 上一轮残留缓存掩盖冷启动空态，或污染真实用户配置 | 本地/桌面验收一律启用独立临时数据目录，测后清理 |
| 在同一页面盲目点「全量提交」不查重 | 看似页面没报错，实则后台发了 3 条重复写请求 | 订阅 `request` / `response` 计数，并发连击后核对写请求次数与落盘条数 |
