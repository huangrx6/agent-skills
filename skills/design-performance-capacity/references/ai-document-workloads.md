# AI、OCR、VLM 与复杂文档容量

## 按成本维度建模

复杂解析不要按文件数建模。建议采集：

- file bytes；
- page count；
- text blocks；
- table regions；
- image regions；
- OCR pixels；
- VLM calls；
- image megapixels；
- model tokens。

## 路由成本加权

不同路由成本通常显著不同：

```text
native text < OCR < VLM image < full-page multimodal
```

容量模型按路由比例加权。示例：

```text
路由        成本(unit)   流量占比   加权
native text  0.2         60%       0.12
OCR          1.0         30%       0.30
VLM image    4.0         5%        0.20
full-page    8.0         5%        0.40
                             合计 = 1.02 units/request
```

容量评估用 1.02 units/request，而不是按文件数。

## OCR/VLM 关注指标

- batch size；
- GPU utilization；
- GPU memory；
- queue wait；
- preprocess / inference / postprocess 时间；
- fallback rate（降级到低成本路由的比例）。

## 在线 vs 离线

吞吐最大的 Batch 不一定满足在线 P99。

- 在线任务：P99 约束，batch 小，延迟敏感；
- 离线任务：吞吐优先，batch 大，可排队；
- 两者使用不同策略或资源池，不混用。

## 远程模型

远程模型还要计算：

- upload bandwidth；
- provider rate limit；
- timeout；
- retry；
- cost/request。

## 优化目标

性能优化目标可以是"满足 SLO 下最低成本"，而不是绝对最快。

- 对成本敏感的 AI 场景，目标是"在 P99 SLO 内用最低 GPU/API 成本"；
- 降低路由成本（如优先 native text 而非 OCR）常比优化速度更划算。

## 验证

- 用真实文档分布做 Load Test（含 small/medium/large、简单/复杂、cache hit/miss）；
- 验证 fallback 路径（VLM 失败降级 OCR 时容量是否仍够）；
- 验证 GPU OOM/排队下的行为。
