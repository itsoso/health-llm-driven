"""LLM 用量/成本查询 API."""
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.llm_usage import LlmUsageLog
from app.api.deps import get_current_user_required
from app.models.user import User

router = APIRouter(prefix="/llm-usage", tags=["llm-usage"])


@router.get("/summary", summary="LLM 用量/成本聚合 (默认最近 7 天)")
def usage_summary(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 总览
    overall = db.query(
        func.count(LlmUsageLog.id).label("calls"),
        func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).label("tokens"),
        func.coalesce(func.sum(LlmUsageLog.cost_usd), 0.0).label("cost_usd"),
        func.coalesce(func.avg(LlmUsageLog.latency_ms), 0).label("avg_latency_ms"),
    ).filter(LlmUsageLog.created_at >= since).one()

    # 按 caller 分组 — 看哪个业务最贵
    by_caller_rows = db.query(
        LlmUsageLog.caller,
        func.count(LlmUsageLog.id).label("calls"),
        func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).label("tokens"),
        func.coalesce(func.sum(LlmUsageLog.cost_usd), 0.0).label("cost_usd"),
    ).filter(LlmUsageLog.created_at >= since).group_by(LlmUsageLog.caller).order_by(
        func.sum(LlmUsageLog.cost_usd).desc()
    ).limit(20).all()

    # 按 model 分组
    by_model_rows = db.query(
        LlmUsageLog.model,
        func.count(LlmUsageLog.id).label("calls"),
        func.coalesce(func.sum(LlmUsageLog.total_tokens), 0).label("tokens"),
        func.coalesce(func.sum(LlmUsageLog.cost_usd), 0.0).label("cost_usd"),
    ).filter(LlmUsageLog.created_at >= since).group_by(LlmUsageLog.model).order_by(
        func.sum(LlmUsageLog.cost_usd).desc()
    ).all()

    # 按天
    by_day_rows = db.query(
        func.date(LlmUsageLog.created_at).label("day"),
        func.count(LlmUsageLog.id).label("calls"),
        func.coalesce(func.sum(LlmUsageLog.cost_usd), 0.0).label("cost_usd"),
    ).filter(LlmUsageLog.created_at >= since).group_by(
        func.date(LlmUsageLog.created_at)
    ).order_by(func.date(LlmUsageLog.created_at).asc()).all()

    return {
        "since": since.isoformat(),
        "days": days,
        "overall": {
            "calls": int(overall.calls),
            "tokens": int(overall.tokens),
            "cost_usd": round(float(overall.cost_usd), 4),
            "avg_latency_ms": int(overall.avg_latency_ms or 0),
        },
        "by_caller": [
            {"caller": r.caller, "calls": int(r.calls), "tokens": int(r.tokens),
             "cost_usd": round(float(r.cost_usd), 4)}
            for r in by_caller_rows
        ],
        "by_model": [
            {"model": r.model, "calls": int(r.calls), "tokens": int(r.tokens),
             "cost_usd": round(float(r.cost_usd), 4)}
            for r in by_model_rows
        ],
        "by_day": [
            {"day": str(r.day), "calls": int(r.calls), "cost_usd": round(float(r.cost_usd), 4)}
            for r in by_day_rows
        ],
    }
