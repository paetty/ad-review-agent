"""Small, explicit evidence policy; not a general Chinese semantic classifier."""
import re

from .schemas import Recommendation

ANALYSIS_POLICY_VERSION = "evidence-boundary-v2"
ANALYSIS_DISCLAIMER = "当前结果是基于输入的辅助判断，不代表原始素材、链路或合规性已通过人工核验。"

# Only recognize statements made entirely of generic sentiment/uncertainty.
# Any unrecognized concrete remainder is retained for model/human assessment.
VAGUE_ONLY_PHRASES = (
    "我说不上来哪里不对", "说不上来哪里不对", "没有具体想投诉的地方",
    "暂时想不起具体操作", "感觉怪怪的", "感觉不太好", "体验不太好",
    "不知道哪里有问题", "说不清哪里不对", "说不上具体原因", "感觉不太对",
    "感觉有点怪", "不太舒服", "有点怪", "体验差",
    "体验一般般", "体验不好", "说不清楚", "不怎么喜欢", "不太对劲",
    "感觉奇怪", "有点奇怪", "看着难受", "不舒服", "不喜欢", "怪怪的",
    "一般般", "有问题", "这个广告", "这条广告", "广告", "感觉", "体验",
    "但是", "不过", "只是", "就是", "暂时", "我", "但", "也", "的", "了",
)


def is_vague_only(text: str) -> bool:
    remainder = re.sub(r"[\s，。！？、；：,.!?;:\"'（）()…]+", "", text)
    if not remainder:
        return False
    for phrase in sorted(VAGUE_ONLY_PHRASES, key=len, reverse=True):
        remainder = remainder.replace(phrase, "")
    return not remainder


def request_information_recommendation() -> Recommendation:
    return Recommendation(
        category="review", action="补充具体操作、预期与实际结果，必要时提供脱敏素材后人工核查",
        rationale="现有信息不足以确定具体问题类别，不把候选猜测当作已发现问题。",
        priority="P2", expected_metric="补充信息后的可定位率", guardrail_metric="无证据问题标签误报率",
    )
