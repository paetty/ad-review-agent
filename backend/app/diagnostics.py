"""On-demand checks on daily advertising metrics; no delivery write access."""
from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Literal

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .business import read_csv
from .database import SessionLocal
from .diagnostic_prompts import PROMPTS
from .diagnostic_requests import RequestPlan, plan_request
from .pii import detect_pii_text
from .provider import OpenAICompatibleProvider, ProviderError
from .schemas import AnalysisInput
from .service import analyze_item
from .taxonomy import LABEL_NAMES, RISK_ORDER

router = APIRouter(prefix="/api/diagnostics", tags=["ad-diagnostics"])


class DailyRow(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    date: date
    ad_id: str = Field(min_length=1, max_length=100)
    creative_id: str = Field(default="", max_length=100)
    industry: str = Field(default="", max_length=100)
    impressions: int = Field(ge=0, le=10**12)
    revenue: float | None = Field(default=None, ge=0, le=10**12)
    spend: float | None = Field(default=None, ge=0, le=10**12)
    ecpm: float | None = Field(default=None, ge=0, le=10**9)
    paying_users: int | None = Field(default=None, ge=0, le=10**12)
    eligible_users: int | None = Field(default=None, ge=0, le=10**12)
    negative_feedback: int | None = Field(default=None, ge=0, le=10**12)
    creative_text: str = Field(default="", max_length=4000)
    feedback_text: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_counts(self):
        if self.paying_users is not None and self.eligible_users is not None and self.paying_users > self.eligible_users:
            raise ValueError("付费人数超过对应的统计人数")
        return self

    @property
    def key(self) -> tuple[str, str]:
        return self.ad_id, self.creative_id


OPTIONAL_NUMBERS = {"revenue", "spend", "ecpm", "paying_users", "eligible_users", "negative_feedback"}
SAMPLE_LAUNCH = date(2026, 11, 7)
SAMPLE_DATES = {
    "launch_date": str(SAMPLE_LAUNCH), "before_start": "2026-11-01", "before_end": "2026-11-03",
    "after_start": "2026-11-08", "after_end": "2026-11-10",
}


def sample_rows() -> list[DailyRow]:
    rows = []
    for offset in (1, 2, 3, 8, 9, 10):
        after = offset > 7
        for ad, creative, impressions, revenue, spend, events, text in [
            ("DEMO-A", "CR-A", 26000, 240 if after else 320, 220, 70 if after else 300,
             "浏览器提示落地页是恶意网站，广告自动跳转。"),
            ("DEMO-B", "CR-B", 20000, 210 if after else 250, 190, 280 if after else 310, ""),
            ("DEMO-C", "CR-C", 6000, 65 if after else 70, 55, 6, "点击和返回正常。"),
        ]:
            rows.append(DailyRow(
                date=date(2026, 11, offset), ad_id=ad, creative_id=creative, impressions=impressions,
                revenue=revenue, spend=spend, negative_feedback=events, eligible_users=1000,
                paying_users=34 if after else 32, creative_text="合成演示素材", feedback_text=text,
                industry="游戏" if ad == "DEMO-C" else "电商",
            ))
    return rows


async def load_rows(file: UploadFile | None) -> list[DailyRow]:
    if file is None:
        return sample_rows()
    raw_rows = await read_csv(file)
    if not raw_rows:
        raise HTTPException(422, "表格没有数据行")
    rows = []
    seen = set()
    creative_scope: dict[str, bool] = {}
    industry_scope: dict[tuple[str, str], str] = {}
    for line, raw in enumerate(raw_rows, 2):
        clean = {key: value.strip() for key, value in raw.items()}
        for key in OPTIONAL_NUMBERS:
            if clean.get(key) == "":
                clean[key] = None
        try:
            row = DailyRow.model_validate(clean)
            if row.date.isoformat() != clean["date"]:
                raise HTTPException(422, f"第 {line} 行日期请使用 YYYY-MM-DD")
        except ValidationError as exc:
            field = ".".join(map(str, exc.errors()[0]["loc"])) or "统计口径"
            raise HTTPException(422, f"第 {line} 行的 {field} 无效，请按模板检查日期、列名及数值") from exc
        if detect_pii_text(" ".join([row.ad_id, row.creative_id, row.industry, row.creative_text, row.feedback_text])):
            raise HTTPException(422, f"第 {line} 行可能包含个人标识，请先脱敏")
        key = (row.date, *row.key)
        if key in seen:
            raise HTTPException(422, f"第 {line} 行的日期、广告 ID 和素材 ID 重复，请先按相同口径去重")
        if row.ad_id in creative_scope and creative_scope[row.ad_id] != bool(row.creative_id):
            raise HTTPException(422, f"第 {line} 行混用了广告汇总与素材明细，可能重复计数")
        creative_scope[row.ad_id] = bool(row.creative_id)
        if row.key in industry_scope and industry_scope[row.key] != row.industry:
            raise HTTPException(422, f"第 {line} 行的素材行业与前面记录不一致")
        industry_scope[row.key] = row.industry
        seen.add(key)
        rows.append(row)
    return rows


def sum_complete(rows: list[DailyRow], field: str) -> int | float | None:
    values = [getattr(row, field) for row in rows]
    return sum(values) if values and all(value is not None for value in values) else None


def ratio(numerator: int | float | None, denominator: int | float | None, scale: int = 1) -> float | None:
    return numerator / denominator * scale if numerator is not None and denominator else None


def metrics(rows: list[DailyRow]) -> dict:
    impressions = sum(row.impressions for row in rows)
    days = len({row.date for row in rows})
    revenue, spend = (sum_complete(rows, field) for field in ("revenue", "spend"))
    feedback, payers, eligible = (sum_complete(rows, field) for field in ("negative_feedback", "paying_users", "eligible_users"))
    ecpm = ratio(revenue, impressions, 1000)
    if revenue is None and rows and all(row.ecpm is not None for row in rows):
        ecpm = ratio(sum(row.ecpm * row.impressions for row in rows), impressions)
    return {
        "days": days, "impressions": impressions, "revenue": revenue, "spend": spend,
        "negative_feedback": feedback, "paying_users": payers, "eligible_users": eligible,
        "daily_impressions": ratio(impressions, days), "daily_revenue": ratio(revenue, days),
        "daily_spend": ratio(spend, days), "ecpm": ecpm,
        "feedback_rate": ratio(feedback, impressions, 100), "payer_rate": ratio(payers, eligible, 100),
    }


class Advice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1, max_length=400)
    evidence_ids: list[str] = Field(min_length=1, max_length=5)


class ModelSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=600)
    recommendations: list[Advice] = Field(min_length=1, max_length=3)


async def summarize(kind: str, report: dict, evidence: dict, use_model: bool, question: str = "") -> dict:
    version, prompt = PROMPTS[kind]
    report.update(prompt_version=version, mode="rules", model_summary=None)
    if not use_model:
        return report
    provider = OpenAICompatibleProvider()
    if not provider.configured:
        report["model_notice"] = "模型配置不完整，本次保留程序计算和规则建议。"
        return report
    # Only server-generated metrics and enum labels cross the provider boundary.
    context = dict(list(evidence.items())[:20])
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(
        {"conclusion": report["status"], "request": question, "evidence": context}, ensure_ascii=False, allow_nan=False,
    )}]
    try:
        result = await provider.generate(messages, ModelSummary.model_json_schema())
        summary = ModelSummary.model_validate(result.data)
        if any(set(item.evidence_ids) - context.keys() for item in summary.recommendations):
            raise ValueError("Unknown evidence ID")
        report.update(mode="provider", model_summary=summary.model_dump(), model=result.model)
    except (ProviderError, httpx.RequestError, ValueError):
        report["model_notice"] = "模型摘要不可用或引用未通过校验，已保留程序计算和规则建议。"
    return report


def meets_exposure(impressions: int, minimum: int | None, inclusive: bool) -> bool:
    return minimum is None or impressions > minimum or (inclusive and impressions == minimum)


def history_windows(rows: list[DailyRow], plan: RequestPlan) -> tuple[list[DailyRow], list[DailyRow]]:
    end = max(row.date.toordinal() for row in rows)
    start = max(1, end - (plan.current_days or (1 if plan.compare_history else end)) + 1)
    current = [row for row in rows if row.date.toordinal() >= start]
    history = [row for row in rows if max(1, start - (plan.history_days or start)) <= row.date.toordinal() < start]
    return current, history


