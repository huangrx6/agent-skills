# 品牌与资产

内容 spec 表达“讲什么”，项目风格表达“怎么呈现”，品牌表达组织身份，
assets 提供真正使用的文件。品牌可选；不写 `deck.brand` 就只使用项目风格。
不要为凑流程创建假 logo、示例客户身份或占位品牌。

## 文件与查找

```text
project/
  deck.spec.json
  brands/acme/
    brand.json
    logo.svg
    logo-inverse.svg
  assets/manifest.json
```

`deck.brand` 可以是品牌名或含 brand.json 的目录路径。查找顺序：`DECK_BRANDS`
指定的根（按平台路径分隔符）→ spec 所在目录的 brands → 当前目录的 brands →
skill 的 brands。优先放在项目里，便于携带；不向 skill 写本次任务资产。

## brand.json 实际契约

version 必须为 1，字段集封闭，仅允许以下键：

| 字段 | 作用 |
| --- | --- |
| `version` | 固定 1 |
| `label` | 品牌显示名 |
| `logo` | 相对品牌目录的文件路径 |
| `logoInverse` | 可选深底版本；有 logo 且背景深时优先使用 |
| `logoOn` | `cover` / `cover+end`（默认）/ `all` / `none` |
| `footer` | 可见页脚署名 |
| `colorSets` | 具名色板，与 style 的色板结构一致 |
| `fonts` | `display` 与 `body` 的 CSS 字体栈 |
| `note` | 给作者的备注，不是渲染规则 |

当前没有 logo 对象、brandColors、locked、approvedThemes、colorPolicy、imagePolicy 或字体 policy 等字段。
它们不能作为“预留协议”写进文件；未知字段会报错。

## 合并规则

`deck.resolve_theme` 是渲染、输入验证与检查共享的解析入口：

- 品牌色板并入风格色板，同名色板由品牌覆盖；其他风格色板保留。
- `deck.colorSet` 选择合并后的具名色板；品牌新增色板也可直接选。
- fonts 同时提供 display 和 body 才覆盖两者；只给一个不会部分替换，故需要覆盖时给齐。
- logo/footer 提供了才出现；品牌控制出现页，位置与大小由样式/壳决定。

合并规则不会自动协调品牌色与所有皮肤效果。最终文字对比度、深底 logo、
图表分类色和复杂背景都要在真实渲染中检查。没有反白版时不擅自重绘官方 logo。

HTML 内嵌 logo；原生 PPTX 不直接支持 SVG，导出器会尝试栅格化，
仍须查看转换与导出诊断。品牌字体只声明名字不等于已安装或获嵌入授权，见 [字体](fonts.md)。

## 图片资产

图文页 `image` 可写相对 spec 项目的文件路径，或 assets/manifest.json 中的 assetId。
清单当前是 schemaVersion 1，`assets` 为 ID 到 `{file, source, note}` 的映射；
file 相对 assets 目录。manifest 本身就是素材选择，不存在 selected/generated/real 等自动优先级链。

解析在编译时完成并记入 trace；改素材后重新渲染与验收。
已有截图、证据或官方素材优先保真；获授权生成的照片/插画按 [images.md](images.md)
写请求、生成并验收。不要用生成图片代替真实业务截图，也不要将结构图关系交给图片模型猜。

## 交付检查

检查品牌名、logo 版本、可见页、颜色与字体；保留图像比例，避免拉伸、错误反白或低对比。
交付 HTML 要确认所有资源可解析；内嵌 logo 不代表其他图片、字体也自动打包。
无需品牌的项目不添加品牌层，已提供资产无需重新生成或重复向用户确认。
