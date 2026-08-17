# Acme Pay 后端编码规范——Java 实施附录

> **主规范**：`coding-standards.md`（语言无关）。本附录是 Java 21 + Spring Boot 的具体实施。先读主规范。

## 1. 命名

| 类型 | 命名 | 位置 |
| --- | --- | --- |
| Controller | `XxxController` | `adapter/in/web` |
| 请求 DTO | `XxxRequest` | `adapter/in/web/dto` |
| 响应 DTO | `XxxView` | `adapter/in/web/dto` |
| 应用服务 | `XxxService` | `application/service` |
| 仓库端口 | `XxxRepository`（接口） | `domain/repository` |
| 仓库实现 | `XxxRepositoryImpl` | `adapter/out/persistence` |
| 数据对象 | `XxxDO` | `adapter/out/persistence` |

- DTO 独立成文件，响应统一 `XxxView`（协议信封/SCIM 类型除外）。
- DO 自声明审计列，不继承共享基类。

## 2. 格式化

- Spotless（import 顺序 `java,jakarta,javax,org,com,io,net`、4 空格、行宽 120）+ `.editorconfig`。
- `mvn spotless:apply` 本地格式化，`spotless:check` 为 CI 门禁。

## 3. 持久化（MyBatis-Plus）

- `@TableField("snake_case")` 显式映射；`@TableId(type = ASSIGN_ID)`；逻辑删除 `@TableLogic`。
- 禁 `mybatis-plus.configuration.*`（触发 NoSuchMethodError）。

## 4. 安全（Spring Security）

- `DelegatingPasswordEncoder`，存储带 `{argon2}`/`{bcrypt}` 前缀；**禁 `{noop}`**。

## 5. 事务（Spring）

- 写：`@Transactional(rollbackFor = Exception.class)`；查询：`@Transactional(readOnly = true)`。

## 6. 测试（Java 栈）

- 单元：领域纯逻辑，无 Spring。
- 集成：`@SpringBootTest` 集中在 bootstrap 测试源，`JdbcTemplate` 原始 SQL 断言。

## 7. 自动化质量门禁（Java/Maven）

| 门禁 | 执行 |
| --- | --- |
| 格式 | `mvn spotless:check` |
| 测试 | `mvn test` |
| 安全 | 依赖扫描（如 OWASP dependency-check） |

> 上表为 Java 专属命令；语言无关的门禁原则见主规范 §8。
