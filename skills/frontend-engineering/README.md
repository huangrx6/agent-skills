# frontend-engineering · 前端工程实现、性能优化与根因调试

> React / TypeScript / Next.js / Vite 旗舰级前端工程规范：完整覆盖异步瀑布消除、包体与懒加载优化、服务端/RSC 与客户端数据流、重渲染与 JS/渲染热点治理、复合组件与状态架构、作用域 CSS 工程化及四阶段根因调试。

| 适合 | 产物 | 依赖 |
| --- | --- | --- |
| React/TS 组件开发与重构、组合与状态架构、全链路前端性能治理、作用域 CSS 工程化、前端 Bug 根因调试 | 干净可组合组件与纯函数模型 · 性能优化与竞态消除 · 样式隔离修复 · 回归用例与构建验证 | 目标项目的前端工具链（Node.js / TypeScript / React / 打包器等） |

Agent 的执行闸门、工程铁律与场景路由见 [SKILL.md](SKILL.md)，9 份高密度专题参考按其中的路由表按需直链读取。

## 快速使用

- “这个组件堆了七八个布尔 props，帮我用复合组件、显式变体和 `state/actions/meta` Context 干净重构。”
- “把这段接口与页面数据加载里的串行 `await` 瀑布改成并行，并把重型编辑器拆成按需加载与悬停预加载。”
- “列表输入搜索掉帧、偶尔旧请求覆盖新结果，帮我按重渲染治理与竞态守卫彻底重构。”
- “弹窗里的图标样式被另一个对话框的 CSS 覆盖了，按四阶段根因调试法定位源头并解决，不要加 `!important`。”
- “这个状态闪烁 Bug 已经改了三次 `useEffect` 还复发，请触发三连败熔断帮我重审状态归属与组件结构。”

## 目录结构

- [SKILL.md](SKILL.md)：工作闸门、工程铁律、按场景路由表、四阶段根因调试与一层参考索引
- [references/async-waterfalls.md](references/async-waterfalls.md)：消除异步瀑布（6 条，CRITICAL）
- [references/bundle-optimization.md](references/bundle-optimization.md)：包体大小与按需加载优化（6 条，CRITICAL）
- [references/server-and-client-data.md](references/server-and-client-data.md)：服务端 / RSC 性能与安全（10 条，HIGH）+ 客户端数据流与存储（4 条，MEDIUM-HIGH）
- [references/rerender-optimization.md](references/rerender-optimization.md)：React 重渲染治理（15 条，MEDIUM）
- [references/rendering-and-js-perf.md](references/rendering-and-js-perf.md)：浏览器渲染性能（11 条，MEDIUM）+ JS 热点性能（14 条，LOW-MEDIUM）
- [references/advanced-react-patterns.md](references/advanced-react-patterns.md)：高级 React 副作用与初始化模式（4 条）+ React 19 API 变更
- [references/composition-and-state.md](references/composition-and-state.md)：复合组件、`state/actions/meta` 依赖注入、UI/状态解耦、纯函数模型与状态复位（7 条 + 实践）
- [references/css-and-interaction-craft.md](references/css-and-interaction-craft.md)：作用域 CSS、Design Tokens、防撑破与粘性滚动模板、键盘焦点闭环与竞态/防双击守卫
- [references/frontend-debugging.md](references/frontend-debugging.md)：前端四阶段根因调试法、CSS/React 采证、三连败架构熔断与反合理化对照表
- `evals/triggers.json` 与 `evals/evals.json`：触发边界与行为评判样例

## 边界

- 负责前端代码架构、性能优化、样式工程化与缺陷根因修复；
- 纯视觉审美方向与设计评审归 `ui-design-craft`，后端/Electron 主进程/数据库架构归 `arch-backend-craft`，独立 TDD 流程归 `tdd-testing`，黑盒浏览器交互验收归 `ui-qa-acceptance`，仓库工程基线配置归 `repo-baseline`；
- 不在未完成复现与计算样式/状态采证前盲目修改样式或堆叠补丁。

## 验证

本 skill 无可执行脚本，结构与引用校验在仓库根目录运行：

```sh
python3 tools/skill-builder/scripts/validate_skill.py skills/frontend-engineering
python3 tools/skill-builder/scripts/check_pointers.py --root . skills/frontend-engineering
```
