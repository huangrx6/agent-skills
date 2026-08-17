# 权威来源

## 官方工程指导

- Kubernetes ConfigMap
  https://kubernetes.io/docs/concepts/configuration/configmap/

- Kubernetes Secrets / Good Practices
  https://kubernetes.io/docs/concepts/configuration/secret/
  https://kubernetes.io/docs/concepts/security/secrets-good-practices/

- Kubernetes Updating Configuration via ConfigMap
  https://kubernetes.io/docs/tutorials/configuration/updating-configuration-via-a-configmap/

- OWASP Secrets Management Cheat Sheet
  https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

- 12-Factor App — Config
  https://12factor.net/config

- HashiCorp Vault — Secrets Management
  https://developer.hashicorp.com/vault/docs

## 适用主题映射

| 主题 | 权威来源 |
| --- | --- |
| K8s ConfigMap/Secret | Kubernetes Docs |
| ConfigMap 更新生效语义 | Kubernetes Updating ConfigMap |
| Secret 安全 | OWASP Secrets Management、K8s Good Practices |
| 配置与环境的分离 | 12-Factor App Config |
| Secret 管理平台 | Vault Docs |

## 使用原则

- 平台的动态刷新行为必须以实际部署方式和当前官方文档/测试为准，不假设统一行为（env vs volume vs subPath 不同）。
- 配置优先级、默认值和校验强度是本组织决策，不直接复制他人默认。
- 区分"平台能力"（K8s ConfigMap 刷新语义）vs"安全建议"（OWASP Secret 管理）vs"组织决策"（本系统优先级）。
- Secret 涉及安全合规时，以组织安全策略和 OWASP 为准。
