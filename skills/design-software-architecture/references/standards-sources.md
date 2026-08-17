# 标准与权威来源

## 架构描述

- ISO/IEC/IEEE 42010:2022 — Software, systems and enterprise — Architecture description  
  https://www.iso.org/standard/74393.html

该标准规定 Architecture Description 的结构与表达要求，并定义 viewpoint、model kind 等架构描述概念。它不规定某一种软件架构风格。

## 质量模型

- ISO/IEC 25010:2023 — SQuaRE — Product quality model  
  https://www.iso.org/standard/78176.html

用于系统化识别和评估产品质量属性。项目仍需把质量属性转换成自己的可测场景和验收指标。

## 架构图

- C4 Model  
  https://c4model.com/

C4 使用 System Context、Container、Component、Code 等不同缩放层级。多数团队通常只需要 Context 和 Container；Code 层通常应由工具按需生成。

## 安全架构

- OWASP Threat Modeling Cheat Sheet  
  https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html

威胁建模应在设计阶段开始，并随系统演进维护。

## 架构风格参考

- Microsoft Azure Architecture Center — Architecture styles  
  https://learn.microsoft.com/azure/architecture/guide/architecture-styles/

- Microsoft Azure Architecture Center — Event-driven architecture style  
  https://learn.microsoft.com/azure/architecture/guide/architecture-styles/event-driven

- AWS Prescriptive Guidance — Decomposing monoliths into microservices  
  https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-decomposing-monoliths/

这些属于平台方工程指导，不是跨行业强制标准。用于比较适用条件、收益和代价，不应被描述为唯一正确架构。

## ADR

- Architecture Decision Record community repository  
  https://github.com/architecture-decision-record/architecture-decision-record

ADR 用于记录重要架构决策的上下文、决定与后果。

## 使用原则

- 区分国际标准、开放模型、平台最佳实践和组织决策。
- 标准提供概念和约束，不替代业务上下文。
- 架构风格没有统一“最佳实践”；必须根据质量属性和约束选择。
