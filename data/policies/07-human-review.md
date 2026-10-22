---
source_type: synthetic_demo
title: 人工复核与风险升级演示规范
version: 1.0
updated_at: 2026-08-17
applicable_scenarios: all
---
## 复核触发
critical 风险必须进入人工复核。high 风险和低置信度样本默认进入队列。自动分析只提供辅助判断，不执行处罚、下线或线上策略修改。

## 冲突处理
规则与模型冲突时采用更保守的风险等级并记录冲突；人工修正版作为新记录保存，不覆盖 AI 原始输出，以支持追溯和后续评测。

