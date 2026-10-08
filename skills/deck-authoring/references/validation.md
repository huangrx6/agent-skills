# 输入与产物验收

先运行 `validate_spec.py` 检查输入，再用 `check.py` 检查真实 HTML。
check 全部阻塞项通过退出 0，任一失败退出 1；advisories 是提示，需结合设计意图判断。
程序检查不能证明事实正确或视觉完美，最终仍要按 [visual-quality.md](visual-quality.md) 审稿。

```sh
python3 scripts/validate_spec.py deck.spec.json
python3 scripts/check.py deck.spec.json deck.html
python3 scripts/check.py deck.spec.json deck.html --resolved resolved.deck.json
```

## 输入门

闭合字段集、必填内容、类型与数量、风格/品牌解析、具名色板、图表数据和系列形式由
validate_spec 检查。未知字段会失败，不能把未实现的布局、动画或品牌协议混进 spec。
非空 annotations、多于两栏、会丢系列的图表形式等明确拒绝，见 [charts.md](charts.md)。

style/brand 合并后的主题用于渲染与验证。`render --style` 是方向试作覆盖；
正式 spec 应记录最终 style，避免后续 check、素材工具或交付重渲选到不同风格。

## 产物中的阻塞项

| 检查 | 证据与边界 |
| --- | --- |
| 对比度 | 合并后 token 预检 + 实测文字/背景/祖先透明度；统一至少 4.5，minLarge 未单独启用 |
| 页面越界、容器裁切 | 每个元素与其所属页比较，检查自身 scroll/client 与祖先裁切区域 |
| 缺失/不可见内容 | 语义清单对应的 DOM、文本与可见性，不能靠 display:none 消掉碰撞 |
| 安全距离、真实文字重叠 | 按角色外扩的安全盒；有界豁免不等于任意重叠合法 |
| 图片与脚本健康 | 图片实际加载、JS error/rejection/console.error |
| 图表就绪 | 每图 ready 标记与渲染错误；pending/缺图/错误阻塞 |
| 页脚与 logo 锚点 | 实际出现的元素逐页相对页面位置一致 |
| 风格语法 | 声明的 rules 对照实际圆角、阴影、渐变与字重档数 |
| 自定义 layout 词表 | 风格有 layouts 时，检查 spec 名称属于词表或内置结构 |
| 错位与装饰 | 若有 effect 声明，检查错位范围、装饰安全区与图表内禁止错位 |
| 本地资源路径 | 图片绝对路径和 file:// 引用影响便携交付；字体本地路径另给提示 |

图片、渐变和复杂合成背景不能可靠按平面色计算时须逐页目检，未计算不等于验证通过。
装饰和 CSS 伪元素不一定在语义测量清单里，也不能只靠碰撞检查验它们。
图表 ready 证明渲染完成，不证明系列、分类、单位和数值都正确；要对照图与输入。

## 提示项

字号与观看方式是否匹配、标题/正文尺度、网格对齐、过密/过空、结构重复、角色与页型匹配、
素材复用以及字体回退属于需要作者判断的信号。字体回退检测是启发式，可能误报；
确认实际可用字族、中文覆盖和目标宿主效果，不为消除提示而机械修改。

连续相同结构可以服务比较，留白可以服务强调；这些例外应有内容依据。
提示不是错误数量竞赛，也不能全部忽略。

## resolved 契约

`render.py --resolved` 保存当时的语义、字体与几何。
传 `check --resolved` 会将该合同与当前测量对账：页数、元素、几何差异超容差会阻塞。
改过文字、风格、字体、素材或运行环境后重渲并重新生成 resolved，不能用旧合同导新 PPTX。

## ink 与浏览器的分工

```sh
python3 scripts/ink.py /project/styles/project-style/style.json
python3 scripts/measure.py deck.html
```

ink 只预检风格色板的文字/背景对比；check 还会看到品牌合并、CSS 覆盖和 opacity。
所以 ink 通过后，真实页面仍可能失败。不要降低门槛来掩盖低对比问题。
measure 读当前浏览器与字体下的实际盒子；换机器后的结果不在这次测量保证范围内。

## 修复与交付

按照报告页号、元素和证据定位；先修事实/字段错误，再修裁切、重叠、缺图与可读性。
需要调整版式时见 [layout-system.md](layout-system.md)，repair 仅处理有限档位信号，
不包含全部 check 项，也不能替代人工内容调整。

修复后重跑受影响检查、看全篇缩略图和关键页实际尺寸，最后回读用户所需格式。
PDF 页数/尺寸、PPTX 的可编辑性/字体、视频时长等属于导出验收，见 [delivery-formats.md](delivery-formats.md)。
只完成 HTML 检查时不能声称所有格式已验证。
