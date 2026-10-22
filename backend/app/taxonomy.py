from __future__ import annotations

LABELS = [
    "forced_or_unexpected_jump", "malicious_or_suspicious_redirect", "misleading_claim",
    "vulgar_or_inappropriate_content", "excessive_ad_frequency", "repetitive_material",
    "unclear_material", "stale_material", "weak_first_three_seconds",
    "irrelevant_targeting", "return_path_friction", "potential_privacy_risk", "no_issue",
]

LABEL_NAMES = {
    "forced_or_unexpected_jump": "强制或非预期跳转", "malicious_or_suspicious_redirect": "恶意/可疑重定向",
    "misleading_claim": "夸大或误导宣传", "vulgar_or_inappropriate_content": "低俗或不适内容",
    "excessive_ad_frequency": "广告频率过高", "repetitive_material": "素材重复",
    "unclear_material": "素材不清晰", "stale_material": "素材陈旧",
    "weak_first_three_seconds": "视频前三秒吸引力不足", "irrelevant_targeting": "内容或场景不相关",
    "return_path_friction": "返回路径过长", "potential_privacy_risk": "潜在隐私风险", "no_issue": "未发现明确问题",
}

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

KEYWORDS = {
    "forced_or_unexpected_jump": ["自动跳转", "强制跳转", "自己打开", "误触就跳", "未经同意", "莫名跳转"],
    "malicious_or_suspicious_redirect": ["病毒", "木马", "恶意网站", "诈骗", "钓鱼", "可疑链接", "诱导跳转"],
    "misleading_claim": ["稳赚", "绝对", "100%", "包治", "第一", " guaranteed", "无需条件", "夸大"],
    "vulgar_or_inappropriate_content": ["低俗", "色情", "裸露", "暴力", "不适", "擦边"],
    "excessive_ad_frequency": ["广告太多", "频繁", "一直弹", "每次都", "重复出现", "刷屏"],
    "repetitive_material": ["素材重复", "同一广告", "看腻", "重复素材", "总是这条"],
    "unclear_material": ["模糊", "看不清", "马赛克", "小字", "低清", "文字太小"],
    "stale_material": ["过时", "陈旧", "去年", "旧活动", "缺乏新鲜", "日期已过"],
    "weak_first_three_seconds": ["开头无聊", "开场拖沓", "前三秒只有空镜", "核心信息出现较晚", "开场没有重点"],
    "irrelevant_targeting": ["不相关", "不感兴趣", "完全无关", "场景不符", "不适合我"],
    "return_path_friction": ["返回很多次", "回不去", "无法返回", "连续返回", "返回路径", "退不出来"],
    "potential_privacy_risk": ["通讯录", "定位权限", "隐私", "手机号", "身份证", "监听", "过度授权"],
}

CRITICAL_LABELS = {"malicious_or_suspicious_redirect", "potential_privacy_risk"}
HIGH_LABELS = {"forced_or_unexpected_jump", "vulgar_or_inappropriate_content", "return_path_friction"}

# These phrases express sentiment without a concrete, auditable failure mode.
VAGUE_FEEDBACK_CUES = [
    "感觉奇怪", "有点奇怪", "体验不好", "不太好", "不舒服", "看着难受",
    "不喜欢", "有问题", "怪怪的", "一般般", "不太对劲",
]

# Only direct, short-range negation is handled by the deterministic engine.
NEGATION_TERMS = ["并不是", "并没有", "并未", "并不", "没有", "没", "未", "不是", "不再", "不会", "不", "无"]
