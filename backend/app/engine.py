from __future__ import annotations
import hashlib, json, time, uuid
from .schemas import AnalysisInput, AnalysisOutput, Citation, Evidence, LabelResult, ModelInfo, Recommendation
from .taxonomy import CRITICAL_LABELS, HIGH_LABELS, KEYWORDS, NEGATION_TERMS, RISK_ORDER, VAGUE_FEEDBACK_CUES

RECOMMENDATIONS = {
    "forced_or_unexpected_jump": ("product", "检查点击意图与跳转触发条件，提供明确返回入口", "降低非预期跳转和返回阻力", "P0", "非预期跳转反馈率", "落地页到达率"),
    "malicious_or_suspicious_redirect": ("delivery", "暂停自动放量并核验重定向链路、域名与安全状态", "疑似恶意链路需先阻断风险", "P0", "恶意跳转拦截率", "误拦截率"),
    "misleading_claim": ("creative", "删除无法验证的绝对化表述并补充适用条件", "减少误导性表达", "P1", "误导投诉率", "素材通过率"),
    "vulgar_or_inappropriate_content": ("review", "限制投放并提交内容安全人工复核", "内容风险需要人工判断语境", "P0", "不适内容投诉率", "审核误杀率"),
    "excessive_ad_frequency": ("delivery", "设置场景级频控并监控重复曝光", "避免连续曝光造成体验疲劳", "P1", "人均重复曝光次数", "有效触达率"),
    "repetitive_material": ("creative", "扩大素材轮换池并设置素材冷却窗口", "提高素材新鲜度", "P2", "重复素材反馈率", "制作成本"),
    "unclear_material": ("creative", "提升分辨率、字号和关键文案对比度", "保证核心信息可读", "P1", "清晰度人评分", "素材加载时延"),
    "stale_material": ("creative", "校验活动日期并建立素材过期下线规则", "避免展示失效信息", "P1", "过期素材率", "可用素材覆盖率"),
    "weak_first_three_seconds": ("creative", "将核心利益点和品牌信息前置到视频前三秒", "改善开场信息效率", "P2", "3秒留存率", "负反馈率"),
    "irrelevant_targeting": ("delivery", "收窄场景与行业匹配条件并观察相关性反馈", "提升内容与场景匹配", "P2", "相关性人评分", "可投库存覆盖率"),
    "return_path_friction": ("product", "缩短返回原媒体路径并提供可识别的一键返回入口", "减少被迫停留", "P0", "返回成功率", "误触返回率"),
    "potential_privacy_risk": ("review", "暂停自动放量并人工核查权限申请、隐私告知与数据最小化", "潜在隐私泄漏不得自动处置", "P0", "隐私风险确认率", "误报率"),
    "no_issue": ("review", "保持监测，无需自动限制", "当前输入未提供明确问题证据", "P2", "后续负反馈率", "人工复核量"),
}

def _risk(labels: set[str]) -> str:
    if labels & CRITICAL_LABELS: return "critical"
    if labels & HIGH_LABELS: return "high"
    if labels == {"no_issue"}: return "low"
    return "medium"

def enforce_rules(payload: dict) -> dict:
    names = {x["label"] for x in payload.get("labels", [])}
    if len(names) > 1:
        payload["labels"] = [x for x in payload["labels"] if x["label"] != "no_issue"]
        names.discard("no_issue")
    expected = _risk(names or {"no_issue"})
    if RISK_ORDER[expected] > RISK_ORDER.get(payload.get("overall_risk", "low"), 0): payload["overall_risk"] = expected
    if payload["overall_risk"] == "critical" or any(x["confidence"] < .62 for x in payload["labels"]): payload["requires_human_review"] = True
    return payload

def _is_negated(text: str, start: int) -> bool:
    """Return True when a keyword is directly scoped by a Chinese negator."""
    prefix = text[max(0, start - 8):start].replace(" ", "")
    return any(prefix.endswith(term) for term in NEGATION_TERMS)

def match_keywords(fields: dict[str, str]) -> dict[str, list[tuple[str, str]]]:
    matched: dict[str, list[tuple[str, str]]] = {}
    for label, words in KEYWORDS.items():
        hits: list[tuple[str, str]] = []
        for field, text in fields.items():
            lowered = text.lower()
            for word in words:
                start = lowered.find(word.lower())
                while start >= 0:
                    if not _is_negated(lowered, start):
                        hits.append((field, word))
                        break
                    start = lowered.find(word.lower(), start + len(word))
        if hits:
            matched[label] = hits
    return matched

class DemoEngine:
    def analyze(self, item: AnalysisInput, citations: list[dict], prompt_version: str = "demo-v1.0") -> AnalysisOutput:
        start = time.perf_counter()
        fields = {"title": item.title, "ad_copy": item.ad_copy, "feedback": item.feedback, "first_three_seconds": item.first_three_seconds or ""}
        joined = " ".join(fields.values()).lower()
        matched = match_keywords(fields)
        if not matched: matched = {"no_issue": []}
        labels = [LabelResult(label=k, confidence=round(min(.96, .68 + .08 * len(v)), 2) if v else .7) for k, v in matched.items()]
        evidence = []
        for label, hits in matched.items():
            for field, word in hits[:2]:
                text = fields[field]
                pos = text.lower().find(word.lower())
                evidence.append(Evidence(source="input", field=field, quote=text[max(0,pos-18):pos+len(word)+28]))
        for c in citations[:2]: evidence.append(Evidence(source="retrieval", quote=c["snippet"][:180], citation_id=c["citation_id"]))
        recs = [Recommendation(category=(r:=RECOMMENDATIONS[label])[0], action=r[1], rationale=r[2], priority=r[3], expected_metric=r[4], guardrail_metric=r[5]) for label in matched]
        uncertainty = []
        if not item.feedback.strip(): uncertainty.append("未提供用户反馈，结论主要基于素材文字。")
        elif matched == {"no_issue": []} and any(cue in item.feedback for cue in VAGUE_FEEDBACK_CUES):
            uncertainty.append("反馈表达较模糊，缺少可定位的问题、触发动作或结果；未据此推断具体风险。")
        if item.image_filename: uncertainty.append("Demo Mode 不支持视觉理解，本次仅分析文字和文件名元数据。")
        if matched == {"no_issue": []}: uncertainty.append("输入未出现明确风险信号；不代表素材已通过法务或人工审核。")
        fingerprint = hashlib.sha256(json.dumps(item.model_dump(), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        latency = 120 + int(fingerprint[:4], 16) % 181
        input_tokens = max(40, len(joined) // 2)
        payload = {
            "analysis_id": str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint)), "labels": [x.model_dump() for x in labels],
            "overall_risk": _risk(set(matched)), "confidence": round(sum(x.confidence for x in labels)/len(labels),2),
            "evidence": [x.model_dump() for x in evidence], "citations": citations,
            "strategy_recommendations": [x.model_dump() for x in recs],
            "requires_human_review": bool(item.image_filename) or _risk(set(matched)) in {"high","critical"} or any(x.confidence < .62 for x in labels),
            "uncertainties": uncertainty,
            "model_info": ModelInfo(provider="deterministic_rules", model="demo-engine-v1", mode="demo", latency_ms=latency, input_tokens=input_tokens, output_tokens=160+len(recs)*35, estimated_cost_usd=0, simulated=True).model_dump(),
            "prompt_version": prompt_version,
        }
        return AnalysisOutput.model_validate(enforce_rules(payload))

def repair_model_output(raw: str) -> dict:
    text = raw.strip().removeprefix("```json").removesuffix("```").strip()
    try: return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start: return json.loads(text[start:end+1])
        raise

