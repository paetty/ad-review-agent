"""Local feedback-to-handoff workflow. No messaging or delivery mutation tools."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import time
import uuid
from collections import Counter, defaultdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import BusinessReport
from .pii import detect_pii_text, detect_sensitive_columns
from .provider import ProviderError
from .schemas import AnalysisInput
from .service import _recommendation, analyze_item
from .engine import _risk
from .taxonomy import LABELS, LABEL_NAMES, RISK_ORDER

router = APIRouter(prefix="/api/business", tags=["business-workflow"])


class WindowKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ad_id: str = Field(min_length=1, max_length=100)
    creative_id: str = Field(min_length=1, max_length=100)
    media_scene: str = Field(default="其他", max_length=100)
    platform: Literal["generic", "vivo", "oppo"] = "generic"
    window_start: date
    window_end: date

    @model_validator(mode="after")
    def valid_window(self):
        if self.window_start > self.window_end:
            raise ValueError("window_start 不能晚于 window_end")
        return self

    def key(self):
        return (self.ad_id, self.creative_id, self.media_scene, self.platform, str(self.window_start), str(self.window_end))


class FeedbackRecord(WindowKey):
    feedback_id: str = Field(min_length=1, max_length=100)
    feedback: str = Field(min_length=1, max_length=4000)
    title: str = Field(default="模拟素材", min_length=1, max_length=200)
    ad_copy: str = Field(default="", max_length=4000)
    industry: str = Field(default="其他", max_length=100)
    material_format: Literal["图片", "图文", "视频", "其他"] = "其他"
    landing_type: Literal["Web", "Deeplink", "应用下载", "小程序", "快应用", "其他"] = "其他"

    @field_validator("material_format", mode="before")
    @classmethod
    def normalize_video(cls, value):
        return "视频" if value in {"横版视频", "竖版视频"} else value


class ExposureRecord(WindowKey):
    impressions: int = Field(ge=0, strict=True)
    coverage: Literal["complete", "sampled", "unknown"] = "sampled"


class ReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback: list[FeedbackRecord] = Field(min_length=1, max_length=200)
    exposures: list[ExposureRecord] = Field(default_factory=list, max_length=200)
    dataset_source: Literal["synthetic", "provided"] = "synthetic"

    @model_validator(mode="after")
    def unique_keys(self):
        ids = [x.feedback_id for x in self.feedback]
        if len(ids) != len(set(ids)):
            raise ValueError("feedback_id 重复，需先按稳定ID去重")
        keys = [x.key() for x in self.exposures]
        if len(keys) != len(set(keys)):
            raise ValueError("曝光表的广告/素材/场景/平台/时间窗键重复，不允许重复累加")
        material_versions = {}
        for x in self.feedback:
            version = (x.material_format, x.landing_type, x.ad_copy)
            if x.key() in material_versions and material_versions[x.key()] != version:
                raise ValueError("同一素材键出现不同形式、落地或文案，请使用独立creative_id区分版本")
            material_versions[x.key()] = version
            if detect_pii_text(" ".join([x.feedback, x.title, x.ad_copy, x.feedback_id, x.ad_id, x.creative_id])):
                raise ValueError("检测到疑似个人标识，请脱敏后再分析")
        return self


class ReportReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["accepted", "modified", "request_info"]
    reviewer: str = Field(default="local_reviewer", min_length=1, max_length=100)
    notes: str = Field(min_length=3, max_length=2000)
    evidence_confirmed: bool = False
    corrected_labels: list[str] | None = None
    corrected_risk: Literal["low", "medium", "high", "critical"] | None = None

    @model_validator(mode="after")
    def valid_correction(self):
        if self.corrected_labels is not None:
            if not self.corrected_labels or set(self.corrected_labels) - set(LABELS):
                raise ValueError("修正标签必须来自给定的13个标签")
            if "no_issue" in self.corrected_labels and len(self.corrected_labels) > 1:
                raise ValueError("no_issue 不能与问题标签共存")
        if self.decision == "modified" and self.corrected_labels is None and self.corrected_risk is None:
            raise ValueError("修改决定必须实际提供修正标签或风险")
        if self.decision != "modified" and (self.corrected_labels is not None or self.corrected_risk is not None):
            raise ValueError("修正内容仅能用于 modified 决定")
        if detect_pii_text(self.notes + " " + self.reviewer):
            raise ValueError("复核备注不得包含个人标识")
        return self


def get_db():
    with SessionLocal() as db:
        yield db


def media_plan(row: FeedbackRecord, labels: set[str]) -> dict:
    checks = []
    if row.material_format in {"图片", "图文"}:
        checks.append("核对原图、展示尺寸、文案可读性及活动有效期")
    if row.material_format == "视频":
        checks.append("核对关键帧、前三秒、音频和字幕；当前未自动执行视频分析")
    if row.landing_type in {"Deeplink", "应用下载", "小程序", "快应用"}:
        checks.append("核对跳转/下载告知、目标一致性和返回路径；需录屏或链路记录")
    visual = bool(labels & {"unclear_material", "misleading_claim", "stale_material", "vulgar_or_inappropriate_content", "weak_first_three_seconds"})
    link = bool(labels & {"forced_or_unexpected_jump", "return_path_friction", "malicious_or_suspicious_redirect", "potential_privacy_risk"})
    return {"material_format": row.material_format, "landing_type": row.landing_type, "checks": checks,
            "automatically_verified": False, "needs_evidence": visual or link,
            "boundary": "这是按媒体类型生成的核查清单；没有自动抓取网页、下载APP、播放视频或执行OCR。"}


def owners(labels: set[str]) -> list[str]:
    teams = []
    if labels & {"forced_or_unexpected_jump", "return_path_friction"}: teams.append("产品/客户端团队")
    if labels & {"malicious_or_suspicious_redirect", "potential_privacy_risk", "vulgar_or_inappropriate_content", "misleading_claim"}: teams.append("内容安全/合规团队")
    if labels & {"unclear_material", "stale_material", "weak_first_three_seconds", "repetitive_material"}: teams.append("素材运营团队")
    if labels & {"excessive_ad_frequency", "irrelevant_targeting"}: teams.append("投放策略团队")
    return teams or ["体验治理运营"]


def refresh_summary(report: dict) -> dict:
    cases = report["cases"]
    pending = sum(x["handoff_status"] in {"awaiting_review", "needs_information"} for x in cases)
    report["summary"] = {"feedback_rows": report["feedback_rows"], "cases": len(cases), "pending_review": pending,
        "draft_ready": sum(x["handoff_status"] == "draft_ready" for x in cases),
        "human_reviewed": sum(x["handoff_status"] == "human_reviewed" for x in cases),
        "handoff_ready": pending == 0, "dispatch_performed": False}
    report["workflow_status"] = "awaiting_review" if pending else "ready_for_handoff"
    return report


async def build_report(payload: ReportInput, db: Session) -> dict:
    started = time.perf_counter()
    grouped = defaultdict(list)
    for row in payload.feedback: grouped[row.key()].append(row)
    exposure_map = {x.key(): x for x in payload.exposures}
    cases = []
    for key, rows in grouped.items():
        counts = Counter()
        results = []
        for row in rows:
            output = await analyze_item(db, AnalysisInput(title=row.title, ad_copy=row.ad_copy, feedback=row.feedback,
                industry=row.industry, media_scene=row.media_scene, material_format=row.material_format,
                landing_type=row.landing_type, platform=row.platform))
            results.append({"feedback_id": row.feedback_id, "user_report": row.feedback,
                "evidence_status": "unverified_user_report", "analysis": output.model_dump()})
            counts.update({x.label for x in output.labels if x.label != "no_issue"})
        labels = set(counts)
        risk = max((x["analysis"]["overall_risk"] for x in results), key=RISK_ORDER.get)
        plans = [media_plan(row, {x["label"] for x in result["analysis"]["labels"]}) for row, result in zip(rows, results)]
        insufficient = any(x["analysis"]["assessment_status"] == "insufficient_evidence" for x in results)
        missing = []
        if insufficient: missing.append("反馈未指明可定位的问题，需补充操作、对象或结果")
        if any(x["needs_evidence"] for x in plans): missing.append("尚未完成对应素材或交互链路的证据核查")
        if labels & {"excessive_ad_frequency", "repetitive_material"}: missing.append("需用户级匿名曝光序列验证频次与素材重复，汇总曝光不能证明人均频次")
        exposure = exposure_map.get(key)
        rate = None
        reason = None
        if exposure is None: reason = "缺少相同广告/素材/场景/平台/时间窗的曝光分母"
        elif exposure.impressions == 0: reason = "曝光为0，不能计算每万次曝光反馈事件数"
        elif exposure.coverage != "complete": reason = "反馈未声明完整覆盖，抽样或未知覆盖不能推导总体负反馈率"
        else: rate = round(len(rows) / exposure.impressions * 10000, 4)
        review = any(x["analysis"]["requires_human_review"] for x in results) or bool(missing)
        citations = {x["chunk_id"]: x for r in results for x in r["analysis"]["citations"]}
        recommendations = {x["action"]: x for r in results for x in r["analysis"]["strategy_recommendations"]}
        first = rows[0]
        cases.append({"case_id": hashlib.sha256("|".join(key).encode()).hexdigest()[:16],
            "ad_id": first.ad_id, "creative_id": first.creative_id, "media_scene": first.media_scene,
            "platform": first.platform, "window_start": str(first.window_start), "window_end": str(first.window_end),
            "feedback_count": len(rows), "labels": [{"label": x, "name": LABEL_NAMES[x], "count": n, "feedback_share": round(n / len(rows), 4)} for x, n in counts.most_common()],
            "original_risk": risk, "effective_risk": risk,
            "effective_labels": sorted(labels or {"no_issue"}),
            "assessment_status": "insufficient_evidence" if insufficient else "issue_detected" if labels else "no_explicit_issue",
            "rate": {"impressions": exposure.impressions if exposure else None, "coverage": exposure.coverage if exposure else None,
                "feedback_events_per_10k_impressions": rate, "unavailable_reason": reason,
                "definition": "按唯一feedback_id统计事件数；不是独立用户投诉概率，也不是已核实问题率"},
            "media_checks": plans, "missing_information": missing, "suggested_owners": owners(labels),
            "observations": results, "citations": list(citations.values()), "recommendations": list(recommendations.values()),
            "handoff_status": "awaiting_review" if review else "draft_ready", "review_history": [],
            "conclusion_type": "问题线索与待验证建议，非确认根因或违规裁决"})
    report = {"report_id": str(uuid.uuid4()), "dataset_source": payload.dataset_source, "feedback_rows": len(payload.feedback),
        "cases": cases, "elapsed_ms_measured": round((time.perf_counter() - started) * 1000),
        "metric_boundary": "每万曝光指标按同维度完整覆盖记录计算；多标签占比之和可以超过100%。不跨素材累加曝光。",
        "permissions": {"export_local_report": True, "send_to_department": False, "change_delivery": False, "penalize_advertiser": False}}
    return refresh_summary(report)


def report_markdown(report: dict, final: bool) -> str:
    lines = ["# 广告反馈问题交接报告" if final else "# 广告反馈分析草稿", "",
        f"数据来源：{report['dataset_source']}；反馈 {report['feedback_rows']} 条；待复核 {report['summary']['pending_review']} 项。", "",
        "只导出供人工交接；没有自动发送。反馈不等于已核实事实，分析不等于因果或违规判定。", ""]
    for case in report["cases"]:
        lines += [f"## {case['ad_id']} / {case['creative_id']}",
            f"场景：{case['media_scene']}；时间窗：{case['window_start']} 至 {case['window_end']}；状态：{case['handoff_status']}",
            f"风险：{case['effective_risk']}；标签：{'、'.join(LABEL_NAMES[x] for x in case['effective_labels'])}",
            f"建议责任团队：{'、'.join(case['suggested_owners'])}",
            f"每万曝光反馈事件数：{case['rate']['feedback_events_per_10k_impressions'] if case['rate']['feedback_events_per_10k_impressions'] is not None else '不可计算：' + str(case['rate']['unavailable_reason'])}", ""]
        lines += ["用户报告：" + x["user_report"] for x in case["observations"]]
        lines += [("原始待核查事项（见人工记录）：" if case["handoff_status"] == "human_reviewed" else "待补信息：") + x for x in case["missing_information"]]
        lines += ["建议动作：" + x["action"] + "；目标：" + x["expected_metric"] + "；护栏：" + x["guardrail_metric"] for x in case["recommendations"]]
        lines += ["规则参考：" + x["document_title"] + "（" + x["source_type"] + "） " + (x.get("source_url") or "本项目自编规范") for x in case["citations"]]
        lines += [f"人工记录：{x['reviewer']} / {x['decision']} / {x['notes']}" for x in case["review_history"]]
        lines += [""]
    return "\n".join(lines)


@router.post("/reports")
async def create_report(payload: ReportInput, db: Session = Depends(get_db)):
    try:
        report = await build_report(payload, db)
    except ProviderError as exc:
        raise HTTPException(503, detail={"code": exc.code, "message": str(exc)}) from exc
    row = BusinessReport(id=report["report_id"], report_json=report)
    db.add(row)
    db.commit()
    return report


@router.get("/reports/{report_id}")
def read_report(report_id: str, db: Session = Depends(get_db)):
    row = db.get(BusinessReport, report_id)
    if not row: raise HTTPException(404, "报告不存在")
    return row.report_json


@router.post("/reports/{report_id}/cases/{case_id}/review")
def review_case(report_id: str, case_id: str, payload: ReportReview, db: Session = Depends(get_db)):
    row = db.get(BusinessReport, report_id)
    if not row: raise HTTPException(404, "报告不存在")
    report = copy.deepcopy(row.report_json)
    case = next((x for x in report["cases"] if x["case_id"] == case_id), None)
    if case is None: raise HTTPException(404, "问题单不存在")
    if payload.decision != "request_info" and not payload.evidence_confirmed:
        raise HTTPException(400, "需明确确认已完成所需人工核验；否则请选择补充信息")
    case["review_history"].append(payload.model_dump())
    if payload.decision == "request_info": case["handoff_status"] = "needs_information"
    else:
        case["handoff_status"] = "human_reviewed"
        if payload.corrected_labels is not None:
            case["effective_labels"] = payload.corrected_labels
            case["suggested_owners"] = owners(set(payload.corrected_labels))
            case["recommendations"] = [_recommendation(x).model_dump() for x in payload.corrected_labels]
            case["effective_risk"] = _risk(set(payload.corrected_labels))
        if payload.corrected_risk is not None and RISK_ORDER[payload.corrected_risk] < RISK_ORDER[_risk(set(case["effective_labels"]))]:
            raise HTTPException(422, "风险与问题标签不一致；如核验已排除问题，请同时修正标签")
        if payload.corrected_risk is not None: case["effective_risk"] = payload.corrected_risk
    row.report_json = refresh_summary(report)
    db.commit()
    return row.report_json


@router.get("/reports/{report_id}/export")
def export_report(report_id: str, final: bool = False, db: Session = Depends(get_db)):
    row = db.get(BusinessReport, report_id)
    if not row: raise HTTPException(404, "报告不存在")
    if final and not row.report_json["summary"]["handoff_ready"]:
        raise HTTPException(409, "仍有待复核或待补信息条目，只允许导出草稿")
    return Response(report_markdown(row.report_json, final), media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="feedback-report-{report_id}.md"'})


@router.get("/demo-input")
def demo_input():
    base = {"media_scene": "天气", "platform": "generic", "window_start": "2026-10-01", "window_end": "2026-10-07"}
    examples = [
        ("AD-A", "CR-A", "画面模糊，小字看不清", "图片", "Web"),
        ("AD-A", "CR-A", "文字太小", "图片", "Web"),
        ("AD-B", "CR-B", "广告太多，一直弹出", "视频", "应用下载"),
        ("AD-C", "CR-C", "感觉怪怪的，体验不太好", "图文", "小程序"),
        ("AD-D", "CR-D", "页面打开和返回都正常", "其他", "Web"),
        ("AD-E", "CR-E", "点击后自动跳转，返回很多次还是回不去", "图片", "Deeplink"),
    ]
    feedback = [{**base, "platform": "oppo" if a == "AD-A" else "vivo" if a == "AD-E" else "generic", "feedback_id": f"F{i:03d}", "ad_id": a, "creative_id": c,
        "feedback": f, "title": "合成素材 " + c, "material_format": m, "landing_type": l} for i, (a,c,f,m,l) in enumerate(examples, 1)]
    exposures = [{**base, "platform": "oppo" if a == "AD-A" else "vivo" if a == "AD-E" else "generic", "ad_id": a, "creative_id": c, "impressions": n, "coverage": coverage}
        for a,c,n,coverage in [("AD-A","CR-A",10000,"complete"),("AD-B","CR-B",1000,"sampled"),("AD-D","CR-D",20000,"complete"),("AD-E","CR-E",0,"complete")]]
    return {"dataset_source": "synthetic", "feedback": feedback, "exposures": exposures}


@router.get("/template")
def csv_template(kind: Literal["feedback", "exposures"] = "feedback"):
    rows = demo_input()[kind]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return Response("\ufeff" + stream.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="synthetic-{kind}.csv"'})


async def read_csv(file: UploadFile) -> list[dict]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "请上传UTF-8 CSV；Excel可另存为该格式")
    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024: raise HTTPException(400, "单个CSV最大2MB")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)): raise ValueError("CSV列名重复")
        if detect_sensitive_columns(fields): raise ValueError("CSV包含不允许的敏感字段")
        rows = list(reader)
        if len(rows) > 200: raise ValueError("单表最多200行")
        if any(None in row or None in row.values() for row in rows): raise ValueError("CSV行列数不一致")
        return rows
    except (UnicodeDecodeError, ValueError, csv.Error) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/reports/upload")
async def upload_report(feedback_file: UploadFile = File(...), exposure_file: UploadFile | None = File(None),
        dataset_source: Literal["synthetic", "provided"] = Form("synthetic"), db: Session = Depends(get_db)):
    feedback = await read_csv(feedback_file)
    exposures = await read_csv(exposure_file) if exposure_file else []
    for row in exposures:
        if not str(row.get("impressions", "")).isdigit(): raise HTTPException(400, "impressions必须为非负整数，不能留空或使用小数")
        row["impressions"] = int(row["impressions"])
    try:
        payload = ReportInput.model_validate({"feedback": feedback, "exposures": exposures, "dataset_source": dataset_source})
    except ValidationError as exc:
        raise HTTPException(422, "表格校验失败：" + str(exc)) from exc
    return await create_report(payload, db)
