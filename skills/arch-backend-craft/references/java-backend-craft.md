# Java 后端专项规范

面向 Java 17+ / Spring Boot 3.x / JPA (Hibernate) / MyBatis / Flyway / Liquibase 后端服务的高频生产深坑与工程标准。通用架构、调试与评审纪律见核心参考，本手册聚焦 JVM 与 Spring 生态最易踩雷的真实问题。

## 1. 模块封装、依赖注入与无状态单例

### 构造器注入与包级封装
- **强制构造器注入**（配 `private final` 字段），禁用 `@Autowired` 字段注入：依赖关系在编译期与单测期显式可见，同时天然暴露循环依赖。
- **模块只暴露 `public` Facade / Service 接口与 DTO**，内部 Repository、转换器、策略实现尽量保持 package-private（默认包可见性），从编译器层面阻断跨模块深插内部实现。
- **Spring 单例 Bean 严禁持有请求级可变状态**：Service / Controller / Component 默认全局单例，把当前用户、临时列表、非线程安全格式化器（如 `SimpleDateFormat`）写成成员变量会在高并发下瞬间串数据；时间格式化一律使用线程安全的 `DateTimeFormatter` 与 `java.time.*`。

### 配置类型安全与凭据脱敏
- 用 `@ConfigurationProperties` + `@Validated`（Jakarta Validation）把配置收拢到不可变 record / 配置类，启动期即失败暴露缺项；
- 实体/配置类的 `toString()` 绝不打印 `password`、`secret`、`token`、`apiKey` 字段（使用 Lombok 时对敏感字段加 `@ToString.Exclude`）。

---

## 2. `@Transactional` 四大生产陷阱与连接池保护

Spring 事务基于 AOP 代理实现，以下 4 类陷阱在线上故障中占比极高：

| 陷阱 | 表现与根因 | 正确修法 |
| --- | --- | --- |
| **1. 同类自调用失效** | `this.saveOrder()` 绕过 Spring 代理，`@Transactional` 形同虚设 | 把事务方法拆到独立 Service Bean，或由外部调用方经代理进入 |
| **2. Checked Exception 不回滚** | 默认仅对 `RuntimeException` / `Error` 回滚，抛出 `IOException` 等受检异常竟然提交了！ | 显式声明 `@Transactional(rollbackFor = Exception.class)` |
| **3. 吞异常破坏回滚** | 在事务方法里 `catch (Exception e)` 后只打日志不重抛，事务照常提交 | 需要回滚就重抛领域异常，或显式 `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` |
| **4. 事务内发远程 I/O 拖爆连接池** | 在 `@Transactional` 内调 HTTP / RPC / MQ 慢接口，长期占住 HikariCP 数据库连接，并发一高全站超时 | 把远程调用移出事务边界，或拆成「事务外调外部 → 编程式 `TransactionTemplate` 精准包 DB 写入」 |

```java
// ✅ 正例：事务边界精准收窄，远程调用绝不占住数据库连接
public OrderDTO createOrder(CreateOrderCmd cmd) {
    // 1. 事务外完成外部校验/价格查询（带明确超时）
    PriceQuote quote = pricingClient.quote(cmd.skuId(), cmd.quantity());

    // 2. 精准事务只包裹数据库写入与本地事件表（Outbox）
    OrderEntity saved = transactionTemplate.execute(status -> {
        OrderEntity order = OrderEntity.create(cmd, quote);
        orderRepository.save(order);
        outboxRepository.save(OutboxEvent.orderCreated(order));
        return order;
    });
    return OrderDTO.from(Objects.requireNonNull(saved));
}
```

- 只读查询标注 `@Transactional(readOnly = true)`，减少 Hibernate 脏检查开销并利于主从读写路由。
- 避免盲目叠加 `REQUIRES_NEW` 嵌套事务：外层持有连接 1 时内层再申请连接 2，当并发数达到 HikariCP 最大连接数时会发生**连接池死锁**。

---

## 3. JPA / Hibernate 与 MyBatis 契约与性能红线