def compare_history(current: dict, previous_rows: list[DailyRow], plan: RequestPlan) -> dict:
    previous = metrics(previous_rows)
    baseline = previous["feedback_rate"]
    observed = current["feedback_rate"]
    if (plan.history_days and previous["days"] < plan.history_days) or (plan.current_days and current["days"] < plan.current_days):
        baseline = None
    return {
        "start": str(min(row.date for row in previous_rows)) if previous_rows else None,
        "end": str(max(row.date for row in previous_rows)) if previous_rows else None,
        "days": previous["days"], "impressions": previous["impressions"],
        "negative_feedback": previous["negative_feedback"], "rate": baseline,
        "delta": None if baseline is None or observed is None else observed - baseline,
    }


@router.get("/template")
def template():
    rows = [row.model_dump(mode="json") for row in sample_rows()]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(DailyRow.model_fields))
    writer.writeheader()
    writer.writerows(rows)
    return Response("\ufeff" + stream.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="ad-diagnostics-synthetic.csv"'})


@router.post("/monitor")
async def monitor(
    file: UploadFile | None = File(None),
    min_impressions: int = Form(100_000, ge=0, le=10**14),
    feedback_threshold: float = Form(1, gt=0, le=100),
    use_model: bool = Form(False),
    analysis_request: str = Form("", max_length=600),
):
    rows = await load_rows(file)
    question = analysis_request.strip()
    plan, planning_mode = await plan_request(question, sorted({row.industry for row in rows if row.industry}), "monitor") if question else (RequestPlan(), "rules")
    scoped = [row for row in rows if not plan.industry or row.industry == plan.industry]
    current, history = history_windows(scoped, plan) if plan.compare_history or plan.current_days else (scoped, [])
    minimum = plan.min_impressions if question else min_impressions
    feedback_threshold = plan.feedback_threshold or feedback_threshold
    groups = defaultdict(list)
    previous_groups = defaultdict(list)
    for row in current:
        groups[row.key].append(row)
    for row in history:
        previous_groups[row.key].append(row)
    items = []
    skipped = 0
    with SessionLocal() as db:
        for (ad_id, creative_id), group in groups.items():
            totals = metrics(group)
            if not meets_exposure(totals["impressions"], minimum, plan.inclusive):
                skipped += 1
                continue
            rate = totals["feedback_rate"]
            abnormal = rate is not None and rate >= feedback_threshold and totals["negative_feedback"] >= 3
            analyses = []
            # Identical copy/feedback is evaluated once per material.
            for copy, feedback in dict.fromkeys((row.creative_text, row.feedback_text) for row in group):
                if copy or feedback:
                    analyses.append(await analyze_item(db, AnalysisInput(
                        title="素材文字核查", ad_copy=copy, feedback=feedback, industry="其他",
                        media_scene="其他", landing_type="其他", material_format="其他",
                    ), mode_override="rules"))
            highest = max(analyses, key=lambda value: RISK_ORDER[value.overall_risk], default=None)
            high = highest and highest.overall_risk in {"high", "critical"}
            findings = []
            if high:
                findings.append("文字触发高风险核查")
            if abnormal:
                findings.append("反馈事件率达到监测阈值")
            baseline = compare_history(totals, previous_groups[(ad_id, creative_id)], plan) if plan.compare_history else None
            higher = baseline is not None and baseline["delta"] is not None and baseline["delta"] > 0
            if higher:
                findings.append("反馈事件率高于同一素材的历史基线")
            labels = [item.label for item in highest.labels if item.label != "no_issue"] if highest else []
            items.append({
                "ad_id": ad_id, "creative_id": creative_id, "industry": group[0].industry,
                "metrics": totals, "flagged": bool(findings), "history": baseline,
                "risk": highest.overall_risk if high else None, "findings": findings,
                "labels": labels, "label_names": [LABEL_NAMES.get(label, label) for label in labels],
                "quotes": [entry.quote for entry in highest.evidence if entry.source == "input"][:3] if high else [],
                "citations": [entry.model_dump() for entry in highest.citations[:2]] if high else [],
                "recommendation": "优先人工复现跳转或查看素材，并核对原始反馈。" if high else
                    "抽查反馈原文，核对反馈归因、去重口径和素材版本。" if abnormal or higher else
                    "补齐同素材的历史反馈和曝光后再比较。" if baseline and baseline["delta"] is None else
                    "补齐反馈或素材信息后复核。" if not analyses or rate is None else "继续按同口径监测。",
            })
    items.sort(key=lambda item: (item["flagged"], RISK_ORDER.get(item["risk"], 0), item["metrics"]["impressions"]), reverse=True)
    evidence = {}
    for index, item in enumerate(items, 1):
        key = item["evidence_id"] = f"A{index:03d}"
        evidence[key] = {name: item[name] for name in ("metrics", "flagged", "risk", "findings", "labels", "history")}
    matched_keys = {(item["ad_id"], item["creative_id"]) for item in items}
    history_summary = None
    if plan.compare_history and matched_keys:
        totals = metrics([row for row in current if row.key in matched_keys])
        baseline = compare_history(totals, [row for row in history if row.key in matched_keys], plan)
        if any(item["history"]["delta"] is None for item in items):
            baseline["rate"] = baseline["delta"] = None
        history_summary = {"current_rate": totals["feedback_rate"], **baseline}
        evidence = {"D01": history_summary, **evidence}
    report = {
        "source": "provided" if file else "synthetic", "rows": len(rows), "items": items,
        "skipped": skipped, "flagged": sum(item["flagged"] for item in items),
        "start": str(min(row.date for row in current)), "end": str(max(row.date for row in current)),
        "min_impressions": minimum, "inclusive": plan.inclusive, "industry": plan.industry,
        "feedback_threshold": feedback_threshold, "history_summary": history_summary,
        "compare_history": plan.compare_history, "planning_mode": planning_mode,
        "status": "存在待核查线索" if any(item["flagged"] for item in items) else "暂无命中核查条件的记录",
    }
    return await summarize("monitor", report, evidence, (bool(question) or use_model) and bool(evidence), question)


COMPARISONS = [
    ("daily_impressions", "日均曝光量", "count"), ("daily_revenue", "日均收入", "money"),
    ("daily_spend", "日均消耗", "money"), ("ecpm", "eCPM", "money"),
    ("payer_rate", "付款人率", "percent"), ("feedback_rate", "反馈事件率", "percent"),
]


@router.post("/strategy")
async def strategy(
    launch_date: date = Form(...),
    before_start: date = Form(...), before_end: date = Form(...),
    after_start: date = Form(...), after_end: date = Form(...),
    target_drop: float = Form(10, gt=0, le=100),
    guardrail_drop: float = Form(10, gt=0, le=100),
    min_period_impressions: int = Form(10_000, ge=1, le=10**14),
    file: UploadFile | None = File(None),
    use_model: bool = Form(False),
    analysis_request: str = Form("", max_length=600),
):
    if not before_start <= before_end < launch_date <= after_start <= after_end:
        raise HTTPException(422, "上线前窗口应早于上线日期，上线后窗口应从上线当天或之后开始，两个窗口不能重叠")
    rows = await load_rows(file)
    question = analysis_request.strip()
    plan, planning_mode = await plan_request(question, sorted({row.industry for row in rows if row.industry}), "strategy") if question else (RequestPlan(), "rules")
    target_drop = plan.target_drop or target_drop
    guardrail_drop = plan.guardrail_drop or guardrail_drop
    min_period_impressions = plan.min_period_impressions or min_period_impressions
    scoped = [row for row in rows if not plan.industry or row.industry == plan.industry]
    exposure = defaultdict(int)
    for row in scoped:
        if before_start <= row.date <= before_end or after_start <= row.date <= after_end:
            exposure[row.key] += row.impressions
    eligible = {key for key, count in exposure.items() if meets_exposure(count, plan.min_impressions, plan.inclusive)}
    before = [row for row in scoped if row.key in eligible and before_start <= row.date <= before_end]
    after = [row for row in scoped if row.key in eligible and after_start <= row.date <= after_end]
    left, right = metrics(before), metrics(after)
    left_days, right_days = (before_end - before_start).days + 1, (after_end - after_start).days + 1
    expected = [left_days, right_days]
    before_ids, after_ids = {row.key for row in before}, {row.key for row in after}
    notes = []
    if left["days"] != left_days or right["days"] != right_days:
        notes.append("至少一个周期缺少日期，请核对未出数、停投与漏传的区别。")
    if min(left["days"], right["days"]) < 3:
        notes.append("每段至少需要 3 个有数据的自然日。")
    if min(left["impressions"], right["impressions"]) < min_period_impressions:
        notes.append("至少一个周期未达到最低曝光门槛。")
    if before_ids != after_ids:
        notes.append("前后广告或素材集合不同，请先用相同范围复算。")
    elif len(before) != len(before_ids) * left_days or len(after) != len(after_ids) * right_days:
        notes.append("有素材缺少单日记录。停投日请填零，未知数据请先补齐。")
    comparable = not notes
    comparisons = []
    for index, (field, title, unit) in enumerate(COMPARISONS, 1):
        a, b = left[field], right[field]
        delta = None if a is None or b is None else b - a
        relative = ratio(delta, a, 100)
        comparisons.append({"evidence_id": f"M{index:02d}", "metric": field, "title": title,
                            "unit": unit, "before": a, "after": b, "delta": delta, "relative": relative})
    indexed = {item["metric"]: item for item in comparisons}
    guardrails = [
        item for item in comparisons if item["metric"] in {"daily_revenue", "ecpm", "payer_rate"}
        and item["relative"] is not None and item["relative"] <= -guardrail_drop
    ]
    target = indexed["feedback_rate"]
    target_met = target["relative"] is not None and target["relative"] <= -target_drop
    core_guards = [indexed[field] for field in ("daily_revenue", "ecpm")]
    required_missing = target["relative"] is None or any(item["relative"] is None for item in core_guards)
    if required_missing:
        notes.append("反馈事件率、日均收入或 eCPM 缺少数据或前期为零，部分相对变化无法计算。")
    if not comparable:
        status, action = "数据不足，暂不判断", "补齐缺失日期和曝光，核对前后范围后重算。"
    elif guardrails:
        status, action = "触发护栏，人工评估回滚", "优先核对数据、同期变动和影响范围，暂停扩大范围，由负责人评估回滚。"
    elif required_missing:
        status, action = "数据不足，暂不判断", "补齐目标指标和核心护栏的分母或收入数据。"
    elif target_met:
        status, action = "观察到目标改善", "在当前范围继续观察，使用对照实验验证是否由策略带来。"
    else:
        status, action = "未观察到达到目标的改善", "核对策略覆盖和样本构成，继续观察或设计有对照的验证。"
    report = {
        "source": "provided" if file else "synthetic", "rows": len(rows),
        "excluded_rows": len(rows) - len(before) - len(after), "status": status, "recommendation": action,
        "dates": {"launch_date": str(launch_date), "before_start": str(before_start), "before_end": str(before_end),
                  "after_start": str(after_start), "after_end": str(after_end)},
        "before": left, "after": right, "expected_days": expected, "common_materials": len(before_ids & after_ids),
        "comparisons": comparisons, "guardrails": [item["evidence_id"] for item in guardrails],
        "target_drop": target_drop, "guardrail_drop": guardrail_drop, "notes": notes,
        "industry": plan.industry, "min_impressions": plan.min_impressions, "inclusive": plan.inclusive,
        "planning_mode": planning_mode,
        "target_met": target_met, "comparable": comparable,
    }
    evidence = {item["evidence_id"]: item for item in comparisons}
    evidence["D01"] = {"observed_days": [left["days"], right["days"]], "expected_days": expected,
                       "common_materials": report["common_materials"], "comparable": comparable,
                       "target_drop": target_drop, "guardrail_drop": guardrail_drop, "guardrails": report["guardrails"]}
    return await summarize("strategy", report, evidence, bool(question) or use_model, question)


@router.get("/sample-periods")
def sample_periods():
    return SAMPLE_DATES
