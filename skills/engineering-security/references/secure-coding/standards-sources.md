# 标准与权威来源

## OWASP ASVS

- OWASP Application Security Verification Standard  
  <https://owasp.org/www-project-application-security-verification-standard/>

当前稳定版为 ASVS 5.0.0（2025-05）。ASVS 提供现代 Web 应用和服务的技术安全验证要求，可用于建立 Secure Coding 和安全测试基线。

引用 ASVS Requirement 时建议包含版本，例如：

```text
v5.0.0-1.2.5
```

不要把 bleeding-edge master 当作生产稳定基线。

## OWASP Cheat Sheet Series

- Index  
  <https://cheatsheetseries.owasp.org/>

关键主题：

- Input Validation
- SQL Injection Prevention
- Cross Site Scripting Prevention
- Authorization
- Authentication
- Session Management
- Password Storage
- Secrets Management
- SSRF Prevention
- File Upload
- Deserialization
- XXE Prevention
- CSRF Prevention
- CORS
- Content Security Policy
- Cryptographic Storage
- OS Command Injection Defense
- Secure Code Review

Cheat Sheet 是实践指导，不等同于协议标准。

## NIST SSDF

- NIST SP 800-218 — Secure Software Development Framework (SSDF) Version 1.1  
  <https://csrc.nist.gov/pubs/sp/800/218/final>

SSDF 描述将安全实践整合进软件开发生命周期的组织级实践。本 Skill 主要使用其“安全必须进入日常开发和验证流程”的原则，不复制其采购/组织治理全部内容。

## CWE

- CWE  
  <https://cwe.mitre.org/>

CWE 用于统一描述软件弱点类型，适合把静态分析、代码评审和缺陷数据映射到稳定分类。

不要用 CWE 编号替代具体修复指导。

## OWASP LLMSVS

- OWASP Large Language Model Security Verification Standard  
  <https://owasp.org/www-project-llm-verification-standard/>

当产品本身包含 LLM/Agent 能力时，需要额外评估模型输入、工具权限、Prompt Injection、模型/向量数据和 Agent 运行边界。本 Secure Coding Skill 只覆盖 AI 作为编码工具时的开发安全。

## 使用原则

优先级：

1. 语言/平台官方安全 API；
2. 稳定安全标准；
3. OWASP 等维护中的实践指南；
4. 组织安全决策。

安全配置、算法和框架版本会变化，实现时应核对当前官方资料。
