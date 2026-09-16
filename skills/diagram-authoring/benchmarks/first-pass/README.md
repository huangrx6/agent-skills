# First-Pass 可用性基准

测一个产品问题：**普通模型第一次生成的规格，不经人工修补能不能用？**

这是一道交付门，不是模型排行榜。`first_pass_usable = true` 当且仅当三门全过：

1. **语义门** —— 清单必须节点恰好绑到一个节点、必须边按声明方向存在；
2. **校验门** —— `validate_spec` 无 error，布局 + `--quality showcase` 无阻塞；
3. **人审门** —— 人在真实渲染里看过且无缺陷。`skipped` 永远不能算 usable。

三门互不冒充：校验全绿说明不了语义对，语义对说明不了好看。

## 套件

`manifest.json` 五个案例（架构 / 流程 / 依赖 / 状态 / 网状），每个声明
必须节点（别名表）、必须边与方向。模型自由选内部 id、分组与措辞 ——
别名绑定不替代拓扑。

## 公平跑法（协议）

- 同一 prompt、同一 skill 提交、同一时限、同一工具面、干净的输出目录；
- **一次完整调用 = attempt 1**；调用结束时候选冻结，此后不许任何事后编辑
  （包括人工）。修正轮可以保留用于诊断，但 first-pass 只认 attempt 1；
- 期间允许模型用本 skill 的 CLI 自校验自修复（这正是被测能力）；
- 记录确切的 agent 与模型名。跑完矩阵再下结论，不完整的矩阵不是证据。

## 跑一次验证

```sh
# 1. 外部 runner 让模型按 manifest 里的 prompt 生成 candidate.diagram.json 并冻结
# 2. 人审后写 run.json：
#    {"visual_review": {"status": "passed", "reviewer": "你的名字", "defects": []}}
# 3. 验证：
python3 benchmarks/first-pass/verify.py \
    --case benchmarks/first-pass/manifest.json#release-flow \
    --candidate /path/to/candidate.diagram.json \
    --run /path/to/run.json --json
```

退出码：0 = first-pass usable，1 = 有门没过，2 = 输入不合法。
人审缺陷用短标签：`clipping` / `node-overlap` / `label-overlap` /
`hidden-route` / `stacked-edge` / `weak-hierarchy` / `unbalanced-whitespace`。

## 没跑过就不发布

没有真实发生的运行与人审，不许发布任何模型结果。基准自身先过自检：
对五个案例各造一份「肯定能过」的参考候选，verify 必须全部 0 退出
（参考候选**不是**模型成绩，只证明验证器接线正确）。
