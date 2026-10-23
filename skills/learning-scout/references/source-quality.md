# 来源质量与搜索

学习路线的可信度，主要不是由“链接数量”决定，而是由**来源层级、时效、可实践性和是否被核验**决定。
先把来源分层，再决定谁进入主路线，谁只进“备选”。

## 来源层级

| 层级 | 适合放在哪里 | 典型来源 | 判断标准 |
| --- | --- | --- | --- |
| 一手 | 概念、接口、规范 | 官方文档、原始论文、维护者博客、官方工程博客 | 能追溯到作者/团队；有版本或日期；不是二手转述 |
| 实践 | 工程细节、踩坑、生产经验 | 一线公司工程博客、维护者/资深工程师博客、会议演讲 | 有生产案例、代码、数据或失败复盘 |
| 社区 | 课程、路线、术语表、补充练习 | Datawhale、BAAI、InfoQ、优质 awesome list、课程仓库 | 结构完整、能运行、注明来源；不把社区结论当规范 |
| 营销 | 产品能力、行业概览 | 厂商博客、产品文档、白皮书 | 只取事实与架构；把营销话术和独立证据分开 |

一条主路线里，优先让**一手 + 实践**占多数。社区课程可以负责“顺序”和“练习”，
但关键结论要回到官方文档或原始来源核对。

## 博客平台候选池

不是白名单，只是优先搜索的起点。进入路线前仍然要核验具体文章。

### 官方 / 一线工程博客

Anthropic、OpenAI、Google DeepMind、Google Cloud、AWS、Microsoft、Meta、Netflix、
Uber、Airbnb、Stripe、Shopify、GitHub、Cloudflare、Databricks、Spotify、Slack、
Figma、Discord、Pinterest、LinkedIn、Dropbox、Elastic、Grafana、Honeycomb。

### 个人 / 实践者博客

Martin Fowler、Julia Evans、Dan Luu、Simon Willison、Arpit Bhayani、Brendan Gregg、
Charity Majors、Gergely Orosz、Kelsey Hightower、Liz Rice、Bryan Cantrill。

### 中文来源

美团技术团队、字节跳动技术团队、阿里云开发者社区、腾讯技术工程、AWS 中国官方博客、
InfoQ 中文、Datawhale、BAAI、机器之心。

中文技术社区（CSDN、知乎、掘金、公众号）不是不能用，但默认按“社区”处理：
必须核对代码、版本、日期和原始出处，不能作为唯一依据。翻译农场、无作者聚合页、
“10 个必看”式 SEO 文章直接排除。

## 视频

视频的核验字段、可信频道与内嵌平台见 [视频](video-sources.md)；本节只讲它在来源分层中的位置。


优先：

- 官方会议频道：CNCF、Google I/O、AWS re:Invent、QCon、Strange Loop、PyCon、NeurIPS。
- 作者/团队自己的频道：LangChain、Anthropic、OpenAI、freeCodeCamp、IBM Technology。
- 课程页能对应到公开大纲、代码仓库或练习。

至少核验：标题、频道、发布日期、时长、语言、是否免费/需登录。
没有看完整内容时，只能写“元数据核验”，不能评价讲得好不好，也不能声称看过了。

## 搜索顺序

```text
1. 主题 + official docs / specification / maintainer
2. 主题 + engineering blog / production / postmortem / lessons
3. 主题 + conference talk / tutorial / hands-on lab
4. 主题 + 中文 教程 / 实践 / 工程
5. 主题 + GitHub / awesome / course（只用来找线索）
```

对每个候选资源问五个问题：

1. 它是一手、实践、社区还是营销？
2. 作者/团队是谁？发布日期是什么？
3. 它解决的是“理解”还是“动手”？适合哪一站？
4. 有没有代码、数据、生产案例或可运行实验？
5. 链接现在能打开吗？免费、付费还是需登录？

## 记录与核验

资源至少记录：

```text
title / url / format / source / tier
why / language / time / cost / verified_at
```

规则：

- 每个主资源写一句“为什么是它”；写不出来就不进主路线。
- 链接必须实际打开过；不能凭搜索结果编 URL。
- 同一资源不要重复放进多个阶段。
- 快速变化的主题优先近 12–18 个月的材料；基础概念可以接受更老的经典。
- 视频只核验元数据就标明；实验没跑就标明“未执行”。
- 付费、登录、云账号、地区限制要写出来，不能让用户点进去才发现。

## 常见坏信号

- 标题很大，正文没有作者、日期和来源。
- 代码不能运行，或依赖早已废弃的 API。
- 大量截图代替解释，关键结论没有出处。
- 只讲“是什么”，没有边界、失败模式或练习。
- 用“2025 最新”包装 2022 的内容。
- 把厂商 benchmark 当成独立评测。
- 让你收藏 40 个链接，却不告诉你先做哪一步。

---

来源质量的目标不是“看起来权威”，而是让学习者能判断：**我为什么现在读这个，读完能做什么。**
