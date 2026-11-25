# 布局系统、空间节奏与多端适配

布局把业务优先级翻译成阅读顺序、分组关系、呼吸节奏与可用空间。**先诊断结构问题，再移动盒子；多端适配是按新情境重思体验，而不是等比缩放像素。**

---

## 一、布局诊断与空间命题

动手重构布局前，先做两件事：

### 1. 眯眼测试（Squint Test）与 7 项结构评估

把页面模糊化或缩小到缩略图尺度，核对以下 7 项（均需落到真实视图或样式源码，不做空泛评价）：

1. **阅读顺序**：模糊细节后，第一视觉焦点、第二视觉层级与主要功能分组是否依次浮现？
2. **亲密性分组**：相关元素是否靠紧凑距离自然成组，还是被迫靠一层层边框/卡片框来强行凑合？
3. **间距节奏**：紧距与宽距之间是否有清晰节拍，还是全页机械重复同一间距值导致万物等权？
4. **拓扑匹配**：多列、卡片网格或抽屉结构是否匹配真实信息关系，而不是照搬框架默认模板？
5. **密度适配**：单屏信息量是否匹配使用频次与访问模式（Operate/Read 追求稳定可预测的线性导航与密度；Persuade/Experience 可在世界允许时引入非对称与节奏变化）？
6. **DOM 与视觉顺序一致**：在窄窗、中等宽、宽屏、200% 缩放与本地化重排下，Tab 键焦点顺序和读屏朗读顺序是否仍与视觉顺序一致？
7. **极端边界承压**：超长文案、空态、浮层、粘性顶底栏、安全区与小触控热区是否暴露裁切或重叠？

### 2. 先写空间命题（Spatial Thesis）

修改前用五句话钉死：主任务/阅读路径是什么；哪些必须紧邻、哪些必须隔离；谁领衔、谁辅助；目标密度与间距节拍；跨容器/视口/输入方式和极端内容时结构如何演变。选用能表达这组关系的**最简布局原语**（Flex 处理一维流、Grid 处理二维对齐）。

---

## 二、4px 空间节奏与分组法则

### 1. 间距标尺（4px 基础步进）

相比纯 8px 步进，**4px 基础步进**保留了 `4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64px` 中最关键的 `12px` 与 `20px` 过渡档，避免在工作台密集控件里非紧即松。

```css
:root {
  --space-1: 0.25rem;  /* 4px  微距：图标与标签、紧贴辅助信息 */
  --space-2: 0.5rem;   /* 8px  组内紧距：关联控件、标题与紧邻副标题 */
  --space-3: 0.75rem;  /* 12px 紧凑内边距：表单控件、紧凑列表行 */
  --space-4: 1rem;     /* 16px 标准内边距与常规同级间距 */
  --space-5: 1.25rem;  /* 20px 中等面板内边距 */
  --space-6: 1.5rem;   /* 24px 组间距：明确分隔两个独立信息块 */
  --space-8: 2rem;     /* 32px 区块间距 */
  --space-12: 3rem;    /* 48px 主页面区段分隔 */
}
```

### 2. 四条空间铁律

- **亲密性优先于套容器**：相关内容先靠缩小间距聚合，不同分组靠放大间距拉开，**组内间距 < 组间距 < 区块间距**。只有当边界确实承担交互或状态分隔职责时才加容器框。
- **标题贴近自己的内容**：标题上方留白必须明显大于下方留白（例如上 `24px–32px`、下 `8px–12px`），防止标题浮在两段之间归属不明。
- **优先 `gap` 管理兄弟节奏**：在 Flex/Grid 父容器上用 `gap` 声明子项间距，替代脆弱的 `:not(:last-child) { margin-bottom }`。
- **重复服务识别，变化表达优先级**：不要为了“显得丰富”随意打破网格；只有内容角色或优先级变化时才切换布局形态。

---

## 三、响应式策略：Mobile-First、容器查询与多端重构

### 1. Mobile-First 与内容驱动断点

- 以移动端单列基础样式起步，通过 `min-width` 逐步叠加桌面复杂度，避免移动端先下载并覆盖大量桌面样式。
- **内容驱动断点**：从窄窗往宽拉，结构在哪个宽度真正开始不舒服，就在哪里设断点（常规 3 档 `640px` / `768px` / `1024px` 即可覆盖绝大多数需求）；字号、内边距与流体列宽优先用 `clamp()` 替代琐碎断点。
- **优先容器查询（Container Queries）**：同一个组件可能同时出现在主工作区、窄侧边栏和弹窗里，让它响应**父容器宽度**而非整页视口宽度：

```css
.panel-host {
  container-type: inline-size;
  container-name: panel;
}

.metric-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-3);
}

@container panel (min-width: 30rem) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }
}
```

### 2. 多情境体验重构矩阵（非缩放）

