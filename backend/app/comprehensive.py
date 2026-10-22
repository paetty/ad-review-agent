from __future__ import annotations

import base64
import struct
from collections import Counter, defaultdict
from typing import Iterable

from .schemas import AnalysisOutput
from .taxonomy import LABEL_NAMES, RISK_ORDER


COMPREHENSIVE_REQUIRED = ["ad_id", "feedback"]
COMPREHENSIVE_OPTIONAL = [
    "title", "ad_copy", "industry", "media_scene", "landing_type",
    "material_format", "first_three_seconds", "image_filename",
]


def image_dimensions(content: bytes, mime: str) -> tuple[int, int] | None:
    """Read dimensions without decoding or retaining the image."""
    if mime == "image/png" and len(content) >= 24:
        return struct.unpack(">II", content[16:24])
    if mime == "image/jpeg":
        offset = 2
        while offset + 9 <= len(content):
            if content[offset] != 0xFF:
                offset += 1
                continue
            marker = content[offset + 1]
            offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            if offset + 2 > len(content):
                break
            length = int.from_bytes(content[offset:offset + 2], "big")
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and offset + 7 <= len(content):
                return int.from_bytes(content[offset + 5:offset + 7], "big"), int.from_bytes(content[offset + 3:offset + 5], "big")
            if length < 2:
                break
            offset += length
    if mime == "image/webp" and len(content) >= 30:
        kind = content[12:16]
        if kind == b"VP8X":
            return 1 + int.from_bytes(content[24:27], "little"), 1 + int.from_bytes(content[27:30], "little")
        if kind == b"VP8L" and content[20] == 0x2F:
            bits = int.from_bytes(content[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def inspect_image(filename: str, content: bytes, mime: str, semantic_review: bool = False) -> dict:
    dimensions = image_dimensions(content, mime)
    findings: list[str] = []
    if dimensions:
        width, height = dimensions
        if min(width, height) < 400:
            findings.append("图片短边低于 400px，存在清晰度风险")
        elif min(width, height) < 720:
            findings.append("图片短边低于 720px，建议人工确认文字可读性")
    else:
        width = height = None
        findings.append("未能读取图片尺寸，建议人工检查文件完整性")
    return {
        "filename": filename,
        "mime": mime,
        "size_bytes": len(content),
        "width": width,
        "height": height,
        "basic_findings": findings,
        "semantic_review": "provider" if semantic_review else "not_performed",
    }


def to_data_url(content: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def aggregate_comprehensive(rows: Iterable[dict], image_catalog: dict[str, dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["ad_id"]].append(row)

    ads: list[dict] = []
    total_label_counts: Counter[str] = Counter()
    affected_ads: Counter[str] = Counter()
    risk_distribution: Counter[str] = Counter()
    image_names_used: set[str] = set()

    for ad_id, items in grouped.items():
        label_counts: Counter[str] = Counter()
        evidence: list[str] = []
        recommendations: list[str] = []
        missing_images: set[str] = set()
        ad_images: dict[str, dict] = {}
        risk = "low"
        requires_review = False
        successful = 0

        for item in items:
            result: AnalysisOutput | None = item.get("result")
            filename = item.get("image_filename") or ""
            if filename:
                if filename in image_catalog:
                    ad_images[filename] = image_catalog[filename]
                    image_names_used.add(filename)
                else:
                    missing_images.add(filename)
                    requires_review = True
            if not result:
                requires_review = True
                continue
            successful += 1
            if RISK_ORDER[result.overall_risk] > RISK_ORDER[risk]:
                risk = result.overall_risk
            requires_review = requires_review or result.requires_human_review
            for label in result.labels:
                if label.label != "no_issue":
                    label_counts[label.label] += 1
            for ev in result.evidence:
                if ev.source in {"input", "image"} and ev.quote not in evidence:
                    evidence.append(ev.quote)
            for rec in result.strategy_recommendations:
                if rec.action not in recommendations:
                    recommendations.append(rec.action)

        for meta in ad_images.values():
            if meta["basic_findings"]:
                label_counts["unclear_material"] += 1
                requires_review = True
                if RISK_ORDER[risk] < RISK_ORDER["medium"]:
                    risk = "medium"

        total_label_counts.update(label_counts)
        for label in label_counts:
            affected_ads[label] += 1
        risk_distribution[risk] += 1
        dominant = [
            {"label": label, "name": LABEL_NAMES.get(label, label), "count": count,
             "share": round(count / max(1, len(items)), 3)}
            for label, count in label_counts.most_common(5)
        ]
        reason_text = "、".join(x["name"] for x in dominant[:3]) if dominant else "暂未发现明确问题"
        if missing_images:
            reason_text += f"；另有 {len(missing_images)} 张素材未匹配"
        ads.append({
            "ad_id": ad_id,
            "feedback_count": len(items),
            "analyzed_count": successful,
            "overall_risk": risk,
            "requires_human_review": requires_review,
            "dominant_causes": dominant,
            "summary": f"综合 {len(items)} 条反馈，主要问题为：{reason_text}。",
            "evidence_samples": evidence[:5],
            "recommendations": recommendations[:5],
            "images": list(ad_images.values()),
            "missing_images": sorted(missing_images),
        })

    ads.sort(key=lambda x: (-RISK_ORDER[x["overall_risk"]], -x["feedback_count"], x["ad_id"]))
    total_feedback = sum(len(x) for x in grouped.values())
    causes = [
        {"label": label, "name": LABEL_NAMES.get(label, label), "occurrences": count,
         "affected_ads": affected_ads[label], "feedback_share": round(count / max(1, total_feedback), 3)}
        for label, count in total_label_counts.most_common()
    ]
    return {
        "summary": {
            "total_rows": total_feedback,
            "total_ads": len(ads),
            "uploaded_images": len(image_catalog),
            "matched_images": len(image_names_used),
            "review_required_ads": sum(x["requires_human_review"] for x in ads),
            "risk_distribution": {k: risk_distribution[k] for k in ["low", "medium", "high", "critical"]},
        },
        "cause_distribution": causes,
        "ads": ads,
        "limitations": [
            "Demo 模式仅检查图片格式、大小和分辨率，不识别图片语义、OCR 文字或人物属性。",
            "图片语义结论必须由已启用的视觉模型或人工审核给出。",
            "结果用于问题定位和审核辅助，不自动下线广告或修改投放策略。",
        ],
    }
