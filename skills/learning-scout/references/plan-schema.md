# 计划合同

当前默认是 v2：多篇笔记系列。v1 的单页路线字段保留在文末，仅供旧的 `render` 命令使用。

## v2：多篇笔记系列合同（默认）

v2 把交付物从“一个 HTML 页面”改成“**一组可独立阅读的 Markdown 笔记 + 一个 HTML 入口**”。
`version: 2` 时用 `python3 scripts/build_series.py` 构建；v1 的 `render` 继续可用，用于快速路线页，
但主题学习默认走 v2。

## 目录形状

```text
<workspace>/
  index.html            # 入口：篇目、进度、视频、动手任务、复习卡、来源
  plan.json             # 唯一的计划源文件
  README.md             # 篇目与路径清单
  notes/
    01-<slug>.md        # 原文（可直接导入 Markdown 知识库）
    01-<slug>.html      # 渲染页
    02-<slug>.md
    02-<slug>.html
```

默认输出目录：`~/Downloads/learning-scout/<topic>-<date>/`。
`--out` 可指定任意目录。

## 最小形状

```json
{
  "version": 2,
  "topic": "可靠队列入门",
  "promise": "从一次丢消息的故障出发，做出一个重启不丢的最小队列。",
  "learner": {
    "level": "会一点 Python",
    "goal": "能独立实现并入队与原子落盘",
    "time_per_day": "40 分钟"
  },
  "notes": [
    {
      "id": "01",
      "title": "先看一次真实失败",
      "goal": "能指出消息在哪一段丢的",
      "depth": "L2",
      "kind": "concept",
      "minutes": 25,
      "file": "notes/01-what.md",
      "videos": [],
      "quiz": [
        {
          "q": "入队成功代表消息安全了吗？",
          "options": ["是", "还要看是否落盘"],
          "answer": 1,
          "why": ["入队只在内存里，进程重启就没了", ""],
          "explain": "入队只是进了内存队列。"
        }
      ]
    }
  ],
  "practice": {
    "title": "做一个不丢消息的队列",
    "brief": "50 行代码，入队 + 原子落盘。",
    "steps": [{"do": "写内存队列", "expect": "重启丢失", "check": "能复现"}]
  },
  "review": [{"front": "为什么先写临时文件？", "back": "保证替换原子。", "source": "POSIX rename"}],
  "sources": {"verified_at": "2026-10-23", "note": "视频只核验元数据。"}
}
```

## 顶层字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `version` | 是 | 固定 `2`。 |
| `topic` | 是 | 学习主题，页面主标题。 |
| `promise` | 是 | 学完能做什么；一句话。 |
| `learner` | 否 | `{level, goal, time_per_day, preferences, constraints}`。 |
| `audience` | 否 | 适合谁、需要什么前置。 |
| `notes` | 是 | 至少 2 篇；见下。 |
| `practice` | 建议 | 整条系列的一次动手任务，`steps` 用 `do/expect/check`。 |
| `review` | 否 | 复习卡：`{front, back, source}`；入口页按 1/3/7 天调度。 |
| `start` | 否 | `{today: [...], week_one: [...]}`；入口页的“从这里开始”。 |
| `prerequisites` | 否 | `[{skill, why}]`；开始前最好具备的能力。 |
| `outcomes` | 否 | `[{title, detail}]`；学完能做什么。 |
| `glossary` | 否 | `[{term, definition}]`；入口页术语表。 |
| `sources` | 是 | `{verified_at, note}`。 |

## 每篇笔记

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 两位数，决定顺序，如 `"01"`。 |
| `title` | 是 | 与 Markdown 标题一致；只回答一个问题。 |
| `goal` | 是 | 读完能做到什么，一句话。 |
| `file` | 是 | 指向 `notes/*.md`，相对 plan.json。 |
| `depth` | 否 | `L1`–`L4`，与深度规范一致。 |
| `kind` | 否 | `concept` / `mechanism` / `practice` / `source-review`。 |
| `minutes` | 否 | 预计阅读分钟数。 |
| `videos` | 否 | 0–2 个，字段见 [视频](video-sources.md)。 |
| `quiz` | 否 | 两种题型：选择题 `{type?: "choice", q, options, answer, explain, why?}`，
  `answer` 是下标、`why` 与 `options` 一一对应；短答题 `{type: "short", q, model_answer, explain?}`，
  不给选项，先自己写再对照参考答案。出题规则见 [自测设计](quiz-design.md)。 |

