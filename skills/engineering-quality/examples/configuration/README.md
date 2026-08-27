# 示例：配置管理产出样例（虚构项目）

> 本项目设定：虚构公司 "NovaPay" 的订单服务，Java 21 + Kubernetes + 配置中心。
> 演示用本 skill 产出的配置分类、Schema、优先级、动态配置、Secret 分离端到端示范。
> **本示例不抄用、仅作参照——配置默认值和优先级是本组织决策，不直接复制他人默认。**

## 文件

- `configuration-design.example.md` — 配置分类 + Schema + 优先级 + 动态配置 + Secret + 变更流程端到端示范

## 要点

1. **分类决定变更方式**：Code Constant/Deployment/Secret/Dynamic/Feature Flag 各有不同变更与回滚。
2. **Secret 只存引用**：普通配置保存 secret_ref，不保存原值。
3. **原子生效**：相关字段同 revision 更新，不半套生效。
4. **last-known-good**：配置中心故障保留最后有效版本，不空值覆盖。
5. **K8s 生效语义**：env 注入 vs volume 挂载刷新行为不同。
