# -*- coding: utf-8 -*-
"""抗衰群体证据 admin 看板(Phase3 P3-3)。

只读、admin 鉴权、去标识。把 N-of-1 → N-of-many 聚合露给运营/路演。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from typing import Optional

from app.api.admin import get_admin_user
from app.database import get_db
from app.models.user import User
from app.services.longevity_cohort_service import (
    cohort_biological_age_outcomes,
    cohort_harm_signals,
    cohort_metric_outcomes,
)

router = APIRouter()


@router.get("/cohort", summary="生物年龄群体证据(去标识)")
async def get_longevity_cohort(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """跨用户聚合已评分的生物年龄 N-of-1 outcome,去标识群体证据。"""
    return cohort_biological_age_outcomes(db)


@router.get("/cohort/metrics", summary="任一指标的群体证据(去标识,泛化)")
async def get_cohort_metrics(
    metric: Optional[str] = None,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """群体证据泛化到全 metric;metric 不传 = 全部已评分指标(逗号分隔可多选)。"""
    metrics = [m.strip() for m in metric.split(",")] if metric else None
    return cohort_metric_outcomes(db, metrics)


@router.get("/cohort/harm", summary="反向飞轮 — 群体 harm 信号(去标识)")
async def get_cohort_harm(
    metric: Optional[str] = None,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """flag 在群体里和 worsening 相关的指标(安全/运营预警,observational 非因果)。"""
    metrics = [m.strip() for m in metric.split(",")] if metric else None
    return cohort_harm_signals(db, metrics)
