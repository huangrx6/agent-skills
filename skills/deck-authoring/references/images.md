# 素材契约与验收

每页决定视觉载体：`none`（纯文字）、`data`（原生图表）、`evidence_image`（外部素材）。
要图或图表时，`visual.ratio` 写清槽位比例，例如 `3:2`、`1:1`。素材接入契约不决定创作方法。

## 按角色选择来源

| 素材 | 优先来源 | 要保住什么 |
| --- | --- | --- |
| 产品界面、报告、现场证据 | 用户或项目已有真实素材 | 内容与颜色真实，不用生图伪造 |
| 架构、流程、拓扑 | 结构化节点与连线、可用的 diagram 工具 | 关系准确、标签可读、可编辑源可交付 |
| 照片、插画、氛围、主视觉 | 真实素材或获授权的生成模型 | 主体、焦点、构图与风格一致 |
| 数据图表 | chart 页型 | 原始数值、类别、系列与单位 |
| 装饰、线条、页码 | skin.css / decor | 服务层级，不承载业务事实 |

页面标题与正文用真实文字，不把整页信息烤进配图。外部结构图作为素材接入时仍可能
在 PPTX 中是图片，应保留其编辑源并说明这一边界。不要为“丰富页面”增加无关图。

## 流程

已有真实素材先登记并验收，无需重生成。需要创作素材时：

```bash
python3 scripts/image_source.py --brief deck.spec.json
# 填写生成的 prompt，生成或由用户提供文件后：
python3 scripts/image_source.py --check deck.spec.json
```

`--brief` 生成 `image-brief.md` 与 `assets/requests/<槽位id>.json`。量槽位用的临时图只存在于
临时目录，不会作为交付素材。用户负责出图时给出完整提示词合同；工具负责出图时自行填写占位符。

可用后端的调用：

```bash
python3 scripts/image_source.py --generate deck.spec.json
python3 scripts/image_source.py --generate deck.spec.json --provider-cmd '你的命令 --prompt {prompt} --out {out}'
```

后端优先级：`--provider-cmd`，然后内置 MiniMax（`MINIMAX_API_KEY` 或 `MINIMAX_CN_API_KEY`）；
可选 `MINIMAX_API_HOST` / `MINIMAX_IMAGE_MODEL`。密钥只读环境变量，不落盘。
无后端、提示词仍有 `〈…〉` 或 `<…>` 占位符时停止生成，并说明需要补什么。
已有目标文件或命中相同请求缓存时跳过；生成只读取合同，不把填好的提示词覆盖回模板。
先有用户对生成任务的授权，再执行可能付费的生成命令；普通素材检查不需要重复确认。

## 请求合同

请求 schemaVersion 为 2，生成器兼容旧 v1。主要字段包括：

- `target_px: [width, height]`：按实测槽位生成的目标宽高。
- `requirements: [{page, width, height, fit}]`：同一素材在所有页面上的需求，复用素材按全部槽位验收。
- `aspect`：覆盖需求的目标比例；实际服务可取支持的相近比例。
- 文件名、槽位、提示词、负面约束、透明通道与生成参数。

具体机读字段以 `build_brief()` 的产物为准。提示词建议按主体、场景、构图、镜头、光线、
色彩、风格、细节、文字与限制组织。像素、比例、数量、seed 放独立参数，不与提示词重复冲突。
真实截图不应为了适配色板被重绘；生成图片的颜色与构图可以协调整套风格，但要保持主体与证据真实。

## 资产清单

没有清单时，`image` 写相对 spec 的路径。使用 `assets/manifest.json` 时，`image` 写 assetId：

```json
{"schemaVersion":1,"assets":{"overview":{"file":"overview.png","source":"provided","note":"真实产品界面"}}}
```

manifest 的 `file` 相对 `assets/`。此处清单仍为 schemaVersion 1，与请求合同 v2 是两个不同 schema。
assetId 只在编译期解析，渲染器使用最终路径。缺文件不能通过自动生成占位物掩盖。

## 图位与裁切

`visual.ratio` 定义槽位形状；图片的 fit 与焦点在项目皮肤声明：

```css
/* 信息图、截图保全；照片按需 cover 并设置焦点。 */
.imgwrap img { object-fit: contain; object-position: 50% 50%; }
```

默认渲染路径仍为 cover。应根据具体图位选择 contain 或 cover，必要时用元素选择器区分，
不能假设主体总在中央。检查人脸、标注、界面边缘与节点是否被裁掉。原生 PPTX 会读取实测
object-fit/object-position 计算图片框与裁切；复杂 CSS 效果仍需回读验证。

## 清晰度与内容验收

`--check` 先检查真实文件存在，再用临时渲染测量实际图位；不会创建交付图片。
按每个槽位的宽高与 fit 计算有效采样需求，不再用固定 1280px 宽度判断所有图片。
cover 要同时满足裁切后的宽高需求，contain 按实际显示图像尺寸检查；比例相近不等于清晰度足够。

机械检查之后还要目检主体、文字、结构关系、品牌、生成瑕疵与裁切。相同比例但文字看不清，
或高分辨率但关系错误，仍不能交付。比例不一致可以通过合理裁切或留边解决，关键内容不能牺牲。
