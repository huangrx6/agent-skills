# AI PPT 品牌与视觉资产统一协议（全文落地）

适用：PPT / HTML Deck / PDF / MP4 / GIF。目标：把 **Content / Style / Brand /
Generated Assets** 四层分开管理，避免颜色、字体、Logo、配图、动画互相覆盖；
同时建立"AI 只生成配图提示词 → 人工/外部模型生成 → 放入约定目录 → 渲染器自动
取用"的稳定工作流。规范里**规则在、本仓库未接机**的机制，在节标题上用【约定】标出。

> 本仓库字段口径：规范示例是嵌套形（`logo:{default,inverse,mark,logoOn}`、
> `brandColors`、`colorPolicy`…）；实际 `brand.json` 用**更扁的封闭集**
> `version/label/logo/logoInverse/logoOn/footer/colorSets/fonts/note`——
> 映射：`logo.default→logo`、`logo.inverse→logoInverse`、`logoOn` 同名。
> 嵌套形与 policy 字段是协议预留，未实现（§6/§7/§9/§10/§34）。

## 1. 总体架构

四层长期层 + 两个运行时解析层：

```text
Content（说什么）→ Style（怎么表达）→ Brand（是谁）→ Asset（拿什么文件画）
        → Resolver（Theme / Asset）→ Renderer（HTML/PPTX/PDF/MP4/GIF）
```

| 层 | 负责 | 不负责 | 本仓库落点 |
| --- | --- | --- | --- |
| Content | 标题、正文、数据、事实、页面目的 | 颜色、Logo、字体文件、图片路径 | spec / 三份规划 JSON |
| Style | 构图、排版性格、色彩语法、图片/图形/动画语言 | 公司身份、官方 Logo、品牌锁定色 | deck 的 `styles/<name>/` |
| Brand | Logo、品牌身份色、字体政策、署名、官方主题、视觉约束 | 页面坐标、布局（`layout`）、具体构图 | `brands/<name>/` |
| Asset | 本 deck 真正用的图片/截图/插图文件 | 决定品牌规范、决定风格 | spec 同目录的图文件 |

**核心原则**：Brand 定义"是谁"，Style 定义"怎么表达"，Content 定义"讲什么"，
Asset 定义"最终拿什么文件来画"。Theme Resolver ≈ `deck.py` 的
`merge_color_sets` / `merge_fonts`（原 `brand.py` + `compile.py` 已合并进 deck.py）；
Asset Resolver ≈ `image_source.py --check`。

## 2. 冲突处理总原则

不用"某层整体覆盖另一层"的粗暴规则；统一
Hard Constraint > Semantic Requirement > Style Grammar > Creative Preference：

```text
用户明确硬要求 > 品牌锁定资产（logo 本体） > 品牌 Locked Identity > 内容事实与语义
    > Style Grammar > Mood/Page Type > 外部灵感 > AI 自由发挥
```

落地即 §5 的字段级融合表——Brand 不直接覆盖 Style；Style 不改 Locked Asset；
**Renderer 不临时决定任何事**（它只消费已解析的 tokens）。

## 3. 品牌层的正确职责

品牌层只存"身份"和"不可丢失约束"。目录 `brands/<name>/`（logo + brand.json；
`assets/product|screenshots|official`、`fonts/` 子目录按需自建）。`brands/`
本身按**同样的解析根**找（先 `<spec 所在目录>/brands/`，再 `<当前目录>/brands/`，
再 skill 的 `brands/`，另有 `DECK_BRANDS` 可注入额外根）—— deck 项目 = spec 所在
目录，从任何 cwd 跑同一个 spec 都命中同一套。品牌层可以不存在：`deck.brand` 不写
就全走 Style + Color + Typography + Asset Rules。

> ⚠️ **仓库里没有任何示例品牌**。纪律：**示例资产必然被当成可用资产**
> （示例 logo 会被直接带进真实交付），所以不留任何示例。
> 品牌一律由用户提供：`brands/<name>/` 放 logo 文件 +
> `brand.json`（封闭字段集见下）；`deck.brand` 不写就整层不生效 —— 这是合法状态。
>
> ⚠️ **logo 与品牌素材一律由用户提供**：不要生成、不要"先放个占位的"。

## 4. brand.json 结构【嵌套形=约定】

字段集封闭，未知字段**直接报错**（`BRAND_FIELDS`，多一个键就失败，不是静默
忽略）。实际形状：

