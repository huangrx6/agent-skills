# 字体选择、加载与交付

字体方案同时包含角色、实际文件、字重和文字覆盖；只写一个字体名字没有完成接入。
自由 HTML 在项目 CSS 接入，分区辅助用 `--deck-display-font` / `--deck-body-font`；
结构化风格才使用 `fonts.display` / `fonts.body`。先表达本次排印意图，
再确认字体实际存在、中文字形完整和目标格式可用。系统 UI 字体也是合法选择，
不因为“来自系统”就需要替换；装饰字更要检查长标题和正文的阅读负担。
与用户讨论字体时先做 [实际文字样张](typography-and-space.md#先确定排印语法)；本篇负责加载与交付。

## 从角色到真实字体

在项目记录中写清标题、正文各用什么字族与字重，中文由谁承担、拉丁/数字是否另配，代码是否需要等宽字。
不要求四套字体；一套覆盖完整、字重适合的字族就可以成立。若另配，比较实际基线、字面大小、笔画和标点，
不能认为相同 CSS 字号就天然协调，也不将长段技术说明全部设为等宽字来营造技术感。

根据参考选择可用字体后，将获准分发的文件放入项目 `assets/fonts/`，逐字重声明 `@font-face`，明确真实的 normal/italic。
可变字体声明其真实支持范围；CJK 分片字体保留完整的 `unicode-range` 和所需文件，不只拷贝拉丁分片。
系统字体方案写明环境依赖；自包含交付使用本地 webfont 或嵌入，不依赖打开时临时访问 Google Fonts。
没有所需字体时先取得文件，或明确替代并重排；不要悄悄回退后继续宣称原风格已经实现。

用实际长标题、两行正文、中文标点、数字单位和图标签组成小样，等待加载完成，再检查实际渲染字体，方法见
[字体核验](typography-and-space.md#确认浏览器实际使用的字体)。样张与代表内容页用同一份 CSS，避免样张好看、正文又回到系统默认。
更换字族后重新测量行宽与版面，不能把它当作只影响外观的最后一步。

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

结构化 `render.py` 可按清单识别本地已就位的字体并注入 @font-face；自由 HTML 的 `web_deck.py` 不替作者下载或注入字体，
需要作者在源文件或项目 CSS 中接入。没有文件时仍会按 CSS 栈回退，部分检查只有启发式提示；
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

## 借鉴 Oh My PPT 的范围

核对版本 [56bc56d4](https://github.com/arcsin1/oh-my-ppt/blob/56bc56d41e6065bbb7fa21f2b3ea407575cb3aae/src/main/presentation/fonts/font-registry.ts)：
字体注册记录用途、拉丁/CJK 覆盖、分类与文件；标题/正文选择通过资源层生成本地 `@font-face` 与 CSS 变量。
借鉴的是“选择—文件—实际渲染”一致，而非固定使用它的 14 款字库或只复制字体名。
其 [PPTX 字体收集实现](https://github.com/arcsin1/oh-my-ppt/blob/56bc56d41e6065bbb7fa21f2b3ea407575cb3aae/src/main/io/html-pptx/font-collect.ts)
按实际文本收集字体、合并所需分片并处理嵌入；缺文件、限制位、转换失败或体积限制仍会跳过。本 skill 的原生 PPTX 尚无这套嵌字实现，不能因借鉴文档就承诺相同能力。
