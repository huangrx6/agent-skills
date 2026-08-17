# 字体、颜色与视觉样式

## 字号

从截图只能可靠得到 glyph/ink 尺寸，CSS font-size 可能受字体、DPR 和缩放影响。

优先：

1. 多字符文本宽度/高度；
2. 相同层级多处交叉验证；
3. 换算到设计稿后再给 normalized 值。

不要单独量一个汉字就断言字号。

## 颜色

- 大面积实心区域用 `pick`，High；
- 系列/主色用区域 palette；
- 小字抗锯齿颜色只能 Medium/Low；
- 半透明色必须结合背景，不把合成后的像素当原始 token。

## 圆角

图片无法精确恢复 CSS border-radius 时：

- 大轮廓可量弧线给 Medium；
- 小卡片只给 observed curvature + recommended token；
- 不默认写 8px。

## 阴影

截图通常只能判断：有/无、方向、软硬、扩散范围。完整 CSS `box-shadow` 通常属于 recommended，不是 observed。

## Design Tokens

§2 同时保存：

```text
Observed value
Normalized token
Confidence
Evidence
```

这样既能追原图，也能让前端落地到统一 token 系统。