```jsonc
{"version": 1, "label": "某某科技",
 "logo": "logo.svg", "logoInverse": "logo-inv.svg",   // 相对 brand 目录
 "logoOn": "cover+end",                                // cover|cover+end|all|none
 "footer": "© 2026 某某科技",
 "colorSets": {"brand": {"primary": "#0B5FFF", /* … */}},
 "fonts": {"display": "…", "body": "…"},               // 给了就整体替换（见 §10）
 "note": "写给人看的备注"}
```

规范的 `brandColors{locked}` / `colorPolicy` / `approvedThemes` / `imagePolicy`
是协议预留【约定】——要哪个先出真实冲突案例（见各节）。

## 5. 品牌颜色与 Style 的融合

禁止两条旧规则：Brand Palette 整体覆盖 Style Palette；品牌色全加、Style 原色
一个不删（颜色膨胀）。三层模型落地：

- **A 身份色**：`brand.colorSets`（如 brand.primary #0B5FFF）；
- **B Style 色彩语法**：`style.json` 的 `colorStructure`（背景模式/色相结构/
  饱和度/对比度——不硬编码品牌色）；
- **C Resolved Theme**：`merge_color_sets` 合并出最终色板表（同名键品牌赢，
  风格原有色板一个不删），**只有这层给 Renderer**。

## 6. 品牌颜色强度（colorPolicy.strength）【约定】

strict（品牌主导）/ strong（品牌明显、Style 可扩展）/ balanced（品牌做
Identity/Accent，Style 保留表达力，推荐默认）/ subtle（只在 Logo 与重点）。
现状是固定策略"并入+同名覆盖"（介于 balanced/strong）；真出现"品牌色与风格
语法打架"的案例再实现四档。

## 7. Locked Color 与派生颜色【约定】

locked=true 的 HEX 必须被真实使用（Logo 关联/关键 Accent/识别线/重点数字），
不得修改；locked=false 可在 OKLCH 派生（Hue 保持，Lightness ±3~15%，Chroma
±5~25%）。未实现：当前同名即覆盖、无锁定语义；需要时先过 `ink.py` 的对比度检查
（`ink.py <style.json>`，任一色板不达标退出码 1）再手工合。

## 8. 品牌色与渐变【约定】

品牌色可作 Gradient Anchor，但不包办所有 Stop（Brand Blue + Style Companion +
Neutral → Ink Black → Brand Blue → Silver 这类）。品牌负责识别，Color Engine
负责 Stop 数量/方向/明度/冷暖。现状：风格自带渐变语法，品牌色经 colorSets 进入。

## 9. Approved Theme【约定】

客户提供完整官方主题（light/dark 的 background/textPrimary）时优先于 Style
自带配色（`colorSets`；spec 只选色板名，无 auto 派生），但只锁颜色应用，
不锁构图/字号跨度/图形/图片/动画语言。未实现；近似做法：把官方色写成一套
`colorSets` 并入同名覆盖。

## 10. 品牌字体与 Style【hybrid/style_allowed=约定】

fonts.policy：strict（Display+Body 都品牌字体）/ hybrid（正文品牌、标题允许
Style Display）/ style_allowed（品牌字体只用于署名与 Logo 配套）。**现状=
strict**：给了 `fonts` 就整体替换（display 与 body 一起换）——只换一半会得到
"标题是品牌字体、正文不是"的半吊子，比不换更难看；只给一个就当没给。
hybrid 是协议预留。

## 11. Logo 规则

Logo 永远属于 Brand Asset。禁止：让图片模型生成 Logo、AI 重绘、用文字猜、
改颜色/比例/形态（除非品牌本身提供可变色规范）。落地：logo 是 `brands/`
目录里的文件，base64 内嵌进产物；图像契约的负面清单里就有 no logo/no
watermark（§18），生成图永远不带 Logo。

## 12. Logo normal / inverse 选择

不判整页背景，判 **Logo 实际 Bounding Box 背后的局部区域**：纸色相对亮度
< 0.45 走反白版（实测阈值：本仓库深底 #000000/#0A0A0A 亮度 0.000/0.003，
浅底最低 #F4F4F4 亮度 0.905，分得干净）。深底 + 没给反白版 → `check.py`
提示（修法在品牌那边补 `logoInverse`，不是改版面）。两版都不达标时的正解：
调 Logo 区域背景或加局部保护区，**不是擅自改 Logo**。

## 13. Logo 的"出现"与"位置"分离

