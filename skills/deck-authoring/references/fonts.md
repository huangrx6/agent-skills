# 字体选择、加载与交付

风格的 fonts.display 与 fonts.body 写 CSS 字体栈，先表达本次排印意图，
再确认字体实际存在、中文字形完整和目标格式可用。系统 UI 字体也是合法选择，
不因为“来自系统”就需要替换；装饰字更要检查长标题和正文的阅读负担。

## 按交付格式判断

| 格式 | 字体影响 |
| --- | --- |
| HTML | 本地文件或系统字体换机器可能失效；可内嵌获准使用的字体文件 |
| PDF | 成功嵌入字体/字形时可保留外观，仍需检查缺字与实际导出 |
| PNG / 贴图 PPTX / MP4 / GIF | 字形已经栅格化，接收者无需安装字体，但文字不可直接编辑 |
| 原生 PPTX | 写字体名字与东亚字族，不嵌字体文件；目标宿主缺字体会替换 |

可编辑性与字体可移植性是两件事。需要接收者编辑时，确认对方可用字体；
不满足时说明限制并提供保真预览，不能把贴图版叫作可编辑文字版。

## 清单与缓存

仓库的 fonts/catalog.json 和 fonts/mapping.json 是清单与字感映射，
字体二进制不随 skill 分发。清单数量和可下载范围以命令输出为准：

```sh
python3 scripts/fonts.py --list --urls
python3 scripts/fonts.py --map --a-only
python3 scripts/fonts.py --installed
python3 scripts/fonts.py --where
```

下载目录由 `DECK_FONT_DIR` 指定，默认 `~/.config/deck-authoring/fonts/`；
`--temp` 可临时下载。旧 fonts/ttf 目录如果存在仍作为读取兜底，新下载不写入 skill。

```sh
python3 scripts/fonts.py --fetch
python3 scripts/fonts.py --fetch --only '霞鹜文楷'
python3 scripts/fonts.py --fetch --temp
```

fetch 只处理已有可验证下载实现的字体；其余按 `--list --urls` 查看来源。
找不到直链时明确报告，不把“清单中存在”当成“工具能自动安装”。
下载会联网；仅做本地检查时不必下载全部字体。

## 许可与来源

清单的 A/B/C 是筛选信息，不是法律结论或永久授权。默认 fetch 与
`--list --license A` 使用严格 A；A/B 不被当作 A。`--map --a-only` 给出严格 A 的候选。
正式使用按实际字体文件、来源和当前许可核对允许的用途，尤其是安装、嵌入与再分发。
已有用户提供的有效授权按其范围处理，不需要为了清单分级强行换字。

需要随产物分发字体时保留来源和适用许可信息；工具不会替作者完成许可判断。
不要从一次字体/PDF测试推导所有文件格式、字体或浏览器版本都适用的结论。

## 加载与回退

写清单识别的名字，渲染时本地已就位的字体可自动注入 @font-face。
没有文件时仍会按 CSS 栈回退，check 给出启发式提示；
“没有裂图”不代表首选字体已经生效。核对实际字形、中文覆盖、数字与标点的节奏。

fonts.py 用字体内部名称及受约束的匹配记号识别文件；不要只改文件名就声称字体可用。
同一字族存在多格式时工具有选择顺序，但单次 TTF/OTF 实测不能保证所有字体都相同。
浏览器加载、PDF 嵌入和 PowerPoint 替换需分别验证。

## HTML 字体内嵌

```sh
python3 scripts/fonts.py --embed deck.html -o portable.html
```

命令将现有 @font-face 的本地 URL 替换为数据，保留字重与样式，支持相对路径和 file:// URL，
并检查整个生成 HTML 的体积。超过限制会拒绝，不应删掉必要字形来凑体积。

它只处理字体，不打包图片或所有外部资源，也不自动保证许可与跨浏览器一致。
交付前把文件放到另一目录、确认资源可解析，再检查实际页面；
PDF 还应检查嵌入结果，原生 PPTX 仍需目标宿主回读。
