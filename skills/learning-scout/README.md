# learning-scout

> 把一个学习需求变成一组能读进去的独立笔记，以及一个可离线打开的入口页。

| 适合 | 产物 | 依赖 |
| --- | --- | --- |
| 主题学习 · 系列笔记 · 可复习的离线课程 | 笔记 `.md` · HTML 入口 · 打印版 / PDF | Python 3.11+；渲染增强可选 |

## 快速开始

```sh
sh scripts/setup.sh                                 # 可选：装 Markdown 渲染与代码高亮
python3 scripts/check_notes.py --plan plan.json     # 质量闸门
python3 scripts/build_series.py build --input plan.json
python3 scripts/build_series.py build --input plan.json --out ./dist --force --open
```

默认输出到 `~/Downloads/learning-scout/<topic>-<date>/`。`--no-check` 跳过质量检查，
仅用于临时草稿。

## 输出结构

```text
<workspace>/
├── index.html      # 篇目、进度、视频墙、动手任务、复习卡、术语表
├── print.html      # 全部篇目合并，可直接打印或导出 PDF
├── plan.json       # 计划源文件
├── README.md       # 篇目与路径清单
└── notes/
    ├── 01-xxx.md   # 独立成篇的深度笔记，可导入知识库或直接发布到博客/公众号
    └── 01-xxx.html # 渲染页：目录、视频、自测、上一篇/下一篇
```

## 依赖

- Python 3.11+。
- **可选**：`markdown-it-py`、`mdit-py-plugins`、`pygments`，提供嵌套列表、表格对齐与代码高亮。
  它们装在项目家目录，不放进 skill：

  ```sh
  sh scripts/setup.sh
  # → ${AGENT_SKILLS_HOME:-~/.agent-skills}/data/learning-scout/venv
  ```

  可用 `LEARNING_SCOUT_VENV` 指定别处。未安装时自动回退到内置渲染器：
  基本 Markdown 可用，嵌套列表会被拍平、代码不高亮。

## 页面能力

- 亮 / 暗自动切换，无远程字体与脚本。
- 篇目搜索、已读勾选、继续上次、复习卡 1/3/7 天调度、测验答案持久化。
- 视频点击后才加载播放器；断网时正文、目录、测验、复习卡仍可读。
- 打印时隐藏导航、视频与测验；`print.html` 合并全部篇目。

## 目录与参考

<details>
<summary><strong>展开文件说明</strong></summary>

| 文件 | 作用 |
| --- | --- |
| `SKILL.md` | 工作流程、来源规则、验收标准 |
| `scripts/build_series.py` | 构建入口：校验、质检、渲染、复制原文与图片、生成 index 与 print |
| `scripts/render_md.py` | Markdown 引擎（markdown-it + Pygments；无依赖时回退） |
| `scripts/series_theme.py` | 简洁样式（亮/暗）与前端脚本（进度、测验、复习、搜索） |
| `scripts/check_notes.py` | 结构与独立性检查（默认节、代码量、跨篇引用、个人路径；长度仅提示） |
| `scripts/setup.sh` | 可选的 venv 安装 |
| `tests/learning-scout/`（仓库根目录） | 渲染、视频地址、校验、构建、图片复制、检查器 |
| `references/depth-standard.md` | 每篇写多深、多少行、默认有哪些节 |
| `references/note-templates.md` | 四类笔记的起步骨架 |
| `references/learning-design.md` | 承诺、篇目节奏、独立性与练习 |
| `references/plan-schema.md` | v2 系列合同；v1 单页字段在文末 |
| `references/video-sources.md` | 视频来源、核验字段、内嵌平台 |
| `references/content-quality.md` | 内容合同与清晰度检查 |
| `references/source-quality.md` | 博客 / 视频 / 社区来源的分层与核验 |
| `examples/series.plan.json` | v2 系列示例（配 `examples/series-notes/`） |
| `examples/rag.plan.json` | v1 单页路线示例（legacy） |
| `examples/langchain-notes.plan.json` | v1 paged 示例（legacy） |
| `scripts/learning_scout.py` | v1 单页渲染器（legacy，保留兼容） |
| `assets/`、`templates/` | v1 版式的样式与模板（legacy） |

</details>

## 验证

```sh
python3 -m unittest discover -s tests/learning-scout -v   # 55 条：全绿（未装可选依赖时跳过渲染用例）
```

## 限制

- 未装可选依赖时，嵌套列表会拍平、代码无高亮；`check_notes.py` 仍可用。
- 视频内嵌需要联网；离线只保留标题与链接。
- 进度、答题与复习记录保存在浏览器 `localStorage`，换设备或清缓存会丢失。
- 1 / 3 / 7 天是轻量间隔复习，不是完整 FSRS。
