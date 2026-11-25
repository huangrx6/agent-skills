# ui-design-craft · 界面设计工艺与可用性规范

> 面向 Web 与桌面产品的系统化界面设计、反 AI 模板脸审视、排版布局配色、动效编排、既有界面精修、生产级极端加固，以及 20 分审计与 40 分设计批评规范。

| 适合 | 典型产物 | 外部依赖 |
| --- | --- | --- |
| 新界面视觉定调、反模板评审、排版/布局/色彩/文案打磨、动效规格、既有页面精修、高数量与多语种加固、5 维技术审计与深度 Critique | 视觉命题与 Token 方案 · 风格漂移清单 · 动效与降级规格 · 极端加固方案 · P0–P3 审计/批评报告 | 无外部运行时依赖（有浏览器工具时可结合真实渲染核验） |

Agent 的核心路由、工艺底线与参考索引见 [SKILL.md](SKILL.md)。

## 典型用法

- **新界面定调**：“帮我给这个开发者工作台定一套清晰克制的视觉方向、Token 色板和布局骨架，不要 AI 模板味。”
- **既有页面精修**：“这个设置弹窗和旁边页面风格脱节，按现有设计体系做漂移归类并给出最窄层级的统一改法。”
- **动效编排**：“梳理全站的展开收起、抽屉弹层和加载动效，给出时长、曲线、Hover 防抖和 `prefers-reduced-motion` 有意降级方案。”
- **生产级加固**：“这个扩展选择器现在只有 3 条数据，装到 100 项、超长名称、德语膨胀、RTL 和窄矮窗口下怎么加固？”
- **技术审计 / 深度批评**：“对这个 Web 应用跑一次 5 维 20 分技术审计，或按尼尔森 10 项启发式 + 测试角色做一次深度 Critique 并输出 P0–P3 整改清单。”

## 目录结构

- [SKILL.md](SKILL.md)：访客模式判定表、任务路由闸门、工艺底线、反 AI 模板红线、P0–P3 规则与一层参考索引
- [references/visitor-modes-and-direction.md](references/visitor-modes-and-direction.md)：Operate / Read / Persuade 三模式法则、视觉世界 4 项边界与两遍设计命题工作法
- [references/craft-floor-and-anti-slop.md](references/craft-floor-and-anti-slop.md)：9 项工艺底线、5 类 AI 模板脸校准、完整 Refuse 禁令与浏览器默认表面主题化
- [references/typography-system.md](references/typography-system.md)：角色尺度、45–75ch 行宽、暗底亮字三轴补偿、`text-wrap` 断行、`text-box` 光学对齐与微排印
- [references/layout-and-responsive.md](references/layout-and-responsive.md)：眯眼测试、4px 空间节奏、容器查询、多端体验重构、触控热区与 RTL 逻辑属性核查
- [references/color-and-theming.md](references/color-and-theming.md)：语义 Token 分层、OKLCH 工程范本、有色底面规则、暗色主题独立编排与对比度无障碍
- [references/copy-distill-and-onboard.md](references/copy-distill-and-onboard.md)：UI 文案四层结构、六维去噪、五类空态与首值引导、局部放大、降噪克制与微愉悦
- [references/motion-choreography.md](references/motion-choreography.md)：动效四要素命题、材质语义、100–800ms 时长表、Hover 防抖、可中断性与减少动态降级
- [references/polish-and-component-review.md](references/polish-and-component-review.md)：精修铁律、4 类漂移分类、5 级分诊、全路径 5 维精修、组件评审与视觉性能核查
- [references/hardening-extremes.md](references/hardening-extremes.md)：极端输入溢出 CSS、30–40% 翻译膨胀与阿波语系、表单/URL/水合、全状态码容错、中断手势与无障碍焦点
- [references/critique-and-audit-rubric.md](references/critique-and-audit-rubric.md)：双视角防锚定、5 维 20 分审计表、认知负荷与尼尔森 10 项 40 分量表、测试角色、P0–P3 模板与上线基线
- `evals/triggers.json` 与 `evals/evals.json`：触发边界与行为评判样例

## 职责边界

- **负责**：界面视觉与交互设计、反模板审视、排版布局色彩、文案与空态引导、动效编排、既有页面精修、前端界面加固、技术审计与 UX Critique。
- **不负责**：React 状态/Hook 架构重构与渲染性能调优（归 `frontend-engineering`）、产品范围与编号 AC 收敛（归 `product-spec`）、黑盒点击验收报告（归 `ui-qa-acceptance`）、幻灯片与技术图制作（归 `deck-authoring` / `diagram-authoring`）。

## 维护校验

本 skill 无可执行脚本，结构、规则与引用校验在仓库根目录运行：

```sh
python3 tools/skill-builder/scripts/validate_skill.py skills/ui-design-craft
python3 tools/skill-builder/scripts/check_pointers.py --root . skills/ui-design-craft
```