- **显式关闭 OSIV（`spring.jpa.open-in-view=false`）**：开启 OSIV 会让数据库连接一直挂到整个 HTTP 视图渲染结束，把 N+1 延迟加载藏进 JSON 序列化阶段并耗尽连接池。
- **严禁 Controller 直接返回 JPA Entity**：必须映射为不可变 `record` DTO，既避免敏感字段/循环引用泄漏，也彻底切断持久化上下文泄漏。
- **治理 N+1 查询**：列表查关联数据显式使用 `JOIN FETCH`、`@EntityGraph` 或批量 IN 查询；注意分页查询不要对 `@OneToMany` 直接 `JOIN FETCH`（Hibernate 会在内存中全表分页！应先分页查主表 ID，再按 ID 批量查关联）。
- **MyBatis 防 SQL 注入铁律**：所有值参数一律使用 `#{param}` 预编译占位符；**禁止把外部输入放入 `${param}`**，动态排序字段/方向必须经显式 `Map` / 枚举白名单转换后再拼接。
- **并发写乐观锁**：实体/表加 `@Version`（或 SQL `WHERE id = ? AND version = ?` 检查影响行数 = 1），冲突返回 `409 CONFLICT` 而不是静默后写覆盖先写。

---

## 4. Flyway / Liquibase 不可变迁移规范

- **已部署的迁移脚本严禁修改**：Flyway 校验 checksum，改动已执行脚本会直接阻断生产启动；修正只能追加新版本号脚本（如 `V012__...sql`）。
- **关闭生产环境自动建表**：`spring.jpa.hibernate.ddl-auto=validate`（绝不用 `update` 或 `create-drop`），Schema 演进 100% 归迁移工具单源管理。
- **大表 DDL 与滚动发布安全**：新增列先允许可空或带轻量默认值，重命名/删列严格走四阶段扩张-收缩（Expand → Backfill → Switch → Contract），避免锁表或打挂滚动升级中的旧版本实例。

---

## 5. 入口校验、统一错误信封与安全防线

### Bean Validation + 全局 `@RestControllerAdvice`
- 所有请求 DTO 标注 `@Valid` 与 Jakarta 约束注解（`@NotBlank`、`@Size`、`@Min`/`@Max`、`@Pattern`）；
- 全局 `@RestControllerAdvice` 统一将校验失败、乐观锁冲突、业务异常、未知异常映射为脱敏结构化错误信封（或 RFC 9457 `ProblemDetail`），不把堆栈与 SQL 原文返回客户端。

### NIO 路径防逃逸与归档防 Zip Slip / Zip Bomb
```java
public static Path resolveContainedPath(Path baseDir, String untrustedRel) throws IOException {
    if (untrustedRel == null || untrustedRel.isBlank() || untrustedRel.indexOf('\0') >= 0) {
        throw new IllegalArgumentException("路径非法");
    }
    Path baseReal = baseDir.toRealPath();
    Path target = baseReal.resolve(untrustedRel).normalize();
    if (!target.startsWith(baseReal)) {
        throw new SecurityException("路径越出允许目录: " + untrustedRel);
    }
    if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
        if (Files.isSymbolicLink(target) || !target.toRealPath().startsWith(baseReal)) {
            throw new SecurityException("禁止符号链接越界: " + untrustedRel);
        }
    }
    return target;
}
```

- **解压 ZIP 必须双防**：每条 `ZipEntry` 用 `normalize().startsWith(baseDir)` 防 Zip Slip；同时用有界流按字节累加真实解压大小（不轻信 `entry.getSize()`）并限制最大条目数与压缩比，防 Zip Bomb 打爆磁盘与内存。
- **原子写盘**：先在同目录 `Files.createTempFile(target.getParent(), ...)` 写入并 `FileChannel.force(true)`，再 `Files.move(tmp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)`。
- **外部调用与线程池资源卫生**：
  - 所有 HTTP 客户端（`RestClient` / `WebClient` / `HttpClient`）显式配置连接超时与读取超时；
  - 禁用无界 `Executors.newFixedThreadPool` / `newCachedThreadPool` 导致 OOM，使用有界队列 + 明确拒绝策略 + 优雅停机（`server.shutdown=graceful`）；
  - 文件流、数据库连接、`ZipInputStream` 一律放在 `try-with-resources` 中确保释放。