| 目标情境 | 布局重构 | 交互与导航重构 | 内容策略 |
| --- | --- | --- | --- |
| **Desktop → Mobile** | 多列转单列垂直流；全宽控件；表格转卡片行（利用 `data-label`）或锁定首列横向滚 | 高频操作下移至拇指热区；复杂下拉改底部抽屉（Bottom Sheet）；导航收进底部 Tab 或抽屉 | 渐进披露（次要项收进 `<details>` / Tab）；不阉割核心功能 |
| **Tablet（混合端）** | 优先双栏（如 Master-Detail 列表+详情），横竖屏自适应 | 同时兼顾触控热区（≥44px）与外接键盘/鼠标 | 密度高于手机、低于大屏桌面 |
| **Mobile → Desktop** | 利用横向空间分栏；常驻侧栏；**设 `max-width` 防止 4K 宽屏把行宽拉裂** | 补全悬停提示、快捷键、右键菜单、框选与批量操作 | 减少不必要折叠，直接展示多列数据表与完整上下文 |
| **窄窗 / 矮窗工作台** | 弹窗/抽屉限制 `max-height: min(85dvh, 40rem)`，内部主列表独立 `overflow-y: auto` | 头部搜索栏与底部提交栏 `position: sticky` 常驻可见 | 确保 320px 宽或矮窗口下主按钮永不被推出屏外 |
| **Print（打印）** | `@media print` 隐藏导航/侧栏/按钮，合理控制分页断页 | 去除所有交互依赖 | 展开被折叠或截断的全文与完整 URL，补页眉/页码/日期 |

---

## 四、输入方式探测、触控热区与手势隔离

**屏幕宽度不等于输入方式**（触屏笔记本是大屏+触控，配键盘的平板既有指针又有触控）。必须通过媒体查询探测真实输入能力：

```css
/* 精准指针（鼠标/触控板） */
@media (pointer: fine) {
  .action-btn { min-height: 36px; padding-inline: 12px; }
  /* 仅在精准指针桌面端按需关闭页面橡皮筋回弹，避免破坏移动端下拉刷新 */
  html.app-shell { overscroll-behavior: none; }
}

/* 粗指针（手指/触控笔） */
@media (pointer: coarse) {
  .action-btn { min-height: 44px; min-width: 44px; padding-inline: 16px; }
}

/* 仅在支持真实悬停的设备上启用悬停视觉变化；绝不把核心功能藏在 hover 里 */
@media (hover: hover) {
  .card:hover .card-surface { transform: translateY(-2px); }
}
```

### 触控、热区与滚动边界硬规范

1. **触控目标尺寸**：
   - 移动端主交互热区建议 **≥ `44×44px`**；
   - **WCAG 2.2 AA（SC 2.5.8）最低底线**：所有目标 ≥ `24×24 CSS px`（例外仅限：行内文本链接、用户代理原生控件、功能必需尺寸、存在等价替代控件，或以目标中心画 `24px` 直径圆不与任何其他目标及其 `24px` 圆重叠）。
   - 视觉图标较小时（如 `16px` 关闭按钮），通过 `padding` 或透明伪元素扩大可点命中区，不必把图形本身画笨重。
2. **消除触控延迟与滚动穿透**：
   - 交互元素设置 `touch-action: manipulation`（消除双击放大 300ms 延迟）；
   - 有意设定 `-webkit-tap-highlight-color`；
   - 模态框、抽屉与局部滚层设置 `overscroll-behavior: contain`，防止滚到底部时带动底层页面一起滚。
3. **自定义手势控件验证（滑块 / 对比拉杆 / 拖拽条）**：
   - 沿控件操作轴拖动时只驱动控件、不滚动页面（配合精确的 `touch-action: pan-y` 或 `none`）；
   - 沿页面主滚动轴划过控件时只滚动页面、不误触控件；
   - 报告测试证据时须注明手段（模拟器、合成触控、真实引擎 Safari vs Chromium、真机），**截图与改视口尺寸只能证明布局，不能证明手势可用**。

---

## 五、安全区与响应式媒体

### 1. 刘海屏与底部手势条安全区

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
```

```css
.app-header {
  padding-top: max(0.75rem, env(safe-area-inset-top));
  padding-inline: max(1rem, env(safe-area-inset-left)) max(1rem, env(safe-area-inset-right));
}

.sticky-footer {
  padding-bottom: max(1rem, env(safe-area-inset-bottom));
}
```

### 2. 响应式图片与艺术指导

- 分辨率适配使用 `srcset`（`w` 描述符）+ `sizes`，并标明 `width` 与 `height` 防止 CLS；
- 不同断点需要不同裁切比例（如桌面横幅转移动竖图）时使用 `<picture>` + `<source media="...">`；
- 严禁靠外层盲目 `overflow-x: hidden` 掩盖真实布局溢出（应先查出撑宽的固定像素或未设 `min-width: 0` 的子项）。

---

## 六、RTL（从右到左）布局与方向核查

面对声明了 `dir="rtl"`（或包含 `ar`、`fa`、`ur`、`he` 等 RTL 语种的页面，注意浏览器只认 `dir` 不从 `lang` 自动推方向）的界面，按以下准则设计与排查：

1. **全面使用 CSS 逻辑属性**：
   - `margin-inline-start` / `margin-inline-end` 替代 `margin-left` / `margin-right`；
   - `padding-inline`、`border-inline-start`、`text-align: start`、`inset-inline-start` 替代物理方向；
   - 若历史样式使用 `[dir="rtl"] .item { margin-right: 1rem; }` 局部覆写，**必须同步清零冲突的旧物理属性（`margin-left: 0;`）**，否则两侧间距会同时生效。
2. **水平居中切勿误改**：`left: 50%; transform: translateX(-50%);` 是方向无关的居中写法；机械把 `left` 改成 `inset-inline-start` 会因为 `translateX` 不镜像而导致严重偏位。
3. **方向性图标目检核实**：返回箭头、前进箭头、列表折角、侧栏收起图标在 RTL 下应指向阅读逻辑方向；纯 RTL 页面可能直接提供已画好方向的资源，核查渲染结果而非机械检查有没有写 `transform: scaleX(-1)`。
