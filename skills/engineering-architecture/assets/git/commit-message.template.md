# Conventional Commit 模板

## 标准格式

```
<type>[scope][!]: <简短描述>

<可选正文：解释 why，不重复 how>

<可选 footer>
```

## 示例：功能

```
feat(orders): add bulk export endpoint

支持按日期范围批量导出订单为 CSV。导出任务异步执行，
完成后通知用户。

Closes #142
```

## 示例：修复

```
fix(auth): redirect on expired token

Token 过期后前端未正确重定向到登录页，导致 401 后白屏。
改为在 axios 拦截器中捕获 401 并 push 到 /login。
```

## 示例：破坏性变更

```
feat(api)!: change export endpoint to async

BREAKING CHANGE: /api/v1/orders/export（同步）已移除，
改用 /api/v2/orders/export（异步任务）。迁移：调用新端点
获取 task_id，轮询 /api/v2/tasks/<id> 获取结果。
```

## 示例：重构

```
refactor(parser): extract token classifier

将 token 分类逻辑从 parse() 提取到独立类，便于复用。
外部行为不变，测试全部通过。
```

## 撰写检查

- [ ] type 准确（feat/fix/docs/...）
- [ ] scope 是稳定代码区域名（可选）
- [ ] 描述英文祈使语气，首字母小写，无句号
- [ ] 描述 ≤ 50 字符
- [ ] 正文解释 why（不重复 diff）
- [ ] BREAKING CHANGE 有迁移路径
- [ ] 无密钥/内部地址/工单号堆砌
