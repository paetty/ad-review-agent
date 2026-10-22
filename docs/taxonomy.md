# 多标签 Taxonomy

通用边界：标签只能依据输入或检索证据；证据不足写 `uncertainties`。`no_issue` 与其他标签互斥；它表示“未发现明确问题”，不等于合规通过。

| 标签 | 定义 | 正例 | 反例 / 边界 |
|---|---|---|---|
| forced_or_unexpected_jump | 非明确意图触发跳转 | 未点击就自动打开页面 | 主动点击“查看详情”后正常打开 |
| malicious_or_suspicious_redirect | 疑似病毒、诈骗、钓鱼或恶意链路 | 跳到病毒网站并索要转账 | 仅域名陌生但无恶意证据 |
| misleading_claim | 绝对化、夸大或无法验证宣传 | 100%稳赚、包治 | 有条件和来源的客观参数 |
| vulgar_or_inappropriate_content | 低俗、色情暗示、暴力或场景不适 | 锁屏出现低俗擦边图 | 正常泳装需结合语境人工判断 |
| excessive_ad_frequency | 短窗口曝光过多 | 一分钟弹了五次 | 隔很久出现一次 |
| repetitive_material | 创意长期或连续重复 | 每次都是同一条素材 | 同品牌不同创意 |
| unclear_material | 分辨率、字号或对比度导致不可读 | 小字模糊看不清 | 信息复杂但像素清晰 |
| stale_material | 日期、活动或表达明显过期 | 展示去年的过期活动 | 主观“不新鲜”但无时间证据 |
| weak_first_three_seconds | 视频开场信息效率不足 | 前三秒全是空镜 | 慢开场服务必要叙事 |
| irrelevant_targeting | 内容与意图或场景弱相关 | 天气页出现完全无关内容 | 不喜欢不等于不相关 |
| return_path_friction | 回原媒体路径过长或失败 | 连续返回仍回不去 | 一次返回但动画稍慢 |
| potential_privacy_risk | 过度权限、敏感信息或告知同意风险 | 无关功能强要通讯录 | 天气功能明确说明后请求定位 |
| no_issue | 当前证据无明确问题 | 打开、浏览、返回均正常 | 不能与问题标签并存 |

风险默认映射：恶意/隐私为 critical；强制跳转、不适内容、返回摩擦为 high；一般质量与相关性为 medium；仅 no_issue 为 low。规则只作辅助，人工可修正。

