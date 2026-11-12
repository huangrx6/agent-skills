# 样式预设与确认

四套预设解决「同一封邮件对内正式、对外简洁、故障醒目」的差异。样式只改令牌，不改内容。

## 四套预设

| 预设 | 适用 | 视觉特征 |
| --- | --- | --- |
| `business`（默认） | 申请、确认、邀请、通知 | 白底，深蓝 `#1F4E79` 强调色，标题左侧色条，宽 640px |
| `report` | 汇报、交付、周报 | 顶部摘要卡，表格浅灰斑马纹，宽 640px |
| `plain` | 日常、对外、短通知 | 无色块，靠留白与标题层级，宽 600px |
| `alert` | 故障、协调、紧急 | 顶部警示色带，红色强调，宽 640px |

## 自动选择顺序

1. `style` 明确指定。
2. `urgent: true` 或 `type: coordination` → alert。
3. `type: daily`，或 `audience` 含「外部 / 客户 / 甲方 / 供应商」→ plain。
4. `type` 为 report / handover → report。
5. `type` 为 approval / confirm / invitation / notice / business / followup → business。
6. 表格 3 行以上或图片 2 张以上 → report；否则 business。

`style` 的优先级高于自动选择。命令行 `--preset` 又高于 Spec（用于临时预览）。
预设优先级：命令行 `--preset` > 模板 `style.json` > Spec > 自动选择。
覆盖值按 Spec、样式文件顺序合并，不因切换预设丢失。

## 令牌结构

样式在 `assets/styles/*.json`：

```json
{
  "name": "business",
  "width": 640,
  "font": {"family": "'Microsoft YaHei', '微软雅黑', 'PingFang SC', Arial, sans-serif",
           "size": 14, "line_height": 1.7},
  "color": {"accent": "#1F4E79", "text": "#1F2328", "muted": "#5B6770",
            "background": "#FFFFFF", "page": "#F3F5F7",
            "surface": "#F1F6FA", "border": "#D9E2EA"},
  "spacing": {"page": 24, "content": 28, "block": 12},
  "frame": {"border": true},
  "heading": {"bar": true, "size": 20, "section_size": 16},
  "summary": {"card": true},
  "callout": {"card": true},
  "table": {"zebra": false, "header_background": "#EAF1F8"},
  "band": {"enabled": false, "color": "#B42318", "text": "#FFFFFF"}
}
```

- `width` 必须 ≤ 640；超过会被校验阻断。
- 颜色都写十六进制；正文与背景的对比度要足够。
- `heading.bar` 控制标题左侧色条；`summary.card` 控制摘要卡；`table.zebra` 控制斑马纹；
  `band.enabled` 控制顶部色带。
- 字体回退链按 `Microsoft YaHei` → `微软雅黑` → `PingFang SC` → `Arial` 顺序。
- `spacing.content` 是内边距，图片版心 = `width - 2 × content`。

## 覆盖方式

Spec 内：

```yaml
style:
  preset: business
  overrides:
    color:
      accent: "#0F5C4E"
    width: 600
```

命令行 / 模板：

```sh
python3 <skill路径>/scripts/render.py spec.yaml --preset report
python3 <skill路径>/scripts/render.py spec.yaml --style-file style.json
```

`style.json` 可以是：

```json
{"preset": "report", "overrides": {"table": {"zebra": false}}}
```

也可以直接是一份不完整的令牌表，脚本会深合并到当前预设上。覆盖只改令牌，
不重写正文、不改变模块顺序。

## C2 按需确认

普通邮件直接采用预设。仅用户要求预览或复杂版式需要选择时，合并说明：

> 结构：主题 + 摘要 + 发布范围（3 条）+ 3 张图 + 工时表（3 行）+ 待办（2 项）+ 签名。
> 样式：business 预设，强调色 #1F4E79，宽 640px，标题左侧色条。
> 结构和样式是否接受？接受 / 调整颜色 / 更简洁 / 更正式 / 换预设。

- 接受：进入渲染与校验。
- 调整颜色：只改 `color.accent` 等令牌，给出新色值。
- 更简洁：换 plain，去掉色块与斑马纹。
- 更正式：换 business 或 report，保留色条/摘要卡。
- 换预设：四套之一，说明理由。

按用户反馈调整，不因固定轮数限制而擅自退回默认预设。
用户指定品牌色时，用 `style.overrides.color.accent` 或 `--style-file`，不要改预设文件。

## 原始 HTML 模板

原始 HTML 模板自带版式，不使用这四套预设，也不读样式令牌。它的兼容规则、
变量与校验见 [templates.md](templates.md)；若用户要求预览，展示「模板版式 + 变量清单」；已选定的模板无需重复确认。