Brand 决定 `logoOn`（cover | cover+end | all | none，缺省 cover+end，封闭集）；
Style/Layout 决定位置、尺寸、安全边距、与标题的关系。品牌里**不存在**
logoTop/logoRight/logoX/logoY 这类字段——想挪去改 `skin.css` 的 `.brandlogo`
（约束高度不约束宽度：logo 多是横长条，锁高才能让宽高比自然展开）。

## 14. 配图必须成为独立 Asset Pipeline

AI 不"随便找一张图"。落地：

```text
PagePlan/spec 的 image 字段 → image_source.py --brief（Image Prompt Builder）
  → image-brief.md（Request）→ 人/外部模型生成 → 放 spec 同目录
  → image_source.py --check（Asset Resolver + QA）→ Renderer 取用
```

AI 负责把"需要什么图"描述准确；生成在系统外完成（不配 provider 就永远不会
调生图模型——这是设计不是疏漏）。

## 15. 图片生成发生在布局之后

先知道图片角色、盒子比例、视觉焦点、文字在哪边、留白、裁切方向，再写
Prompt。落地：`--brief` 从**渲染后的实测插槽几何**算（量出来的盒子 ×2 =
minWidth、目标比例、文字列位置），禁止"先生成图再想怎么塞"。

## 16. 图片角色

规范十角色（hero/supporting/background/evidence/product/portrait/
illustration/diagram/texture/decoration）。落地：spec 的 `type: content-image`
页即"这一页的主视觉槽"；角色细分由 brief 的 purpose/构图字段承载。

## 17. AI 图片与真实资产必须分开

Generated（氛围/抽象/概念/3D/背景——非事实性）走契约流程；Official/Factual
（品牌 Logo、官方产品截图、官方 UI、真实人物照、客户提供的图、法务要求准确
的视觉）**默认不得用生成图替代**——走人提供的文件。

## 18. 生成图中禁止内嵌正式文字

PPT 正式文字由 Renderer 排（可搜索/可翻译/可编辑），不要求图片模型生成。
Prompt 负面清单：**no text / no logo / no watermark**。原因：图片模型文字
不稳定、字体不可控、品牌字体无法保证、后续无法编辑。

## 19. 文字留白区

左文右图 → brief 的构图字段写明主体偏哪侧、哪侧留干净负空间（从实测插槽
几何来，不是猜）。生成图服务布局，不是布局迁就图。

## 20. Image Request 标准结构

规范的 Request JSON（id/slideId/role/purpose/subject/composition/style/
colorIntent/constraints/output）落地为 `image-brief.md` 的**结构化小节**
（每图一块：用途/构图/管线提示/中英 Prompt/参数块），字段一一对应、
人直接可读可贴。

## 21. Prompt Builder

输入 = 内容语义 + 页型 + 图片角色 + **实测布局** + 风格气质 + 已解析色彩 +
品牌图片约束；输出 = Positive Prompt + Negative Prompt + 生成参数 + 输出
契约（文件名/最小宽度/比例/透明度）。

## 22. Prompt 结构

Subject → Scene → Composition → Spatial → Camera(可选) → Lighting →
Color → Style → Detail → Constraints。**不机械堆词**；镜头行默认不输出
（要加自己贴，合同里留了位置和示例）。

## 23. Prompt 示例（规范样例，同我们的写法）

> A premium futuristic visualization of a unified AI inference platform, a
> central computational core connected to distributed model nodes, …, clean
> negative space covering roughly the left 35% for presentation text, …,
> dark neutral foundation with restrained brand-blue accents, …, no text,
> no logos, no watermark, avoid generic blue-purple AI gradients.

## 24. Prompt 不写什么

不写 PPT 正式标题、品牌 Logo、页码、正文、品牌官方字体名（只可描述气质）、
Renderer 才处理的 UI 元素。**图片负责画面，Renderer 负责信息**。

## 25. 约定目录

规范推荐 `projects/<deck-id>/assets/{requests,generated,provided,…}`；
本仓库简化为**产物与 spec 同目录**（deck.spec.json + 图文件并排，交付整体
拷走不断链）。用户流程相同：读合同 → 按 Prompt 生成 → 用规定文件名放好 →
Renderer 自动取。

## 26. 文件名必须稳定

禁止 final.png / new.png / 好看的图2.png；统一 `<语义名>.<ext>`——spec 的
`image` 字段即文件名，**同一个名字就是同一个语义槽位**（brief 与 spec 一一
对应，`--check` 按名验收）。

## 27. 多版本管理【约定】

`__v01/__v02` 候选 + manifest 选定；无 selected 时单候选自动用、多候选阻塞。
未实现——现行约定：一个槽一个文件名，换图就换文件（删旧防重复检查误报）。

