# 字体：库、用法、以及"分享出去对方没字体"到底影响什么

## 先回答那个问题：取决于交付格式

**结论不是"有影响"或"没影响"，而是逐格式不同** —— 下面每条都是实测出来的，
不是推断：

| 交付格式 | 对方没装字体会怎样 | 依据 |
| --- | --- | --- |
| **PDF** | **完全没事** | 实测：Chrome 把用到的字形**子集内嵌**（PDF 里是 `AAAAAA+SmileySans-Oblique` 这种子集名 + `/FontFile2` 流）。25MB 的霞鹜文楷出成 PDF 总共 **113KB** |
| **PDF（另一种形态）** | 也没事 | 同一份 PDF 里另一款字体走的是 **Type3** 形态（12 个 `/CharProcs`）—— Type3 的每个字形是 PDF 内部的绘图指令，**自包含**，与内嵌字体等效 |
| **PNG 截图 / 贴图版 PPTX / MP4 / GIF** | **没事** | 全部已栅格化成像素，字体信息在导出那一刻就固化进图了 |
| **原生 PPTX** | **有事** ⚠️ | python-pptx 只写字体**名字**（`<a:latin typeface="...">` / `<a:ea>`），不嵌字体文件。对方没装就由宿主应用替换，版面会走形 |
| **HTML** | **有事** | 浏览器用**读者**的字体。`@font-face` 指本地文件时，产物一换目录/换机器就断 |

**所以：要保观感就发 PDF、PNG 或贴图 PPTX；要对方能改字就得接受字体替换，
或者把字体也发给对方装上。**

## 库在哪、怎么取

仓库里只有**清单**（纯文本），字体文件**不进仓库** —— 单款 CJK 字体 5–28MB，
126 款就是 1–2GB，塞进仓库不现实。换台机器跑一次就回来了：

```bash
python3 scripts/fonts.py --list                 # 126 款清单（6 类各 21 款）
python3 scripts/fonts.py --list --urls          # 带上来源页地址
python3 scripts/fonts.py --fetch --tier A       # 取能直接下的那批
python3 scripts/fonts.py --installed            # 本地已就位哪些
python3 scripts/fonts.py --map                  # 字体 ↔ 风格映射表
python3 scripts/fonts.py --embed out.html -o portable.html   # 字体内联进 HTML
```

### 字体放哪儿：**不放在 skill 目录里**

字体文件落在**用户级缓存**，不在 skill 目录 —— skill 目录是**可分发的代码**，
不该长出自下载的二进制（仓库里 h264 编码器早就是这个规矩：编译进 tempdir 按源码
哈希命名）。

解析顺序：

| 顺序 | 位置 | 什么时候用 |
| --- | --- | --- |
| 1 | `$DECK_FONT_DIR` | 显式指定 —— 让**调用方决定下载到哪**，不用改代码 |
| 2 | `~/.config/deck-authoring/fonts/` | 默认，**持久**：单款 CJK 5–28MB，每次重下太浪费 |
| 3 | 临时目录（`--temp`） | 不想在这台机器上留东西（CI / 一次性用） |

```bash
python3 scripts/fonts.py --where          # 看当前会用哪个目录
python3 scripts/fonts.py --fetch --temp   # 这一次放临时目录
DECK_FONT_DIR=/tmp/f python3 scripts/fonts.py --fetch   # 指定任意位置
```

旧的 `fonts/ttf/`（如果之前下过）**仍会被读取**当兜底，但**新下载只进缓存** ——
已经下过的人不用重下。想清掉：`rm -rf fonts/ttf`。

**所以做 PPT 的 AI 可以按实际情况选**：常用就让它落 `~/.config/...`（下次直接有），
临时跑一遍就 `--temp`，也有环境变量这条路可走。

**只有一部分能自动取**：清单里大多数只在这几个字体站上分发，下载要走页面（有的还要
登录 / 领授权）。凡是没能验证直链的，`--fetch` 就**如实说"去来源页拿"**，不编 URL。
已验证能直取的是这几款（都是 OFL / MIT，可以下载、安装、分发）：

| 字体 | 仓库 | 授权 |
| --- | --- | --- |
| 得意黑 Smiley Sans | `atelier-anchor/smiley-sans` | OFL-1.1 |
| 霞鹜文楷 / 霞鹜文楷 TC | `lxgw/LxgwWenKai` / `lxgw/LxgwWenKaiTC` | OFL-1.1 |
| 清松手写体 1–9 | `jasonhandwriting/JasonHandwriting` | OFL |
| Fusion Pixel Font | `TakWolf/fusion-pixel-font` | MIT |

其余 120 款按 `--list --urls` 给的来源页手工拿，放进 `fonts/ttf/` 即可 —— 文件名里
带得上字体名（或拉丁名）就能被 `--installed` 认出来。

## 只走 A 档：没有 license 也能用的那一套

**没有 license 就用严格 A，别碰 B/C，连 `A/B` 也别碰。**

理由是 `A/B` 不等于 A：它意味着"某个来源标了 A、另一个标了 B"，而 B 意味着署名 /
地区 / 禁商标 / **禁嵌入**等限制之一。而**把字体嵌进交付物属于再分发**，比"自己用"
敏感得多 —— 没有 license 的时候，含糊等于不能用。

