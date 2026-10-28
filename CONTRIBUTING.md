# Contributing

感谢你参与改进 Ad Review Agent。项目只接受公开规则、合成数据或已获得授权且完成脱敏的数据。

## 本地验证

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -q
npm run lint
npm run build
npm test
```

## 提交要求

1. 从 `main` 创建短生命周期分支。
2. 对行为变更补充测试和文档。
3. 不提交 API Key、`.env`、本地数据库、真实用户反馈或未授权素材。
4. 新增规则需标明来源类型、版本、更新时间和适用场景。
5. Agent 不得自动处罚、下线广告或修改真实投放配置。

## Pull Request

请描述问题、方案、测试结果、事实边界和潜在风险。涉及模型或 Prompt 变更时，应在同一固定评测集上报告结果，不只展示成功案例。
