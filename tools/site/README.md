# 站点生成器

`tools/build_site.py` 从仓库里的 Markdown 生成项目子站：

- `/agent-skills/`：项目首页（skill 卡片、安装方式、工作方式）
- `/agent-skills/docs/`：开始使用、Skill 目录、每个 skill 的 README、编写指南、维护与路线图

内容只维护 Markdown 源文件；改完 README / GUIDE / ROADMAP 后重新生成，不手改输出 HTML。

## 依赖

```sh
python3 -m pip install -r tools/site/requirements.txt
```

## 构建与检查

```sh
# 输出到临时目录并检查内部链接、必备文件、模板残留
python3 tools/build_site.py --out /tmp/agent-skills-site --check

# 生成器回归
python3 -m unittest discover -s tools/site/tests -v
```

`--check` 会检查：

- 18 个页面、样式、脚本、图标与 `.nojekyll` 是否齐全；
- HTML 内链目标是否存在（跳过外链与站点根目录之外的链接）；
- 是否有 `@@TOKEN@@` 残留；
- 每个页面是否有 `<title>`。

它不检查视觉呈现；发布前用浏览器看关键页面。

## 输出结构

```text
<out>/
├── index.html                 # 项目首页
├── 404.html
├── docs/
│   ├── index.html
│   ├── getting-started.html
│   ├── guide.html
│   ├── maintenance.html
│   ├── roadmap.html
│   └── skills/
│       ├── index.html
│       └── <skill>.html
└── assets/
```

页面使用相对链接，可从任意目录前缀提供服务；本地预览：

```sh
python3 -m http.server 8000 --directory <out>
```

## 部署

项目子站由本仓库的 `docs/` 发布到 GitHub Pages：
https://huangrx6.github.io/agent-skills/

生成到仓库并检查：

```sh
python3 tools/build_site.py --out docs --check
```

提交 `docs/` 后，`.github/workflows/pages.yml` 用 GitHub Actions 发布。
仓库的 Pages Source 需要设为 **GitHub Actions**（不是分支部署）。
`gate.yml` 的站点 job 会重新生成到临时目录并与 `docs/` 对比，
防止提交的页面和 Markdown 源不一致。

根域名站点 `https://huangrx6.github.io/` 不属于本仓库，保持不变。

## 设计约束

- 内容单源：根 README 的 Skill 表决定分类与顺序；skill README 决定详情页正文。
- 链接改写：skill 内的相对链接指向 GitHub 的 blob / raw；根 README 的安装与维护章节
  映射到站点页面。
- GitHub alert（`> [!NOTE]`）转成中文引用块，避免原样输出标记。
- 页面模板在 `tools/site/templates/`，样式与脚本在 `tools/site/assets/`；
  不要在其他地方复制一份。
- 生成器是仓库工具，不进入 `skills/`，不会被安装到 agent。
