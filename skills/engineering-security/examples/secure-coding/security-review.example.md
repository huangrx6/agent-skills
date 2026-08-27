# 安全评审：订单查询接口

> 评审对象：NovaPay `GET /api/v1/orders?merchantRef=X&sort=amount`（虚构）

## 1. Source 识别

- `merchantRef`（query 参数）→ 不可信 Source
- `sort`（query 参数）→ 不可信 Source（进入 SQL 标识符位置，高风险）
- `Authorization` header → 认证信息

## 2. Sink 识别

- `sort` 直接拼接进 SQL `ORDER BY` → **SQL 注入 Sink**（标识符位置，参数化无法覆盖）

## 3. 原始代码（含漏洞）

```java
@GetMapping("/api/v1/orders")
public ApiResponse<List<Order>> list(@RequestParam String merchantRef,
                                     @RequestParam(defaultValue = "id") String sort) {
    String sql = "SELECT * FROM orders WHERE merchant_ref = '" + merchantRef + "' ORDER BY " + sort;
    // ❌ merchantRef 字符串拼接 → SQLi；sort 直接进 ORDER BY → 注入
    List<Order> orders = jdbcTemplate.query(sql, rowMapper);
    return ApiResponse.success(orders);
}
```

## 4. 控制与修复

### 4a. merchantRef → 参数化（结构化安全 API）

```java
@GetMapping("/api/v1/orders")
public ApiResponse<List<Order>> list(@RequestParam String merchantRef,
                                     @RequestParam(defaultValue = "id") String sort) {
    // ✓ 参数化：merchantRef 作为绑定变量
    List<Order> orders = jdbcTemplate.query(
        "SELECT * FROM orders WHERE merchant_ref = ? ORDER BY " + sortColumn(sort) + " " + sortDir(sort),
        new Object[]{merchantRef}, rowMapper);
    return ApiResponse.success(orders);
}
```

### 4b. sort → allowlist 映射（标识符无法参数化，用应用侧映射）

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
    "id", "id", "createdAt", "created_at", "amount", "amount");

private String sortColumn(String sort) {
    String col = SORT_COLUMNS.get(sort);
    if (col == null) throw new BusinessException(INVALID_SORT_FIELD);
    return col;
}
```

### 4c. 授权（认证通过 ≠ 有权限）

```java
// ✓ 资源级授权：只返回当前商户自己的订单，不能传任意 merchantRef 查别人
String currentMerchant = merchantAuth.currentMerchantId();  // 从 Token 解析，不信任 query
```

### 4d. 资源限制

```java
@RequestParam(defaultValue = "20") @Max(100) int size  // 分页硬上限
```

## 5. 安全测试（负向）

```java
@Test
void untrustedSortFieldNeverReachesSqlIdentifier() {
    // sort=amount; DROP TABLE orders-- 应被 allowlist 拒绝，SQL 不含注入串
}

@Test
void userACannotReadUserBOrders() {
    // 传其他商户 merchantRef 应返回 403/404，不泄露存在性
}

@Test
void oversizeSizeParamIsRejected() {
    // size=10000 应被 @Max(100) 拒绝
}
```

## 6. 静态检查与扫描

- SAST：确认无字符串拼接进 SQL（参数化 + allowlist 已消除）
- Secret 扫描：本变更无新 secret
- 依赖扫描：无新依赖

## 7. 安全例外（如有无法立即修复项）

本例无需例外——全部控制可即时实施。若存在（如遗留 ORM 逃生 API 需 2 周迁移），用 `security-exception.template.md` 记录：

- 风险：遗留 `NativeQuery` 可拼标识符
- Owner：交易组
- 期限：2 周
- 补偿：该查询仅允许白名单 sort 且无外部暴露
- 退出条件：迁移到参数化 + allowlist 后关闭

## 8. 完成检查

- ✅ 无新 Source 未处理
- ✅ 无新 Sink（注入点已消除）
- ✅ 权限边界逐资源执行
- ✅ 无新 Secret
- ✅ 资源上限（分页/长度）到位
- ✅ 负向测试覆盖
