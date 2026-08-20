# ProcessOn 思维导图引擎

将此分支用于层次化知识结构。

## 支持的结构

- `mind_free` — 通用思维导图 / 中心辐射结构
- `mind_right` — 右向逻辑图
- `mind_org` — 组织层次结构
- `mind_ishikawa_left` — 鱼骨图/根因结构
- `mind_timeline_h` — 水平时间线
- `mind_tree_free` — 树状图
- `mind_treeTable_left_title` — 树状表格结构

如果用户未指定结构且意图没有强烈暗示，请使用 `mind_free`。

## 生成前转换内容

思维导图应是一个知识结构，而不是逐字文本转储。

- 确定一个根主题。
- 当重要源标题承载真实结构时，请保留它们。
- 提取结论、概念、类别、步骤、证据、决策和行动。
- 合并重复项并删除低价值细节。
- 保持节点简短且可扫描。
- 保持标题深度连续。
- 优先使用 Markdown 标题表示层次结构，使用项目符号表示叶细节。

## 生成

首先准备 Markdown。然后通过管道将其传递到此技能文件夹中的捆绑客户端：

```bash
printf '%s' "$MARKDOWN" | node scripts/processon-mindmap.mjs \
  --mode general \
  --title "<title>" \
  --structure mind_free \
  --markdown -
```

对于长内容，优先使用标准输入而不是在仓库中创建临时 Markdown 文件。

结果是 JSON。当存在时，请保留 `imgUrl` 和 `visitUrl`。