# 动效编排、交互阻尼与减少动态降级

动效只承担两类职责：**解释状态、空间关系与层级**，或在页面真正值得的节点提供**一处精心编排的焦点时刻**。无目的的动效不是精致，而是延迟与维护债。

---

## 一、按访问模式定动效边界

- **Operate / Read**：服务即时反馈、状态切换与空间连续性。常规过渡务必利落迅速，**严禁让用户在每次进入工作台或文档时苦等开屏入场动画**。
- **Persuade / Experience**：动效可以参与表达产品气质，但**一处排练精良的焦点编排**远胜满屏零散特效；严禁全页每个区块千篇一律地“淡入 + 上移（fade-and-slide-up）”或每张卡片无脑浮起。

---

## 二、先写动效命题（四要素），再写关键帧

动笔写 CSS / JS 前，先用四行定清命题，避免随手加 `transition`：

1. **焦点时刻（Focal Moment）**：整屏或全流程中唯一值得专门编排的一处动作（若无需要则留空）；它必须源自本产品机制，通用淡入上移不算命题。
2. **空间连续性（Continuity）**：哪些布局变化、展开收起、弹层或路由切换需要用运动解释“从哪来、到哪去”。
3. **操作反馈（Feedback）**：哪些按钮、开关、勾选、提交与错误状态需要立刻回应用户动作。
4. **性能预算（Budget）**：哪些效果成本较高（如局部模糊、阴影、Canvas）、运行频次如何、低端移动设备上如何收束。

---

## 三、按语义选择动效材质

`transform` 与 `opacity` 是稳定基底，但并非全部手段。按想传达的语义选材质，**整屏只立一个主材质思路，不堆砌奇技淫巧**：

| 传达语义 | 推荐材质与技术手段 | 典型场景 |
| --- | --- | --- |
| **空间连续与归属** | FLIP 变换、共享元素运动、View Transitions API、`grid-template-rows: 0fr → 1fr` | 列表展开详情、手风琴折叠、Tab 指示条滑动、视图切换 |
| **焦点与景深** | 有界限的局部 `backdrop-filter` / `filter: blur()` / 阴影层次过渡 | 模态层浮起、命令面板聚焦 |
| **揭示与构图** | `clip-path`、`mask` 裁切、受控遮挡揭幕 | 品牌首屏主视觉、对比拉杆、图像揭幕 |
| **状态与反馈** | 最小且最清晰的色阶/位姿/描边微变 | 按钮按压、开关拨动、勾选确认、校验轻抖 |

- **列表错峰（Stagger）纪律**：仅在列表真正作为一组队列入场时使用，单步间隔 `25–50ms` 且**总延迟严格封顶（≤ 250–300ms）**；绝不把普通滚动区块全做成错峰列表。

---

## 四、时长档位与缓动曲线标准

时长必须映射位移距离与事件份量，**长反馈在体感上等于卡顿**：

| 档位 | 时长范围 | 适用场景 | 退场时长建议 |
| --- | --- | --- | --- |
| **即时反馈** | `100–150 ms` | 按钮按压、开关拨动、复选框、菜单悬停高亮 | `80–120 ms` |
| **常规状态切换** | `150–300 ms` | Tab 切换、筛选显隐、手风琴展开、Tooltip / 下拉浮层 | `120–200 ms` |
| **布局与视图转场** | `300–500 ms` | 抽屉滑入、模态对话框、侧栏收展、局部视图切换 | `200–320 ms` |
| **焦点编排入场** | `500–800 ms` | 极少数经过专门设计的首屏或里程碑焦点时刻 | — |

### 四条曲线与过渡铁律

1. **退场永远快于进场**：退场时长取进场的 `65%–80%`，不拖泥带水挡住用户下一步操作。
2. **自然减速为主**：进场与位移优先指数减速 `cubic-bezier(0.16, 1, 0.3, 1)` 或 `ease-out-quart`（`cubic-bezier(0.25, 1, 0.5, 1)`），**禁止反射性套用回弹（bounce）或弹簧过冲（elastic）**。
3. **严禁 `transition: all`**：必须显式列出过渡属性（如 `transition: transform 200ms var(--ease-out), opacity 180ms ease;`），避免布局属性或主题切换色值被意外拖慢。
4. **设置准确的 `transform-origin`**：下拉菜单从触发按钮边缘展开，弹窗从视觉锚点缩放；**SVG 内部图形变换必须作用于 `<g>` 包裹层并声明 `transform-box: fill-box; transform-origin: center;`**。

---

## 五、高频交互缺陷防护（CSS 实战范本）

