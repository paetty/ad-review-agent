# Security Policy

## Supported versions

当前仅维护最新的 `main` 分支。

## Reporting a vulnerability

请不要在公开 Issue 中发布密钥、个人信息、可利用的攻击细节或真实广告数据。请通过仓库维护者在 GitHub 个人资料中公开的安全联系方式私下报告，并说明影响范围、复现步骤和建议修复方式。

## Data boundaries

- API Key 仅由后端环境变量读取。
- 图片仅在请求内存中处理，默认不持久化。
- CSV 会拦截常见直接标识字段和正文模式。
- AI 输出只用于辅助判断；高风险样本进入人工复核。
