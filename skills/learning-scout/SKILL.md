---
name: learning-scout
description: >-
  Use when 想学一个主题，需要学习路线、资料/博客/视频筛选、实践项目建议，或要制定
  30 分钟、1 周、1 个月的个性化学习计划。中文触发：学习路线、找学习资料、找教程、
  找技术博客、推荐视频、怎么入门、进阶路线、面试准备、学习计划。产出可离线打开的
  HTML 学习笔记，带测验、间隔复习和本机进度，不是 Markdown 链接清单。
  Do NOT use for: 维护已有笔记或知识库、
  没有学习目标的纯搜索、课程制作、学术论文写作。
---

# learning-scout

把一个模糊的“我想学 X”变成一份**有判断、有节奏、能跟着学**的 HTML 学习笔记。
研究做真，路线做窄，内容讲透；不要用 30 个链接冒充学习计划，也不要把“去看这个”
当成教学。

## 先定四件事

尽量从上下文推断；缺少时只问这四个，不要审问：

1. 想达到什么结果？（能做什么，而不是“学会”）
2. 现在什么水平？（完全新手 / 会一点 / 想进阶）
3. 有多少时间？（30 分钟 / 一周 / 一个月）
4. 偏好什么形式？（中文/英文、文档/视频/动手）

用户没回答就写明假设。先给一个可调整的版本，再根据反馈收窄。

## 研究和筛选

用可用的搜索、抓取和官方文档工具并行找：

- 官方文档、规范、原始论文、维护者文章
- 一线工程博客、生产复盘、会议演讲
- 可运行 repo、lab、课程练习
- 中文资料，单独标注来源层级
- 视频：只从官方频道、会议频道、作者本人或可信课程找

选来源的优先级和平台池见
[来源质量](references/source-quality.md)。核心规则：

- 主路线优先一手 + 实践来源；社区课程负责顺序和练习。
- 每个主资源写一句“为什么是它”；写不出来就不要放。
- 至少核验标题、URL、作者/频道、日期、语言、时长、收费方式。
- 视频没看完整就只写“元数据核验”，不要评价讲得好不好。
- 付费、登录、云账号、地区限制必须写出来。
- 不用内容农场、翻译农场、无作者 SEO 聚合页作为主来源。

不要把搜索结果原样倾倒。先判断它适合哪一站，再决定是否进入路线。

## 设计路线

不要固定成“每站五个栏目”。阶段是叙事节拍，不是表单：

- 一站可以只有一组资源和一次练习；
- 一站可以只有一次实验和一个过关问题；
- 时间、类比、绕路、能力清单都是可选的；
- 但每个阶段至少要有资源、练习或检查点之一；
- 整条路线至少要有一个真正的动手任务。

好的节奏通常是：

```text
建立判断 → 跑通最小闭环 → 补关键盲区 → 做一次真实迭代
```

不是每个主题都需要四段。短计划可以只有 2–3 站；系统学习可以 5–6 站。
主资源每站 1–3 个，超过 4 个通常应该拆站。详细设计手法见
[学习路线设计](references/learning-design.md)；每一步的讲解标准见
[内容质量](references/content-quality.md)。

如果要交付“能跟着学”的 `paged` 笔记，每章默认 2–3 篇解释 + 一次动手 +
一次测验；一章一个核心问题，不要把所有概念塞进一页。每个阶段配 2–5 道回忆题，
整条路线配 5–10 张复习卡；复习间隔先用 1 / 3 / 7 天，不假装是完整 FSRS。

每站尽量有一个具体类比或反差，但不要堆梗。有趣来自：

- 一个准确的日常类比
- 一个反直觉的问题
- 一个带约束的小任务
- 一个能拿走的产物
- 一个“学完再跳”的可选深坑

不要把“有趣”做成积分、徽章和感叹号。

## 写计划 JSON