笔记正文的深度、长度参考、默认结构见 [笔记深度规范](depth-standard.md)；每篇必须独立成篇，
不引用同系列其他篇；不需要为独立性补齐所有前置知识。

## Markdown 支持范围

渲染器实现的是一个受控子集：标题、段落、有序/无序列表、任务列表、表格、围栏代码、
引用、`> [!note]` / `> [!warning]` 提示块、行内代码/粗体/斜体/链接/图片、分隔线。

不支持：嵌套列表（按平铺处理）、脚注、数学公式、HTML 原片。需要这些时改用 v1 的
`paged` 页面，或把内容写成文字。

## 校验原则

- `version` 必须是 `2`；`notes` 少于 2 篇直接报错（单篇内容不属于系列）。
- `file` 必须存在、必须是 `.md`、不能越出 plan 目录。
- `id` 重复、`quiz.answer` 越界、`sources.verified_at` 缺失：错误。
- 视频缺 `verified_at`、笔记缺 `goal`、整条系列没有 `practice`：警告。
- 构建会复制 Markdown 原文到输出目录，导入任何 Markdown 知识库都不需要再转换。

## 构建

```sh
python3 scripts/check_notes.py --plan plan.json        # 深度与独立性检查
python3 scripts/build_series.py build --input plan.json
python3 scripts/build_series.py build --input plan.json --out ./dist --force --open
```

构建会先跑 `check_notes.py` 的同款检查，失败则中止；`--no-check` 可跳过。
`--force` 覆盖已存在的输出目录，`--open` 构建后打开入口页。成功后打印输出目录与
`index.html` 路径，并生成合并全部篇目的 `print.html`。

---

# v1（legacy）：单页路线

> 以下字段只被 `scripts/learning_scout.py` 使用；新内容请按上面的 v2 写。


渲染器只读一个 JSON 文件。它负责把“研究结果”变成可发布的 HTML；agent 负责把研究做真。
字段按“有就写，没有就省略”设计，不要求每个阶段凑齐同一组栏目。

## 最小形状

```json
{
  "version": 1,
  "topic": "RAG 实战",
  "title": "从开卷考试到可评估系统",
  "promise": "不是把文档塞进 prompt，而是造一台会找、会答、会认错的机器。",
  "stages": [
    {
      "id": "s1",
      "title": "先把 RAG 看成一场开卷考试",
      "hook": "先别碰向量数据库。先搞清楚什么问题值得用 RAG。",
      "resources": [
        {
          "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
          "url": "https://arxiv.org/abs/2005.11401",
          "format": "paper",
          "source": "arXiv",
          "tier": "primary",
          "why": "原始论文，帮你判断一个系统到底在解决哪一类问题。",
          "time": "15 分钟略读"
        }
      ],
      "practice": {
        "title": "画一张自己的 RAG 流水线",
        "brief": "只画你理解的链路，不抄框架图。",
        "deliverable": "一张 7 个框的图和 3 个可能的失败点"
      },
      "checkpoint": {
        "question": "检索很差时，应该先怪模型吗？",
        "pass": "能指出问题在 query、召回、切块、排序还是生成。"
      },
      "time": "60–90 分钟"
    }
  ],
  "sources": {
    "verified_at": "2026-10-22",
    "note": "链接核验于 2026-10-22；视频只核验标题、频道和时长，未逐分钟观看。"
  }
}
```