所以 `--tier A` 与 `--list --license A` 用的是**严格相等**（`license == "A"`），
不是 `startswith`。原先写成 `startswith` 的后果是 `A/B` 一路放过去，而那 4 款里有
`阿里巴巴普惠体 3.0`、`猫啃珠圆体`、`庞门正道粗书体` 这种很容易被顺手用上的字。

```bash
python3 scripts/fonts.py --fetch                 # 默认就是严格 A（要 B/C 得 --tier all）
python3 scripts/fonts.py --list --license A      # 只看纯 A 的
python3 scripts/fonts.py --map --a-only          # 8 套风格各一整套纯 A 方案
```

**`--map --a-only` 是一份完整的替代方案**，不是"删掉几款" —— 每套风格 × display /
body / numeral 三档都给齐，所以"只用免费的"不会变成"有几套风格不能用"。
有测试钉着：那份表里点到的每一款授权必须**恰好是 A**。

> **OFL 唯一要记住的一条**：如果你把**字体文件本身**再分发出去（比如把 `fonts/ttf/`
> 打包给别人），要带上它的版权声明与 License 文本。只是拿它排版、或者把用到的字形
> 子集嵌进 PDF，不受这条影响 —— 那是通行做法。

清单 126 款里严格 A 是 **86 款**；`A/B` 有 4 处落在默认映射上，`B` 有 2 处
（`京华老宋体`、`HarmonyOS Sans`）—— 这些在纯 A 方案里都换掉了。

## 授权：清单标了 A/B/C，但不是"标了就没事"

- **A**（86 款）：OFL / 开源或官方明确广泛免费商用 —— 可以下载、安装、进交付物。
- **B**（28 款）：免费商用但有**署名 / 地区 / 禁商标 / 禁嵌入**等限制 —— 用之前读条款。
- **C**（12 款）：只是"被免费字体平台收录为商免"，授权未经一手确认。

**免费字体的授权会调整**，而把字体嵌进交付物（尤其 PDF / PPTX）属于"再分发"，
比"自己用"更敏感。所以：**正式上线前把每款字体的授权页面 / License 文件一起存下来**，
以最新条款为准。清单里每一条都带来源页地址，就是为了这件事。

## 各风格该配哪款字

完整映射表在 `fonts/mapping.json`（`--map` 可打成人类可读的样式），分两层：

- **styles**：8 套风格 × display / body / numeral 三档该配哪款字，以及为什么
  （比如 `terminal` 必须锁死等宽、`swiss-grid` 只能用**中性到没有性格**的字、
  `paper-ink` 的 400 字重标题只有楷体/明朝体配得上）。
- **categories**：六类艺术字各适合什么场合（国潮 / 毛笔 / 潮流 / 卡通 / 电商 / 科技），
  以及忌讳（像素字字号必须落在整数倍、这一层最"吵"所以一页只用一款）。

**映射表里的每一款都必须在清单里** —— 有测试把关。映射到查不到的字体，等于给了一条
走不通的路。

## 怎么用上：写清单名，渲染时自动注入 `@font-face`

样式栈里直接写**清单里的字体名**：

```json
"fonts": { "display": "得意黑 Smiley Sans, sans-serif", "body": "霞鹜文楷, sans-serif" }
```

渲染时会自动为本地已有的字体注入 `@font-face`；本地没有的**静默跳过**（栈里还有
回退项，不会画出裂图，具体谁顶上了由 `check.py` 的字体回退提示说清楚）。

### 为什么不靠"把字体装进系统"

**因为装了也不一定认。** 实测：把得意黑 cp 进 `~/Library/Fonts`、字体名也写对，
Chrome 仍然回退到 `STSongti-SC-Regular` —— macOS 的字体缓存不会因为复制一个文件
就刷新。`@font-face` 指本地文件立刻生效，而且顺带把 PDF 的内嵌也解决了。

### 四个实测出来的坑（都踩过）

1. **同一个字族有 `.otf` 和 `.ttf` 时，必须选 `.ttf`**。实测同一个得意黑：`.otf`
   那份 Chrome **完全不嵌**（出 PDF 零字体、40KB），`.ttf` 那份正常嵌成
   `AAAAAA+SmileySans-Oblique`（45KB）。所以挑文件有格式优先级。
2. **`format()` 关键字不能一律写 `truetype`**。`.otf` 要写 `opentype`；写错了
   Chrome **直接不用这款字体**，而且**不报错** —— 产物看着一切正常，只有 PDF 里
   少一款字才露出来。
3. **字体自己的 family 名和清单里的中文名不是一回事**：清单写"得意黑 Smiley Sans"，
   字体内部是 `Smiley Sans Oblique`。所以认字体要么读字体文件的 `name` 表（真名，
   本模块就是这么做的），要么用清单里**验证过**的 `match` 记号 —— 不要拿文件名猜。
4. **短记号做子串匹配必然误报**：`AR PL UKai` 的 `ar` 会撞上 `Regul**ar**`、
   `OPPO **Sans**` 会撞上 `Smiley**Sans**`（实测：只下了 4 款却报"已就位 8 款"）。
   所以认字体要求记号 **≥5 字符**，而且两边都归一化。**宁可漏也不要误报** ——
   报"已就位"但其实是回退，会静默渲出一份字体不对的 deck。
