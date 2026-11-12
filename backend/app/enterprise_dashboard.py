"""Shared workspace statistics and separately curated industry references."""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .enterprise_settings import ENABLED, ROOT
from .models import Analysis, HumanReview

router = APIRouter(prefix="/api/enterprise", tags=["enterprise-workspace"])
BUSINESS_TZ = timezone(timedelta(hours=8))


def pending_review():
    completed = select(HumanReview.id).where(
        HumanReview.analysis_id == Analysis.id,
        HumanReview.decision.in_(("accepted", "modified")),
    )
    return Analysis.requires_human_review.is_(True) & ~completed.exists()


def risk_trends(db: Session) -> dict:
    today = datetime.now(BUSINESS_TZ).date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    day = func.date(Analysis.created_at, "+8 hours")
    high = Analysis.overall_risk.in_(("high", "critical"))
    daily = {
        key: (count, high_count) for key, count, high_count in db.execute(
            select(day, func.count(Analysis.id), func.count(Analysis.id).filter(high))
            .where(day.between(days[0], days[-1])).group_by(day)
        )
    }
    return {
        "source": "synthetic_demo" if ENABLED else "local",
        "timezone": "UTC+8",
        "analysis_count": sum(count for count, _ in daily.values()),
        "high_risk_count": sum(count for _, count in daily.values()),
        "pending_review_count": db.scalar(select(func.count(Analysis.id)).where(pending_review())),
        "trend": [
            {"date": key, "analyses": daily.get(key, (0, 0))[0], "high_risk": daily.get(key, (0, 0))[1]}
            for key in days
        ],
        "feedback_rate": None,
    }

@router.get("/dashboard")
def dashboard():
    if not ENABLED:
        raise HTTPException(404)
    with SessionLocal() as db:
        return risk_trends(db)


@router.get("/policy-watch")
def policy_watch():
    return json.loads((ROOT / "data" / "enterprise" / "policy-watch.json").read_text(encoding="utf-8"))