## 顶层字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `version` | 是 | 固定为 `1`。 |
| `topic` | 是 | 学习主题，也是页面主标题。 |
| `title` | 否 | 主题下的一句路线标题，建议有画面感。 |
| `title_lines` | 否 | 可选的标题分行数组；用来避免中文标题在页面里被随机拆词。 |
| `promise` | 是 | 学完能得到什么；一句话，不写课程大纲。 |
| `subtitle` | 否 | 补充说明，适合放在 hero 的 meta 区域。 |
| `audience` | 否 | 适合谁、需要什么前置。 |
| `language` | 否 | 资料语言偏好或实际构成。 |
| `duration` | 否 | 总时长；没有承诺就不要编。 |
| `effort` | 否 | 每天/每周投入。 |
| `why_now` | 否 | 为什么现在值得学；给动机，不给焦虑。 |
| `thesis` | 否 | 整条路线的一句话主张，页面会用大字号呈现。 |
| `layout` | 否 | `journey`、`atlas`、`studio` 或 `paged`；默认 `journey`。 |
| `theme` | 否 | `{name, accent, motif, reason}`；不填时按主题自动选。 |
| `stats` | 否 | `[{value, label}]`；不填时按阶段、资源、任务自动算。 |
| `outcomes` | 否 | `[{title, detail}]`；学完后的可验证能力。 |
| `learner` | 否 | `{level, background, goal, time_per_day, preferences, constraints}`；`paged` 的起点。 |
| `prerequisites` | 否 | `[{skill, why}]`；开始前最好具备的能力。 |
| `glossary` | 否 | `[{term, definition, source, url}]`；术语表，重复 term 会报错。 |
| `capstone` | 否 | `{title, brief, acceptance}`；最终项目说明。 |
| `review` | 否 | `[{id, stage, front, back, source, url}]`；`paged` 的复习卡。 |
| `stages` | 是 | 至少一站；见下。 |
| `interludes` | 否 | 阶段之间的过场：`{after, quote, note, source}`。 |
| `not_now` | 否 | `[{title, why}]`；明确暂时不学的分支。 |
| `rabbit_holes` | 否 | `[{title, why, url}]`；学完再跳的坑。 |
| `start` | 否 | `{today: [], week_one: []}`；第一动作。 |
| `sources` | 是 | `{verified_at, note}`；没有核验日期就不算完成。 |

## 阶段字段

`id` 和 `title` 必填。其余都按内容需要出现；渲染器不会为了“完整”造空栏目。

| 字段 | 说明 |
| --- | --- |
| `label` | 默认 `STAGE 01`；可改成 `第一站` 等。 |
| `title_lines` | 可选的分行数组；避免中文阶段标题被随机拆词。 |
| `kicker` | 阶段的一句话定位。 |
| `hook` | 先抓住注意力的反差、问题或场景。 |
| `time` | 这一站的预计时间。 |
| `goal` | 这一站要建立的理解或能力。 |
| `orbit` | 星图节点上的短标签，例如 `MAP`；不填用阶段序号。 |
| `orbit_note` | 星图节点的小字，例如 `FRAME`；不填用 `STAGE`。 |
| `metaphor` | 一个具体类比；不要堆砌。 |
| `resources` | 1–3 个主资源为宜；多于 4 个会提示。 |
| `practice` | `{title, brief, steps, deliverable, time}`；`steps` 是 `[{do, expect, check}]`。 |
| `checkpoint` | `{question, pass}`；自测问题与过关标准。 |
| `sections` | `paged` 的笔记页；见下。 |
| `quiz` | `[{question, options, answer, explain}]`；`answer` 是选项索引，最多 5 题。 |
| `misconceptions` | `[{wrong, right}]`；阶段页的“错误直觉 → 正确说法”。 |
| `teach_back` | 字符串；学完这一章后，让学习者不看笔记讲出来的问题。 |
| `detour` | `{title, brief, url}`；可选绕路。 |
| `skills` | 字符串列表；这站带走的能力。 |

至少要有 `resources`、`practice`、`checkpoint` 之一。不是每个阶段都必须三件套；
但如果一站什么也不做、什么也不读，它只是标题，不是路线。

