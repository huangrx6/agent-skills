# 依赖与供应链基础安全

## 适用范围

本文件只规定 Secure Coding 阶段的最小依赖安全。

完整 SBOM、构建签名、Provenance 和供应链治理可独立建立专门 Skill。

## 新增依赖

新增前确认：

- 包真实存在；
- 官方名称和 registry；
- publisher/maintainer；
- 下载量不是唯一安全指标；
- 最近维护；
- license；
- known vulnerabilities；
- transitive dependency 规模；
- 是否已有标准库/现有依赖可完成。

## AI 推荐依赖

AI 可能生成看似真实但不存在的包名。

必须从官方 registry/项目站点确认：

- exact name；
- publisher；
- official repository；
- supported version。

禁止直接执行模型提供的任意：

```text
curl ... | sh
pip install unknown-name
npm install typo-package
```

## 版本

- lockfile 提交；
- 生产构建可重复；
- 不使用无限浮动版本；
- 及时应用安全更新；
- 大版本升级执行回归。

## 脚本

审查：

- install scripts；
- postinstall；
- build plugins；
- Gradle/Maven plugin；
- GitHub Action；
- Docker base image。

构建脚本本身就是代码执行。

## Dependency Confusion / Typosquatting

- 配置私有 namespace；
- 固定 registry；
- 对内部包使用不可冲突命名；
- 不从多个不受控源按最高版本自动解析。

## 废弃依赖

删除未使用依赖。

依赖越多：

- 攻击面越大；
- 补丁成本越高；
- 供应链复杂度越高。
