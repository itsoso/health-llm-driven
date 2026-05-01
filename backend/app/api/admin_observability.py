"""Admin 观察期看板 API.

把 `scripts/observation_dashboard.py` 的 7 模块通过 HTTP 暴露,
让 admin 前端 tab 直接看, 不用 SSH 敲 CLI.

CLI 与本 API 共享 `app/services/observability_service.py`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.database import get_db
from app.models.user import User
from app.services.observability_service import (
    actionable_suggestions,
    collect_dashboard,
    utc_now,
)

router = APIRouter()


@router.get("/dashboard", summary="观察期看板 — 7 模块聚合")
async def get_observation_dashboard(
    days: int = Query(7, ge=1, le=90),
    user_id: Optional[int] = Query(None, description="限定单用户; 不传 = 全量"),
    include_journalctl: bool = Query(False, description="跑 journalctl 扫 tool_validator (仅生产机有效)"),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """聚合 6-7 个观察期信号给 admin 前端展示.

    7 个 section:
      - open_loop: APNs 推送总数 / 反馈分布 / 投递失败
      - clinical_journal: SOAP 条数 / 完整率 / 主题分布
      - memory_kg: Fact / Entity / Relation 总量与窗口内增量
      - doctor_report: NotificationLog 里 doctor/weekly/advisor 类型的状态
      - action_card: 信任循环 (新建/已评分/平均 accuracy)
      - safety_guardian: 评估次数 / 告警累计
      - tool_validator: journalctl 扫 (本地 host 没 systemd 时 skipped)
    """
    report = collect_dashboard(
        db, days=days, user_id=user_id, include_journalctl=include_journalctl,
    )
    return {
        "generated_at": utc_now().isoformat(),
        "window_days": days,
        "user_id": user_id,
        "report": report,
        "suggestions": actionable_suggestions(report),
    }