按 [计划合同](references/plan-schema.md) 写 JSON。最小结构：

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
      "resources": [
        {
          "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
          "url": "https://arxiv.org/abs/2005.11401",
          "format": "paper",
          "source": "arXiv",
          "tier": "primary",
          "why": "原始论文，先看摘要和架构图。",
          "time": "15 分钟"
        }
      ],
      "practice": {
        "title": "画一张自己的 RAG 流水线",
        "brief": "用 7 个框画出从文档到答案的路径。",
        "deliverable": "一张手绘图 + 3 个失败点"
      }
    }
  ],
  "sources": {
    "verified_at": "2026-10-22",
    "note": "链接核验于 2026-10-22；视频只核验元数据。"
  }
}
```

可用字段：

- `title_lines`：标题分行，避免中文被随机拆词。
- `layout`：`journey` / `atlas` / `studio` / `paged`；决定结构，不只是颜色。
- `paged` 特有：`learner`（起点/目标/时间/偏好）、`sections`（每篇 `body`、
  `points`、`code`、`aside`、`sources`）、`quiz`（问题/选项/答案/解释）、
  `review`（front/back/来源）、`practice.steps`（do/expect/check）。
- `theme`：`deep-field` / `paper-trail` / `citrus` / `blueprint`，可换
  `accent` 与 `motif`；不填时按主题自动选择。
- `interludes`：阶段之间的过场，`after` 指向阶段 id。
- `not_now`：现在不学的分支，防止路线膨胀。
- `rabbit_holes`：学完再跳的深坑，可带 URL。
- `start`：`today` 和 `week_one`，给学习者一个立刻可做的动作。

## 选择版式

至少提供四种结构不同的版式，不要只换颜色：

- `journey`：星图 + 纵向阶段。适合从概念走到项目的主线。
- `atlas`：目录式双栏，标题在左、内容在右。适合资料多、需要反复查阅的路线。
- `studio`：海报式开场 + 卡片墙。适合源码、工程项目、多天集训。
- `paged`：一屏一页、滚动吸附、视差背景；每页讲一个概念，附依据链接。
  适合“读一篇长笔记”而不是“扫一遍目录”。

版式按内容和阅读场景选：

- 学习故事、概念递进：`journey`
- 资料库、手册、需要快速定位：`atlas`
- 工作坊、源码深潜、项目冲刺：`studio`
- 系统学习、教程、需要从第一页读到最后一页：`paged`

同一份内容可以用不同版式重新渲染：

```sh
python3 scripts/learning_scout.py render --input plan.json --layout atlas
python3 scripts/learning_scout.py render --input plan.json --layout studio
python3 scripts/learning_scout.py render --input examples/langchain-notes.plan.json --open
```

不要把“换主题”当成“换风格”。结构不同，才算真正不同的页面。

## 渲染

```sh
python3 scripts/learning_scout.py validate --input plan.json
python3 scripts/learning_scout.py render --input plan.json --open
python3 scripts/learning_scout.py render --input plan.json --layout studio
python3 scripts/learning_scout.py render --input examples/langchain-notes.plan.json --open
```

默认写到：

- macOS/Linux：`~/Downloads/learning-scout/<topic>-<date>/index.html`
- Windows：`%USERPROFILE%\Downloads\learning-scout\<topic>-<date>\index.html`

可用 `--out` 指定完整路径，`--output-dir` 或 `LEARNING_SCOUT_OUTPUT_DIR` 换目录。
`--stdout` 只打印 HTML，不落盘。`--layout` 覆盖版式，`--theme`、`--accent`、
`--motif` 覆盖视觉；`--theme` 默认使用该主题自己的 accent/motif。

HTML 是自包含的：CSS、JS 和内容都在一个文件里，不依赖远程字体或图片。
默认不产出 Markdown；JSON 只是可复现的源文件，不是交付物。

## 视觉验收

渲染后至少检查：

1. 桌面 1440px：标题不拆词、首屏不过度下沉、阶段导航清楚、侧栏不遮挡。
2. 至少试两种 `--layout`；确认它们不是只换了颜色。
3. 手机 390px：没有横向溢出；资源卡、按钮、勾选框都能用。
4. 资源筛选、进度勾选、外链、回到顶部都实际点一次。
5. `paged` 还要点一次测验、完成按钮、翻面评分、导出 Markdown、刷新后的续读。
6. 页面在断网时仍能打开；不加载远程依赖。
7. 资源列表没有重复 URL；视频和付费内容标注正确。

视觉上优先“像一本有性格的路线志”，而不是后台仪表盘。版式决定结构，主题决定
颜色/材质：研究型可用 journey + deep-field，资料型用 atlas + paper-trail，
工程型用 studio + blueprint，创意型用 atlas/citrus。不要让所有页面都长得一样；
也不要为了炫技牺牲可读性。

## 常见失败

- 把搜索结果的标题和摘要当正文，编出不存在的链接。
- 给每站硬凑五个栏目，读起来像表格。
- 主路线塞 20 个链接，没有“先做哪一步”。
- 把长课程写成“看完”，没有分段建议。
- 视频只核验了标题，就写“讲得很好”。
- 只给“去看这篇文档”，没有解释、例子和检查点；新手看不出来。
- 用 Markdown 交付；用户没有阅读欲望。
- 页面很漂亮，但手机上横向溢出，或链接点不开。
- 忘记写核验日期和“哪些没有验证”。

## 边界

- 不自动把计划写进任何知识库；先交付 HTML，是否沉淀由用户决定。
- 不下载、转录或重新分发付费课程和视频。
- 不声称看过没有看过的内容。
- 不把学习路线包装成“保证学会”或“7 天精通”。
- 不把 localStorage 说成云同步；换设备/清缓存就丢失。
- 不把 1 / 3 / 7 天说成完整 FSRS；它只是轻量间隔复习。
- 资源应该服务于路线；路线不应该服务于资源数量。