## 28. Asset Manifest【约定】

`{version, assets:{id:{kind,role,request,required,selected}}}` 未建独立
manifest；spec 的 image 字段承担"必需素材清单"职责（required 语义见 §30）。

## 29. Asset Resolver

解析优先级落地：spec `image` 字段（精确文件名）→ spec 同目录查找 → 品牌资产
（logo 走 brands/）。**禁止缺图自动去网上随便找**——本仓库没有 web 回退开关，
结构上不可能发生。

## 30. 图片缺失策略

`content-image` 页 = required=true：缺图**阻塞**（`--check` 明说缺哪个文件、
期望路径；渲染前 `check.py` 也拦 content-image 无 image）。required=false 的
可选素材当前不存在于 schema——要加再议。

## 31. 禁止静默替换

找不到图、尺寸太小、比例严重不匹配、品牌图被普通图替代、Logo 缺失——一律
warning 或 blocking，**绝不静默**。落地：`--check` 的四类阻断（缺文件/宽度
不足/比例不对/同名重复）+ `check.py` 的 logo 三条（§50）。

## 32. 图片质量检查

已查：文件存在、宽度（minWidth）、宽高比（与插槽目标比）、同名重复。
未查【约定】：解码深度、alpha、拉伸/裁切程度、主体被文字遮挡、负面空间
满足度——这些需要视觉判读，留给抽帧人审。

## 33. 图片裁切规则【约定】

Prompt 阶段对齐比例（实测插槽比）；渲染 `fit` 记录 focalPoint 优先保留焦点、
禁只用中心裁切——未实现 focalPoint 字段，当前靠比例在合同阶段对齐。

## 34. Brand Image Policy【约定】

`imagePolicy{preferred,avoid,allowGeneratedLogo:false,…}` 未实现；原则已由
§17/§18 承担（Logo 永不生成、事实素材不生成替代）。品牌要约束图风时写在
`note` 里给人看。

## 35. Style Image Grammar

Style 负责图片语言不定内容：风格的气质/管线提示（双色调、网点、纸感）写进
brief 的 Style/Constraints 段——Content 决定画什么，Style 决定怎么画，Brand
决定哪些身份元素不能错。

## 36. 图片与品牌色的关系

Prompt 可继承品牌色作 anchor，但禁止"整张图都必须是品牌蓝"；写法是
"restrained brand-blue accents with complementary neutrals"——不破坏 Style。

## 37. 官方产品 / UI 截图

属于 provided/brand asset，不是 generated。禁止让模型重画官方 UI、猜界面、
改关键业务数据；允许外框/阴影/遮罩/透视 mockup，但**截图像素本身不被篡改**
（除非用户明确要求）。

## 38. 真实产品图

要"精确产品外观"优先官方产品图；生成模型只适合围绕真实产品做环境扩展，
不是重新发明产品。

## 39. 图片生成与 Brand Logo 永远分层

封面要"品牌 Logo + AI 主视觉"时：Generated Hero Image + **Renderer 叠印
原版 Logo**；禁止让图片模型把 Logo 画进去（画出来的是猜的）。

## 40. 页面 Image Request 的生成时机

Content → Storyline → Page Planner → spec（Layout 已定）→ 插槽几何实测 →
Prompt Builder → Request（image-brief.md）→ 等人生成 → `--check` →
Renderer。对应 `pipeline.md` 的 ⑤⑥ 站。

## 41. 生成图状态

pending/ready/selected/rejected/missing 的机器状态未建；等价物流：brief
发出=pending，`--check` 通过=ready，缺文件报错=missing（阻塞）。

## 42. 图片 QA 不合格时

不自动改整页。按序：换更大图/对齐比例（重生成）→ 调整图片盒子（改 spec）→
调蒙版/overlay → 重新生成 Prompt → 请求重生成。**主体位置完全错 → 回
Prompt Builder 重写，不靠裁切硬救**。

## 43. 统一资产 ID

PagePlan/spec 的 `image` 值 = brief 里的文件名 = 磁盘文件名，三处一致
（规范四处含 manifest，本仓库无独立 manifest）。

## 44. Renderer 不负责生成 Prompt

Prompt Builder（image_source）→ Request；Asset Resolver（--check）→ File；
Renderer → Draw。**Renderer 只接受已解析的 asset 路径，禁止临时调图片模型**
（结构上就没这条路径）。

## 45. 导出规则

