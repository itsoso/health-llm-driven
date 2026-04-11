"""
GET /api/v1/safety/me —— Safety Guardian 端点。

返回当前用户的所有安全告警（药物相互作用、PGx、急性阈值、肝酶异常等）。
供前端仪表盘和 AI 助理使用。
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.agents.safety_guardian import evaluate_safety
from app.agents.safety_guardian.engine import registry
from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.twin.builder import build_twin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/safety", tags=["safety"])


@router.get("/me")
def get_my_safety_report(
    severity_min: int = Query(0, ge=0, le=4, description="只返回 >= 此严重度的告警"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """
    当前用户的安全告警报告。

    返回结构：
      {
        user_id, generated_at,
        alerts: [{rule_id, category, severity, title, message, action, ...}],
        summary: {total, critical, high, medium, rules_evaluated},
        timing: {twin_build_ms, evaluate_ms}
      }
    """
    twin = build_twin(db, current_user.id)
    report = evaluate_safety(twin)

    if severity_min > 0:
        report.alerts = [a for a in report.alerts if int(a.severity) >= severity_min]

    return report.model_dump_for_api()


@router.get("/rules")
def list_rules(
    current_user: User = Depends(get_current_user_required),
):
    """列出所有已注册的 Safety 规则 —— 透明度用。"""
    return {
        "total": registry.count(),
        "rules": [name for name, _ in registry.all_rules()],
    }
