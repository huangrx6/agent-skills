# 架构文档、ADR 与图

## 目录

- [文档最小集合](#文档最小集合)
- [ADR](#adr)
- [C4](#c4)
- [动态与部署视图](#动态与部署视图)
- [图的规则](#图的规则)
- [文档生命周期](#文档生命周期)

## 文档最小集合

推荐只维护：

1. Architecture Brief；
2. System Context；
3. Container/Deployment 视图；
4. 关键动态流程；
5. ADR Log；
6. 风险登记。

不要求所有系统维护完整 UML 集合。

## ADR

ADR 用于架构显著决策。

状态：

```text
Proposed
Accepted
Rejected
Superseded
Deprecated
```

内容：

- Context；
- Drivers；
- Decision；
- Alternatives；
- Consequences；
- Risks；
- Validation；
- Revisit Trigger。

一个 ADR 聚焦一个主要决策。

不要修改历史 ADR 让它看起来一直正确；用新 ADR supersede 旧 ADR。

## C4

优先：

- System Context；
- Container。

只有复杂模块确实需要时才画 Component。

Code diagram 通常由 IDE 或代码生成，不建议长期手工维护。

## 动态与部署视图

需要解释跨组件流程时画 Dynamic Diagram。

需要解释运行环境、故障域和网络边界时画 Deployment Diagram。

不要在静态容器图里塞入所有请求顺序。

## 图的规则

每张图必须：

- 有标题；
- 有范围；
- 有受众；
- 有图例或一致 notation；
- 标明关系方向和含义；
- 标明技术或协议；
- 不混合过多抽象层级。

避免：

```text
System A → System B
```

但没有说明“调用什么、为什么、同步还是异步”。

## 文档生命周期

文档必须有：

- Owner；
- Last Reviewed；
- 适用系统版本或范围；
- 源文件；
- 自动生成方式（如果有）。

重大架构变更与代码在同一变更中更新。

过时且无法维护的图应删除，而不是保留错误信息。
