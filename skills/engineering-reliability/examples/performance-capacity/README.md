# 示例：性能与容量产出样例（虚构项目）

> 本项目设定：虚构公司 "NovaPay" 的文档处理平台（AI/OCR/VLM 场景），Java 21 + GPU worker。
> 演示用本 skill 产出的性能预算、Work Unit 建模、负载测试、容量模型端到端示范。
> **本示例不抄用、仅作参照——性能参数没有跨系统统一最佳值，必须以本系统真实负载和实验为事实来源。**

## 文件

- `performance-capacity.example.md` — 性能预算 + Work Unit 模型 + 负载测试 + 容量规划端到端示范

## 要点

1. **归一化 Work Unit**：不同路由成本差异大，按 unit 加权而非裸 QPS。
2. **预算分解**：端到端 SLO 按阶段分配（upload/parse/OCR/VLM/merge）。
3. **找到饱和点**：不只证明"目标 QPS 能跑"，要加压到首个瓶颈。
4. **Headroom 保留**：能承受单 AZ 故障，正常状态不跑满。
5. **回归基线**：与同环境 Baseline 比较，不静默重置。