## 资源字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 资源标题。 |
| `url` | 是 | 只接受 `http://` 或 `https://`。 |
| `format` | 是 | `docs/blog/video/course/paper/book/repo/lab/podcast/other`。 |
| `source` | 否 | 站点、频道或作者。 |
| `tier` | 否 | `primary/practitioner/community/video`。 |
| `why` | 否 | 为什么是它；没有理由的链接不进主路线。 |
| `time` | 否 | 预计阅读/观看时间。 |
| `language` | 否 | `中文`、`英文` 或 `中英`。 |
| `cost` | 否 | `免费`、`付费`、`需登录`。 |

同一 URL 在整份计划里只能出现一次。资源会同时出现在阶段里和页面底部的资源架中，
方便按格式筛选。

## 版式

`layout` 控制页面的结构，不只是颜色：

- `journey`：默认，星图 + 纵向阶段，适合从概念走到项目。
- `atlas`：目录式双栏，阶段标题在左、内容在右，适合资料多、需要快速查阅的路线。
- `studio`：海报式开场 + 卡片墙，阶段像工作台卡片，适合源码、工程项目和多天集训。
- `paged`：一屏一页、滚动吸附、视差背景；适合“从第一页读到最后一页”的系统笔记。

版式和主题可以组合。不要只换主题不换结构；内容密度高时优先 `atlas`，
想做沉浸式开营或工作坊时优先 `studio`。

## `paged` 笔记字段

`paged` 的每个阶段必须有 `sections`，每篇笔记至少要有 `body`、`points` 或 `code` 之一：

```json
{
  "sections": [
    {
      "id": "d1-map",
      "eyebrow": "DAY 01 / 01",
      "title": "先把 create_agent 当成一台编译器",
      "lede": "你给它的不是一次 prompt，而是一份装配说明。",
      "body": ["第一段解释。", "第二段把概念接到源码。"],
      "points": [{"title": "入口", "text": "看 `create_agent` 的返回类型。"}],
      "code": {"language": "python", "title": "最小 Agent", "content": "..."},
      "aside": {"label": "读源码时", "text": "不要从第一行开始背。"},
      "sources": [{"label": "Quickstart", "url": "https://..."}]
    }
  ]
}
```

- 正文优先解释“为什么/怎么工作”，再给源码和操作；不要只写“去看这篇”。
- `sources` 是这一页的依据，至少放一个可点的官方文档或源码链接；整篇的来源质量仍按
  [来源质量](source-quality.md) 判断。
- `code.status` 只能取 `tested`、`illustrative`、`pseudo`；没有实际运行就不要写 `tested`。
- 正文的全面性、清晰度和“不是链接清单”的检查见
  [内容质量](content-quality.md)。
- `quiz` 是阶段结束后的回忆题；不要考刚翻回去就能抄到的定义。
- `review` 是整条路线的复习卡，`stage` 必须引用存在的阶段 id；默认按 1 / 3 / 7 天
  做轻量间隔复习，不声称是完整 FSRS。
- `practice.steps` 用 `do / expect / check` 写“学习者要做什么、应看到什么、怎么算过”，
  而不是让 AI 替学习者做。

## 主题

`theme.name` 可取：

- `deep-field`：深色、荧光绿、适合 AI/研究/前沿技术。
- `paper-trail`：暖纸色、衬线、适合人文/写作/产品。
- `citrus`：明亮、橙色、适合设计/前端/创意。
- `blueprint`：深蓝、青色、适合系统/基础设施/工程。

`motif` 可取 `orbit`、`grid`、`waves`、`bloom`。`accent` 只接受 `#rrggbb`。
不指定主题时，渲染器根据主题词自动选择；这是起点，不是限制。

## 校验原则

- 缺主题、承诺、阶段或核验日期：错误。
- 非法 URL、重复 URL、未知格式/主题：错误。
- 阶段为空、interlude 指向不存在的阶段：错误。
- `paged` 阶段缺 `sections`、section 没有内容、quiz 答案越界、review 指错阶段：错误。
- `glossary` 缺 term/definition、term 重复、`misconceptions` 缺 wrong/right：错误。
- 阶段过多、单站资源过多、全篇没有动手任务：警告，不阻止渲染。
- 渲染器会转义文本，不把 JSON 当作 HTML。

