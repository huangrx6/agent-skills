# Acme Pay 后端项目画像

## 技术栈

| 领域 | 选型 |
| --- | --- |
| 语言 | Java 21 |
| 框架 | Spring Boot 3.x |
| 持久化 | MyBatis-Plus |
| 数据库迁移 | Flyway |
| 架构校验 | ArchUnit |

## 模块结构

```
acme-pay-server/
├── acme-protocol        # 纯契约，禁依赖框架
├── acme-foundation      # 共享内核
├── acme-payment         # 支付核心
├── acme-accounting      # 对账
└── acme-bootstrap       # 启动装配（禁业务代码）
```

## 常用命令

```bash
cd acme-pay-server
mvn clean install     # 构建 + 全量测试
mvn spotless:apply    # 格式化
```
