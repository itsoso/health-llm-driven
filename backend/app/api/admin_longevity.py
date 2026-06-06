# -*- coding: utf-8 -*-
"""抗衰群体证据 admin 看板(Phase3 P3-3)。

只读、admin 鉴权、去标识。把 N-of-1 → N-of-many 聚合露给运营/路演。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.database import get_db
from app.models.user import User
from app.services.longevity_cohort_service import cohort_biological_age_outcomes

router = APIRouter()


@router.get("/cohort", summary="生物年龄群体证据(去标识)")
async def get_longevity_cohort(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """跨用户聚合已评分的生物年龄 N-of-1 outcome,去标识群体证据。"""
    return cohort_biological_age_outcomes(db)
