# 项目风格与规格契约

内容写在 deck.spec.json；字号、配色、字体和构图视觉写在项目的
`styles/<name>/style.json` 与 `skin.css`；组织身份放在可选 brand。
本篇给出当前实现的接口，不是成品风格模板。图表、素材、品牌分别按对应参考文档补充。

## 风格查找

`deck.style` 必填，可用名字或包含两份风格文件的目录路径。按顺序查找：

1. `DECK_STYLES` 指定的额外根（平台路径分隔符）。
2. spec 所在目录的 `styles/`。
3. 当前工作目录的 `styles/`。
4. skill 自身的 `styles/`，仅供用户显式托管的全局风格。

每份新 deck 在项目内设计风格；不要向 skill 写本次项目文件。
没有内置默认风格。`--style /tmp/direction-a` 可用于临时探索，正式采用后搬入项目并更新 deck.style。
从其他 cwd 调用也应解析到同一项目风格；环境变量可覆盖它，因此交付前记录实际采用的目录。

## style.json

下面是可解析的接口示例，数值只是示意，需根据本次观看场景与内容量设计；仍需配套 skin.css：

```json
{
  "version": 1,
  "label": "项目风格",
  "temperature": "清晰克制",
  "reference": "本项目内容与观看场景",
  "note": "接口示例，需按实际内容设计皮肤",
  "colorSets": {
    "main": {
      "primary": "#145A46",
      "secondary": "#433A32",
      "background": "#FFFFFF",
      "text": "#202020"
    }
  },
  "contrast": {"minBody": 4.5},
  "type": {
    "cover": 84, "compact": 48, "small": 38, "end": 84,
    "subtitle": 24, "bulletLarge": 30, "bullet": 24, "bulletSmall": 20,
    "colTitle": 26, "nodeLabel": 20, "nodeNote": 16,
    "chartValue": 16, "chartLabel": 14, "caption": 16, "foot": 14
  },
  "fonts": {"display": "sans-serif", "body": "sans-serif"},
  "viewerBackground": "#141414",
  "motion": {
    "easing": "expoOut", "cssEase": "cubic-bezier(0.16, 1, 0.3, 1)",
    "enterMs": 520, "staggerMs": 70, "titleHoldMs": 260,
    "holdMs": 2600, "readPerItemMs": 760
  }
}
```

运行所需核心块是 colorSets、type、fonts、viewerBackground、motion；
保留 version、label 和说明元数据便于素材 brief 和维护。style 当前没有独立的完整闭合 schema 验证器，
不要将“JSON 能解析”当成“风格已验证”。缺键和非法值会在各消费路径暴露。

| 字段 | 实际语义 |
| --- | --- |
| `colorSets.<name>` | primary / secondary / background 必需；text 可显式指定，省略时由 ink.text_color 派生 |
| `contrast.minBody` | 色板预检门槛；实际文字仍要求至少 4.5，不能通过降低它绕过可读性 |
| `type` | 示例中 15 个档位覆盖壳/皮肤所用字号，可增加自定义档位 |
| `fonts.display` / `fonts.body` | 完整 CSS 字体栈；必须核对实际加载和中文覆盖 |
| `viewerBackground` | 浏览器中幻灯片外侧底色 |
| `motion` | 七项时间/缓动参数，见 [animation.md](animation.md) |
| `label` / `temperature` / `reference` / `note` | 说明或素材提示词的输入，不是自动创作规则 |

`contrast.minLarge` / `largeTextPx` 不单独参与当前判定。
`ink` 可留设计说明，但不存在根据 ink.derivation 自动切换混色算法的机制；
决定显式文字色的是 colorSets 中的 text。派生色是视觉效果，不是物理印刷精确模拟。

### 可选默认值与语法

| 键 | 形状与用途 |
| --- | --- |
| `titleTiers` | 页型到 type 档名的映射；逐页 titleTier 优先 |
| `bulletDefault` | content-text / content-image 的缺省条目档，默认 bullet |
| `layouts` | 自定义 layout 名称数组，供 check 校验拼写 |
| `rules.corners` | square / rounded / any |
| `rules.shadow` | none / soft / any |
| `rules.gradients` | none / any |
| `rules.weightSteps` | 实际文字字重最多几档 |

默认标题档：title→cover，content-text→compact，end→end，其余→small。
two-column 缺省条目档是 bulletSmall，可由该页 bulletTier 覆盖。
脚本不按条数自动缩字；未声明字段的有限修复需显式执行 `render --repair`。
没有 rules 声明就不做该项语法检查；这不是要求所有风格都直角、无阴影或无渐变。

### 可选效果

无效果时直接省略，不必声明全零对象。

| 块 | 当前消费的字段 |
| --- | --- |
| `misregistration` | offsetRangeX / offsetRangeY / rotationRange：各为两端数值区间，按 seed 派生 |
| `texture` | grainOpacity 区间、grainBaseFrequency；与 skin 的纸纹实现配合 |
| `decor` | kind 为 halftone-circle 或 accent-block；sizes 尺寸池、types 适用页型、zones 落点 |

halftoneDotSize 和 misregistration.blendMode 没有被当前脚本消费，不能依赖它们改变效果。
效果应服务当前方向。装饰不承载业务事实，不能压正文，图表内部不做错位叠印。
所有效果都要验证最终导出；原生 PPTX 不复刻任意 CSS 或滤镜。

## skin.css

壳提供结构，皮肤负责视觉。公共钩子包括：

