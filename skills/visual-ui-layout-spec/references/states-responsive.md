# 状态与响应式

## 状态

状态分三类：

- Observed：截图直接提供；
- Provided Variant：用户提供了另一张状态图；
- Recommended：工程建议，图中不可见。

§7 必须标来源。

## 多图

同页面不同状态：共享区域 ID，状态差异写 variant。

不同分辨率：分别建立 viewport，只有两张图都能支持时才总结响应式规则。

## 单图响应式

单张桌面截图不能证明：

- mobile breakpoint；
- 卡片折行顺序；
- sidebar collapse；
- hidden columns。

可以提出建议，但必须 Low Confidence / Recommended。
