# 示例：UI 布局规格样例（虚构页面）

> 本目录演示用本 skill 产出的 UI 布局规格样例。
> **示例中的截图是虚构的，未提供真实 PNG**（`canvas` 和 Evidence Ledger 中的 `image_probe.py` 命令演示格式）；
> **尺寸、颜色、字号与置信度均应基于真实视觉证据**，不直接复制本样例数值。

## 文件

- `orders-page.example.md` — 虚构订单列表页 §1–§10 Markdown 输出样例；
- `orders-page.example.layout.json` — 同页面对应的机器结果 JSON。

## 要点

1. **双轨证据**：视觉语义（VLM）+ 确定性测量（`image_probe.py`）；
2. **§1–§10 骨架**：来源、令牌、分区、组件、图表、文案、状态、实现提示、待确认、自检；
3. **Observed / Normalized / Recommended**：设计令牌分三态，前端可落地到 token 系统；
4. **Evidence Ledger**：每条事实引用可重跑命令（`EV-001` 等）；
5. **Low Confidence 进入 §9**：未提供状态、单图响应式、字体族等。

## 校验

```bash
python scripts/validate_skill_assets.py .
python scripts/validate_layout_spec.py examples/orders-page.example.md
```