| 钩子 | 对象 |
| --- | --- |
| `section.slide[data-page]` | 页型 |
| `[data-layout]` | 声明的布局，未知名字使用缺省结构 |
| `.title` / `.subtitle` | 主标题、副标题 |
| `.bullets` / `.bullets.small` | 正文列表 |
| `.col` / `.colTitle` | 双栏与栏标题 |
| `.tl .label` / `.tl .note` | 时间线节点 |
| `.imgwrap` / `.chartwrap` | 图片与图表区域 |
| `.chartcap` / `.chartsrc` | 图注、图表来源/单位 |
| `.footrow` / `.foot` / `.brandfoot` / `.brandlogo` | 页脚与品牌元素 |

render 注入 `--paper`、`--text`、`--accent`、`--accent-2`、`--display`、`--body`、`--viewer`，
以及全局 `--t-<档名>`、逐元素 `--s-title` / `--s-bullet` 等变量和 grid 的间距变量。
局部变量使用前确认作用域，或用全局 token 回退，例如：

```css
.bullets {
  font-family: var(--body);
  font-size: var(--s-bullet, var(--t-bullet));
  line-height: 1.55;
}
```

不要因缺少局部变量让整条 font shorthand 失效。
列表默认圆点由壳 reset，皮肤可用 `li::before` 画标记；正文不要再手填装饰符号造成双标记。
注意 CSS 伪元素不一定进入检查清单，原生 PPTX 也不会自动重建它们。

页脚/品牌元素由壳锚定。避免 `.slide > * {position:relative}` 等通配破坏定位；
只抬正文层就把选择器收窄到正文容器。若有意移动 chrome，用准确选择器并保持逐页一致。
壳 CSS 在 skin 后注入，覆盖需看实际选择器优先级，不能仅凭文件先后猜结果。

截图、结构图与照片的 object-fit 不应一概相同。需要完整证据用 contain，照片可用 cover 并检查焦点。
图片/渐变上的文字不能只看 token 对比度，必须审查真实叠层。

## 字号与观看场景

1600×900 是画布，不是字号处方。先看 live（投影）、async（桌面）或 printable（打印），
再设计封面、正文、图注的层级。接口示例中的 14px 图表标签只适合近距离密集阅读的试排，
不能直接作为投影稿的默认值。

用最密内容页与最长标题试排，图表最小标签也必须读得清；
装不下时先收内容、换结构或拆页，最后才换较小档。字体加载/回退会改变换行，
检查浏览器实际用到的字体，并在目标格式中复核。详细字体与嵌入流程见 [fonts.md](fonts.md)。

## deck.spec.json

以下完整示例与上面的 project-style/main 对应；它示范输入结构，不是业务事实：

```json
{
  "deck": {
    "style": "project-style",
    "colorSet": "main",
    "seed": 11,
    "title": "项目说明",
    "delivery": "async",
    "slides": [
      {"type": "title", "title": "项目说明", "subtitle": "讨论范围与下一步", "role": "cover", "visual": {"kind": "none"}},
      {"type": "content-text", "title": "先确认范围，再开展验证", "bullets": ["明确需要验证的问题", "为每项结论保留来源"], "role": "actions", "visual": {"kind": "none"}},
      {"type": "end", "title": "确认下一步", "role": "closing", "visual": {"kind": "none"}}
    ]
  }
}
```

顶层仅 deck；deck 允许 style、colorSet、seed、title、slides、brand、note、delivery。
style 与具名 colorSet 必填，不能写 auto；slides 必须非空。delivery 可选 live/async/printable，
用于观看场景提示，不自动改字号。note 为作者备注；brand 见 [品牌](brand-assets.md)。

每页共通字段：type、title、role、visual、notes，及兼容字段 color（只能是 overprint）。
role 的闭合词表见 [planning.md](planning.md)；notes 是讲稿，不占版面。
visual 的字段为 kind / intent / note / ratio，kind 仅 none/data/evidence_image，
ratio 是比例字符串；必须与页型和素材意图匹配。

| type | 该页额外字段 |
| --- | --- |
| `title` | subtitle、titleTier |
| `content-text` | bullets、titleTier、bulletTier |
| `content-image` | bullets、image、caption、layout、titleTier、bulletTier |
| `two-column` | columns（至多两栏，每栏 title + bullets）、layout、titleTier、bulletTier |
| `timeline` | nodes（label + 可选 note）、titleTier |
| `chart` | chart、data 或 series、unit、caption、intent、message、emphasis、annotations |
| `end` | titleTier |

图表不接受 titleTier；message 写了就作大标题，原 title 作数据集名，unit 在图旁可见。
完整图表字段、数量与支持范围见 [charts.md](charts.md)。annotations 当前只能空或省略。
素材的 image 为项目相对路径或 assetId，manifest 解析见 [images.md](images.md)。
layout 的内置结构、自由钩子、候选与修复见 [layout-system.md](layout-system.md)。

字段集闭合：x/y/width/height、像素字号、色值、旧 variant、deck.mood 都不是合法写法。
逐页只选档名和布局；更换视觉数值改 style，品牌身份改 brand，不在 spec 中另建一套样式系统。

## 验证与可复现

```sh
python3 scripts/validate_spec.py /project/deck.spec.json
python3 scripts/ink.py /project/styles/project-style/style.json
python3 scripts/render.py /project/deck.spec.json -o /project/deck.html --resolved /project/resolved.deck.json
python3 scripts/check.py /project/deck.spec.json /project/deck.html --resolved /project/resolved.deck.json
```

同输入与 seed 的派生可复现；浏览器、字体或资源变化仍可能改变几何。
替换样式后重新生成 resolved，重新看真实页面与最终导出，不把缓存或旧截图当成新结果。