### 1. Hover 边缘防抖动与延迟克制

**严禁让承接 `:hover` 的外层容器自身位移**——当指针停在元素底边时，元素上移会脱离鼠标导致高频闪烁。始终让外框静止、内部视觉层位移：

```css
/* ✅ 外框不动承接命中区，内部 surface 承载视觉浮起 */
.card {
  position: relative;
}
.card-surface {
  transition: transform 180ms cubic-bezier(0.16, 1, 0.3, 1),
              box-shadow 180ms ease;
}
@media (hover: hover) {
  .card:hover .card-surface {
    transform: translateY(-2px);
  }
}

/* 可选悬浮预览：仅在进入时加短暂延迟防划过误触，离开时零延迟立刻收起 */
.preview-popover {
  opacity: 0;
  transition: opacity 140ms ease;
}
.trigger:hover .preview-popover {
  opacity: 1;
  transition-delay: 180ms;
}
```

### 2. 无跳变折叠展开（不动画化 `height: auto`）

```css
.accordion-panel {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 220ms cubic-bezier(0.16, 1, 0.3, 1);
}
.accordion-panel[data-open="true"] {
  grid-template-rows: 1fr;
}
.accordion-inner {
  overflow: hidden;
  min-height: 0;
}
```

### 3. 可中断性、默认可见与循环控制

- **全程可中断**：用户中途再次点击展开/收起、快速切换 Tab 或按 `Esc` 关闭弹层时，动效必须从当前帧平滑转向新目标，禁止锁死点击或先播完再跳回。复杂可中断序列优先用 Web Animations API 或成熟动效库。
- **默认态立即可见**：关键内容不得依赖 JS 滚动监听才从 `opacity: 0` 变可见，防止脚本延迟或失败导致整屏空白。
- **循环与自动播放控制**：任何持续超过 `5 秒` 且与正文并存的自动播放动效，必须提供**暂停、停止或隐藏控件**；非必要装饰循环在元素离开视口（IntersectionObserver）或页面隐藏（`document.hidden`）时必须自动暂停。

---

## 六、合成层性能与 `will-change` 克制

- 避免随手动画化触发重排的属性（`width`、`height`、`top`、`left`、`margin`、`padding`）；确需尺寸变化时用 `transform`、FLIP 或 `grid-template-rows`。
- 模糊、滤镜、大面积阴影与 Shader 必须限定在隔离的小区域内，并在真实中低端设备实测帧率（目标 60fps / 每帧 < 16ms），不盲目迷信“写了 transform 就一定快”。
- **`will-change` 仅作精准临时提示**：严禁全局常驻 `will-change: transform`（会滥建 GPU 图层暴涨显存）；仅在已知高开销动画即将开始前添加、动画落定后移除。

---

## 七、`prefers-reduced-motion` 有意降级（严禁一刀切清零）

**常见严重错误**：写一段全局 `* { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }` 把所有动效直接砍死。这会破坏加载指示、状态确认与层级感知。

**正确原则**：减少动态效果 = **移除或大幅缩减空间位移、缩放与视差，停止装饰性循环，同时保留传达状态变化与因果关系的轻量透明度/颜色过渡**。

```css
:root {
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --dur-fast: 140ms;
  --dur-base: 220ms;
  --dur-overlay: 320ms;
}

.drawer {
  transition: transform var(--dur-overlay) var(--ease-out),
              opacity var(--dur-base) ease;
}

.ambient-pulse {
  animation: pulse 2.4s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  /* 1. 停止纯装饰循环 */
  .ambient-pulse {
    animation: none;
  }

  /* 2. 取消空间大位移，保留清晰克制的透明度切换以维持状态可读 */
  .drawer {
    transform: none !important;
    transition: opacity 150ms ease;
  }

  /* 3. 平滑滚动降为即时跳转，避免晕动症 */
  html {
    scroll-behavior: auto;
  }
}
```

---

## 八、动效验收五帧核查法

不要凭单个静止截图或口头感觉宣称“动效丝滑”。在**正常模式**与**开启 `prefers-reduced-motion` 模式**下，分别对进场与退场检查 5 个时间点：

1. **触发前**：静息态无残留 `will-change`、无错位层叠；
2. **首动帧**：即时响应，无明显起手卡顿或闪烁；
3. **中段帧**：运动轨迹连贯、无内容被裁成半截、无邻近元素被挤跳；
4. **末动帧**：平滑减速落位，中途反转操作可即时打断；
5. **落定态**：落定后的 DOM 层级、清晰度、可点击区域与静态态完全一致，无文字被遮挡或模糊残留。
