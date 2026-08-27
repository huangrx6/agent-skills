# 示例：完整规范产出样例（Acme Pay 后端）

> 本目录是一个**虚构项目**的规范样例，演示用本 skill 产出的完整成品长什么样。
> 不抄用，作参照。项目设定：Acme Pay，Java 21 + Spring Boot 后端，单语言。
> 采用"主规范 + 语言附录"两层（详见 repository-layout.md）。
> 本样例为顶层平铺以方便对比，实际项目建议放 `docs/standards/` 下（参见 `repository-layout.md`）。

## 文件

- `coding-standards.md` — 主规范（语言无关，九段结构）
- `coding-standards-java.md` — Java 实施附录
- `project-profile.md` — 项目画像

## 如何使用本样例

1. 本样例为**演示参考**：展示主规范/附录/画像的分层形态与九段结构，不承诺覆盖全部检查项。
2. 对照 `assets/standard-completeness-checklist.csv`，用其逐条核对你自己的规范产出是否覆盖九段——这是自查示范的用法。
3. 注意每条规则的强度标注（必须/应/可）与执行方式（可自动化/需评审）。
4. 语言附录开头声明依赖主规范，不重复规则——这是分层的关键。