HTML/PDF：logo base64 内嵌（产物自包含，挪动不断链），SVG 最好。PPTX：
python-pptx 不吃 SVG → **按实测盒子尺寸 ×2 栅格化**（Chrome 现场做；
传实测 w×h 截图 —— 标量窗宽会截成方形、丢宽高比且不报错）。栅格化保持
宽高比、按实际盒子、≥2×，**不得
固定方形窗口**。栅格化不了明说跳过，不静默少一个 logo。

## 46. 品牌与图片的最终冲突判定

品牌硬禁止 > 内容真实性 > Page Type > Style Image Grammar > Creative
Preference。品牌禁 cyberpunk：即使 Style=futuristic 也不能用，但可走 clean
futuristic / premium digital / technical editorial。

## 47. 与 Color Rules 的接口

Brand 不输出最终 Theme。Color 侧输入 = 身份色（colorSets）+ Style 色彩语法
（colorStructure）→ 合并出 Resolved 色板 → Renderer 只读最终结果；Prompt
Builder 只读已解析色彩（§36 的 anchor 写法）。

## 48. 与 Typography Rules 的接口

Typography 输入 = 品牌字体政策（fonts）+ Style 字栈 + 语言/密度 →
`merge_fonts` 整体替换或保持 → Renderer 只读最终字栈。

## 49. 与 Motion Rules 的接口

生成图可参与 Mask Reveal / Image Reveal / Subtle Scale，但**内容不得因动画
变形**。落地：imageReveal preset = 横向揭开 + `1.02→1` 的 settle——可以；
skew 40°——管线里根本不存在（preset 写死，没有随机变形）。

## 50. check.py / QA 建议检查

| 判据 | 级别 | 状态 |
| --- | --- | --- |
| Logo 压住文字（实测矩形相交） | **阻塞** | ✅ |
| 深底 + 没给反白版 | 提示 | ✅ |
| 位图 logo 被放大渲染 | 提示 | ✅ |
| Logo 文件在不在 | 加载时报 | ✅（带具体路径） |
| required asset 存在/宽度/比例/重复 | **阻塞** | ✅（`--check`） |
| 锁定色被非法修改 / 字体政策满足 | — | 约定（无 locked/policy 机制） |
| 图片可解码/拉伸/遮挡/负面空间 | — | 约定（抽帧人审） |

## 51. Do NOT

**Brand**：不把品牌色/字体写进 spec（deck 只有 `brand` 一个入口，字段封闭，
写了会被指名报出）；不在品牌里写位置（logoTop/logoRight 不存在）；不让品牌
色无条件覆盖 Style（字段级同名覆盖）；不让 Style 改 locked asset；**不让图片
模型生成 Logo**。
**Image**：不让 LLM 随机找图塞页面（没有这条路径）；不先生成图再定布局；
不让图片模型承担 PPT 正式文字；不让生成图替代官方截图/Logo/事实素材；不用
final.png/test2.png 不稳定名；**不在素材缺失时静默换图**；不让 Renderer
临时生成 Prompt。

## 52. 最终推荐工作流

```text
Content → Storyline → Page Planner → Style → Brand → Theme（合并）
  → Layout（spec+实测插槽）→ Asset Requirement（--brief）
  → 人/外部模型生成 → --check 验收 → Renderer → Visual QA → Repair
  → PPTX / HTML / PDF / MP4 / GIF
```

## 53. 一句话定义

**Brand 负责身份，Style 负责视觉语言，Content 负责语义，Prompt Builder 负责
描述所需图像，用户或外部模型负责生成实际图片，Asset Resolver 负责从约定
目录准确取用，Renderer 只负责把已解析好的视觉资产画到页面上。** 由此：品牌
不破坏 Style、Style 不篡改品牌、图片生成不污染 Renderer、Prompt 与图片一
一对应、素材可复现可替换可回归、同一品牌跨 deck 复用、同一 deck 换 Style
不丢品牌身份。

---

## 起步：做一个品牌

```bash
mkdir -p brands/acme
cp 你的logo.svg brands/acme/logo.svg
cp 你的反白logo.svg brands/acme/logo-inverse.svg
$EDITOR brands/acme/brand.json     # 照 §4 的形状写
python3 scripts/deck.py acme                 # 看摘要：logo 认到没、色板加了几套
```

然后在 spec 的 `deck` 里加一行 `"brand": "acme"`，跑五道门（`pipeline.md`）。

## 署名（footer）

渲染成左下角页脚一行里的一块（`.footrow` 里的 `.brandfoot`）。和页脚**并排**
而不是分居两端：多数风格把右下角给了巨号页码，署名放右下会压页码；页脚一带
本来就该放"文档元信息"。
