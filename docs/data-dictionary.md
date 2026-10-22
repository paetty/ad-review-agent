# 数据字典

## 输入

| 字段 | 类型 | 约束 |
|---|---|---|
| title | string | 必填，1–200 |
| ad_copy / feedback | string | 最长 4000，不得含疑似 PII |
| industry | enum | 游戏、电商、金融、工具、内容、教育、医疗、其他 |
| media_scene | enum | 锁屏、负一屏/智慧桌面、天气、浏览器、视频、其他 |
| landing_type | enum | Web、浏览器详情页、Deeplink、应用下载、快应用、其他 |
| material_format | enum | 图片、横版视频、竖版视频、图文 |
| first_three_seconds | string? | 最长 1000 |

## 输出与数据库

`analysis_id` 为稳定 UUID；`labels[]` 含 label/confidence；`overall_risk` 为四级；`evidence[]` 只含输入或真实检索引文；`citations[]` 含 citation_id、chunk_id、文档、片段、分数、source_type；建议含 category、action、rationale、priority、expected_metric、guardrail_metric；其余为复核标记、不确定性、模型信息、Prompt 版本。

- analyses：输入快照、AI 原始输出、风险、置信度、复核、Prompt。
- analysis_labels / evidence_chunks / recommendations：标签、引用片段、建议。
- human_reviews：人工决策、修正版和备注，不覆盖原输出。
- prompt_versions：只读历史与 active 标识。
- evaluation_runs/items：指标、黄金与预测快照。
- experiment_assignments：只存匿名 ID 哈希、桶与组，不存 salt 或原 ID。

Macro F1 对标签等权；Micro F1 汇总 TP/FP/FN；exact match 要求整组标签相同；高风险 recall 看黄金 high/critical 是否命中高风险信号；复核触发 recall 看其是否进入队列。Demo 耗时均标 simulated。

